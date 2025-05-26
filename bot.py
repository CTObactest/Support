import os
import logging
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime, timedelta, date
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import re

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Your Custom Content Constants ---
DERIV_AFFILIATE_LINK = "https://track.deriv.com/_qamZPcT5Sau2vdm9PpHVCmNd7ZgqdRLk/1/"
DERIV_PROCEDURE_LINK_TEXT = "https://t.me/forexbactest/1341" # For display
DERIV_TAGGING_GUIDE_LINK = "https://t.me/derivaccountopeningguide/66"
ADMIN_TELEGRAM_LINK = "https://t.me/Fxbactest_bot" # Replace with actual admin username/link

# This is a very long list, store it efficiently
CR_NUMBERS_LIST = {
    "CR5499637", "CR5500382", "CR5529877", "CR5535613", "CR5544922", "CR5551288", "CR5552176", "CR5556284", 
    "CR5556287", "CR5561483", "CR5563616", "CR5577880", "CR5585327", "CR5589802", "CR5592846", "CR5594968", 
    "CR5595416", "CR5597602", "CR5605478", "CR5607701", "CR5616548", "CR5616657", "CR5617024", "CR5618746", 
    "CR5634872", "CR5638055", "CR5658165", "CR5662243", "CR5681280", "CR5686151", "CR5693620", "CR5694136", 
    "CR5729218", "CR5729228", "CR5729255", "CR5734377", "CR5734685", "CR5734864", "CR5751222", "CR5755906", 
    "CR5784782", "CR5786213", "CR5786969", "CR5799865", "CR5799868", "CR5799916", "CR5822964", "CR5836935", 
    "CR5836938", "CR5839647", "CR5839797", "CR5859465", "CR5864046", "CR5873762", "CR5881030", "CR5886556", 
    "CR5890102", "CR5924066", "CR5930200", "CR5970531", "CR6007156", "CR6012579", "CR6012919", "CR6022355", 
    "CR6024318", "CR6037913", "CR6043787", "CR6077426", "CR6086720", "CR6094490", "CR6102922", "CR6128596", 
    "CR6135793", "CR6141138", "CR6141427", "CR6141685", "CR6142172", "CR6142245", "CR6143176", "CR6146767", 
    "CR6146888", "CR6167387", "CR6172824", "CR6181075", "CR6181076", "CR6182660", "CR6194673", "CR6198415", 
    "CR6209246", "CR6268178", "CR6283228", "CR6295186", "CR6299453", "CR6301714", "CR6313536", "CR6316942", 
    "CR6316943", "CR6316945", "CR6321295", "CR6330598", "CR6341042", "CR6379985", "CR6399552", "CR6401733", 
    "CR6403902", "CR6413389", "CR6423099", "CR6423523", "CR6462778", "CR6474692", "CR6487699", "CR6505876", 
    "CR6520436", "CR6520451", "CR6523858", "CR6524558", "CR6528520", "CR6532131", "CR6532137", "CR6532275", 
    "CR6610101", "CR6620010", "CR6653814", "CR6667537", "CR6669363", "CR6669366", "CR6675564", "CR6676337", 
    "CR6676341", "CR6682471", "CR6691842", "CR6691852", "CR6710741", "CR6756501", "CR6756521", "CR6762445", 
    "CR6772496", "CR6799617", "CR6800730", "CR6973584", "CR6978912", "CR6983840", "CR6984178", "CR6994219", 
    "CR7016028", "CR7044018", "CR7052204", "CR7112762", "CR7114951", "CR7124896", "CR7237163", "CR7310563", 
    "CR7380411", "CR7381612", "CR5217806", "CR5218145", "CR5247338", "CR5431311", "CR5455669", "CR5141478", 
    "CR5466762", "CR6154878", "CR6514641", "CR7443452", "CR7462159", "CR7496923", "CR7514165", "CR7619347", 
    "CR7625010", "CR7655242", "CR7707424", "CR7708242", "CR4965219", "CR4985194", "CR5053549", "CR5085020", 
    "CR5076079", "CR5115383", "CR5127519", "CR5128799", "CR5128821", "CR5128906", "CR5108974", "CR5140335", 
    "CR5140339", "CR5146592", "CR5146651", "CR5140283", "CR5150548", "CR5168586", "CR5182098", "CR5195948", 
    "CR5195953", "CR5195954", "CR5208742", "CR5191512", "CR5191516", "CR5230088", "CR5242731", "CR5232901", 
    "CR5304118", "CR5376438", "CR5383018", "CR5559722", "CR5576367", "CR5583683", "CR5747075", "CR5845914", 
    "CR5851342", "CR5851788", "CR5882107", "CR6174976", "CR6200366", "CR6156707", "CR6158587", "CR6300261", 
    "CR6352212", "CR6384361", "CR6399574", "CR6408968", "CR6439217", "CR6706694", "CR6771489", "CR6828268", 
    "CR7283876", "CR7283878", "CR7383923", "CR7383924", "CR7383926", "CR5107260", "CR5107344", "CR5121522", 
    "CR5124042", "CR5131270", "CR5131273", "CR5140709", "CR5145112", "CR5145144", "CR5150792", "CR5151132", 
    "CR5152411", "CR5156334", "CR5168665", "CR5171621", "CR5171935", "CR5172416", "CR5174518", "CR5175283", 
    "CR5175357", "CR5175623", "CR5176885", "CR5178412", "CR5183689", "CR5192564", "CR5192768", "CR5196405", 
    "CR5201751", "CR5201863", "CR5208818", "CR5209139", "CR5211727", "CR5217038", "CR5217041", "CR5217294", 
    "CR5217716", "CR5217841", "CR5218709", "CR5220504", "CR5221257", "CR5222812", "CR5224492", "CR5234722", 
    "CR5250590", "CR5253563", "CR5253566", "CR5253922", "CR5268275", "CR5273673", "CR5273869", "CR5276090", 
    "CR5276310", "CR5281994", "CR5283490", "CR5283554", "CR5283705", "CR5283721", "CR5291732", "CR5298913", 
    "CR5299111", "CR5299430", "CR5303230", "CR5304735", "CR5305240", "CR5305810", "CR5310002", "CR5317151", 
    "CR5321069", "CR5324653", "CR5325581", "CR5327120", "CR5328157", "CR5337678", "CR5337712", "CR5337783", 
    "CR5337784", "CR5337791", "CR5337793", "CR5404655", "CR5421490", "CR5442253", "CR5442355", "CR5442531", 
    "CR5442605", "CR5444280", "CR5445094", "CR5446889", "CR5466632", "CR5471054", "CR5477031", "CR5485897", 
    "CR5487026", "CR5487767", "CR5487928", "CR5488506", "CR5491460", "CR3648598", "CR3654244", "CR3654335", 
    "CR3762108", "CR3845409", "CR3925151", "CR4085158", "CR4090372", "CR4138661", "CR4210749", "CR4296364", 
    "CR4373296", "CR4488218", "CR4583558", "CR4655132", "CR7792475", "CR7814776", "CR7816651", "CR7817244", 
    "CR7818330", "CR5149678", "CR8010847", "CR8036589", "CR8047034", "CR8052255", "CR8581785", 
    "CR8644473", "CR8648274", "CR8661054"
}
GREETING_KEYWORDS = {"hello", "hi", "hey", "good morning", "good afternoon", "good evening", "what's up", "howdy", "greetings", "hey there"}
MIN_DEPOSIT_DERIV_VIP = 50 # As per "I can verify that you are tagged under us. Please proceed to fund your account with a minimum of $50"
MIN_DEPOSIT_MENTORSHIP = 50
MIN_DEPOSIT_CURRENCIES_OCTA = 100
MIN_DEPOSIT_CURRENCIES_VANTAGE = 100 # From initial text, $50 is min deposit, but for premium signals it's $100

