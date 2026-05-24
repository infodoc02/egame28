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
import random
import base64
import os

# ==============================================================================
# 1. إعدادات الصفحة الأساسية ونظام المظهر الفاخر (Configuration & Theme)
# ==============================================================================
st.set_page_config(
    page_title="InfoDoc - Client Portal",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

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
    
    if "prêt" in status_lower: 
        return 1
    elif "annulé" in status_lower: 
        return 2
    elif "non réparable" in status_lower: 
        return 3
    elif "réparable" in status_lower: 
        return 4
    elif "en cours" in status_lower: 
        return 5
    elif "en attente" in status_lower: 
        return 6   
    elif "livré & payé" in status_lower or "livré (dette)" in status_lower:
        return 7
    else: 
        return 99

def render_hero_logo():
    """جلب اللوغو باستعمال المسار الحقيقي للسكريبت لتفادي مشكلة المجلدات في Streamlit"""
    import os
    import base64
    
    # تحديد مسار المجلد الحالي للسكريبت بالظبط (fail-safe path)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(current_dir, "ico.ico")
    
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as f:
                data = f.read()
                encoded = base64.b64encode(data).decode()
            # قراءة ملف الـ .ico وحقنه مباشرة كـ صورة متحركة
            return f'<img src="data:image/x-icon;base64,{encoded}" class="hero-logo-animated">'
        except:
            pass
            
    # الفولباك الآمن: إيموجي تقني يشتغل بدون إنترنت وبدون أن ينكسر أو يظهر كمربع
    return '<div class="hero-logo-animated" style="font-size: 4rem; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">🛠️</div>'
# ==============================================================================
# 4. تشغيل بوت التلغرام الاحترافي (المطور لـ InfoDoc)
# ==============================================================================
@st.cache_resource
def start_telegram_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: 
        return None

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
                        "3️⃣ سيظهر لك زر التفعيل إذا كان حسابك غير مرتبط بعد."
                    )
                    bot.reply_to(m, welcome_msg)
            except Exception as e:
                print(f"Error in Telegram logic: {e}")

        thread = threading.Thread(target=bot.infinity_polling, daemon=True)
        thread.start()
        return bot 
    except Exception as e:
        return None

