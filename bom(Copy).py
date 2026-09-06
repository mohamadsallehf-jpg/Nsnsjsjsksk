import os
import copy
import asyncio
import smtplib
import json
import logging
import re
import random
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import pytz
import socks
from telethon import TelegramClient, events, Button, errors
from telethon.sessions import StringSession
from telethon.tl.functions.account import ReportPeerRequest
from telethon.tl.functions.messages import ReportRequest as ReportMessageRequest
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantRequest
from telethon.tl.types import (
    InputReportReasonSpam,
    InputReportReasonViolence,
    InputReportReasonPornography,
    InputReportReasonFake,
    InputReportReasonChildAbuse,
    InputReportReasonCopyright,
    InputReportReasonPersonalDetails,
    InputReportReasonOther
)

# ==================== CONFIGURATION ====================
API_ID = 25790571
API_HASH = "2b95fb1f6f630a83e0712e84ddb337f2"
BOT_TOKEN = "8511023644:AAG0bFerYHQtqe40CKqHl5kvlDdOXZ7s38o"
OWNER_IDS = [6580618549]

DATA_FILE = "data.json"
ADMIN_SESSIONS_DIR = "admin_sessions"
PROXIES_FILE = "proxies.txt"

os.makedirs(ADMIN_SESSIONS_DIR, exist_ok=True)

logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

DEVICE_MODELS = [
    {"app_version": "10.13.1", "device_model": "iPhone 15 Pro", "system_version": "iOS 17.5.1", "lang_code": "en"},
    {"app_version": "10.13.0", "device_model": "Samsung Galaxy S24", "system_version": "Android 14", "lang_code": "fa"},
    {"app_version": "10.12.2", "device_model": "Xiaomi 13 Pro", "system_version": "Android 13", "lang_code": "en"},
    {"app_version": "10.11.1", "device_model": "Google Pixel 8", "system_version": "Android 14", "lang_code": "en"},
    {"app_version": "10.13.1", "device_model": "iPhone 14 Pro Max", "system_version": "iOS 17.4.1", "lang_code": "fa"}
]

# ==================== PROXY SYSTEM ====================

def parse_proxy_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    proxy_type = socks.SOCKS5
    if line.startswith("socks5://"):
        proxy_type = socks.SOCKS5
        line = line[9:]
    elif line.startswith("socks4://"):
        proxy_type = socks.SOCKS4
        line = line[9:]
    elif line.startswith("http://") or line.startswith("https://"):
        proxy_type = socks.HTTP
        line = line.split("://")[1]

    user, pwd, host, port = None, None, None, None

    if "@" in line:
        auth, host_port = line.split("@", 1)
        if ":" in auth:
            user, pwd = auth.split(":", 1)
        else:
            user = auth
        parts = host_port.split(":")
        if len(parts) == 2 and parts[1].isdigit():
            host, port = parts[0], int(parts[1])
    else:
        parts = line.split(":")
        if len(parts) == 2 and parts[1].isdigit():
            host, port = parts[0], int(parts[1])
        elif len(parts) == 4 and parts[1].isdigit():
            host, port, user, pwd = parts[0], int(parts[1]), parts[2], parts[3]

    if host and port:
        if user and pwd:
            return (proxy_type, host, port, user, pwd)
        else:
            return (proxy_type, host, port)
    return None

