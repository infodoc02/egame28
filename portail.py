import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime, timedelta
import threading
import telebot
from io import BytesIO

# --- 1. إعدادات الصفحة والأيقونة ---
st.set_page_config(page_title="InfoDoc Client Portal", page_icon="📱", layout="wide")

# --- 2. تهيئة Firebase ---
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
        except: return False
    return True

init_firebase()

# --- 3. الدوال المنطقية ---
def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if p.startswith("213"): p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]: p = "0" + p
    return p

def get_warranty_status(date_sortie_str):
    """حساب حالة الضمان بناءً على تاريخ الخروج (شهر واحد)"""
    if not date_sortie_str or date_sortie_str == "---":
        return "لا يوجد تاريخ خروج", False
    try:
        date_sortie = datetime.strptime(date_sortie_str, "%Y-%m-%d")
        expiry_date = date_sortie + timedelta(days=30)
        is_expired = datetime.now() > expiry_date
        return expiry_date.strftime("%Y-%m-%d"), is_expired
    except:
        return "تاريخ غير صالح", False

# --- 4. التصميم (CSS الاحترافي) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700&display=swap');
    
    .stApp { background: #0d1117; color: #c9d1d9; }
    
    /* تأثير الوماض */
    @keyframes blink-green { 0% { opacity: 1; box-shadow: 0 0 10px #238636; } 50% { opacity: 0.5; box-shadow: none; } 100% { opacity: 1; box-shadow: 0 0 10px #238636; } }
    @keyframes blink-red { 0% { opacity: 1; box-shadow: 0 0 10px #f85149; } 50% { opacity: 0.5; box-shadow: none; } 100% { opacity: 1; box-shadow: 0 0 10px #f85149; } }
    
    .status-online { color: #3fb950; border: 2px solid #238636; padding: 5px 15px; border-radius: 50px; animation: blink-green 1.5s infinite; font-weight: bold; }
    .status-offline { color: #f85149; border: 2px solid #f85149; padding: 5px 15px; border-radius: 50px; animation: blink-red 1.5s infinite; font-weight: bold; }

    /* أزرار التواصل */
    .contact-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-top: 15px; }
    .social-btn {
        text-decoration: none; color: white !important; background: rgba(255,255,255,0.05);
        border: 1px solid #30363d; padding: 12px; border-radius: 12px; text-align: center;
        transition: 0.3s; font-family: 'Cairo'; font-weight: 700;
    }
    .social-btn:hover { background: #1f6feb; border-color: #58a6ff; transform: translateY(-3px); }

    /* بطاقة الجهاز */
    .device-card {
        background: #161b22; border: 1px solid #30363d; border-radius: 16px; padding: 20px;
        margin-bottom: 20px; position: relative; overflow: hidden;
    }
    .status-100 { border-left: 5px solid #3fb950; }
    
    /* الضمان المشطب */
    .warranty-expired { text-decoration: line-through; color: #f85149 !important; opacity: 0.6; }
    .warranty-active { color: #3fb950 !important; font-weight: bold; }

    .greeting-text { font-family: 'Cairo'; font-size: 1.2rem; color: #8b949e; margin-bottom: 5px; }
    .time-badge { background: #21262d; padding: 2px 10px; border-radius: 5px; font-family: monospace; }
    </style>
""", unsafe_allow_html=True)

# --- 5. الهيدر والترحيب ---
now = datetime.now()
greeting = "صباح الخير ☀️" if now.hour < 12 else "مساء الخير 🌙"
time_str = now.strftime("%H:%M")

col_h1, col_h2 = st.columns([2, 1])
with col_h1:
    st.markdown(f"<div class='greeting-text'>{greeting} زبوننا الكريم في <b>InfoDoc</b></div>", unsafe_allow_html=True)
    st.markdown(f"الوقت الحالي في الشلف: <span class='time-badge'>{time_str}</span>", unsafe_allow_html=True)

with col_h2:
    try:
        is_open = db.reference("shop_settings/is_open").get()
    except: is_open = True
    status_class = "status-online" if is_open else "status-offline"
    status_label = "ATELIER OUVERT" if is_open else "ATELIER FERMÉ"
    st.markdown(f"<div style='text-align:right'><span class='{status_class}'>{status_label}</span></div>", unsafe_allow_html=True)

st.markdown("<h1 style='font-family:Orbitron; color:#58a6ff; margin-bottom:0;'>INFODOC TECHNOLOGY</h1>", unsafe_allow_html=True)

# أزرار التواصل الاحترافية
st.markdown(f"""
    <div class="contact-grid">
        <a href="tel:0798661900" class="social-btn">📞 0798661900</a>
        <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="social-btn">📍 الموقع</a>
        <a href="https://www.facebook.com/InfoDoc" target="_blank" class="social-btn">📘 فيسبوك</a>
        <a href="https://www.tiktok.com/@infodoc02" target="_blank" class="social-btn">📱 تيك توك</a>
    </div>
""", unsafe_allow_html=True)

st.divider()

# --- 6. البحث والتتبع ---
st.markdown("### 🔍 تتبع حالة جهازك")
search_col1, search_col2 = st.columns([2, 1])

with search_col1:
    phone_input = st.text_input("أدخل رقم هاتفك المسجل:", placeholder="07XXXXXXXX")

if phone_input:
    phone_n = normalize_phone(phone_input)
    if len(phone_n) >= 9:
        # جلب البيانات من Firebase
        raw_data = db.reference("atelier").get()
        if raw_data:
            # تصفية الأجهزة المرتبطة بالرقم
            my_devices = []
            for k, v in raw_data.items():
                if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:]):
                    v["_id"] = k
                    my_devices.append(v)
            
            if not my_devices:
                st.info("لم نجد أجهزة مرتبطة بهذا الرقم.")
            else:
                for dev in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    # منطق الحالة والنسبة المئوية
                    statut = str(dev.get("Statut", "")).upper()
                    
                    if statut == "LIVRE ET PAYE":
                        prog = 100
                        color = "#3fb950"
                        special_class = "status-100"
                    elif statut == "PRET":
                        prog = 100
                        color = "#58a6ff"
                        special_class = "status-100"
                    elif statut == "REPARABLE":
                        prog = 66
                        color = "#d29922"
                        special_class = ""
                    elif statut == "ENCOURS":
                        prog = 33
                        color = "#1f6feb"
                        special_class = ""
                    else: # EN ATTENTE
                        prog = 0
                        color = "#8b949e"
                        special_class = ""

                    # منطق الضمان
                    expiry_date, is_expired = get_warranty_status(dev.get("Date_Sortie"))
                    warranty_style = "warranty-expired" if is_expired else "warranty-active"
                    warranty_text = f"ينتهي في: {expiry_date}" if not is_expired else f"منتهي ({expiry_date})"

                    # تصميم البطاقة
                    with st.container():
                        st.markdown(f"""
                            <div class="device-card {special_class}">
                                <div style="display:flex; justify-content:space-between">
                                    <span style="font-family:Orbitron; color:#58a6ff">#{dev.get('ID')} | {dev.get('Appareil')}</span>
                                    <span style="background:{color}; color:white; padding:2px 10px; border-radius:5px; font-size:0.8rem">{statut}</span>
                                </div>
                                <div style="margin:15px 0">
                                    <div style="display:flex; justify-content:space-between; font-size:0.8rem; color:#8b949e">
                                        <span>التقدم: {prog}%</span>
                                        <span>المشكلة: {dev.get('Panne')}</span>
                                    </div>
                                    <div style="background:#21262d; height:8px; border-radius:10px; margin-top:5px">
                                        <div style="background:{color}; width:{prog}%; height:100%; border-radius:10px"></div>
                                    </div>
                                </div>
                                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; font-size:0.9rem">
                                    <div>📅 دخول: {dev.get('Date_Entree')}</div>
                                    <div>💰 السعر: {dev.get('Prix')} دج</div>
                                    <div class="{warranty_style}">🛡️ الضمان: {warranty_text}</div>
                                    <div style="color:#8b949e">🕒 خروج: {dev.get('Date_Sortie', '---')}</div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # أزرار الإجراءات
                        bcol1, bcol2 = st.columns([1, 1])
                        with bcol1:
                            if st.button(f"📥 تحميل فاتورة #{dev.get('ID')}", key=f"inv_{dev.get('ID')}"):
                                invoice_content = f"""
                                INFODOC TECHNOLOGY - فاتورة صيانة
                                --------------------------------
                                رقم الجهاز: {dev.get('ID')}
                                الجهاز: {dev.get('Appareil')}
                                الحالة: {statut}
                                تاريخ الدخول: {dev.get('Date_Entree')}
                                تاريخ الخروج: {dev.get('Date_Sortie')}
                                السعر الإجمالي: {dev.get('Prix')} DZD
                                الضمان: شهر واحد من تاريخ الخروج
                                --------------------------------
                                شكرًا لثقتكم بنا.
                                """
                                st.download_button("تأكيد تحميل الملف", invoice_content, file_name=f"InfoDoc_{dev.get('ID')}.txt")
                        
                        with bcol2:
                            tg_url = f"https://t.me/{st.secrets['BOT_USERNAME']}?start={phone_n}"
                            st.link_button("🔗 ربط بـ Telegram", tg_url, use_container_width=True)

# --- 7. بوت التليغرام (Background) ---
def run_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return
    bot = telebot.TeleBot(token)
    
    @bot.message_handler(commands=['start'])
    def sync(m):
        args = m.text.split()
        if len(args) > 1:
            p = normalize_phone(args[1])
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.send_message(m.chat.id, "✅ تم ربط جهازك بنجاح! ستصلك إشعارات عند أي تحديث.")
    
    bot.polling(none_stop=True)

if "bot_thread" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_thread"] = True
