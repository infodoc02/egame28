import os
import threading
import re
from datetime import datetime, timedelta
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
            st.error(f"Firebase Error: {e}")

ensure_firebase()

TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
BOT_USERNAME = st.secrets.get("BOT_USERNAME", "")

# --- 2. الدوال المنطقية ---
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

# --- 3. التصميم (CSS) ---
st.set_page_config(page_title="InfoDoc - Portal", page_icon="📱", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap');
    
    .stApp { background: #010409; color: #FFFFFF !important; }

    /* أنيميشن الوميض */
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; opacity: 1; } 50% { opacity: 0.6; box-shadow: none; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; opacity: 1; } 50% { opacity: 0.6; box-shadow: none; } }

    .hero-container { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); border: 1px solid #30363d; border-radius: 15px; padding: 25px; margin-bottom: 20px; }
    .main-title { font-family: 'Orbitron', sans-serif; color: #58a6ff; font-size: 2.2rem; font-weight: 900; }
    
    .status-open { color: #3fb950; border: 1px solid #3fb950; padding: 5px 12px; border-radius: 8px; animation: blink-green 2s infinite; font-weight: bold; }
    .status-closed { color: #f85149; border: 1px solid #f85149; padding: 5px 12px; border-radius: 8px; animation: blink-red 2s infinite; font-weight: bold; }

    /* مربعات التواصل الاحترافية */
    .contact-link {
        text-decoration: none; color: white !important; background: #21262d; border: 1px solid #30363d;
        padding: 15px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
        gap: 10px; transition: 0.3s; font-family: 'Cairo'; font-weight: bold;
    }
    .contact-link:hover { background: #30363d; border-color: #58a6ff; transform: translateY(-3px); box-shadow: 0 5px 15px rgba(88,166,255,0.2); }

    .dev-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 20px; }
    .dev-header { background: #161b22; padding: 12px 15px; display: flex; justify-content: space-between; border-bottom: 1px solid #30363d; }
    
    .stTextInput input { background-color: #0d1117 !important; color: white !important; border: 1px solid #30363d !important; }
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 4. رسالة الترحيب ---
current_hour = datetime.now().hour
greeting = "صباح الخير" if 5 <= current_hour < 12 else "مساء الخير"
st.markdown(f"<div style='text-align: right; font-family: Cairo; color: #8b949e;'>{greeting} زبوننا الكريم، الوقت الحالي في الشلف: {datetime.now().strftime('%H:%M')}</div>", unsafe_allow_html=True)

# --- 5. الهيدر ---
shop_open = get_shop_status()
st_cls = "status-open" if shop_open else "status-closed"
st_txt = "ATELIER OUVERT" if shop_open else "ATELIER FERMÉ"

st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            <div class="{st_cls}">{st_txt}</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 20px;">
            <a href="tel:0798661900" class="contact-link">📞 0798661900</a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="contact-link" style="border-bottom: 3px solid #238636;">📍 موقع المحل</a>
            <a href="https://facebook.com/infodoc02" target="_blank" class="contact-link">🔵 Facebook</a>
            <a href="https://tiktok.com/@infodoc02" target="_blank" class="contact-link">⚫ TikTok</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 6. المحتوى الرئيسي ---
col_main, col_sync = st.columns([2.2, 1])

with col_main:
    st.markdown("### 🔍 تتبع حالة جهازك")
    phone_input = st.text_input("أدخل رقم الهاتف المسجل:", placeholder="07XXXXXXXX", key="main_search")
    phone_n = normalize_phone(phone_input)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("لم يتم العثور على أجهزة.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "N/A"))
                # منطق الحالات والتقدم
                p_map = {"En attente": 20, "En Cours": 50, "Prêt": 85, "Livre et payé": 100}
                prog = p_map.get(stt, 10)
                st_color = "#238636" if stt in ["Prêt", "Livre et payé"] else "#1f6feb"
                
                # تاريخ الضمان
                exit_date = r.get('Date_Sortie', '---')
                warranty_info = f"🛡️ الضمان يبدأ من: {exit_date}" if stt == "Livre et payé" else ""

                st.markdown(f"""
                    <div class="dev-card">
                        <div class="dev-header">
                            <b style="color:#58a6ff;">#{int(r.get('ID',0))} | {r.get('Appareil','Device')}</b>
                            <span style="background:{st_color}; padding:2px 10px; border-radius:5px; font-weight:bold; font-size:0.8rem;">{stt}</span>
                        </div>
                        <div style="padding:15px;">
                            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:10px; margin-bottom:15px;">
                                <div><small style="color:#8b949e;">المشكل</small><br><b>{r.get('Panne','---')}</b></div>
                                <div><small style="color:#8b949e;">السعر</small><br><b>{float(r.get('Prix',0)):,.0f} DZD</b></div>
                                <div><small style="color:#8b949e;">الدخول</small><br><b>{r.get('Date_Entree','---')}</b></div>
                            </div>
                            <div style="width:100%; background:#21262d; border-radius:10px; height:10px; overflow:hidden; margin-bottom:10px;">
                                <div style="width:{prog}%; background:linear-gradient(90deg, #1f6feb, #58a6ff); height:100%; transition:1s;"></div>
                            </div>
                            <div style="color:#3fb950; font-size:0.8rem; font-weight:bold;">{warranty_info}</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                # زر تحميل الفاتورة (يظهر فقط عند التسليم)
                if stt == "Livre et payé":
                    st.download_button(label=f"📄 تحميل فاتورة جهاز #{r.get('ID')}", 
                                       data=f"INFO DOC TECHNOLOGY\nDevice: {r.get('Appareil')}\nPrice: {r.get('Prix')} DZD\nWarranty: 1 Month from {exit_date}", 
                                       file_name=f"facture_{r.get('ID')}.txt")

with col_sync:
    st.markdown("### 🤖 ربط التليغرام")
    st.info("اربط جهازك لتلقي إشعارات فورية عند الجاهزية.")
    if phone_n and len(phone_n) >= 9:
        qr_url = f"https://t.me/{BOT_USERNAME}?start={phone_n}"
        qr_img = qrcode.make(qr_url)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="امسح الكود للربط")
        st.link_button("🚀 فتح في تليغرام", qr_url, use_container_width=True)

# --- 7. البوت ---
if "bot_active" not in st.session_state:
    def run_bot():
        if not TELEGRAM_TOKEN: return
        bot = telebot.TeleBot(TELEGRAM_TOKEN)
        @bot.message_handler(commands=["start"])
        def sync_acc(m):
            args = m.text.split()
            if len(args) > 1:
                p = normalize_phone(args[1])
                ref = db.reference("atelier")
                raw = ref.get()
                if raw:
                    for k, v in raw.items():
                        if normalize_phone(v.get("Telephone","")).endswith(p[-9:]):
                            ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                    bot.send_message(m.chat.id, "✅ تم الربط! ستصلك رسالة هنا فور جاهزية جهازك.")
        bot.polling(none_stop=True)
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
