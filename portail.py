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

# --- 1. إعداد Firebase ---
def ensure_firebase():
    if not firebase_admin._apps:
        try:
            cred_dict = dict(st.secrets["firebase"])
            if "\\n" in cred_dict["private_key"]:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
        except Exception as e:
            st.error(f"خطأ: {e}")

ensure_firebase()

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
BOT_USERNAME = st.secrets.get("BOT_USERNAME", "")

# --- 2. الدوال ---
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

# --- 3. CSS المحسن (بدون فجوات بيضاء) ---
st.set_page_config(page_title="InfoDoc - Client Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap');
    
    .stApp { background: #010409; color: #FFFFFF !important; }

    .hero-container {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #30363d; border-radius: 15px; padding: 25px; margin-bottom: 5px;
    }
    
    .main-title { font-family: 'Orbitron', sans-serif; color: #58a6ff; font-size: 2.2rem; font-weight: 900; }
    
    .status-open { color: #3fb950; border: 1px solid #3fb950; padding: 5px 12px; border-radius: 8px; animation: blink-green 2s infinite; font-weight: bold; }
    .status-closed { color: #f85149; border: 1px solid #f85149; padding: 5px 12px; border-radius: 8px; animation: blink-red 2s infinite; font-weight: bold; }
    
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 10px #3fb950; } 50% { box-shadow: none; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 10px #f85149; } 50% { box-shadow: none; } }

    .contact-card {
        background: #21262d; border: 1px solid #30363d; padding: 12px;
        border-radius: 8px; color: #FFFFFF !important; text-decoration: none;
        display: flex; align-items: center; justify-content: center; transition: 0.3s;
        font-family: 'Cairo'; font-size: 0.9rem;
    }
    .contact-card:hover { background: #30363d; border-color: #58a6ff; transform: translateY(-2px); }

    .dev-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 15px; overflow: hidden; }
    .dev-header { background: #161b22; padding: 12px 15px; display: flex; justify-content: space-between; border-bottom: 1px solid #30363d; align-items: center; }
    
    .stTextInput input { background-color: #0d1117 !important; color: white !important; border: 1px solid #30363d !important; }
    
    /* إخفاء شريط المساعدة السفلي في Streamlit */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 4. الهيدر والترحيب ---
st.markdown(f"<div style='text-align: right; color: #8b949e; font-family: Cairo; margin-bottom: 5px;'>الوقت الحالي في الشلف: {datetime.now().strftime('%H:%M')}</div>", unsafe_allow_html=True)

shop_open = get_shop_status()
status_class = "status-open" if shop_open else "status-closed"
status_text = "ATELIER OUVERT" if shop_open else "ATELIER FERMÉ"

st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            <div class="{status_class}">{status_text}</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-top: 20px;">
            <a href="tel:0798661900" class="contact-card">📞 0798661900</a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="contact-card" style="background: #238636;">📍 موقع المحل</a>
            <a href="https://www.facebook.com/infodoc02" target="_blank" class="contact-card">🔵 Facebook</a>
            <a href="https://www.tiktok.com/@infodoc02" target="_blank" class="contact-card">⚫ TikTok</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 5. الشروط ---
with st.expander("⚠️ ملاحظات وشروط الصيانة"):
    st.markdown("<div style='text-align: right; direction: rtl; font-family: Cairo;'>فحص الجهاز المرفوض: 1000 دج | صيانة البطاقة الأم تبدأ من 3000 دج.</div>", unsafe_allow_html=True)

# --- 6. البحث والتتبع ---
col_main, col_sync = st.columns([2, 1])

with col_main:
    st.markdown("### 🔍 Track Device")
    phone_input = st.text_input("Registered Phone Number:", placeholder="07XXXXXXXX", key="p_search")
    phone_n = normalize_phone(phone_input)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("No devices found.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "N/A"))
                st_color = "#238636" if stt == "Prêt" else "#1f6feb"
                prog = {"En attente": 25, "En Cours": 60, "Prêt": 100}.get(stt, 10)
                
                st.markdown(f"""
                    <div class="dev-card">
                        <div class="dev-header">
                            <b>#{int(r.get('ID', 0))} | {r.get('Appareil', 'Device')}</b>
                            <span style="background:{st_color}; padding:2px 8px; border-radius:5px; font-size:0.8rem; font-weight:bold;">{stt}</span>
                        </div>
                        <div style="padding: 15px;">
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                                <div><small style="color:#8b949e;">PANNE</small><br><b>{r.get('Panne', '---')}</b></div>
                                <div><small style="color:#8b949e;">PRIX</small><br><b>{float(r.get('Prix', 0)):,.0f} DZD</b></div>
                                <div><small style="color:#8b949e;">DATE</small><br><b>{r.get('Date_Entree', '---')}</b></div>
                            </div>
                            <div style="width: 100%; background: #21262d; border-radius: 10px; height: 8px; overflow: hidden;">
                                <div style="width: {prog}%; background: linear-gradient(90deg, #1f6feb, #58a6ff); height: 100%;"></div>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

with col_sync:
    st.markdown("### 🤖 Telegram")
    if phone_n and len(phone_n) >= 9:
        qr_url = f"https://t.me/{BOT_USERNAME}?start={phone_n}"
        qr_img = qrcode.make(qr_url)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), width=150)
        st.link_button("🚀 Sync Telegram", qr_url, use_container_width=True)

# --- 7. بوت التليغرام (Background) ---
if "bot_active" not in st.session_state:
    def run_bot():
        if not TELEGRAM_TOKEN: return
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
                    bot.send_message(m.chat.id, "✅ تم الربط بنجاح!")
        bot.polling(none_stop=True)
    
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
