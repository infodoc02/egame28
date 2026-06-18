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
import uuid

# ==============================================================================
# 1. إعدادات الصفحة الأساسية ونظام المظهر الفاخر
# ==============================================================================
st.set_page_config(
    page_title="InfoDoc - عالم الصيانة الاحترافي",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==============================================================================
# 2. الاتصال الآمن بقاعدة البيانات
# ==============================================================================
@st.cache_resource
def init_db():
    """ربط التطبيق بـ Firebase مع معالجة حماية الانهيار"""
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
                st.warning("⚠️ Mode local/limité activé (Secrets non configured).")
                return False
        except Exception as e:
            st.error(f"❌ Erreur connexion Firebase: {e}")
            return False
    return True

db_status = init_db()

# ==============================================================================
# 3. الدوال المساعدة
# ==============================================================================
def normalize_phone(phone: str) -> str:
    """تنسيق وتوحيد رقم الهاتف الجزائري"""
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
    """حساب وضمان الأجهزة المستلمة"""
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
    """تحديد أولوية الفرز"""
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
    else: 
        return 99

def render_hero_logo():
    """جلب اللوغو"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(current_dir, "ico.ico")
    
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as f:
                data = f.read()
                encoded = base64.b64encode(data).decode()
            return f'<img src="data:image/x-icon;base64,{encoded}" class="hero-logo-animated">'
        except:
            pass
            
    return '<div class="hero-logo-animated" style="font-size: 4rem; display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">🛠️</div>'

@st.cache_resource
def start_telegram_bot():
    """بوت التلغرام"""
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
                                "✅ *تم ربط حسابك بنجاح!*\n\n"
                                "📦 *الأجهزة المرتبطة:*\n"
                                f"{devices_list_str}\n\n"
                                "⏱️ _شكراً لثقتكم في خدماتنا._"
                            )
                            bot.reply_to(m, success_msg)
                        else:
                            error_msg = "❌ *خطأ في عملية الربط*\n\nعذراً، لم نجد أي جهاز مسجل برقم الهاتف هذا."
                            bot.reply_to(m, error_msg)
                    else:
                        bot.reply_to(m, "⚠️ قاعدة البيانات فارغة حالياً.")
                else:
                    welcome_msg = (
                        "👋 *مرحباً بك في بوت ورشة InfoDoc!*\n\n"
                        "هذا البوت مخصص لإرسال إشعارات تلقائية لتتبع حالة أجهزتك.\n\n"
                        "ℹ️ *كيفية التفعيل:*\n"
                        "1️⃣ اذهب إلى موقعنا الإلكتروني\n"
                        "2️⃣ قم بتسجيل حسابك برقم هاتفك\n"
                        "3️⃣ سيظهر لك زر التفعيل"
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
# 4. إدارة الحالة (State Management)
# ==============================================================================
if "page" not in st.session_state:
    st.session_state["page"] = "login"  # login, register, dashboard
if "user_phone" not in st.session_state:
    st.session_state["user_phone"] = ""
if "user_telegram_id" not in st.session_state:
    st.session_state["user_telegram_id"] = ""
if "auth_step" not in st.session_state:
    st.session_state["auth_step"] = "input_phone"
if "generated_otp" not in st.session_state:
    st.session_state["generated_otp"] = None
if "visitor_tracked" not in st.session_state and db_status:
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
# 5. أنماط CSS والتصميم
# ==============================================================================
st.markdown("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
""", unsafe_allow_html=True)

