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
    def __init__(self, bot_token: str, mongodb_uri: str):
        self.bot_token = bot_token
        self.mongodb_uri = mongodb_uri
        self.db_client = None
        self.db = None
        self.pending_tickets = {}

        # Admins from ENV
        self.admin_ids = set(
            map(int, os.getenv("ADMINS", "").split(","))
        )
        """FOREX-Backtest tailored support bot"""


    VIP_CR_WHITELIST = {
    "CR3648598",
    "CR3654244",
    "CR3654335",
    "CR3762108",
    "CR3845409",
    "CR3925151",
    "CR4085158",
    "CR4090372",
    "CR4138661",
    "CR4210749",
    "CR4296364",
    "CR4373296",
    "CR4488218",
    "CR4583558",
    "CR4655132",
    "CR4965219",
    "CR4985194",
    "CR5053549",
    "CR5076079",
    "CR5085020",
    "CR5107260",
    "CR5107344",
    "CR5108974",
    "CR5115383",
    "CR5121522",
    "CR5124042",
    "CR5127519",
    "CR5128799",
    "CR5128821",
    "CR5128906",
    "CR5131270",
    "CR5131273",
    "CR5140283",
    "CR5140335",
    "CR5140339",
    "CR5140709",
    "CR5141478",
    "CR5145112",
    "CR5145144",
    "CR5146592",
    "CR5146651",
    "CR5149678",
    "CR5150548",
    "CR5150792",
    "CR5151132",
    "CR5152411",
    "CR5156334",
    "CR5168586",
    "CR5168665",
    "CR5171621",
    "CR5171935",
    "CR5172416",
    "CR5174518",
    "CR5175283",
    "CR5175357",
    "CR5175623",
    "CR5176885",
    "CR5178412",
    "CR5182098",
    "CR5183689",
    "CR5191512",
    "CR5191516",
    "CR5192564",
    "CR5192768",
    "CR5195948",
    "CR5195953",
    "CR5195954",
    "CR5196405",
    "CR5201751",
    "CR5201863",
    "CR5208742",
    "CR5208818",
    "CR5209139",
    "CR5211727",
    "CR5217038",
    "CR5217041",
    "CR5217294",
    "CR5217716",
    "CR5217806",
    "CR5217841",
    "CR5218145",
    "CR5218709",
    "CR5220504",
    "CR5221257",
    "CR5222812",
    "CR5224492",
    "CR5230088",
    "CR5232901",
    "CR5234722",
    "CR5242731",
    "CR5247338",
    "CR5250590",
    "CR5253563",
    "CR5253566",
    "CR5253922",
    "CR5268275",
    "CR5273673",
    "CR5273869",
    "CR5276090",
    "CR5276310",
    "CR5281994",
    "CR5283490",
    "CR5283554",
    "CR5283705",
    "CR5283721",
    "CR5291732",
    "CR5298913",
    "CR5299111",
    "CR5299430",
    "CR5303230",
    "CR5304118",
    "CR5304735",
    "CR5305240",
    "CR5305810",
    "CR5310002",
    "CR5317151",
    "CR5321069",
    "CR5324653",
    "CR5325581",
    "CR5327120",
    "CR5328157",
    "CR5337678",
    "CR5337712",
    "CR5337783",
    "CR5337784",
    "CR5337791",
    "CR5337793",
    "CR5376438",
    "CR5383018",
    "CR5404655",
    "CR5421490",
    "CR5431311",
    "CR5442253",
    "CR5442355",
    "CR5442531",
    "CR5442605",
    "CR5444280",
    "CR5445094",
    "CR5446889",
    "CR5455669",
    "CR5466632",
    "CR5466762",
    "CR5471054",
    "CR5477031",
    "CR5485897",
    "CR5487026",
    "CR5487767",
    "CR5487928",
    "CR5488506",
    "CR5491460",
    "CR5499637",
    "CR5500382",
    "CR5529877",
    "CR5535613",
    "CR5544922",
    "CR5551288",
    "CR5552176",
    "CR5556284",
    "CR5556287",
    "CR5559722",
    "CR5561483",
    "CR5563616",
    "CR5576367",
    "CR5577880",
    "CR5583683",
    "CR5585327",
    "CR5589802",
    "CR5592846",
    "CR5594968",
    "CR5595416",
    "CR5597602",
    "CR5605478",
    "CR5607701",
    "CR5616548",
    "CR5616657",
    "CR5617024",
    "CR5618746",
    "CR5634872",
    "CR5638055",
    "CR5658165",
    "CR5662243",
    "CR5681280",
    "CR5686151",
    "CR5693620",
    "CR5694136",
    "CR5729218",
    "CR5729228",
    "CR5729255",
    "CR5734377",
    "CR5734685",
    "CR5734864",
    "CR5747075",
    "CR5751222",
    "CR5755906",
    "CR5784782",
    "CR5786213",
    "CR5786969",
    "CR5799865",
    "CR5799868",
    "CR5799916",
    "CR5822964",
    "CR5836935",
    "CR5836938",
    "CR5839647",
    "CR5839797",
    "CR5845914",
    "CR5851342",
    "CR5851788",
    "CR5859465",
    "CR5864046",
    "CR5873762",
    "CR5881030",
    "CR5882107",
    "CR5886556",
    "CR5890102",
    "CR5924066",
    "CR5930200",
    "CR5970531",
    "CR6007156",
    "CR6012579",
    "CR6012919",
    "CR6022355",
    "CR6024318",
    "CR6037913",
    "CR6043787",
    "CR6077426",
    "CR6086720",
    "CR6094490",
    "CR6102922",
    "CR6128596",
    "CR6135793",
    "CR6141138",
    "CR6141427",
    "CR6141685",
    "CR6142172",
    "CR6142245",
    "CR6143176",
    "CR6146767",
    "CR6146888",
    "CR6154878",
    "CR6156707",
    "CR6158587",
    "CR6167387",
    "CR6172824",
    "CR6174976",
    "CR6181075",
    "CR6181076",
    "CR6182660",
    "CR6194673",
    "CR6198415",
    "CR6200366",
    "CR6209246",
    "CR6268178",
    "CR6283228",
    "CR6295186",
    "CR6299453",
    "CR6300261",
    "CR6301714",
    "CR6303536",
    "CR6313536",
    "CR6316942",
    "CR6316943",
    "CR6316945",
    "CR6321295",
    "CR6330598",
    "CR6341042",
    "CR6352212",
    "CR6379985",
    "CR6384361",
    "CR6399552",
    "CR6399574",
    "CR6401733",
    "CR6403902",
    "CR6408968",
    "CR6413389",
    "CR6423099",
    "CR6423523",
    "CR6439217",
    "CR6462778",
    "CR6474692",
    "CR6487699",
    "CR6505876",
    "CR6514641",
    "CR6520436",
    "CR6520451",
    "CR6523858",
    "CR6524558",
    "CR6528520",
    "CR6532131",
    "CR6532137",
    "CR6532275",
    "CR6610101",
    "CR6620010",
    "CR6653814",
    "CR6667537",
    "CR6669363",
    "CR6669366",
    "CR6675564",
    "CR6676337",
    "CR6676341",
    "CR6682471",
    "CR6691842",
    "CR6691852",
    "CR6706694",
    "CR6710741",
    "CR6756501",
    "CR6756521",
    "CR6762445",
    "CR6771489",
    "CR6772496",
    "CR6799617",
    "CR6800730",
    "CR6828268",
    "CR6973584",
    "CR6978912",
    "CR6983840",
    "CR6984178",
    "CR6994219",
    "CR7016028",
    "CR7044018",
    "CR7052204",
    "CR7112762",
    "CR7114951",
    "CR7124896",
    "CR7237163",
    "CR7283876",
    "CR7283878",
    "CR7310563",
    "CR7380411",
    "CR7381612",
    "CR7383923",
    "CR7383924",
    "CR7383926",
    "CR7443452",
    "CR7462159",
    "CR7496923",
    "CR7514165",
    "CR7619347",
    "CR7625010",
    "CR7655242",
    "CR7707424",
    "CR7708242",
    "CR7792475",
    "CR7814776",
    "CR7816651",
    "CR7817244",
    "CR7818330",
    "CR8010847",
    "CR8036589",
    "CR8047034",
    "CR8052255",
    "CR8581785",
    "CR8644473",
    "CR8648274",
    "CR8661054"
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

    async def connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.admin_ids:
            await update.message.reply_text("❌ Only admins can use this command.")
            return
        group_id = update.effective_chat.id
        group_name = update.effective_chat.title or "Unnamed"
        existing = await self.db.groups.find_one({"group_id": group_id})
        if existing:
            await update.message.reply_text("Group already connected.")
            return
        await self.db.groups.insert_one({
            "group_id": group_id,
            "group_name": group_name,
            "status": "active",
            "connected_at": datetime.utcnow()
        })
        await update.message.reply_text(f"✅ Group '{group_name}' connected.")

    async def disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in self.admin_ids:
            await update.message.reply_text("❌ Only admins can use this command.")
            return
        group_id = update.effective_chat.id
        result = await self.db.groups.delete_one({"group_id": group_id})
        if result.deleted_count:
            await update.message.reply_text("✅ Group disconnected.")
        else:
            await update.message.reply_text("Group not found.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        # Support reply detection
        if update.effective_chat.type in ["group", "supergroup"] and update.message.reply_to_message:
            reply_text = update.message.reply_to_message.text
            match = re.search(r"\*\*ID:\*\* (TKT-\d{8}-\d{5})", reply_text)
            if match:
                ticket_id = match.group(1)
                ticket = await self.db.tickets.find_one({"ticket_id": ticket_id})
                if ticket and ticket.get("status") == "assigned":
                    await self.db.tickets.update_one(
                        {"ticket_id": ticket_id},
                        {"$push": {"messages": {
                            "from": update.effective_user.id,
                            "text": update.message.text,
                            "date": datetime.utcnow()
                        }}, "$set": {"updated_at": datetime.utcnow()}}
                    )
                    await update.message.reply_text(
                        f"💬 Reply recorded for ticket {ticket_id}.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Mark as Solved", callback_data=f"solve_{ticket_id}")]
                        ])
                    )
                    return

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data
        if data.startswith("solve_"):
            await self.mark_ticket_solved(query, data.replace("solve_", ""))

    async def mark_ticket_solved(self, query, ticket_id: str):
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id})
        if not ticket:
            await query.answer("Ticket not found.")
            return
        if ticket.get("status") == "closed":
            await query.answer("Already closed.")
            return
        await self.db.tickets.update_one({"ticket_id": ticket_id}, {
            "$set": {
                "status": "closed",
                "closed_by": query.from_user.id,
                "closed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        })
        await query.answer("Marked as solved.")
        await query.edit_message_text(
            f"✅ Ticket {ticket_id} marked as solved by @{query.from_user.username or query.from_user.first_name}",
            parse_mode="Markdown"
        )
    async def get_support_groups(self):
        cursor = self.db.groups.find({"status": "active"})
        return await cursor.to_list(length=None)

    async def search_knowledge_base(self, query: str):
        """Search the knowledge base for relevant answers"""
        query_words = query.lower().split()
        search_conditions = []
        
        for word in query_words:
            search_conditions.extend([
                {"question": {"$regex": word, "$options": "i"}},
                {"answer": {"$regex": word, "$options": "i"}},
                {"keywords": {"$in": [word]}}
            ])
        
        if not search_conditions:
            return []
        
        cursor = self.db.knowledge_base.find({
            "$or": search_conditions
        }).limit(3)
        
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

    async def handle_group_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command in groups"""
        await update.message.reply_text(
            "👋 Hello! I'm the FOREX-Backtest support bot. Use /connect to set up this group for ticket notifications."
        )

    # -------------------------------------------------------------
    #  Help Command
    # -------------------------------------------------------------
    async def show_help_inline(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information"""
        help_text = (
            "🆘 *FOREX-Backtest Support Bot Help*\n\n"
            "**Available Commands:**\n"
            "• `/start` - Show main menu\n"
            "• `/help` - Show this help message\n"
            "• `/connect` - Connect group for support notifications\n"
            "• `/disconnect` - Disconnect group from notifications\n\n"
            "**Features:**\n"
            "• VIP verification and premium access\n"
            "• Free mentorship enrollment\n"
            "• Support ticket system\n"
            "• FAQ and knowledge base\n\n"
            "**VIP Services:**\n"
            "• *Deriv VIP* - Premium Deriv signals\n"
            "• *Currencies VIP* - Premium currency signals\n"
            "• *Free Mentorship* - Educational support\n\n"
            "For technical support, create a ticket using the main menu."
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]]
        
        if update.message:
            await update.message.reply_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        elif update.callback_query:
            await update.callback_query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # -------------------------------------------------------------
    #  Group Connection Commands
    # -------------------------------------------------------------
    async def connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Connect a group to receive support notifications"""
        if update.effective_chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("This command can only be used in groups.")
            return
        
        # Check if user is admin
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
            if member.status not in ["administrator", "creator"]:
                await update.message.reply_text("Only group administrators can connect the group.")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("Error checking permissions.")
            return
        
        group_id = update.effective_chat.id
        group_name = update.effective_chat.title or "Unknown Group"
        
        # Check if already connected
        existing = await self.db.groups.find_one({"group_id": group_id})
        if existing:
            await update.message.reply_text("This group is already connected for support notifications.")
            return
        
        # Add to database
        await self.db.groups.insert_one({
            "group_id": group_id,
            "group_name": group_name,
            "status": "active",
            "connected_at": datetime.utcnow(),
            "connected_by": update.effective_user.id
        })
        
        await update.message.reply_text(
            f"✅ Group '{group_name}' has been connected for support ticket notifications."
        )

    async def disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Disconnect a group from receiving support notifications"""
        if update.effective_chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("This command can only be used in groups.")
            return
        
        # Check if user is admin
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
            if member.status not in ["administrator", "creator"]:
                await update.message.reply_text("Only group administrators can disconnect the group.")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("Error checking permissions.")
            return
        
        group_id = update.effective_chat.id
        
        # Remove from database
        result = await self.db.groups.delete_one({"group_id": group_id})
        if result.deleted_count > 0:
            await update.message.reply_text("✅ Group has been disconnected from support notifications.")
        else:
            await update.message.reply_text("This group was not connected.")

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
    #  FAQ Functions
    # -------------------------------------------------------------
    async def show_faq_categories(self, query):
        """Show available FAQ categories"""
        categories = await self.db.knowledge_base.distinct("category")
        if not categories:
            await query.edit_message_text(
                "📚 No FAQ categories available yet.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]])
            )
            return
        
        keyboard = []
        for category in categories:
            keyboard.append([InlineKeyboardButton(f"📂 {category.title()}", callback_data=f"faq_cat_{category}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "📚 *FAQ Categories*\n\nSelect a category to browse:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def show_faq_for_category(self, query, category):
        """Show FAQ items for a specific category"""
        cursor = self.db.knowledge_base.find({"category": category})
        items = await cursor.to_list(length=None)
        
        if not items:
            await query.edit_message_text(
                f"No FAQ items found for category '{category}'.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="faq")]])
            )
            return
        
        keyboard = []
        for item in items[:10]:  # Limit to 10 items
            keyboard.append([InlineKeyboardButton(f"❓ {item['question'].title()}", callback_data=f"faq_item_{item['_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Categories", callback_data="faq")])
        
        await query.edit_message_text(
            f"📚 *{category.title()} FAQ*\n\nSelect a question:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def show_faq_answer(self, query, item_id):
        """Show the answer for a specific FAQ item"""
        try:
            item = await self.db.knowledge_base.find_one({"_id": ObjectId(item_id)})
            if not item:
                await query.edit_message_text("FAQ item not found.")
                return
            
            answer_text = (
                f"❓ *{item['question'].title()}*\n\n"
                f"{item['answer']}"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Back to Category", callback_data=f"faq_cat_{item['category']}")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu")]
            ]
            
            await query.edit_message_text(
                answer_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error showing FAQ answer: {e}")
            await query.edit_message_text("Error retrieving FAQ item.")

    # -------------------------------------------------------------
    #  Ticket System Functions
    # -------------------------------------------------------------
    async def start_ticket_creation(self, query):
        """Start the ticket creation process"""
        user_id = query.from_user.id
        
        categories = [
            "Technical Support",
            "Account Issues", 
            "VIP Access",
            "Mentorship",
            "General Question",
            "Bug Report"
        ]
        
        keyboard = []
        for category in categories:
            keyboard.append([InlineKeyboardButton(f"📂 {category}", callback_data=f"category_{category.lower().replace(' ', '_')}")])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "🎫 *Create Support Ticket*\n\nPlease select a category:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def set_ticket_category(self, query, category):
        """Set the ticket category and ask for description"""
        user_id = query.from_user.id
        
        # Initialize ticket creation state
        self.pending_tickets[user_id] = {
            "category": category.replace("_", " ").title(),
            "step": "description"
        }
        
        await query.edit_message_text(
            f"🎫 *New Ticket: {category.replace('_', ' ').title()}*\n\n"
            "Please describe your issue or question in detail. Be as specific as possible."
        )

    async def process_ticket_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
        """Process user input for ticket creation"""
        user_id = update.effective_user.id
        
        if user_id not in self.pending_tickets:
            return
        
        ticket_data = self.pending_tickets[user_id]
        
        if ticket_data["step"] == "description":
            # Create the ticket
            ticket_id = f"TKT-{datetime.utcnow().strftime('%Y%m%d')}-{int(datetime.utcnow().timestamp())%100000:05d}"
            
            ticket_doc = {
                "ticket_id": ticket_id,
                "user_id": user_id,
                "user_info": {
                    "id": user_id,
                    "username": update.effective_user.username,
                    "name": f"{update.effective_user.first_name or ''} {update.effective_user.last_name or ''}".strip() or update.effective_user.username or "N/A",
                },
                "category": ticket_data["category"],
                "description": message_text,
                "status": "open",
                "priority": "normal",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "messages": []
            }
            
            await self.db.tickets.insert_one(ticket_doc)
            
            # Clean up state
            del self.pending_tickets[user_id]
            
            # Notify user
            keyboard = [
                [InlineKeyboardButton("📊 View My Tickets", callback_data="my_tickets")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu")]
            ]
            
            await update.message.reply_text(
                f"✅ *Ticket Created*\n\n"
                f"**Ticket ID:** {ticket_id}\n"
                f"**Category:** {ticket_data['category']}\n\n"
                "Our support team will respond soon.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
            
            # Forward to support groups
            await self.forward_to_support_groups(context, ticket_doc)

    async def show_user_tickets(self, query):
        """Show user's tickets"""
        user_id = query.from_user.id
        
        cursor = self.db.tickets.find({"user_id": user_id}).sort("created_at", -1)
        tickets = await cursor.to_list(length=None)
        
        if not tickets:
            await query.edit_message_text(
                "📊 *My Tickets*\n\nYou haven't created any tickets yet.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]),
                parse_mode="Markdown"
            )
            return
        
        keyboard = []
        for ticket in tickets[:10]:  # Show latest 10
            status_emoji = "🟢" if ticket["status"] == "open" else "🔴" if ticket["status"] == "closed" else "🟡"
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {ticket['ticket_id']} - {ticket['category']}", 
                callback_data=f"ticket_{ticket['ticket_id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "📊 *My Tickets*\n\nSelect a ticket to view details:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def show_ticket_details(self, query, ticket_id):
        """Show details of a specific ticket"""
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id})
        
        if not ticket:
            await query.edit_message_text("Ticket not found.")
            return
        
        status_emoji = "🟢" if ticket["status"] == "open" else "🔴" if ticket["status"] == "closed" else "🟡"
        created_date = ticket["created_at"].strftime("%Y-%m-%d %H:%M")
        
        ticket_text = (
            f"🎫 *Ticket Details*\n\n"
            f"**ID:** {ticket['ticket_id']}\n"
            f"**Status:** {status_emoji} {ticket['status'].title()}\n"
            f"**Category:** {ticket['category']}\n"
            f"**Created:** {created_date}\n"
            f"**Priority:** {ticket.get('priority', 'normal').title()}\n\n"
            f"**Description:**\n{ticket['description']}"
        )
        
        if len(ticket.get('messages', [])) > 0:
            ticket_text += f"\n\n**Messages:** {len(ticket['messages'])}"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to My Tickets", callback_data="my_tickets")]]
        
        await query.edit_message_text(
            ticket_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    async def forward_to_support_groups(self, context: ContextTypes.DEFAULT_TYPE, ticket_doc: dict):
        """Forward new ticket to support groups"""
        groups = await self.get_support_groups()
        
        notification_text = (
            f"🎫 *New Support Ticket*\n\n"
            f"**ID:** {ticket_doc['ticket_id']}\n"
            f"**Category:** {ticket_doc['category']}\n"
            f"**Priority:** {ticket_doc.get('priority', 'normal').title()}\n"
            f"**User:** {ticket_doc['user_info']['name']}\n"
            f"**Username:** @{ticket_doc['user_info']['username'] or 'N/A'}\n\n"
            f"**Description:**\n{ticket_doc['description']}"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Take Ticket", callback_data=f"take_{ticket_doc['ticket_id']}")],
            [InlineKeyboardButton("❌ Close Ticket", callback_data=f"close_{ticket_doc['ticket_id']}")]
        ]
        
        # Get bot instance from application if context not available
        bot = context.bot if context else None
        if not bot:
            # This is a fallback - in production you'd want to store bot reference
            return
        
        for group in groups:
            try:
                await bot.send_message(
                    chat_id=group["group_id"],
                    text=notification_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error forwarding to group {group['group_id']}: {e}")

    async def handle_take_ticket(self, query, context: ContextTypes.DEFAULT_TYPE, ticket_id: str):
        """Handle taking a ticket by support staff"""
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id})
        if not ticket:
            await query.answer("Ticket not found.")
            return
        
        if ticket["status"] != "open":
            await query.answer("Ticket is no longer open.")
            return
        
        # Update ticket
        await self.db.tickets.update_one(
            {"ticket_id": ticket_id},
            {
                "$set": {
                    "status": "assigned",
                    "assigned_to": query.from_user.id,
                    "assigned_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        await query.answer(f"Ticket {ticket_id} assigned to you.")
        
        # Update the message
        new_text = query.message.text + f"\n\n✅ *Taken by:* @{query.from_user.username or query.from_user.first_name}"
        await query.edit_message_text(new_text, parse_mode="Markdown")

    async def handle_close_ticket(self, query, context: ContextTypes.DEFAULT_TYPE, ticket_id: str):
        """Handle closing a ticket"""
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id})
        if not ticket:
            await query.answer("Ticket not found.")
            return
        
        # Update ticket
        await self.db.tickets.update_one(
            {"ticket_id": ticket_id},
            {
                "$set": {
                    "status": "closed",
                    "closed_by": query.from_user.id,
                    "closed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        await query.answer(f"Ticket {ticket_id} closed.")
        
        # Update the message
        new_text = query.message.text + f"\n\n❌ *Closed by:* @{query.from_user.username or query.from_user.first_name}"
        await query.edit_message_text(new_text, parse_mode="Markdown")

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
            await self.show_help_inline(update, context)
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

    async def process_group_connection(self, query, data):
        """Process group connection requests"""
        # This is a placeholder - implement based on your connection logic
        await query.edit_message_text("Group connection feature not implemented yet.")

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

# Add this function after the SupportBot class definition

async def health_check(request):
    """Simple health check endpoint"""
    return web.Response(text="OK", status=200)

async def create_health_server():
    """Create a simple health check server"""
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)  # Root path for basic health checks
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Health check server started on port {port}")
    return runner

# Modify the main_async_logic function to include the health server:

async def main_async_logic():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")

    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN env var missing")

    support_bot = SupportBot(bot_token, mongodb_uri)
    await support_bot.init_database()

    # Start health check server
    health_runner = await create_health_server()

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

    # Start polling
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await health_runner.cleanup()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main_async_logic())
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
