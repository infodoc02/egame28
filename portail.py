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
    p = str(phone or "").replace(".0", "").strip()
    p = re.sub(r"\D", "", p)
    if p.startswith("213"):
        p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]:
        p = "0" + p
    return p

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
    .stApp {
        background:
            radial-gradient(circle at 10% 10%, rgba(56,189,248,.20) 0%, transparent 25%),
            radial-gradient(circle at 85% 20%, rgba(34,197,94,.14) 0%, transparent 23%),
            radial-gradient(circle at 70% 80%, rgba(59,130,246,.16) 0%, transparent 30%),
            linear-gradient(135deg, #020617 0%, #0b1220 35%, #0f172a 100%);
        color: #e5ecf8;
    }
    .main .block-container { padding-top: 1.6rem; }
    .bg-circuit {
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: -1;
        opacity: 0.35;
        background-image:
            linear-gradient(rgba(56,189,248,0.18) 1px, transparent 1px),
            linear-gradient(90deg, rgba(56,189,248,0.18) 1px, transparent 1px);
        background-size: 38px 38px;
        mask-image: radial-gradient(circle at center, black 40%, transparent 100%);
    }
    @keyframes floatGlow {
        0% { transform: translateY(0px); opacity: 0.55; }
        50% { transform: translateY(-8px); opacity: 0.95; }
        100% { transform: translateY(0px); opacity: 0.55; }
    }
    @keyframes pulseLineA {
        0% { background-position: 0% 50%; }
        100% { background-position: 200% 50%; }
    }
    @keyframes pulseLineB {
        0% { transform: translateY(-40%); opacity: 0; }
        35% { opacity: .55; }
        100% { transform: translateY(180%); opacity: 0; }
    }
    .portal-wrap {
        position: relative;
        border-radius: 22px;
        overflow: hidden;
        margin-bottom: 1.1rem;
        border: 1px solid rgba(56,189,248,0.45);
    }
    .circuit-bg {
        position: absolute;
        inset: 0;
        background:
            radial-gradient(circle at 18% 20%, rgba(56,189,248,0.50), transparent 28%),
            radial-gradient(circle at 82% 28%, rgba(34,197,94,0.35), transparent 27%),
            radial-gradient(circle at 35% 78%, rgba(59,130,246,0.45), transparent 30%),
            linear-gradient(135deg, #020617 0%, #0b1220 40%, #1e3a8a 100%);
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
        animation: pulseLineA 7s linear infinite;
        mix-blend-mode: screen;
    }
    .scan-line {
        position: absolute;
        left: 0; right: 0;
        height: 120px;
        background: linear-gradient(180deg, transparent 0%, rgba(56,189,248,0.22) 45%, transparent 100%);
        animation: pulseLineB 4.5s linear infinite;
        pointer-events: none;
    }
    .hero-card {
        position: relative;
        z-index: 2;
        border-radius: 20px;
        padding: 1.5rem 1.5rem;
        color: #eef6ff;
        backdrop-filter: blur(1.5px);
    }
    .chip-dot {
        width: 10px; height: 10px; border-radius: 50%;
        background: #38bdf8; display: inline-block; margin-inline-end: 8px;
        animation: floatGlow 2.3s ease-in-out infinite;
        box-shadow: 0 0 14px rgba(56,189,248,0.9);
    }
    .hero-card {
        margin-bottom: 0.35rem;
        box-shadow: 0 18px 40px rgba(2, 6, 23, 0.55);
    }
    .hero-title { font-size: 1.72rem; font-weight: 900; margin-bottom: 0.2rem; letter-spacing: .3px; }
    .hero-subtitle { font-size: 0.96rem; opacity: 0.95; }
    .section-card {
        border: 1px solid rgba(56,189,248,0.45);
        border-radius: 16px;
        padding: 1rem 1.05rem;
        background: rgba(15, 23, 42, 0.55);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.30);
        margin-bottom: 0.8rem;
    }
    .mini-tech {
        border: 1px solid rgba(56,189,248,0.35);
        background: rgba(15, 23, 42, 0.75);
        color: #dbeafe;
        border-radius: 12px;
        padding: 0.65rem 0.8rem;
        font-size: 0.84rem;
        margin-bottom: 0.65rem;
    }
    .dev-card {
        border: 1px solid rgba(56,189,248,0.35);
        border-radius: 14px;
        padding: 0.8rem 0.9rem;
        background: rgba(15, 23, 42, 0.72);
        margin-bottom: .55rem;
    }
    .dev-head { font-weight: 800; color: #f8fbff; margin-bottom: .22rem; }
    .dev-sub { color: #bfd4ff; font-size: .88rem; }
    .chip {
        display: inline-block;
        padding: .16rem .52rem;
        border-radius: 999px;
        font-size: .75rem;
        font-weight: 700;
        margin-top: .32rem;
    }
    .chip-ready { background: rgba(34,197,94,.18); color: #86efac; border: 1px solid rgba(134,239,172,.35); }
    .chip-work { background: rgba(56,189,248,.18); color: #7dd3fc; border: 1px solid rgba(125,211,252,.35); }
    .chip-other { background: rgba(251,191,36,.18); color: #fde68a; border: 1px solid rgba(253,230,138,.35); }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<div class="bg-circuit"></div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="portal-wrap">
        <div class="circuit-bg"></div>
        <div class="circuit-lines"></div>
        <div class="scan-line"></div>
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
        <div style="font-size: 0.95rem; font-weight: 700; color: #dbeafe; margin-bottom: 0.35rem;">
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
        for _, r in df.iterrows():
            stt = str(r.get("Statut", "")).strip()
            cls = "chip-other"
            if stt == "Prêt":
                cls = "chip-ready"
            elif stt in ["En Cours", "En attente"]:
                cls = "chip-work"
            st.markdown(
                f"""
                <div class="dev-card">
                    <div class="dev-head">#{int(pd.to_numeric(r.get("ID", 0), errors="coerce") or 0)} - {str(r.get("Appareil", "---"))}</div>
                    <div class="dev-sub">العطل: {str(r.get("Panne", "---"))}</div>
                    <div class="dev-sub">السعر: {float(pd.to_numeric(r.get("Prix", 0), errors="coerce") or 0):,.0f} DA</div>
                    <div class="dev-sub">الدخول: {str(r.get("Date_Entree", "---"))}</div>
                    <span class="chip {cls}">{stt or '---'}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with st.expander("عرض جدول الأجهزة (تفصيلي)"):
            show_cols = []
            for c in ["ID", "Appareil", "Panne", "Statut", "Prix", "Date_Entree", "Date_Sortie"]:
                if c in df.columns:
                    show_cols.append(c)
            st.dataframe(df[show_cols], use_container_width=True, hide_index=True)
else:
    st.info("أدخل رقم هاتفك لعرض قائمة الأجهزة.")
