import os
import threading
from datetime import datetime
import firebase_admin
import pandas as pd
import streamlit as st
import telebot
from firebase_admin import credentials, db, initialize_app





def normalize_phone(phone: str) -> str:
    phone = str(phone or "").replace("+213", "0").replace(" ", "").replace(".0", "").strip()
    if phone.startswith("213"):
        phone = "0" + phone[3:]
    if len(phone) == 9 and phone[0] in ["5", "6", "7"]:
        phone = "0" + phone
    return phone


def ensure_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json_path)
        initialize_app(cred, {"databaseURL": DB_URL})


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
    .hero-card {
        background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 100%);
        border-radius: 14px;
        padding: 1.1rem 1.3rem;
        color: white;
        margin-bottom: 1rem;
        box-shadow: 0 10px 25px rgba(15, 23, 42, 0.2);
    }
    .hero-title { font-size: 1.4rem; font-weight: 800; margin-bottom: 0.25rem; }
    .hero-subtitle { font-size: 0.95rem; opacity: 0.92; }
    .section-card {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 0.9rem 1rem;
        background: #ffffff;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
        margin-bottom: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
    <div class="hero-card">
        <div class="hero-title">📱 بوابة الزبائن InfoDoc</div>
        <div class="hero-subtitle">تابع حالة جهازك، السعر، وفعل إشعارات Telegram مباشرة.</div>
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

phone = st.text_input("رقم الهاتف", placeholder="مثال: 0555123456", label_visibility="collapsed")
phone_n = normalize_phone(phone)

if phone_n and len(phone_n) >= 9:
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
        st.link_button("🚀 تفعيل الإشعارات عبر Telegram", telegram_link(phone_n))
        st.caption("بعد فتح الرابط اضغط Start داخل Telegram لإتمام الربط.")

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

