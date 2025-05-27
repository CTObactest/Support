import os
import logging
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes,
)
from datetime import datetime, timedelta, date
from motor.motor_asyncio import AsyncIOMotorClient
import re

# Enhanced logging for debugging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,  # Changed to DEBUG for more verbose logging
)
logger = logging.getLogger(__name__)

# Disable some noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)

# ––– Constants –––
DERIV_AFFILIATE_LINK = "https://track.deriv.com/_qamZPcT5Sau2vdm9PpHVCmNd7ZgqdRLk/1/"
DERIV_PROCEDURE_LINK_TEXT = "https://t.me/forexbactest/1341"
DERIV_TAGGING_GUIDE_LINK = "https://t.me/derivaccountopeningguide/66"
ADMIN_TELEGRAM_LINK = "https://t.me/Fxbactest_bot"

MIN_DEPOSIT_DERIV_VIP = 50
MIN_DEPOSIT_MENTORSHIP = 50
MIN_DEPOSIT_CURRENCIES_OCTA = 100
MIN_DEPOSIT_CURRENCIES_VANTAGE = 100

# Shortened CR list for testing
CR_NUMBERS_LIST = {
    "CR5499637", "CR5500382", "CR5529877", "CR5535613", "CR5544922"
}

GREETING_KEYWORDS = {
    "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    "what's up", "howdy", "greetings", "hey there",
}

OCTAFX_INFO = (
    "🚀 **Join Currencies Premium Channel (OctaFX) and Access Exclusive Signals!** 🚀\n"
    "Step 1: Open an account https://my.octafx.com/open-account/?refid=ib32402925\n"
    "Step 2: Deposit $100+ then confirm with admins."
)

VANTAGE_INFO = (
    "Unlock the Opportunity with Vantage!\n\n"
    "1. Open a STANDARD account https://vigco.co/VR7F7b (or change IB to 100440).\n"
    "2. Deposit at least $100 then DM admin to join premium channel."
)