OCTAFX_INFO = """
🚀 **Join Currencies Premium Channel (OctaFX) and Access Exclusive Signals!** 🚀
What You Get:
📈 Premium Signals: Stay ahead of the game with accurate and timely signals, curated by our team of expert traders. Our signals are designed to guide you through profitable trades.
🔥 Step 1: Click the link https://my.octafx.com/open-account/?refid=ib32402925 to open an account with Octa.
If you already have an account click this link to change: https://my.octafx.com/change-partner-request/?partner=32402925
🔥 Step 2: Deposit a minimum of $100 into your account.
🔥 Step 3: Confirm your subscription to Currencies Premium Channel with our admins.
🔥 Step 4: Start receiving premium signals and watch your profits soar!
"""

VANTAGE_INFO = """
Unlock the Opportunity with Vantage!
Here's How:
1. Open a STANDARD account with Vantage Brokers by following this link: https://vigco.co/VR7F7b.
If you already have an account with Vantage simply contact Vantage support and request to change your IB to code 100440.
2. Deposit a minimum of $100 into your account and then send an inbox message to the admin to be added to the premium currencies channel.

VANTAGE EXCLUSIVES
* Free live webinars.
* Spreads from 0.0
* Leverage up to 1:1000
* Minimum deposit $50 (Note: for premium channel, instructions state $100)
* $0 deposit and Withdrawal fees
* Copy trading starting from $50
* 50% first deposit bonus. T&C applies.
* FAST & EASY ACCOUNT OPENING
"""


