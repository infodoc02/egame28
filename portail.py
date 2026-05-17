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
            # محاولة جلب البيانات من Secrets بأمان
            if "firebase" in st.secrets and "DB_URL" in st.secrets:
                cred_dict = dict(st.secrets["firebase"])
                if "\\n" in cred_dict.get("private_key", ""):
                    cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
                return True
            else:
                # وضع احتياطي محلي في حال غياب السيكرتس لتجنب توقف البورطاي
                st.warning("⚠️ Mode local/limité activé (Secrets non configurés).")
                return False
        except Exception as e:
            st.error(f"❌ Erreur connexion Firebase: {e}")
            return False
    return True

# تفعيل الاتصال
db_status = init_db()

# ==============================================================================
# 7. تشغيل بوت التلغرام الاحترافي (المطور لـ InfoDoc)
# ==============================================================================

@st.cache_resource
def start_telegram_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: 
        return "Missing Token"

    try:
        # استخدام TeleBot مع حماية لمنع تكرار الاتصال
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
                            # المطابقة الذكية لأحدث 9 أرقام لضمان الدقة الكاملة
                            db_phone = normalize_phone(v.get("Telephone", ""))
                            if db_phone.endswith(client_phone[-9:]):
                                ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                                # جمع أسماء الأجهزة المرتبطة لعرضها للزبون في رسالة التأكيد
                                device_name = v.get("Appareil", "جهاز غير معروف")
                                ticket_id = v.get("ID", "0000")
                                linked_devices.append(f"• *{device_name}* (تذكرة #{ticket_id})")
                        
                        if linked_devices:
                            devices_list_str = "\n".join(linked_devices)
                            success_msg = (
                                "🔔 *تفعيل الإشعارات الفورية - InfoDoc*\n\n"
                                "✅ *تم ربط حسابك بنجاح!*\n"
                                "ستصلك إشعارات تلقائية وفورية هنا على التلغرام بمجرد حدوث أي تغيير في حالة أجهزتك (فحص، قيد الصيانة، أو جاهز للتسليم).\n\n"
                                "📦 *الأجهزة المرتبطة حالياً:*\n"
                                f"{devices_list_str}\n\n"
                                "⏱️ _شكراً لثقتكم في خدماتنا._"
                            )
                            bot.reply_to(m, success_msg)
                        else:
                            error_msg = (
                                "❌ *خطأ في عملية الربط*\n\n"
                                "عذراً، لم نجد أي جهاز مسجل برقم الهاتف هذا في قاعدة بيانات الورشة حالياً.\n"
                                "يرجى التأكب من الرقم الذي سجلت به عند تسليم الجهاز."
                            )
                            bot.reply_to(m, error_msg)
                    else:
                        bot.reply_to(m, "⚠️ قاعدة البيانات فارغة حالياً أو غير متصلة.")
                else:
                    # رسالة الترحيب العامة إذا دخل البوت مباشرة بدون رابط التطبيق
                    welcome_msg = (
                        "👋 *مرحباً بك في بوت ورشة InfoDoc الفنية!*\n\n"
                        "هذا البوت مخصص لإرسال إشعارات تلقائية وفورية لزبائننا لتتبع حالة صيانة أجهزتهم (لابتوب / كمبيوتر).\n\n"
                        "ℹ️ *كيفية تفعيل الخدمة:*\n"
                        "1️⃣ اذهب إلى موقعنا الإلكتروني.\n"
                        "2️⃣ ابحث عن أجهزتك باستخدام رقم هاتفك.\n"
                        "3️⃣ اضغط على زر *🚀 تفعيل إشعارات التلغرام* العائم ليربط حسابك تلقائياً."
                    )
                    bot.reply_to(m, welcome_msg)
            except Exception as e:
                print(f"Error in Telegram logic: {e}")

        # تشغيل البوت في خيط (Thread) منفصل مستقر تماماً
        thread = threading.Thread(target=bot.infinity_polling, daemon=True)
        thread.start()
        return "Bot Started Successfully"
    except Exception as e:
        return f"Error: {e}"

# 🚀 التأمين والتشغيل الذكي (يوضع هذا السطر في أعلى الـ Main بعد إعداد الصفحة مباشرة)
if "bot_initialized" not in st.session_state:
    if "TELEGRAM_TOKEN" in st.secrets:
        status = start_telegram_bot()
        if "Successfully" in status:
            st.session_state["bot_initialized"] = True