class SupportBot:
    def __init__(self, bot_token: str, mongodb_uri: str):
        self.bot_token = bot_token
        self.mongodb_uri = mongodb_uri
        self.db_client: AsyncIOMotorClient | None = None
        self.db = None
        self.pending_connections: dict[str, dict] = {}
        self.bot_healthy = False

    # ––– Database –––
    async def init_database(self):
        try:
            logger.info("Attempting to connect to MongoDB...")
            self.db_client = AsyncIOMotorClient(self.mongodb_uri)
            self.db = self.db_client.support_bot_new
            
            # Test the connection
            await self.db_client.admin.command('ping')
            logger.info("MongoDB ping successful")
            
            await self.db.tickets.create_index("ticket_id", unique=True)
            await self.db.tickets.create_index("user_id")
            await self.db.groups.create_index("group_id", unique=True)
            self.bot_healthy = True
            logger.info("MongoDB connected & indexes ensured")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            self.bot_healthy = False
            raise

    # ––– /start –––
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Start command received from user {update.effective_user.id}")
        
        try:
            user_data = context.user_data
            user_data.clear()

            # Group start ⇒ connect flow
            if update.effective_chat.type in {"group", "supergroup"}:
                logger.info(f"Group start in {update.effective_chat.id}")
                await self.handle_group_start(update, context)
                return

            keyboard = [
                [InlineKeyboardButton("✨ Join VIP/Premium Group", callback_data="select_vip_type")],
                [InlineKeyboardButton("🎓 Get Free Mentorship", callback_data="free_mentorship_start")],
                [InlineKeyboardButton("📊 My Tickets", callback_data="my_tickets")],
                [InlineKeyboardButton("📘 Tagging Guide", url=DERIV_TAGGING_GUIDE_LINK)],
                [InlineKeyboardButton("👤 Contact Admin", url=ADMIN_TELEGRAM_LINK)],
            ]
            text = "Welcome! Choose an option below:"
            markup = InlineKeyboardMarkup(keyboard)
            
            if update.message:
                await update.message.reply_text(text, reply_markup=markup)
                logger.info("Start menu sent successfully")
            elif update.callback_query:
                await update.callback_query.edit_message_text(text, reply_markup=markup)
                logger.info("Start menu edited successfully")
                
        except Exception as e:
            logger.error(f"Error in start_command: {e}")
            try:
                if update.message:
                    await update.message.reply_text("❌ An error occurred. Please try again.")
                elif update.callback_query:
                    await update.callback_query.message.reply_text("❌ An error occurred. Please try again.")
            except Exception as reply_error:
                logger.error(f"Error sending error message: {reply_error}")

    # ––– Messages –––
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Message received from user {update.effective_user.id}: {update.message.text if update.message else 'No text'}")
        
        try:
            if not (msg := update.message) or not msg.text:
                logger.warning("Message has no text content")
                return

            text_lower = msg.text.lower()
            user_data = context.user_data
            flow, step = user_data.get("vip_or_mentorship_flow"), user_data.get("current_step")

            logger.debug(f"Current flow: {flow}, step: {step}")

            # Greetings
            if any(g in text_lower for g in GREETING_KEYWORDS) and not flow:
                reply = "Hello! Use /start to see options." if len(text_lower.split()) <= 2 else "How can I help? Use /start for VIP or mentorship."
                await msg.reply_text(reply)
                logger.info(f"Greeting response sent to user {update.effective_user.id}")
                return

            # Flow‑specific handlers (Deriv VIP, Mentorship, …)
            if flow == "deriv_vip":
                if step == "awaiting_deriv_creation_date":
                    await self.process_deriv_creation_date(update, context, msg.text)
                    return
                if step == "awaiting_deriv_cr_number":
                    await self.process_deriv_cr_number(update, context, msg.text)
                    return
            elif flow == "mentorship" and step == "awaiting_mentorship_cr_number":
                await self.process_mentorship_cr_number(update, context, msg.text)
                return

            # Fallback
            if not flow:
                await msg.reply_text("Message received. Use /start for guided assistance.")
                logger.info(f"Fallback response sent to user {update.effective_user.id}")
                
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
            try:
                await update.message.reply_text("❌ Sorry, an error occurred processing your message.")
            except Exception as reply_error:
                logger.error(f"Error sending error message: {reply_error}")

    # ––– Photos –––
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Photo received from user {update.effective_user.id}")
        
        try:
            if not update.message or not update.message.photo:
                logger.warning("Photo message has no photo content")
                return
            
            user_data = context.user_data
            flow = user_data.get("vip_or_mentorship_flow")
            step = user_data.get("current_step")
            
            logger.debug(f"Photo - Current flow: {flow}, step: {step}")
            
            if flow == "deriv_vip" and step == "awaiting_deposit_proof":
                await self.process_deriv_deposit_proof(update, context)
            elif flow in ["currencies_octa", "currencies_vantage"] and step == "awaiting_deposit_proof":
                await self.process_currencies_deposit_proof(update, context)
            else:
                await update.message.reply_text(
                    "📷 Photo received, but I'm not sure what it's for. Use /start to begin a process."
                )
                
        except Exception as e:
            logger.error(f"Error in handle_photo: {e}")
            try:
                await update.message.reply_text("❌ Error processing your photo. Please try again.")
            except Exception as reply_error:
                logger.error(f"Error sending error message: {reply_error}")

    async def process_deriv_deposit_proof(self, update, context):
        logger.info("Processing Deriv deposit proof")
        try:
            # Create VIP ticket
            ticket_id = f"DERIV_VIP_{update.effective_user.id}_{int(datetime.now().timestamp())}"
            user_data = context.user_data
            
            ticket_data = {
                "ticket_id": ticket_id,
                "user_id": update.effective_user.id,
                "username": update.effective_user.username or "N/A",
                "first_name": update.effective_user.first_name or "N/A",
                "type": "deriv_vip",
                "cr_number": user_data.get("deriv_cr_number"),
                "creation_date": user_data.get("deriv_creation_date"),
                "photo_file_id": update.message.photo[-1].file_id,
                "status": "pending",
                "created_at": datetime.now(),
            }
            
            await self.db.tickets.insert_one(ticket_data)
            
            await update.message.reply_text(
                f"✅ **Deriv VIP Request Submitted!**\n\n"
                f"📋 Ticket ID: `{ticket_id}`\n"
                f"🔢 CR Number: {user_data.get('deriv_cr_number')}\n"
                f"📅 Account Created: {user_data.get('deriv_creation_date')}\n\n"
                f"Your deposit proof has been received and is under review. "
                f"You'll be added to the VIP group within 24 hours if approved.\n\n"
                f"Need help? Contact admin: {ADMIN_TELEGRAM_LINK}",
                parse_mode="Markdown"
            )
            
            logger.info(f"Deriv VIP ticket created: {ticket_id}")
            
        except Exception as e:
            logger.error(f"Failed to create Deriv VIP ticket: {e}")
            await update.message.reply_text(
                "❌ Error processing your request. Please try again or contact admin."
            )
        
        context.user_data.clear()

    async def process_currencies_deposit_proof(self, update, context):
        logger.info("Processing currencies deposit proof")
        try:
            user_data = context.user_data
            flow = user_data.get("vip_or_mentorship_flow")
            broker = "OctaFX" if flow == "currencies_octa" else "Vantage"
            
            ticket_id = f"{broker.upper()}_VIP_{update.effective_user.id}_{int(datetime.now().timestamp())}"
            
            ticket_data = {
                "ticket_id": ticket_id,
                "user_id": update.effective_user.id,
                "username": update.effective_user.username or "N/A",
                "first_name": update.effective_user.first_name or "N/A",
                "type": f"currencies_vip_{broker.lower()}",
                "broker": broker,
                "photo_file_id": update.message.photo[-1].file_id,
                "status": "pending",
                "created_at": datetime.now(),
            }
            
            await self.db.tickets.insert_one(ticket_data)
            
            await update.message.reply_text(
                f"✅ **{broker} VIP Request Submitted!**\n\n"
                f"📋 Ticket ID: `{ticket_id}`\n"
                f"🏦 Broker: {broker}\n\n"
                f"Your deposit proof has been received and is under review. "
                f"You'll be added to the Currencies Premium group within 24 hours if approved.\n\n"
                f"Need help? Contact admin: {ADMIN_TELEGRAM_LINK}",
                parse_mode="Markdown"
            )
            
            logger.info(f"Currencies VIP ticket created: {ticket_id}")
            
        except Exception as e:
            logger.error(f"Failed to create {broker} VIP ticket: {e}")
            await update.message.reply_text(
                "❌ Error processing your request. Please try again or contact admin."
            )
        
        context.user_data.clear()

    # ––– Buttons –––
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"Button callback received: {update.callback_query.data}")
        
        try:
            query = update.callback_query
            await query.answer()
            data, user_data = query.data, context.user_data

            if data == "my_tickets":
                await self.show_user_tickets(query)
                return

            if data == "select_vip_type":  # VIP selection menu
                user_data.clear()
                keyboard = [
                    [InlineKeyboardButton("📈 Deriv VIP (Synthetic)", callback_data="vip_deriv_start")],
                    [InlineKeyboardButton("📊 Currencies VIP", callback_data="vip_currencies_start")],
                    [InlineKeyboardButton("🔙 Back", callback_data="start_command_reset")],
                ]
                await query.edit_message_text("Which VIP/Premium group would you like to join?", reply_markup=InlineKeyboardMarkup(keyboard))
                return

            if data == "start_command_reset":
                await self.start_command(update, context)
                return

            # VIP Flow Handlers
            if data == "vip_deriv_start":
                user_data["vip_or_mentorship_flow"] = "deriv_vip"
                user_data["current_step"] = "awaiting_deriv_creation_date"
                
                await query.edit_message_text(
                    f"📈 **Deriv VIP (Synthetic) Registration**\n\n"
                    f"Requirements:\n"
                    f"• Account opened via our link: {DERIV_AFFILIATE_LINK}\n"
                    f"• Account older than 30 days\n"
                    f"• Minimum deposit: ${MIN_DEPOSIT_DERIV_VIP} USD\n\n"
                    f"First, please enter your Deriv account creation date (YYYY-MM-DD format):"
                )
                return

            if data == "vip_currencies_start":
                user_data.clear()
                keyboard = [
                    [InlineKeyboardButton("🟢 OctaFX", callback_data="currencies_octa_start")],
                    [InlineKeyboardButton("🔵 Vantage", callback_data="currencies_vantage_start")],
                    [InlineKeyboardButton("🔙 Back", callback_data="select_vip_type")],
                ]
                await query.edit_message_text(
                    "📊 **Currencies Premium Group**\n\nChoose your broker:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return

            if data == "currencies_octa_start":
                user_data["vip_or_mentorship_flow"] = "currencies_octa"
                user_data["current_step"] = "awaiting_deposit_proof"
                
                await query.edit_message_text(
                    f"🟢 **OctaFX Premium Registration**\n\n"
                    f"{OCTAFX_INFO}\n\n"
                    f"After completing both steps, please upload a screenshot of your deposit (minimum ${MIN_DEPOSIT_CURRENCIES_OCTA} USD)."
                )
                return

            if data == "currencies_vantage_start":
                user_data["vip_or_mentorship_flow"] = "currencies_vantage"
                user_data["current_step"] = "awaiting_deposit_proof"
                
                await query.edit_message_text(
                    f"🔵 **Vantage Premium Registration**\n\n"
                    f"{VANTAGE_INFO}\n\n"
                    f"After completing both steps, please upload a screenshot of your deposit (minimum ${MIN_DEPOSIT_CURRENCIES_VANTAGE} USD)."
                )
                return

            # Mentorship Flow
            if data == "free_mentorship_start":
                user_data["vip_or_mentorship_flow"] = "mentorship"
                user_data["current_step"] = "awaiting_mentorship_cr_number"
                
                await query.edit_message_text(
                    f"🎓 **Free Mentorship Program**\n\n"
                    f"Requirements:\n"
                    f"• Deriv account opened via our link: {DERIV_AFFILIATE_LINK}\n"
                    f"• Basic understanding of trading concepts\n"
                    f"• Commitment to learning\n\n"
                    f"Please provide your Deriv CR number to continue:"
                )
                return
                
            logger.warning(f"Unhandled callback: {data}")
            
        except Exception as e:
            logger.error(f"Error in button_callback: {e}")
            try:
                await update.callback_query.message.reply_text("❌ An error occurred. Please try again.")
            except Exception as reply_error:
                logger.error(f"Error sending error message: {reply_error}")

    # ––– Helper Methods –––
    async def process_deriv_creation_date(self, update, context, date_text):
        logger.info(f"Processing Deriv creation date: {date_text}")
        try:
            # Parse date (expecting format like "2024-01-15" or similar)
            creation_date = datetime.strptime(date_text.strip(), "%Y-%m-%d").date()
            days_old = (date.today() - creation_date).days
            
            if days_old < 30:
                await update.message.reply_text(
                    f"⚠️ Your account is only {days_old} days old. "
                    "Deriv VIP requires accounts older than 30 days. Please try again later."
                )
                context.user_data.clear()
                return
            
            context.user_data["deriv_creation_date"] = date_text
            context.user_data["current_step"] = "awaiting_deriv_cr_number"
            
            await update.message.reply_text(
                "✅ Account age verified! Now please provide your Deriv CR number:"
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid date format. Please use YYYY-MM-DD format (e.g., 2024-01-15):"
            )

    async def process_deriv_cr_number(self, update, context, cr_number_text):
        logger.info(f"Processing Deriv CR number: {cr_number_text}")
        cr_number = cr_number_text.strip().upper()
        
        if cr_number not in CR_NUMBERS_LIST:
            await update.message.reply_text(
                f"❌ CR number {cr_number} not found in our affiliate list.\n"
                f"Please open your account using our link: {DERIV_AFFILIATE_LINK}\n"
                "Then provide the correct CR number."
            )
            return
        
        context.user_data["deriv_cr_number"] = cr_number
        context.user_data["current_step"] = "awaiting_deposit_proof"
        
        await update.message.reply_text(
            f"✅ CR number {cr_number} verified!\n\n"
            f"Now please upload a screenshot showing your deposit of at least ${MIN_DEPOSIT_DERIV_VIP} USD.\n"
            "The screenshot should clearly show the amount and your account details."
        )

    async def process_mentorship_cr_number(self, update, context, cr_number_text):
        logger.info(f"Processing mentorship CR number: {cr_number_text}")
        cr_number = cr_number_text.strip().upper()
        
        if cr_number not in CR_NUMBERS_LIST:
            await update.message.reply_text(
                f"❌ CR number {cr_number} not found in our affiliate list.\n"
                f"Please open your account using our link: {DERIV_AFFILIATE_LINK}\n"
                "Then provide the correct CR number."
            )
            return
        
        # Create ticket for mentorship
        ticket_id = f"MENTOR_{update.effective_user.id}_{int(datetime.now().timestamp())}"
        
        ticket_data = {
            "ticket_id": ticket_id,
            "user_id": update.effective_user.id,
            "username": update.effective_user.username or "N/A",
            "first_name": update.effective_user.first_name or "N/A",
            "type": "mentorship",
            "cr_number": cr_number,
            "status": "pending",
            "created_at": datetime.now(),
        }
        
        try:
            await self.db.tickets.insert_one(ticket_data)
            
            await update.message.reply_text(
                f"🎓 **Mentorship Request Submitted!**\n\n"
                f"📋 Ticket ID: `{ticket_id}`\n"
                f"🔢 CR Number: {cr_number}\n\n"
                f"Your request has been forwarded to our mentors. "
                f"You'll be contacted within 24 hours.\n\n"
                f"Need immediate help? Contact admin: {ADMIN_TELEGRAM_LINK}",
                parse_mode="Markdown"
            )
            
            logger.info(f"Mentorship ticket created: {ticket_id}")
            
        except Exception as e:
            logger.error(f"Failed to create mentorship ticket: {e}")
            await update.message.reply_text(
                "❌ Error processing your request. Please try again or contact admin."
            )
        
        context.user_data.clear()

    async def show_user_tickets(self, query):
        logger.info(f"Showing tickets for user {query.from_user.id}")
        user_id = query.from_user.id
        
        try:
            tickets = await self.db.tickets.find({"user_id": user_id}).sort("created_at", -1).limit(10).to_list(length=10)
            
            if not tickets:
                await query.edit_message_text(
                    "📊 **My Tickets**\n\nYou have no tickets yet.\n\nUse /start to create VIP or mentorship requests."
                )
                return
            
            text = "📊 **My Tickets**\n\n"
            for ticket in tickets:
                status_emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(ticket.get("status", "pending"), "❓")
                created = ticket.get("created_at", datetime.now()).strftime("%Y-%m-%d %H:%M")
                
                text += (
                    f"{status_emoji} **{ticket.get('type', 'Unknown').title()}**\n"
                    f"🆔 `{ticket.get('ticket_id', 'N/A')}`\n"
                    f"📅 {created}\n"
                    f"📊 Status: {ticket.get('status', 'pending').title()}\n\n"
                )
            
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="start_command_reset")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error fetching user tickets: {e}")
            await query.edit_message_text("❌ Error loading tickets. Please try again later.")

    async def handle_group_start(self, update, context):
        logger.info(f"Handling group start for {update.effective_chat.id}")
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "Unknown Group"
        
        # Store group connection request
        group_data = {
            "group_id": chat_id,
            "group_title": chat_title,
            "status": "pending",
            "requested_at": datetime.now(),
        }
        
        try:
            await self.db.groups.update_one(
                {"group_id": chat_id},
                {"$set": group_data},
                upsert=True
            )
            
            await update.message.reply_text(
                f"🤖 **Bot Connection Request**\n\n"
                f"Group: {chat_title}\n"
                f"ID: `{chat_id}`\n\n"
                f"Connection request logged. Admin will review and activate the bot for this group.\n\n"
                f"Contact admin: {ADMIN_TELEGRAM_LINK}",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Failed to store group connection: {e}")
            await update.message.reply_text(
                "❌ Error processing group connection request. Please contact admin directly."
            )


# ––– Health Check Server –––
async def health_check(request):
    """Simple health check endpoint"""
    return web.Response(text="OK", status=200)

async def create_health_server():
    """Create a simple HTTP server for health checks"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)  # Some platforms check root
    return app

# ––– Main App –––
async def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    mongodb_uri = os.getenv("MONGODB_URI")
    port = int(os.getenv("PORT", 8080))

    if not bot_token or not mongodb_uri:
        logger.error("Env vars TELEGRAM_BOT_TOKEN / MONGODB_URI not set.")
        return

    logger.info("Starting bot initialization...")
    logger.info(f"Bot token (first 10 chars): {bot_token[:10]}...")
    logger.info(f"MongoDB URI (first 20 chars): {mongodb_uri[:20]}...")

    bot_app = SupportBot(bot_token, mongodb_uri)
    
    try:
        await bot_app.init_database()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return

    # Setup Telegram bot
    application = Application.builder().token(bot_token).build()

    # Test bot connection
    try:
        bot_info = await application.bot.get_me()
        logger.info(f"Bot connected successfully: @{bot_info.username} ({bot_info.first_name})")
    except Exception as e:
        logger.error(f"Failed to connect to Telegram: {e}")
        return

    # Add handlers
    application.add_handler(CommandHandler("start", bot_app.start_command))
    application.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("Use /start for options.")))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_app.handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, bot_app.handle_photo))
    application.add_handler(CallbackQueryHandler(bot_app.button_callback))

    logger.info("Handlers registered successfully")

    # Setup health check server
    health_app = await create_health_server()
    
    # Define bot and server runners
    async def run_bot():
        try:
            logger.info("Starting bot polling...")
            await application.run_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
                poll_interval=1.0,
                timeout=10
            )
            logger.info("Telegram bot polling exited normally")
        except Exception as e:
            logger.error(f"Bot polling crashed: {e}")
            raise

    async def run_health_server():
        try:
            runner = web.AppRunner(health_app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            logger.info(f"Health check server running on port {port}")
            
            # Keep the server running
            while True:
                await asyncio.sleep(3600)  # Sleep for 1 hour, then continue
                
        except Exception as e:
            logger.error(f"Failed to start health server: {e}")
            raise

    # Run both concurrently
    logger.info("Starting both bot and health server...")
    try:
        await asyncio.gather(
            run_bot(),
            run_health_server(),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"Main execution failed: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
