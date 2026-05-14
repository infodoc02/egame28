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
            firebase_admin.initialize_app(cred, {
                'databaseURL': st.secrets["DB_URL"]
            })
        except Exception as e:
            st.error(f"فشل الاتصال: {e}")

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
                    msg = "✅ تم تفعيل إشعارات InfoDoc بنجاح لهذا الرقم."
                else:
                    msg = "⚠️ لم نجد جهازاً مسجلاً بهذا الرقم حالياً."
                safe_send(bot, chat_id, msg)
            except Exception:
                safe_send(bot, chat_id, "❌ حدث خطأ أثناء الربط.")
        else:
            safe_send(bot, chat_id, "👋 مرحباً بك في InfoDoc.")
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

def get_shop_status():
    try:
        status = db.reference("shop_settings/is_open").get()
        return True if status is None else status
    except Exception:
        return True

# --- واجهة Streamlit والإعدادات البصرية ---
st.set_page_config(page_title="InfoDoc - Portail Client", page_icon="📱", layout="wide")

if "bot_thread" not in st.session_state:
    try:
        threading.Thread(target=run_bot, daemon=True).start()
        st.session_state["bot_thread"] = True
    except Exception:
        st.session_state["bot_thread"] = False

# --- CSS الكامل بدون حذف ---
st.markdown("""
    <style>
    @keyframes pulseStatus {
        0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }
        70% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
        100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
    }
    .status-badge {
        padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: bold;
        display: inline-flex; align-items: center; gap: 6px;
    }
    .status-open { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; animation: pulseStatus 2s infinite; }
    .status-closed { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }
    .stApp {
        background: radial-gradient(circle at 10% 10%, rgba(56,189,248,.20) 0%, transparent 25%),
                    radial-gradient(circle at 85% 20%, rgba(34,197,94,.14) 0%, transparent 23%),
                    linear-gradient(135deg, #020617 0%, #0b1220 35%, #0f172a 100%);
        color: #e5ecf8;
    }
    .bg-circuit {
        position: fixed; inset: 0; pointer-events: none; z-index: -1; opacity: 0.35;
        background-image: linear-gradient(rgba(56,189,248,0.18) 1px, transparent 1px),
                          linear-gradient(90deg, rgba(56,189,248,0.18) 1px, transparent 1px);
        background-size: 38px 38px;
    }
    .portal-wrap { position: relative; border-radius: 22px; overflow: hidden; margin-bottom: 1.1rem; border: 1px solid rgba(56,189,248,0.45); }
    .circuit-bg { position: absolute; inset: 0; background: linear-gradient(135deg, #020617 0%, #0b1220 40%, #1e3a8a 100%); }
    .scan-line {
        position: absolute; left: 0; right: 0; height: 100px;
        background: linear-gradient(180deg, transparent 0%, rgba(56,189,248,0.2) 50%, transparent 100%);
        animation: pulseLineB 4.5s linear infinite;
    }
    @keyframes pulseLineB { 0% { transform: translateY(-100%); } 100% { transform: translateY(300%); } }
    .hero-card { position: relative; z-index: 2; padding: 1.5rem; backdrop-filter: blur(2px); }
    .hero-title { font-size: 1.7rem; font-weight: 900; }
    .contact-info-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 10px; margin-top: 15px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 15px;
    }
    .contact-item { font-size: 0.85rem; display: flex; align-items: center; gap: 8px; color: #bfd4ff; }
    .section-card { border: 1px solid rgba(56,189,248,0.45); border-radius: 16px; padding: 1rem; background: rgba(15, 23, 42, 0.55); margin-bottom: 0.8rem; }
    .dev-card { border: 1px solid rgba(56,189,248,0.35); border-radius: 14px; padding: 0.9rem; background: rgba(15, 23, 42, 0.72); margin-bottom: .55rem; }
    .dev-head { font-weight: 800; color: #f8fbff; }
    .chip { display: inline-block; padding: .2rem .6rem; border-radius: 999px; font-size: .75rem; font-weight: 700; margin-top: 5px; }
    .chip-ready { background: rgba(34,197,94,.18); color: #86efac; border: 1px solid rgba(134,239,172,.35); }
    .chip-work { background: rgba(56,189,248,.18); color: #7dd3fc; border: 1px solid rgba(125,211,252,.35); }
    .chip-other { background: rgba(251,191,36,.18); color: #fde68a; border: 1px solid rgba(253,230,138,.35); }
    .notice-box {
        background: rgba(251, 191, 36, 0.1); border-right: 4px solid #fbbf24;
        padding: 15px; border-radius: 8px; font-size: 0.9rem; line-height: 1.6; color: #fde68a;
    }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="bg-circuit"></div>', unsafe_allow_html=True)

# --- عرض معلومات المحل في الهيرو ---
shop_open = get_shop_status()
status_html = '<span class="status-badge status-open">● Ouvert - مفتوح</span>' if shop_open else '<span class="status-badge status-closed">○ Fermé - مغلق</span>'

st.markdown(f"""
    <div class="portal-wrap">
        <div class="circuit-bg"></div>
        <div class="scan-line"></div>
        <div class="hero-card">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div class="hero-title">بوابة الزبائن InfoDoc</div>
                {status_html}
            </div>
            <div class="contact-info-grid">
                <div class="contact-item">📞 0798661900</div>
                <div class="contact-item">📍 الشلف وسط المدينة - OPGI</div>
                <div class="contact-item">🔵 Facebook: InfoDoc</div>
                <div class="contact-item">⚫ TikTok: @infodoc02</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- قسم الملاحظات والقوانين الجديدة ---
with st.container():
    st.markdown("""
    <div class="notice-box">
        <b>📝 ملاحظات هامة:</b><br>
        • في حالة كان الجهاز قابل للتصليح ورفضتم التصليح، يترتب دفع مبلغ <b>1000 دج</b> ثمن الفحص والفتح والغلق.<br>
        • أسعار التصليح (عند العمل على البطاقة الأم) تبدأ من <b>3000 دج</b>.<br>
        • <b>نظام الأسعار:</b> إذا كان السعر بين 3000 و 4000 دج نصلح مباشرة، فوق 4000 دج ننتظر موافقتكم عبر رسالة.<br>
        • <b>للتواصل الجيد:</b> يرجى تحميل تطبيق <b>تلغرام</b> وربطه عبر الزر أدناه لتلقي التنبيهات فوراً.
    </div>
    """, unsafe_allow_html=True)

st.write("")

# --- منطقة الاستعلام ---
st.markdown('<div class="section-card">🔍 أدخل رقم هاتفك المسجل لمتابعة أجهزتك</div>', unsafe_allow_html=True)
phone = st.text_input("phone", placeholder="0XXXXXXXXX", label_visibility="collapsed")
phone_n = normalize_phone(phone)

if phone_n and len(phone_n) >= 9:
    # جلب البيانات
    df = fetch_customer_devices(phone_n)
    
    # تفعيل التلغرام
    st.subheader("🔔 إشعارات Telegram")
    col_t1, col_t2 = st.columns([2, 1])
    with col_t1:
        st.info("لضمان وصول التحديثات فوراً، تأكد من ربط حسابك بالضغط على الزر")
        st.link_button("🚀 تفعيل الإشعارات عبر Telegram", telegram_link(phone_n))
    with col_t2:
        st.image(telegram_qr_bytes(phone_n), caption="QR Code للربط", width=120)

    st.divider()
    
    # عرض الأجهزة
    st.subheader("📋 قائمة أجهزتي")
    if df.empty:
        st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم حالياً.")
    else:
        for _, r in df.iterrows():
            stt = str(r.get("Statut", "")).strip()
            cls = "chip-ready" if stt == "Prêt" else "chip-work" if stt in ["En Cours", "En attente"] else "chip-other"
            
            st.markdown(f"""
                <div class="dev-card">
                    <div class="dev-head">#{int(pd.to_numeric(r.get("ID", 0), errors="coerce") or 0)} - {str(r.get("Appareil", "---"))}</div>
                    <div style="font-size: 0.88rem; margin-top: 5px; opacity: 0.9;">
                        <b>العطل:</b> {str(r.get("Panne", "---"))}<br>
                        <b>السعر:</b> {float(pd.to_numeric(r.get("Prix", 0), errors="coerce") or 0):,.0f} DA<br>
                        <b>تاريخ الدخول:</b> {str(r.get("Date_Entree", "---"))}
                    </div>
                    <span class="chip {cls}">{stt or '---'}</span>
                </div>
                """, unsafe_allow_html=True)

        with st.expander("عرض الجدول الكامل"):
            st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("الرجاء إدخال رقم هاتفك بالأسفل")