# ==============================================================================
# 3. الدوال البرمجية المساعدة وإدارة الحالات والضمان (Helper Functions)
# ==============================================================================

def normalize_phone(phone: str) -> str:
    """تنسيق وتوحيد رقم الهاتف الجزائري (نقال وثابت) ليطابق المخزن في السيرفر الرئيسي."""
    if not phone: 
        return ""
    p = re.sub(r"\D", "", str(phone))
    
    if p.startswith("213"):
        p = "0" + p[3:]
    elif p.startswith("00213"):
        p = "0" + p[5:]
    
    # تحسين: يشمل الهاتف النقال (5,6,7) والهاتف الثابت للولايات (يبدأ بـ 2، 3، 4، إلخ)
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
        remaining_days = 30 - diff_days # نتركها بالسالب لمعرفة كم يوم مضى على انتهاء الضمان
        
        # حماية النسبة المئوية لتبقى بين 0 و 100 دائماً
        percent = max(0, min((remaining_days / 30) * 100, 100))
        
        return {
            "percent": int(percent), 
            "is_expired": diff_days > 30, 
            "days_left": remaining_days, # تقدر تكون سالبة (مثال: -5 تعني انتهى منذ 5 أيام)
            "actual_date": date_s.strftime("%d/%m/%Y")
        }
    
    return None

def get_status_priority(status):
    """تحديد أولوية الفرز لعرض الأجهزة الجاهزة للزبون أولاً (Dashboard Priority)."""
    s = str(status).strip()
    # توحيد حالة الأحرف لتفادي مشاكل الحروف الكبيرة والصغيرة (Case-insensitive)
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
        return 7  # المستلم والمخلص يرجع هو الأخير قاع
    else: 
        return 99
# ==============================================================================
# 3. واجهة المستخدم وتتبع الزوار الذكي (UI & Visitor Tracking)
# ==============================================================================

# استدعاء الخطوط الاحترافية من قوقل لضمان المظهر العالمي للبوابة
st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# تفعيل تتبع الزوار الذكي (المدمج والمحمي في الجزء الأول) عبر الـ session_state لمنع أي بطء
# ==============================================================================
# 5. نظام تتبع الزوار الذكي الفعلي (Visitor Tracking Execution)
# ==============================================================================
if db_status and 'visitor_tracked' not in st.session_state:
    try:
        tz = pytz.timezone('Africa/Algiers')
        now_dt = datetime.now(tz)
        today_str = now_dt.strftime("%Y-%m-%d")
        
        # جلب آمن وسريع عبر سياق Streamlit بدون طلبات requests خارجية تبطئ التصفح
        headers = st.context.headers
        ip = headers.get("X-Forwarded-For", headers.get("Remote-Addr", "127.0.0.1")).split(",")[0].strip()
        clean_ip = ip.replace(".", "_")
        
        # التأكد والتسجيل في خطوة موحدة
        ref_ip = db.reference(f"stats/daily_ips/{today_str}/{clean_ip}")
        if ref_ip.get() is None:
            ref_ip.set(True)
            # تحديث عداد الزوار الذكي والذري (Atomic Transaction) لمنع تداخل البيانات
            visitor_counter_ref = db.reference(f"stats/daily_visitors/{today_str}")
            visitor_counter_ref.transaction(lambda current_value: (current_value or 0) + 1)
            
        st.session_state['visitor_tracked'] = True
    except:
        pass

# إعداد التوقيت المحلي والترحيب بالزبائن بدقة
algeria_tz = pytz.timezone('Africa/Algiers')
now = datetime.now(algeria_tz)
greeting = "عزيزي الزبون، صباح الخير ☀️" if 5 <= now.hour < 12 else "عزيزي الزبون، مساء الخير ✨"

# جلب حالة المحل الحالية من السيرفر الرئيسي مع معالجة الأخطاء
try:
    shop_status = db.reference("shop_settings/is_open").get()
    if shop_status is None:
        shop_status = False
except:
    shop_status = False

# تأثيرات الأنيميشن والنيون الفاخرة (Neon Pulse Effects) لحالة المحل
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
    </style>