class SupportBot:
    def __init__(self, bot_token, mongodb_uri):
        self.bot_token = bot_token
        self.mongodb_uri = mongodb_uri
        self.db_client = None
        self.db = None
        # self.pending_tickets = {} # Deprecating in favor of context.user_data for multi-step flows
        self.pending_connections = {}  # Store pending group connections

    async def init_database(self):
        """Initialize MongoDB connection"""
        try:
            self.db_client = AsyncIOMotorClient(self.mongodb_uri)
            self.db = self.db_client.support_bot_new # Use a new DB or collection if needed

            await self.db.tickets.create_index("ticket_id", unique=True)
            await self.db.tickets.create_index("user_id")
            await self.db.groups.create_index("group_id", unique=True)
            # Knowledge base can be kept if you still want FAQ functionality
            # await self.db.knowledge_base.create_index("question")  
            # await self.db.knowledge_base.create_index("keywords")
            # if await self.db.knowledge_base.count_documents({}) == 0:
            #     await self.init_default_knowledge_base() # Optional: keep if FAQ is still desired
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

    # ... (init_default_knowledge_base, get_support_groups - keep if needed) ...

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_data = context.user_data
        user_data.clear() # Clear previous states

        if update.effective_chat.type in ['group', 'supergroup']:
            await self.handle_group_start(update, context)
            return

        keyboard = [
            [InlineKeyboardButton("✨ Join VIP/Premium Group", callback_data="select_vip_type")],
            [InlineKeyboardButton("🎓 Get Free Mentorship", callback_data="free_mentorship_start")],
            # [InlineKeyboardButton("📚 Browse FAQ", callback_data="faq")], # Optional
            # [InlineKeyboardButton("🎫 Create General Support Ticket", callback_data="create_ticket")] # Optional
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        welcome_text = "Hello! How can I assist you today? Please choose an option:"
        
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup)
        
        user_data['main_selection_message_id'] = update.effective_message.message_id if update.effective_message else None


    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        
        user_message_lower = update.message.text.lower()
        user_data = context.user_data
        current_flow = user_data.get('vip_or_mentorship_flow')
        current_step = user_data.get('current_step')

        # 1. Greeting Recognition
        if any(greeting in user_message_lower for greeting in GREETING_KEYWORDS) and not current_flow:
            if len(user_message_lower.split()) <= 2: # Simple greeting like "Hi"
                 await update.message.reply_text("Hello! How can I assist you today? You can use /start to see options.")
            else: # Greeting with more context, try to answer or prompt
                 await update.message.reply_text(f"Hello! How can I help you? If you're looking for VIP access or mentorship, please use the /start command.")
            return

        # 2. Handle ongoing flows based on user_data
        if current_flow == 'deriv_vip':
            if current_step == 'awaiting_deriv_creation_date':
                await self.process_deriv_creation_date(update, context, update.message.text)
                return
            elif current_step == 'awaiting_deriv_cr_number':
                await self.process_deriv_cr_number(update, context, update.message.text)
                return
        elif current_flow == 'mentorship':
            if current_step == 'awaiting_mentorship_cr_number':
                await self.process_mentorship_cr_number(update, context, update.message.text)
                return
        
        # Fallback to original message handling (e.g., FAQ search) if no specific flow is active
        # For now, we'll just acknowledge if no flow is active and it's not a greeting
        if not current_flow: # and not a greeting
            await update.message.reply_text("I've received your message. If you need specific assistance with VIP or mentorship, please use /start.")
            # Or you can integrate your existing FAQ search here:
            # results = await self.search_knowledge_base(update.message.text)
            # ... (handle FAQ results) ...


    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_data = context.user_data
        current_flow = user_data.get('vip_or_mentorship_flow')
        current_step = user_data.get('current_step')
        
        required_amount = 0
        ticket_type = ""
        success_message = ""

        if current_flow == 'deriv_vip' and current_step == 'awaiting_deriv_funding_screenshot':
            required_amount = MIN_DEPOSIT_DERIV_VIP
            ticket_type = "Deriv VIP"
            success_message = "Deriv VIP access request."
        elif current_flow == 'mentorship' and current_step == 'awaiting_mentorship_funding_screenshot':
            required_amount = MIN_DEPOSIT_MENTORSHIP
            ticket_type = "Free Mentorship"
            success_message = "Free Mentorship access request."
        else:
            # Not expecting a photo for the current flow/step
            # Check if it's for a general ticket after description
            # For now, just ignore if not in a specific funding step
            if user_data.get('general_ticket_awaits_photo'): # A custom flag you might set
                 await update.message.reply_text("Photo received for your general ticket. An agent will review it.")
                 # process photo for general ticket if needed
            return

        # Simplified amount extraction from caption
        # For robust OCR, you'd need a library like pytesseract
        amount_detected = None
        if update.message.caption:
            numbers = re.findall(r'\b\d+\.?\d*\b', update.message.caption)
            if numbers:
                try:
                    amount_detected = float(numbers[0]) # Take the first number found
                except ValueError:
                    pass
        
        photo_file_id = update.message.photo[-1].file_id

        if amount_detected is not None and amount_detected >= required_amount:
            await update.message.reply_text(f"Screenshot received showing ${amount_detected:.2f}. Thank you!")
            # Create Deriv VIP ticket / Mentorship ticket
            ticket_details = {
                "flow": current_flow,
                "cr_number": user_data.get('cr_number_validated'),
                "amount_deposited": amount_detected,
                "screenshot_file_id": photo_file_id
            }
            await self.create_specific_ticket(
                update, context, ticket_type,
                f"{success_message} User has sent screenshot of ${amount_detected:.2f} deposit.",
                ticket_details
            )
            user_data.clear()
        elif amount_detected is not None and amount_detected < required_amount:
             await update.message.reply_text(f"The amount in your screenshot (${amount_detected:.2f}) is less than the required ${required_amount:.2f}. Please deposit the correct amount and send a new screenshot.")
        else:
            # Amount not found in caption or less than required
            await update.message.reply_text(f"I couldn't automatically detect the deposit amount from your screenshot's caption, or it was less than ${required_amount:.2f}. "
                                            f"Please ensure the deposit is at least ${required_amount:.2f} and reply with the amount you deposited (e.g., '$50' or '50'), or send the screenshot again with the amount in the caption.")
            user_data['awaiting_manual_amount_confirmation_after_photo'] = True
            user_data['photo_for_confirmation_file_id'] = photo_file_id
            # If user replies with amount text, handle_message should pick it up if you add logic for 'awaiting_manual_amount_confirmation_after_photo'

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        user_data = context.user_data

        # Clear previous step message if any
        # prev_message_id = user_data.pop('current_step_message_id', None)
        # if prev_message_id and query.message.message_id == user_data.get('main_selection_message_id'):
        #     try: # This might fail if the message is the main menu itself
        #         await context.bot.delete_message(chat_id=query.message.chat_id, message_id=prev_message_id)
        #     except Exception as e:
        #         logger.info(f"Could not delete previous step message: {e}")
        # else: # Edit the current message
        #    pass

        # --- Main Menu Options ---
        if data == "select_vip_type":
            user_data.clear() # Reset for new selection
            user_data['vip_or_mentorship_flow'] = 'vip_selection'
            keyboard = [
                [InlineKeyboardButton("📈 Deriv VIP (Synthetic Indices)", callback_data="vip_deriv_start")],
                [InlineKeyboardButton("📊 Currencies VIP", callback_data="vip_currencies_start")],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start_command_reset")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Which VIP/Premium group do you wish to join?", reply_markup=reply_markup)

        elif data == "start_command_reset":
            await self.start_command(update, context) # Go back to main menu

        # --- Deriv VIP Flow ---
        elif data == "vip_deriv_start":
            user_data.clear()
            user_data['vip_or_mentorship_flow'] = 'deriv_vip'
            user_data['current_step'] = 'awaiting_deriv_procedure_confirm'
            keyboard = [
                [InlineKeyboardButton("Yes, I did", callback_data="deriv_procedure_yes")],
                [InlineKeyboardButton("No, I didn't", callback_data="deriv_procedure_no")],
                [InlineKeyboardButton("🔙 Back", callback_data="select_vip_type")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"Welcome to Deriv VIP Onboarding!\n\n"
                                          f"Have you created a Deriv account using this specific procedure link? \n🔗 {DERIV_PROCEDURE_LINK_TEXT}",
                                          reply_markup=reply_markup, disable_web_page_preview=True)

        elif data == "deriv_procedure_yes":
            if user_data.get('vip_or_mentorship_flow') == 'deriv_vip':
                user_data['current_step'] = 'awaiting_deriv_creation_date'
                msg = await query.edit_message_text("Great! When did you create the account? Please enter the date (e.g., YYYY-MM-DD or DD/MM/YYYY).")
                user_data['current_step_message_id'] = msg.message_id

        elif data == "deriv_procedure_no":
            if user_data.get('vip_or_mentorship_flow') == 'deriv_vip':
                user_data.clear() # End this flow attempt
                keyboard = [[InlineKeyboardButton("View Procedure Guide", url=DERIV_PROCEDURE_LINK_TEXT)],[InlineKeyboardButton("🔙 Back to VIP Selection", callback_data="select_vip_type")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("To join Deriv VIP, you need to create an account using our specific procedure. "
                                              "Please follow the guide and then restart this process.", reply_markup=reply_markup)

        # --- Currencies VIP Flow ---
        elif data == "vip_currencies_start":
            user_data.clear()
            user_data['vip_or_mentorship_flow'] = 'currencies_vip'
            user_data['current_step'] = 'creating_ticket' # Immediate ticket

            # Provide info, then create ticket
            info_text = (
                "Welcome to Currencies VIP Services!\n\n"
                "We offer premium signals through our partner brokers OctaFX and Vantage.\n"
                "Please ensure you have followed the setup instructions for your chosen broker:\n\n"
                f"{OCTAFX_INFO}\n\n---\n\n{VANTAGE_INFO}\n\n"
                "I will now create a 'VIP Currencies Ticket' for you. Our admin team will follow up."
            )
            await query.edit_message_text(info_text, parse_mode='Markdown', disable_web_page_preview=True)
            
            await self.create_specific_ticket(
                update, context, "VIP Currencies",
                "User selected Currencies VIP. User has been shown OctaFX and Vantage instructions.",
                {"flow": "currencies_vip"}
            )
            user_data.clear() # Reset after ticket
            await query.message.reply_text("A 'VIP Currencies Ticket' has been created. Please wait for the admin team to contact you. You can go /start again for other options.", 
                                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="start_command_reset")]]))


        # --- Free Mentorship Flow ---
        elif data == "free_mentorship_start":
            user_data.clear()
            user_data['vip_or_mentorship_flow'] = 'mentorship'
            user_data['current_step'] = 'awaiting_mentorship_account_exists_confirm'
            keyboard = [
                [InlineKeyboardButton("Yes, I have a Deriv account", callback_data="mentorship_account_yes")],
                [InlineKeyboardButton("No, I need to create one", callback_data="mentorship_account_no")],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start_command_reset")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Welcome to Free Mentorship Onboarding!\n\n"
                                          "This mentorship requires a Deriv account funded under our partner link.\n"
                                          "Do you already have a Deriv account?",
                                          reply_markup=reply_markup)

        elif data == "mentorship_account_yes":
            if user_data.get('vip_or_mentorship_flow') == 'mentorship':
                user_data['current_step'] = 'awaiting_mentorship_cr_number'
                msg = await query.edit_message_text("Okay, please provide your Deriv Client ID (CR Number, e.g., CR123456).")
                user_data['current_step_message_id'] = msg.message_id
        
        elif data == "mentorship_account_no":
            if user_data.get('vip_or_mentorship_flow') == 'mentorship':
                user_data['current_step'] = 'told_to_create_account_for_mentorship'
                keyboard = [
                    [InlineKeyboardButton("Open Deriv Account Now", url=DERIV_AFFILIATE_LINK)],
                    [InlineKeyboardButton("I've created it / I'll do it later", callback_data="mentorship_account_actions_after_link")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(f"Please open a Deriv account using our recommended broker's link: \n🔗 {DERIV_AFFILIATE_LINK}\n\n"
                                              "After creating and funding it with at least ${MIN_DEPOSIT_MENTORSHIP}, come back and we'll proceed.",
                                              reply_markup=reply_markup, disable_web_page_preview=True)

        elif data == "mentorship_account_actions_after_link":
            # This could lead back to asking for CR number or funding proof
            user_data['current_step'] = 'awaiting_mentorship_funding_screenshot_after_creation' # Or CR if they claim they already had one
            await query.edit_message_text(f"Once your account is created using our link ({DERIV_AFFILIATE_LINK}) "
                                          f"and funded with a minimum of ${MIN_DEPOSIT_MENTORSHIP}, please send a screenshot of the funded account balance here.\n"
                                          "If you already had an account and just tagged it, we might need your CR number again if not yet provided.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="free_mentorship_start")]]))


        # --- Deriv CR / Kennedynespot flow ---
        elif data == "deriv_kennedynespot_yes":
            if user_data.get('current_step') == 'awaiting_kennedynespot_confirm':
                user_data['current_step'] = 'told_to_dm_kennedy_proof'
                await query.edit_message_text("Please send us a direct message (DM) with a screenshot of the confirmation from our partner (Kennedynespot) showing you are tagged under them. "
                                              f"You can message the admin here: {ADMIN_TELEGRAM_LINK}",
                                              reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to VIP Selection", callback_data="select_vip_type")]]))
        
        elif data == "deriv_kennedynespot_no":
            if user_data.get('current_step') == 'awaiting_kennedynespot_confirm':
                user_data['current_step'] = 'told_to_follow_tagging_guide'
                keyboard = [[InlineKeyboardButton("View Tagging Guide", url=DERIV_TAGGING_GUIDE_LINK)], [InlineKeyboardButton("🔙 Back to VIP Selection", callback_data="select_vip_type")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("Please follow the tagging guide to ensure your account is under our partner: "
                                              f"{DERIV_TAGGING_GUIDE_LINK}\n\n"
                                              "After completing the steps and waiting 24 hours for systems to update, please try the Deriv VIP verification again from /start.",
                                              reply_markup=reply_markup, disable_web_page_preview=True)
        
        # Fallback for other button data (original bot functions)
        # This part needs careful integration if you keep old FAQ/Ticket buttons
        else:
            # Basic navigation back
            if data == "back_to_menu": # Assuming this was an old callback
                await self.start_command(update, context)
            # ... handle other pre-existing callbacks like faq_cat_, ticket_ etc. if you keep them ...
            # For now, let's log unhandled callbacks during this refactoring
            logger.info(f"Unhandled callback_data: {data} in main button_callback")


    async def process_deriv_creation_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE, date_text: str):
        user_data = context.user_data
        parsed_date = self._parse_date(date_text)

        if not parsed_date:
            await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD or DD/MM/YYYY.")
            return

        if (datetime.now().date() - parsed_date).days < 1:
            user_data.clear() # End this flow attempt
            await update.message.reply_text("Your account is less than one day old. Please wait up to 24 hours for the account to reflect in our system, then try again from /start.")
        else:
            user_data['deriv_account_creation_date'] = parsed_date.isoformat()
            user_data['current_step'] = 'awaiting_deriv_cr_number'
            await update.message.reply_text("Thank you. Now, please provide your Deriv Client ID (CR Number, e.g., CR12345).")

    async def process_deriv_cr_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cr_number_text: str):
        user_data = context.user_data
        cr_number = cr_number_text.strip().upper()

        if not re.match(r"^CR\d+$", cr_number):
            await update.message.reply_text("Invalid CR number format. It should be 'CR' followed by numbers (e.g., CR12345). Please try again.")
            return

        if cr_number in CR_NUMBERS_LIST:
            user_data['cr_number_validated'] = cr_number
            user_data['current_step'] = 'awaiting_deriv_funding_screenshot'
            await update.message.reply_text(f"I can verify that CR number {cr_number} is tagged under us. Thank you!\n\n"
                                            f"Please proceed to fund your Deriv account with a minimum of ${MIN_DEPOSIT_DERIV_VIP}. "
                                            "Once funded, send a screenshot of the account balance here.")
        else:
            user_data['current_step'] = 'awaiting_kennedynespot_confirm'
            user_data['cr_number_not_found'] = cr_number
            keyboard = [
                [InlineKeyboardButton("Yes, I am tagged", callback_data="deriv_kennedynespot_yes")],
                [InlineKeyboardButton("No, I am not / I don't know", callback_data="deriv_kennedynespot_no")],
                [InlineKeyboardButton("🔙 Try different CR", callback_data="vip_deriv_start")] # Or go back to CR input step
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            # Assuming query object might not be available if this is called from handle_message
            await update.message.reply_text(f"CR number {cr_number} was not found in our primary list.\n"
                                            "Are you tagged under our partner, Kennedynespot?",
                                            reply_markup=reply_markup)

    async def process_mentorship_cr_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cr_number_text: str):
        user_data = context.user_data
        cr_number = cr_number_text.strip().upper()

        if not re.match(r"^CR\d+$", cr_number):
            await update.message.reply_text("Invalid CR number format. It should be 'CR' followed by numbers (e.g., CR12345). Please try again.")
            return

        if cr_number in CR_NUMBERS_LIST:
            user_data['cr_number_validated'] = cr_number
            user_data['current_step'] = 'awaiting_mentorship_funding_screenshot'
            await update.message.reply_text(f"CR number {cr_number} is verified under us. Great!\n\n"
                                            f"Please ensure your Deriv account is funded with a minimum of ${MIN_DEPOSIT_MENTORSHIP}. "
                                            "Once funded, send a screenshot of the account balance here.")
        else:
            # For mentorship, if CR not found, guide them to create a new one or re-tag
            user_data['current_step'] = 'mentorship_cr_not_found_guidance'
            keyboard = [
                [InlineKeyboardButton("Open New Account (Our Link)", url=DERIV_AFFILIATE_LINK)],
                [InlineKeyboardButton("View Tagging Guide (Existing Account)", url=DERIV_TAGGING_GUIDE_LINK)],
                 [InlineKeyboardButton("🔙 Try different CR", callback_data="free_mentorship_start")] # or back to cr input
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"CR number {cr_number} was not found in our list for mentorship.\n"
                                            "For free mentorship, your account needs to be affiliated with us.\n"
                                            "- If you need to create a new account, use our link.\n"
                                            "- If you have an existing account, you might need to re-tag it using the guide.\n\n"
                                            "After setting this up and funding with at least ${MIN_DEPOSIT_MENTORSHIP}, please send the screenshot.",
                                            reply_markup=reply_markup, disable_web_page_preview=True)


    def _parse_date(self, date_text: str) -> date | None:
        formats_to_try = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"]
        for fmt in formats_to_try:
            try:
                return datetime.strptime(date_text, fmt).date()
            except ValueError:
                continue
        return None

    async def create_specific_ticket(self, update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_type: str, description: str, details: dict):
        user = update.effective_user
        user_id = user.id
        user_info = {
            "id": user_id,
            "username": user.username,
            "name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "N/A"
        }
        
        count = await self.db.tickets.count_documents({"created_at": {"$gte": datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)}})
        ticket_id_num = f"TKT-{datetime.now().strftime('%Y%m%d')}-{count+1:04d}"
        
        ticket_doc = {
            "ticket_id": ticket_id_num,
            "user_id": user_id,
            "user_info": user_info,
            "category": ticket_type, # Using ticket_type as category
            "description": description,
            "status": "open",
            "priority": "high", # VIP/Mentorship tickets might be high priority
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "messages": [{"from_user_id": user_id, "from_support": False, "sender_name": user_info["name"], "message": description, "timestamp": datetime.now()}],
            "assigned_to": None,
            "resolution": None,
            "ticket_type_custom": ticket_type, # explicit field for type
            "flow_details": details # Store CR number, deposit info etc.
        }
        
        try:
            await self.db.tickets.insert_one(ticket_doc)
            confirmation_text = (f"✅ **{ticket_type} Ticket Created Successfully!**\n\n"
                                 f"🎫 **Ticket ID:** `{ticket_id_num}`\n"
                                 f"Our support team will review your request. You will be contacted shortly.")
            
            # Reply to original message if query, else send new message
            target_message = update.callback_query.message if update.callback_query else update.message
            await target_message.reply_text(confirmation_text, parse_mode='Markdown')
            
            await self.forward_to_support_groups(context, ticket_doc)
            logger.info(f"{ticket_type} ticket {ticket_id_num} created for user {user_id}")

        except Exception as e:
            logger.error(f"Error creating specific ticket {ticket_id_num}: {e}")
            target_message = update.callback_query.message if update.callback_query else update.message
            await target_message.reply_text("❌ Error creating your ticket. Please try again or contact support directly if the issue persists.")
        finally:
            context.user_data.clear()


    # --- Existing Methods (potentially keep or adapt) ---
    async def init_default_knowledge_base(self): # Keep if you want FAQ
        default_kb = [
            {"question": "how to login", "answer": "To login, visit our website and click 'Sign In' in the top right corner.", "category": "account", "keywords": ["login", "sign in", "access", "enter"]},
            # ... more generic FAQs ...
        ]
        # Check if collection is empty before inserting
        if await self.db.knowledge_base.count_documents({}) == 0:
            await self.db.knowledge_base.insert_many(default_kb)
            logger.info("Default knowledge base initialized")

    async def get_support_groups(self): # Keep for forwarding tickets
        cursor = self.db.groups.find({"status": "active"})
        return await cursor.to_list(length=None)

    async def handle_group_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE): # Keep
        # ... (original code for group connection) ...
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


    async def connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE): # Keep
        if update.effective_chat.type not in ['group', 'supergroup']: await update.message.reply_text("❌ The /connect command can only be used in groups."); return
        await self.handle_group_start(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE): # Update help text
        await update.message.reply_text("❓ *How to use this bot:*\n\n"
                                       "• Use /start to explore VIP programs and Mentorship.\n"
                                       "• Follow the on-screen instructions for verification.\n"
                                       "• For group admins: /connect and /disconnect manage support group links.\n\n"
                                       "If you get stuck, you can always restart with /start.", 
                                       parse_mode="Markdown")

    async def disconnect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE): # Keep
        # ... (original code for disconnect) ...
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


    async def process_group_connection(self, query: Update.callback_query, connection_code_from_button: str): # Keep
        # ... (original code for group connection processing) ...
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

    async def forward_to_support_groups(self, context: ContextTypes.DEFAULT_TYPE, ticket_doc): # Adapt message format
        support_groups = await self.get_support_groups()
        if not support_groups: 
            logger.warning(f"Ticket {ticket_doc['ticket_id']} created, but no active support groups connected.")
            return

        user_contact = f"@{ticket_doc['user_info']['username']}" if ticket_doc['user_info']['username'] else f"User ID: {ticket_doc['user_info']['id']}"
        
        # Enhanced support text for new ticket types
        support_text = f"🆕 **New {ticket_doc.get('ticket_type_custom', 'Support Ticket')}**\n\n" \
                       f"🎫 **ID:** `{ticket_doc['ticket_id']}`\n" \
                       f"👤 **User:** {ticket_doc['user_info']['name']} ({user_contact})\n" \
                       f"📂 **Type/Category:** {ticket_doc['category']}\n" \
                       f"📅 **Created:** {ticket_doc['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n" \
                       f"📝 **Description/Details:**\n{ticket_doc['description']}\n\n"

        if ticket_doc.get('flow_details'):
            support_text += "**Flow Specific Info:**\n"
            for key, value in ticket_doc['flow_details'].items():
                support_text += f"- {key.replace('_', ' ').title()}: {value}\n"
        
        keyboard = [
            [InlineKeyboardButton("🙋‍♂️ Take Ticket", callback_data=f"take_{ticket_doc['ticket_id']}")],
            [InlineKeyboardButton("🔒 Close Ticket", callback_data=f"close_{ticket_doc['ticket_id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        for group in support_groups:
            try:
                await context.bot.send_message(chat_id=group["group_id"], text=support_text, reply_markup=reply_markup, parse_mode='Markdown')
                await self.db.groups.update_one({"_id": group["_id"]}, {"$inc": {"tickets_forwarded": 1, "open_tickets_count": 1}}) # Assuming you track open tickets
            except Exception as e:
                logger.error(f"Failed to forward ticket {ticket_doc['ticket_id']} to group {group['group_name']} ({group['group_id']}): {e}")

    # Keep handle_take_ticket, handle_close_ticket, show_user_tickets, show_ticket_details
    # Their functionality related to agents handling general tickets is likely still useful.
    # You might want to adapt the displayed ticket details if `flow_details` is important for agents to see directly.

    async def handle_take_ticket(self, query: Update.callback_query, context: ContextTypes.DEFAULT_TYPE, ticket_id: str):
        # ... (original code) ...
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
        # ... (original code) ...
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

    async def show_user_tickets(self, query: Update.callback_query): # Minor adaptation for clarity
        user_id = query.from_user.id
        tickets_cursor = self.db.tickets.find({"user_id": user_id}).sort("created_at", -1).limit(10)
        tickets = await tickets_cursor.to_list(length=None)

        if not tickets:
            await query.edit_message_text("📊 **My Tickets**\n\nYou don't have any support tickets yet.\n"
                                          "Use /start to create a VIP/Mentorship request or a general ticket.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="start_command_reset")]]), parse_mode='Markdown')
            return

        keyboard = []
        status_emojis = {"open": "🟢", "closed": "🔴", "pending": "🟡", "on-hold": "🟠"}
        for ticket in tickets:
            emoji = status_emojis.get(ticket["status"], "⚪️")
            ticket_display_category = ticket.get('ticket_type_custom', ticket['category'].title())
            keyboard.append([InlineKeyboardButton(f"{emoji} {ticket['ticket_id']} - {ticket_display_category} ({ticket['status']})", callback_data=f"ticket_{ticket['ticket_id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="start_command_reset")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"📊 **My Tickets** (Showing last {len(tickets)})\n\nSelect a ticket to view details:", reply_markup=reply_markup, parse_mode='Markdown')

    async def show_ticket_details(self, query: Update.callback_query, ticket_id_str: str): # Adapt to show flow_details
        ticket = await self.db.tickets.find_one({"ticket_id": ticket_id_str, "user_id": query.from_user.id})
        if not ticket:
            await query.edit_message_text("❌ Ticket not found or you don't have permission to view it.",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 My Tickets", callback_data="my_tickets")]]))
            return

        status_emojis = {"open": "🟢", "closed": "🔴", "pending": "🟡", "on-hold": "🟠"}
        status_emoji = status_emojis.get(ticket["status"], "⚪️")
        ticket_display_category = ticket.get('ticket_type_custom', ticket['category'].title())

        details_text = f"🎫 **Ticket Details**\n\n" \
                       f"**ID:** `{ticket['ticket_id']}`\n" \
                       f"**Status:** {status_emoji} {ticket['status'].title()}\n" \
                       f"**Type/Category:** {ticket_display_category}\n" \
                       f"**Priority:** {ticket.get('priority', 'Normal').title()}\n" \
                       f"**Created:** {ticket['created_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n" \
                       f"**Last Updated:** {ticket['updated_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n" \
                       f"**Description:**\n{ticket['description']}\n\n"

        if ticket.get('flow_details'):
            details_text += "**Submission Details:**\n"
            for key, value in ticket['flow_details'].items():
                if key == "screenshot_file_id": # Don't show file_id to user
                    details_text += f"- Screenshot Provided: Yes\n"
                else:
                    details_text += f"- {key.replace('_', ' ').title()}: {value}\n"
            details_text += "\n"
            
        if ticket.get('assigned_to_name'): details_text += f"**Assigned To:** {ticket['assigned_to_name']}\n"
        if ticket.get('resolution'): details_text += f"**Resolution:**\n{ticket['resolution']}\n"
        
        # ... rest of message history if needed ...
        keyboard = [[InlineKeyboardButton("📊 Back to My Tickets", callback_data="my_tickets")],
                    [InlineKeyboardButton("🔙 Main Menu", callback_data="start_command_reset")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(details_text, reply_markup=reply_markup, parse_mode='Markdown')

    # Any other original methods like show_faq_categories, process_ticket_input (if general tickets are kept)
    # would need to be reviewed to ensure they integrate smoothly or are explicitly chosen paths.
    # For now, the main flow is driven by the new VIP/Mentorship paths.


# === Main Application Setup ===
async def main_async_logic():
    import logging
    from aiohttp import web

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

    # 🔧 Add health check endpoint for Koyeb
    async def health_check(request):
        return web.Response(text="OK")

    # Create and start the web server
    web_app = web.Application()
    web_app.router.add_get("/", health_check)
    web_app.router.add_get("/health", health_check)
    
    # Start the web server
    runner = web.AppRunner(web_app)
    await runner.setup()
    
    port = int(os.getenv('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server started on port {port}")

    # ✅ Start polling
    await app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("Deleted webhook. Starting polling...")

    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot is now polling Telegram for updates.")

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
        await runner.cleanup()
        logger.info("Application shut down gracefully.")



if __name__ == '__main__':
    try:
        asyncio.run(main_async_logic())
    except ValueError as ve: # Catch specific startup errors like missing tokens
        logger.critical(f"Configuration error: {ve}")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