st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #1e1b4b 100%);
        background-attachment: fixed;
    }
    
    [data-testid="stVerticalBlock"] { padding-top: 1rem !important; }
    
    /* الأزرار المحسنة */
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

    /* Hero Container */
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

    /* نموذج الإدخال */
    div[data-testid="stTextInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stSelectbox"] {
        direction: rtl !important;
        text-align: right !important;
        font-family: 'Cairo', sans-serif !important;
        color: #f1f5f9 !important;
        background-color: rgba(15, 23, 42, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 10px !important;
    }

    /* بطاقات الأجهزة */
    .device-card {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 12px;
        transition: all 0.3s ease;
    }

    .device-card:hover {
        border-color: rgba(59, 130, 246, 0.5);
        box-shadow: 0 8px 20px rgba(59, 130, 246, 0.15);
    }

    /* بطاقات العروض */
    .offer-card {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
        border: 1px solid rgba(139, 92, 246, 0.3);
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
        position: relative;
        overflow: hidden;
    }

    .offer-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 100%);
    }

    .offer-badge {
        display: inline-block;
        background: linear-gradient(90deg, #ec4899 0%, #f43f5e 100%);
        color: white;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: bold;
        margin-bottom: 12px;
    }

    /* نموذج إضافة جهاز */
    .form-card {
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
    }

    .form-section-title {
        color: #3b82f6;
        font-family: 'Cairo', sans-serif;
        font-size: 1.1rem;
        font-weight: 700;
        margin-top: 16px;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 2px solid rgba(59, 130, 246, 0.3);
    }

    /* شريط التبويبات */
    .tabs-container {
        display: flex;
        gap: 8px;
        margin-bottom: 20px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        overflow-x: auto;
        padding-bottom: 12px;
    }

    .tab-button {
        padding: 10px 20px;
        border-radius: 8px;
        border: none;
        background: rgba(255, 255, 255, 0.05);
        color: #94a3b8;
        cursor: pointer;
        font-family: 'Cairo', sans-serif;
        font-weight: 600;
        transition: all 0.3s ease;
        white-space: nowrap;
    }

    .tab-button:hover {
        background: rgba(255, 255, 255, 0.1);
    }

    .tab-button.active {
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
        color: white;
    }

    /* الشارات */
    .badge-success {
        background: rgba(46, 204, 113, 0.15);
        border: 1px solid #2ecc71;
        color: #2ecc71;
        padding: 8px 14px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 0.85rem;
    }

    .badge-warning {
        background: rgba(230, 126, 34, 0.15);
        border: 1px solid #e67e22;
        color: #e67e22;
        padding: 8px 14px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 0.85rem;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. واجهة تسجيل الدخول والتسجيل
# ==============================================================================
def render_login_register():
    """واجهة تسجيل الدخول والتسجيل"""
    
    logo_html = render_hero_logo()
    header_html = f"""<div class="hero-container" dir="rtl">
    {logo_html}
    <div class="hero-subtitle" style="margin-bottom: 15px; margin-top: 10px;">
    🛠️ منصة InfoDoc الإلكترونية الاحترافية
    </div>
    <p style="color: #cbd5e1; font-family: 'Cairo'; margin: 0;">
    تتبع أجهزتك وتخطيط صيانتك بسهولة واحترافية
    </p>
    </div>"""
    
    st.markdown(header_html, unsafe_allow_html=True)
    
    # تبويبات الدخول والتسجيل
    tab1, tab2 = st.tabs(["🔑 دخول", "✨ تسجيل جديد"])
    
    with tab1:
        st.markdown('<h3 style="text-align: right; font-family: \'Cairo\'; color: #e2e8f0;">أهلاً بك مجدداً</h3>', unsafe_allow_html=True)
        
        login_phone = st.text_input(
            "",
            placeholder="أدخل رقم الهاتف (مثال: 0798661900)",
            key="login_phone",
            label_visibility="collapsed"
        )
        
        if st.button("🚀 الدخول إلى حسابي", use_container_width=True):
            if login_phone:
                norm_phone = normalize_phone(login_phone)
                if len(norm_phone) < 9:
                    st.error("⚠️ رقم هاتف غير صحيح")
                else:
                    st.session_state["user_phone"] = norm_phone
                    st.session_state["auth_step"] = "verify_otp"
                    st.session_state["page"] = "auth"
                    st.rerun()
            else:
                st.error("❌ الرجاء إدخال رقم الهاتف")
    
    with tab2:
        st.markdown('<h3 style="text-align: right; font-family: \'Cairo\'; color: #e2e8f0;">إنشاء حساب جديد</h3>', unsafe_allow_html=True)
        
        register_phone = st.text_input(
            "",
            placeholder="أدخل رقم الهاتف (مثال: 0798661900)",
            key="register_phone",
            label_visibility="collapsed"
        )
        
        register_telegram_username = st.text_input(
            "",
            placeholder="اسم حسابك في التلغرام (بدون @)",
            key="register_telegram",
            label_visibility="collapsed"
        )
        
        if st.button("✅ إنشاء حسابي", use_container_width=True):
            if register_phone and register_telegram_username:
                norm_phone = normalize_phone(register_phone)
                if len(norm_phone) < 9:
                    st.error("⚠️ رقم هاتف غير صحيح")
                else:
                    # حفظ بيانات المستخدم الجديد
                    try:
                        user_id = str(uuid.uuid4())[:8]
                        users_ref = db.reference("users")
                        users_ref.child(norm_phone).set({
                            "phone": norm_phone,
                            "telegram_username": register_telegram_username,
                            "created_at": datetime.now(pytz.timezone('Africa/Algiers')).isoformat(),
                            "user_id": user_id
                        })
                        
                        st.session_state["user_phone"] = norm_phone
                        st.session_state["user_telegram_id"] = register_telegram_username
                        st.session_state["page"] = "auth"
                        st.session_state["auth_step"] = "verify_otp_new"
                        st.success("✅ تم إنشاء الحساب بنجاح!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ حدث خطأ: {str(e)}")
            else:
                st.error("❌ الرجاء ملء جميع الحقول")

# ==============================================================================
# 7. واجهة التحقق بـ OTP
# ==============================================================================
def render_otp_verification():
    """واجهة التحقق بـ OTP"""
    
    st.markdown(f"""
    <div style="background: rgba(30, 41, 59, 0.5); border: 1px dashed #3b82f6; padding: 20px; 
                border-radius: 16px; text-align: center; margin-bottom: 20px; direction: rtl;">
        <h4 style="color: #3b82f6; font-family: 'Cairo'; margin-top:0;">🔐 التحقق ثنائي الخطوات</h4>
        <p style="color: #94a3b8; font-family: 'Cairo';">
        سيتم إرسال كود التحقق إلى حساب التلغرام الخاص بك
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("📱 إرسال كود التحقق عبر التلغرام"):
        with st.spinner("⏳ جارٍ إرسال الكود..."):
            otp_code = str(random.randint(1000, 9999))
            st.session_state["generated_otp"] = otp_code
            
            bot = st.session_state.get("bot_instance")
            if bot:
                try:
                    # هنا يتم إرسال الكود إلى التلغرام
                    st.success("✅ تم إرسال الكود!")
                    st.session_state["auth_step"] = "confirm_otp"
                    st.rerun()
                except:
                    st.error("❌ فشل الإرسال، حاول لاحقاً")
    
    if st.session_state.get("auth_step") == "confirm_otp":
        entered_otp = st.text_input(
            "",
            placeholder="أدخل الكود المؤلف من 4 أرقام",
            key="otp_input",
            label_visibility="collapsed"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ تأكيد"):
                if entered_otp == st.session_state["generated_otp"]:
                    st.session_state["page"] = "dashboard"
                    st.rerun()
                else:
                    st.error("❌ كود غير صحيح")
        
        with col2:
            if st.button("⬅️ رجوع"):
                st.session_state["page"] = "login"
                st.rerun()

# ==============================================================================
# 8. لوحة التحكم الرئيسية
# ==============================================================================
def render_dashboard():
    """واجهة لوحة التحكم الرئيسية مع التبويبات"""
    
    user_phone = st.session_state.get("user_phone", "")
    
    # Header المستخدم
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        st.markdown(f"""
        <div style="color: #e2e8f0; font-family: 'Cairo'; font-size: 1.1rem;">
        <strong>👋 أهلاً بك</strong><br>
        <span style="color: #94a3b8; font-size: 0.95rem;">{user_phone}</span>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        if st.button("🚪 خروج"):
            st.session_state["page"] = "login"
            st.session_state["user_phone"] = ""
            st.rerun()
    
    st.divider()
    
    # التبويبات الرئيسية
    st.markdown('<h3 style="text-align: right; font-family: \'Cairo\'; color: #e2e8f0; margin-top: 20px;">📊 لوحة التحكم</h3>', unsafe_allow_html=True)
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 أجهزتي",
        "➕ إضافة جهاز جديد",
        "🎉 العروض والتخفيفات",
        "ℹ️ الشروط والملاحظات"
    ])
    
    # التبويب 1: أجهزتي
    with tab1:
        render_my_devices(user_phone)
    
    # التبويب 2: إضافة جهاز
    with tab2:
        render_add_device(user_phone)
    
    # التبويب 3: العروض والتخفيفات
    with tab3:
        render_offers()
    
    # التبويب 4: الشروط والملاحظات
    with tab4:
        render_terms_conditions()

def render_my_devices(user_phone):
    """عرض أجهزة المستخدم"""
    st.markdown('<h4 style="text-align: right; font-family: \'Cairo\'; color: #2ecc71;">🔧 الأجهزة المسجلة لديك</h4>', unsafe_allow_html=True)
    
    with st.spinner("⏳ جارٍ تحميل الأجهزة..."):
        try:
            db_ref = db.reference("atelier")
            all_data = db_ref.get()
            devices = []
            
            if all_data:
                for k, v in all_data.items():
                    db_phone = normalize_phone(v.get("Telephone", ""))
                    if db_phone.endswith(user_phone[-9:]):
                        devices.append(dict(v, _id=k))
            
            if not devices:
                st.info("📭 لا توجد أجهزة مسجلة حالياً. قم بإضافة جهاز جديد من التبويب التالي.")
            else:
                devices.sort(key=lambda x: get_status_priority(x.get("Statut", "")))
                
                for dev in devices:
                    render_device_card(dev)
        except Exception as e:
            st.error(f"❌ خطأ في تحميل الأجهزة: {str(e)}")

def render_device_card(device):
    """بطاقة جهاز واحد"""
    dev_id = device.get("ID", "0000")
    brand = device.get("Marque", "")
    model = device.get("Appareil", "جهاز غير معروف")
    status = device.get("Statut", "في الانتظار")
    fault = device.get("Panne", "غير محدد")
    price = device.get("Prix", "0")
    entry_date = device.get("Date_Entree", "---")
    exit_date = device.get("Date_Sortie", "---")
    
    w_stats = get_warranty_stats(exit_date)
    
    # تحديد اللون حسب الحالة
    status_colors = {
        "prêt": "#2ecc71",
        "en cours": "#f1c40f",
        "en attente": "#e67e22",
        "annulé": "#e74c3c"
    }
    status_color = status_colors.get(status.lower(), "#3498db")
    
    st.markdown(f"""
    <div class="device-card" dir="rtl">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
            <div>
                <h5 style="margin: 0; color: #e2e8f0; font-family: 'Cairo';">{brand} - {model}</h5>
                <span style="color: #94a3b8; font-size: 0.85rem;">تذكرة #{dev_id}</span>
            </div>
            <span style="background: {status_color}20; border: 1px solid {status_color}; color: {status_color}; 
                        padding: 6px 14px; border-radius: 8px; font-weight: bold; font-family: 'Cairo';">{status}</span>
        </div>
        
        <div style="color: #cbd5e1; font-family: 'Cairo'; font-size: 0.95rem; line-height: 1.8; text-align: right;">
            <div>📌 <strong>العطل:</strong> {fault}</div>
            <div>💰 <strong>السعر:</strong> <span style="color: #2ecc71; font-weight: bold;">{price} دج</span></div>
            <div>📅 <strong>الاستلام:</strong> {entry_date}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_add_device(user_phone):
    """نموذج إضافة جهاز احترافي"""
    st.markdown('<h4 style="text-align: right; font-family: \'Cairo\'; color: #3b82f6;">🆕 إضافة جهاز للصيانة</h4>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="form-card" dir="rtl">
    <p style="color: #cbd5e1; font-family: 'Cairo'; text-align: right;">
    🔍 <strong>نموذج الإبلاغ عن جهاز جديد</strong><br>
    <span style="font-size: 0.9rem; color: #94a3b8;">
    الرجاء ملء التفاصيل أدناه. سيتم التواصل معك قريباً للتأكيد والبدء بالصيانة.
    </span>
    </p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("add_device_form", clear_on_submit=True):
        # المعلومات الأساسية
        st.markdown('<div class="form-section-title">📱 معلومات الجهاز</div>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            brand = st.text_input("العلامة التجارية*", placeholder="Samsung, Apple, Asus...")
        with col2:
            model = st.text_input("موديل الجهاز*", placeholder="Galaxy A51, iPhone 12...")
        
        col1, col2 = st.columns(2)
        with col1:
            device_type = st.selectbox(
                "نوع الجهاز*",
                ["هاتف ذكي", "لابتوب", "حاسوب مكتبي", "تابلت", "ساعة ذكية", "أخرى"]
            )
        with col2:
            year = st.number_input("سنة الصنع", min_value=2000, max_value=2025, value=2023)
        
        # وصف العطل
        st.markdown('<div class="form-section-title">🔧 وصف المشكلة</div>', unsafe_allow_html=True)
        
        fault_description = st.text_area(
            "اشرح المشكلة التي تواجهها*",
            placeholder="مثال: الشاشة مكسورة، البطارية لا تشتغل، يسخن كثيراً...",
            height=100
        )
        
        col1, col2 = st.columns(2)
        with col1:
            is_urgent = st.checkbox("✨ حالة عاجلة / أولوية عالية")
        with col2:
            has_warranty = st.checkbox("🛡️ لديه ضمان من الشركة")
        
        # معلومات إضافية
        st.markdown('<div class="form-section-title">📋 معلومات إضافية</div>', unsafe_allow_html=True)
        
        additional_notes = st.text_area(
            "ملاحظات إضافية (اختيارية)",
            placeholder="معلومات أخرى تود أن تشاركها معنا...",
            height=60
        )
        
        # قبول الشروط
        st.markdown('<div style="background: rgba(139, 92, 246, 0.1); border: 1px solid rgba(139, 92, 246, 0.3); padding: 12px; border-radius: 8px; margin-top: 16px; margin-bottom: 16px;" dir="rtl"><span style="color: #cbd5e1; font-family: \'Cairo\'; font-size: 0.9rem;"><input type="checkbox" id="terms"> <label for="terms">أوافق على الشروط والأحكام الخاصة بالصيانة</label></span></div>', unsafe_allow_html=True)
        
        submitted = st.form_submit_button("✅ تقديم طلب الصيانة", use_container_width=True)
        
        if submitted:
            if brand and model and fault_description:
                try:
                    # حفظ الطلب الجديد
                    device_id = str(uuid.uuid4())[:6]
                    device_ref = db.reference("device_requests")
                    device_ref.child(device_id).set({
                        "device_id": device_id,
                        "customer_phone": user_phone,
                        "brand": brand,
                        "model": model,
                        "device_type": device_type,
                        "year": year,
                        "fault_description": fault_description,
                        "is_urgent": is_urgent,
                        "has_warranty": has_warranty,
                        "additional_notes": additional_notes,
                        "created_at": datetime.now(pytz.timezone('Africa/Algiers')).isoformat(),
                        "status": "pending"
                    })
                    
                    st.success(f"✅ تم تقديم الطلب بنجاح! رقم الطلب: {device_id}\n📞 سيتم التواصل معك قريباً")
                except Exception as e:
                    st.error(f"❌ حدث خطأ: {str(e)}")
            else:
                st.error("❌ الرجاء ملء الحقول المرجحة (*)")

def render_offers():
    """تبويب العروض والتخفيفات"""
    st.markdown('<h4 style="text-align: right; font-family: \'Cairo\'; color: #ec4899;">🎉 العروض والتخفيفات الحصرية</h4>', unsafe_allow_html=True)
    
    # عرض 1
    st.markdown("""
    <div class="offer-card" dir="rtl">
        <span class="offer-badge">🔥 عرض ساخن</span>
        <h5 style="margin-top: 0; color: #e2e8f0; font-family: 'Cairo';">تخفيف 20% على صيانة البطاريات</h5>
        <p style="color: #cbd5e1; font-family: 'Cairo'; margin: 8px 0;">
        استمتع بخصم 20% على جميع خدمات استبدال وإصلاح البطاريات لجميع الأجهزة.
        </p>
        <p style="color: #2ecc71; font-weight: bold; font-family: 'Cairo';">
        ⏰ العرض ساري حتى نهاية الشهر الجاري
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # عرض 2
    st.markdown("""
    <div class="offer-card" dir="rtl">
        <span class="offer-badge" style="background: linear-gradient(90deg, #3b82f6 0%, #0ea5e9 100%);">💎 عرض VIP</span>
        <h5 style="margin-top: 0; color: #e2e8f0; font-family: 'Cairo';">صيانة شاملة بسعر خاص</h5>
        <p style="color: #cbd5e1; font-family: 'Cairo'; margin: 8px 0;">
        احصل على فحص شامل مجاني + تنظيف عميق + تطبيق حماية حرارية بسعر واحد فقط.
        </p>
        <p style="color: #3b82f6; font-weight: bold; font-family: 'Cairo';">
        💰 2500 دج فقط بدلاً من 3500 دج
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # عرض 3
    st.markdown("""
    <div class="offer-card" dir="rtl">
        <span class="offer-badge" style="background: linear-gradient(90deg, #10b981 0%, #059669 100%);">🎁 هدية مع كل صيانة</span>
        <h5 style="margin-top: 0; color: #e2e8f0; font-family: 'Cairo';">أكسسوارات مجانية مع طلبك</h5>
        <p style="color: #cbd5e1; font-family: 'Cairo'; margin: 8px 0;">
        كل جهاز يتم فحصه يحصل على تغليفة حماية أو شاحن بسيط مجاني.
        </p>
        <p style="color: #10b981; font-weight: bold; font-family: 'Cairo';">
        ✨ بدون شروط إضافية
        </p>
    </div>
    """, unsafe_allow_html=True)

def render_terms_conditions():
    """شروط وملاحظات الصيانة"""
    st.markdown("""
    <style>
    @keyframes gold-glow {
        0%, 100% { box-shadow: 0 4px 10px rgba(234, 179, 8, 0.15); }
        50% { box-shadow: 0 4px 20px rgba(250, 204, 21, 0.3); }
    }
    .rule-card {
        background: rgba(30, 41, 59, 0.6);
        border-left: 4px solid #eab308;
        padding: 16px;
        margin-bottom: 12px;
        border-radius: 8px;
        color: #e2e8f0;
        line-height: 1.7;
        text-align: right;
        direction: rtl;
        font-family: 'Cairo', sans-serif;
    }
    </style>
    <h4 style="text-align: right; font-family: 'Cairo'; color: #eab308;">⚠️ شروط وملاحظات مهمة</h4>
    <div class="rule-card">
    <strong>1️⃣ رسوم الفحص:</strong> إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<strong>رفض الزبون</strong> ذلك، يتم دفع <strong>1000 دج</strong> ثمن الفحص.
    </div>
    <div class="rule-card">
    <strong>2️⃣ أسعار المكونات الدقيقة:</strong> أسعار البطاقة الأم والمكونات الإلكترونية تبدأ من <strong>3000 دج</strong>.
    </div>
    <div class="rule-card">
    <strong>3️⃣ خدمات البرمجة:</strong> خدمات الفلاش والبيوس تبدأ من <strong>1500 دج</strong>.
    </div>
    <div class="rule-card">
    <strong>4️⃣ الموافقة التلقائية:</strong> نقوم بالإصلاح مباشرة للتكاليف بين <strong>3000-4000 دج</strong> بدون الاتصال.
    </div>
    <div class="rule-card">
    <strong>5️⃣ الضمان:</strong> ضمان <strong>30 يوماً</strong> على العيب الإلكتروني المُصلح فقط.
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 9. منطق التوجيه الرئيسي
# ==============================================================================
if not db_status:
    st.error("❌ عذراً، لا يمكن الاتصال بقاعدة البيانات حالياً.")
    st.stop()

if st.session_state.get("page") == "login":
    render_login_register()
elif st.session_state.get("page") == "auth":
    render_otp_verification()
elif st.session_state.get("page") == "dashboard":
    render_dashboard()