def load_proxies():
    if not os.path.exists(PROXIES_FILE):
        return []
    parsed_proxies = []
    try:
        with open(PROXIES_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            proxy = parse_proxy_line(line)
            if proxy:
                parsed_proxies.append(proxy)
    except Exception as e:
        logger.error(f"Error reading proxies file: {e}")
    return parsed_proxies

# ==================== DATASETS & SUBMENUS ====================

REPORT_MAIN_REASONS = {
    'child_abuse': ('کودک‌آزاری / Child Abuse', InputReportReasonChildAbuse(), 'Child abuse content'),
    'violence': ('خشونت / Violence', InputReportReasonViolence(), 'Violence content'),
    'illegal_goods': ('کالاها و خدمات غیرمجاز / Illegal Goods', InputReportReasonOther(), 'Illegal goods or services'),
    'pornography': ('محتوای بزرگسالان / Pornography', InputReportReasonPornography(), 'Adult content'),
    'personal_details': ('داده‌های شخصی / Personal Details', InputReportReasonPersonalDetails(), 'Personal details leak'),
    'fake_scam': ('کلاهبرداری یا تقلب / Fake or Scam', InputReportReasonFake(), 'Fake or scam content'),
    'copyright': ('حق تکثیر / Copyright', InputReportReasonCopyright(), 'Copyright infringement'),
    'spam': ('هرزنامه / Spam', InputReportReasonSpam(), 'Spam content'),
    'other': ('دیگر / Other', InputReportReasonOther(), 'Other violation'),
}

REPORT_SUB_REASONS = {
    'child_abuse': {
        'ca_sexual': ('کودک‌آزاری جنسی', InputReportReasonChildAbuse(), 'Child sexual abuse content'),
        'ca_physical': ('کودک‌آزاری جسمی', InputReportReasonChildAbuse(), 'Child physical abuse content')
    },
    'violence': {
        'v_insult': ('اهانت یا اطلاعات نادرست', InputReportReasonViolence(), 'Insult or misinformation'),
        'v_graphic': ('محتوای خشونت‌آمیز گرافیکی', InputReportReasonViolence(), 'Graphic violent content'),
        'v_extreme': ('خشونت شدید، مثله کردن', InputReportReasonViolence(), 'Extreme violence or mutilation'),
        'v_hate': ('نفرت‌پراکنی', InputReportReasonViolence(), 'Hate speech'),
        'v_encourage': ('تشویق به خشونت', InputReportReasonViolence(), 'Encouraging violence'),
        'v_crime': ('جرائم سازمان‌یافته', InputReportReasonViolence(), 'Organized crime'),
        'v_terror': ('تروریسم', InputReportReasonViolence(), 'Terrorism'),
        'v_animal': ('حیوان‌آزاری', InputReportReasonViolence(), 'Animal cruelty')
    },
    'illegal_goods': {
        'ig_weapons': ('سلاح‌ها', InputReportReasonOther(), 'Weapons sale'),
        'ig_drugs': ('مواد مخدر', InputReportReasonOther(), 'Illegal drugs'),
        'ig_fake_docs': ('سندهای جعلی', InputReportReasonOther(), 'Fake documents'),
        'ig_fake_money': ('پول تقلبی', InputReportReasonOther(), 'Counterfeit money'),
        'ig_hacking': ('ابزارهای هک', InputReportReasonOther(), 'Hacking tools'),
        'ig_counterfeit': ('کالاهای جعلی', InputReportReasonOther(), 'Counterfeit goods'),
        'ig_other': ('سایر محصولات', InputReportReasonOther(), 'Other illegal products')
    },
    'pornography': {
        'p_child': ('کودک‌آزاری', InputReportReasonChildAbuse(), 'Child abuse content'),
        'p_services': ('خدمات جنسی غیرقانونی', InputReportReasonPornography(), 'Illegal sexual services'),
        'p_animal': ('حیوان‌آزاری', InputReportReasonPornography(), 'Animal abuse in sexual context'),
        'p_nonconsensual': ('بدون رضایت', InputReportReasonPornography(), 'Non-consensual pornography'),
        'p_immoral': ('غیر اخلاقی', InputReportReasonPornography(), 'Immoral adult content'),
        'p_other': ('محتوای جنسی دیگر', InputReportReasonPornography(), 'Other adult content')
    },
    'personal_details': {
        'pd_docs': ('اسناد خصوصی', InputReportReasonPersonalDetails(), 'Private documents leak'),
        'pd_phone': ('شماره تلفن', InputReportReasonPersonalDetails(), 'Private phone number leak'),
        'pd_address': ('آدرس', InputReportReasonPersonalDetails(), 'Private address leak'),
        'pd_stolen': ('اطلاعات دزدیده شده', InputReportReasonPersonalDetails(), 'Stolen private details'),
        'pd_other': ('اطلاعات خصوصی دیگر', InputReportReasonPersonalDetails(), 'Other private details leak')
    },
    'fake_scam': {
        'scam_impersonation': ('جعل هویت', InputReportReasonFake(), 'Impersonation / Fake account'),
        'scam_financial': ('ادعاهای مالی فریبنده یا غیرواقعی', InputReportReasonFake(), 'Financial scam'),
        'scam_phishing': ('بدافزار، فیشینگ', InputReportReasonFake(), 'Phishing / Malware link'),
        'scam_fake_seller': ('فروشنده، محصول یا خدمت جعلی', InputReportReasonFake(), 'Fake seller or product')
    },
    'spam': {
        's_insult': ('اهانت یا اطلاعات نادرست', InputReportReasonSpam(), 'Spam insult or misinformation'),
        's_promo': ('تبلیغ محتوای دیگر', InputReportReasonSpam(), 'Promoting other content / spam')
    },
    'other': {
        'o_not_interested': ('به این علاقه ندارم', InputReportReasonOther(), 'Not interested'),
        'o_misinfo': ('اطلاعات نادرست یا تهمت', InputReportReasonOther(), 'Misinformation or slander'),
        'o_something_else': ('چیزی دیگر', InputReportReasonOther(), 'Something else')
    }
}

DEFAULT_DATA = {
    "admins": {},
    "users": [],
    "blocked": [],
    "force_channels": [],
    "admin_data": {},
    "global_smtp_status": "on",
    "send_today": 0,
    "send_week": 0,
    "today_date": "",
    "week_number": "",
    "bot_status": "on",
    "user_lang": {}
}

USER_STATE = {}

# ==================== HELPER FUNCTIONS ====================

async def close_pending_client(user_id):
    state = USER_STATE.get(user_id)
    if state and isinstance(state, dict):
        client = state.get("client")
        if client and isinstance(client, TelegramClient):
            try:
                if client.is_connected():
                    await client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting pending client for user {user_id}: {e}")

def load_data():
    if not os.path.exists(DATA_FILE):
        data = copy.deepcopy(DEFAULT_DATA)
        save_data(data)
        return data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    for key, value in DEFAULT_DATA.items():
        if key not in data:
            data[key] = copy.deepcopy(value)
    
    def safe_list(k):
        if not isinstance(data.get(k), list):
            data[k] = []
    def safe_dict(k):
        if not isinstance(data.get(k), dict):
            data[k] = {}

    safe_list("users")
    safe_list("blocked")
    safe_list("force_channels")
    safe_dict("admin_data")
    safe_dict("admins")
    safe_dict("user_lang")

    if not isinstance(data.get("send_today"), int):
        data["send_today"] = 0
    if not isinstance(data.get("send_week"), int):
        data["send_week"] = 0
    if not isinstance(data.get("today_date"), str):
        data["today_date"] = ""
    if not isinstance(data.get("week_number"), str):
        data["week_number"] = ""

    for uid_str, info in list(data["admins"].items()):
        if isinstance(info, dict):
            if isinstance(info.get("expires"), str):
                try:
                    info["expires"] = datetime.fromisoformat(info["expires"])
                except ValueError:
                    info["expires"] = datetime.now(pytz.timezone('Asia/Tehran'))
            if isinstance(info.get("activated"), str):
                try:
                    info["activated"] = datetime.fromisoformat(info["activated"])
                except ValueError:
                    info["activated"] = datetime.now(pytz.timezone('Asia/Tehran'))

    for uid_str in data.get("admins", {}):
        data.setdefault("admin_data", {}).setdefault(uid_str, {
            "smtp": [],
            "active_senders": [],
            "recipients": []
        })
    for oid in OWNER_IDS:
        data.setdefault("admin_data", {}).setdefault(str(oid), {
            "smtp": [],
            "active_senders": [],
            "recipients": []
        })
    return data

def save_data(data):
    data_to_save = copy.deepcopy(data)
    if "admins" in data_to_save:
        admins_copy = {}
        for uid_str, info in data_to_save["admins"].items():
            info_copy = info.copy()
            if isinstance(info_copy.get("expires"), datetime):
                info_copy["expires"] = info_copy["expires"].isoformat()
            if isinstance(info_copy.get("activated"), datetime):
                info_copy["activated"] = info_copy["activated"].isoformat()
            admins_copy[uid_str] = info_copy
        data_to_save["admins"] = admins_copy
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Save data error: {e}")

def is_owner(user_id):
    return user_id in OWNER_IDS

def is_admin(user_id):
    data = load_data()
    admins = data.get("admins", {})
    if str(user_id) not in admins:
        return False
    try:
        tehran = pytz.timezone('Asia/Tehran')
        now = datetime.now(tehran)
        expires = admins[str(user_id)]["expires"]
        if expires.tzinfo is None:
            expires = tehran.localize(expires)
        return expires > now
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

def can_telegram_reporter(user_id):
    return is_owner(user_id) or is_admin(user_id)

def get_user_lang(user_id):
    data = load_data()
    return data.get("user_lang", {}).get(str(user_id), None)

def set_user_lang(user_id, lang):
    data = load_data()
    data.setdefault("user_lang", {})[str(user_id)] = lang
    save_data(data)

def is_blocked(user_id):
    data = load_data()
    return str(user_id) in [str(x) for x in data.get("blocked", [])]

def get_admin_sessions_dir(admin_id):
    d = os.path.join(ADMIN_SESSIONS_DIR, str(admin_id))
    os.makedirs(d, exist_ok=True)
    return d

def get_user_sessions(user_id, force_refresh=False):
    cache_attr = f"session_cache_{user_id}"
    if not hasattr(get_user_sessions, cache_attr) or force_refresh:
        sessions = []
        if is_owner(user_id):
            for root, dirs, files in os.walk(ADMIN_SESSIONS_DIR):
                for f in files:
                    if f.endswith('.session'):
                        rel_path = os.path.relpath(os.path.join(root, f), ADMIN_SESSIONS_DIR)
                        admin_id_str = rel_path.split(os.sep)[0]
                        sessions.append((admin_id_str, f))
        else:
            admin_dir = get_admin_sessions_dir(user_id)
            for f in os.listdir(admin_dir):
                if f.endswith('.session'):
                    sessions.append((str(user_id), f))
        setattr(get_user_sessions, cache_attr, sessions)
    return getattr(get_user_sessions, cache_attr)

def clear_user_cache(user_id=None):
    if user_id:
        cache_attr = f"session_cache_{user_id}"
        if hasattr(get_user_sessions, cache_attr):
            delattr(get_user_sessions, cache_attr)
    else:
        for attr in list(get_user_sessions.__dict__.keys()):
            if attr.startswith("session_cache_"):
                delattr(get_user_sessions, attr)

def test_smtp_connection_sync(email, app_password):
    server = None
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(email, app_password)
        return True
    except Exception as e:
        logger.error(f"SMTP test failed for {email}: {e}")
        return False
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass

async def test_smtp_connection(email, app_password):
    return await asyncio.to_thread(test_smtp_connection_sync, email, app_password)

def send_email_sync(sender_email, password, to_email, subject, body):
    server = None
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, password)
        server.sendmail(sender_email, to_email, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass

def sync_send_counters(data_db):
    tehran = pytz.timezone('Asia/Tehran')
    now = datetime.now(tehran)
    today_str = now.strftime('%Y-%m-%d')
    week_str = now.strftime('%Y-%W')
    changed = False
    if data_db.get("today_date") != today_str:
        data_db["today_date"] = today_str
        data_db["send_today"] = 0
        changed = True
    if data_db.get("week_number") != week_str:
        data_db["week_number"] = week_str
        data_db["send_week"] = 0
        changed = True
    return changed

def bump_send_counters(data_db, count=1):
    if count <= 0:
        return
    sync_send_counters(data_db)
    data_db["send_today"] = data_db.get("send_today", 0) + count
    data_db["send_week"] = data_db.get("send_week", 0) + count

async def join_channel_with_approval(client, entity, session_file):
    try:
        await client(JoinChannelRequest(entity))
        return {'success': True, 'message': "✅ Joined"}
    except errors.UserAlreadyParticipantError:
        return {'success': True, 'message': "✅ Already joined"}
    except errors.InviteRequestSentError:
        return {'success': True, 'message': "✅ Join request sent"}
    except errors.FloodWaitError as e:
        return {'success': False, 'message': f"❌ Flood wait: {e.seconds}s"}
    except errors.ChannelPrivateError:
        return {'success': False, 'message': "❌ Channel is private"}
    except errors.ChannelInvalidError:
        return {'success': False, 'message': "❌ Invalid channel"}
    except Exception as e:
        return {'success': False, 'message': f"❌ Error: {str(e)[:30]}"}

async def validate_phone_number(phone):
    if not phone.startswith('+'):
        return False
    clean = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if len(clean) < 8 or len(clean) > 15:
        return False
    if not clean[1:].isdigit():
        return False
    return True

async def validate_post_link(link):
    if not (link.startswith('https://t.me/') or link.startswith('t.me/')):
        return False
    pattern = r'(?:https?://)?t\.me/(?:c/)?([^/]+)(?:/(\d+))?'
    match = re.search(pattern, link)
    if not match:
        return False
    return True

# ==================== KEYBOARD FUNCTIONS ====================

def main_menu_keyboard(user_id):
    lang = get_user_lang(user_id) or "fa"
    if not (is_owner(user_id) or is_admin(user_id)):
        return None
    kb = [
        [
            Button.inline("📧 ایمیل ریپورتر" if lang == "fa" else "📧 Email Reporter", "menu_email", style="primary"),
            Button.inline("🚫 تلگرام ریپورتر" if lang == "fa" else "🚫 Telegram Reporter", "menu_telegram", style="primary")
        ],
        [
            Button.inline("🌐 تغییر زبان" if lang == "fa" else "🌐 Change Language", "change_lang", style="success"),
            Button.url("📞 پشتیبانی / Support", "https://t.me/shikh4")
        ]
    ]
    if is_owner(user_id):
        kb.append([Button.inline("👑 پنل مالک" if lang == "fa" else "👑 Owner Panel", "owner_panel", style="danger")])
        kb.append([Button.inline("➕ افزودن ادمین" if lang == "fa" else "➕ Add Admin", "add_admin", style="success")])
    return kb

def owner_panel_keyboard(user_id):
    lang = get_user_lang(user_id) or "fa"
    return [
        [
            Button.inline("📢 پیام همگانی" if lang == "fa" else "📢 Broadcast", "em_broadcast", style="primary"),
            Button.inline("👤 پیام به کاربر" if lang == "fa" else "👤 Message User", "em_msg_user", style="primary")
        ],
        [
            Button.inline("🚫 بلاک کاربر" if lang == "fa" else "🚫 Block User", "em_block", style="danger"),
            Button.inline("✅ آنبلاک کاربر" if lang == "fa" else "✅ Unblock User", "em_unblock", style="success")
        ],
        [
            Button.inline("📢 مدیریت کانال اجباری" if lang == "fa" else "📢 Manage Force Channel", "em_force_channel", style="primary")
        ],
        [Button.inline("🔙 بازگشت به منوی اصلی" if lang == "fa" else "🔙 Back to Main Menu", "back_main", style="primary")]
    ]

def email_menu_keyboard(user_id):
    lang = get_user_lang(user_id) or "fa"
    kb = []
    if lang == "fa":
        kb.append([
            Button.inline("➕ افزودن SMTP", "em_smtp_add", style="primary"),
            Button.inline("📋 لیست SMTP", "em_smtp_list", style="primary")
        ])
        kb.append([
            Button.inline("🟢 فعال‌سازی ارسال‌کننده", "em_activate", style="success"),
            Button.inline("📧 ارسال تکی", "em_single_send", style="primary")
        ])
        kb.append([
            Button.inline("📨 ارسال گروهی", "em_bulk_send", style="success"),
            Button.inline("👥 لیست گیرنده‌ها", "em_recips", style="primary")
        ])
        kb.append([
            Button.inline("➕ افزودن گیرنده", "em_add_recip", style="primary"),
            Button.inline("🗑 پاک‌کردن گیرنده‌ها", "em_clear_recip", style="danger")
        ])
        kb.append([
            Button.inline("📊 آمار زنده", "em_stats", style="primary"),
            Button.inline("دریافت نمایندگی", "em_agency", style="success")
        ])
        kb.append([Button.inline("🔙 بازگشت به منوی اصلی", "back_main", style="primary")])
    else:
        kb.append([
            Button.inline("➕ ADD SMTP", "em_smtp_add", style="primary"),
            Button.inline("📋 SMTP LIST", "em_smtp_list", style="primary")
        ])
        kb.append([
            Button.inline("🟢 ACTIVATE SENDER", "em_activate", style="success"),
            Button.inline("📧 SEND SINGLE", "em_single_send", style="primary")
        ])
        kb.append([
            Button.inline("📨 BULK SEND", "em_bulk_send", style="success"),
            Button.inline("👥 RECIPIENTS LIST", "em_recips", style="primary")
        ])
        kb.append([
            Button.inline("➕ ADD RECIPIENT", "em_add_recip", style="primary"),
            Button.inline("🗑 CLEAR RECIPIENTS", "em_clear_recip", style="danger")
        ])
        kb.append([
            Button.inline("📊 LIVE STATS", "em_stats", style="primary"),
            Button.inline("AGENCY", "em_agency", style="success")
        ])
        kb.append([Button.inline("🔙 BACK TO MAIN MENU", "back_main", style="primary")])
    return kb

def force_channel_keyboard(user_id):
    lang = get_user_lang(user_id) or "fa"
    return [
        [
            Button.inline("➕ افزودن کانال" if lang=="fa" else "➕ ADD CHANNEL", "em_fc_add", style="primary"),
            Button.inline("➖ حذف کانال" if lang=="fa" else "➖ REMOVE CHANNEL", "em_fc_remove", style="danger")
        ],
        [
            Button.inline("📋 لیست کانال‌ها" if lang=="fa" else "📋 CHANNEL LIST", "em_fc_list", style="primary"),
            Button.inline("🔙 بازگشت" if lang=="fa" else "🔙 BACK", "em_back", style="primary")
        ]
    ]

def telegram_menu_keyboard(user_id):
    lang = get_user_lang(user_id) or "fa"
    is_own = is_owner(user_id)
    kb = []
    kb.append([
        Button.inline("🚫 ریپورت کانال/گروه" if lang=="fa" else "🚫 REPORT CHANNEL/GROUP", "tg_report", style="danger"),
        Button.inline("📝 ریپورت پست" if lang=="fa" else "📝 REPORT POST", "tg_report_post", style="danger")
    ])
    kb.append([
        Button.inline("👤 ریپورت پروفایل" if lang=="fa" else "👤 REPORT PROFILE", "tg_report_profile", style="danger"),
        Button.inline("🤖 ریپورت ربات" if lang=="fa" else "🤖 REPORT BOT", "tg_report_bot", style="danger")
    ])
    kb.append([
        Button.inline("👤 ریپورت اکانت" if lang=="fa" else "👤 REPORT ACCOUNT", "tg_report_account", style="danger"),
        Button.inline("📋 ریپورت دستی" if lang=="fa" else "📋 MANUAL REPORT", "tg_manual_report", style="primary")
    ])
    kb.append([
        Button.inline("🌐 لیست و وضعیت پروکسی‌ها" if lang=="fa" else "🌐 PROXIES STATUS", "tg_proxies_list", style="primary")
    ])
    if is_own:
        kb.append([
            Button.inline("⚙️ مدیریت اکانت‌ها" if lang=="fa" else "⚙️ MANAGE ACCOUNTS", "tg_manage_acc", style="primary"),
            Button.inline("🔙 بازگشت به منوی اصلی" if lang=="fa" else "🔙 BACK TO MAIN MENU", "back_main", style="primary")
        ])
    else:
        kb.append([
            Button.inline("➕ افزودن اکانت" if lang=="fa" else "➕ ADD ACCOUNT", "tg_add_acc", style="success"),
            Button.inline("📋 لیست اکانت‌ها" if lang=="fa" else "📋 LIST ACCOUNTS", "tg_list_shared", style="primary")
        ])
        kb.append([
            Button.inline("🗑 حذف اکانت" if lang=="fa" else "🗑 DELETE ACCOUNT", "tg_del_acc", style="danger"),
            Button.inline("🔙 بازگشت به منوی اصلی" if lang=="fa" else "🔙 BACK TO MAIN MENU", "back_main", style="primary")
        ])
    return kb

def manage_accounts_keyboard(user_id):
    lang = get_user_lang(user_id) or "fa"
    return [
        [
            Button.inline("➕ افزودن اکانت" if lang=="fa" else "➕ ADD ACCOUNT", "tg_add_acc", style="success"),
            Button.inline("🗑 حذف اکانت" if lang=="fa" else "🗑 DELETE ACCOUNT", "tg_del_acc", style="danger")
        ],
        [
            Button.inline("📋 لیست اکانت‌ها" if lang=="fa" else "📋 LIST ACCOUNTS", "tg_list_all", style="primary"),
            Button.inline("📋 لیست اشتراکی" if lang=="fa" else "📋 LIST SHARED", "tg_list_shared", style="primary")
        ],
        [Button.inline("🔙 بازگشت" if lang=="fa" else "🔙 BACK", "tg_back", style="primary")]
    ]

def main_reason_keyboard(lang="fa"):
    buttons = []
    for key, val in REPORT_MAIN_REASONS.items():
        buttons.append([Button.inline(val[0], f"tg_reason_main_{key}")])
    buttons.append([Button.inline("🔙 بازگشت" if lang == "fa" else "🔙 Back", "tg_back")])
    return buttons

def sub_reason_keyboard(parent_key, lang="fa"):
    buttons = []
    subs = REPORT_SUB_REASONS.get(parent_key, {})
    for sub_key, val in subs.items():
        buttons.append([Button.inline(f"➡️ {val[0]}", f"tg_reason_sub_{sub_key}")])
    buttons.append([Button.inline("🔙 بازگشت" if lang == "fa" else "🔙 Back", "tg_reason_back_main")])
    return buttons

def admin_duration_keyboard(lang):
    return [
        [
            Button.inline("1 ساعت" if lang=="fa" else "1 hour", "adm_1h", style="primary"),
            Button.inline("1 روز" if lang=="fa" else "1 day", "adm_1d", style="primary")
        ],
        [
            Button.inline("1 هفته" if lang=="fa" else "1 week", "adm_1w", style="primary"),
            Button.inline("1 ماه" if lang=="fa" else "1 month", "adm_1m", style="primary")
        ],
        [
            Button.inline("3 ماه" if lang=="fa" else "3 months", "adm_3m", style="primary"),
            Button.inline("6 ماه" if lang=="fa" else "6 months", "adm_6m", style="primary")
        ],
        [
            Button.inline("1 سال" if lang=="fa" else "1 year", "adm_1y", style="success"),
            Button.inline("🔙 برگشت" if lang=="fa" else "🔙 Back", "back_main", style="primary")
        ]
    ]

# ==================== FORCE JOIN ====================

async def get_missing_channels(client, user_id, data_db):
    channels = data_db.get("force_channels", [])
    missing = []
    for ch in channels:
        try:
            await client(GetParticipantRequest(channel=ch, participant=user_id))
        except Exception:
            missing.append(ch)
    return missing

def force_join_keyboard(channels, lang):
    kb = []
    for ch in channels:
        username = ch.lstrip("@")
        kb.append([Button.url(f"📢 {ch}", f"https://t.me/{username}")])
    kb.append([Button.inline("✅ عضو شدم، بررسی کن" if lang == "fa" else "✅ I joined, check again", "check_join")])
    return kb

def force_join_message(lang):
    return ("⚠️ برای استفاده از ربات ابتدا باید در کانال‌های زیر عضو شوید:" if lang == "fa"
            else "⚠️ You must join the following channels before using this bot:")

# ==================== REPORT EXECUTION LOGIC ====================

async def handle_report_callbacks(event, data, user_id, lang, USER_STATE):
    if data.startswith("tg_reason_main_"):
        reason_key = data.replace("tg_reason_main_", "", 1)
        if reason_key in REPORT_SUB_REASONS and REPORT_SUB_REASONS[reason_key]:
            await event.edit(
                "📋 لطفاً جزئیات دقیق‌تر را انتخاب کنید:" if lang == "fa" else "📋 Please select a sub-reason:",
                buttons=sub_reason_keyboard(reason_key, lang)
            )
            return True

        state = USER_STATE.get(user_id, {})
        if state:
            state["reason_obj"] = REPORT_MAIN_REASONS[reason_key][1]
            state["default_msg"] = REPORT_MAIN_REASONS[reason_key][2]
            state["reason_name"] = REPORT_MAIN_REASONS[reason_key][0]
            state["step"] = "count_per_account"
            prompt = "🔢 تعداد ریپورت هر اکانت؟ (1-50)" if lang == "fa" else "🔢 Reports per account? (1-50)"
            await event.edit(prompt)
        return True

    if data.startswith("tg_reason_sub_"):
        sub_key = data.replace("tg_reason_sub_", "", 1)
        sub_data = None
        for subs in REPORT_SUB_REASONS.values():
            if sub_key in subs:
                sub_data = subs[sub_key]
                break

        state = USER_STATE.get(user_id, {})
        if state and sub_data:
            state["reason_obj"] = sub_data[1]
            state["default_msg"] = sub_data[2]
            state["reason_name"] = sub_data[0]
            state["step"] = "count_per_account"
            prompt = "🔢 تعداد ریپورت هر اکانت؟ (1-50)" if lang == "fa" else "🔢 Reports per account? (1-50)"
            await event.edit(prompt)
        return True

    if data == "tg_reason_back_main":
        await event.edit("📝 دلیل ریپورت را انتخاب کنید:", buttons=main_reason_keyboard(lang))
        return True

    return False

async def perform_report(client, entity, reason, message, count=1, msg_ids=None, retries=2):
    successes = 0
    failures = 0
    for i in range(count):
        attempt = 0
        while attempt <= retries:
            try:
                if msg_ids:
                    await client(ReportMessageRequest(
                        peer=entity,
                        id=msg_ids if isinstance(msg_ids, list) else [msg_ids],
                        reason=reason,
                        message=message
                    ))
                else:
                    await client(ReportPeerRequest(
                        peer=entity,
                        reason=reason,
                        message=message
                    ))
                successes += 1
                break
            except errors.FloodWaitError as e:
                failures += 1
                logger.warning(f"FloodWait hit: {e.seconds}s delay required.")
                await asyncio.sleep(min(e.seconds, 60))
                break
            except Exception as e:
                if attempt < retries:
                    logger.warning(f"Report failed, retrying ({attempt+1}/{retries}): {e}")
                    await asyncio.sleep(2)
                    attempt += 1
                else:
                    failures += 1
                    logger.error(f"Report failed after {retries+1} attempts: {e}")
                    break
        if i < count - 1:
            delay = random.uniform(5.0, 12.0)
            await asyncio.sleep(delay)
    return successes, failures

async def execute_report_operation(event, state, user_id, lang):
    sessions = state.get("selected_sessions", [])
    op_type = state.get("type")
    
    reason_obj = state.get("reason_obj", InputReportReasonSpam())
    default_msg = state.get("default_msg", "Reported by user")
    reason_name = state.get("reason_name", "Spam")
    
    custom_msg = state.get("custom_reason", default_msg)
    if custom_msg == "/skip" or not custom_msg:
        custom_msg = default_msg

    count_per_account = state.get("count_per_account", 1)

    total_success = 0
    total_fail = 0
    errors_list = []

    proxies_list = load_proxies()
    has_proxies = len(proxies_list) > 0

    status_msg = await event.reply(
        f"🚀 شروع عملیات ریپورت با شبیه‌سازی دستگاه واقعی و پروکسی...\n"
        f"🌐 وضعیت پروکسی: {'پروکسی فعال (' + str(len(proxies_list)) + ' عدد)' if has_proxies else 'بدون پروکسی (آی‌پی مستقیم)'}"
        if lang == "fa" else
        f"🚀 Starting report operation with device emulation...\n"
        f"🌐 Proxies: {'Active (' + str(len(proxies_list)) + ' available)' if has_proxies else 'Direct IP'}"
    )

    total_sessions = len(sessions)
    for idx, (admin_id_str, filename) in enumerate(sessions, 1):
        path = os.path.join(ADMIN_SESSIONS_DIR, admin_id_str, filename)
        if not os.path.exists(path):
            total_fail += 1
            continue

        # خواندن سشن
        try:
            with open(path, 'r', encoding='utf-8') as f:
                session_str = f.read().strip()
            if not session_str:
                total_fail += 1
                continue
        except Exception as e:
            total_fail += 1
            logger.error(f"Failed to read session {path}: {e}")
            continue

        # انتخاب پروکسی با تلاش برای اتصال
        proxy_used = None
        proxy_str = "آی‌پی مستقیم سرور"
        if has_proxies:
            for p in proxies_list:
                try:
                    # تست واقعی پروکسی با استفاده از سشن اکانت
                    test_client = TelegramClient(
                        StringSession(session_str), 
                        API_ID, 
                        API_HASH, 
                        proxy=p,
                        device_model="TestDevice",
                        system_version="TestOS",
                        app_version="1.0",
                        lang_code="en"
                    )
                    await test_client.connect()
                    if await test_client.is_user_authorized():
                        # اگر اتصال و احراز هویت موفق بود، پروکسی کار می‌کند
                        await test_client.disconnect()
                        proxy_used = p
                        proxy_str = f"{p[1]}:{p[2]}"
                        break
                    await test_client.disconnect()
                except Exception as e:
                    logger.warning(f"Proxy test failed for {p}: {e}")
                    continue
            if proxy_used is None:
                proxy_str = "⚠️ پروکسی‌ها نامعتبر، استفاده از آی‌پی مستقیم"
                logger.warning("All proxies failed, using direct IP")

        device_info = random.choice(DEVICE_MODELS)

        client = None
        try:
            client = TelegramClient(
                StringSession(session_str), 
                API_ID, 
                API_HASH, 
                proxy=proxy_used,
                device_model=device_info["device_model"],
                system_version=device_info["system_version"],
                app_version=device_info["app_version"],
                lang_code=device_info["lang_code"]
            )
            await client.connect()
            
            if not await client.is_user_authorized():
                total_fail += 1
                continue

            try:
                if op_type == "report_post":
                    post_links = state.get("post_links", [])
                    post_count = state.get("post_count", 0)
                    channel_link = state.get("channel_link", None)

                    if post_links:
                        for link in post_links:
                            pattern = r'(?:https?://)?t\.me/(?:c/)?([^/]+)/(\d+)'
                            match = re.search(pattern, link)
                            if not match:
                                continue
                            chn_raw = match.group(1)
                            if chn_raw.isdigit():
                                if not chn_raw.startswith("-100"):
                                    chn = int("-100" + chn_raw)
                                else:
                                    chn = int(chn_raw)
                            else:
                                chn = chn_raw
                            p_id = int(match.group(2))
                            
                            try:
                                target_entity = await client.get_entity(chn)
                                if getattr(target_entity, 'broadcast', False) or getattr(target_entity, 'megagroup', False):
                                    join_result = await join_channel_with_approval(client, target_entity, filename)
                                    if not join_result['success']:
                                        errors_list.append(f"{filename} (Post {link}): {join_result['message']}")
                                        total_fail += count_per_account
                                        continue
                                s, f = await perform_report(
                                    client=client,
                                    entity=target_entity,
                                    reason=reason_obj,
                                    message=custom_msg,
                                    count=count_per_account,
                                    msg_ids=[p_id]
                                )
                                total_success += s
                                total_fail += f
                            except Exception as e:
                                total_fail += count_per_account
                                errors_list.append(f"{filename} (Post {link}): {str(e)[:40]}")
                    elif post_count and channel_link:
                        try:
                            clean_channel = channel_link.replace("https://t.me/", "").replace("t.me/", "").replace("@", "")
                            if clean_channel.isdigit():
                                entity_id = int(clean_channel)
                            else:
                                entity_id = "@" + clean_channel
                            target_entity = await client.get_entity(entity_id)
                            
                            if getattr(target_entity, 'broadcast', False) or getattr(target_entity, 'megagroup', False):
                                join_result = await join_channel_with_approval(client, target_entity, filename)
                                if not join_result['success']:
                                    errors_list.append(f"{filename} (Channel {channel_link}): {join_result['message']}")
                                    total_fail += (post_count * count_per_account)
                                    continue
                            
                            messages = await client.get_messages(target_entity, limit=min(post_count, 100))
                            if not messages:
                                errors_list.append(f"{filename} (Channel {channel_link}): No messages found")
                                total_fail += (post_count * count_per_account)
                                continue
                            
                            for msg in messages:
                                s, f = await perform_report(
                                    client=client,
                                    entity=target_entity,
                                    reason=reason_obj,
                                    message=custom_msg,
                                    count=count_per_account,
                                    msg_ids=[msg.id]
                                )
                                total_success += s
                                total_fail += f
                        except Exception as e:
                            total_fail += (post_count * count_per_account)
                            errors_list.append(f"{filename} (Channel {channel_link}): {str(e)[:40]}")
                else:
                    target_str = state.get("target", "").strip()
                    clean_target = target_str.replace("https://t.me/", "").replace("t.me/", "").replace("@", "")
                    
                    if clean_target.startswith("c/") and clean_target[2:].split('/')[0].isdigit():
                        raw_id = clean_target[2:].split('/')[0]
                        clean_target = int("-100" + raw_id) if not raw_id.startswith("-100") else int(raw_id)
                    elif clean_target.startswith("-100") and clean_target[4:].isdigit():
                        clean_target = int(clean_target)
                    elif clean_target.isdigit():
                        clean_target = int(clean_target)
                    elif not clean_target.startswith("+"):
                        clean_target = "@" + clean_target

                    target_entity = await client.get_entity(clean_target)

                    if op_type in ["report", "manual_report"]:
                        if getattr(target_entity, 'broadcast', False) or getattr(target_entity, 'megagroup', False):
                            join_result = await join_channel_with_approval(client, target_entity, filename)
                            if not join_result['success']:
                                errors_list.append(f"{filename}: {join_result['message']}")
                                total_fail += count_per_account
                                continue

                    s, f = await perform_report(
                        client=client,
                        entity=target_entity,
                        reason=reason_obj,
                        message=custom_msg,
                        count=count_per_account
                    )
                    total_success += s
                    total_fail += f

            except Exception as e:
                if op_type == "report_post":
                    if state.get("post_count"):
                        total_fail += (state.get("post_count", 0) * count_per_account)
                    else:
                        total_fail += (len(state.get("post_links", [])) * count_per_account)
                else:
                    total_fail += count_per_account
                errors_list.append(f"{filename}: {str(e)[:40]}")

        except Exception as e:
            if op_type == "report_post":
                if state.get("post_count"):
                    total_fail += (state.get("post_count", 0) * count_per_account)
                else:
                    total_fail += (len(state.get("post_links", [])) * count_per_account)
            else:
                total_fail += count_per_account
            errors_list.append(f"{filename}: {str(e)[:40]}")
        finally:
            if client and client.is_connected():
                await client.disconnect()

        if idx < total_sessions:
            delay = random.randint(30, 70)
            try:
                await status_msg.edit(
                    f"📊 **پیشرفت گزارش‌دهی ({idx}/{total_sessions})**\n\n"
                    f"📱 اکانت: +{filename.replace('.session','')}\n"
                    f"💻 دستگاه: {device_info['device_model']}\n"
                    f"🌐 پروکسی: {proxy_str}\n"
                    f"✅ موفق: {total_success} | ❌ ناموفق: {total_fail}\n\n"
                    f"⏱ تاخیر هوشمند کاربر واقعی ({delay} ثانیه)..."
                    if lang == "fa" else
                    f"📊 **Progress ({idx}/{total_sessions})**\n\n"
                    f"📱 Account: +{filename.replace('.session','')}\n"
                    f"💻 Device: {device_info['device_model']}\n"
                    f"🌐 Proxy: {proxy_str}\n"
                    f"✅ Success: {total_success} | ❌ Fail: {total_fail}\n\n"
                    f"⏱ Human Delay ({delay}s)..."
                )
            except Exception:
                pass
            await asyncio.sleep(delay)

    result = (
        f"📊 **عملیات ریپورت با موفقیت پایان یافت**\n\n"
        f"🎯 دلیل: {reason_name}\n"
        f"👥 تعداد اکانت‌ها: {total_sessions}\n"
        f"🔢 ریپورت/اکانت: {count_per_account}\n"
        f"✅ گزارش‌های موفق: {total_success}\n"
        f"❌ گزارش‌های ناموفق: {total_fail}"
        if lang == "fa" else
        f"📊 **Report Operation Complete**\n\n"
        f"🎯 Reason: {reason_name}\n"
        f"👥 Accounts: {total_sessions}\n"
        f"🔢 Reports/Account: {count_per_account}\n"
        f"✅ Success: {total_success}\n"
        f"❌ Failed: {total_fail}"
    )

    if errors_list:
        unique_errors = list(set(errors_list))[:5]
        result += ("\n\n⚠️ خطاهای ثبت شده:\n" + "\n".join(unique_errors)) if lang == "fa" else ("\n\n⚠️ Logged Errors:\n" + "\n".join(unique_errors))

    try:
        await status_msg.edit(result)
    except Exception:
        await event.reply(result)

# ==================== EVENT HANDLERS ====================

async def start_handler(event):
    user_id = event.sender_id
    if is_blocked(user_id):
        await event.reply("🚫 شما بلاک هستید" if get_user_lang(user_id) == "fa" else "🚫 You are blocked")
        return

    await close_pending_client(user_id)
    USER_STATE.pop(user_id, None)

    data = load_data()
    if user_id not in data["users"]:
        data["users"].append(user_id)
        save_data(data)

    lang = get_user_lang(user_id)
    if lang is None:
        buttons = [
            [Button.inline("فارسی", "lang_fa", style="primary"), Button.inline("English", "lang_en", style="primary")]
        ]
        await event.reply("🌍 Please choose your language:\nلطفاً زبان خود را انتخاب کنید:", buttons=buttons)
        return

    if not (is_owner(user_id) or is_admin(user_id)):
        await event.reply(
            "⛔ شما مجاز به استفاده از این ربات نیستید. لطفاً با پشتیبانی تماس بگیرید." if lang == "fa" else "⛔ You are not authorized to use this bot. Please contact support."
        )
        return

    if not is_owner(user_id):
        missing = await get_missing_channels(event.client, user_id, data)
        if missing:
            await event.reply(force_join_message(lang), buttons=force_join_keyboard(missing, lang))
            return

    await event.reply(
        "✅ به ربات ریپورتر شیخ خوش آمدید" if lang == "fa" else "✅ Welcome to SHIKH REPORTER Bot",
        buttons=main_menu_keyboard(user_id)
    )

async def callback_handler(event):
    data_str = event.data.decode('utf-8')
    user_id = event.sender_id
    lang = get_user_lang(user_id) or "fa"

    if data_str in ["noop", "none"]:
        await event.answer()
        return

    if data_str in ["lang_fa", "lang_en"]:
        lang_code = "fa" if data_str == "lang_fa" else "en"
        set_user_lang(user_id, lang_code)
        lang = lang_code
        if not (is_owner(user_id) or is_admin(user_id)):
            await event.edit(
                "⛔ شما مجاز به استفاده از این ربات نیستید. لطفاً با پشتیبانی تماس بگیرید." if lang == "fa" else "⛔ You are not authorized to use this bot. Please contact support."
            )
            return
        if not is_owner(user_id):
            missing = await get_missing_channels(event.client, user_id, load_data())
            if missing:
                await event.edit(force_join_message(lang), buttons=force_join_keyboard(missing, lang))
                return
        await event.edit(
            "✅ زبان ذخیره شد" if lang == "fa" else "✅ Language saved",
            buttons=main_menu_keyboard(user_id)
        )
        return

    if not (is_owner(user_id) or is_admin(user_id)):
        await event.answer("⛔ دسترسی غیرمجاز" if lang == "fa" else "⛔ Unauthorized", alert=True)
        return

    if data_str == "check_join":
        missing = await get_missing_channels(event.client, user_id, load_data())
        if missing:
            await event.answer("⛔ هنوز عضو همه‌ی کانال‌ها نشدید" if lang == "fa" else "⛔ You haven't joined all channels yet", alert=True)
            await event.edit(force_join_message(lang), buttons=force_join_keyboard(missing, lang))
            return
        await event.answer("✅ تایید شد" if lang == "fa" else "✅ Verified")
        await event.edit(
            "✅ به ربات ریپورتر شیخ خوش آمدید" if lang == "fa" else "✅ Welcome to SHIKH REPORTER Bot",
            buttons=main_menu_keyboard(user_id)
        )
        return

    if not is_owner(user_id):
        missing = await get_missing_channels(event.client, user_id, load_data())
        if missing:
            await event.edit(force_join_message(lang), buttons=force_join_keyboard(missing, lang))
            return

    if data_str == "change_lang":
        buttons = [
            [Button.inline("فارسی", "lang_fa", style="primary"), Button.inline("English", "lang_en", style="primary")]
        ]
        await event.edit("🌍 انتخاب زبان / Choose language:", buttons=buttons)
        return

    if data_str == "menu_email":
        await event.edit(
            "📧 **ایمیل ریپورتر**" if lang == "fa" else "📧 **Email Reporter**",
            buttons=email_menu_keyboard(user_id)
        )
        return

    if data_str == "menu_telegram":
        if not can_telegram_reporter(user_id):
            await event.answer("⛔ دسترسی غیرمجاز" if lang == "fa" else "⛔ Unauthorized access", alert=True)
            return
        await event.edit(
            "🚫 **تلگرام ریپورتر**" if lang == "fa" else "🚫 **Telegram Reporter**",
            buttons=telegram_menu_keyboard(user_id)
        )
        return

    if data_str == "back_main":
        await close_pending_client(user_id)
        USER_STATE.pop(user_id, None)
        await event.edit("✅ منوی اصلی" if lang == "fa" else "✅ Main Menu", buttons=main_menu_keyboard(user_id))
        return

    if data_str == "owner_panel":
        if not is_owner(user_id):
            await event.answer("⛔ دسترسی غیرمجاز" if lang == "fa" else "⛔ Unauthorized", alert=True)
            return
        await event.edit("👑 پنل مالک" if lang == "fa" else "👑 Owner Panel",
                        buttons=owner_panel_keyboard(user_id))
        return

    if data_str == "add_admin":
        if not is_owner(user_id):
            await event.answer("⛔ دسترسی غیرمجاز" if lang == "fa" else "⛔ Unauthorized", alert=True)
            return
        USER_STATE[user_id] = {"action": "add_admin", "step": "waiting_user_id"}
        await event.edit("🆔 آیدی عددی کاربر را برای افزودن به ادمین‌ها وارد کنید" if lang == "fa" else "🆔 Enter user ID to add as admin")
        return

    if data_str.startswith("adm_"):
        state = USER_STATE.get(user_id, {})
        if state.get("action") != "add_admin" or state.get("step") != "waiting_duration":
            await event.answer("⏳ لطفاً ابتدا آیدی کاربر را وارد کنید" if lang == "fa" else "⏳ Please enter user ID first", alert=True)
            return
        target_user = state.get("target_user")
        if not target_user:
            await event.answer("❌ خطا" if lang == "fa" else "❌ Error")
            return

        current_time = datetime.now(pytz.timezone('Asia/Tehran'))
        duration_map = {
            "adm_1h": timedelta(hours=1),
            "adm_1d": timedelta(days=1),
            "adm_1w": timedelta(weeks=1),
            "adm_1m": timedelta(days=30),
            "adm_3m": timedelta(days=90),
            "adm_6m": timedelta(days=180),
            "adm_1y": timedelta(days=365)
        }
        duration = duration_map.get(data_str)
        if not duration:
            await event.answer("مدت نامعتبر" if lang == "fa" else "Invalid duration")
            return

        expires = current_time + duration
        data_db = load_data()
        data_db.setdefault("admins", {})[str(target_user)] = {
            "expires": expires,
            "activated": current_time
        }
        data_db.setdefault("admin_data", {}).setdefault(str(target_user), {
            "smtp": [],
            "active_senders": [],
            "recipients": []
        })
        save_data(data_db)

        await event.edit(
            f"✅ ادمین برای کاربر {target_user} با موفقیت افزوده شد\n"
            f"تاریخ انقضا: {expires.strftime('%Y-%m-%d %H:%M:%S')}" if lang == "fa" else
            f"✅ Admin added for user {target_user}\n"
            f"Expires: {expires.strftime('%Y-%m-%d %H:%M:%S')}",
            buttons=[[Button.inline("🔙 بازگشت به منوی اصلی" if lang == "fa" else "🔙 BACK TO MAIN MENU", "back_main", style="primary")]]
        )
        USER_STATE.pop(user_id, None)
        return

    if data_str.startswith("em_"):
        await email_callback(event, data_str, user_id, lang)
        return

    if data_str.startswith("tg_"):
        await telegram_callback(event, data_str, user_id, lang)
        return

    await event.answer("Unknown")

async def email_callback(event, data, user_id, lang):
    data_db = load_data()
    admin_data = data_db.setdefault("admin_data", {}).setdefault(
        str(user_id), {"smtp": [], "active_senders": [], "recipients": []}
    )

    if data == "em_smtp_add":
        USER_STATE[user_id] = {"section": "email", "flow": "smtp", "step": "waiting_email"}
        await event.edit("📧 آدرس Gmail را وارد کنید" if lang == "fa" else "📧 Enter Gmail address")
        return

    if data == "em_smtp_list":
        smtp_list = admin_data.get("smtp", [])
        if not smtp_list:
            await event.edit("❌ SMTP ثبت نشده" if lang == "fa" else "❌ No SMTP found",
                           buttons=[[Button.inline("🔙 بازگشت" if lang == "fa" else "BACK", "em_back", style="primary")]])
            return
        kb = []
        row = []
        for smtp in smtp_list:
            email = smtp.get("email", "")
            if email:
                row.append(Button.inline(email, f"em_smtp_view_{email}", style="primary"))
                if len(row) == 2:
                    kb.append(row)
                    row = []
        if row:
            kb.append(row)
        kb.append([Button.inline("🔙 بازگشت" if lang == "fa" else "BACK", "em_back", style="primary")])
        await event.edit("📋 لیست SMTP", buttons=kb)
        return

    if data.startswith("em_smtp_view_"):
        email = data.replace("em_smtp_view_", "", 1)
        kb = [
            [Button.inline("🗑 حذف" if lang == "fa" else "DELETE", f"em_smtp_del_{email}", style="danger")],
            [Button.inline("🔙 بازگشت" if lang == "fa" else "BACK", "em_smtp_list", style="primary")]
        ]
        await event.edit(f"📧 {email}\n\nحذف شود؟" if lang == "fa" else f"📧 {email}\n\nDelete?",
                        buttons=kb)
        return

    if data.startswith("em_smtp_del_"):
        email = data.replace("em_smtp_del_", "", 1)
        admin_data["smtp"] = [s for s in admin_data.get("smtp", []) if s.get("email") != email]
        admin_data["active_senders"] = [s for s in admin_data.get("active_senders", []) if s != email]
        save_data(data_db)
        smtp_list = admin_data["smtp"]
        if not smtp_list:
            await event.edit("✅ حذف شد\n📭 لیست خالی" if lang == "fa" else "✅ Deleted\nEmpty list",
                           buttons=[[Button.inline("🔙 بازگشت" if lang == "fa" else "BACK", "em_back", style="primary")]])
            return
        kb = []
        row = []
        for s in smtp_list:
            em = s.get("email", "")
            row.append(Button.inline(em, f"em_smtp_view_{em}", style="primary"))
            if len(row) == 2:
                kb.append(row)
                row = []
        if row:
            kb.append(row)
        kb.append([Button.inline("🔙 بازگشت" if lang == "fa" else "BACK", "em_back", style="primary")])
        await event.edit("📋 لیست SMTP", buttons=kb)
        return

    if data == "em_activate":
        smtp_list = admin_data.get("smtp", [])
        active = admin_data.get("active_senders", [])
        kb = []
        for s in smtp_list:
            email = s.get("email", "")
            status = "🟢" if email in active else "🔴"
            kb.append([Button.inline(f"{status} {email}", f"em_toggle_{email}", style="success" if email in active else "primary")])
        kb.append([Button.inline("🔙 بازگشت" if lang == "fa" else "BACK", "em_back", style="primary")])
        await event.edit("🟢 انتخاب SMTP فعال" if lang == "fa" else "🟢 Select active SMTP", buttons=kb)
        return

    if data.startswith("em_toggle_"):
        email = data.replace("em_toggle_", "", 1)
        active = admin_data.get("active_senders", [])
        if email in active:
            active.remove(email)
        else:
            active.append(email)
        save_data(data_db)
        kb = []
        for s in admin_data.get("smtp", []):
            em = s.get("email", "")
            status = "🟢" if em in active else "🔴"
            kb.append([Button.inline(f"{status} {em}", f"em_toggle_{em}", style="success" if em in active else "primary")])
        kb.append([Button.inline("🔙 بازگشت" if lang == "fa" else "BACK", "em_back", style="primary")])
        await event.edit("🟢 انتخاب SMTP فعال" if lang == "fa" else "🟢 Select active SMTP", buttons=kb)
        await event.answer("✅ وضعیت تغییر کرد" if lang == "fa" else "✅ Status changed")
        return

    if data == "em_single_send":
        USER_STATE[user_id] = {"section": "email", "flow": "single", "step": "to"}
        await event.edit("📧 گیرنده را وارد کنید" if lang == "fa" else "📧 Enter recipient")
        return

    if data == "em_bulk_send":
        USER_STATE[user_id] = {"section": "email", "flow": "bulk", "step": "subject"}
        await event.edit("✏️ موضوع را وارد کنید" if lang == "fa" else "✏️ Enter subject")
        return

    if data == "em_add_recip":
        USER_STATE[user_id] = {"section": "email", "step": "add_recipient"}
        await event.edit("📧 ایمیل گیرنده را ارسال کنید" if lang == "fa" else "📧 Send recipient email")
        return

    if data == "em_clear_recip":
        admin_data["recipients"] = []
        save_data(data_db)
        await event.edit("🗑 پاک شد" if lang == "fa" else "🗑 Cleared")
        return

    if data == "em_recips":
        recips = admin_data.get("recipients", [])
        text = "\n".join(recips) if recips else ("خالی" if lang == "fa" else "Empty")
        await event.edit(text, buttons=[[Button.inline("🔙 بازگشت" if lang == "fa" else "BACK", "em_back", style="primary")]])
        return

    if data == "em_stats":
        if sync_send_counters(data_db):
            save_data(data_db)
        today = data_db.get("send_today", 0)
        week = data_db.get("send_week", 0)
        await event.edit(f"📊 ارسال امروز: {today}\n📊 ارسال این هفته: {week}" if lang == "fa" else
                        f"📊 Today: {today}\n📊 This Week: {week}")
        return

    if data == "em_agency":
        await event.answer("بخش نمایندگی غیرفعال است" if lang == "fa" else "Agency disabled", alert=True)
        return

    if data in ["em_broadcast", "em_msg_user", "em_block", "em_unblock", "em_force_channel", "em_fc_add", "em_fc_remove", "em_fc_list"]:
        if not is_owner(user_id):
            await event.answer("⛔ دسترسی غیرمجاز" if lang == "fa" else "⛔ Unauthorized", alert=True)
            return

    if data == "em_broadcast":
        USER_STATE[user_id] = {"section": "email", "step": "waiting_broadcast"}
        await event.edit("📨 متن همگانی را ارسال کنید" if lang == "fa" else "📨 Send broadcast message")
        return

    if data == "em_msg_user":
        USER_STATE[user_id] = {"section": "email", "step": "waiting_msg_user_id"}
        await event.edit("🆔 آیدی کاربر را ارسال کنید" if lang == "fa" else "🆔 Send user ID")
        return

    if data == "em_block":
        USER_STATE[user_id] = {"section": "email", "step": "waiting_block_id"}
        await event.edit("🚫 آیدی برای بلاک" if lang == "fa" else "🚫 Send ID to block")
        return

    if data == "em_unblock":
        USER_STATE[user_id] = {"section": "email", "step": "waiting_unblock_id"}
        await event.edit("✅ آیدی برای آنبلاک" if lang == "fa" else "✅ Send ID to unblock")
        return

    if data == "em_force_channel":
        await event.edit("📢 مدیریت کانال اجباری" if lang == "fa" else "📢 Manage Force Channel",
                        buttons=force_channel_keyboard(user_id))
        return

    if data == "em_fc_add":
        USER_STATE[user_id] = {"section": "email", "step": "waiting_fc_add"}
        await event.edit("📢 لینک یا یوزرنیم کانال را ارسال کنید" if lang == "fa" else "📢 Send channel username/link")
        return

    if data == "em_fc_remove":
        USER_STATE[user_id] = {"section": "email", "step": "waiting_fc_remove"}
        await event.edit("🗑 یوزرنیم کانال برای حذف" if lang == "fa" else "🗑 Send username to remove")
        return

    if data == "em_fc_list":
        channels = data_db.get("force_channels", [])
        text = "\n".join(channels) if channels else ("خالی" if lang == "fa" else "Empty")
        await event.edit(text)
        return

    if data == "em_back":
        await event.edit("📧 ایمیل ریپورتر" if lang == "fa" else "📧 Email Reporter",
                        buttons=email_menu_keyboard(user_id))
        return

    await event.answer("Unknown email callback")

async def telegram_callback(event, data, user_id, lang):
    if not can_telegram_reporter(user_id):
        await event.answer("⛔ دسترسی غیرمجاز" if lang == "fa" else "⛔ Unauthorized access", alert=True)
        return

    if await handle_report_callbacks(event, data, user_id, lang, USER_STATE):
        return

    if data == "tg_proxies_list":
        proxies = load_proxies()
        if not proxies:
            msg = ("🌐 **وضعیت پروکسی‌ها: غیرفعال (بدون پروکسی)**\n\n"
                   "برای استفاده از آی‌پی‌های مختلف، فایلی به نام `proxies.txt` در کنار سورس ربات بسازید و پروکسی‌های خود را در آن قرار دهید.\n\n"
                   "**فرمت‌های پشتیبانی شده:**\n"
                   "• `socks5://user:pass@ip:port`\n"
                   "• `http://user:pass@ip:port`\n"
                   "• `ip:port:user:pass`\n"
                   "• `ip:port`") if lang == "fa" else (
                   "🌐 **Proxy Status: Inactive (No Proxies)**\n\nCreate a file named `proxies.txt` alongside the bot script to use multiple IPs.")
        else:
            msg = (f"🌐 **تعداد {len(proxies)} پروکسی فعال آماده استفاده است.**\n\n"
                   f"تمام اکانت‌های شما هنگام ارسال ریپورت به صورت چرخشی از آی‌پی‌های این پروکسی‌ها استفاده خواهند کرد تا از فریز اکانت جلوگیری شود.") if lang == "fa" else f"🌐 **{len(proxies)} proxies active.**"
        
        await event.edit(msg, buttons=[[Button.inline("🔙 بازگشت" if lang=="fa" else "BACK", "tg_back", style="primary")]])
        return

    if data in ["tg_report", "tg_report_post", "tg_report_profile", "tg_report_bot", "tg_report_account", "tg_manual_report"]:
        sessions = get_user_sessions(user_id)
        if not sessions:
            await event.answer("❌ هیچ اکانتی در دسترس نیست" if lang == "fa" else "❌ No accounts available", alert=True)
            return
        type_map = {
            "tg_report": "report",
            "tg_report_post": "report_post",
            "tg_report_profile": "report_profile",
            "tg_report_bot": "report_bot",
            "tg_report_account": "report_account",
            "tg_manual_report": "manual_report"
        }
        USER_STATE[user_id] = {"section": "telegram", "type": type_map[data], "step": "count", "sessions": sessions}
        await event.edit(f"🔢 تعداد اکانت؟ (1-{len(sessions)})" if lang == "fa" else f"🔢 Number of accounts? (1-{len(sessions)})")
        return

    if data == "tg_manage_acc":
        if not is_owner(user_id):
            await event.answer("⛔ دسترسی غیرمجاز" if lang == "fa" else "⛔ Unauthorized", alert=True)
            return
        await event.edit("⚙️ مدیریت اکانت‌ها" if lang == "fa" else "⚙️ Manage Accounts",
                        buttons=manage_accounts_keyboard(user_id))
        return

    if data in ["tg_list_shared", "tg_list_all"]:
        if data == "tg_list_all" and not is_owner(user_id):
            await event.answer("⛔ دسترسی غیرمجاز" if lang == "fa" else "⛔ Unauthorized", alert=True)
            return
        sessions = get_user_sessions(user_id)
        if not sessions:
            await event.answer("❌ اکانتی وجود ندارد" if lang == "fa" else "❌ No accounts", alert=True)
            return
        kb = []
        for admin_id, filename in sessions[:15]:
            phone = filename.replace('.session', '')
            btn_text = f"📱 +{phone} (Admin {admin_id})" if data == "tg_list_all" else f"📱 +{phone}"
            kb.append([
                Button.inline(btn_text, "noop"),
                Button.inline("🗑", f"tg_delacc_{admin_id}_{phone}", style="danger")
            ])
        kb.append([Button.inline("🔙 بازگشت" if lang=="fa" else "BACK", "tg_back", style="primary")])
        await event.edit("📋 لیست اکانت‌ها" if lang=="fa" else "📋 Accounts", buttons=kb)
        return

    if data == "tg_add_acc":
        await close_pending_client(user_id)
        if is_owner(user_id):
            USER_STATE[user_id] = {"section": "telegram", "step": "select_admin"}
            await event.edit("🆔 آیدی عددی ادمین مقصد را وارد کنید (یا 0 برای خودتان)" if lang == "fa" else "🆔 Enter target admin ID (or 0 for yourself)")
        else:
            USER_STATE[user_id] = {"section": "telegram", "step": "phone", "target_admin": user_id}
            await event.edit("📱 شماره تلفن با + را وارد کنید" if lang == "fa" else "📱 Enter phone number with +")
        return

    if data == "tg_del_acc":
        if is_owner(user_id):
            USER_STATE[user_id] = {"section": "telegram", "step": "delete_select_admin"}
            await event.edit("🆔 آیدی عددی ادمین برای حذف اکانت را وارد کنید" if lang == "fa" else "🆔 Enter admin ID to delete account from")
        else:
            USER_STATE[user_id] = {"section": "telegram", "step": "delete_phone", "target_admin": user_id}
            await event.edit("📱 شماره تلفن برای حذف را وارد کنید" if lang == "fa" else "📱 Enter phone number to delete")
        return

    if data.startswith("tg_delacc_"):
        parts = data[len("tg_delacc_"):].split("_", 1)
        if len(parts) != 2:
            await event.answer("Error")
            return
        admin_id_str, phone_clean = parts
        if not is_owner(user_id) and admin_id_str != str(user_id):
            await event.answer("⛔ Unauthorized", alert=True)
            return
        admin_dir = get_admin_sessions_dir(int(admin_id_str))
        path = os.path.join(admin_dir, f"{phone_clean}.session")
        if os.path.exists(path):
            os.remove(path)
            clear_user_cache()
            await event.answer("✅ حذف شد" if lang=="fa" else "✅ Deleted", alert=True)
        else:
            await event.answer("❌ یافت نشد" if lang=="fa" else "❌ Not found", alert=True)
        sessions = get_user_sessions(user_id, force_refresh=True)
        kb = []
        for a_id, fn in sessions[:15]:
            ph = fn.replace('.session', '')
            btn_text = f"📱 +{ph}"
            kb.append([
                Button.inline(btn_text, "noop"),
                Button.inline("🗑", f"tg_delacc_{a_id}_{ph}", style="danger")
            ])
        kb.append([Button.inline("🔙 بازگشت" if lang=="fa" else "BACK", "tg_back", style="primary")])
        await event.edit("📋 لیست اکانت‌ها" if lang=="fa" else "📋 Accounts", buttons=kb)
        return

    if data == "tg_back":
        await close_pending_client(user_id)
        await event.edit("🚫 تلگرام ریپورتر" if lang == "fa" else "🚫 Telegram Reporter",
                        buttons=telegram_menu_keyboard(user_id))
        return

    await event.answer("Unknown telegram callback")

# ==================== MESSAGE HANDLERS ====================

async def message_handler(event):
    if event.text.startswith('/'):
        return

    text = event.text.strip()
    user_id = event.sender_id
    state = USER_STATE.get(user_id, {})
    lang = get_user_lang(user_id) or "fa"

    if not state:
        return

    if not (is_owner(user_id) or is_admin(user_id)):
        await close_pending_client(user_id)
        USER_STATE.pop(user_id, None)
        return

    if state.get("action") == "add_admin" and state.get("step") == "waiting_user_id":
        if not text.isdigit():
            await event.reply("❌ لطفاً یک آیدی عددی وارد کنید" if lang == "fa" else "❌ Please enter a numeric ID")
            return
        target_user = int(text)
        state["target_user"] = target_user
        state["step"] = "waiting_duration"
        await event.reply("⏰ مدت ادمین را انتخاب کنید:" if lang == "fa" else "⏰ Select admin duration:",
                         buttons=admin_duration_keyboard(lang))
        return

    section = state.get("section")
    if section == "email":
        await email_message_handler(event, state, text, user_id, lang)
    elif section == "telegram":
        await telegram_message_handler(event, state, text, user_id, lang)

async def email_message_handler(event, state, text, user_id, lang):
    data_db = load_data()
    admin_data = data_db.setdefault("admin_data", {}).setdefault(
        str(user_id), {"smtp": [], "active_senders": [], "recipients": []}
    )
    flow = state.get("flow")
    step = state.get("step")

    if flow == "smtp":
        if step == "waiting_email":
            if "@" not in text or "." not in text:
                await event.reply("❌ ایمیل معتبر نیست" if lang == "fa" else "❌ Invalid email")
                return
            state["email"] = text
            state["step"] = "waiting_password"
            await event.reply("🔑 App Password را وارد کنید" if lang == "fa" else "🔑 Enter App Password")
            return
        if step == "waiting_password":
            email = state["email"]
            password = text.replace(" ", "")
            ok = await test_smtp_connection(email, password)
            if not ok:
                USER_STATE.pop(user_id, None)
                await event.reply("❌ ایمیل یا App Password اشتباه است" if lang == "fa" else "❌ Wrong email or app password")
                return
            admin_data.setdefault("smtp", []).append({"email": email, "password": password})
            save_data(data_db)
            USER_STATE.pop(user_id, None)
            await event.reply("✅ SMTP با موفقیت ذخیره شد" if lang == "fa" else "✅ SMTP saved successfully")
            return

    if flow == "single":
        if step == "to":
            if "@" not in text or "." not in text:
                await event.reply("❌ ایمیل معتبر نیست" if lang == "fa" else "❌ Invalid email")
                return
            state["to"] = text
            state["step"] = "subject"
            await event.reply("📝 موضوع را وارد کنید" if lang == "fa" else "📝 Enter subject")
            return
        if step == "subject":
            state["subject"] = text
            state["step"] = "body"
            await event.reply("📝 متن ایمیل را وارد کنید" if lang == "fa" else "📝 Enter email body")
            return
        if step == "body":
            to = state["to"]
            subject = state["subject"]
            body = text
            smtp_list = admin_data.get("smtp", [])
            if not smtp_list:
                USER_STATE.pop(user_id, None)
                await event.reply("❌ SMTP موجود نیست" if lang == "fa" else "❌ No SMTP available")
                return
            active = admin_data.get("active_senders", [])
            sender = next((s for s in smtp_list if s["email"] in active), smtp_list[0])
            ok, err = await asyncio.to_thread(send_email_sync, sender["email"], sender["password"], to, subject, body)
            if ok:
                bump_send_counters(data_db, 1)
                save_data(data_db)
                await event.reply("✅ ارسال شد" if lang == "fa" else "✅ Sent")
            else:
                logger.error(f"Single send failed: {err}")
                await event.reply("❌ خطا در ارسال" if lang == "fa" else "❌ Send failed")
            USER_STATE.pop(user_id, None)
            return

    if flow == "bulk":
        if step == "subject":
            state["subject"] = text
            state["step"] = "body"
            await event.reply("📝 متن ایمیل را وارد کنید" if lang == "fa" else "📝 Enter email body")
            return
        if step == "body":
            subject = state["subject"]
            body = text
            recips = admin_data.get("recipients", [])
            smtp_list = admin_data.get("smtp", [])
            if not smtp_list:
                USER_STATE.pop(user_id, None)
                await event.reply("❌ SMTP ندارید" if lang == "fa" else "❌ No SMTP")
                return
            if not recips:
                USER_STATE.pop(user_id, None)
                await event.reply("❌ گیرنده‌ای نیست" if lang == "fa" else "❌ No recipients")
                return
            active = admin_data.get("active_senders", [])
            sender = next((s for s in smtp_list if s["email"] in active), smtp_list[0])
            success = 0
            failed = 0
            for r in recips:
                ok, err = await asyncio.to_thread(send_email_sync, sender["email"], sender["password"], r, subject, body)
                if ok:
                    success += 1
                else:
                    failed += 1
                    logger.error(f"Bulk send to {r} failed: {err}")
                await asyncio.sleep(1)
            if success:
                bump_send_counters(data_db, success)
                save_data(data_db)
            await event.reply(
                f"✅ تمام شد\n📨 کل: {len(recips)}\n✅ موفق: {success}\n❌ ناموفق: {failed}"
                if lang == "fa" else
                f"✅ Done\n📨 Total: {len(recips)}\n✅ Success: {success}\n❌ Failed: {failed}"
            )
            USER_STATE.pop(user_id, None)
            return

    if step == "add_recipient":
        emails = [x.strip() for x in text.splitlines() if x.strip()]
        added = 0
        dup = 0
        for email in emails:
            if email in admin_data["recipients"]:
                dup += 1
                continue
            admin_data["recipients"].append(email)
            added += 1
        save_data(data_db)
        await event.reply(f"✅ {added} گیرنده اضافه شد\n⚠️ تکراری: {dup}" if lang == "fa" else
                         f"✅ {added} added\n⚠️ duplicate: {dup}")
        USER_STATE.pop(user_id, None)
        return

    if step == "waiting_broadcast":
        if not is_owner(user_id):
            USER_STATE.pop(user_id, None)
            return
        if not text.strip():
            await event.reply("❌ متن خالی است" if lang == "fa" else "❌ Empty text")
            return
        users = data_db.get("users", [])
        sent = 0
        blocked = 0
        failed = 0
        total = len(users)
        if total == 0:
            await event.reply("❌ کاربری وجود ندارد" if lang == "fa" else "❌ No users")
            USER_STATE.pop(user_id, None)
            return
        msg = await event.reply("🚀 ارسال همگانی آغاز شد..." if lang == "fa" else "🚀 Broadcast started...")
        for i, uid in enumerate(users, 1):
            try:
                await event.client.send_message(int(uid), text)
                sent += 1
            except errors.UserIsBlockedError:
                blocked += 1
            except Exception:
                failed += 1
            if i % 10 == 0 or i == total:
                percent = int(i * 100 / total)
                bar = "🟩" * (percent // 10) + "⬜" * (10 - percent // 10)
                try:
                    await msg.edit(
                        f"🚀 ارسال همگانی\n{bar} {percent}%\n👥 کل: {total}\n📤 موفق: {sent}\n🚫 بلاک: {blocked}\n❌ خطا: {failed}"
                        if lang == "fa" else
                        f"🚀 Broadcast\n{bar} {percent}%\n👥 Total: {total}\n📤 Sent: {sent}\n🚫 Blocked: {blocked}\n❌ Failed: {failed}"
                    )
                except Exception:
                    pass
            await asyncio.sleep(0.05)
        await msg.edit(
            f"✅ ارسال همگانی پایان یافت\n🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 100%\n👥 کل: {total}\n📤 موفق: {sent}\n🚫 بلاک: {blocked}\n❌ خطا: {failed}"
            if lang == "fa" else
            f"✅ Broadcast completed\n🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 100%\n👥 Total: {total}\n📤 Sent: {sent}\n🚫 Blocked: {blocked}\n❌ Failed: {failed}"
        )
        USER_STATE.pop(user_id, None)
        return

    if step == "waiting_msg_user_id":
        if not is_owner(user_id):
            USER_STATE.pop(user_id, None)
            return
        if not text.isdigit():
            await event.reply("❌ فقط آیدی عددی" if lang == "fa" else "❌ Numeric ID only")
            return
        state["target_user"] = int(text)
        state["step"] = "waiting_msg_user_text"
        await event.reply("✉️ متن پیام را ارسال کنید" if lang == "fa" else "✉️ Send message text")
        return

    if step == "waiting_msg_user_text":
        if not is_owner(user_id):
            USER_STATE.pop(user_id, None)
            return
        target = state.get("target_user")
        if not target:
            USER_STATE.pop(user_id, None)
            return
        try:
            await event.client.send_message(target, text)
            await event.reply("✅ پیام ارسال شد" if lang == "fa" else "✅ Message sent")
        except Exception:
            await event.reply("❌ ارسال ناموفق" if lang == "fa" else "❌ Failed")
        USER_STATE.pop(user_id, None)
        return

    if step == "waiting_block_id":
        if not is_owner(user_id):
            USER_STATE.pop(user_id, None)
            return
        if not text.isdigit():
            await event.reply("❌ فقط آیدی عددی" if lang == "fa" else "❌ Numeric ID only")
            return
        data_db.setdefault("blocked", [])
        target = int(text)
        if target not in data_db["blocked"]:
            data_db["blocked"].append(target)
            save_data(data_db)
        await event.reply("🚫 کاربر بلاک شد" if lang == "fa" else "🚫 User blocked")
        USER_STATE.pop(user_id, None)
        return

    if step == "waiting_unblock_id":
        if not is_owner(user_id):
            USER_STATE.pop(user_id, None)
            return
        if not text.isdigit():
            await event.reply("❌ فقط آیدی عددی" if lang == "fa" else "❌ Numeric ID only")
            return
        data_db.setdefault("blocked", [])
        target = int(text)
        if target in data_db["blocked"]:
            data_db["blocked"].remove(target)
            save_data(data_db)
        await event.reply("✅ کاربر آنبلاک شد" if lang == "fa" else "✅ User unblocked")
        USER_STATE.pop(user_id, None)
        return

    if step == "waiting_fc_add":
        if not is_owner(user_id):
            USER_STATE.pop(user_id, None)
            return
        if not text.strip():
            await event.reply("❌ ورودی نامعتبر" if lang == "fa" else "❌ Invalid input")
            return
        channel = text.strip()
        if not channel.startswith("@"):
            channel = "@" + channel
        data_db.setdefault("force_channels", [])
        if channel not in data_db["force_channels"]:
            data_db["force_channels"].append(channel)
            save_data(data_db)
        await event.reply("✅ کانال اضافه شد" if lang == "fa" else "✅ Channel added")
        USER_STATE.pop(user_id, None)
        return

    if step == "waiting_fc_remove":
        if not is_owner(user_id):
            USER_STATE.pop(user_id, None)
            return
        if not text.strip():
            await event.reply("❌ ورودی نامعتبر" if lang == "fa" else "❌ Invalid input")
            return
        channel = text.strip()
        if not channel.startswith("@"):
            channel = "@" + channel
        data_db.setdefault("force_channels", [])
        if channel in data_db["force_channels"]:
            data_db["force_channels"].remove(channel)
            save_data(data_db)
        await event.reply("✅ کانال حذف شد" if lang == "fa" else "✅ Channel removed")
        USER_STATE.pop(user_id, None)
        return

async def telegram_message_handler(event, state, text, user_id, lang):
    step = state.get("step")

    if step == "select_admin":
        if not text.strip().isdigit() and text != "0":
            await event.reply("❌ آیدی نامعتبر" if lang == "fa" else "❌ Invalid ID")
            return
        target_admin = user_id if text == "0" else int(text)
        if target_admin != user_id and not is_admin(target_admin) and not is_owner(target_admin):
            await event.reply("❌ ادمین یافت نشد" if lang == "fa" else "❌ Admin not found")
            return
        state["target_admin"] = target_admin
        state["step"] = "phone"
        await event.reply("📱 شماره تلفن با + را وارد کنید" if lang == "fa" else "📱 Enter phone number with +")
        return

    if step == "delete_select_admin":
        if not text.strip().isdigit():
            await event.reply("❌ آیدی نامعتبر" if lang == "fa" else "❌ Invalid ID")
            return
        target_admin = int(text)
        if target_admin != user_id and not is_admin(target_admin) and not is_owner(target_admin):
            await event.reply("❌ ادمین یافت نشد" if lang == "fa" else "❌ Admin not found")
            return
        state["target_admin"] = target_admin
        state["step"] = "delete_phone"
        await event.reply("📱 شماره تلفن برای حذف را وارد کنید" if lang == "fa" else "📱 Enter phone number to delete")
        return

    if step == "phone":
        if not await validate_phone_number(text):
            await event.reply("❌ شماره نامعتبر است" if lang == "fa" else "❌ Invalid phone number")
            return
        state["phone"] = text
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            await client.send_code_request(text)
            state["client"] = client
            state["step"] = "code"
            await event.reply("✅ کد ارسال شد. کد را وارد کنید" if lang == "fa" else "✅ Code sent. Enter code")
        except Exception as e:
            await event.reply(f"❌ خطا: {str(e)[:100]}")
            await client.disconnect()
            USER_STATE.pop(user_id, None)
        return

    if step == "code":
        if len(text) < 4:
            await event.reply("❌ کد نامعتبر" if lang == "fa" else "❌ Invalid code")
            return
        client = state.get("client")
        phone = state.get("phone")
        target_admin = state.get("target_admin", user_id)
        if not client or not phone:
            await close_pending_client(user_id)
            USER_STATE.pop(user_id, None)
            return
        try:
            await client.sign_in(phone, text)
            session_str = client.session.save()
            phone_clean = phone.replace('+', '').replace(' ', '')
            filename = f"{phone_clean}.session"
            admin_dir = get_admin_sessions_dir(target_admin)
            path = os.path.join(admin_dir, filename)
            with open(path, "w", encoding='utf-8') as f:
                f.write(session_str)
            clear_user_cache()
            me = await client.get_me()
            profile = f"✅ اکانت اضافه شد\n👤 {me.first_name or ''} {me.last_name or ''}\n📱 {phone}\n🆔 {me.id}\n@{me.username or 'None'}"
            await event.reply(profile)
            await client.disconnect()
            USER_STATE.pop(user_id, None)
        except errors.SessionPasswordNeededError:
            state["step"] = "password"
            await event.reply("🔐 رمز دو مرحله‌ای را وارد کنید" if lang == "fa" else "🔐 Enter 2FA password")
        except errors.PhoneCodeInvalidError:
            await event.reply("❌ کد اشتباه است" if lang == "fa" else "❌ Invalid code")
        except errors.PhoneCodeExpiredError:
            await event.reply("❌ کد منقضی شده" if lang == "fa" else "❌ Code expired")
            await client.disconnect()
            USER_STATE.pop(user_id, None)
        except Exception as e:
            await event.reply(f"❌ خطا: {str(e)[:100]}")
            await client.disconnect()
            USER_STATE.pop(user_id, None)
        return

    if step == "password":
        if not text:
            await event.reply("❌ رمز نامعتبر" if lang == "fa" else "❌ Invalid password")
            return
        client = state.get("client")
        phone = state.get("phone")
        target_admin = state.get("target_admin", user_id)
        if not client:
            USER_STATE.pop(user_id, None)
            return
        try:
            await client.sign_in(password=text)
            session_str = client.session.save()
            phone_clean = phone.replace('+', '').replace(' ', '')
            filename = f"{phone_clean}.session"
            admin_dir = get_admin_sessions_dir(target_admin)
            path = os.path.join(admin_dir, filename)
            with open(path, "w", encoding='utf-8') as f:
                f.write(session_str)
            clear_user_cache()
            me = await client.get_me()
            profile = f"✅ اکانت اضافه شد\n👤 {me.first_name or ''} {me.last_name or ''}\n📱 {phone}\n🆔 {me.id}\n@{me.username or 'None'}"
            await event.reply(profile)
            await client.disconnect()
            USER_STATE.pop(user_id, None)
        except errors.PasswordHashInvalidError:
            await event.reply("❌ رمز اشتباه است" if lang == "fa" else "❌ Invalid password")
        except Exception as e:
            await event.reply(f"❌ خطا: {str(e)[:100]}")
            await client.disconnect()
            USER_STATE.pop(user_id, None)
        return

    if step == "delete_phone":
        if not text.startswith('+'):
            await event.reply("❌ شماره باید با + شروع شود" if lang == "fa" else "❌ Number must start with +")
            return
        phone_clean = text.replace('+', '').replace(' ', '')
        target_admin = state.get("target_admin", user_id)
        admin_dir = get_admin_sessions_dir(target_admin)
        deleted = False
        for f in os.listdir(admin_dir):
            if f == f"{phone_clean}.session":
                os.remove(os.path.join(admin_dir, f))
                deleted = True
        if deleted:
            clear_user_cache()
            await event.reply(f"✅ اکانت {text} حذف شد" if lang == "fa" else f"✅ Account {text} deleted")
        else:
            await event.reply("❌ اکانتی یافت نشد" if lang == "fa" else "❌ No account found")
        USER_STATE.pop(user_id, None)
        return

    if step == "count":
        try:
            count = int(text)
            sessions = state["sessions"]
            if count < 1 or count > len(sessions):
                await event.reply(f"❌ عدد بین 1 تا {len(sessions)}" if lang == "fa" else f"❌ Between 1 and {len(sessions)}")
                return
            state["count"] = count
            state["selected_sessions"] = sessions[:count]
            op_type = state.get("type")
            if op_type == "report_post":
                state["step"] = "post_links"
                await event.reply("🔗 لینک‌های پست (حداکثر ۱۰۰ عدد) را ارسال کنید (هر خط یک لینک)\nیا یک عدد برای دریافت پست‌های آخر کانال وارد کنید." if lang == "fa" else "🔗 Send post links (max 100, one per line) or enter a number to get last N posts of a channel.")
            else:
                state["step"] = "target"
                await event.reply("🔗 لینک/یوزرنیم هدف را وارد کنید" if lang == "fa" else "🔗 Enter target link/username")
        except ValueError:
            await event.reply("❌ عدد وارد کنید" if lang == "fa" else "❌ Enter a number")
        return

    if step == "post_links":
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            await event.reply("❌ ورودی خالی است" if lang == "fa" else "❌ Empty input")
            return

        all_digits = all(ln.isdigit() for ln in lines)
        if all_digits and len(lines) == 1:
            try:
                num = int(lines[0])
                if num < 1:
                    await event.reply("❌ عدد باید بزرگتر از 0 باشد" if lang == "fa" else "❌ Number must be > 0")
                    return
                if num > 100:
                    num = 100
                    await event.reply("⚠️ تعداد حداکثر ۱۰۰ در نظر گرفته شد" if lang == "fa" else "⚠️ Max 100 posts allowed")
                state["post_count"] = num
                state["step"] = "channel_for_last_posts"
                await event.reply("🔗 حالا لینک کانال را وارد کنید (مثلاً t.me/username)" if lang == "fa" else "🔗 Now enter the channel link (e.g., t.me/username)")
                return
            except ValueError:
                pass

        post_links = []
        for link in lines:
            if not await validate_post_link(link):
                await event.reply(f"❌ لینک نامعتبر: {link}" if lang == "fa" else f"❌ Invalid link: {link}")
                return
            post_links.append(link)
            if len(post_links) >= 100:
                break
        state["post_links"] = post_links
        state["step"] = "select_reason"
        await event.reply("📝 دلیل ریپورت را انتخاب کنید:", buttons=main_reason_keyboard(lang))
        return

    if step == "channel_for_last_posts":
        channel_link = text.strip()
        if not channel_link:
            await event.reply("❌ لینک کانال نامعتبر" if lang == "fa" else "❌ Invalid channel link")
            return
        if not (channel_link.startswith("https://t.me/") or channel_link.startswith("t.me/") or channel_link.startswith("@")):
            channel_link = "@" + channel_link.lstrip("@")
        else:
            channel_link = channel_link.replace("https://t.me/", "").replace("t.me/", "")
        state["channel_link"] = channel_link
        state["step"] = "select_reason"
        await event.reply("📝 دلیل ریپورت را انتخاب کنید:", buttons=main_reason_keyboard(lang))
        return

    if step == "target":
        target = text.strip()
        if not target:
            await event.reply("❌ خالی نباشد" if lang == "fa" else "❌ Not empty")
            return
        state["target"] = target
        state["step"] = "select_reason"
        await event.reply("📝 دلیل ریپورت را انتخاب کنید:", buttons=main_reason_keyboard(lang))
        return

    if step == "count_per_account":
        try:
            cnt = int(text)
            if cnt < 1 or cnt > 50:
                await event.reply("❌ عدد بین 1 تا 50" if lang == "fa" else "❌ Between 1 and 50")
                return
            state["count_per_account"] = cnt
            state["step"] = "custom_reason"
            await event.reply("📝 متن دلخواه (یا /skip)" if lang == "fa" else "📝 Custom message (or /skip)")
        except ValueError:
            await event.reply("❌ عدد وارد کنید" if lang == "fa" else "❌ Enter a number")
        return

    if step == "custom_reason":
        state["custom_reason"] = text
        asyncio.create_task(execute_report_operation(event, copy.deepcopy(state), user_id, lang))
        USER_STATE.pop(user_id, None)
        return

# ==================== MAIN RUNNER ====================

async def main():
    session_file = "bot_session.session"
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
            logger.info("Removed old session file")
        except:
            pass

    bot = TelegramClient("bot_session", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("Bot started successfully.")

    bot.add_event_handler(start_handler, events.NewMessage(pattern=r'/start(?: (.+))?'))
    bot.add_event_handler(callback_handler, events.CallbackQuery())
    bot.add_event_handler(message_handler, events.NewMessage(func=lambda e: e.is_private and not e.text.startswith('/')))

    logger.info("SHIKH REPORTER is running...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())