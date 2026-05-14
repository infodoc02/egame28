import os
import threading
import re
from datetime import datetime, timedelta
import firebase_admin
import pandas as pd
import streamlit as st
import telebot
from io import BytesIO
from firebase_admin import credentials, db

# --- 1. Firebase Setup ---
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

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
BOT_USERNAME = st.secrets.get("BOT_USERNAME", "")

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

# --- 3. Custom CSS ---
st.set_page_config(page_title="InfoDoc - Portal", page_icon="📱", layout="centered")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap');
    
    .stApp { background: #010409; color: #FFFFFF !important; }

    /* Blink Animation */
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .status-open { color: #3fb950; border: 1px solid #3fb950; padding: 4px 10px; border-radius: 8px; font-weight: bold; animation: blink 2s infinite; }
    .status-closed { color: #f85149; border: 1px solid #f85149; padding: 4px 10px; border-radius: 8px; font-weight: bold; animation: blink 2s infinite; }

    /* Hero Section */
    .hero { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; text-align: center; }
    .main-title { font-family: 'Orbitron', sans-serif; color: #58a6ff; font-size: 2rem; font-weight: 900; margin-bottom: 15px; }

    /* Contact Links */
    .contact-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-top: 15px; }
    .c-link { text-decoration: none; color: #adbac7 !important; background: #21262d; border: 1px solid #30363d; padding: 10px; border-radius: 8px; font-size: 0.85rem; transition: 0.3s; }
    .c-link:hover { border-color: #58a6ff; background: #30363d; transform: translateY(-2px); }

    /* Device Cards */
    .dev-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 15px; overflow: hidden; position: relative; }
    .dev-header { background: #161b22; padding: 10px 15px; display: flex; justify-content: space-between; border-bottom: 1px solid #30363d; align-items: center; }
    
    /* Special Style for Livre et Payé */
    .special-card { border: 1px solid #d29922 !important; box-shadow: 0 0 15px rgba(210, 153, 34, 0.1); }
    .badge-gold { background: #d29922; color: #000 !important; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.75rem; }
    
    .warranty-active { color: #3fb950; font-weight: bold; font-size: 0.9rem; }
    .warranty-expired { color: #f85149; text-decoration: line-through; font-weight: bold; opacity: 0.7; }

    .stTextInput input { background-color: #0d1117 !important; color: white !important; border: 1px solid #30363d !important; border-radius: 10px; }
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 4. Greeting & Header ---
now = datetime.now()
greeting = "صباح الخير" if 5 <= now.hour < 12 else "مساء الخير"
st.markdown(f"<div style='text-align: right; font-family: Cairo; color: #8b949e; font-size: 0.9rem;'>{greeting}، الوقت في الشلف: {now.strftime('%H:%M')}</div>", unsafe_allow_html=True)

shop_open = get_shop_status()
st_cls = "status-open" if shop_open else "status-closed"
st_txt = "OUVERT" if shop_open else "FERMÉ"

st.markdown(f"""
    <div class="hero">
        <div class="main-title">INFODOC TECHNOLOGY</div>
        <div style="margin-bottom: 15px;"><span class="{st_cls}">SHOP {st_txt}</span></div>
        <div class="contact-grid">
            <a href="tel:0798661900" class="c-link">📞 اتصل بنا</a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="c-link">📍 الموقع</a>
            <a href="https://facebook.com/infodoc02" target="_blank" class="c-link">🔵 Facebook</a>
            <a href="https://tiktok.com/@infodoc02" target="_blank" class="c-link">⚫ TikTok</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 5. Main Content ---
st.markdown("<h3 style='text-align: center; font-family: Cairo;'>🔍 تتبع حالة الجهاز</h3>", unsafe_allow_html=True)
phone_input = st.text_input("", placeholder="أدخل رقم هاتفك (07XXXXXXXX)...", key="search_bar")
phone_n = normalize_phone(phone_input)

if phone_n and len(phone_n) >= 9:
    df = fetch_customer_devices(phone_n)
    if df.empty:
        st.warning("لم يتم العثور على أجهزة مرتبطة بهذا الرقم.")
    else:
        for _, r in df.iterrows():
            stt = str(r.get("Statut", "N/A"))
            
            # Logic: Progress & Styles
            p_map = {"En attente": 0, "En Cours": 33, "Réparable": 66, "Prêt": 100, "Livre et payé": 100}
            prog = p_map.get(stt, 0)
            
            is_delivered = (stt == "Livre et payé")
            card_class = "dev-card special-card" if is_delivered else "dev-card"
            badge_html = f'<span class="badge-gold">LIVRÉ & PAYÉ</span>' if is_delivered else f'<span style="color:#58a6ff; font-weight:bold;">{stt}</span>'

            # Warranty Logic
            warranty_html = ""
            if is_delivered:
                exit_date_str = r.get('Date_Sortie', '')
                try:
                    exit_date = datetime.strptime(exit_date_str, '%d/%m/%Y')
                    expiry_date = exit_date + timedelta(days=30)
                    if datetime.now() <= expiry_date:
                        warranty_html = f'<div class="warranty-active">🛡️ ضمان ساري لغاية: {expiry_date.strftime("%d/%m/%Y")}</div>'
                    else:
                        warranty_html = f'<div class="warranty-expired">🛡️ الضمان منتهي ({expiry_date.strftime("%d/%m/%Y")})</div>'
                except:
                    warranty_html = f'<div style="color:#8b949e; font-size:0.8rem;">تاريخ التسليم: {exit_date_str}</div>'

            st.markdown(f"""
                <div class="{card_class}">
                    <div class="dev-header">
                        <b style="color:#adbac7;">#{int(r.get('ID',0))} | {r.get('Appareil','الجهاز')}</b>
                        {badge_html}
                    </div>
                    <div style="padding: 15px;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; font-size: 0.9rem;">
                            <div><small style="color:#8b949e;">العطل:</small><br><b>{r.get('Panne','---')}</b></div>
                            <div><small style="color:#8b949e;">التكلفة:</small><br><b style="color:#3fb950;">{float(r.get('Prix',0)):,.0f} DZD</b></div>
                        </div>
                        <div style="width: 100%; background: #21262d; border-radius: 20px; height: 8px; overflow: hidden; margin-bottom: 10px;">
                            <div style="width: {prog}%; background: linear-gradient(90deg, #1f6feb, #58a6ff); height: 100%;"></div>
                        </div>
                        {warranty_html}
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Telegram Sync Button (Placed inside each card if not linked)
            if not r.get("Telegram_ID"):
                tg_url = f"https://t.me/{BOT_USERNAME}?start={phone_n}"
                st.link_button(f"🔔 ربط تنبيهات الجهاز #{r.get('ID')}", tg_url, use_container_width=True)

# --- 6. Telegram Bot Thread ---
if "bot_active" not in st.session_state:
    def run_bot():
        if not TELEGRAM_TOKEN: return
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        @bot.message_handler(commands=["start"])
        def handle_start(m):
            args = m.text.split()
            if len(args) > 1:
                p = normalize_phone(args[1])
                ref = db.reference("atelier")
                raw = ref.get()
                if raw:
                    found = False
                    for k, v in raw.items():
                        if normalize_phone(v.get("Telephone", "")).endswith(p[-9:]):
                            ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                            found = True
                    if found: bot.send_message(m.chat.id, "✅ تم تفعيل التنبيهات! سنخطرك هنا فور تغير حالة جهازك.")
        bot.polling(none_stop=True)
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
