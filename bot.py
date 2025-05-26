import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from aiohttp import web
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
            await self.db.knowledge_base.create_index("keywords")

            if await self.db.knowledge_base.count_documents({}) == 0:
                await self.init_default_knowledge_base()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    async def init_default_knowledge_base(self):
        default_kb = [
            {"question": "how to login", "answer": "To login, visit our website and click 'Sign In' in the top right corner.", "category": "account", "keywords": ["login", "sign in", "access", "enter"]},
            {"question": "reset password", "answer": "Click 'Forgot Password' on the login page and follow the email instructions.", "category": "account", "keywords": ["password", "reset", "forgot", "change"]},
            {"question": "pricing plans", "answer": "We offer Basic ($9/month), Pro ($19/month), and Enterprise ($49/month) plans.", "category": "billing", "keywords": ["price", "cost", "plan", "subscription", "billing"]},
            {"question": "refund policy", "answer": "We offer full refunds within 30 days of purchase, no questions asked.", "category": "billing", "keywords": ["refund", "money back", "return", "cancel"]},
            {"question": "technical support", "answer": "For technical issues, please create a support ticket with detailed information about the problem.", "category": "technical", "keywords": ["bug", "error", "problem", "issue", "broken"]}
        ]
        await self.db.knowledge_base.insert_many(default_kb)
        logger.info("Default knowledge base initialized")

    async def get_support_groups(self):
        cursor = self.db.groups.find({"status": "active"})
        return await cursor.to_list(length=None)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type in ['group', 'supergroup']:
            await self.handle_group_start(update, context)
            return
        keyboard = [[InlineKeyboardButton("📚 Browse FAQ", callback_data="faq")], [InlineKeyboardButton("🎫 Create Support Ticket", callback_data="create_ticket")], [InlineKeyboardButton("📊 My Tickets", callback_data="my_tickets")], [InlineKeyboardButton("❓ Help", callback_data="help")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        welcome_text = "👋 Welcome to Support Bot!\n\nI'm here to help you with:\n• Quick answers from our FAQ\n• Creating support tickets\n• Tracking your support requests\n• Connecting you with our support team\n\nWhat would you like to do?"
        if update.message: await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        elif update.callback_query: await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)

    async def handle_group_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat; user = update.effective_user
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ['administrator', 'creator']: await update.message.reply_text("❌ Only group administrators can connect this group as a support group."); return
        except Exception as e: logger.error(f"Error checking admin status for user {user.id} in chat {chat.id}: {e}"); return
        existing_group = await self.db.groups.find_one({"group_id": chat.id})
        if existing_group:
            if existing_group.get("status") == "active": await update.message.reply_text(f"✅ This group is already connected as a support group!\nConnected on: {existing_group.get('connected_at', 'Unknown').strftime('%Y-%m-%d %H:%M:%S') if existing_group.get('connected_at') else 'Unknown'}"); return
            else: await self.db.groups.update_one({"group_id": chat.id}, {"$set": {"status": "active", "reactivated_at": datetime.now()}}); await update.message.reply_text("✅ Support group reactivated successfully!"); return
        connection_code = f"CONNECT_{chat.id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self.pending_connections[connection_code] = {"group_id": chat.id, "group_name": chat.title, "admin_id": user.id, "admin_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "Admin", "expires_at": datetime.now() + timedelta(minutes=10)}
        keyboard = [[InlineKeyboardButton("🔗 Connect as Support Group", callback_data=f"connect_{connection_code}")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_connection")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"🔗 **Connect Support Group**\n\nGroup: {chat.title}\nAdmin: {user.first_name or user.username}\n\nClick the button below to connect this group as a support group. Support tickets will be forwarded here for your team to handle.\n\n⏰ This connection request expires in 10 minutes.", reply_markup=reply_markup, parse_mode='Markdown')

    async def connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type not in ['group', 'supergroup']: await update.message.reply_text("❌ The /connect command can only be used in groups."); return
        await self.handle_group_start(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❓ *How to use this bot:*\n\n• Use /start to begin\n• Use /connect to link support groups (group admins only)\n• Use /disconnect to unlink support groups (group admins only)\n• Ask questions directly or use the buttons for FAQ and tickets.\n\nℹ️ You can also click 'Help' from the main menu for more details!", parse_mode="Markdown")

    async def disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type not in ['group', 'supergroup']: await update.message.reply_text("❌ The /disconnect command can only be used in groups."); return
        chat = update.effective_chat; user = update.effective_user
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ['administrator', 'creator']: await update.message.reply_text("❌ Only group administrators can disconnect the support group."); return
        except Exception as e: logger.error(f"Error checking admin status for disconnect: {e}"); pass
        group_check = await self.db.groups.find_one({"group_id": chat.id, "status": "active"})
        if not group_check: await update.message.reply_text("❌ This group is not currently connected as an active support group."); return
        result = await self.db.groups.update_one({"group_id": chat.id}, {"$set": {"status": "inactive", "disconnected_at": datetime.now()}})
        if result.modified_count > 0: await update.message.reply_text("✅ Support group disconnected successfully. No new tickets will be forwarded to this group.")
        else: await update.message.reply_text("❌ This group is not connected as a support group or was already inactive.")

    async def search_knowledge_base(self, query: str):
        query_lower = query.lower().strip();
        if not query_lower: return []
        exact_match = await self.db.knowledge_base.find_one({"question": {"$regex": f"^{re.escape(query_lower)}$", "$options": "i"}})
        if exact_match: return [exact_match]
        query_words = [re.escape(word) for word in query_lower.split() if len(word) > 2]
        pipeline = [{"$match": {"$or": [{"keywords": {"$in": [re.compile(word, re.IGNORECASE) for word in query_words]}}, {"question": {"$regex": query_lower, "$options": "i"}}]}}, {"$limit": 3}]
        cursor = self.db.knowledge_base.aggregate(pipeline); return await cursor.to_list(length=None)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text: return
        if update.effective_chat.type in ['group', 'supergroup']:
            bot_username = context.bot.username; text = update.message.text
            is_reply_to_bot = (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id)
            is_mention = f"@{bot_username}".lower() in text.lower() if bot_username else False
            if not (is_reply_to_bot or is_mention): return
        user_message_full = update.message.text; user_id = update.effective_user.id; user_message_cleaned = user_message_full
        if context.bot.username: user_message_cleaned = re.sub(f'@{context.bot.username}', '', user_message_full, flags=re.IGNORECASE).strip()
        if not user_message_cleaned: await update.message.reply_text("Yes? How can I help you today? Try /start or ask a question."); return
        if user_id in self.pending_tickets: await self.process_ticket_input(update, context, user_message_cleaned); return
        results = await self.search_knowledge_base(user_message_cleaned)
        if results:
            response = "🔍 **Found these relevant answers:**\n\n";
            for i, result in enumerate(results, 1): response += f"**{i}. {result['question'].title()}**\n{result['answer']}\n\n"
            keyboard = [[InlineKeyboardButton("🎫 Still need help? Create ticket", callback_data="create_ticket")], [InlineKeyboardButton("📚 Browse all FAQ", callback_data="faq")]]; reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            keyboard = [[InlineKeyboardButton("🎫 Create Support Ticket", callback_data="create_ticket")], [InlineKeyboardButton("📚 Browse FAQ", callback_data="faq")]]; reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("🤔 I couldn't find a specific answer to your question.\nWould you like to create a support ticket or browse our FAQ?", reply_markup=reply_markup)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query; await query.answer(); data = query.data
        if data == "faq": await self.show_faq_categories(query)
        elif data == "create_ticket": await self.start_ticket_creation(query)
        elif data == "my_tickets": await self.show_user_tickets(query)
        elif data == "help": await self.show_help_inline(query)
        elif data.startswith("connect_"): connection_code = data; await self.process_group_connection(query, connection_code)
        elif data == "cancel_connection": await query.edit_message_text("❌ Connection request cancelled by user.")
        elif data.startswith("category_"): category = data.replace("category_", ""); await self.set_ticket_category(query, category)
        elif data.startswith("faq_cat_"): category_name = data.replace("faq_cat_", ""); await self.show_faq_for_category(query, category_name)
        elif data.startswith("faq_item_"): item_id_str = data.replace("faq_item_", ""); await self.show_faq_answer(query, item_id_str)
        elif data.startswith("ticket_"): ticket_id = data.replace("ticket_", ""); await self.show_ticket_details(query, ticket_id)
        elif data == "back_to_menu": await self.start_command(update, context)
        elif data.startswith("take_"): ticket_id = data.split("_", 1)[1]; await self.handle_take_ticket(query, context, ticket_id)
        elif data.startswith("close_"): ticket_id = data.split("_", 1)[1]; await self.handle_close_ticket(query, context, ticket_id)

    async def process_group_connection(self, query: Update.callback_query, connection_code_from_button: str):
        actual_code = connection_code_from_button.replace("connect_", "")
        connection_data = self.pending_connections.get(actual_code)
        if not connection_data: await query.edit_message_text("❌ Connection request invalid or already processed."); return
        if datetime.now() > connection_data["expires_at"]: del self.pending_connections[actual_code]; await query.edit_message_text("❌ Connection request expired."); return
        if query.from_user.id != connection_data["admin_id"]: await query.answer("Only the admin who initiated this can connect the group.", show_alert=True); return
        group_doc = {"group_id": connection_data["group_id"], "group_name": connection_data["group_name"], "admin_id": connection_data["admin_id"], "admin_name": connection_data["admin_name"], "status": "active", "connected_at": datetime.now(), "tickets_forwarded": 0}
        try:
            await self.db.groups.update_one({"group_id": connection_data["group_id"]}, {"$set": group_doc}, upsert=True)
            del self.pending_connections[actual_code]
            await query.edit_message_text(f"✅ **Support Group Connected Successfully!**\n\nGroup: {connection_data['group_name']}\nConnected by: {connection_data['admin_name']}\n\n🎫 Support tickets will now be forwarded to this group.\n📋 Use /disconnect to disconnect this group later.", parse_mode='Markdown')
            logger.info(f"Support group connected: {connection_data['group_name']} ({connection_data['group_id']})")
        except Exception as e: logger.error(f"Error connecting support group: {e}"); await query.edit_message_text("❌ Error connecting support group. Please try again.")

    async def show_faq_categories(self, query: Update.callback_query):
        categories_cursor = self.db.knowledge_base.aggregate([{"$group": {"_id": "$category", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}]); categories = await categories_cursor.to_list(length=None)
        if not categories: await query.edit_message_text("📚 FAQ is currently empty or being updated. Please create a support ticket for assistance.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]])); return
        keyboard = []
        for cat_doc in categories: category_name = cat_doc["_id"] if cat_doc["_id"] else "General"; count = cat_doc["count"]; keyboard.append([InlineKeyboardButton(f"📂 {category_name.title()} ({count})", callback_data=f"faq_cat_{category_name}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]); reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📚 **Frequently Asked Questions**\n\nSelect a category:", reply_markup=reply_markup, parse_mode='Markdown')

    async def show_faq_for_category(self, query: Update.callback_query, category_name: str):
        filter_query = {"category": category_name} if category_name != "General" else {"category": {"$in": [None, "", "General"]}}
        faq_items_cursor = self.db.knowledge_base.find(filter_query).limit(20); faq_items = await faq_items_cursor.to_list(length=None)
        if not faq_items: await query.edit_message_text(f"📚 No questions found in the '{category_name.title()}' category.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📚 All Categories", callback_data="faq")], [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]])); return
        keyboard = []
        for item in faq_items: keyboard.append([InlineKeyboardButton(item["question"].title()[:50] + ("..." if len(item["question"]) > 50 else ""), callback_data=f"faq_item_{str(item['_id'])}")])
        keyboard.append([InlineKeyboardButton("📚 All Categories", callback_data="faq")]); keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]); reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"📚 **FAQ - {category_name.title()}**\n\nSelect a question:", reply_markup=reply_markup, parse_mode='Markdown')

    async def show_faq_answer(self, query: Update.callback_query, item_id_str: str):
        try: item_oid = ObjectId(item_id_str)
        except Exception: await query.edit_message_text("❌ Invalid FAQ item ID.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📚 Back to FAQ", callback_data="faq")]])); return
        faq_item = await self.db.knowledge_base.find_one({"_id": item_oid})
        if not faq_item: await query.edit_message_text("❌ FAQ item not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📚 Back to FAQ", callback_data="faq")]])); return
        keyboard = [[InlineKeyboardButton("🎫 Create Ticket if unsolved", callback_data="create_ticket")], [InlineKeyboardButton("📚 Back to FAQ Categories", callback_data="faq")]]; reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"**{faq_item['question'].title()}**\n\n{faq_item['answer']}", reply_markup=reply_markup, parse_mode='Markdown')

    async def start_ticket_creation(self, query: Update.callback_query):
        categories = ["General", "Technical", "Billing", "Account", "Feature Request", "Other"]; keyboard = []
        for cat in categories: keyboard.append([InlineKeyboardButton(f"📂 {cat.title()}", callback_data=f"category_{cat.lower().replace(' ', '_')}")])
        keyboard.append([InlineKeyboardButton("🔙 Cancel & Back to Menu", callback_data="back_to_menu")]); reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🎫 **Create Support Ticket**\n\nPlease select a category for your issue:", reply_markup=reply_markup, parse_mode='Markdown')

    async def set_ticket_category(self, query: Update.callback_query, category: str):
        user_id = query.from_user.id
        self.pending_tickets[user_id] = {"category": category.replace('_', ' ').title(), "created_at": datetime.now(), "user": {"id": user_id, "username": query.from_user.username, "name": f"{query.from_user.first_name or ''} {query.from_user.last_name or ''}".strip() or query.from_user.username or "N/A"}}
        await query.edit_message_text(f"🎫 **Support Ticket - {self.pending_tickets[user_id]['category']}**\n\nPlease describe your issue in detail. Include:\n• What happened?\n• What were you trying to do?\n• Any error messages (copy-paste if possible)\n• Steps to reproduce the issue\n\n💬 Type your message below. Send photos/screenshots separately if needed *after* sending this text.", parse_mode='Markdown')

    async def process_ticket_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, description: str):
        user_id = update.effective_user.id; ticket_data = self.pending_tickets.get(user_id)
        if not ticket_data: await update.message.reply_text("❌ Ticket session error. Please start over with /start and create a ticket."); return
        if not description.strip(): await update.message.reply_text("📝 Please provide a description for your ticket. Your ticket has not been created yet."); return
        count = await self.db.tickets.count_documents({"created_at": {"$gte": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)}})
        ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d')}-{count+1:04d}"
        ticket_doc = {"ticket_id": ticket_id, "user_id": user_id, "user_info": ticket_data["user"], "category": ticket_data["category"], "description": description, "status": "open", "priority": "normal", "created_at": datetime.now(), "updated_at": datetime.now(), "messages": [{"from_user_id": user_id, "from_support": False, "sender_name": ticket_data["user"]["name"], "message": description, "timestamp": datetime.now()}], "assigned_to": None, "resolution": None}
        try:
            await self.db.tickets.insert_one(ticket_doc)
            confirmation_text = f"✅ **Ticket Created Successfully!**\n\n🎫 **Ticket ID:** `{ticket_id}`\n📂 **Category:** {ticket_data['category']}\n📝 **Description:** {description[:100]}{'...' if len(description) > 100 else ''}\n\n⏰ **Status:** Open\n\nOur support team will review your ticket. You can view its status via 'My Tickets'."
            keyboard = [[InlineKeyboardButton("📊 My Tickets", callback_data="my_tickets")], [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")]]; reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(confirmation_text, reply_markup=reply_markup, parse_mode='Markdown')
            await self.forward_to_support_groups(context, ticket_doc)
        except Exception as e: logger.error(f"Error creating ticket: {e}"); await update.message.reply_text("❌ Error creating ticket. Please try again or contact support directly if the issue persists.")
        finally:
            if user_id in self.pending_tickets: del self.pending_tickets[user_id]

    async def forward_to_support_groups(self, context: ContextTypes.DEFAULT_TYPE, ticket_doc):
        support_groups = await self.get_support_groups()
        if not support_groups: logger.warning(f"Ticket {ticket_doc['ticket_id']} created, but no active support groups connected to forward to."); return
        user_contact = f"@{ticket_doc['user_info']['username']}" if ticket_doc['user_info']['username'] else f"User ID: {ticket_doc['user_info']['id']}"
        support_text = f"🆕 **New Support Ticket**\n\n🎫 **ID:** `{ticket_doc['ticket_id']}`\n👤 **User:** {ticket_doc['user_info']['name']} ({user_contact})\n📂 **Category:** {ticket_doc['category']}\n📅 **Created:** {ticket_doc['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n📝 **Description:**\n{ticket_doc['description']}"
        keyboard = [[InlineKeyboardButton("🙋‍♂️ Take Ticket", callback_data=f"take_{ticket_doc['ticket_id']}")], [InlineKeyboardButton("🔒 Close Ticket", callback_data=f"close_{ticket_doc['ticket_id']}")]]; reply_markup = InlineKeyboardMarkup(keyboard)
        for group in support_groups:
            try:
                await context.bot.send_message(chat_id=group["group_id"], text=support_text, reply_markup=reply_markup, parse_mode='Markdown')
                await self.db.groups.update_one({"_id": group["_id"]}, {"$inc": {"tickets_forwarded": 1, "open_tickets_count": 1}})
            except Exception as e: logger.error(f"Failed to forward ticket {ticket_doc['ticket_id']} to group {group['group_name']} ({group['group_id']}): {e}")

    async def show_user_tickets(self, query: Update.callback_query):
        user_id = query.from_user.id; tickets_cursor = self.db.tickets.find({"user_id": user_id}).sort("created_at", -1).limit(10); tickets = await tickets_cursor.to_list(length=None)
        if not tickets: await query.edit_message_text("📊 **My Tickets**\n\nYou don't have any support tickets yet.\nCreate one by clicking the button below or from the main menu!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎫 Create New Ticket", callback_data="create_ticket")], [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]]), parse_mode='Markdown'); return
        keyboard = []; status_emojis = {"open": "🟢", "closed": "🔴", "pending": "🟡", "on-hold": "🟠"}
        for ticket in tickets: emoji = status_emojis.get(ticket["status"], "⚪️"); keyboard.append([InlineKeyboardButton(f"{emoji} {ticket['ticket_id']} - {ticket['category'].title()} ({ticket['status']})", callback_data=f"ticket_{ticket['ticket_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]); reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"📊 **My Tickets** (Showing last {len(tickets)})\n\nSelect a ticket to view details:", reply_markup=reply_markup, parse_mode='Markdown')

    async def show_ticket_details(self, query: Update.callback_query, ticket_id_str: str):
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id_str, "user_id": query.from_user.id})
        if not ticket: await query.edit_message_text("❌ Ticket not found or you don't have permission to view it.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 My Tickets", callback_data="my_tickets")]])); return
        status_emojis = {"open": "🟢", "closed": "🔴", "pending": "🟡", "on-hold": "🟠"}; status_emoji = status_emojis.get(ticket["status"], "⚪️")
        details_text = f"🎫 **Ticket Details**\n\n**ID:** `{ticket['ticket_id']}`\n**Status:** {status_emoji} {ticket['status'].title()}\n**Category:** {ticket['category'].title()}\n**Priority:** {ticket.get('priority', 'Normal').title()}\n**Created:** {ticket['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n**Last Updated:** {ticket['updated_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n**Description:**\n{ticket['description']}\n\n"
        if ticket.get('assigned_to_name'): details_text += f"**Assigned To:** {ticket['assigned_to_name']}\n"
        if ticket.get('resolution'): details_text += f"**Resolution:**\n{ticket['resolution']}\n"
        details_text += "\n**History:**\n";
        if ticket.get("messages"):
            for msg in ticket["messages"][:5]: sender = msg.get("sender_name", "Support" if msg.get("from_support") else "You"); details_text += f"- *{sender} ({msg['timestamp'].strftime('%Y-%m-%d %H:%M')}):* {msg['message'][:80]}...\n"
        else: details_text += "No messages in history yet beyond initial description.\n"
        keyboard = [[InlineKeyboardButton("📊 Back to My Tickets", callback_data="my_tickets")], [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_menu")]]; reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(details_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_help_inline(self, query: Update.callback_query):
        help_text = "❓ **How to use this bot:**\n\n🔍 **Quick Search:** Just type your question directly in the chat.\n📚 **FAQ:** Use the 'Browse FAQ' button to see common questions by category.\n🎫 **Support Tickets:** Click 'Create Support Ticket' to submit a detailed request.\n📊 **Track Tickets:** 'My Tickets' shows your past and current support requests.\n\n💡 **Tips for Tickets:**\n• Be specific: The more details, the faster we can help.\n• Include error messages or screenshots if relevant.\n\n👥 **For Group Admins:**\n• Add me to your support group.\n• Use `/connect` (or click the button when I join) to link it for receiving tickets.\n• Use `/disconnect` to stop receiving tickets in that group."
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]]; reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_take_ticket(self, query: Update.callback_query, context: ContextTypes.DEFAULT_TYPE, ticket_id: str):
        agent_user = query.from_user; agent_name = f"{agent_user.first_name or ''} {agent_user.last_name or ''}".strip() or agent_user.username
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id})
        if not ticket: await query.answer("Ticket not found.", show_alert=True); return
        if ticket.get("assigned_to") and ticket.get("assigned_to") != agent_user.id: await query.answer(f"This ticket is already assigned to {ticket.get('assigned_to_name', 'another agent')}.", show_alert=True); return
        elif ticket.get("assigned_to") == agent_user.id: await query.answer("You have already taken this ticket.", show_alert=True); return
        if ticket.get("status") == "closed": await query.answer("This ticket is already closed.", show_alert=True); return
        update_result = await self.db.tickets.update_one({"ticket_id": ticket_id, "status": {"$ne": "closed"}}, {"$set": {"assigned_to": agent_user.id, "assigned_to_name": agent_name, "status": "pending", "updated_at": datetime.now(), "$push": {"messages": {"from_support": True, "sender_name": "System", "message": f"Ticket taken by agent {agent_name}.", "timestamp": datetime.now()}}}})
        if update_result.modified_count > 0:
            await query.answer(f"You've taken ticket {ticket_id}.", show_alert=True)
            original_message = query.message; new_text = original_message.text + f"\n\n---\n**🧑‍💻 Taken by:** {agent_name} at {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            new_keyboard = [[InlineKeyboardButton("🔒 Close Ticket", callback_data=f"close_{ticket_id}")]]; await query.edit_message_text(text=new_text, reply_markup=InlineKeyboardMarkup(new_keyboard), parse_mode='Markdown')
            try: await context.bot.send_message(chat_id=ticket["user_id"], text=f"ℹ️ Ticket `{ticket_id}` has been assigned to agent {agent_name}. They will review your issue shortly.", parse_mode='Markdown')
            except Exception as e: logger.error(f"Failed to notify user {ticket['user_id']} about assignment: {e}")
        else: await query.answer("Could not take the ticket. It might be closed or already assigned.", show_alert=True)

    async def handle_close_ticket(self, query: Update.callback_query, context: ContextTypes.DEFAULT_TYPE, ticket_id: str):
        agent_user = query.from_user; agent_name = f"{agent_user.first_name or ''} {agent_user.last_name or ''}".strip() or agent_user.username
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id})
        if not ticket: await query.answer("Ticket not found.", show_alert=True); return
        if ticket.get("status") == "closed": await query.answer("This ticket is already closed.", show_alert=True); return
        update_result = await self.db.tickets.update_one({"ticket_id": ticket_id}, {"$set": {"status": "closed", "closed_by_name": agent_name, "closed_by_id": agent_user.id, "updated_at": datetime.now(), "resolution": ticket.get("resolution", "Closed by support agent."), "$push": {"messages": {"from_support": True, "sender_name": "System", "message": f"Ticket closed by agent {agent_name}.", "timestamp": datetime.now()}}}})
        if update_result.modified_count > 0:
            await query.answer(f"Ticket {ticket_id} has been closed.", show_alert=True)
            original_message = query.message; new_text = original_message.text.split("\n\n---")[0] + f"\n\n---\n**🔴 Closed by:** {agent_name} at {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            await query.edit_message_text(text=new_text, reply_markup=None, parse_mode='Markdown')
            if query.message and query.message.chat: await self.db.groups.update_one({"group_id": query.message.chat.id}, {"$inc": {"open_tickets_count": -1}})
            try: await context.bot.send_message(chat_id=ticket["user_id"], text=f"✅ Ticket `{ticket_id}` has been marked as closed by our support team. If your issue is not resolved, please create a new ticket.", parse_mode='Markdown')
            except Exception as e: logger.error(f"Failed to notify user {ticket['user_id']} about ticket closure: {e}")
        else: await query.answer("Could not close the ticket.", show_alert=True)