""", unsafe_allow_html=True)

# عرض الهيدر الرئيسي الفاخر (Hero Container) متوافق تماماً مع الاتجاه من اليمين لليسار للعربية
st.markdown(f'''
    <div class="hero-container" dir="rtl">
        <div style="color: #64748b; font-size: 0.95rem; font-family: 'Cairo', sans-serif; font-weight: 700; margin-bottom: 12px;">
            ✨ {greeting} | 📅 {now.strftime("%d/%m/%Y - %H:%M")}
        </div>
        <div class="hero-brand">
            INFODOC
        </div>
        <div class="hero-subtitle" style="margin-bottom: 25px;">
            🛠️ الـمـنـصـة الإلـكـتـرونـيـة الـمـتـقـدمـة لـخـدمـات الـصـيـانـة والـضـمـان
        </div>
        <span class="{"badge-open" if shop_status else "badge-closed"}" 
              style="padding: 12px 30px; border-radius: 14px; font-weight: 900; display: inline-block; font-family: 'Cairo', sans-serif; font-size: 1.05rem; letter-spacing: 1px;">
            {'● مـفـتـوح حـالـيـاً - مـرحـبـاً بـكـم في الـورشـة' if shop_status else '● مـغـلـق حـالـيـاً - نـسـتـقـبـلكم في أوقـات الـعـمـل'}
        </span>
    </div>
''', unsafe_allow_html=True)
# ==============================================================================
# 4. أزرار التواصل السريع والخلفية المتطورة (Quick Contact Buttons & Tech BG)
# ==============================================================================

# استدعاء أيقونات FontAwesome الشهيرة لضمان مظهر موحد واحترافي على كاع الأجهزة
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
""", unsafe_allow_html=True)

# نظام التنسيق المتقدم: خلفية إلكترونية رقمية + أزرار تواصل مستجيبة وفخمة
st.markdown("""
    <style>
    /* إضافة لمسة الإلكترونيات والخلفية الشبكية السيبرانية للتطبيق بالكامل */
    .stApp {
        background: radial-gradient(circle at top left, #1a365d, #0b1329) !important;
        background-image: 
            radial-gradient(at 0% 0%, rgba(37, 99, 235, 0.2) 0, transparent 50%), 
            radial-gradient(at 50% 0%, rgba(29, 78, 216, 0.1) 0, transparent 50%),
            linear-gradient(rgba(255, 255, 255, 0.005) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255, 255, 255, 0.005) 1px, transparent 1px) !important;
        background-size: 100% 100%, 100% 100%, 30px 30px, 30px 30px !important;
        background-attachment: fixed !important;
    }

    /* حاوية الأزرار لضمان التجاوب الكامل على الهواتف والأجهزة اللوحية */
    .contact-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 15px;
        margin-bottom: 30px;
        width: 100%;
    }

    /* التصميم الزجاجي الموحد للأزرار */
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
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }

    /* حركة الارتفاع العامة */
    .portal-contact-btn:hover {
        transform: translateY(-5px);
        color: #ffffff !important;
        border-color: rgba(255, 255, 255, 0.2) !important;
    }

    /* تأثير نيون مخصص لكل زر حسب هوية المنصة */
    .btn-phone:hover { 
        background: rgba(46, 204, 113, 0.15) !important; 
        box-shadow: 0 8px 25px rgba(46, 204, 113, 0.3);
        color: #2ecc71 !important;
    }
    .btn-map:hover { 
        background: rgba(231, 76, 60, 0.15) !important; 
        box-shadow: 0 8px 25px rgba(231, 76, 60, 0.3);
        color: #e74c3c !important;
    }
    .btn-facebook:hover { 
        background: rgba(24, 119, 242, 0.15) !important; 
        box-shadow: 0 8px 25px rgba(24, 119, 242, 0.3);
        color: #1877f2 !important;
    }
    .btn-tiktok:hover { 
        background: rgba(0, 242, 234, 0.08) !important; 
        box-shadow: 0 8px 25px rgba(254, 44, 85, 0.25);
        color: #00f2ea !important;
    }

    /* تنسيق حجم الأيقونات والنصوص */
    .portal-contact-btn i {
        font-size: 2rem;
        margin-bottom: 10px;
        transition: 0.3s transform ease;
    }
    .portal-contact-btn:hover i {
        transform: scale(1.15);
    }
    .portal-contact-btn .label {
        font-family: 'Cairo', sans-serif !important;
        font-size: 0.95rem;
        font-weight: 700;
        letter-spacing: 0.3px;
    }
    </style>
""", unsafe_allow_html=True)

# عرض الأزرار داخل حاوية الـ Grid الذكية والمتوافقة مع العربية RTL
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
# ==============================================================================
# 5. قسم الشروط والملاحظات الهامة (Glow Expander)
# ==============================================================================

