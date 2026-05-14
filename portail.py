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
from firebase_admin import credentials, db, initialize_app

# --- Configuration ---
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "fallback_token_here")
BOT_USERNAME = st.secrets.get("BOT_USERNAME", "default_bot")
DB_URL = st.secrets.get("DB_URL", "https://your-default-db.firebaseio.com/")

def ensure_firebase():
    if not firebase_admin._apps:
        try:
            cred_dict = dict(st.secrets["firebase"])
            if "\\n" in cred_dict["private_key"]:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
        except Exception as e:
            st.error(f"Firebase Connection Error: {e}")

ensure_firebase()

# --- Logic ---
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

def fetch_customer_devices(phone: str) -> pd.DataFrame:
    phone = normalize_phone(phone)
    if len(phone) < 9: return pd.DataFrame()
    last9 = phone[-9:]
    raw = db.reference("atelier").get()
    if not raw or not isinstance(raw, dict): return pd.DataFrame()
    rows = []
    for key, val in raw.items():
        tel = normalize_phone(val.get("Telephone", ""))
        if tel.endswith(last9):
            r = val.copy()
            r["_id"] = key
            rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty and "ID" in df.columns:
        df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)
        df = df.sort_values("ID", ascending=False)
    return df

# --- UI & Professional CSS with Animations ---
st.set_page_config(page_title="InfoDoc - Client Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap');
    
    .stApp {
        background: #010409;
        color: #FFFFFF !important;
    }

    /* Keyframes for Blinking Status */
    @keyframes blink-green {
        0% { opacity: 1; box-shadow: 0 0 15px rgba(63, 185, 80, 0.6); }
        50% { opacity: 0.4; box-shadow: 0 0 5px rgba(63, 185, 80, 0.2); }
        100% { opacity: 1; box-shadow: 0 0 15px rgba(63, 185, 80, 0.6); }
    }
    @keyframes blink-red {
        0% { opacity: 1; box-shadow: 0 0 15px rgba(248, 81, 73, 0.6); }
        50% { opacity: 0.4; box-shadow: 0 0 5px rgba(248, 81, 73, 0.2); }
        100% { opacity: 1; box-shadow: 0 0 15px rgba(248, 81, 73, 0.6); }
    }

    .hero-container {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #30363d;
        border-radius: 15px;
        padding: 25px;
        margin-bottom: 20px;
    }
    
    .main-title {
        font-family: 'Orbitron', sans-serif;
        color: #58a6ff;
        font-size: 2.5rem;
        font-weight: 900;
    }

    /* Status Badges with Animation */
    .status-active-open {
        background: rgba(63, 185, 80, 0.15);
        color: #3fb950 !important;
        border: 1px solid #3fb950;
        padding: 8px 16px;
        border-radius: 8px;
        font-weight: bold;
        animation: blink-green 2s infinite ease-in-out;
    }
    .status-active-closed {
        background: rgba(248, 81, 73, 0.15);
        color: #f85149 !important;
        border: 1px solid #f85149;
        padding: 8px 16px;
        border-radius: 8px;
        font-weight: bold;
        animation: blink-red 2s infinite ease-in-out;
    }

    /* Contact Info Section */
    .contact-item {
        background: #21262d;
        border-left: 4px solid #58a6ff;
        padding: 12px 20px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #FFFFFF !important;
        font-family: 'Cairo', sans-serif;
    }

    /* Arabic Instructions (Right Aligned) */
    .instruction-box {
        direction: rtl;
        text-align: right;
        background: rgba(210, 153, 34, 0.1);
        border-right: 5px solid #d29922;
        padding: 20px;
        border-radius: 10px;
        margin: 20px 0;
        font-family: 'Cairo', sans-serif;
        color: #f0f6fc !important;
        line-height: 1.8;
    }

    /* Device Card UI */
    .dev-card {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 12px;
        margin-bottom: 20px;
        overflow: hidden;
    }
    .dev-header {
        background: #161b22;
        padding: 15px 20px;
        border-bottom: 1px solid #30363d;
        display: flex;
        justify-content: space-between;
    }
    .status-label {
        padding: 4px 10px;
        border-radius: 5px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    
    p, span, div, label { color: #FFFFFF !important; }
    .stTextInput input {
        background-color: #0d1117 !important;
        color: white !important;
        border: 1px solid #30363d !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Shop Info Section ---
shop_open = get_shop_status()
if shop_open:
    status_html = '<div class="status-active-open">ATELIER OUVERT MAINTENANT</div>'
else:
    status_html = '<div class="status-active-closed">ATELIER FERMÉ MAINTENANT</div>'

st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            <div>{status_html}</div>
        </div>
        <hr style="border-color: #30363d; margin: 20px 0;">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px;">
            <div class="contact-item">📞 <b>رقم الهاتف:</b> 0798661900</div>
            <div class="contact-item">📍 <b>الموقع:</b> الشلف وسط المدينة - المركز التجاري OPGI (الطابق السفلي)</div>
            <div class="contact-item">🔵 <b>Facebook:</b> InfoDoc</div>
            <div class="contact-item">⚫ <b>TikTok:</b> @infodoc02</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Arabic Instructions (Right-Aligned) ---
st.markdown("""
    <div class="instruction-box">
        <h3 style="margin-top:0; color:#d29922; font-weight:900;">⚠️ ملاحظات وشروط الصيانة</h3>
        1️⃣ عند فحص الجهاز وتبين أنه قابل للتصليح ثم <b>رفض الزبون التصليح</b>، يتوجب دفع مبلغ <b>1000 دج</b> ثمن الفحص والفتح والغلق.<br>
        2️⃣ أسعار التصليح في حالة العمل على <b>البطاقة الأم (Carte Mère)</b> تبدأ من <b>3000 دج</b> فما فوق.<br>
        3️⃣ <b>نظام الموافقة:</b> نصلح الجهاز مباشرة إذا كانت التكلفة بين 3000 و 4000 دج. في حال تجاوزت 4000 دج، سنرسل لك رسالة للموافقة أو الرفض.<br>
        4️⃣ <b>للتواصل السريع:</b> نرجو من زبائننا الكرام تحميل تطبيق <b>Telegram</b> وربطه عبر الزر أدناه لتلقي الإشعارات الفورية.
    </div>
    """, unsafe_allow_html=True)

# --- Main App ---
col_main, col_sync = st.columns([2, 1])

with col_main:
    st.markdown("### 🔍 Track Device Status")
    phone_input = st.text_input("Enter phone number:", placeholder="07XXXXXXXX")
    phone_n = normalize_phone(phone_input)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("No records found.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "N/A"))
                color = "#238636" if stt == "Prêt" else "#1f6feb"
                
                st.markdown(f"""
                    <div class="dev-card">
                        <div class="dev-header">
                            <span style="color: #58a6ff; font-weight: bold;">ID: #{int(r.get('ID', 0))} | {r.get('Appareil', 'Device')}</span>
                            <span class="status-label" style="background:{color};">{stt}</span>
                        </div>
                        <div style="padding: 20px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px;">
                            <div><small style="color:#8b949e;">🛠️ PROBLEM</small><br><b>{r.get('Panne', '---')}</b></div>
                            <div><small style="color:#8b949e;">💰 PRICE</small><br><b>{float(r.get('Prix', 0)):,.0f} DZD</b></div>
                            <div><small style="color:#8b949e;">📅 DATE</small><br><b>{r.get('Date_Entree', '---')}</b></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

with col_sync:
    st.markdown("### 🤖 Telegram Sync")
    if phone_n and len(phone_n) >= 9:
        qr_img = qrcode.make(f"https://t.me/{BOT_USERNAME}?start={phone_n}")
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="Scan to Link Account", width=180)
        st.link_button("🚀 Start Telegram Bot", f"https://t.me/{BOT_USERNAME}?start={phone_n}", use_container_width=True)
    else:
        st.info("Input phone to sync.")

# --- Background Bot Thread ---
def run_bot():
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    @bot.message_handler(commands=["start"])
    def sync(m):
        args = m.text.split()
        if len(args) > 1:
            p = normalize_phone(args[1])
            ref = db.reference("atelier")
            raw = ref.get()
            if raw:
                updated = 0
                for k, v in raw.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                        updated += 1
                bot.send_message(m.chat.id, "✅ InfoDoc Sync: Success!")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
