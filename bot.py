import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import aiohttp
import json
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import re

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class SupportBot:
    def __init__(self, bot_token, mongodb_uri):
        self.bot_token = bot_token
        self.mongodb_uri = mongodb_uri
        self.db_client = None
        self.db = None
        self.pending_tickets = {}
        self.pending_connections = {}  # Store pending group connections
        
    async def init_database(self):
        """Initialize MongoDB connection"""
        try:
            self.db_client = AsyncIOMotorClient(self.mongodb_uri)
            self.db = self.db_client.support_bot
            
            # Create indexes
            await self.db.tickets.create_index("ticket_id", unique=True)
            await self.db.tickets.create_index("user_id")
            await self.db.groups.create_index("group_id", unique=True)
            await self.db.knowledge_base.create_index("question")
            
            # Initialize default knowledge base if empty
            if await self.db.knowledge_base.count_documents({}) == 0:
                await self.init_default_knowledge_base()
                
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    async def init_default_knowledge_base(self):
        """Initialize default knowledge base entries"""
        default_kb = [
            {
                "question": "how to login",
                "answer": "To login, visit our website and click 'Sign In' in the top right corner.",
                "category": "account",
                "keywords": ["login", "sign in", "access", "enter"]
            },
            {
                "question": "reset password",
                "answer": "Click 'Forgot Password' on the login page and follow the email instructions.",
                "category": "account",
                "keywords": ["password", "reset", "forgot", "change"]
            },
            {
                "question": "pricing plans",
                "answer": "We offer Basic ($9/month), Pro ($19/month), and Enterprise ($49/month) plans.",
                "category": "billing",
                "keywords": ["price", "cost", "plan", "subscription", "billing"]
            },
            {
                "question": "refund policy",
                "answer": "We offer full refunds within 30 days of purchase, no questions asked.",
                "category": "billing",
                "keywords": ["refund", "money back", "return", "cancel"]
            },
            {
                "question": "technical support",
                "answer": "For technical issues, please create a support ticket with detailed information about the problem.",
                "category": "technical",
                "keywords": ["bug", "error", "problem", "issue", "broken"]
            }
        ]
        
        await self.db.knowledge_base.insert_many(default_kb)
        logger.info("Default knowledge base initialized")

    async def get_support_groups(self):
        """Get all connected support groups"""
        cursor = self.db.groups.find({"status": "active"})
        return await cursor.to_list(length=None)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        # Check if this is a group and bot was just added
        if update.effective_chat.type in ['group', 'supergroup']:
            await self.handle_group_start(update, context)
            return
            
        keyboard = [
            [InlineKeyboardButton("📚 Browse FAQ", callback_data="faq")],
            [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="create_ticket")],
            [InlineKeyboardButton("📊 My Tickets", callback_data="my_tickets")],
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            "👋 Welcome to Support Bot!\n\n"
            "I'm here to help you with:\n"
            "• Quick answers from our FAQ\n"
            "• Creating support tickets\n"
            "• Tracking your support requests\n"
            "• Connecting you with our support team\n\n"
            "What would you like to do?"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def handle_group_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle bot being added to a group"""
        chat = update.effective_chat
        user = update.effective_user
        
        # Check if user is admin
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ['administrator', 'creator']:
                await update.message.reply_text(
                    "❌ Only group administrators can connect this group as a support group."
                )
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return

        # Check if group is already connected
        existing_group = await self.db.groups.find_one({"group_id": chat.id})
        if existing_group:
            if existing_group.get("status") == "active":
                await update.message.reply_text(
                    f"✅ This group is already connected as a support group!\n"
                    f"Connected on: {existing_group.get('connected_at', 'Unknown')}"
                )
            else:
                # Reactivate the group
                await self.db.groups.update_one(
                    {"group_id": chat.id},
                    {"$set": {"status": "active", "reactivated_at": datetime.now()}}
                )
                await update.message.reply_text(
                    "✅ Support group reactivated successfully!"
                )
            return

        # Store pending connection
        connection_code = f"CONNECT_{chat.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.pending_connections[connection_code] = {
            "group_id": chat.id,
            "group_name": chat.title,
            "admin_id": user.id,
            "admin_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "expires_at": datetime.now() + timedelta(minutes=10)
        }

        keyboard = [
            [InlineKeyboardButton("🔗 Connect as Support Group", callback_data=f"connect_{connection_code}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_connection")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🔗 **Connect Support Group**\n\n"
            f"Group: {chat.title}\n"
            f"Admin: {user.first_name}\n\n"
            f"Click the button below to connect this group as a support group. "
            f"Support tickets will be forwarded here for your team to handle.\n\n"
            f"⏰ This connection request expires in 10 minutes.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /connect command for manual group connection"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text(
                "❌ The /connect command can only be used in groups."
            )
            return
            
        await self.handle_group_start(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(  # This line was not indented
            "❓ *How to use this bot:*\n\n"
            "• Use /start to begin\n"
            "• Use /connect to link support groups\n"
            "• Use /disconnect to unlink\n"
            "• Ask questions directly or use the buttons\n\n"
            "ℹ️ You can also click 'Help' from the main menu!",
            parse_mode="Markdown"
        )

    async def disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /disconnect command"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text(
                "❌ The /disconnect command can only be used in groups."
            )
            return

        chat = update.effective_chat
        user = update.effective_user
        
        # Check if user is admin
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ['administrator', 'creator']:
                await update.message.reply_text(
                    "❌ Only group administrators can disconnect the support group."
                )
                return
        except Exception:
            return

        # Disconnect the group
        result = await self.db.groups.update_one(
            {"group_id": chat.id},
            {"$set": {"status": "inactive", "disconnected_at": datetime.now()}}
        )

        if result.modified_count > 0:
            await update.message.reply_text(
                "✅ Support group disconnected successfully. "
                "No new tickets will be forwarded to this group."
            )
        else:
            await update.message.reply_text(
                "❌ This group is not connected as a support group."
            )

    async def search_knowledge_base(self, query: str):
        """Search knowledge base for relevant answers"""
        query_lower = query.lower()
        
        # Search by keywords and question text
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"keywords": {"$in": [{"$regex": word, "$options": "i"} for word in query_lower.split()]}},
                        {"question": {"$regex": query_lower, "$options": "i"}},
                        {"answer": {"$regex": query_lower, "$options": "i"}}
                    ]
                }
            },
            {"$limit": 3}
        ]
        
        cursor = self.db.knowledge_base.aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages"""
        # Skip group messages that don't mention the bot
        if update.effective_chat.type in ['group', 'supergroup']:
            # Only respond to messages that mention the bot or reply to bot messages
            bot_username = context.bot.username
            text = update.message.text.lower()
            
            is_reply_to_bot = (update.message.reply_to_message and 
                             update.message.reply_to_message.from_user.id == context.bot.id)
            is_mention = f"@{bot_username}".lower() in text if bot_username else False
            
            if not (is_reply_to_bot or is_mention):
                return

        user_message = update.message.text
        user_id = update.effective_user.id
        
        # Remove bot mention from message
        if context.bot.username:
            user_message = re.sub(f'@{context.bot.username}', '', user_message, flags=re.IGNORECASE).strip()
        
        # Check if user is in ticket creation mode
        if user_id in self.pending_tickets:
            await self.process_ticket_input(update, context)
            return
        
        # Search knowledge base
        results = await self.search_knowledge_base(user_message)
        
        if results:
            response = "🔍 **Found these relevant answers:**\n\n"
            for i, result in enumerate(results, 1):
                response += f"**{i}. {result['question'].title()}**\n"
                response += f"{result['answer']}\n\n"
            
            keyboard = [
                [InlineKeyboardButton("🎫 Still need help? Create ticket", callback_data="create_ticket")],
                [InlineKeyboardButton("📚 Browse all FAQ", callback_data="faq")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="create_ticket")],
                [InlineKeyboardButton("📚 Browse FAQ", callback_data="faq")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🤔 I couldn't find a specific answer to your question.\n"
                "Would you like to create a support ticket or browse our FAQ?",
                reply_markup=reply_markup
            )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "faq":
            await self.show_faq(query)
        elif query.data == "create_ticket":
            await self.start_ticket_creation(query)
        elif query.data == "my_tickets":
            await self.show_user_tickets(query)
        elif query.data == "help":
            await self.show_help_inline(query)
        elif query.data.startswith("connect_"):
            connection_code = query.data.replace("connect_", "")
            await self.process_group_connection(query, connection_code)
        elif query.data == "cancel_connection":
            await query.edit_message_text("❌ Connection cancelled.")
        elif query.data.startswith("category_"):
            category = query.data.replace("category_", "")
            await self.set_ticket_category(query, category)
        elif query.data.startswith("faq_"):
            topic_id = query.data.replace("faq_", "")
            await self.show_faq_answer(query, topic_id)
        elif query.data.startswith("ticket_"):
            ticket_id = query.data.replace("ticket_", "")
            await self.show_ticket_details(query, ticket_id)

    async def process_group_connection(self, query, connection_code):
        """Process group connection request"""
        connection_data = self.pending_connections.get(connection_code)
        
        if not connection_data:
            await query.edit_message_text("❌ Connection request expired or invalid.")
            return
            
        if datetime.now() > connection_data["expires_at"]:
            del self.pending_connections[connection_code]
            await query.edit_message_text("❌ Connection request expired.")
            return

        # Save group to database
        group_doc = {
            "group_id": connection_data["group_id"],
            "group_name": connection_data["group_name"],
            "admin_id": connection_data["admin_id"],
            "admin_name": connection_data["admin_name"],
            "status": "active",
            "connected_at": datetime.now(),
            "tickets_forwarded": 0
        }
        
        try:
            await self.db.groups.insert_one(group_doc)
            
            # Clean up pending connection
            del self.pending_connections[connection_code]
            
            await query.edit_message_text(
                f"✅ **Support Group Connected Successfully!**\n\n"
                f"Group: {connection_data['group_name']}\n"
                f"Connected by: {connection_data['admin_name']}\n\n"
                f"🎫 Support tickets will now be forwarded to this group.\n"
                f"📋 Use /disconnect to disconnect this group later.",
                parse_mode='Markdown'
            )
            
            logger.info(f"Support group connected: {connection_data['group_name']} ({connection_data['group_id']})")
            
        except Exception as e:
            logger.error(f"Error connecting support group: {e}")
            await query.edit_message_text("❌ Error connecting support group. Please try again.")

    async def show_faq(self, query):
        """Display FAQ categories"""
        pipeline = [
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        
        categories = await self.db.knowledge_base.aggregate(pipeline).to_list(length=None)
        
        if not categories:
            await query.edit_message_text("📚 FAQ is currently being updated. Please create a support ticket for assistance.")
            return
        
        keyboard = []
        for cat in categories:
            category = cat["_id"] or "general"
            count = cat["count"]
            keyboard.append([InlineKeyboardButton(
                f"📂 {category.title()} ({count})", 
                callback_data=f"faq_cat_{category}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📚 **Frequently Asked Questions**\n\nSelect a category:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def show_faq_answer(self, query, topic_id):
        """Show specific FAQ answer"""
        try:
            faq_item = await self.db.knowledge_base.find_one({"_id": ObjectId(topic_id)})
        except:
            faq_item = None
            
        if not faq_item:
            await query.edit_message_text("❌ FAQ item not found.")
            return
        
        keyboard = [
            [InlineKeyboardButton("🎫 Create Ticket", callback_data="create_ticket")],
            [InlineKeyboardButton("🔙 Back to FAQ", callback_data="faq")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"**{faq_item['question'].title()}**\n\n{faq_item['answer']}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def start_ticket_creation(self, query):
        """Start the ticket creation process"""
        categories = ["general", "technical", "billing", "account", "feature_request"]
        
        keyboard = []
        for category in categories:
            keyboard.append([InlineKeyboardButton(
                f"📂 {category.title()}", 
                callback_data=f"category_{category}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎫 **Create Support Ticket**\n\n"
            "Please select a category for your issue:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def set_ticket_category(self, query, category):
        """Set ticket category and ask for description"""
        user_id = query.from_user.id
        self.pending_tickets[user_id] = {
            "category": category,
            "created_at": datetime.now(),
            "user": {
                "id": user_id,
                "username": query.from_user.username,
                "name": f"{query.from_user.first_name or ''} {query.from_user.last_name or ''}".strip()
            }
        }
        
        await query.edit_message_text(
            f"🎫 **Support Ticket - {category.title()}**\n\n"
            "Please describe your issue in detail. Include:\n"
            "• What happened?\n"
            "• What were you trying to do?\n"
            "• Any error messages\n"
            "• Screenshots (if applicable)\n\n"
            "💬 Type your message below:",
            parse_mode='Markdown'
        )

    async def process_ticket_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process the ticket description"""
        user_id = update.effective_user.id
        ticket_data = self.pending_tickets.get(user_id)
        
        if not ticket_data:
            await update.message.reply_text("❌ Ticket session expired. Please start over with /ticket")
            return
        
        # Generate ticket ID
        ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d')}-{user_id}-{datetime.now().strftime('%H%M%S')}"
        
        # Create ticket document
        ticket_doc = {
            "ticket_id": ticket_id,
            "user_id": user_id,
            "user_info": ticket_data["user"],
            "category": ticket_data["category"],
            "description": update.message.text,
            "status": "open",
            "priority": "normal",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": [
                {
                    "from": "user",
                    "message": update.message.text,
                    "timestamp": datetime.now()
                }
            ]
        }
        
        try:
            # Save ticket to database
            await self.db.tickets.insert_one(ticket_doc)
            
            # Send confirmation to user
            confirmation_text = (
                f"✅ **Ticket Created Successfully!**\n\n"
                f"🎫 **Ticket ID:** `{ticket_id}`\n"
                f"📂 **Category:** {ticket_data['category'].title()}\n"
                f"📝 **Description:** {update.message.text[:100]}{'...' if len(update.message.text) > 100 else ''}\n\n"
                f"⏰ **Status:** Open\n\n"
                f"Our support team will respond within 24 hours.\n"
                f"Use the 'My Tickets' button to check your ticket status."
            )
            
            keyboard = [[InlineKeyboardButton("📊 My Tickets", callback_data="my_tickets")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                confirmation_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            # Forward to all connected support groups
            await self.forward_to_support_groups(context, ticket_doc)
            
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await update.message.reply_text("❌ Error creating ticket. Please try again.")
        
        # Clean up pending ticket
        if user_id in self.pending_tickets:
            del self.pending_tickets[user_id]

    async def forward_to_support_groups(self, context, ticket_doc):
        """Forward ticket to all connected support groups"""
        support_groups = await self.get_support_groups()
        
        if not support_groups:
            logger.warning("No support groups connected")
            return
        
        support_text = (
            f"🆕 **New Support Ticket**\n\n"
            f"🎫 **ID:** `{ticket_doc['ticket_id']}`\n"
            f"👤 **User:** {ticket_doc['user_info']['name']} (@{ticket_doc['user_info']['username'] or 'N/A'})\n"
            f"📂 **Category:** {ticket_doc['category'].title()}\n"
            f"📅 **Created:** {ticket_doc['created_at'].strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"📝 **Description:**\n{ticket_doc['description']}"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Take Ticket", callback_data=f"take_{ticket_doc['ticket_id']}")],
            [InlineKeyboardButton("🔒 Close Ticket", callback_data=f"close_{ticket_doc['ticket_id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        for group in support_groups:
            try:
                await context.bot.send_message(
                    chat_id=group["group_id"],
                    text=support_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
                # Update forwarded count
                await self.db.groups.update_one(
                    {"_id": group["_id"]},
                    {"$inc": {"tickets_forwarded": 1}}
                )
                
            except Exception as e:
                logger.error(f"Failed to forward ticket to group {group['group_id']}: {e}")

    async def show_user_tickets(self, query):
        """Show user's tickets"""
        user_id = query.from_user.id
        
        # Get user's recent tickets
        cursor = self.db.tickets.find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(10)
        
        tickets = await cursor.to_list(length=None)
        
        if not tickets:
            await query.edit_message_text(
                "📊 **My Tickets**\n\n"
                "You don't have any support tickets yet.\n"
                "Create one by clicking the button below!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎫 Create Ticket", callback_data="create_ticket")]
                ]),
                parse_mode='Markdown'
            )
            return
        
        keyboard = []
        for ticket in tickets:
            status_emoji = "🟢" if ticket["status"] == "open" else "🔴" if ticket["status"] == "closed" else "🟡"
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {ticket['ticket_id']} - {ticket['category'].title()}",
                callback_data=f"ticket_{ticket['ticket_id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📊 **My Tickets** ({len(tickets)} total)\n\n"
            "Select a ticket to view details:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def show_ticket_details(self, query, ticket_id):
        """Show detailed ticket information"""
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id})
        
        if not ticket:
            await query.edit_message_text("❌ Ticket not found.")
            return
        
        status_emoji = "🟢" if ticket["status"] == "open" else "🔴" if ticket["status"] == "closed" else "🟡"
        
        details_text = (
            f"🎫 **Ticket Details**\n\n"
            f"**ID:** `{ticket['ticket_id']}`\n"
            f"**Status:** {status_emoji} {ticket['status'].title()}\n"
            f"**Category:** {ticket['category'].title()}\n"
            f"**Created:** {ticket['created_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Updated:** {ticket['updated_at'].strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"**Description:**\n{ticket['description']}"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Back to My Tickets", callback_data="my_tickets")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(details_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_help_inline(self, query):
        """Show help information inline"""
        help_text = (
            "❓ **How to use this bot:**\n\n"
            "🔍 **Quick Search:** Just type your question\n"
            "📚 **FAQ:** Browse common questions and answers\n"
            "🎫 **Support Tickets:** Create detailed support requests\n"
            "📊 **Track Tickets:** View your ticket status and history\n\n"
            "💡 **Tips:**\n"
            "• Try the FAQ first for instant answers\n"
            "• Be specific when creating tickets\n"
            "• Include relevant details and context\n\n"
            "👥 **For Group Admins:**\n"
            "• Add me to your support group\n"
            "• Use /connect to link as support group\n"
            "• Use /disconnect to unlink group"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

async def main():
    """Main function to run the bot"""
    # Get configuration from environment variables
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    
    # Initialize bot
    support_bot = SupportBot(bot_token, mongodb_uri)
    
    # Initialize database
    await support_bot.init_database()
    
    # Create application
    app = Application.builder().token(bot_token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", support_bot.start_command))
    app.add_handler(CommandHandler("help", support_bot.help_command))
    app.add_handler(CommandHandler("connect", support_bot.connect_command))
    app.add_handler(CommandHandler("disconnect", support_bot.disconnect_command))
    app.add_handler(CallbackQueryHandler(support_bot.button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, support_bot.handle_message))
    
    # Start the bot
    logger.info("Starting Telegram Support Bot with MongoDB...")
    
    # For Koyeb deployment, use webhook mode
    port = int(os.getenv('PORT', 8000))
    webhook_url = os.getenv('WEBHOOK_URL')
    
    if webhook_url:
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=f"{webhook_url}/webhook"
        )
    else:
        # For local development, use polling
        app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