if "bot_instance" not in st.session_state:
    if "TELEGRAM_TOKEN" in st.secrets:
        bot_obj = start_telegram_bot()
        if bot_obj:
            st.session_state["bot_instance"] = bot_obj

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
# 6. استدعاء الخطوط والمكتبات الخارجية لجمالية التصميم
# ==============================================================================
st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
""", unsafe_allow_html=True)

# ==============================================================================
# 7. نظام الـ CSS الكامل والمطور (The Premium Glassmorphism UI مع حركات اللوغو)
# ==============================================================================
st.markdown("""
    <style>
    .stApp {
        background: radial-gradient(circle at top left, #1e3a8a, #0f172a);
        background-attachment: fixed;
    }
    
    [data-testid="stVerticalBlock"] { padding-top: 1rem !important; }
    
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
        font-family: 'Cairo', sans-serif !important;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5) !important;
    }

    .hero-container {
        background: rgba(30, 41, 59, 0.45);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 30px;
        border-radius: 20px;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    /* أنيميشن اللوغو المطور */
    .hero-logo-animated {
        width: 105px;
        height: auto;
        margin: 0 auto 10px auto;
        filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.5));
        animation: floatLogo 3s ease-in-out infinite, glowPulse 2s ease-in-out infinite alternate;
    }

    @keyframes floatLogo {
        0% { transform: translateY(0px); }
        50% { transform: translateY(-8px); }
        100% { transform: translateY(0px); }
    }

    @keyframes glowPulse {
        0% { filter: drop-shadow(0 0 6px rgba(59, 130, 246, 0.4)); }
        100% { filter: drop-shadow(0 0 18px rgba(96, 165, 250, 0.8)); }
    }

    .hero-subtitle {
        color: #94a3b8;
        font-family: 'Cairo', sans-serif;
        font-weight: 700;
        font-size: 1.1rem;
    }
    
    .badge-open { background: rgba(46, 204, 113, 0.15); border: 1px solid #2ecc71; color: #2ecc71; }
    .badge-closed { background: rgba(231, 76, 60, 0.15); border: 1px solid #e74c3c; color: #e74c3c; }

    .contact-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 12px;
        margin-bottom: 25px;
    }
    .portal-contact-btn {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 15px;
        border-radius: 14px;
        text-decoration: none !important;
        font-family: 'Cairo', sans-serif;
        font-size: 0.85rem;
        font-weight: bold;
        transition: all 0.3s ease;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .portal-contact-btn i { font-size: 1.4rem; margin-bottom: 8px; }
    .portal-contact-btn:hover { transform: translateY(-3px); }
    
    .btn-phone { background: rgba(52, 152, 219, 0.1); color: #3498db !important; }
    .btn-map { background: rgba(230, 126, 34, 0.1); color: #e67e22 !important; }
    .btn-facebook { background: rgba(26, 115, 232, 0.1); color: #1a73e8 !important; }
    .btn-tiktok { background: rgba(255, 255, 255, 0.05); color: #ffffff !important; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 8. عرض واجهة المستخدم الرسومية العليا (UI Header) - نسخة مأمنة من الفراغات
# ==============================================================================
if not db_status:
    st.error("❌ عذراً، لا يمكن الاتصال بقاعدة البيانات حالياً. يرجى مراجعة إعدادات الخادم الفنية.")
    st.stop()

logo_html = render_hero_logo()
algeria_tz = pytz.timezone('Africa/Algiers')
now = datetime.now(algeria_tz)
greeting = "عزيزي الزبون، صباح الخير ☀️" if 5 <= now.hour < 12 else "عزيزي الزبون، مساء الخير ✨"

try:
    shop_status = db.reference("shop_settings/is_open").get()
    if shop_status is None: shop_status = False
except:
    shop_status = False

badge_class = "badge-open" if shop_status else "badge-closed"
badge_text = '● مـفـتـوح حـالـيـاً - مـرحـبـاً بـكـم في الـورشـة' if shop_status else '● مـغـلـق حـالـيـاً - نـسـتـقـبـلكم في وقـت لاحــق'
formatted_time = now.strftime("%d/%m/%Y - %H:%M")

# السر هنا: الأسطر راهي لاصقة في الحافة بدون مسافات لتفادي قراءتها كـ Code Block
header_html = f"""<div class="hero-container" dir="rtl">
<div style="color: #64748b; font-size: 0.95rem; font-family: 'Cairo'; font-weight: 300; margin-bottom: 15px;">
✨ {greeting} | 📅 {formatted_time}
</div>
{logo_html}
<div class="hero-subtitle" style="margin-bottom: 15px; margin-top: 10px;">
🛠️ الـمـنـصـة الإلـكـتـرونـيـة لـخـدمـات الـصـيـانـة لـورشـة INFODOC
</div>
<span class="{badge_class}" style="padding: 12px 30px; border-radius: 14px; font-weight: 900; display: inline-block; font-family: 'Cairo'; font-size: 1.05rem;">
{badge_text}
</span>
</div>"""

st.markdown(header_html, unsafe_allow_html=True)

# الروابط الاجتماعية للاتصال سريعاً
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

# لوحة شروط وملاحظات الصيانة الهامة لقوننة التعامل
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
<div class="rule-card">1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<span class="hl">رفض الزبون ذلك</span>, يتم دفع <span class="hl">1000 دج</span> ثمن الفحص والقياسات.</div>
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
# 9. نظام البحث المتقدم والمؤمن بالـ OTP عبر التلغرام (Secure Search Engine)
# ==============================================================================
st.markdown("""
<style>
div[data-testid="stTextInput"] input {
    direction: rtl !important;
    text-align: right !important;
    font-family: 'Cairo', sans-serif !important;
    color: #f1f5f9 !important;
    background-color: rgba(15, 23, 42, 0.6) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 10px !important;
}
.otp-container {
    background: rgba(30, 41, 59, 0.5) !important;
    border: 1px dashed #3b82f6 !important;
    padding: 20px !important;
    border-radius: 16px !important;
    text-align: center !important;
    margin-bottom: 20px !important;
}
.not-linked-container {
    background: rgba(30, 41, 59, 0.5) !important;
    border: 1px dashed #e67e22 !important;
    padding: 25px !important;
    border-radius: 16px !important;
    text-align: center !important;
    margin-bottom: 20px !important;
    direction: rtl;
}
.device-top-card {
    background: rgba(30, 41, 59, 0.7) !important;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 14px 14px 0 0 !important;
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
.device-expander {
    background: rgba(30, 41, 59, 0.85) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-top: none !important;
    border-radius: 0 0 14px 14px !important;
    padding: 0 16px;
    margin-bottom: 8px;
    font-family: 'Cairo', sans-serif;
}
.device-expander summary {
    color: #e2e8f0 !important;
    font-weight: bold;
    font-size: 1rem;
    cursor: pointer;
    outline: none;
    list-style: none;
    padding: 12px 4px;
    text-align: right;
    direction: rtl;
}
.device-expander summary::-webkit-details-marker { display: none; }
.detail-row {
    color: #e2e8f0;
    font-family: 'Cairo', sans-serif;
    font-size: 0.95rem;
    line-height: 2;
    text-align: right;
    direction: rtl;
    padding: 4px 0;
}
.detail-row:hover { background-color: rgba(255, 255, 255, 0.02); }
.detail-label { color: #94a3b8; font-weight: bold; }
.warranty-ok {
    background: rgba(46, 204, 113, 0.1);
    border: 1px solid #2ecc71;
    border-radius: 8px;
    color: #2ecc71;
    padding: 10px 14px;
    text-align: right;
    direction: rtl;
    font-family: 'Cairo', sans-serif;
    margin-top: 8px;
}
.warranty-expired {
    background: rgba(231, 76, 60, 0.1);
    border: 1px solid #e74c3c;
    border-radius: 8px;
    color: #e74c3c;
    padding: 10px 14px;
    text-align: right;
    direction: rtl;
    font-family: 'Cairo', sans-serif;
    margin-top: 8px;
}
.warranty-progress-wrap {
    background: rgba(255,255,255,0.1);
    border-radius: 6px;
    height: 8px;
    margin-top: 8px;
    margin-bottom: 12px;
    overflow: hidden;
    direction: rtl;
}
.warranty-progress-bar {
    background: #2ecc71;
    height: 8px;
    border-radius: 6px;
    transition: width 0.5s ease;
}
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
    z-index: 999999;
    animation: tg-bounce 2.5s infinite ease-in-out;
}
@keyframes tg-bounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
}
</style>
""", unsafe_allow_html=True)

if "auth_step" not in st.session_state:
    st.session_state["auth_step"] = "input_phone"
if "generated_otp" not in st.session_state:
    st.session_state["generated_otp"] = None
if "target_tg_id" not in st.session_state:
    st.session_state["target_tg_id"] = None
if "verified_phone" not in st.session_state:
    st.session_state["verified_phone"] = ""
if "hide_tg_button" not in st.session_state:
    st.session_state["hide_tg_button"] = True 

# --- المرحلة 1: إدخال رقم الهاتف وفحص الحساب ---
if st.session_state["auth_step"] == "input_phone":
    st.session_state["hide_tg_button"] = True  
    st.markdown('<h3 style="text-align: right; font-family: \'Cairo\'; color: #e2e8f0; font-size: 1.25rem; font-weight:700;">🔍 تتبع حالة أجهزتك بأمان:</h3>', unsafe_allow_html=True)
    
    user_phone = st.text_input("", placeholder="أدخل رقم هاتفك هنا (مثال: 0798661900)", key="phone_input_key", label_visibility="collapsed")
    submit_search = st.button("🔎 دخول ومتابعة حالة الأجهزة")

    if submit_search and user_phone:
        norm_phone = normalize_phone(user_phone)
        if len(norm_phone) < 9:
            st.error("⚠️ يرجى إدخال رقم هاتف صحيح يتكون من 9 أرقام على الأقل.")
        else:
            with st.spinner("⏳ جارٍ فحص الحساب وقاعدة البيانات..."):
                db_ref = db.reference("atelier")
                all_data = db_ref.get()

                has_devices = False
                telegram_id = None

                if all_data:
                    for k, v in all_data.items():
                        db_phone = normalize_phone(v.get("Telephone", ""))
                        if db_phone.endswith(norm_phone[-9:]):
                            has_devices = True
                            if v.get("Telegram_ID"):
                                telegram_id = str(v.get("Telegram_ID"))
                                break

                if not has_devices:
                    st.error("❌ عذراً، لم نجد أي جهاز نشط مرتبط برقم الهاتف هذا حالياً في قاعدة بيانات الورشة.")
                else:
                    st.session_state["verified_phone"] = norm_phone
                    
                    if telegram_id:
                        st.session_state["target_tg_id"] = telegram_id
                        st.session_state["hide_tg_button"] = True
                        
                        otp_code = str(random.randint(1000, 9999))
                        st.session_state["generated_otp"] = otp_code
                        
                        bot = st.session_state.get("bot_instance")
                        if bot:
                            try:
                                msg_text = (
                                    f"🔐 *كود تأكيد الهوية لـ بورطاي InfoDoc:*\n\n"
                                    f"كود الدخول الخاص بك هو: `{otp_code}`\n\n"
                                    f"⏱️ _هذا الكود صالح للاستعمال لمرة واحدة فقط في المتصفح._"
                                )
                                bot.send_message(telegram_id, msg_text)
                                st.session_state["auth_step"] = "verify_otp"
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ فشل السيرفر في إرسال الكود إلى تلغرام، يرجى المحاولة لاحقاً.")
                        else:
                            st.error("❌ نظام البوت غير متصل حالياً بالسيرفر، يرجى مراجعة الإعدادات الفنية للورشة.")
                    else:
                        st.session_state["auth_step"] = "not_linked"
                        st.session_state["hide_tg_button"] = False 
                        st.rerun()

# --- المرحلة 2: واجهة الحساب غير مرتبط بالتلغرام ---
elif st.session_state["auth_step"] == "not_linked":
    st.session_state["hide_tg_button"] = False  
    phone_to_link = st.session_state["verified_phone"]
    target_link = f"https://t.me/InfoDoc02_bot?start={phone_to_link}"

    st.markdown(f"""
    <div class="not-linked-container">
        <h4 style="color: #e67e22; font-family: 'Cairo'; margin-top:0;">⚠️ حسابك غير مرتبط ببوت التلغرام</h4>
        <p style="color: #cbd5e1; font-family: 'Cairo'; font-size:1rem; line-height:1.6;">
            لتأمين تذاكرك واصلاحاتك، نستخدم نظام التحقق الآمن عبر التلغرام.<br>
            رقمك <b>({phone_to_link})</b> يحتاج إلى تفعيل الإشعارات أولاً لتلقي كود الدخول.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
        <div style="margin-bottom:20px;" dir="rtl">
            <a href="{target_link}" target="_blank" style="text-decoration:none;">
                <button style="width:100%; border-radius:12px; height:3.2em; background:linear-gradient(90deg, #24A1DE 0%, #1d80b0 100%); color:white; font-weight:700; font-family:'Cairo'; border:none; box-shadow:0 4px 15px rgba(36, 161, 222, 0.3); cursor:pointer;">
                    🚀 اضغط هنا لتفعيل إشعارات التلغرام فوراً
                </button>
            </a>
        </div>
    """, unsafe_allow_html=True)

    col_recheck, col_back = st.columns(2)
    with col_recheck:
        if st.button("🔄 تم التفعيل، اضغط هنا للدخول"):
            with st.spinner("⏳ جارٍ التحقق من إتمام عملية الربط الفعلي..."):
                db_ref = db.reference("atelier")
                fresh_data = db_ref.get()
                updated_tg_id = None
                
                if fresh_data:
                    for k, v in fresh_data.items():
                        db_phone = normalize_phone(v.get("Telephone", ""))
                        if db_phone.endswith(phone_to_link[-9:]) and v.get("Telegram_ID"):
                            updated_tg_id = str(v.get("Telegram_ID"))
                            break
                
                if updated_tg_id:
                    st.session_state["target_tg_id"] = updated_tg_id
                    st.session_state["hide_tg_button"] = True
                    
                    otp_code = str(random.randint(1000, 9999))
                    st.session_state["generated_otp"] = otp_code
                    
                    bot = st.session_state.get("bot_instance")
                    if bot:
                        msg_text = (
                            f"🔐 *كود تأكيد الهوية لـ بورطاي InfoDoc:*\n\n"
                            f"كود الدخول الخاص بك هو: `{otp_code}`\n\n"
                            f"⏱️ _هذا الكود صالح للاستعمال لمرة واحدة فقط في المتصفح._"
                        )
                        bot.send_message(updated_tg_id, msg_text)
                        st.session_state["auth_step"] = "verify_otp"
                        st.rerun()
                else:
                    st.error("❌ يبدو أنك لم تقم بالضغط على زر Start في التلغرام بعد، يرجى الضغط عليه والبدء ثم المحاولة مجدداً.")
                    
    with col_back:
        if st.button("⬅️ تراجع وتغيير الرقم"):
            st.session_state["auth_step"] = "input_phone"
            st.session_state["hide_tg_button"] = True
            st.rerun()

# --- المرحلة 3: واجهة إدخل كود الـ OTP المحدثة والتلقائية ---
elif st.session_state["auth_step"] == "verify_otp":
    st.session_state["hide_tg_button"] = True  
    st.markdown(f"""
    <div class="otp-container" dir="rtl">
        <h4 style="color: #3b82f6; font-family: 'Cairo'; margin-top:0;">🔐 نظام التحقق ثنائي الخطوات (2FA)</h4>
        <p style="color: #94a3b8; font-family: 'Cairo'; font-size:0.95rem;">
            تم إرسال كود سري إلى حساب التلغرام الخاص بك المرتبط بالرقم ({st.session_state["verified_phone"]}).
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    entered_otp = st.text_input("", placeholder="أدخل كود الـ OTP المتكون من 4 أرقام هنا...", key="otp_field", label_visibility="collapsed")

    col_confirm, col_resend, col_cancel = st.columns(3)
    with col_confirm:
        if st.button("✅ تأكيد الرمز"):
            if entered_otp.strip() == st.session_state["generated_otp"]:
                st.session_state["auth_step"] = "display_devices"
                st.rerun()
            else:
                st.error("❌ الكود السري غير صحيح!")
                
    with col_resend:
        if st.button("🔄 إعادة إرسال الكود"):
            with st.spinner("⏳ جارٍ توليد وإرسال كود جديد..."):
                otp_code = str(random.randint(1000, 9999))
                st.session_state["generated_otp"] = otp_code
                
                bot = st.session_state.get("bot_instance")
                if bot and st.session_state["target_tg_id"]:
                    try:
                        msg_text = (
                            f"🔄 *كود تأكيد الهوية الجديد لـ بورطاي InfoDoc:*\n\n"
                            f"كود الدخول الجديد الخاص بك هو: `{otp_code}`\n\n"
                            f"⏱️ _هذا الكود الجديد يلغي الكود السابق وهو صالح لمرة واحدة._"
                        )
                        bot.send_message(st.session_state["target_tg_id"], msg_text)
                        st.toast("⚡ تم إرسال كود جديد بنجاح لحسابك!", icon="📩")
                    except:
                        st.error("❌ فشل إعادة إرسال الرسالة، يرجى المحاولة مجدداً.")
                
    with col_cancel:
        if st.button("⬅️ تراجع للخلف"):
            st.session_state["auth_step"] = "input_phone"
            st.session_state["hide_tg_button"] = True  
            st.rerun()

# --- المرحلة 4: جلب وعرض الأجهزة حياً ومباشرة من قاعدة البيانات ---
elif st.session_state["auth_step"] == "display_devices":
    st.session_state["hide_tg_button"] = True  
    
    col_title, col_logout = st.columns([3, 1])
    with col_title:
        st.markdown('<h3 style="text-align: right; font-family: \'Cairo\'; color: #2ecc71; font-size: 1.25rem; font-weight:700;">📋 أجهزتك الحالية في الورشة :</h3>', unsafe_allow_html=True)
    with col_logout:
        if st.button("🚪 خروج وبحث جديد"):
            st.session_state["auth_step"] = "input_phone"
            st.session_state["hide_tg_button"] = True  
            st.rerun()

    phone_query = st.session_state["verified_phone"]
    
    with st.spinner("⏳ جارٍ تحديث حالة الأجهزة مباشرة من السيرفر..."):
        db_ref = db.reference("atelier")
        all_data = db_ref.get()
        live_devices = []

        if all_data:
            for k, v in all_data.items():
                db_phone = normalize_phone(v.get("Telephone", ""))
                if db_phone.endswith(phone_query[-9:]):
                    status_lower = str(v.get("Statut", "")).strip().lower()
                    date_s = v.get("Date_Sortie", "---")
                    
                    if status_lower in ["livré & payé", "livré (dette)"]:
                        w_stats = get_warranty_stats(date_s)
                        if w_stats and w_stats.get("is_expired"):
                            continue 
                    
                    live_devices.append(dict(v, _id=k))

    if not live_devices:
        st.warning("🔄 لا توجد أجهزة نشطة حالياً للعرض.")
    else:
        live_devices.sort(key=lambda x: get_status_priority(x.get("Statut", "")))

        for dev in live_devices:
            dev_id = dev.get("ID", "0000")
            brand = dev.get("Marque", "")
            model = dev.get("Appareil", "جهاز غير معروف")
            status = dev.get("Statut", "En attente")
            panne = dev.get("Panne", "غير محدد")
            prix = dev.get("Prix", "0")
            date_s = dev.get("Date_Sortie", "---")
            date_e = dev.get("Date_Entree", "---")
            w_stats = get_warranty_stats(date_s)

            status_colors = {"prêt": "#2ecc71", "en cours": "#f1c40f", "en attente": "#e67e22", "annulé": "#e74c3c"}
            col_status = status_colors.get(status.lower(), "#3498db")
            
            status_lower = status.lower().strip()
            livred_statuses = ["livré & payé", "livré (dette)"]
            dynamic_bar_html = ""

            if status_lower in livred_statuses:
                if w_stats:
                    if w_stats["is_expired"]:
                        dynamic_bar_html = f'<div class="warranty-expired">🔴 انتهى الضمان منذ {abs(w_stats["days_left"])} أيام ({w_stats["actual_date"]})</div>'
                    else:
                        dynamic_bar_html = f'<div class="warranty-ok">🟢 الضمان ساري المفعول! متبقي {w_stats["days_left"]} يوم</div><div class="warranty-progress-wrap"><div class="warranty-progress-bar" style="width:{w_stats["percent"]}%;"></div></div>'
            else:
                repair_steps = {
                    "en attente": (0, "#e67e22", "⏳ في الانتظار والأرشفة الفنية"),
                    "en cours": (33, "#f1c40f", "🔧 جارٍ الفحص وتتبع الإشارات المجهرية"),
                    "réparable": (66, "#3498db", "✅ قابل للإصلاح وبانتظار المكونات"),
                    "prêt": (100, "#2ecc71", "🎉 جاهز تماماً للاستلام من الورشة"),
                    "annulé": (66, "#e74c3c", "❌ تم إلغاء العملية")
                }
                if status_lower in repair_steps:
                    pct, color, label = repair_steps[status_lower]
                    dynamic_bar_html = f'<div style="color:{color}; font-weight:bold; text-align:right;">{label}</div><div class="warranty-progress-wrap"><div class="warranty-progress-bar" style="width:{pct}%; background:{color};"></div></div>'

            st.markdown(f"""
            <div class="device-top-card" dir="rtl">
                <div class="card-container">
                    <div style="text-align: right;">
                        <span style="color: #cbd5e1; font-size: 0.85rem;">تذكرة #{dev_id}</span>
                        <h4 style="margin: 4px 0; color: #ffffff; font-family: 'Cairo';">{brand} - {model}</h4>
                    </div>
                    <div style="background: {col_status}20; border: 1px solid {col_status}; color: {col_status}; padding: 6px 16px; border-radius: 8px; font-weight: bold;">{status}</div>
                </div>
            </div>
            <details class="device-expander">
                <summary>📄 عرض تفاصيل العطل والتكلفة المحسوبة</summary>
                <div style="padding-bottom: 14px;">
                    <div class="detail-row">📌 <span class="detail-label">العطل المشخص:</span> {panne}</div>
                    <div class="detail-row">💰 <span class="detail-label">تكلفة الإصلاح:</span> <span style="color:#2ecc71; font-weight:bold;">{prix} دج</span></div>
                    <div class="detail-row">📅 <span class="detail-label">تاريخ الاستلام:</span> {date_e}</div>
                    <div class="detail-row">📅 <span class="detail-label">تاريخ الخروج والاقفال:</span> {date_s}</div>
                    {dynamic_bar_html}
                </div>
            </details>
            """, unsafe_allow_html=True)

# ==============================================================================
# 10. حقن زر التلغرام العائم ذكياً
# ==============================================================================
if not st.session_state.get("hide_tg_button", True):
    current_phone = st.session_state.get("verified_phone", "")
    target_link = f"https://t.me/InfoDoc02_bot?start={current_phone}" if current_phone else "https://t.me/InfoDoc02_bot"
    st.markdown(f"""
        <a href="{target_link}" target="_blank" class="floating-tg-button">
            <i class="fa-brands fa-telegram"></i>
            <span>🚀 تفعيل إشعارات التلغرام</span>
        </a>
    """, unsafe_allow_html=True)

st.divider()
st.subheader("🛠️ أدوات الإدارة (للتجريب فقط)")
if st.button("🚀 إرسال رسالة تجريبية للمجموعة الآن"):
    test_msg = "السلام عليكم جيراننا الكرام،\nهذه رسالة تجريبية من البوت للتأكد من تفعيل نظام الإشعارات في المجموعة. 🤖🏢✅"
    
    # استعملنا الـ ID المصحح بـ -100
    success = safe_send(-1003869677102, test_msg)
    
    if success:
        st.success("✅ تم الإرسال للمجموعة بنجاح! روح للتلغرام وتأكد.")
    else:
        st.error("❌ فشل الإرسال! تأكد من أن البوت مضاف في المجموعة وعنده صلاحية الكتابة.")
