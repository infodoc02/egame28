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

# --- 1. الاتصال بقاعدة البيانات ---
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

# --- 2. منطق البحث والبيانات ---
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

# --- 3. هندسة التصميم (CSS الملكي) ---
st.set_page_config(page_title="InfoDoc Pro", layout="wide")

st.markdown("""
    <style>
    /* الخطوط والخلفية */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
    
    .stApp { background-color: #000000 !important; }
    html, body, [data-testid="stVerticalBlock"] { background-color: #000000 !important; }
    
    * { font-family: 'Cairo', sans-serif !important; color: #FFFFFF !important; }

    /* أنيميشن الوميض */
    @keyframes blink-green { 0%, 100% { border-color: #00ff00; box-shadow: 0 0 15px #00ff00; } 50% { border-color: transparent; box-shadow: none; } }
    @keyframes blink-red { 0%, 100% { border-color: #ff0000; box-shadow: 0 0 15px #ff0000; } 50% { border-color: transparent; box-shadow: none; } }
    @keyframes pulse-gold { 0%, 100% { border: 2px solid #ffcc00; } 50% { border: 2px solid #ffffff; } }

    /* حاوية الهيدر */
    .header-card {
        background: #111111;
        border: 1px solid #333333;
        border-radius: 15px;
        padding: 25px;
        margin-bottom: 20px;
        text-align: center;
    }
    
    /* بادجات الحالة */
    .badge-open { border: 2px solid #00ff00; padding: 10px; border-radius: 10px; animation: blink-green 2s infinite; font-weight: bold; color: #00ff00 !important; }
    .badge-closed { border: 2px solid #ff0000; padding: 10px; border-radius: 10px; animation: blink-red 2s infinite; font-weight: bold; color: #ff0000 !important; }

    /* إطار الشروط */
    div[data-testid="stExpander"] {
        background: #000000 !important;
        border: 2px solid #ffcc00 !important;
        animation: pulse-gold 3s infinite;
        border-radius: 10px !important;
    }

    /* كرت الجهاز */
    .device-box {
        background: #111111;
        border: 1px solid #333333;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 20px;
    }
    
    /* شريط التقدم */
    .bar-container { width: 100%; background: #333333; height: 12px; border-radius: 10px; margin: 15px 0; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 10px; transition: width 1s ease-in-out; }

    /* ختم الضمان */
    .guarantee {
        background: #008000;
        color: white !important;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-block;
    }

    /* المدخلات */
    input { background-color: #111111 !important; color: white !important; border: 1px solid #333333 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. العرض الفعلي ---

# الهيدر
shop_status = get_shop_status()
st_html = '<span class="badge-open">ATELIER OUVERT MAINTENANT</span>' if shop_status else '<span class="badge-closed">ATELIER FERMÉ MAINTENANT</span>'

st.markdown(f"""
    <div class="header-card">
        <h1 style="color: #00aaff !important; margin-bottom: 10px;">INFODOC TECHNOLOGY</h1>
        <div style="margin-bottom: 20px;">{st_html}</div>
        <div style="display: flex; justify-content: center; gap: 20px; flex-wrap: wrap;">
            <span>📞 0798661900</span>
            <span>📍 الشلف - OPGI</span>
            <a href="https://maps.google.com" style="color: #00aaff !important;">🗺️ موقع المحل</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# الشروط
with st.expander("⚠️ ملاحظات وشروط الصيانة (اضغط للقراءة)"):
    st.markdown("""
        <div style="direction: rtl; text-align: right; padding: 10px;">
        • فحص الجهاز (عند رفض التصليح): <b>1000 دج</b>.<br>
        • تصليح البطاقة الأم يبدأ من <b>3000 دج</b>.<br>
        • نصلح الأعطال أقل من 4000 دج تلقائياً.<br>
        • يرجى ربط <b>التلغرام</b> لتصلك وضعية جهازك.
        </div>
    """, unsafe_allow_html=True)

# البحث
c1, c2 = st.columns([2, 1])

with c1:
    st.markdown("### 🔍 تتبع جهازك")
    phone_in = st.text_input("أدخل رقم هاتفك:")
    
    if phone_in:
        results = fetch_devices(phone_in)
        if results.empty:
            st.info("لا توجد نتائج.")
        else:
            for _, r in results.iterrows():
                stt = str(r.get("Statut", "En attente"))
                
                # إعدادات الشريط
                p_width = 100 if stt == "Prêt" else 60 if stt == "En Cours" else 20
                p_color = "#00ff00" if stt == "Prêt" else "#00aaff"
                
                st.markdown(f"""
                    <div class="device-box">
                        <div style="display: flex; justify-content: space-between;">
                            <b style="font-size: 1.2rem; color: #00aaff !important;">#{r.get('ID')} | {r.get('Appareil')}</b>
                            { '<span class="guarantee">🛡️ GARANTIE 30 JOURS</span>' if stt == "Prêt" else '' }
                        </div>
                        <div style="margin-top: 10px;">
                            <span>العطل: {r.get('Panne')}</span> | 
                            <span style="color: #ffcc00 !important;">السعر: {r.get('Prix')} دج</span>
                        </div>
                        <div class="bar-container">
                            <div class="bar-fill" style="width: {p_width}%; background: {p_color};"></div>
                        </div>
                        <div style="display: flex; justify-content: space-between; opacity: 0.7; font-size: 0.8rem;">
                            <span>الحالة: {stt}</span>
                            <span>التاريخ: {r.get('Date_Entree')}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

with c2:
    st.markdown("### 🤖 إشعارات تلغرام")
    if phone_in and len(normalize_phone(phone_in)) >= 9:
        bot_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={normalize_phone(phone_in)}"
        qr = qrcode.make(bot_url)
        buf = BytesIO()
        qr.save(buf, format="PNG")
        st.image(buf.getvalue(), width=150)
        st.link_button("🚀 ربط الحساب الآن", bot_url)

# --- 5. تشغيل البوت ---
def run_bot():
    bot = telebot.TeleBot(st.secrets.get("TELEGRAM_TOKEN"))
    @bot.message_handler(commands=["start"])
    def sync(m):
        args = m.text.split()
        if len(args) > 1:
            p_end = normalize_phone(args[1])[-9:]
            ref = db.reference("atelier")
            raw = ref.get()
            if raw:
                for k, v in raw.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p_end):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.send_message(m.chat.id, "✅ InfoDoc: تم الربط بنجاح!")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
