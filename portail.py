import os
import threading
from datetime import datetime
import firebase_admin
import pandas as pd
import streamlit as st
import telebot
import qrcode
from io import BytesIO
from firebase_admin import credentials, db, initialize_app

# الطريقة المباشرة (تخدم إذا كان الملف موجود في Secrets)
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "fallback_token_here")
BOT_USERNAME = st.secrets.get("BOT_USERNAME", "default_bot")
DB_URL = st.secrets.get("DB_URL", "https://your-default-db.firebaseio.com/")

def ensure_firebase():
    # التحقق إذا كان التطبيق مفعل مسبقاً
    if not firebase_admin._apps:
        try:
            # التأكد من أننا نستخدم بيانات المشروع الجديد info-2b186
            cred_dict = dict(st.secrets["firebase"])
            
            # معالجة المفتاح الخاص (السطر الجديد)
            if "\\n" in cred_dict["private_key"]:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
            cred = credentials.Certificate(cred_dict)
            
            # تهيئة التطبيق مع تحديد الرابط بدقة
            firebase_admin.initialize_app(cred, {
                'databaseURL': st.secrets["DB_URL"]
            })
            # st.success("Connected to Firebase!") # للتحقق فقط، احذفه لاحقاً
        except Exception as e:
            st.error(f"فشل الاتصال: {e}")
    else:
        # إذا كان التطبيق موجوداً، نتأكد من أنه يستخدم الرابط الصحيح
        pass

ensure_firebase()

def normalize_phone(phone: str) -> str:
    phone = str(phone or "").replace("+213", "0").replace(" ", "").replace(".0", "").strip()
    if phone.startswith("213"):
        phone = "0" + phone[3:]
    if len(phone) == 9 and phone[0] in ["5", "6", "7"]:
        phone = "0" + phone
    return phone

