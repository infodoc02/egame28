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

# --- Advanced UI & Animations ---
st.set_page_config(page_title="InfoDoc - Expert Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap');
    
    .stApp { background: #010409; color: #FFFFFF !important; }

    /* Animations */
    @keyframes blink-green { 0%, 100% { opacity: 1; box-shadow: 0 0 15px #3fb950; } 50% { opacity: 0.5; } }
    @keyframes blink-red { 0%, 100% { opacity: 1; box-shadow: 0 0 15px #f85149; } 50% { opacity: 0.5; } }
    @keyframes blink-yellow { 0%, 100% { border-color: #d29922; box-shadow: 0 0 5px #d29922; } 50% { border-color: #ffcc00; box-shadow: 0 0 15px #ffcc00; } }

    .hero-container {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #30363d;
        border-radius: 15px; padding: 25px; margin-bottom: 15px;
    }
    
    .status-open { color: #3fb950; border: 1px solid #3fb950; padding: 5px 12px; border-radius: 8px; animation: blink-green 2s infinite; font-weight: bold; }
    .status-closed { color: #f85149; border: 1px solid #f85149; padding: 5px 12px; border-radius: 8px; animation: blink-red 2s infinite; font-weight: bold; }

    /* Contact & Maps */
    .contact-card {
        background: #21262d; border-right: 4px solid #58a6ff;
        padding: 10px 15px; border-radius: 8px; color: #FFFFFF !important; font-family: 'Cairo';
    }
    .maps-btn {
        background: #238636; color: white !important; text-align: center; padding: 12px;
        border-radius: 8px; font-weight: bold; display: block; text-decoration: none;
        transition: 0.3s; margin-top: 10px; font-family: 'Cairo';
    }
    .maps-btn:hover { background: #2ea043; transform: scale(1.02); }

    /* Expander Styling */
    div[data-testid="stExpander"] {
        border: 2px solid #d29922 !important; border-radius: 10px !important;
        animation: blink-yellow 3s infinite; direction: rtl; margin-bottom: 20px;
    }

    /* Device Card */
    .dev-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 20px; overflow: hidden; }
    .progress-bg { width: 100%; background: #21262d; border-radius: 10px; height: 8px; margin: 10px 0; }
    .progress-fill { height: 8px; border-radius: 10px; transition: width 1.5s ease-in-out; }
    
    .warranty-badge {
        border: 1px solid #238636; color: #3fb950 !important; padding: 2px 10px;
        border-radius: 20px; font-size: 0.75rem; font-weight: bold; display: inline-block;
    }

    p, span, div, label, summary, b { color: #FFFFFF !important; }
    </style>
    """, unsafe_allow_html=True)

# --- Real-time Greeting ---
hour = datetime.now().hour
greeting = "صباح الخير" if 5 <= hour < 12 else "مساء الخير"
st.markdown(f"<div style='text-align: right; color: #8b949e; font-family: Cairo;'>{greeting} زبوننا الكريم | {datetime.now().strftime('%H:%M')}</div>", unsafe_allow_html=True)

# --- Header Section ---
shop_open = get_shop_status()
st_class = "status-open" if shop_open else "status-closed"
st_text = "ATELIER OUVERT" if shop_open else "ATELIER FERMÉ"

st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div style="font-family: 'Orbitron'; color: #58a6ff; font-size: 2rem; font-weight: 900;">INFODOC TECHNOLOGY</div>
            <div class="{st_class}">{st_text}</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin-top: 15px;">
            <div class="contact-card">📞 0798661900</div>
            <div class="contact-card">📍 الشلف - المركز التجاري OPGI</div>
            <div class="contact-card">🔵 Facebook: InfoDoc</div>
            <a href="https://www.google.com/maps/search/?api=1&query=Chlef+OPGI" target="_blank" class="maps-btn">📍 فتح الموقع على الخريطة</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Instructions Expander ---
with st.expander("⚠️ اضغط هنا لقراءة شروط وملاحظات الصيانة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: 'Cairo'; line-height: 1.8; padding: 10px;">
            • في حال تم التشخيص ورفض الزبون التصليح، يتوجب دفع <b>1000 دج</b> ثمن الفحص.<br>
            • أسعار تصليح اللوحة الأم تبدأ من <b>3000 دج</b>.<br>
            • التصليح المباشر يكون للمبالغ بين 3000 و 4000 دج. ما فوق ذلك يتطلب موافقتك.<br>
            • يرجى ربط حسابك بـ <b>Telegram</b> لتلقي التنبيهات الفورية.
        </div>
    """, unsafe_allow_html=True)

# --- Search & Content ---
col_main, col_sync = st.columns([2, 1])

with col_main:
    st.markdown("### 🔍 Track Device Status")
    phone_input = st.text_input("Enter Phone Number:", placeholder="07XXXXXXXX")
    phone_n = normalize_phone(phone_input)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("No devices found.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "N/A"))
                
                # Progress Logic
                p_map = {"En attente": 25, "En Cours": 65, "Prêt": 100}
                p_val = p_map.get(stt, 10)
                p_color = "#238636" if stt == "Prêt" else "#1f6feb"
                
                st.markdown(f"""
                    <div class="dev-card">
                        <div style="background:#161b22; padding:12px 15px; display:flex; justify-content:space-between; align-items:center;">
                            <b style="color:#58a6ff;">#{int(r.get('ID', 0))} | {r.get('Appareil', 'Device')}</b>
                            <div>
                                {f'<span class="warranty-badge">🛡️ Warranty Active</span>' if stt == "Prêt" else ''}
                                <span style="background:{p_color}; padding:2px 8px; border-radius:5px; font-size:0.8rem;">{stt}</span>
                            </div>
                        </div>
                        <div style="padding:15px;">
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; font-size:0.9rem;">
                                <div><small style="color:#8b949e;">PROBLEM</small><br><b>{r.get('Panne', '---')}</b></div>
                                <div><small style="color:#8b949e;">PRICE</small><br><b>{float(r.get('Prix', 0)):,.0f} DZD</b></div>
                                <div><small style="color:#8b949e;">DATE</small><br><b>{r.get('Date_Entree', '---')}</b></div>
                            </div>
                            <div class="progress-bg">
                                <div class="progress-fill" style="width: {p_val}%; background: {p_color}; shadow: 0 0 10px {p_color};"></div>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

with col_sync:
    st.markdown("### 🤖 Notification Sync")
    if phone_n and len(phone_n) >= 9:
        qr_img = qrcode.make(f"https://t.me/{BOT_USERNAME}?start={phone_n}")
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), width=160)
        st.link_button("🚀 Sync Telegram Bot", f"https://t.me/{BOT_USERNAME}?start={phone_n}", use_container_width=True)
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
                for k, v in raw.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.send_message(m.chat.id, "✅ InfoDoc: Your device is now synced!")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