# أنيميشن ومظهر خاص للأكسباندر التحذيري ليكون مضيئاً وجاذباً للانتباه بشكل متوافق تماماً
st.markdown("""
    <style>
    /* أنيميشن الوميض الذهبي الفاخر */
    @keyframes gold-glow {
        0%, 100% { border-color: rgba(234, 179, 8, 0.4); box-shadow: 0 0 10px rgba(234, 179, 8, 0.1); }
        50% { border-color: rgba(250, 204, 21, 0.9); box-shadow: 0 0 25px rgba(250, 204, 21, 0.3); }
    }
    
    /* استهداف الحاوية الأصلية للـ Expander في Streamlit */
    div[data-testid="stExpander"] {
        border: 2px solid #eab308 !important;
        animation: gold-glow 3.5s infinite ease-in-out !important;
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.8) 0%, rgba(234, 179, 8, 0.04) 100%) !important;
        border-radius: 16px !important;
        padding: 2px !important;
        margin-top: 20px !important;
        margin-bottom: 20px !important;
    }
    
    /* ضبط اتجاه النص والعنوان ليكون عربياً خالصاً من اليمين لليسار */
    div[data-testid="stExpander"] details summary {
        direction: rtl !important;
        text-align: right !important;
    }
    
    /* تنسيق نص العنوان الرئيسي للأكسباندر */
    div[data-testid="stExpander"] details summary span p {
        font-family: 'Cairo', sans-serif !important;
        font-weight: 900 !important;
        color: #facc15 !important;
        font-size: 1.15rem !important;
        letter-spacing: 0.5px;
    }
    
    /* تحسين أيقونة السهم الافتراضية لـ Streamlit لتتوافق مع الـ RTL */
    div[data-testid="stExpander"] details summary svg {
        position: absolute !important;
        left: 15px !important;
        right: auto !important;
        color: #facc15 !important;
    }
    
    /* تنسيق تذاكر الشروط الداخلية */
    .rule-item {
        background: rgba(255, 255, 255, 0.02) !important;
        border-right: 4px solid #eab308;
        border-left: 1px solid rgba(255,255,255,0.05);
        border-top: 1px solid rgba(255,255,255,0.05);
        border-bottom: 1px solid rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 12px;
        transition: 0.3s all ease;
    }
    .rule-item:hover {
        background: rgba(234, 179, 8, 0.05) !important;
        transform: scale(1.01);
    }
    .highlight-gold {
        color: #facc15 !important;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

# إنشاء الـ Expander المضيء مباشرة بدون كسر الـ HTML
with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: 'Cairo', sans-serif; color: #e2e8f0; padding: 10px 5px;" dir="rtl">
            
            <div class="rule-item">
                1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<span class="highlight-gold">رفض الزبون ذلك</span>، يتم دفع <span class="highlight-gold">1000 دج</span> ثمن الجهد والفحص المخبري وعمليات القياس الدقيقة.
            </div>
            
            <div class="rule-item">
                2️⃣ أسعار العمل الاحترافي والدقيق على <span class="highlight-gold">البطاقة الأم (Carte Mère)</span> والمكونات الإلكترونية المجهرية تبدأ من <span class="highlight-gold">3000 دج</span>.
            </div>
            
            <div class="rule-item">
                3️⃣ أسعار <span class="highlight-gold">تفليش وفتح البيوس وبرمجة السوبر آي أو (Flash BIOS / SIO)</span> تبدأ من <span class="highlight-gold">1500 دج</span> حسب جيل ونوع معالج الجهاز.
            </div>
            
            <div class="rule-item">
                4️⃣ <span class="highlight-gold">سياسة الموافقة التلقائية:</span> نقوم بالإصلاح مباشرة وبدون الاتصال بك إذا كانت التكلفة الإجمالية تتراوح بين <span class="highlight-gold">3000 دج و 4000 دج</span> لتسريع وثيقة التسليم، وما فوق ذلك نتصل بك مسبقاً.
            </div>
            
            <div class="rule-item">
                5️⃣ <span class="highlight-gold">شروط الضمان المتقدم:</span> الضمان الممنوح لخدماتنا (<span class="highlight-gold">30 يوماً</span>) صالح <span class="highlight-gold">حصراً</span> على العيب أو العنصر الإلكتروني الذي تم إصلاحه، وأي خلل مفاجئ يمس مكوناً آخر لا يدخل ضمن الضمان.
            </div>
            
            <div class="rule-item" style="border-right-color: #3b82f6; margin-bottom: 0;">
                6️⃣ <span style="color: #3b82f6; font-weight: bold;">تحديثات فورية لهاتفك:</span> نوصي بشدة بفتح حساب في تطبيق <span style="color: #3b82f6; font-weight: bold;">Telegram</span>، ثم تفعيل بوت الإشعارات بالأسفل لتلقي تحديثات حية ومؤتمتة لحالة جهازك (<span class="highlight-gold">En cours / Prêt</span>) مباشرة على هاتفك.
            </div>
            
        </div>
    """, unsafe_allow_html=True)

