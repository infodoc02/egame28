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
import re
from datetime import datetime, timedelta
import threading
import telebot

# --- 1. الإعدادات الأساسية ---
st.set_page_config(page_title="InfoDoc - Client Portal", page_icon="📱", layout="wide")

@st.cache_resource
def init_db():
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

init_db()

# --- 2. الدوال المنطقية ---
def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
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

# --- 3. تصميم الواجهة (CSS) ---
st.set_page_config(page_title="InfoDoc - Client Portal", page_icon="⚡", layout="wide")

def get_warranty_info(status, date_sortie_str):
    # الضمان يظهر فقط في حالة Livré & Payé
    if status != "Livré & Payé" or not date_sortie_str or date_sortie_str == "---":
        return None
    try:
        date_s = datetime.strptime(date_sortie_str, "%Y-%m-%d")
        expiry = date_s + timedelta(days=30)
        expired = datetime.now() > expiry
        return {"expiry": expiry.strftime("%Y-%m-%d"), "is_expired": expired}
    except: return None

# --- 3. تصميم الـ CSS (الوميض + الألوان + الأزرار) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@500;900&display=swap');
    
    .stApp { background: #010409; color: #FFFFFF !important; }

    /* الهيدر وبطاقة المعلومات */
    .hero-container {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #30363d; border-radius: 15px; padding: 25px; margin-bottom: 15px;
    }
    
    .main-title { font-family: 'Orbitron', sans-serif; color: #58a6ff; font-size: 2.2rem; font-weight: 900; }
    
    .status-open { color: #3fb950; border: 1px solid #3fb950; padding: 5px 12px; border-radius: 8px; animation: blink-green 2s infinite; font-weight: bold; }
    .status-closed { color: #f85149; border: 1px solid #f85149; padding: 5px 12px; border-radius: 8px; animation: blink-red 2s infinite; font-weight: bold; }
    
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; } 50% { box-shadow: none; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; } 50% { box-shadow: none; } }

    .contact-item {
        background: #21262d; border-left: 4px solid #58a6ff; padding: 10px 15px;
        border-radius: 8px; font-family: 'Cairo', sans-serif; font-size: 0.9rem;
    }

    /* التنبيه الوماض */
    div[data-testid="stExpander"] {
        border: 2px solid #d29922 !important; border-radius: 10px !important;
        background: rgba(210, 153, 34, 0.05) !important; direction: rtl;
    }
    
    /* بطاقة الجهاز */
    .dev-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; margin-bottom: 15px; overflow: hidden; }
    .dev-header { background: #161b22; padding: 12px 15px; display: flex; justify-content: space-between; border-bottom: 1px solid #30363d; align-items: center; }
    
    .stTextInput input { background-color: #0d1117 !important; color: white !important; border: 1px solid #30363d !important; }
    p, span, div, label, summary { color: #FFFFFF !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. الترحيب والوقت ---
current_hour = datetime.now().hour
greeting = "صباح الخير" if 5 <= current_hour < 12 else "مساء الخير"
st.markdown(f"<div style='text-align: right; color: #8b949e; font-family: Cairo; margin-bottom: 10px;'>{greeting} زبوننا الكريم، الوقت الحالي في الشلف: {datetime.now().strftime('%H:%M')}</div>", unsafe_allow_html=True)

# --- 5. الهيدر والمعلومات ---
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
                <div style="background: #238636; color: white; text-align: center; padding: 10px; border-radius: 8px; font-weight: bold; transition: 0.3s;">
                    📍 اتبع المسار إلى المحل (Google Maps)
                </div>
            </a>
            <div class="contact-item">🔵 <b>Facebook:</b> InfoDoc</div>
            <div class="contact-item">⚫ <b>TikTok:</b> @infodoc02</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 6. الشروط الموضحة ---
with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: Cairo; line-height: 1.8;">
            1️⃣ فحص الجهاز المرفوض تصليحه: <b>1000 دج</b>.<br>
            2️⃣ صيانة البطاقة الأم تبدأ من <b>3000 دج</b>.<br>
            3️⃣ الموافقة التلقائية بين 3000 و 4000 دج، ما فوق ذلك نتصل بك.<br>
            4️⃣ يرجى ربط <b>Telegram</b> لتصلك الإشعارات فوراً.
        </div>
    """, unsafe_allow_html=True)

# --- 7. البحث والتتبع (هنا تم حل مشكلة Duplicate ID) ---
col_main, col_sync = st.columns([2, 1])

with col_main:
    st.markdown("### 🔍 Track Device")
    # تم وضع KEY فريد لمنع تكرار العنصر
    phone_input = st.text_input("Registered Phone Number:", placeholder="07XXXXXXXX", key="main_phone_search")
    phone_n = normalize_phone(phone_input)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("No devices found for this number.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "N/A"))
                st_color = "#238636" if stt == "Prêt" else "#1f6feb"
                prog_val = {"En attente": 25, "En Cours": 60, "Prêt": 100}.get(stt, 10)
                
                warranty = f'<div style="border: 1px solid #238636; color: #3fb950; padding: 2px 10px; border-radius: 20px; font-size: 0.7rem; display: inline-block; margin-top: 10px;">🛡️ Garantie Incluse</div>' if stt == "Prêt" else ""

# --- 5. البحث وتوزيع الألوان للحالات ---
st.markdown("### 🔍 تتبع حالة جهازك")
phone_raw = st.text_input("أدخل رقم هاتفك المسجل:", key="search_input")

# قاموس الألوان للحالات
status_config = {
    "En Cours": {"color": "#1f6feb", "prog": 33},
    "Réparable": {"color": "#39c5bb", "prog": 66},
    "Prêt": {"color": "#3fb950", "prog": 100},
    "Non Réparable": {"color": "#f85149", "prog": 100},
    "Livré & Payé": {"color": "#3fb950", "prog": 100},
    "Livré (Dette)": {"color": "#d29922", "prog": 100},
    "Annulé": {"color": "#8b949e", "prog": 0}
}

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            my_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم.")
            else:
                # رابط التليغرام
                if not any(str(d.get("Telegram_ID", "")).strip() != "" for d in my_devices):
                    tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                    st.link_button("🚀 ربط الحساب بالتليغرام لتلقي الإشعارات", tg_url, type="primary", use_container_width=True)
                
                # عرض الأجهزة
                for d in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = d.get("Statut", "En Cours")
                    cfg = status_config.get(stat, {"color": "#8b949e", "prog": 0})
                    
                    # الضمان
                    w_info = get_warranty_info(stat, d.get("Date_Sortie"))
                    w_html = ""
                    if w_info:
                        w_class = "w-expired" if w_info["is_expired"] else "w-active"
                        w_text = f"🛡️ ضمان منتهي ({w_info['expiry']})" if w_info["is_expired"] else f"🛡️ ضمان ساري لغاية: {w_info['expiry']}"
                        w_html = f'<div class="{w_class}">{w_text}</div>'

                    st.markdown(f"""
                        <div class="device-card" style="border-right: 6px solid {cfg['color']};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <b style="font-family: 'Orbitron'; color: #58a6ff; font-size: 1.1rem;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span style="background: {cfg['color']}; color: #0d1117; padding: 4px 12px; border-radius: 5px; font-weight: bold; font-size: 0.8rem;">{stat.upper()}</span>
                            </div>
                            <div style="margin: 15px 0;">
                                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #8b949e; margin-bottom: 5px;">
                                    <span>تقدم العمل: {cfg['prog']}%</span>
                                    <span>العطل: {d.get('Panne')}</span>
                                </div>
                                <div style="width: 100%; background: #21262d; height: 10px; border-radius: 10px; overflow: hidden;">
                                    <div style="width: {cfg['prog']}%; background: {cfg['color']}; height: 100%; transition: 0.5s;"></div>
                                </div>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.9rem; font-family: 'Cairo';">
                                <div>📅 الدخول: {d.get('Date_Entree')}</div>
                                <div>🕒 الخروج: {d.get('Date_Sortie', '---')}</div>
                                <div style="color: #58a6ff; font-weight: bold;">💰 السعر: {d.get('Prix')} دج</div>
                                <div>{w_html}</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # زر تحميل الفاتورة (الآن ملون وواضح)
                    inv_text = f"INFODOC TECHNOLOGY\nID: {d.get('ID')}\nDevice: {d.get('Appareil')}\nPrice: {d.get('Prix')} DZD\nStatus: {stat}"
                    st.download_button(f"📄 تحميل معلومات الجهاز #{d.get('ID')}", inv_text, file_name=f"InfoDoc_{d.get('ID')}.txt", key=f"inv_{d.get('ID')}")

# --- 6. بوت التليغرام ---
def start_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return
    bot = telebot.TeleBot(token)
    @bot.message_handler(commands=['start'])
    def handle(m):
        args = m.text.split()
        if len(args) > 1:
            p = normalize_phone(args[1])
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.reply_to(m, "✅ تم ربط حسابك! ستصلك رسالة هنا فور جاهزية جهازك.")
    bot.polling(none_stop=True)

if "bot_running" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_running"] = True