def telegram_qr_bytes(phone: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(telegram_link(phone))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def telegram_link(phone: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={phone}"


def safe_send(bot: telebot.TeleBot, chat_id: str, message: str) -> bool:
    if not chat_id:
        return False
    try:
        bot.send_message(chat_id, message, parse_mode="Markdown")
        return True
    except Exception:
        return False


def link_telegram_id_to_phone(phone: str, telegram_id: str) -> int:
    """
    Link telegram_id to all atelier tickets matching phone last 9 digits.
    Returns number of updated records.
    """
    phone = normalize_phone(phone)
    last9 = phone[-9:]
    ref = db.reference("atelier")
    raw = ref.get()
    if not raw or not isinstance(raw, dict):
        return 0
    updated = 0
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        tel = normalize_phone(val.get("Telephone", ""))
        if tel.endswith(last9):
            ref.child(key).update({"Telegram_ID": str(telegram_id)})
            updated += 1
    return updated


def run_bot():
    bot = telebot.TeleBot(TELEGRAM_TOKEN)

    @bot.message_handler(commands=["start"])
    def handle_start(message):
        args = message.text.split()
        chat_id = str(message.chat.id)
        if len(args) > 1:
            phone = normalize_phone(args[1])
            try:
                updated = link_telegram_id_to_phone(phone, chat_id)
                if updated > 0:
                    msg = (
                        "✅ تم تفعيل إشعارات InfoDoc بنجاح لهذا الرقم.\n\n"
                        "من الآن فصاعداً ستصلك تحديثات حالة جهازك مباشرة هنا."
                    )
                else:
                    msg = (
                        "⚠️ لم نجد جهازاً مسجلاً بهذا الرقم حالياً.\n\n"
                        "إذا سجلت جهازك لاحقاً بنفس الرقم سيتم الربط تلقائياً."
                    )
                safe_send(bot, chat_id, msg)
            except Exception:
                safe_send(bot, chat_id, "❌ حدث خطأ أثناء الربط، حاول لاحقاً.")
        else:
            safe_send(bot, chat_id, "👋 مرحباً بك. فعّل الإشعارات من بوابة InfoDoc.")

    bot.remove_webhook()
    bot.polling(none_stop=True, skip_pending=True)


def fetch_customer_devices(phone: str) -> pd.DataFrame:
    phone = normalize_phone(phone)
    if len(phone) < 9:
        return pd.DataFrame()
    last9 = phone[-9:]
    raw = db.reference("atelier").get()
    if not raw or not isinstance(raw, dict):
        return pd.DataFrame()
    rows = []
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        tel = normalize_phone(val.get("Telephone", ""))
        if tel.endswith(last9):
            r = val.copy()
            r["_id"] = key
            rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty and "ID" in df.columns:
        df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)
        df = df.sort_values("ID", ascending=False)
    # Hide delivered & paid tickets from customer list
    if not df.empty and "Statut" in df.columns:
        statut_clean = df["Statut"].astype(str).str.strip()
        df = df[statut_clean != "Livré & Payé"]
    return df


def is_telegram_linked(df: pd.DataFrame) -> bool:
    if df.empty or "Telegram_ID" not in df.columns:
        return False
    tg = df["Telegram_ID"].astype(str).str.strip()
    return ((tg.str.isdigit()) & (tg.str.len() > 5)).any()


# --- App ---
st.set_page_config(page_title="InfoDoc - Portail Client", page_icon="📱", layout="wide")

ensure_firebase()

if "bot_thread" not in st.session_state:
    try:
        threading.Thread(target=run_bot, daemon=True).start()
        st.session_state["bot_thread"] = True
    except Exception:
        st.session_state["bot_thread"] = False

st.markdown(
    """
    <style>
    @keyframes floatGlow {
        0% { transform: translateY(0px); opacity: 0.55; }
        50% { transform: translateY(-8px); opacity: 0.95; }
        100% { transform: translateY(0px); opacity: 0.55; }
    }
    @keyframes pulseLine {
        0% { background-position: 0% 50%; }
        100% { background-position: 200% 50%; }
    }
    .portal-wrap {
        position: relative;
        border-radius: 18px;
        overflow: hidden;
        margin-bottom: 1rem;
        border: 1px solid rgba(59,130,246,0.30);
    }
    .circuit-bg {
        position: absolute;
        inset: 0;
        background:
            radial-gradient(circle at 18% 20%, rgba(56,189,248,0.35), transparent 22%),
            radial-gradient(circle at 82% 28%, rgba(34,197,94,0.25), transparent 22%),
            radial-gradient(circle at 35% 78%, rgba(59,130,246,0.30), transparent 25%),
            linear-gradient(135deg, #020617 0%, #0f172a 45%, #1e3a8a 100%);
    }
    .circuit-lines {
        position: absolute;
        inset: 0;
        background: linear-gradient(
            90deg,
            transparent 0%,
            rgba(14,165,233,0.0) 15%,
            rgba(14,165,233,0.45) 50%,
            rgba(14,165,233,0.0) 85%,
            transparent 100%
        );
        background-size: 200% 100%;
        animation: pulseLine 8s linear infinite;
        mix-blend-mode: screen;
    }
    .hero-card {
        position: relative;
        z-index: 2;
        border-radius: 16px;
        padding: 1.25rem 1.35rem;
        color: #eef6ff;
        backdrop-filter: blur(1px);
    }
    .chip-dot {
        width: 10px; height: 10px; border-radius: 50%;
        background: #38bdf8; display: inline-block; margin-inline-end: 8px;
        animation: floatGlow 2.3s ease-in-out infinite;
        box-shadow: 0 0 14px rgba(56,189,248,0.9);
    }
    .hero-card {
        margin-bottom: 0.25rem;
        box-shadow: 0 15px 35px rgba(2, 6, 23, 0.45);
    }
    .hero-title { font-size: 1.55rem; font-weight: 900; margin-bottom: 0.2rem; letter-spacing: .2px; }
    .hero-subtitle { font-size: 0.96rem; opacity: 0.95; }
    .section-card {
        border: 1px solid #dbeafe;
        border-radius: 14px;
        padding: 0.95rem 1rem;
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
        box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06);
        margin-bottom: 0.8rem;
    }
    .mini-tech {
        border: 1px solid rgba(148,163,184,0.25);
        background: #0b1220;
        color: #cbd5e1;
        border-radius: 12px;
        padding: 0.65rem 0.8rem;
        font-size: 0.84rem;
        margin-bottom: 0.65rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <div class="portal-wrap">
        <div class="circuit-bg"></div>
        <div class="circuit-lines"></div>
        <div class="hero-card">
            <div class="hero-title"><span class="chip-dot"></span>بوابة الزبائن InfoDoc</div>
            <div class="hero-subtitle">متابعة احترافية لحالة الأجهزة، الأسعار، والتنبيهات الفورية عبر Telegram.</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="section-card">
        <div style="font-size: 0.95rem; font-weight: 700; color: #0f172a; margin-bottom: 0.35rem;">
            📞 أدخل رقم هاتفك
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

phone = st.text_input("رقم الهاتف", placeholder="0XXXXXXXXX", label_visibility="collapsed")
phone_n = normalize_phone(phone)

if phone_n and len(phone_n) >= 9:
    a1, a2, a3 = st.columns(3)
    a1.markdown('<div class="mini-tech">🔧 Diagnostic Live</div>', unsafe_allow_html=True)
    a2.markdown('<div class="mini-tech">📡 Telegram Alert Ready</div>', unsafe_allow_html=True)
    a3.markdown('<div class="mini-tech">🧠 Smart Ticket Tracking</div>', unsafe_allow_html=True)

    df = fetch_customer_devices(phone_n)

    if df.empty:
        st.warning("⚠️ لا يوجد أجهزة مسجلة بهذا الرقم حالياً.")
        st.info("إذا كنت تريد تفعيل الإشعارات مسبقاً، يمكنك ذلك وسيتم الربط تلقائياً عند تسجيل جهازك بنفس الرقم.")
    else:
        st.success(f"✅ تم العثور على {len(df)} جهاز/تذكرة لهذا الرقم.")

    st.subheader("🔔 تفعيل إشعارات Telegram")
    if not df.empty and is_telegram_linked(df):
        st.success("✅ الإشعارات مفعّلة (Telegram مرتبط).")
    else:
        st.warning("⚠️ الإشعارات غير مفعّلة بعد.")
        t1, t2 = st.columns([2, 1])
        with t1:
            st.link_button("🚀 تفعيل الإشعارات عبر Telegram", telegram_link(phone_n))
            st.caption("بعد فتح الرابط اضغط Start داخل Telegram لإتمام الربط.")
        with t2:
            st.image(telegram_qr_bytes(phone_n), caption="QR Telegram", width=120)

    st.divider()
    st.subheader("📋 أجهزتي")
    if not df.empty:
        show_cols = []
        for c in ["ID", "Appareil", "Panne", "Statut", "Prix", "Date_Entree", "Date_Sortie"]:
            if c in df.columns:
                show_cols.append(c)
        st.dataframe(df[show_cols], use_container_width=True, hide_index=True)
else:
    st.info("أدخل رقم هاتفك لعرض قائمة الأجهزة.")