st.divider()
# ==============================================================================
# 5. نظام البحث والتتبع (النسخة الملتحمة بالكامل - بدون ديكالاج)
# ==============================================================================

# حقن التنسيق العالمي لمنع التباعد والـ Decalage بين الكروت والأكسباندرز
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    /* فرض اتجاه اللغة العربية على حقل إدخال الهاتف بالكامل */
    div[data-testid="stTextInput"] input {
        direction: rtl !important;
        text-align: right !important;
        font-family: 'Cairo', sans-serif !important;
        color: #f1f5f9 !important;
        background-color: rgba(15, 23, 42, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 10px !important;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 10px rgba(59, 130, 246, 0.3) !important;
    }
    
    /* زر البحث المطور داخل الفورم */
    button[data-testid="stFormSubmitButton"] {
        width: 100% !important;
        background: linear-gradient(90deg, #3b82f6 0%, #1d4ed8 100%) !important;
        color: white !important;
        font-family: 'Cairo', sans-serif !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 10px 20px !important;
    }

    /* زر التلغرام العائم الاحترافي */
    .floating-tg-button {
        position: fixed;
        bottom: 30px;
        left: 30px;
        background: linear-gradient(135deg, #24A1DE 0%, #1d80b0 100%);
        color: white !important;
        padding: 14px 24px;
        border-radius: 50px;
        box-shadow: 0 8px 25px rgba(36, 161, 222, 0.4);
        z-index: 99999;
        font-family: 'Cairo', sans-serif;
        font-weight: 900;
        font-size: 0.95rem;
        text-decoration: none !important;
        display: flex;
        align-items: center;
        gap: 8px;
        animation: tg-bounce 2.5s infinite ease-in-out;
        border: 1px solid rgba(255,255,255,0.25);
    }
    @keyframes tg-bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-8px); }
    }
    
    /* التنسيق المتطور لكرت الجهاز العلوي (بدون حواف سفلية دائوية) */
    .device-top-card {
        background: rgba(30, 41, 59, 0.7) !important;
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px 14px 0 0 !important; /* دائرية فقط من الفوق */
        padding: 16px !important;
        margin-top: 15px !important;
        margin-bottom: 0px !important; /* إلغاء الهامش السفلي تماماً */
    }
    .card-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        width: 100%;
    }

    /* إلغاء الفجوة الافتراضية للأكسباندر ليلتحم هندسياً مع الكرت العلوي */
    div[data-testid="stExpander"] {
        background: rgba(30, 41, 59, 0.4) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-top: none !important; /* حذف الخط الفاصل العلوي */
        border-radius: 0 0 14px 14px !important; /* دائرية فقط من الأسفل */
        margin-top: 0px !important; /* صفر ديكالاج */
        margin-bottom: 15px !important;
        box-shadow: 0 8px 20px rgba(0,0,0,0.15) !important;
    }
    div[data-testid="stExpander"] details summary {
        padding: 10px 16px !important;
        direction: rtl !important;
        text-align: right !important;
    }
    div[data-testid="stExpander"] details summary span p {
        font-family: 'Cairo', sans-serif !important;
        font-weight: 700 !important;
        color: #3b82f6 !important;
        font-size: 0.95rem !important;
    }
    /* حماية المقاسات على الهواتف */
    @media (max-width: 600px) {
        .card-container {
            flex-direction: column-reverse;
            align-items: stretch;
            gap: 12px;
        }
        .status-badge { width: 100% !important; }
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<h3 style="text-align: right; font-family: \'Cairo\', sans-serif; color: #e2e8f0; font-size: 1.25rem; margin-bottom: 8px; font-weight:700;">🔍 تتبع حالة أجهزتك الآن:</h3>', unsafe_allow_html=True)

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
                
                # عرض الأجهزة المكتشفة داخل الكروت الزجاجية المدمجة
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
                                    <span style="color: #64748b; font-size: 0.85rem; font-family: 'Cairo';">تذكرة #{dev_id}</span>
                                    <h4 style="margin: 4px 0; color: #ffffff; font-family: 'Cairo'; font-weight:700;">{brand} - {model}</h4>
                                </div>
                                <div class="status-badge" style="background: {col_status}20; border: 1px solid {col_status}; color: {col_status}; padding: 6px 16px; border-radius: 8px; font-weight: bold; font-family: 'Cairo'; font-size: 0.9rem; text-align: center;">
                                    {status}
                                </div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # فتح الأكسباندر السفلي الملتصق بالكرت هندسياً
                    st.markdown('<div class="custom-expander">', unsafe_allow_html=True)
                    with st.expander("📄 عرض تفاصيل العطل والضمان المتقدم لهذا الجهاز"):
                        panne = dev.get("Panne", "غير محدد")
                        prix = dev.get("Prix", "0")
                        date_s = dev.get("Date_Sortie", "---")
                        w_stats = get_warranty_stats(date_s)
                        
                        st.markdown(f"""
                            <div style="text-align: right; direction: rtl; font-family: 'Cairo'; color: #cbd5e1;" dir="rtl">
                                📌 <b>العطل المشخص:</b> {panne}<br>
                                💰 <b>تكلفة الإصلاح:</b> <span style="color: #2ecc71; font-weight: bold;">{prix} دج</span><br>
                                📅 <b>تاريخ خروج الجهاز:</b> {date_s}<br>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        if w_stats:
                            st.write("🛡️ **حالة الضمان الفني للقطعة (30 يوم):**")
                            if w_stats["is_expired"]:
                                st.error(f"🔴 انتهى الضمان منذ {abs(w_stats['days_left'])} أيام (تاريخ الصلاحية: {w_stats['actual_date']})")
                            else:
                                st.success(f"🟢 الضمان ساري المفعول! متبقي {w_stats['days_left']} يوم (تنتهي الصلاحية: {w_stats['actual_date']})")
                                st.progress(w_stats["percent"])
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                raw_data = db_ref.get()
                if raw_data:
                    my_devices = [
                        dict(v, _id=k) for k, v in raw_data.items() 
                        if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])
                    ]
            
            if not my_devices:
                st.warning("⚠️ لم نجد أي جهاز مسجل بهذا الرقم حالياً في الورشة.")
            else:
                # زر التلغرام العائم للزبون الموثق
                bot_user = st.secrets.get("BOT_USERNAME", "InfoDoc_Workshop_Bot")
                st.markdown(f'''
                    <a href="https://t.me/{bot_user}?start={norm_phone}" target="_blank" class="floating-tg-button">
                        <i class="fa-brands fa-telegram" style="font-size:1.3rem;"></i>
                        <span>📢 تفعيل إشعارات الهاتف (Telegram)</span>
                    </a>
                ''', unsafe_allow_html=True)
            
                # ترتيب التذاكر تنازلياً
                my_devices.sort(key=lambda x: -int(x.get("ID", 0)) if str(x.get("ID", 0)).isdigit() else 0)
            
                for dev in my_devices:
                    status_raw = str(dev.get("Statut", "En Attente")).strip()
                    status_lower = status_raw.lower()
                    
                    # مصفوفة الحالات والألوان
                    if "prêt" in status_lower or "pret" in status_lower:
                        s_color, s_bg, s_text = "#22c55e", "rgba(34, 197, 94, 0.12)", "🟢 Prêt"
                    elif "réparable" in status_lower or "reparable" in status_lower:
                        s_color, s_bg, s_text = "#3b82f6", "rgba(59, 130, 246, 0.12)", "🔧 Réparable"
                    elif "annulé" in status_lower or "annule" in status_lower:
                        s_color, s_bg, s_text = "#ef4444", "rgba(239, 68, 68, 0.12)", "❌ Annulé"
                    elif "non réparable" in status_lower or "non reparable" in status_lower:
                        s_color, s_bg, s_text = "#f97316", "rgba(249, 115, 22, 0.12)", "⚠️ Non Réparable"
                    elif "en cours" in status_lower:
                        s_color, s_bg, s_text = "#06b6d4", "rgba(6, 182, 212, 0.12)", "⚙️ En Cours"
                    elif "en attente" in status_lower:
                        s_color, s_bg, s_text = "#eab308", "rgba(234, 179, 8, 0.12)", "🟡 En Attente"
                    elif any(keyword in status_lower for keyword in ["livré", "livre", "payé", "paye"]):
                        if any(dette_kw in status_lower for dette_kw in ["dette", "credit"]):
                            s_color, s_bg, s_text = "#a855f7", "rgba(168, 85, 247, 0.12)", "📦 Livré (Dette)"
                        else:
                            s_color, s_bg, s_text = "#10b981", "rgba(16, 185, 129, 0.12)", "✅ Livré & Payé"
                    else:
                        s_color, s_bg, s_text = "#94a3b8", "rgba(148, 163, 184, 0.12)", status_raw

                    # معالجة السعر الفخمة
                    raw_prix = dev.get('Prix', 0)
                    if "en cours" in status_lower or "en attente" in status_lower:
                        prix_html = '<span style="color: #94a3b8; font-size: 0.95rem; font-family: \'Cairo\'; font-weight: bold;">⚙️ قيد التشخيص...</span>'
                    else:
                        try:
                            formatted_p = f"{int(float(raw_prix)):,}".replace(',', ' ')
                            prix_html = f'<div style="display: inline-block; direction: ltr;"><span style="font-family: \'Orbitron\', sans-serif; font-size: 1.4rem; color: #facc15; font-weight: 900;">{formatted_p}</span> <span style="font-family: \'Cairo\', sans-serif; font-size: 0.9rem; color: #facc15; font-weight: 700;">DA</span></div>'
                        except: 
                            prix_html = '<div style="display: inline-block; direction: ltr;"><span style="font-family: \'Orbitron\', sans-serif; font-size: 1.4rem; color: #94a3b8; font-weight: 900;">0</span> <span style="font-family: \'Cairo\', sans-serif; font-size: 0.9rem; color: #94a3b8;">DA</span></div>'

                    # --- 1. طباعة الكرت العلوي للجهاز مباشرة ---
                    st.markdown(f"""
                        <div class="device-top-card" style="border-right: 5px solid {s_color} !important;">
                            <div class="card-container" dir="rtl">
                                <div class="status-badge" style="background: {s_bg}; border: 1px solid {s_color}; color: {s_color}; 
                                            padding: 8px 16px; border-radius: 8px; font-weight: 900; font-size: 0.95rem;
                                            min-width: 160px; text-align: center; flex-shrink: 0; box-sizing: border-box;">
                                    {s_text}
                                </div>
                                <div style="text-align: right; width: 100%; padding-right: 5px;">
                                    <h3 style="margin: 0; color: #ffffff; font-size: 1.3rem; font-weight: 900; font-family: 'Cairo', sans-serif;">{dev.get('Appareil', 'جهاز غير معروف')}</h3>
                                    <div style="color: #94a3b8; font-size: 0.85rem; font-family: 'Orbitron', sans-serif; margin-top: 3px; font-weight: bold;">TICKET: #{dev.get('ID', '0000')}</div>
                                </div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    # --- 2. فتح الأكسباندر الملتصق مباشرة بالأسفل بدون أي فراغ بايثون ميت ---
                    with st.expander("📄 عرض تفاصيل التقرير والمستحقات الفنية"):
                        
                        d_sortie = dev.get("Date_Sortie")
                        d_entree = dev.get("Date_Entree", "---")
                        panne_text = dev.get('Panne', dev.get('Defaut', 'غير مححدد'))
                        
                        warranty_html = ""
                        progress_html = ""
                        
                        # حساب وعرض نظام الضمان الفاخر
                        if ("livré" in status_lower or "livre" in status_lower or "payé" in status_lower) and d_sortie and str(d_sortie).strip() not in ["", "---", "None"]:
                            w = get_warranty_stats(d_sortie)
                            if w:
                                val = float(w.get('percent', 0)) 
                                is_expired = w.get('is_expired', False)
                                w_color = "#eab308" if not is_expired else "#64748b"
                                w_bg = "rgba(234, 179, 8, 0.06)" if not is_expired else "rgba(100, 116, 139, 0.06)"
                                w_status_txt = "🛡️ الضمان ساري المفعول" if not is_expired else "🛑 فترة الضمان انتهت"
                                
                                warranty_html = f"""
                                <div style="margin-bottom: 15px; border: 1px solid {w_color}; padding: 12px; border-radius: 10px; background: {w_bg}; direction: rtl; text-align: right;">
                                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center;">
                                        <span style="color: {w_color}; font-weight: bold; font-size: 0.9rem; font-family: 'Cairo';">{w_status_txt}</span>
                                        <div style="color: {w_color}; font-family: 'Orbitron', sans-serif; font-weight: 900; font-size: 1.2rem; direction: ltr;">{int(val)}%</div>
                                    </div>
                                    <div style="width: 100%; background: rgba(15, 23, 42, 0.6); border-radius: 10px; height: 6px; overflow: hidden; margin-bottom: 8px;">
                                        <div style="width: {val}%; background: {w_color}; height: 100%; border-radius: 10px;"></div>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; color: #94a3b8; font-size: 0.8rem; font-family: 'Cairo';">
                                        <span>📅 الاستلام: <b style="font-family: monospace; color:#e2e8f0;">{w.get('actual_date')}</b></span>
                                        <span>⏳ المتبقي: <b style="color:{w_color};">{w.get('days_left')} يوم</b></span>
                                    </div>
                                </div>
                                """
                        
                        # بناء شريط تقدم الصيانة
                        elif not any(x in status_lower for x in ["annulé", "annule", "non réparable", "non reparable", "prêt", "pret"]):
                            prog_map = {"en attente": 20, "en cours": 50, "réparable": 80}
                            p_val = prog_map.get(status_lower, 30)
                            
                            progress_html = f"""
                            <div style="margin-bottom: 15px; background: rgba(15, 23, 42, 0.3); padding: 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.03);">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 6px; align-items: center; direction: rtl;">
                                    <span style="color:#cbd5e1; font-size: 0.9rem; font-weight: bold; font-family: 'Cairo';">⚙️ تقدم العمل والمرحلة الحالية:</span>
                                    <div style="color:#3b82f6; font-weight: 900; font-family: 'Orbitron', sans-serif; font-size: 1.2rem; direction: ltr;">{p_val}%</div>
                                </div>
                                <div style="width: 100%; background: rgba(15, 23, 42, 0.6); border-radius: 10px; height: 6px; overflow: hidden;">
                                    <div style="width: {p_val}%; background: linear-gradient(90deg, #3b82f6, #06b6d4); height: 100%; border-radius: 10px;"></div>
                                </div>
                            </div>
                            """

                        # طباعة الجدول الداخلي المنسجم
                        st.markdown(f"""
                            <div style="padding: 5px 12px 12px 12px; font-family: 'Cairo', sans-serif; direction: rtl; text-align: right;">
                                {warranty_html}
                                {progress_html}
                                <table style="width:100%; direction: rtl; text-align: right; border-collapse: collapse; font-size: 0.95rem;">
                                    <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                                        <td style="padding: 8px 0; color: #94a3b8; font-weight: bold;"><i class="fa-solid fa-calendar-plus" style="margin-left:6px; color:#3b82f6;"></i> تاريخ الدخول:</td>
                                        <td style="text-align: left; color: #f1f5f9; font-family: 'Orbitron', sans-serif; font-weight: bold; direction: ltr;">{d_entree}</td>
                                    </tr>
                                    <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                                        <td style="padding: 8px 0; color: #94a3b8; font-weight: bold;"><i class="fa-solid fa-calendar-check" style="margin-left:6px; color:#22c55e;"></i> تاريخ الخروج:</td>
                                        <td style="text-align: left; color: #f1f5f9; font-family: 'Orbitron', sans-serif; font-weight: bold; direction: ltr;">{d_sortie if d_sortie else '---'}</td>
                                    </tr>
                                    <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                                        <td style="padding: 8px 0; color: #94a3b8; font-weight: bold;"><i class="fa-solid fa-microchip" style="margin-left:6px; color:#ef4444;"></i> العطل الفني المشخص:</td>
                                        <td style="text-align: left; color: #f87171; font-weight: bold; font-family: 'Cairo', sans-serif;">{panne_text}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 12px 0 0 0; color: #facc15; font-weight: 900; font-size: 1rem;"><i class="fa-solid fa-file-invoice-dollar" style="margin-left:6px;"></i> المستحقات الفنية:</td>
                                        <td style="text-align: left; padding-top: 12px;">{prix_html}</td>
                                    </tr>
                                </table>
                            </div>
                        """, unsafe_allow_html=True)
