import os
import threading
import re
from datetime import datetime
import firebase_admin
import pandas as pd
import streamlit as st
import telebot
import qrcode
from io import BytesIO
from firebase_admin import credentials, db

# --- 1. الإعدادات والاتصال بقاعدة البيانات ---
def ensure_firebase():
    if not firebase_admin._apps:
        try:
            cred_dict = dict(st.secrets["firebase"])
            if "\\n" in cred_dict["private_key"]:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
        except Exception as e:
            st.error(f"خطأ في الاتصال: {e}")

ensure_firebase()

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
BOT_USERNAME = st.secrets.get("BOT_USERNAME", "")

# --- 2. الدوال البرمجية (Logic) ---
def normalize_phone(phone: str) -> str:
    p = str(phone or "").replace(".0", "").strip()
    p = re.sub(r"\D", "", p)
    if p.startswith("213"): p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]: p = "0" + p
    return p

def get_shop_status():
    try:
        status = db.reference("shop_settings/is_open").get()
        return True if status is None else status
    except: return True

def fetch_devices(phone: str):
    phone_n = normalize_phone(phone)
    if len(phone_n) < 9: return pd.DataFrame()
    last9 = phone_n[-9:]
    raw = db.reference("atelier").get()
    if not raw or not isinstance(raw, dict): return pd.DataFrame()
    rows = [val for val in raw.values() if normalize_phone(val.get("Telephone", "")).endswith(last9)]
    df = pd.DataFrame(rows)
    if not df.empty and "ID" in df.columns:
        df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)
        df = df.sort_values("ID", ascending=False)
    return df

# --- 3. تصميم الواجهة (CSS) ---
st.set_page_config(page_title="InfoDoc Portal", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
    * { font-family: 'Cairo', sans-serif; color: #FFFFFF !important; }
    .stApp { background: #0d1117; }
    
    /* Animations */
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; opacity: 1; } 50% { opacity: 0.6; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; opacity: 1; } 50% { opacity: 0.6; } }
    @keyframes blink-gold { 0%, 100% { border-color: #d29922; } 50% { border-color: #ffcc00; box-shadow: 0 0 10px #ffcc00; } }

    /* Header */
    .hero { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; }
    .status-open { color: #3fb950 !important; border: 1px solid #3fb950; padding: 5px 15px; border-radius: 8px; animation: blink-green 2s infinite; }
    .status-closed { color: #f85149 !important; border: 1px solid #f85149; padding: 5px 15px; border-radius: 8px; animation: blink-red 2s infinite; }
    
    /* Expander */
    div[data-testid="stExpander"] { border: 2px solid #d29922 !important; animation: blink-gold 3s infinite; direction: rtl; }
    
    /* Device Cards */
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 15px; overflow: hidden; }
    .card-header { background: #21262d; padding: 10px 15px; display: flex; justify-content: space-between; }
    .progress-bar { width: 100%; background: #30363d; height: 8px; border-radius: 5px; margin-top: 10px; }
    .progress-fill { height: 100%; border-radius: 5px; transition: width 1s; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. عرض المحتوى ---

# الترحيب وحالة المحل
shop_open = get_shop_status()
st_class = "status-open" if shop_open else "status-closed"
st_text = "مفتوح الآن - OPEN" if shop_open else "مغلق حالياً - CLOSED"

st.markdown(f"""
    <div class="hero">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <h1 style="color: #58a6ff !important; margin:0;">INFODOC TECHNOLOGY</h1>
            <div class="{st_class}">{st_text}</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 20px;">
            <div>📞 0798661900</div>
            <div>📍 الشلف - المركز التجاري OPGI</div>
            <a href="https://www.google.com/maps" style="color: #3fb950 !important; text-decoration: none;">📍 اتبع موقعنا على الخريطة</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# شروط الصيانة (Expander)
with st.expander("⚠️ ملاحظات وشروط الصيانة الهامة - اقرأ هنا"):
    st.markdown("""
        <div style="direction: rtl; text-align: right; line-height: 1.6;">
            • فحص الجهاز (في حال رفض التصليح): <b>1000 دج</b>.<br>
            • أسعار تصليح البطاقة الأم تبدأ من <b>3000 دج</b>.<br>
            • يتم التصليح تلقائياً للمبالغ بين 3000 و 4000 دج.<br>
            • يرجى ربط <b>Telegram</b> لتلقي التنبيهات فوراً.
        </div>
    """, unsafe_allow_html=True)

# البحث عن الأجهزة
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("🔍 تتبع حالة جهازك")
    phone = st.text_input("أدخل رقم هاتفك:", placeholder="07XXXXXXXX")
    if phone:
        df = fetch_devices(phone)
        if df.empty:
            st.info("لا توجد أجهزة مسجلة بهذا الرقم.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "En attente"))
                p_val = 100 if stt == "Prêt" else 60 if stt == "En Cours" else 20
                p_color = "#238636" if stt == "Prêt" else "#1f6feb"
                
                st.markdown(f"""
                    <div class="card">
                        <div class="card-header">
                            <b>#{r.get('ID')} | {r.get('Appareil')}</b>
                            <span style="color:{p_color} !important; font-weight:bold;">{stt}</span>
                        </div>
                        <div style="padding: 15px;">
                            <div style="display: flex; justify-content: space-between; font-size: 0.9rem;">
                                <span>العطل: {r.get('Panne')}</span>
                                <span>السعر: {r.get('Prix')} دج</span>
                            </div>
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: {p_val}%; background: {p_color};"></div>
                            </div>
                            {f'<div style="color:#3fb950 !important; font-size:0.8rem; margin-top:5px;">🛡️ ضمان التصليح مفعل</div>' if stt == "Prêt" else ''}
                        </div>
                    </div>
                """, unsafe_allow_html=True)

with col_right:
    st.subheader("🤖 إشعارات تلغرام")
    if phone:
        qr_data = f"https://t.me/{BOT_USERNAME}?start={normalize_phone(phone)}"
        qr = qrcode.make(qr_data)
        buf = BytesIO()
        qr.save(buf, format="PNG")
        st.image(buf.getvalue(), width=150)
        st.link_button("ربط مع الحساب الآن", qr_data, use_container_width=True)

# --- 5. تشغيل البوت في الخلفية ---
def run_bot():
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    @bot.message_handler(commands=["start"])
    def sync(m):
        args = m.text.split()
        if len(args) > 1:
            p = normalize_phone(args[1])[-9:]
            ref = db.reference("atelier")
            raw = ref.get()
            if raw:
                for k, v in raw.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.send_message(m.chat.id, "✅ تم ربط جهازك بنجاح!")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
