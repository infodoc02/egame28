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

# --- الإعدادات الأساسية ---
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
            st.error(f"فشل الاتصال بـ Firebase: {e}")

ensure_firebase()

# --- الدوال البرمجية (Logic) ---
def normalize_phone(phone: str) -> str:
    p = str(phone or "").replace(".0", "").strip()
    p = re.sub(r"\D", "", p)
    if p.startswith("213"): p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]: p = "0" + p
    return p

def telegram_qr_bytes(phone: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(f"https://t.me/{BOT_USERNAME}?start={phone}")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def run_bot():
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    @bot.message_handler(commands=["start"])
    def handle_start(message):
        args = message.text.split()
        chat_id = str(message.chat.id)
        if len(args) > 1:
            phone = normalize_phone(args[1])
            last9 = phone[-9:]
            ref = db.reference("atelier")
            raw = ref.get()
            if raw and isinstance(raw, dict):
                updated = 0
                for key, val in raw.items():
                    tel = normalize_phone(val.get("Telephone", ""))
                    if tel.endswith(last9):
                        ref.child(key).update({"Telegram_ID": chat_id})
                        updated += 1
                msg = "✅ تم تفعيل الإشعارات بنجاح!" if updated > 0 else "⚠️ سجل جهازك أولاً."
                bot.send_message(chat_id, msg)
    bot.remove_webhook()
    bot.polling(none_stop=True)

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

# --- تصميم الواجهة الاحترافية (CSS) ---
st.set_page_config(page_title="InfoDoc - Expert Repair", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
    
    * { font-family: 'Cairo', sans-serif; }
    
    .stApp {
        background: #050a18;
        background-image: radial-gradient(circle at 20% 30%, #1e3a8a 0%, transparent 20%),
                          radial-gradient(circle at 80% 70%, #1e40af 0%, transparent 20%);
    }

    /* كرت الهيرو الاحترافي */
    .hero-section {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 25px;
        padding: 30px;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 20px 50px rgba(0,0,0,0.5);
    }

    .shop-title {
        font-size: 3rem;
        font-weight: 900;
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 10px;
    }

    /* أيقونات التواصل */
    .contact-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 15px;
        margin-top: 20px;
    }

    .contact-card {
        background: rgba(56, 189, 248, 0.1);
        padding: 12px;
        border-radius: 15px;
        border: 1px solid rgba(56, 189, 248, 0.2);
        font-size: 0.9rem;
        transition: 0.3s;
    }
    .contact-card:hover { transform: translateY(-5px); background: rgba(56, 189, 248, 0.2); }

    /* ملاحظات الأسعار - تصميم مميز */
    .policy-container {
        background: linear-gradient(135deg, rgba(251, 191, 36, 0.1) 0%, rgba(245, 158, 11, 0.05) 100%);
        border-right: 5px solid #fbbf24;
        border-radius: 15px;
        padding: 20px;
        margin: 20px 0;
    }

    .policy-item {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 8px;
        color: #fef3c7;
    }

    /* كروت الأجهزة */
    .device-card {
        background: rgba(15, 23, 42, 0.8);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 18px;
        padding: 20px;
        margin-bottom: 15px;
        transition: 0.4s;
    }
    .device-card:hover { border-color: #38bdf8; box-shadow: 0 0 20px rgba(56, 189, 248, 0.2); }

    .status-badge {
        padding: 5px 15px;
        border-radius: 10px;
        font-weight: bold;
        float: left;
    }
    
    /* أنيميشن النبض للمحل المفتوح */
    .pulse-green {
        width: 10px; height: 10px; background: #22c55e;
        border-radius: 50%; display: inline-block;
        box-shadow: 0 0 0 rgba(34, 197, 94, 0.4);
        animation: pulse 2s infinite;
        margin-right: 8px;
    }
    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); } 70% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); } 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); } }
    </style>
    """, unsafe_allow_html=True)

# --- الهيكل البصري ---

# 1. الهيرو (العنوان والمعلومات)
st.markdown(f"""
    <div class="hero-section">
        <div class="shop-title">INFODOC TECHNOLOGY</div>
        <div style="font-size: 1.2rem; opacity: 0.8; margin-bottom: 20px;">
            <span class="pulse-green"></span> مركز الصيانة المعتمد - مصلحة الزبائن
        </div>
        <div class="contact-grid">
            <div class="contact-card">📞 <b>0798661900</b></div>
            <div class="contact-card">📍 <b>الشلف - وسط المدينة</b><br><small>المركز التجاري OPGI</small></div>
            <div class="contact-card">🔵 <b>Facebook</b><br>InfoDoc</div>
            <div class="contact-card">⚫ <b>TikTok</b><br>@infodoc02</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# 2. قسم السياسات والأسعار (اللمسة الاحترافية)
