import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
import pandas as pd
import threading
import telebot
import io
import pytz

# ==============================================================================
# 1. إعدادات الصفحة الأساسية ونظام المظهر الفاخر (Configuration & Theme)
# ==============================================================================
st.set_page_config(
    page_title="InfoDoc - Client Portal",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# تحسين الـ CSS المخصص ليواكب المظهر الزجاجي والاحترافي للتطبيق الرئيسي
st.markdown("""
    <style>
    /* تحسين الخلفية العامة للبورطاي */
    .stApp {
        background: radial-gradient(circle at top left, #1e3a8a, #0f172a);
        background-attachment: fixed;
    }
    
    /* ضبط الحاويات والبطاقات الافتراضية */
    [data-testid="stVerticalBlock"] { padding-top: 1rem !important; }
    
    /* تنسيق الأزرار بشكل مستجيب وجذاب */
    div.stButton > button:first-child {
        width: 100% !important;
        border-radius: 12px !important;
        height: 3em !important;
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%) !important;
        color: white !important;
        font-weight: 700 !important;
        border: none !important;
        box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3) !important;
        transition: all 0.3s ease !important;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5) !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. الاتصال الآمن بقاعدة البيانات ونظام تتبع الزوار (Firebase & Visitor Tracking)
# ==============================================================================
@st.cache_resource
def init_db():
    """ربط التطبيق بـ Firebase مع معالجة حماية الانهيار (Fail-safe)."""
    if not firebase_admin._apps:
        try:
            if "firebase" in st.secrets and "DB_URL" in st.secrets:
                cred_dict = dict(st.secrets["firebase"])
                if "\\n" in cred_dict.get("private_key", ""):
                    cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
                return True
            else:
                st.warning("⚠️ Mode local/limité activé (Secrets non配置).")
                return False
        except Exception as e:
            st.error(f"❌ Erreur connexion Firebase: {e}")
            return False
    return True

db_status = init_db()

# ==============================================================================
# 3. الدوال البرمجية المساعدة وإدارة الحالات والضمان (Helper Functions)
# ==============================================================================
def normalize_phone(phone: str) -> str:
    """تنسيق وتوحيد رقم الهاتف الجزائري ليطابق المخزن في السيرفر الرئيسي."""
    if not phone: 
        return ""
    p = re.sub(r"\D", "", str(phone))
    
    if p.startswith("213"):
        p = "0" + p[3:]
    elif p.startswith("00213"):
        p = "0" + p[5:]
    
    if len(p) == 9 and p[0] in ["2", "3", "4", "5", "6", "7", "9"]:
        p = "0" + p
        
    return p

def get_warranty_stats(date_sortie_str):
    """حساب وضمان الأجهزة المستلمة بدقة رياضية متناهية ودعم الأيام السالبة للأرشفة."""
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None", "nan"]:
        return None
    
    date_formats = [
        "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", 
        "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d", "%d-%m-%Y", 
        "%d/%m/%Y", "%d/%m/%Y %H:%M"
    ]
    
    tz = pytz.timezone('Africa/Algiers')
    now = datetime.now(tz).replace(tzinfo=None)
    date_s = None
    
    for fmt in date_formats:
        try:
            date_s = datetime.strptime(str(date_sortie_str).strip(), fmt)
            break 
        except ValueError:
            continue
    
    if date_s:
        diff_days = (now - date_s).days
        remaining_days = 30 - diff_days
        percent = max(0, min((remaining_days / 30) * 100, 100))
        
        return {
            "percent": int(percent), 
            "is_expired": diff_days > 30, 
            "days_left": remaining_days, 
            "actual_date": date_s.strftime("%d/%m/%Y")
        }
    return None

def get_status_priority(status):
    """تحديد أولوية الفرز لعرض الأجهزة الجاهزة للزبون أولاً."""
    s = str(status).strip()
    status_lower = s.lower()
    
    if "prêt" in status_lower or "pret" in status_lower: 
        return 1
    elif "réparable" in status_lower or "reparable" in status_lower: 
        return 2
    elif "en cours" in status_lower: 
        return 3
    elif "en attente" in status_lower: 
        return 4
    elif "annulé" in status_lower or "annule" in status_lower: 
        return 5
    elif "non réparable" in status_lower or "non reparable" in status_lower: 
        return 6
    elif "livré" in status_lower or "livre" in status_lower or "payé" in status_lower or "paye" in status_lower:
        return 7
    else: 
        return 99

# ==============================================================================
# 4. تشغيل بوت التلغرام الاحترافي (المطور لـ InfoDoc)
# ==============================================================================
@st.cache_resource
def start_telegram_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: 
        return "Missing Token"

    try:
        bot = telebot.TeleBot(token, parse_mode="Markdown")

        @bot.message_handler(commands=['start'])
        def handle_start(m):
            try:
                command_parts = m.text.split()
                if len(command_parts) > 1:
                    client_phone = normalize_phone(command_parts[1])
                    ref = db.reference("atelier")
                    data = ref.get()
                    
                    if data:
                        linked_devices = []
                        for k, v in data.items():
                            db_phone = normalize_phone(v.get("Telephone", ""))
                            if db_phone.endswith(client_phone[-9:]):
                                ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                                device_name = v.get("Appareil", "جهاز غير معروف")
                                ticket_id = v.get("ID", "0000")
                                linked_devices.append(f"• *{device_name}* (تذكرة #{ticket_id})")
                        
                        if linked_devices:
                            devices_list_str = "\n".join(linked_devices)
                            success_msg = (
                                "🔔 *تفعيل الإشعارات الفورية - InfoDoc*\n\n"
                                "✅ *تم ربط حسابك بنجاح!*\n"
                                "ستصلك إشعارات تلقائية وفورية هنا على التلغرام بمجرد حدوث أي تغيير في حالة أجهزتك.\n\n"
                                "📦 *الأجهزة المرتبطة حالياً:*\n"
                                f"{devices_list_str}\n\n"
                                "⏱️ _شكراً لثقتكم في خدماتنا._"
                            )
                            bot.reply_to(m, success_msg)
                        else:
                            error_msg = (
                                "❌ *خطأ في عملية الربط*\n\n"
                                "عذراً، لم نجد أي جهاز مسجل برقم الهاتف هذا في قاعدة بيانات الورشة حالياً."
                            )
                            bot.reply_to(m, error_msg)
                    else:
                        bot.reply_to(m, "⚠️ قاعدة البيانات فارغة حالياً أو غير متصلة.")
                else:
                    welcome_msg = (
                        "👋 *مرحباً بك في بوت ورشة InfoDoc الفنية!*\n\n"
                        "هذا البوت مخصص لإرسال إشعارات تلقائية لزبائننا لتتبع حالة صيانة أجهزتهم.\n\n"
                        "ℹ️ *كيفية تفعيل الخدمة:*\n"
                        "1️⃣ اذهب إلى موقعنا الإلكتروني.\n"
                        "2️⃣ ابحث عن أجهزتك باستخدام رقم هاتفك.\n"
                        "3️⃣ اضغط على زر *🚀 تفعيل إشعارات التلغرام* العائم."
                    )
                    bot.reply_to(m, welcome_msg)
            except Exception as e:
                print(f"Error in Telegram logic: {e}")

        thread = threading.Thread(target=bot.infinity_polling, daemon=True)
        thread.start()
        return "Bot Started Successfully"
    except Exception as e:
        return f"Error: {e}"

# تشغيل البوت الذكي
if "bot_initialized" not in st.session_state:
    if "TELEGRAM_TOKEN" in st.secrets:
        status = start_telegram_bot()
        if "Successfully" in status:
            st.session_state["bot_initialized"] = True

# ==============================================================================
# 5. نظام تتبع الزوار الذكي الفعلي (Visitor Tracking Execution)
# ==============================================================================
if db_status and 'visitor_tracked' not in st.session_state:
    try:
        tz = pytz.timezone('Africa/Algiers')
        now_dt = datetime.now(tz)
        today_str = now_dt.strftime("%Y-%m-%d")
        
        headers = st.context.headers
        ip = headers.get("X-Forwarded-For", headers.get("Remote-Addr", "127.0.0.1")).split(",")[0].strip()
        clean_ip = ip.replace(".", "_")
        
        ref_ip = db.reference(f"stats/daily_ips/{today_str}/{clean_ip}")
        if ref_ip.get() is None:
            ref_ip.set(True)
            visitor_counter_ref = db.reference(f"stats/daily_visitors/{today_str}")
            visitor_counter_ref.transaction(lambda current_value: (current_value or 0) + 1)
            
        st.session_state['visitor_tracked'] = True
    except:
        pass

# ==============================================================================
# 6. واجهة المستخدم الرسومية (UI Header & Stats)
# ==============================================================================
st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
""", unsafe_allow_html=True)

algeria_tz = pytz.timezone('Africa/Algiers')
now = datetime.now(algeria_tz)
greeting = "عزيزي الزبون، صباح الخير ☀️" if 5 <= now.hour < 12 else "عزيزي الزبون، مساء الخير ✨"

try:
    shop_status = db.reference("shop_settings/is_open").get()
    if shop_status is None: shop_status = False
except:
    shop_status = False

st.markdown("""
    <style>
    @keyframes pulse-green {
        0% { box-shadow: 0 0 0 0 rgba(63, 185, 80, 0.7); }
        70% { box-shadow: 0 0 0 15px rgba(63, 185, 80, 0); }
        100% { box-shadow: 0 0 0 0 rgba(63, 185, 80, 0); }
    }
    @keyframes pulse-red {
        0% { box-shadow: 0 0 0 0 rgba(248, 81, 73, 0.7); }
        70% { box-shadow: 0 0 0 15px rgba(248, 81, 73, 0); }
        100% { box-shadow: 0 0 0 0 rgba(248, 81, 73, 0); }
    }
    .badge-open { 
        color: #2ecc71 !important; 
        border: 2px solid #2ecc71 !important; 
        animation: pulse-green 2s infinite;
        background: rgba(46, 204, 113, 0.1) !important;
    }
    .badge-closed { 
        color: #e74c3c !important; 
        border: 2px solid #e74c3c !important; 
        animation: pulse-red 2s infinite;
        background: rgba(231, 76, 60, 0.1) !important;
    }
    .hero-container {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.6) 0%, rgba(30, 41, 59, 0.8) 100%) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 24px !important;
        padding: 35px !important;
        margin-bottom: 30px !important;
        text-align: center !important;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4) !important;
    }
    .hero-brand {
        font-family: 'Orbitron', sans-serif !important;
        color: #3b82f6;
        font-size: 3.8rem;
        font-weight: 900;
        letter-spacing: 4px;
        text-shadow: 0 0 30px rgba(59, 130, 246, 0.6);
        margin-bottom: 5px;
    }
    .hero-subtitle {
        color: #94a3b8;
        font-family: 'Cairo', sans-serif !important;
        font-size: 1.15rem;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    
    /* نظام الشبكة التكنولوجية للأزرار */
    .contact-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 15px;
        margin-bottom: 30px;
        width: 100%;
    }
    .portal-contact-btn {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        background: rgba(30, 41, 59, 0.4) !important;
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 16px !important;
        padding: 18px 10px !important;
        text-decoration: none !important;
        color: #94a3b8 !important;
        transition: cubic-bezier(0.4, 0, 0.2, 1) 0.3s all;
        height: 105px;
        text-align: center;
    }
    .portal-contact-btn:hover {
        transform: translateY(-5px);
        color: #ffffff !important;
        border-color: rgba(255, 255, 255, 0.2) !important;
    }
    .btn-phone:hover { background: rgba(46, 204, 113, 0.15) !important; box-shadow: 0 8px 25px rgba(46, 204, 113, 0.3); color: #2ecc71 !important; }
    .btn-map:hover { background: rgba(231, 76, 60, 0.15) !important; box-shadow: 0 8px 25px rgba(231, 76, 60, 0.3); color: #e74c3c !important; }
    .btn-facebook:hover { background: rgba(24, 119, 242, 0.15) !important; box-shadow: 0 8px 25px rgba(24, 119, 242, 0.3); color: #1877f2 !important; }
    .btn-tiktok:hover { background: rgba(0, 242, 234, 0.08) !important; box-shadow: 0 8px 25px rgba(254, 44, 85, 0.25); color: #00f2ea !important; }

    .portal-contact-btn i { font-size: 2rem; margin-bottom: 10px; }
    .portal-contact-btn .label { font-family: 'Cairo'; font-size: 0.95rem; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f'''
    <div class="hero-container" dir="rtl">
        <div style="color: #64748b; font-size: 0.95rem; font-family: 'Cairo'; font-weight: 700; margin-bottom: 12px;">
            ✨ {greeting} | 📅 {now.strftime("%d/%m/%Y - %H:%M")}
        </div>
        <div class="hero-brand">INFODOC</div>
        <div class="hero-subtitle" style="margin-bottom: 25px;">
            🛠️ الـمـنـصـة الإلـكـتـرونـيـة لـخـدمـات الـصـيـانـة 
        </div>
        <span class="{"badge-open" if shop_status else "badge-closed"}" 
              style="padding: 12px 30px; border-radius: 14px; font-weight: 900; display: inline-block; font-family: 'Cairo'; font-size: 1.05rem;">
            {'● مـفـتـوح حـالـيـاً - مـرحـبـاً بـكـم في الـورشـة' if shop_status else '● مـغـلـق حـالـيـاً - نـسـتـقـبـلكم في أوقـات الـعـمـل'}
        </span>
    </div>
''', unsafe_allow_html=True)

# عرض أزرار التواصل
st.markdown("""
    <div class="contact-grid" dir="rtl">
        <a href="tel:0798661900" class="portal-contact-btn btn-phone">
            <i class="fa-solid fa-phone-flip"></i>
            <span class="label">إتصل بنا فوراً</span>
        </a>
        <a href="https://maps.app.goo.gl/RBGLbVDiCeqAdxVT8" target="_blank" class="portal-contact-btn btn-map">
            <i class="fa-solid fa-location-dot"></i>
            <span class="label">موقع الورشة</span>
        </a>
        <a href="https://www.facebook.com/share/18dX9h9otd/" target="_blank" class="portal-contact-btn btn-facebook">
            <i class="fa-brands fa-facebook-f"></i>
            <span class="label">صفحة الفيسبوك</span>
        </a>
        <a href="https://tiktok.com/@infodoc02/" target="_blank" class="portal-contact-btn btn-tiktok">
            <i class="fa-brands fa-tiktok"></i>
            <span class="label">حساب تيك توك</span>
        </a>
    </div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
@keyframes gold-glow {
    0%, 100% { box-shadow: 0 4px 10px rgba(234, 179, 8, 0.15); border-color: rgba(234, 179, 8, 0.6); }
    50%       { box-shadow: 0 4px 20px rgba(250, 204, 21, 0.3); border-color: rgba(250, 204, 21, 0.95); }
}
.glow-expander {
    background: #f8fafc !important;
    border: 1px solid #eab308;
    border-radius: 14px;
    padding: 15px;
    margin-bottom: 25px;
    font-family: 'Cairo', sans-serif;
    animation: gold-glow 2.5s ease-in-out infinite;
}
.glow-expander summary {
    color: #1e293b !important;
    font-weight: bold;
    font-size: 1.1rem;
    cursor: pointer;
    outline: none;
    list-style: none;
    padding: 5px 10px;
    text-align: right;
    direction: rtl;
}
.glow-expander summary::-webkit-details-marker { display: none; }
.rule-card {
    background: #ffffff !important;
    border-right: 4px solid #eab308;
    padding: 14px 18px;
    margin-bottom: 12px;
    border-radius: 6px;
    color: #334155 !important;
    line-height: 1.6;
    text-align: right;
    direction: rtl;
    box-shadow: 0 2px 4px rgba(0,0,0,0.02);
}
.rule-card:last-child { margin-bottom: 5px; }
.hl { color: #b45309 !important; font-weight: bold; }
</style>
<div dir="rtl">
<details class="glow-expander">
<summary>⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة</summary>
<div style="margin-top: 15px;">
<div class="rule-card">1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<span class="hl">رفض الزبون ذلك</span>، يتم دفع <span class="hl">1000 دج</span> ثمن الفحص والقياسات.</div>
<div class="rule-card">2️⃣ أسعار العمل على <span class="hl">البطاقة الأم (Carte Mère)</span> والمكونات الإلكترونية المجهرية تبدأ من <span class="hl">3000 دج</span>.</div>
<div class="rule-card">3️⃣ أسعار <span class="hl">تفليش البيوس وبرمجة السوبر آي أو (Flash BIOS / SIO)</span> تبدأ من <span class="hl">1500 دج</span>.</div>
<div class="rule-card">4️⃣ <span class="hl">سياسة الموافقة التلقائية:</span> نقوم بالإصلاح مباشرة وبدون الاتصال بك إذا كانت التكلفة الإجمالية بين <span class="hl">3000 دج و 4000 دج</span>.</div>
<div class="rule-card">5️⃣ <span class="hl">شروط الضمان المتقدم:</span> الضمان الممنوح (<span class="hl">30 يوماً</span>) صالح حصراً على العيب الإلكتروني الذي تم إصلاحه.</div>
</div>
</details>
</div>
""", unsafe_allow_html=True)

st.divider()

# ==============================================================================
# 8. نظام البحث والتتبع المتقدم والملتحم هندسياً (Search Engine)
# ==============================================================================
st.markdown("""
    <style>
    /* تنسيقات الإدخال والفورم */
    div[data-testid="stTextInput"] input {
        direction: rtl !important;
        text-align: right !important;
        font-family: 'Cairo', sans-serif !important;
        color: #f1f5f9 !important;
        background-color: rgba(15, 23, 42, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 10px !important;
    }
    
    /* التنسيق المتطور لكرت الجهاز العلوي المتلاحم */
    .device-top-card {
        background: rgba(30, 41, 59, 0.7) !important;
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px 14px 0 0 !important; /* دائرية من فوق فقط */
        padding: 16px !important;
        margin-top: 15px !important;
        margin-bottom: 0px !important;
    }
    .card-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        width: 100%;
    }

       
    /* الزر العائم للتلغرام */
    .floating-tg-button {
        position: fixed;
        bottom: 30px;
        left: 30px;
        background: linear-gradient(135deg, #24A1DE 0%, #1d80b0 100%);
        color: white !important;
        padding: 14px 24px;
        border-radius: 50px;
        box-shadow: 0 8px 25px rgba(36, 161, 222, 0.4);
        font-family: 'Cairo', sans-serif;
        font-weight: 900;
        text-decoration: none !important;
        display: flex;
        align-items: center;
        gap: 8px;
        animation: tg-bounce 2.5s infinite ease-in-out;
    }
    @keyframes tg-bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-8px); }
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<h3 style="text-align: right; font-family: \'Cairo\'; color: #e2e8f0; font-size: 1.25rem; font-weight:700;">🔍 تتبع حالة أجهزتك الآن:</h3>', unsafe_allow_html=True)

with st.form("search_form", clear_on_submit=False):
    user_phone = st.text_input("", placeholder="أدخل رقم هاتفك هنا (مثال: 0798661900)", label_visibility="collapsed")
    submit_search = st.form_submit_button("⚡ ابحث عن أجهزتي في الورشة")

if submit_search and user_phone:
    norm_phone = normalize_phone(user_phone)
    if len(norm_phone) < 9:
        st.error("⚠️ يرجى إدخال رقم هاتف صحيح يتكون من 9 أرقام على الأقل.")
    else:
        with st.spinner("⏳ جاري فحص قاعدة البيانات بسرعة النيون..."):
            db_ref = db.reference("atelier")
            all_data = db_ref.get()
            
            my_devices = []
            if all_data:
                # الفلترة الذكية المرنة بآخر 9 أرقام لتفادي مشاكل الـ 00213 والـ +213 والـ 0
                for k, v in all_data.items():
                    db_phone = normalize_phone(v.get("Telephone", ""))
                    if db_phone.endswith(norm_phone[-9:]):
                        my_devices.append(dict(v, _id=k))
            
            if my_devices:
                # ترتيب الأجهزة لظهور الجاهز Prêt أولاً
                my_devices.sort(key=lambda x: get_status_priority(x.get("Statut", "")))
                
                for dev in my_devices:
                    dev_id = dev.get("ID", "0000")
                    brand = dev.get("Marque", "")
                    model = dev.get("Appareil", "جهاز غير معروف")
                    status = dev.get("Statut", "En attente")
                    
                    status_colors = {"prêt": "#2ecc71", "en cours": "#f1c40f", "en attente": "#e67e22", "annulé": "#e74c3c"}
                    col_status = status_colors.get(status.lower(), "#3498db")
                    
                    # الكرت العلوي
                    st.markdown(f"""
                        <div class="device-top-card" dir="rtl">
                            <div class="card-container">
                                <div style="text-align: right;">
                                    <span style="color: #cbd5e1; font-size: 0.85rem; font-family: 'Cairo';">تذكرة #{dev_id}</span>
                                    <h4 style="margin: 4px 0; color: #ffffff; font-family: 'Cairo'; font-weight:700;">{brand} - {model}</h4>
                                </div>
                                <div class="status-badge" style="background: {col_status}20; border: 1px solid {col_status}; color: {col_status}; padding: 6px 16px; border-radius: 8px; font-weight: bold; font-family: 'Cairo'; font-size: 0.9rem; text-align: center;">
                                    {status}
                                </div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # الأكسباندر الملتحم
                    st.markdown('<div class="custom-expander">', unsafe_allow_html=True)
                    with st.expander("📄 عرض تفاصيل العطل والضمان المتقدم لهذا الجهاز"):
                        panne = dev.get("Panne", "غير محدد")
                        prix = dev.get("Prix", "0")
                        date_s = dev.get("Date_Sortie", "---")
                        w_stats = get_warranty_stats(date_s)
                        
                        st.markdown(f"""
                            <div style="text-align: right; direction: rtl; font-family: 'Cairo'; color: #ffffff;" dir="rtl">
                                📌 <b style="color: #cbd5e1;">العطل المشخص:</b> {panne}<br>
                                💰 <b style="color: #cbd5e1;">تكلفة الإصلاح:</b> <span style="color: #2ecc71; font-weight: bold;">{prix} دج</span><br>
                                📅 <b style="color: #cbd5e1;">تاريخ خروج الجهاز:</b> {date_s}<br>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        if w_stats:
                            st.markdown('<div style="text-align: right; direction: rtl; color: #ffffff; font-family: \'Cairo\';">🛡️ <b>حالة الضمان الفني للقطعة (30 يوم):</b></div>', unsafe_allow_html=True)
                            if w_stats["is_expired"]:
                                st.error(f"🔴 انتهى الضمان منذ {abs(w_stats['days_left'])} أيام (تاريخ الصلاحية: {w_stats['actual_date']})")
                            else:
                                st.success(f"🟢 الضمان ساري المفعول! متبقي {w_stats['days_left']} يوم (تنتهي الصلاحية: {w_stats['actual_date']})")
                                st.progress(w_stats["percent"])
                    st.markdown('</div>', unsafe_allow_html=True)
                # حقن زر التلغرام العائم بـ Z-index حماية قصوى
                bot_username = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                tg_link = f"https://t.me/{bot_username}?start={norm_phone}"
                st.markdown(f"""
                    <a href="{tg_link}" target="_blank" class="floating-tg-button" style="z-index: 999999 !important;">
                        <i class="fa-brands fa-telegram" style="font-size: 1.4rem;"></i>
                        <span>🚀 تفعيل إشعارات التلغرام</span>
                    </a>
                """, unsafe_allow_html=True)
            else:
                st.error("❌ عذراً، لم نجد أي جهاز مرتبط برقم الهاتف هذا حالياً في قاعدة البيانات.")
