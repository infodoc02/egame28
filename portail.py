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

# --- Core Configuration ---
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
            st.error(f"Firebase Error: {e}")

ensure_firebase()

# --- Logic Functions ---
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

# --- UI & Professional CSS ---
st.set_page_config(page_title="InfoDoc Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;900&family=Cairo:wght@400;700&display=swap');
    
    .stApp {
        background: #020617;
        color: #e2e8f0; /* Silver text for high contrast */
    }

    /* Hero Section */
    .hero-box {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid #38bdf8;
        border-radius: 20px;
        padding: 30px;
        margin-bottom: 25px;
        box-shadow: 0 0 20px rgba(56, 189, 248, 0.15);
    }

    .main-title {
        font-family: 'Orbitron', sans-serif;
        color: #38bdf8;
        font-size: 2.2rem;
        font-weight: 900;
        letter-spacing: 2px;
    }

    /* Status Badge */
    .status-badge {
        padding: 5px 15px;
        border-radius: 50px;
        font-family: 'Cairo', sans-serif;
        font-weight: bold;
        font-size: 0.85rem;
    }
    .status-open { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }
    .status-closed { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }

    /* Arabic Instructions Box (The Professional Touch) */
    .instruction-box {
        background: rgba(251, 191, 36, 0.05);
        border-right: 5px solid #fbbf24;
        padding: 20px;
        border-radius: 10px;
        margin: 20px 0;
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        line-height: 1.7;
    }

    /* Device Cards */
    .dev-card {
        background: #0f172a;
        border: 1px solid #1e293b;
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 15px;
    }
    .dev-card:hover { border-color: #38bdf8; }
    
    .label-tag { color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; }
    .value-tag { color: #f1f5f9; font-weight: bold; font-size: 1rem; }

    /* Fix Input Contrast */
    div[data-baseweb="input"] { background-color: #1e293b !important; border-radius: 10px !important; }
    input { color: #ffffff !important; }
    </style>
    """, unsafe_allow_html=True)

# --- Header Section ---
shop_open = get_shop_status()
st_class = "status-open" if shop_open else "status-closed"
st_text = "SHOP OPEN - مفتوح" if shop_open else "SHOP CLOSED - مغلق"

st.markdown(f"""
    <div class="hero-box">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            <div class="status-badge {st_class}">{st_text}</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px; margin-top: 20px; border-top: 1px solid #1e293b; padding-top: 20px;">
            <div><small class="label-tag">Phone</small><br><b>0798661900</b></div>
            <div><small class="label-tag">Location</small><br><b>الشلف - وسط المدينة</b></div>
            <div><small class="label-tag">Social</small><br><b>InfoDoc / @infodoc02</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Arabic Instructions (Only instructions in Arabic as requested) ---
st.markdown("""
    <div class="instruction-box">
        <h4 style="color:#fbbf24; margin-top:0;">⚠️ ملاحظات هامة للزبائن:</h4>
        • في حالة كان جهازك قابلاً للتصليح ورفضت ذلك، يترتب عليك دفع مبلغ <b>1000 دج</b> (ثمن الفحص والفتح والغلق).<br>
        • أسعار التصليح (عند العمل على البطاقة الأم) تبدأ من <b>3000 دج</b>.<br>
        • <b>نظام الموافقة:</b> من 3000 إلى 4000 دج نصلح مباشرة، وفوق 4000 دج ننتظر موافقتك عبر رسالة.<br>
        • <b>للتواصل الجيد:</b> يرجى تحميل تطبيق <b>Telegram</b> وربطه عبر الزر أدناه لتلقي الإشعارات فوراً.
    </div>
    """, unsafe_allow_html=True)

# --- Main App ---
col1, col2 = st.columns([2, 1])

with col1:
    st.write("### 🔍 Track Device")
    phone = st.text_input("Enter Phone Number", placeholder="07XXXXXXXX")
    phone_n = normalize_phone(phone)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.info("No devices found for this number.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "N/A"))
                st_color = "#4ade80" if stt == "Prêt" else "#38bdf8"
                st.markdown(f"""
                    <div class="dev-card">
                        <div style="display:flex; justify-content:space-between; margin-bottom:15px;">
                            <b style="font-size:1.2rem; color:#38bdf8;">#{int(r.get('ID', 0))} | {r.get('Appareil', 'Device')}</b>
                            <span style="color:{st_color}; font-weight:bold;">{stt}</span>
                        </div>
                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
                            <div><span class="label-tag">Problem:</span><br><span class="value-tag">{r.get('Panne', '---')}</span></div>
                            <div><span class="label-tag">Price:</span><br><span class="value-tag">{float(r.get('Prix', 0)):,.0f} DZD</span></div>
                            <div><span class="label-tag">Entry Date:</span><br><span class="value-tag">{r.get('Date_Entree', '---')}</span></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

with col2:
    st.write("### 🤖 Telegram Alert")
    if phone_n and len(phone_n) >= 9:
        qr = qrcode.make(f"https://t.me/{BOT_USERNAME}?start={phone_n}")
        buf = BytesIO()
        qr.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="Scan to Link Telegram", width=160)
        st.link_button("🚀 Activate Telegram Bot", f"https://t.me/{BOT_USERNAME}?start={phone_n}", use_container_width=True)
    else:
        st.caption("Enter phone number to generate sync link.")

# Telegram Bot Threading (Remains as is)
def run_bot():
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    @bot.message_handler(commands=["start"])
    def h(m):
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
                bot.send_message(m.chat.id, "✅ InfoDoc Sync Complete!" if updated > 0 else "⚠️ No device found.")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