st.markdown("""
    <div class="policy-container">
        <h4 style="color: #fbbf24; margin-top:0;">⚠️ ميثاق الصيانة والأسعار</h4>
        <div class="policy-item">📌 <b>الفحص والتشخيص:</b> في حال رفض التصليح بعد الفتح، يتم دفع 1000 دج ثمن الفحص والجهد.</div>
        <div class="policy-item">💳 <b>البطاقة الأم (Motherboard):</b> أسعار العمل الدقيق تبدأ من 3000 دج.</div>
        <div class="policy-item">⚙️ <b>نظام الموافقة:</b> نصلح مباشرة حتى 4000 دج. فوق ذلك، ننتظر تأكيدك عبر التلغرام.</div>
        <div class="policy-item">📱 <b>تواصل ذكي:</b> لضمان حقك وسرعة الرد، نعتمد تطبيق Telegram كمنصة رسمية.</div>
    </div>
    """, unsafe_allow_html=True)

# 3. منطقة الاستعلام
col_main, col_side = st.columns([2, 1])

with col_main:
    st.markdown("### 🔍 تتبع حالة جهازك")
    phone = st.text_input("أدخل رقم هاتفك المسجل", placeholder="06XXXXXXXX", label_visibility="collapsed")
    phone_n = normalize_phone(phone)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("❌ لم نجد أي جهاز مرتب بهذا الرقم. تأكد من الرقم الصحيح.")
        else:
            for _, r in df.iterrows():
                stt = str(r.get("Statut", "En attente"))
                color = "#22c55e" if stt == "Prêt" else "#38bdf8" if "Cours" in stt else "#94a3b8"
                
                st.markdown(f"""
                    <div class="device-card">
                        <span class="status-badge" style="background: {color}22; color: {color}; border: 1px solid {color};">
                            {stt}
                        </span>
                        <div style="font-size: 1.3rem; font-weight: bold; color: #fff;">
                            #{int(r.get("ID", 0))} | {r.get("Appareil", "جهاز غير محدد")}
                        </div>
                        <hr style="opacity: 0.1; margin: 10px 0;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.95rem;">
                            <div>🛠️ <b>العطل:</b> {r.get("Panne", "---")}</div>
                            <div>💰 <b>التكلفة:</b> {float(r.get("Prix", 0)):,.0f} دج</div>
                            <div>📅 <b>تاريخ الاستلام:</b> {r.get("Date_Entree", "---")}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

with col_side:
    st.markdown("### 🤖 ربط التلغرام")
    if phone_n and len(phone_n) >= 9:
        st.write("استلم إشعارات فورية عند انتهاء التصليح:")
        st.image(telegram_qr_bytes(phone_n), use_container_width=True)
        st.link_button("فتح تلغرام مباشرة", f"https://t.me/{BOT_USERNAME}?start={phone_n}", use_container_width=True)
        st.caption("افتح الرابط واضغط على Start")
    else:
        st.info("أدخل رقم الهاتف أولاً لإظهار رمز الربط.")

# تشغيل البوت في الخلفية
if "bot_thread" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_thread"] = True
