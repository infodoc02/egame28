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

# --- 1. إعداد الاتصال ---
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

# --- 3. تصميم الواجهة الاحترافي (CSS) ---
st.set_page_config(page_title="InfoDoc Pro Portal", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@600;900&display=swap');
    
    /* الخلفية الداكنة جداً */
    .stApp {
        background-color: #010409 !important;
    }

    /* كل النصوص بالأبيض */
    h1, h2, h3, p, span, div, label, b, summary {
        color: #FFFFFF !important;
        font-family: 'Cairo', sans-serif;
    }

    /* أنيميشن الوميض */
    @keyframes blink-green { 0%, 100% { opacity: 1; box-shadow: 0 0 15px #3fb950; } 50% { opacity: 0.4; } }
    @keyframes blink-red { 0%, 100% { opacity: 1; box-shadow: 0 0 15px #f85149; } 50% { opacity: 0.4; } }
    @keyframes blink-border-gold { 0%, 100% { border-color: #d29922; } 50% { border-color: #ffcc00; box-shadow: 0 0 20px rgba(210, 153, 34, 0.3); } }

    /* الهيدر الاحترافي */
    .hero-box {
        background: linear-gradient(145deg, #0d1117, #161b22);
        border: 1px solid #30363d;
        border-radius: 20px;
        padding: 30px;
        margin-bottom: 25px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    }

    .main-title {
        font-family: 'Orbitron', sans-serif;
        font-size: 2.8rem;
        font-weight: 900;
        background: linear-gradient(90deg, #58a6ff, #bc8cff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    /* حالات العمل */
    .status-badge-open {
        background: rgba(63, 185, 80, 0.1);
        color: #3fb950 !important;
        border: 1px solid #3fb950;
        padding: 8px 20px;
        border-radius: 10px;
        font-weight: 900;
        animation: blink-green 2s infinite;
        text-transform: uppercase;
    }
    .status-badge-closed {
        background: rgba(248, 81, 73, 0.1);
        color: #f85149 !important;
        border: 1px solid #f85149;
        padding: 8px 20px;
        border-radius: 10px;
        font-weight: 900;
        animation: blink-red 2s infinite;
        text-transform: uppercase;
    }

    /* إطار الشروط المومض */
    div[data-testid="stExpander"] {
        background: #0d1117 !important;
        border: 2px solid #d29922 !important;
        border-radius: 12px !important;
        animation: blink-border-gold 3s infinite;
    }

    /* بطاقات الأجهزة */
    .device-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 15px;
        margin-bottom: 20px;
        transition: 0.3s;
    }
    .device-card:hover { border-color: #58a6ff; }
    
    .card-top {
        background: #21262d;
        padding: 15px 20px;
        border-radius: 15px 15px 0 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    /* شريط التقدم */
    .progress-container {
        width: 100%;
        background: #30363d;
        height: 10px;
        border-radius: 20px;
        margin: 15px 0;
        overflow: hidden;
    }
    .progress-fill {
        height: 100%;
        border-radius: 20px;
        transition: width 1s ease-in-out;
    }

    /* أزرار التواصل */
    .contact-pill {
        background: #21262d;
        border: 1px solid #30363d;
        padding: 10px 15px;
        border-radius: 10px;
        font-size: 0.9rem;
    }
    
    .map-link {
        background: #238636;
        color: white !important;
        text-decoration: none;
        padding: 12px;
        border-radius: 10px;
        display: block;
        text-align: center;
        font-weight: bold;
        transition: 0.3s;
    }
    .map-link:hover { background: #2ea043; transform: translateY(-2px); }

    /* تحسين حقول الإدخال */
    .stTextInput input {
        background-color: #0d1117 !important;
        color: white !important;
        border: 1px solid #30363d !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 4. العرض وتوزيع العناصر ---

# الترحيب الذكي
curr_h = datetime.now().hour
greet = "صباح الخير" if 5 <= curr_h < 12 else "مساء الخير"
st.markdown(f"<div style='text-align: right; opacity: 0.7;'>{greet} زبوننا الكريم | {datetime.now().strftime('%H:%M')}</div>", unsafe_allow_html=True)

# الهيدر
is_open = get_shop_status()
status_html = '<div class="status-badge-open">Atelier Ouvert Maintenant</div>' if is_open else '<div class="status-badge-closed">Atelier Fermé Maintenant</div>'

st.markdown(f"""
    <div class="hero-box">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            {status_html}
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 25px;">
            <div class="contact-pill">📞 <b>الهاتف:</b> 0798661900</div>
            <div class="contact-pill">📍 <b>الموقع:</b> الشلف - المركز التجاري OPGI</div>
            <div class="contact-pill">🔵 <b>فيسبوك:</b> InfoDoc</div>
            <a href="https://www.google.com/maps/search/?api=1&query=Chlef+OPGI" target="_blank" class="map-link">📍 عرض الموقع على الخريطة</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# الشروط (Expander المومض)
with st.expander("⚠️ ملاحظات وشروط الصيانة الهامة (يرجى القراءة)"):
    st.markdown("""
        <div style="direction: rtl; text-align: right; line-height: 1.8; padding: 10px;">
            1️⃣ فحص الجهاز (في حال رفض التصليح): <b>1000 دج</b> ثمن الفحص والجهد.<br>
            2️⃣ تصليح البطاقة الأم (Carte Mère): تبدأ الأسعار من <b>3000 دج</b>.<br>
            3️⃣ <b>الموافقة:</b> يتم التصليح تلقائياً إذا كان السعر أقل من 4000 دج، ما فوق ذلك ننتظر تأكيدك.<br>
            4️⃣ <b>تنبيهات:</b> اربط حسابك بـ <b>Telegram</b> لتصلك رسالة فور جاهزية جهازك.
        </div>
    """, unsafe_allow_html=True)

# البحث والنتائج
c1, c2 = st.columns([2, 1])

with c1:
    st.markdown("### 🔍 تتبع حالة جهازك")
    u_phone = st.text_input("أدخل رقم الهاتف المسجل:", placeholder="07XXXXXXXX")
    
    if u_phone:
        df_dev = fetch_devices(u_phone)
        if df_dev.empty:
            st.warning("لم يتم العثور على أجهزة مرتبطة بهذا الرقم.")
        else:
            for _, row in df_dev.iterrows():
                stt = str(row.get("Statut", "En attente"))
                
                # إعدادات شريط التقدم
                p_percent = 100 if stt == "Prêt" else 65 if stt == "En Cours" else 25
                p_color = "#238636" if stt == "Prêt" else "#1f6feb"
                
                st.markdown(f"""
                    <div class="device-card">
                        <div class="card-top">
                            <span style="font-weight: bold; font-size: 1.1rem; color: #58a6ff !important;">#{row.get('ID')} | {row.get('Appareil')}</span>
                            <span style="background: {p_color}; padding: 3px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: bold;">{stt}</span>
                        </div>
                        <div style="padding: 20px;">
                            <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
                                <span><b>المشكلة:</b> {row.get('Panne')}</span>
                                <span style="color: #d29922 !important;"><b>التكلفة:</b> {row.get('Prix')} DZD</span>
                            </div>
                            <div class="progress-container">
                                <div class="progress-fill" style="width: {p_percent}%; background: {p_color}; box-shadow: 0 0 10px {p_color};"></div>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <small style="opacity: 0.6;">تاريخ الدخول: {row.get('Date_Entree')}</small>
                                {f'<span style="color: #3fb950 !important; font-size: 0.8rem; font-weight: bold;">🛡️ ضمان الصيانة مفعل</span>' if stt == "Prêt" else ''}
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

with c2:
    st.markdown("### 🤖 إشعارات التلغرام")
    if u_phone and len(normalize_phone(u_phone)) >= 9:
        qr_link = f"https://t.me/{BOT_USERNAME}?start={normalize_phone(u_phone)}"
        qr_img = qrcode.make(qr_link)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), width=180, caption="امسح الرمز للربط")
        st.link_button("🚀 ربط الحساب الآن", qr_link, use_container_width=True)
    else:
        st.info("أدخل رقم هاتفك لظهور رابط الربط.")

# --- 5. تشغيل البوت ---
def start_bot():
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    @bot.message_handler(commands=["start"])
    def handle_sync(m):
        cmd_args = m.text.split()
        if len(cmd_args) > 1:
            p_end = normalize_phone(cmd_args[1])[-9:]
            db_ref = db.reference("atelier")
            data = db_ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p_end):
                        db_ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.send_message(m.chat.id, "✅ InfoDoc: تم تفعيل الإشعارات بنجاح!")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_running" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_running"] = True
