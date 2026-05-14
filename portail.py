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

# --- 3. تصميم الواجهة الفخم (Super Pro CSS) ---
st.set_page_config(page_title="InfoDoc VIP Portal", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@600;900&display=swap');
    
    /* الأساس */
    .stApp { background-color: #05070a !important; }
    * { font-family: 'Cairo', sans-serif; color: #ffffff !important; }

    /* أنيميشن */
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 20px rgba(63, 185, 80, 0.6); border-color: #3fb950; } 50% { box-shadow: 0 0 5px rgba(63, 185, 80, 0.2); border-color: transparent; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 20px rgba(248, 81, 73, 0.6); border-color: #f85149; } 50% { box-shadow: 0 0 5px rgba(248, 81, 73, 0.2); border-color: transparent; } }
    @keyframes slide-in { from { transform: translateX(20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    @keyframes pulse-gold { 0% { border-color: #d29922; } 50% { border-color: #ffcc00; box-shadow: 0 0 15px rgba(255, 204, 0, 0.4); } 100% { border-color: #d29922; } }

    /* الهيدر */
    .hero-container {
        background: linear-gradient(135deg, rgba(22, 27, 34, 0.8), rgba(13, 17, 23, 0.9));
        border: 1px solid #30363d;
        border-radius: 24px;
        padding: 40px;
        margin-bottom: 30px;
        backdrop-filter: blur(10px);
    }
    .main-title {
        font-family: 'Orbitron', sans-serif;
        font-size: clamp(1.5rem, 5vw, 3.5rem);
        font-weight: 900;
        background: linear-gradient(90deg, #58a6ff, #bc8cff, #58a6ff);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: shine 3s linear infinite;
    }
    @keyframes shine { to { background-position: 200% center; } }

    /* حالات الوميض */
    .status-open { border: 2px solid #3fb950; color: #3fb950 !important; padding: 10px 20px; border-radius: 12px; animation: blink-green 2s infinite; font-weight: 900; }
    .status-closed { border: 2px solid #f85149; color: #f85149 !important; padding: 10px 20px; border-radius: 12px; animation: blink-red 2s infinite; font-weight: 900; }

    /* Expander المومض */
    div[data-testid="stExpander"] {
        border: 2px solid #d29922 !important;
        border-radius: 15px !important;
        background: rgba(210, 153, 34, 0.05) !important;
        animation: pulse-gold 3s infinite;
        direction: rtl;
    }

    /* بطاقة الجهاز الجديدة */
    .pro-card {
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 20px;
        margin-bottom: 25px;
        overflow: hidden;
        animation: slide-in 0.5s ease-out;
    }
    .card-header {
        background: #161b22;
        padding: 20px;
        display: flex;
        justify-content: space-between;
        border-bottom: 1px solid #30363d;
    }
    .card-body { padding: 25px; }

    /* شريط التقدم الفعلي */
    .progress-track {
        background: #21262d;
        height: 14px;
        border-radius: 50px;
        margin: 20px 0;
        position: relative;
        overflow: hidden;
        border: 1px solid #30363d;
    }
    .progress-bar-fill {
        height: 100%;
        border-radius: 50px;
        transition: width 1.5s cubic-bezier(0.4, 0, 0.2, 1);
        background: linear-gradient(90deg, #1f6feb, #58a6ff);
        box-shadow: 0 0 15px rgba(88, 166, 255, 0.5);
    }

    /* ختم الضمان */
    .warranty-seal {
        background: linear-gradient(135deg, #238636, #2ea043);
        color: white !important;
        padding: 5px 15px;
        border-radius: 50px;
        font-size: 0.8rem;
        font-weight: 900;
        display: flex;
        align-items: center;
        gap: 5px;
        border: 2px solid rgba(255,255,255,0.2);
    }

    /* أزرار التواصل */
    .map-btn {
        background: #238636;
        color: white !important;
        text-decoration: none;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        display: block;
        font-weight: bold;
        transition: 0.3s;
        border: 1px solid #3fb950;
    }
    .map-btn:hover { background: #2ea043; transform: scale(1.02); }

    .stTextInput input {
        background: #0d1117 !important;
        border: 1px solid #30363d !important;
        border-radius: 10px !important;
        padding: 12px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 4. العرض ---

# الترحيب
st.markdown(f"<p style='text-align: right; opacity: 0.6; margin-bottom: 0;'>{datetime.now().strftime('%H:%M')} | مرحباً بك في InfoDoc</p>", unsafe_allow_html=True)

# الهيدر الاحترافي
is_open = get_shop_status()
st_html = f'<div class="status-open">ATELIER OUVERT</div>' if is_open else f'<div class="status-closed">ATELIER FERMÉ</div>'

st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            {st_html}
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-top: 30px;">
            <div style="background: rgba(88, 166, 255, 0.1); padding: 15px; border-radius: 15px; border: 1px solid rgba(88, 166, 255, 0.2);">
                📞 <b style="font-size: 1.1rem;">0798661900</b>
            </div>
            <div style="background: rgba(255, 255, 255, 0.05); padding: 15px; border-radius: 15px; border: 1px solid rgba(255,255,255,0.1);">
                📍 <b>الشلف - المركز التجاري OPGI</b>
            </div>
            <a href="https://www.google.com/maps/search/?api=1&query=Chlef+OPGI" target="_blank" class="map-btn">📍 موقعنا على الخريطة</a>
        </div>
    </div>
    """, unsafe_allow_html=True)

# الشروط (التي تومض)
with st.expander("⚠️ ملاحظات وشروط الصيانة الهامة (يرجى الاطلاع)"):
    st.markdown("""
        <div style="direction: rtl; text-align: right; line-height: 2; padding: 15px; font-size: 1.1rem;">
            ✅ فحص الجهاز عند رفض التصليح: <b>1000 دج</b>.<br>
            ✅ تصليح اللوحة الأم يبدأ من <b>3000 دج</b>.<br>
            ✅ التصليح التلقائي للأعطال تحت 4000 دج.<br>
            ✅ تواصل معنا عبر <b>تلغرام</b> للحصول على تنبيهات فورية.
        </div>
    """, unsafe_allow_html=True)

# محرك البحث
col_a, col_b = st.columns([2, 1])

with col_a:
    st.markdown("### 🔍 تتبع حالة جهازك")
    user_p = st.text_input("أدخل رقم هاتفك للبحث:", placeholder="07XXXXXXXX")
    
    if user_p:
        df_res = fetch_devices(user_p)
        if df_res.empty:
            st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم حالياً.")
        else:
            for _, r in df_res.iterrows():
                status = str(r.get("Statut", "En attente"))
                
                # إعدادات الشريط والضمان
                progress = 100 if status == "Prêt" else 60 if status == "En Cours" else 20
                bar_color = "#3fb950" if status == "Prêt" else "#58a6ff"
                
                warranty_html = '<div class="warranty-seal">🛡️ Garantie 30 Jours</div>' if status == "Prêt" else ''
                
                st.markdown(f"""
                    <div class="pro-card">
                        <div class="card-header">
                            <span style="font-size: 1.2rem; font-weight: 900; color: #58a6ff !important;">#{r.get('ID')} | {r.get('Appareil')}</span>
                            {warranty_html}
                        </div>
                        <div class="card-body">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                                <span style="font-size: 1.1rem;">🛠️ المشكلة: <b>{r.get('Panne')}</b></span>
                                <span style="color: #ffcc00 !important; font-weight: bold; font-size: 1.2rem;">{r.get('Prix')} دج</span>
                            </div>
                            <div style="text-align: right; margin-bottom: 5px;"><small style="opacity: 0.7;">حالة التصليح: {status}</small></div>
                            <div class="progress-track">
                                <div class="progress-bar-fill" style="width: {progress}%; background: {bar_color};"></div>
                            </div>
                            <div style="opacity: 0.5; font-size: 0.8rem; margin-top: 10px;">📅 تاريخ الاستلام: {r.get('Date_Entree')}</div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

with col_b:
    st.markdown("### 🤖 إشعارات تلغرام")
    if user_p and len(normalize_phone(user_p)) >= 9:
        qr_url = f"https://t.me/{BOT_USERNAME}?start={normalize_phone(user_p)}"
        img = qrcode.make(qr_url)
        b = BytesIO()
        img.save(b, format="PNG")
        st.image(b.getvalue(), width=180)
        st.link_button("🚀 تفعيل التنبيهات الآن", qr_url, use_container_width=True)
    else:
        st.info("💡 أدخل رقم هاتفك لربط حسابك بتلغرام وتلقي الإشعارات.")

# --- 5. البوت ---
def run_bot():
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    @bot.message_handler(commands=["start"])
    def sync(m):
        args = m.text.split()
        if len(args) > 1:
            p_end = normalize_phone(args[1])[-9:]
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p_end):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.send_message(m.chat.id, "✅ InfoDoc: تم ربط جهازك! ستصلك رسالة هنا فور جاهزيته.")
    bot.remove_webhook()
    bot.polling(none_stop=True)

if "bot_v3" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_v3"] = True
