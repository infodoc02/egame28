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

# --- منطق قاعدة البيانات والبوت ---
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
    except:
        return True

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
                msg = "✅ تم تفعيل الإشعارات بنجاح!" if updated > 0 else "⚠️ يرجى تسجيل جهازك في المحل أولاً."
                bot.send_message(chat_id, msg)
    bot.remove_webhook()
    bot.polling(none_stop=True)

# --- واجهة المستخدم (CSS المحسن للقراءة) ---
st.set_page_config(page_title="InfoDoc - بوابة الزبائن", page_icon="📱", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;900&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }

    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #020617 100%);
        color: #f1f5f9; /* نص فاتح جداً للوضوح */
    }

    /* كرت الرأس الرئيسي */
    .hero-container {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 20px;
        padding: 2rem;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }

    .main-title {
        color: #38bdf8;
        font-size: 2.5rem;
        font-weight: 900;
        margin-bottom: 0.5rem;
    }

    .info-text { color: #cbd5e1; font-size: 1.1rem; }

    /* أيقونات ومعلومات الاتصال */
    .contact-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
        margin-top: 1.5rem;
    }

    .contact-item {
        background: rgba(255, 255, 255, 0.05);
        padding: 15px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.1);
        color: #f8fafc;
        text-align: center;
    }

    /* حالة المحل */
    .status-badge {
        padding: 6px 16px;
        border-radius: 50px;
        font-weight: bold;
        font-size: 0.9rem;
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }
    .open { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }
    .closed { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }

    /* صندوق الملاحظات الذهبي */
    .policy-box {
        background: rgba(251, 191, 36, 0.1);
        border-right: 5px solid #fbbf24;
        border-radius: 12px;
        padding: 20px;
        margin: 20px 0;
        color: #fef3c7; /* نص ذهبي فاتح */
        line-height: 1.8;
    }

    /* كروت الأجهزة */
    .device-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 15px;
    }
    .device-card b { color: #38bdf8; }
    
    /* تعديل مدخلات النصوص لتكون واضحة */
    input { color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- جلب حالة المحل ---
shop_open = get_shop_status()
status_class = "open" if shop_open else "closed"
status_text = "● مفتوح الآن" if shop_open else "○ مغلق حالياً"

# --- واجهة العرض ---

# 1. الرأس
st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
            <div class="main-title">إنفو دوك للتكنولوجيا (InfoDoc)</div>
            <div class="status-badge {status_class}">{status_text}</div>
        </div>
        <p class="info-text">المركز التجاري OPGI، الطابق السفلي - الشلف وسط المدينة</p>
        
        <div class="contact-grid">
            <div class="contact-item">📞 0798661900</div>
            <div class="contact-item">🔵 فيسبوك: InfoDoc</div>
            <div class="contact-item">⚫ تيك توك: @infodoc02</div>
            <div class="contact-item">📍 الموقع: الشلف وسط المدينة</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# 2. الملاحظات الهامة (بالعربية الفصحى)
st.markdown("""
    <div class="policy-box">
        <h3 style="margin-top:0; color:#fbbf24;">⚠️ شروط وملاحظات الصيانة:</h3>
        • في حالة كان الجهاز قابلاً للتصليح وتم رفض العملية من قبل الزبون، يتوجب دفع مبلغ <b>1000 دج</b> ثمن الفحص والتشخيص.<br>
        • أسعار التصليح (عند العمل على اللوحة الأم) تبدأ من <b>3000 دج</b> فما فوق.<br>
        • إذا كانت تكلفة التصليح تتراوح بين <b>3000 و 4000 دج</b>، يتم البدء في العمل مباشرة.<br>
        • في حال تجاوزت التكلفة <b>4000 دج</b>، ستصلك رسالة لطلب الموافقة أو الرفض قبل البدء.<br>
        • لضمان تواصل أفضل، يرجى تحميل تطبيق <b>تلغرام</b> وربطه عبر الزر الموجود في الأسفل.
    </div>
    """, unsafe_allow_html=True)

# 3. نظام الاستعلام
col_search, col_space = st.columns([2, 1])

with col_search:
    st.markdown("### 🔍 تتبع حالة جهازك")
    phone_input = st.text_input("أدخل رقم الهاتف المسجل لدينا:", placeholder="مثال: 0798661900")
    phone_n = normalize_phone(phone_input)

    if phone_n and len(phone_n) >= 9:
        df = fetch_customer_devices(phone_n)
        if df.empty:
            st.warning("لم يتم العثور على أي أجهزة مسجلة بهذا الرقم.")
        else:
            st.success(f"تم العثور على {len(df)} جهاز.")
            for _, r in df.iterrows():
                # تحويل الحالات للعربية
                raw_status = str(r.get("Statut", ""))
                status_map = {"Prêt": "جاهز للتسليم ✅", "En Cours": "قيد التصليح 🛠️", "En attente": "في الانتظار ⏳"}
                arabic_status = status_map.get(raw_status, raw_status)
                
                st.markdown(f"""
                    <div class="device-card">
                        <div style="font-size: 1.2rem; font-weight: bold; color: #38bdf8; margin-bottom: 10px;">
                            رقم الجهاز: #{int(r.get("ID", 0))} | {r.get("Appareil", "---")}
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                            <div><b>الحالة:</b> {arabic_status}</div>
                            <div><b>العطل:</b> {r.get("Panne", "---")}</div>
                            <div><b>السعر التقديري:</b> {float(r.get("Prix", 0)):,.0f} دج</div>
                            <div><b>تاريخ الدخول:</b> {r.get("Date_Entree", "---")}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

# 4. قسم التلغرام
st.divider()
st.markdown("### 🔔 تفعيل التنبيهات الفورية")
if phone_n and len(phone_n) >= 9:
    t_col1, t_col2 = st.columns([1, 2])
    with t_col1:
        qr_img = qrcode.make(f"https://t.me/{BOT_USERNAME}?start={phone_n}")
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="امسح الرمز للربط السريع", width=150)
    with t_col2:
        st.write("للحصول على إشعارات فورية عند جاهزية جهازك، يرجى الضغط على الزر أدناه وتفعيل البوت:")
        st.link_button("🚀 ربط حساب تلغرام (Telegram)", f"https://t.me/{BOT_USERNAME}?start={phone_n}")
else:
    st.info("يرجى إدخال رقم الهاتف أولاً لتفعيل ميزة التنبيهات.")

# تشغيل البوت
if "bot_thread" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_thread"] = True
