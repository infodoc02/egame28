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

# --- 1. Configuration & Firebase ---
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

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "fallback_token_here")
BOT_USERNAME = st.secrets.get("BOT_USERNAME", "default_bot")

# --- 2. Logic Functions ---
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

# --- 3. UI Setup & CSS ---
st.set_page_config(page_title="InfoDoc - Client Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap');
    
    .stApp { background: #010409; color: #FFFFFF !important; }

    @keyframes blink-green { 0%, 100% { opacity: 1; box-shadow: 0 0 15px #3fb950; } 50% { opacity: 0.5; } }
    @keyframes blink-red { 0%, 100% { opacity: 1; box-shadow: 0 0 15px #f85149; } 50% { opacity: 0.5; } }
    @keyframes blink-yellow-border { 0%, 100% { border-color: #d29922; box-shadow: 0 0 5px #d29922; } 50% { border-color: #ffcc00; box-shadow: 0 0 20px #ffcc00; } }

    .hero-container {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #30363d; border-radius: 15px; padding: 25px; margin-bottom: 15px;
    }
    
    .main-title { font-family: 'Orbitron', sans-serif; color: #58a6ff; font-size: 2.2rem; font-weight: 900; }
    .status-open { color: #3fb950; border: 1px solid #3fb950; padding: 5px 12px; border-radius: 8px; animation: blink-green 2s infinite; font-weight: bold; }
    .status-closed { color: #f85149; border: 1px solid #f85149; padding: 5px 12px; border-radius: 8px; animation: blink-red 2s infinite; font-weight: bold; }

    .contact-item {
        background: #21262d; border-left: 4px solid #58a6ff; padding: 10px 15px;
        border-radius: 8px; color: #FFFFFF !important; font-family: 'Cairo', sans-serif; font-size: 0.9rem;
    }

    div[data-testid="stExpander"] {
        border: 2px solid #d29922 !important; border-radius: 10px !important;
        animation: blink-yellow-border 3s infinite ease-in-out;
        background: rgba(210, 153, 34, 0.05) !important; direction: rtl;
    }
    
    div[data-testid="stExpander"] summary { color: #ffcc00 !important; font-family: 'Cairo', sans-serif; font-weight: 900 !important; font-size: 1.1rem !important; }
    .dev-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 15px; overflow: hidden; }
    .dev-header { background: #161b22; padding: 12px 15px; display: flex; justify-content: space-between; border-bottom: 1px solid #30363d; }
    
    p, span, div, label, summary { color: #FFFFFF !important; }
    .stTextInput input { background-color: #0d1117 !important; color: white !important; border: 1px solid #30363d !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. Header & Greeting ---
current_hour = datetime.now().hour
greeting = "صباح الخير" if 5 <= current_hour < 12 else "مساء الخير"

st.markdown(f"""
    <div style="text-align: right; color: #8b949e; font-family: 'Cairo'; margin-bottom: 10px;">
        {greeting} زبوننا الكريم، الوقت الحالي في الشلف: {datetime.now().strftime('%H:%M')}
    </div>
""", unsafe_allow_html=True) 

shop_open = get_shop_status()
status_class = "status-open" if shop_open else "status-closed"
status_text = "ATELIER OUVERT" if shop_open else "ATELIER FERMÉ"

st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            <div class="{status_class}">{status_text}</div>
        </div>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; margin-top: 15px;">
            <div class="contact-item">📞 <b>الهاتف:</b> 0798661900</div>
            
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" style="text-decoration: none;">
                <div style="background: #238636; color: white; text-align: center; padding: 10px; 
                            border-radius: 8px; font-weight: bold; height: 100%; display: flex; 
                            align-items: center; justify-content: center; transition: 0.3s;"
                     onmouseover="this.style.background='#2ea043'" onmouseout="this.style.background='#238636'">
                    📍 اتبع المسار إلى المحل
                </div>
            </a>

            <div class="contact-item">🔵 <b>Facebook:</b> InfoDoc</div>
            <div class="contact-item">⚫ <b>TikTok:</b> @infodoc02</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 5. Info Expander ---
with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: 'Cairo'; line-height: 1.8; padding: 10px; color: #f0f6fc;">
            1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<b>رفض الزبون ذلك</b>، يتم دفع <b>1000 دج</b> ثمن الجهد والفحص.<br>
            2️⃣ أسعار العمل على <b>البطاقة الأم (Carte Mère)</b> تبدأ من <b>3000 دج</b>.<br>
            3️⃣ <b>الموافقة التلقائية:</b> نصلح مباشرة إذا كان السعر بين 3000 و 4000 دج. فوق ذلك نطلب موافقتك أولاً.<br>
            4️⃣ <b>التنبيهات:</b> يرجى ربط حسابك بـ <b>Telegram</b> لتصلك رسالة فور جاهزية جهازك.
        </div>
    """, unsafe_allow_html=True)

# --- 6. Main Content (Search & Tracking) ---
col_main, col_sync = st.columns([2, 1])

with col_main:
    st.markdown("### 🔍 Track Device")
    phone_input = st.text_input("Registered Phone Number:", placeholder="07XXXXXXXX", key="unique_phone_input")
    phone_n = normalize_phone(phone_input)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("No devices found.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "N/A"))
                st_color = "#238636" if stt == "Prêt" else "#1f6feb"
                
                progress_map = {"En attente": 25, "En Cours": 60, "Prêt": 100}
                current_val = progress_map.get(stt, 10)
                
                warranty_badge = ""
                if stt == "Prêt":
                    warranty_badge = """
                    <div style="border: 1px solid #238636; color: #3fb950; padding: 2px 10px; 
                         border-radius: 20px; font-size: 0.7rem; display: inline-block; margin-top: 10px; font-weight: bold;">
                         🛡️ Garantie Incluse
                    </div>
                    """

                st.markdown(f"""
                    <div class="dev-card">
                        <div class="dev-header">
                            <b style="color: #58a6ff;">#{int(r.get('ID', 0))} | {r.get('Appareil', 'Device')}</b>
                            <span style="background:{st_color}; padding:2px 8px; border-radius:5px; font-size:0.8rem; font-weight:bold;">{stt}</span>
                        </div>
                        <div style="padding: 15px;">
                            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 10px;">
                                <div><small style="color:#8b949e;">PROBLEM</small><br><b>{r.get('Panne', '---')}</b></div>
                                <div><small style="color:#8b949e;">PRICE</small><br><b>{float(r.get('Prix', 0)):,.0f} DZD</b></div>
                                <div><small style="color:#8b949e;">DATE</small><br><b>{r.get('Date_Entree', '---')}</b></div>
                            </div>
                            <div style="width: 100%; background-color: #21262d; border-radius: 10px; margin: 10px 0; height: 8px; overflow: hidden;">
                                <div style="width: {current_val}%; background: linear-gradient(90deg, #1f6feb, #58a6ff); 
                                     height: 100%; transition: width 1s ease-in-out;">
                                </div>
                            </div>
                            {warranty_badge}
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
    else:
        st.info("Input phone to sync.")

# --- 7. Telegram Bot Thread ---
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
                bot.send_message(m.chat.id, "✅ Done! Your device is now linked to InfoDoc.")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
