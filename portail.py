import os
import threading
import re
from datetime import datetime
from io import BytesIO

import firebase_admin
from firebase_admin import credentials, db
import pandas as pd
import streamlit as st
import telebot
import qrcode

# --- 1. إعدادات الصفحة والتهيئة ---
st.set_page_config(
    page_title="InfoDoc - Client Portal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# دالة لتهيئة Firebase مرة واحدة فقط وبطريقة آمنة
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            cred_dict = dict(st.secrets["firebase"])
            if "\\n" in cred_dict["private_key"]:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
            return True
        except Exception as e:
            st.error(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")
            return False
    return True

firebase_ready = init_firebase()

# --- 2. المنطق البرمجي (Logic) ---
def normalize_phone(phone: str) -> str:
    """تنظيف وتوحيد أرقام الهواتف الجزائرية"""
    p = str(phone or "").replace(".0", "").strip()
    p = re.sub(r"\D", "", p) # إزالة أي حرف غير رقمي
    if p.startswith("213"): p = "0" + p[3:]
    if p.startswith("00213"): p = "0" + p[5:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]: p = "0" + p
    return p

@st.cache_data(ttl=60) # التخزين المؤقت للبيانات لمدة دقيقة لتقليل الضغط على Firebase
def fetch_all_data():
    try:
        ref = db.reference("atelier").get()
        return ref if ref else {}
    except:
        return {}

def get_customer_devices(phone_query: str):
    phone_query = normalize_phone(phone_query)
    if len(phone_query) < 9: return []
    
    all_data = fetch_all_data()
    last9 = phone_query[-9:]
    
    results = []
    for key, val in all_data.items():
        tel = normalize_phone(val.get("Telephone", ""))
        if tel.endswith(last9):
            val["_id"] = key
            results.append(val)
            
    # ترتيب من الأحدث إلى الأقدم بناءً على ID
    return sorted(results, key=lambda x: int(x.get("ID", 0)), reverse=True)

# --- 3. تصميم الواجهة (Custom CSS) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&family=Orbitron:wght@600;900&display=swap');
    
    :root {
        --primary: #58a6ff;
        --success: #3fb950;
        --danger: #f85149;
        --bg-card: #161b22;
        --border: #30363d;
    }

    .stApp { background-color: #010409; color: #adbac7; }
    
    /* Hero Section */
    .hero-container {
        background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
        border: 1px solid var(--border);
        border-radius: 15px;
        padding: 30px;
        margin-bottom: 25px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }
    
    .main-title { font-family: 'Orbitron', sans-serif; color: var(--primary); font-size: 2.5rem; letter-spacing: 2px; }
    
    /* Status Badges */
    .status-badge {
        padding: 6px 15px; border-radius: 20px; font-weight: bold; font-size: 0.8rem;
        text-transform: uppercase; border: 1px solid transparent;
    }
    .open { color: var(--success); border-color: var(--success); box-shadow: 0 0 10px rgba(63, 185, 80, 0.2); }
    .closed { color: var(--danger); border-color: var(--danger); }

    /* Device Card */
    .dev-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 12px;
        margin-bottom: 20px;
        transition: transform 0.3s ease;
    }
    .dev-card:hover { transform: translateY(-5px); border-color: var(--primary); }
    
    .card-header {
        background: rgba(88, 166, 255, 0.1);
        padding: 12px 20px;
        border-bottom: 1px solid var(--border);
        display: flex; justify-content: space-between; align-items: center;
    }

    /* Links */
    .contact-card {
        text-decoration: none; color: white !important;
        background: #21262d; padding: 10px; border-radius: 8px;
        display: flex; align-items: center; justify-content: center; gap: 8px;
        border: 1px solid var(--border); transition: 0.3s;
    }
    .contact-card:hover { background: #30363d; border-color: var(--primary); }
    
    /* Progress Bar */
    .progress-track { background: #21262d; border-radius: 10px; height: 10px; margin: 15px 0; overflow: hidden; }
    .progress-fill { height: 100%; transition: width 1s ease-in-out; }
    
    [data-testid="stExpander"] { border: 1px solid #d29922 !important; background: rgba(210, 153, 34, 0.05) !important; }
    </style>
""", unsafe_allow_html=True)

# --- 4. محتوى الصفحة ---
if firebase_ready:
    # الترويسة
    shop_open = db.reference("shop_settings/is_open").get()
    if shop_open is None: shop_open = True
    
    status_cls = "open" if shop_open else "closed"
    status_txt = "Atelier Ouvert" if shop_open else "Atelier Fermé"

    st.markdown(f"""
        <div class="hero-container">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div>
                    <div class="main-title">INFODOC <span style="color:white">TECH</span></div>
                    <p style="font-family: Cairo; color: #8b949e;">مركز الصيانة المعتمد - الشلف</p>
                </div>
                <div class="status-badge {status_cls}">{status_txt}</div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 20px;">
                <a href="tel:0798661900" class="contact-card">📞 0798661900</a>
                <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="contact-card">📍 الموقع</a>
                <a href="https://www.facebook.com/InfoDoc" target="_blank" class="contact-card">📘 Facebook</a>
            </div>
        </div>
    """, unsafe_allow_html=True)

    with st.expander("📝 شروط الصيانة والتسعير"):
        st.markdown("""
            <div style="direction: rtl; font-family: Cairo; text-align: right;">
                • فحص الجهاز (في حال عدم التصليح): <b>1000 دج</b><br>
                • صيانة البطاقة الأم تبدأ من: <b>3000 دج</b><br>
                • الموافقة التلقائية حتى 4000 دج. ما فوق ذلك يتم الاتصال بك.
            </div>
        """, unsafe_allow_html=True)

    # قسم التتبع
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("🔍 تتبع حالة جهازك")
        phone_input = st.text_input("أدخل رقم الهاتف المسجل به:", placeholder="0XXXXXXXXX", key="user_phone")
        
        if phone_input:
            devices = get_customer_devices(phone_input)
            if not devices:
                st.info("💡 لم يتم العثور على أجهزة مرتبطة بهذا الرقم.")
            else:
                for dev in devices:
                    stat = dev.get("Statut", "En attente")
                    prog = {"En attente": 20, "En Cours": 60, "Prêt": 100, "Livré": 100}.get(stat, 10)
                    color = "#3fb950" if stat in ["Prêt", "Livré"] else "#58a6ff"
                    
                    st.markdown(f"""
                        <div class="dev-card">
                            <div class="card-header">
                                <span style="font-family: Orbitron; font-weight: bold;">#{dev.get('ID', '0')}</span>
                                <span style="font-weight: bold; color: {color}">{stat}</span>
                            </div>
                            <div style="padding: 20px;">
                                <h3 style="margin:0; color: white;">{dev.get('Appareil', 'Device')}</h3>
                                <div style="display: flex; gap: 20px; margin-top: 10px; font-size: 0.9rem; color: #8b949e;">
                                    <span>🛠️ {dev.get('Panne', '---')}</span>
                                    <span>💰 {dev.get('Prix', '0')} DZD</span>
                                </div>
                                <div class="progress-track">
                                    <div class="progress-fill" style="width: {prog}%; background: {color};"></div>
                                </div>
                                <small>📅 تاريخ الدخول: {dev.get('Date_Entree', '---')}</small>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

    with col_right:
        st.subheader("🤖 إشعارات تليغرام")
        if phone_input and len(normalize_phone(phone_input)) >= 9:
            clean_p = normalize_phone(phone_input)
            tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={clean_p}"
            
            # توليد QR Code
            qr = qrcode.QRCode(box_size=10, border=2)
            qr.add_data(tg_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="white", back_color="#0d1117")
            
            buf = BytesIO()
            img.save(buf, format="PNG")
            
            st.image(buf.getvalue(), caption="امسح الكود للتفعيل", width=200)
            st.link_button("🚀 تفعيل الإشعارات", tg_url, use_container_width=True)
        else:
            st.warning("يرجى إدخال رقم الهاتف أولاً لتفعيل الإشعارات.")

# --- 5. بوت التليغرام (في خيط منفصل) ---
def start_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return
    
    bot = telebot.TeleBot(token)

    @bot.message_handler(commands=['start'])
    def handle_start(message):
        text = message.text.split()
        if len(text) > 1:
            phone = normalize_phone(text[1])
            # تحديث معرف التليغرام في قاعدة البيانات لكل الأجهزة المرتبطة بهذا الرقم
            all_data = db.reference("atelier").get()
            if all_data:
                for k, v in all_data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(phone[-9:]):
                        db.reference(f"atelier/{k}").update({"Telegram_ID": message.chat.id})
                bot.reply_to(message, "✅ ممتاز! تم ربط حسابك. ستصلك رسالة هنا بمجرد جاهزية جهازك.")
        else:
            bot.reply_to(message, "مرحباً بك في InfoDoc! يرجى الدخول عبر الموقع لربط جهازك.")

    bot.infinity_polling()

if "bot_started" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_started"] = True