# === End of SupportBot class ===


async def main_async_logic():
    """Asynchronously sets up and runs the bot."""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    global logger
    logger = logging.getLogger(__name__)

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')

    if not bot_token:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable is required")
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    if not mongodb_uri:
        logger.critical("MONGODB_URI environment variable is required")
        raise ValueError("MONGODB_URI environment variable is required.")

    support_bot = SupportBot(bot_token, mongodb_uri)
    await support_bot.init_database()

    app_builder = Application.builder().token(bot_token)
    app = app_builder.build()

    # Add handlers
    app.add_handler(CommandHandler("start", support_bot.start_command))
    app.add_handler(CommandHandler("help", support_bot.help_command))
    app.add_handler(CommandHandler("connect", support_bot.connect_command))
    app.add_handler(CommandHandler("disconnect", support_bot.disconnect_command))
    app.add_handler(CallbackQueryHandler(support_bot.button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, support_bot.handle_message))

    await app.initialize()
    await app.start()

    logger.info("PTB Application initialized and started.")

    port = int(os.getenv('PORT', 8080))
    webhook_url_env = os.getenv('WEBHOOK_URL')

    if webhook_url_env:
        url_path = bot_token.split(':')[-1][:16]
        full_webhook_url_for_telegram = f"{webhook_url_env.rstrip('/')}/{url_path}"

        logger.info(f"Attempting to start webhook mode. Uvicorn will listen on 0.0.0.0:{port} at path /{url_path}")
        logger.info(f"Webhook URL to be set with Telegram: {full_webhook_url_for_telegram}")

        # ✅ Add this health check route so Koyeb health checks pass
        async def health_check(request):
            return web.Response(text="OK")

        app.web_app.router.add_get("/", health_check)

        await app.updater.start_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=url_path
        )

        await app.bot.set_webhook(
            url=full_webhook_url_for_telegram,
            allowed_updates=Update.ALL_TYPES
        )

        logger.info(f"Webhook set with Telegram. Bot should be active and listening at {full_webhook_url_for_telegram}")

        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown signal received.")
        finally:
            logger.info("Stopping webhook and shutting down application...")
            await app.updater.stop()

    else:
        logger.info("Starting bot in polling mode.")
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES
        )
        logger.info("Polling started.")
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown signal received.")
        finally:
            logger.info("Stopping poller and shutting down application...")
            await app.updater.stop()

    await app.stop()
    await app.shutdown()
    logger.info("Application shut down gracefully.")



if __name__ == '__main__':
    try:
        asyncio.run(main_async_logic())
    except ValueError as ve: # Catch specific startup errors like missing tokens
        logger.critical(f"Configuration error: {ve}")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
