import os
import logging
import asyncio
import re
from datetime import datetime, timedelta
from bson import ObjectId

from telegram import (Update, InlineKeyboardButton,
                      InlineKeyboardMarkup, InputMediaPhoto)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)
from motor.motor_asyncio import AsyncIOMotorClient
from aiohttp import web

# =============================================================
#  FOREX‑Backtest Support & Verification Bot
#  ----------------------------------------
#  Tailored version of the generic SupportBot for @forexbactest
#  Company‑specific flows implemented:
#  • Deriv VIP verification (incl. CR number + deposit check)
#  • Currencies VIP quick ticket
#  • Free Mentorship flow (Deriv + $50 deposit)
#  • Custom knowledge‑base starter entries removed (company will
#    manage its own KB via the DB UI or separate script)
# =============================================================

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


class SupportBot:
    """FOREX‑Backtest tailored support bot"""

    VIP_CR_WHITELIST = {
        "CR5499637",
        "CR5500382",
        "CR5529877",
        "CR5535613",
    }

    REQUIRED_DERIV_DEPOSIT = 50

    def __init__(self, bot_token: str, mongodb_uri: str):
        self.bot_token = bot_token
        self.mongodb_uri = mongodb_uri
        self.db_client = None
        self.db = None

        # generic state trackers -----------------------------------
        self.pending_tickets: dict[int, dict] = {}
        self.pending_connections: dict[str, dict] = {}

        # company‑specific state trackers --------------------------
        # structure: {user_id: {"flow": str, "step": int, "data": {…}}}
        self.pending_verifications: dict[int, dict] = {}

    # -------------------------------------------------------------
    #  Mongo / KB helpers
    # -------------------------------------------------------------
    async def init_database(self):
        self.db_client = AsyncIOMotorClient(self.mongodb_uri)
        self.db = self.db_client.support_bot

        await self.db.tickets.create_index("ticket_id", unique=True)
        await self.db.tickets.create_index("user_id")
        await self.db.groups.create_index("group_id", unique=True)
        await self.db.knowledge_base.create_index("question")
        await self.db.knowledge_base.create_index("keywords")

        # Remove generic default KB & insert minimal starter if empty
        if await self.db.knowledge_base.count_documents({}) == 0:
            starter_kb = [
                {
                    "question": "how to join deriv vip",
                    "answer": "Click *VIP / Mentorship* → choose *Deriv VIP* and follow the guided verification.",
                    "category": "vip",
                    "keywords": ["deriv", "vip", "cr", "deposit"],
                },
                {
                    "question": "free mentorship requirements",
                    "answer": "Open a Deriv account through our link and deposit at least $50, then complete verification via the bot.",
                    "category": "mentorship",
                    "keywords": ["mentorship", "free", "deriv"],
                },
            ]
            await self.db.knowledge_base.insert_many(starter_kb)
            logger.info("Starter company knowledge‑base initialised")

        logger.info("Database initialised")

    async def get_support_groups(self):
        cursor = self.db.groups.find({"status": "active"})
        return await cursor.to_list(length=None)

    # -------------------------------------------------------------
    #  /start & Main Menu
    # -------------------------------------------------------------
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type in ["group", "supergroup"]:
            await self.handle_group_start(update, context)
            return

        keyboard = [
            [InlineKeyboardButton("🎖️ VIP / Mentorship", callback_data="vip_start")],
            [InlineKeyboardButton("📚 Browse FAQ", callback_data="faq")],
            [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="create_ticket")],
            [InlineKeyboardButton("📊 My Tickets", callback_data="my_tickets")],
            [InlineKeyboardButton("❓ Help", callback_data="help")],
        ]
        welcome_text = (
            "👋 *Welcome to FOREX‑Backtest Support Bot!*\n\n"
            "I can help you with:"
            "\n• VIP verification & premium access"
            "\n• Free mentorship enrolment"
            "\n• General support tickets and FAQs\n\n"
            "_What would you like to do?_"
        )
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

    # -------------------------------------------------------------
    #  VIP / Mentorship flow (callback entry‑point)
    # -------------------------------------------------------------
    async def vip_start_flow(self, query):
        keyboard = [
            [InlineKeyboardButton("💎 Deriv VIP", callback_data="vip_deriv")],
            [InlineKeyboardButton("🚀 Currencies VIP", callback_data="vip_currencies")],
            [InlineKeyboardButton("🎓 Free Mentorship", callback_data="vip_mentorship")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")],
        ]
        await query.edit_message_text(
            "🎖️ *VIP / Mentorship*\n\n"
            "Which service would you like to be enrolled in?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )

    # -------------------------------------------------------------
    #  Callback dispatcher
    # -------------------------------------------------------------
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data

        # ===== Company‑specific entries first =====
        if data == "vip_start":
            await self.vip_start_flow(query)
            return
        if data.startswith("vip_"):
            await self.handle_vip_callback(query, data)
            return

        # ===== Generic callbacks (original bot) =====
        if data == "faq":
            await self.show_faq_categories(query)
        elif data == "create_ticket":
            await self.start_ticket_creation(query)
        elif data == "my_tickets":
            await self.show_user_tickets(query)
        elif data == "help":
            await self.show_help_inline(query)
        elif data.startswith("connect_"):
            await self.process_group_connection(query, data)
        elif data == "cancel_connection":
            await query.edit_message_text("❌ Connection request cancelled.")
        elif data.startswith("category_"):
            await self.set_ticket_category(query, data.replace("category_", ""))
        elif data.startswith("faq_cat_"):
            await self.show_faq_for_category(query, data.replace("faq_cat_", ""))
        elif data.startswith("faq_item_"):
            await self.show_faq_answer(query, data.replace("faq_item_", ""))
        elif data.startswith("ticket_"):
            await self.show_ticket_details(query, data.replace("ticket_", ""))
        elif data == "back_to_menu":
            await self.start_command(update, context)
        elif data.startswith("take_"):
            await self.handle_take_ticket(query, context, data.split("_", 1)[1])
        elif data.startswith("close_"):
            await self.handle_close_ticket(query, context, data.split("_", 1)[1])

    # -------------------------------------------------------------
    #  VIP Callback handler (Deriv / Currencies / Mentorship)
    # -------------------------------------------------------------
    async def handle_vip_callback(self, query, data):
        user_id = query.from_user.id

        if data == "vip_deriv":
            # Step 0 → Ask about account creation
            self.pending_verifications[user_id] = {
                "flow": "deriv_vip",
                "step": 1,
                "data": {},
            }
            await query.edit_message_text(
                "💎 *Deriv VIP Verification*\n\n"
                "Have you *already created* your Deriv account *following this procedure*?\n"
                "https://t.me/forexbactest/1341\n\n"
                "Please reply with *Yes* or *No*.",
                parse_mode="Markdown",
            )
            return

        if data == "vip_currencies":
            # Immediate ticket — no further checks
            description = "Request to join Currencies VIP premium channel."
            await self.create_company_ticket(query.from_user, "Currencies VIP", description)
            await query.edit_message_text(
                "✅ Your request has been logged. Our admin team will add you to *Currencies VIP* shortly.",
                parse_mode="Markdown",
            )
            return

        if data == "vip_mentorship":
            # Start mentorship flow
            self.pending_verifications[user_id] = {
                "flow": "mentorship",
                "step": 1,
                "data": {},
            }
            await query.edit_message_text(
                "🎓 *Free Mentorship*\n\n"
                "1️⃣ If you *already* have a Deriv account, please provide your *CR number* so that we can verify it.\n"
                "2️⃣ If you *don't have* a Deriv account, open one with our link first:\n"
                "https://track.deriv.com/_qamZPcT5Sau2vdm9PpHVCmNd7ZgqdRLk/1/\n\n"
                "Once done, *deposit at least $50* and send the *deposit screenshot*.\n\n"
                "Please reply now with either your CR number or the word *Done* once you have finished all steps.",
                parse_mode="Markdown",
            )
            return

    # -------------------------------------------------------------
    #  Main text message handler (includes verification FSM)
    # -------------------------------------------------------------
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return

        user_id = update.effective_user.id

        # Company‑specific pending verification
        if user_id in self.pending_verifications:
            await self.process_verification_step(update)
            return

        # ---------- Existing generic logic ----------
        if update.effective_chat.type in ["group", "supergroup"]:
            bot_username = context.bot.username
            text = update.message.text or ""
            is_reply_to_bot = (
                update.message.reply_to_message and
                update.message.reply_to_message.from_user.id == context.bot.id
            )
            is_mention = f"@{bot_username}".lower() in text.lower() if bot_username else False
            if not (is_reply_to_bot or is_mention):
                return

        user_message_full = (update.message.text or "").strip()
        if not user_message_full:
            return

        # pending generic ticket? ---------------------------------
        if user_id in self.pending_tickets:
            await self.process_ticket_input(update, context, user_message_full)
            return

        # not in a ticket: search KB or suggest ticket ------------
        results = await self.search_knowledge_base(user_message_full)
        if results:
            response = "🔍 *Found these relevant answers:*\n\n"
            for i, result in enumerate(results, 1):
                response += f"*{i}. {result['question'].title()}*\n{result['answer']}\n\n"
            keyboard = [
                [InlineKeyboardButton("🎫 Still need help? Create ticket", callback_data="create_ticket")],
                [InlineKeyboardButton("📚 Browse all FAQ", callback_data="faq")],
            ]
            await update.message.reply_text(response, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            keyboard = [
                [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="create_ticket")],
                [InlineKeyboardButton("📚 Browse FAQ", callback_data="faq")],
            ]
            await update.message.reply_text(
                "🤔 I couldn't find a specific answer. Want to create a support ticket?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    # -------------------------------------------------------------
    async def process_verification_step(self, update: Update):
        """Finite‑state machine for Deriv VIP and Mentorship flows"""
        user_id = update.effective_user.id
        state = self.pending_verifications[user_id]
        text = (update.message.text or "").strip()
        flow = state["flow"]
        step = state["step"]
        data = state["data"]

        # ====== Deriv VIP ======
        if flow == "deriv_vip":
            if step == 1:
                # Expect Yes/No about account creation
                if text.lower() not in {"yes", "no", "y", "n"}:
                    await update.message.reply_text("Please answer *Yes* or *No*.", parse_mode="Markdown")
                    return
                if text.lower() in {"no", "n"}:
                    await update.message.reply_text(
                        "Please create your Deriv account first via the guide link above, then come back once done."
                    )
                    del self.pending_verifications[user_id]
                    return
                # If Yes → ask for creation date
                state["step"] = 2
                await update.message.reply_text(
                    "Great! On *what date* did you create the account? (Format: YYYY‑MM‑DD)",
                    parse_mode="Markdown",
                )
                return

            if step == 2:
                # Parse creation date
                try:
                    created_dt = datetime.strptime(text, "%Y-%m-%d")
                except ValueError:
                    await update.message.reply_text("Date format should be YYYY‑MM‑DD. Please try again.")
                    return
                age = datetime.utcnow() - created_dt
                if age < timedelta(days=1):
                    await update.message.reply_text(
                        "Your account is less than a day old. Please wait up to *24 hours* for it to reflect in our system and then restart the verification.",
                        parse_mode="Markdown",
                    )
                    del self.pending_verifications[user_id]
                    return
                # Age ok → ask CR number
                data["created_date"] = created_dt.isoformat()
                state["step"] = 3
                await update.message.reply_text(
                    "Please provide your CR number in the format *CR12345*.",
                    parse_mode="Markdown",
                )
                return

            if step == 3:
                cr_match = re.fullmatch(r"CR\d{5,8}", text.upper())
                if not cr_match:
                    await update.message.reply_text("Invalid format. It should look like CR12345.")
                    return
                cr = cr_match.group()
                data["cr"] = cr
                if cr in self.VIP_CR_WHITELIST:
                    # Tagged under us
                    state["step"] = 4
                    await update.message.reply_text(
                        "✅ I can verify that you are tagged under us.\n"
                        "Please *fund your account with at least $50* and *send me a screenshot* of your balance (or forward the deposit confirmation).",
                        parse_mode="Markdown",
                    )
                else:
                    state["step"] = 30  # branch for not‑tagged
                    await update.message.reply_text(
                        "❌ I couldn't find that CR in our list.\n"
                        "— Are you tagged under our partner *Kennedynespot*? (Yes/No)"
                    )
                return

            if step == 30:
                if text.lower() not in {"yes", "no", "y", "n"}:
                    await update.message.reply_text("Please reply Yes or No.")
                    return
                if text.lower() in {"yes", "y"}:
                    state["step"] = 31
                    await update.message.reply_text(
                        "Great. Please send a *screenshot* showing the confirmation that you are tagged under Kennedynespot."
                    )
                    return
                # Not tagged → send guide then end
                await update.message.reply_text(
                    "Please follow the tagging guide first: https://t.me/derivaccountopeningguide/66\n"
                    "After 24 hours, start the verification again."
                )
                del self.pending_verifications[user_id]
                return

            if step in {4, 31}:
                # Expect screenshot (photo)
                await update.message.reply_text("Please send the screenshot as an *image attachment*.", parse_mode="Markdown")
                return

            if step == 5:
                # Expect numeric deposit amount after screenshot (fallback)
                try:
                    amount = float(re.search(r"\d+(?:\.\d+)?", text).group())
                except Exception:
                    await update.message.reply_text("Please send the amount as a number (e.g. 50).")
                    return
                if amount < self.REQUIRED_DERIV_DEPOSIT:
                    await update.message.reply_text(
                        f"It looks like the deposit is below ${self.REQUIRED_DERIV_DEPOSIT}. Please fund at least ${self.REQUIRED_DERIV_DEPOSIT} and try again."
                    )
                    del self.pending_verifications[user_id]
                    return
                description = (
                    "Deriv VIP verification completed.\n"
                    f"CR: {data['cr']}\nDeposit: ${amount:.2f}"
                )
                await self.create_company_ticket(update.effective_user, "Deriv VIP", description)
                await update.message.reply_text(
                    "🎉 All set! Your Deriv VIP request has been logged. Our admin team will add you shortly."
                )
                del self.pending_verifications[user_id]
                return

        # ====== Mentorship ======
        if flow == "mentorship":
            if step == 1:
                # Expect CR number or the word Done
                if text.lower() == "done":
                    await update.message.reply_text(
                        "Once your deposit is visible, send a *screenshot* of your account balance >= $50."
                    )
                    state["step"] = 2  # waiting for screenshot
                    return
                cr_match = re.fullmatch(r"CR\d{5,8}", text.upper())
                if not cr_match:
                    await update.message.reply_text("Please provide a valid CR number or the word Done.")
                    return
                data["cr"] = cr_match.group()
                await update.message.reply_text(
                    "Thank you. Now send a *screenshot* showing a balance of at least $50."
                )
                state["step"] = 2
                return
            if step == 3:
                # Expect deposit amount numeric
                try:
                    amount = float(re.search(r"\d+(?:\.\d+)?", text).group())
                except Exception:
                    await update.message.reply_text("Send the amount as a plain number (e.g. 75).")
                    return
                if amount < 50:
                    await update.message.reply_text("Deposit must be at least $50.")
                    del self.pending_verifications[user_id]
                    return
                description = "Free Mentorship verification completed."
                if "cr" in data:
                    description += f" CR: {data['cr']}"
                description += f" Deposit: ${amount:.2f}"
                await self.create_company_ticket(update.effective_user, "Free Mentorship", description)
                await update.message.reply_text(
                    "✅ You are enrolled for free mentorship! Our mentors will reach out soon."
                )
                del self.pending_verifications[user_id]
                return

        # fallback -----------------------------------------------
        await update.message.reply_text("⚠️ Sorry, I didn't understand. Please restart with /start.")
        del self.pending_verifications[user_id]

    # -------------------------------------------------------------
    #  Photo handler (for screenshots)
    # -------------------------------------------------------------
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in self.pending_verifications:
            return
        state = self.pending_verifications[user_id]
        flow = state["flow"]
        step = state["step"]

        # Save file or just acknowledge (not stored)
        await update.message.reply_text("✅ Screenshot received.")

        if flow == "deriv_vip" and step in {4, 31}:
            # Ask for numeric amount if caption didn't include
            caption = update.message.caption or ""
            amount_match = re.search(r"\d+(?:\.\d+)?", caption)
            if amount_match and float(amount_match.group()) >= self.REQUIRED_DERIV_DEPOSIT:
                description = (
                    "Deriv VIP verification completed.\n"
                    f"CR: {state['data'].get('cr', 'N/A')}\nDeposit: ${float(amount_match.group()):.2f}"
                )
                await self.create_company_ticket(update.effective_user, "Deriv VIP", description)
                await update.message.reply_text(
                    "🎉 All set! Your Deriv VIP request has been logged. Our admin team will add you shortly."
                )
                del self.pending_verifications[user_id]
            else:
                await update.message.reply_text(
                    "Now, please send the *deposit amount* as a number (e.g. 55)."
                )
                state["step"] = 5  # await amount
            return

        if flow == "mentorship" and step == 2:
            caption = update.message.caption or ""
            amount_match = re.search(r"\d+(?:\.\d+)?", caption)
            if amount_match and float(amount_match.group()) >= 50:
                description = "Free Mentorship verification completed. "
                if "cr" in state["data"]:
                    description += f"CR: {state['data']['cr']} "
                description += f"Deposit: ${float(amount_match.group()):.2f}"
                await self.create_company_ticket(update.effective_user, "Free Mentorship", description)
                await update.message.reply_text("✅ You are enrolled for free mentorship! Our mentors will reach out soon.")
                del self.pending_verifications[user_id]
            else:
                await update.message.reply_text("Please send the deposit amount as a number (e.g. 80).")
                state["step"] = 3

    # -------------------------------------------------------------
    #  Helper: create ticket quickly from verifications
    # -------------------------------------------------------------
    async def create_company_ticket(self, user, category: str, description: str):
        """Wrapper around the generic ticket creation, used by VIP flows"""
        ticket_id = f"TKT-{datetime.utcnow().strftime('%Y%m%d')}-{int(datetime.utcnow().timestamp())%100000:05d}"
        ticket_doc = {
            "ticket_id": ticket_id,
            "user_id": user.id,
            "user_info": {
                "id": user.id,
                "username": user.username,
                "name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "N/A",
            },
            "category": category,
            "description": description,
            "status": "open",
            "priority": "high",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "messages": [],
        }
        await self.db.tickets.insert_one(ticket_doc)
        await self.forward_to_support_groups(None, ticket_doc)  # forward without context (uses bot in forward func)

    # -------------------------------------------------------------
    #  Existing helper functions from original bot (unchanged)
    #  ... [Due to space, they are elided here.  All methods not
    #       explicitly redefined remain identical to the original
    #       generic SupportBot implementation supplied earlier.] ...

    # NOTE: In the actual implementation file, **copy the rest of the
    # original SupportBot methods without modification**, or `import`
    # them from the previous module, to keep this example concise.


# =============================================================
#  Bot bootstrap (unchanged apart from registering new handlers)
# =============================================================

async def main_async_logic():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")

    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN env var missing")

    support_bot = SupportBot(bot_token, mongodb_uri)
    await support_bot.init_database()

    app = Application.builder().token(bot_token).build()

    # Command handlers
    app.add_handler(CommandHandler("start", support_bot.start_command))
    app.add_handler(CommandHandler("help", support_bot.show_help_inline))
    app.add_handler(CommandHandler("connect", support_bot.connect_command))
    app.add_handler(CommandHandler("disconnect", support_bot.disconnect_command))

    # Callback queries
    app.add_handler(CallbackQueryHandler(support_bot.button_callback))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, support_bot.handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, support_bot.handle_message))

    await app.initialize()
    await app.start()
    logger.info("Bot started — polling mode active.")

    # Simplified — polling only for this deployment
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main_async_logic())
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
