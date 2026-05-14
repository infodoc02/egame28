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

# --- UI & Professional CSS (Enhanced Visibility) ---
st.set_page_config(page_title="InfoDoc - Client Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap');
    
    .stApp {
        background: #010409;
        color: #FFFFFF !important;
    }

    /* Hero & Titles */
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
        text-shadow: 0 0 10px rgba(88, 166, 255, 0.3);
    }

    /* Contact Info Section */
    .contact-item {
        background: #21262d;
        border-left: 3px solid #58a6ff;
        padding: 12px 20px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #FFFFFF !important;
        font-family: 'Cairo', sans-serif;
    }
    .contact-item b { color: #58a6ff; }

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

    /* Device Card (Ultra Style) */
    .dev-card {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 0;
        margin-bottom: 20px;
        overflow: hidden;
        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
    }
    .dev-header {
        background: #161b22;
        padding: 15px 20px;
        border-bottom: 1px solid #30363d;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .dev-body { padding: 20px; }
    
    /* Status Styles */
    .status-badge {
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: bold;
        text-transform: uppercase;
        font-size: 0.8rem;
    }
    .ready { background: #238636; color: white; box-shadow: 0 0 10px rgba(35, 134, 54, 0.4); }
    .working { background: #1f6feb; color: white; box-shadow: 0 0 10px rgba(31, 111, 235, 0.4); }
    .waiting { background: #9e6a03; color: white; }

    /* Text Visibility Fix */
    p, span, div, label { color: #FFFFFF !important; }
    .label-blue { color: #58a6ff !important; font-weight: bold; font-size: 0.85rem; }
    
    /* Input Styling */
    .stTextInput input {
        background-color: #0d1117 !important;
        color: white !important;
        border: 1px solid #30363d !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Shop Info Section ---
shop_open = get_shop_status()
status_html = '<span style="color:#3fb950; font-weight:bold;">● OPEN</span>' if shop_open else '<span style="color:#f85149; font-weight:bold;">○ CLOSED</span>'

st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            <div style="font-family: 'Orbitron'; font-size: 1.1rem;">{status_html}</div>
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
        2️⃣ أسعار التصليح في حالة العمل على <b>البطاقة الأم (Carte Mère)</b> تبدأ من <b>3000 دج</b>.<br>
        3️⃣ <b>نظام الموافقة:</b> نصلح الجهاز مباشرة إذا كانت التكلفة بين 3000 و 4000 دج. في حال تجاوزت 4000 دج، سنرسل لك رسالة للموافقة أو الرفض.<br>
        4️⃣ <b>للتواصل السريع:</b> نرجو من زبائننا الكرام تحميل تطبيق <b>Telegram</b> وربطه عبر الزر أدناه لتلقي الإشعارات الفورية.
    </div>
    """, unsafe_allow_html=True)

# --- Main Interaction ---
col_main, col_sync = st.columns([2, 1])

with col_main:
    st.markdown("### 🔍 Track Device Status")
    phone_input = st.text_input("Enter your registered phone number:", placeholder="0798661900")
    phone_n = normalize_phone(phone_input)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("No records found for this phone number.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "N/A"))
                st_class = "ready" if stt == "Prêt" else "working" if "Cours" in stt else "waiting"
                
                st.markdown(f"""
                    <div class="dev-card">
                        <div class="dev-header">
                            <span style="font-family: 'Orbitron'; color: #58a6ff; font-weight: bold; font-size: 1.1rem;">
                                ID: #{int(r.get('ID', 0))} — {r.get('Appareil', 'Device')}
                            </span>
                            <span class="status-badge {st_class}">{stt}</span>
                        </div>
                        <div class="dev-body">
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px;">
                                <div>
                                    <span class="label-blue">🛠️ PROBLEM</span><br>
                                    <span style="font-size: 1.1rem;">{r.get('Panne', '---')}</span>
                                </div>
                                <div>
                                    <span class="label-blue">💰 PRICE</span><br>
                                    <span style="font-size: 1.1rem; color: #f0f6fc;">{float(r.get('Prix', 0)):,.0f} DZD</span>
                                </div>
                                <div>
                                    <span class="label-blue">📅 ENTRY DATE</span><br>
                                    <span>{r.get('Date_Entree', '---')}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

with col_sync:
    st.markdown("### 🤖 Sync Telegram")
    if phone_n and len(phone_n) >= 9:
        st.write("Link your device to receive instant notifications:")
        qr_img = qrcode.make(f"https://t.me/{BOT_USERNAME}?start={phone_n}")
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="Scan to Connect", width=180)
        st.link_button("🚀 Open Telegram Bot", f"https://t.me/{BOT_USERNAME}?start={phone_n}", use_container_width=True)
    else:
        st.info("Please enter your phone number to show the sync link.")

# --- Bot Backend (Hidden) ---
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
                bot.send_message(m.chat.id, "✅ InfoDoc Sync: Success!" if updated > 0 else "⚠️ No device linked.")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
