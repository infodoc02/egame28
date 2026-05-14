import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
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

# تحسين دالة الضمان
def get_warranty_stats(date_sortie_str):
    if not date_sortie_str or date_sortie_str == "---":
        return None
    try:
        # تحويل التاريخ الحالي وتاريخ الخروج
        date_s = datetime.strptime(date_sortie_str, "%Y-%m-%d")
        today = datetime.now()
        diff_days = (today - date_s).days
        
        total_warranty_days = 30
        remaining_days = max(0, total_warranty_days - diff_days)
        
        # حساب النسبة المئوية المتبقية (تبدأ من 100% وتنقص)
        percent = (remaining_days / total_warranty_days) * 100
        expired = diff_days > total_warranty_days
        
        return {"percent": percent, "is_expired": expired, "remaining": remaining_days}
    except: return None

# --- 3. تصميم الـ CSS المعدل ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    .stApp { background: #0d1117; color: white; }
    .hero-box { background: linear-gradient(180deg, #161b22 0%, #0d1117 100%); border: 1px solid #30363d; border-radius: 15px; padding: 25px; margin-bottom: 20px; }
    .main-title { font-family: 'Orbitron'; color: #58a6ff; font-size: 2.2rem; font-weight: 900; }
    
    /* أنيميشن الربط المشع */
    @keyframes pulse-blue {
        0% { box-shadow: 0 0 0 0 rgba(0, 136, 204, 0.7); }
        70% { box-shadow: 0 0 0 15px rgba(0, 136, 204, 0); }
        100% { box-shadow: 0 0 0 0 rgba(0, 136, 204, 0); }
    }
    .tg-glow-button {
        background: #0088cc; color: white !important; padding: 12px 20px;
        border-radius: 10px; text-decoration: none; display: flex;
        align-items: center; justify-content: center; gap: 10px;
        font-family: 'Cairo'; font-weight: bold; margin: 10px 0;
        animation: pulse-blue 2s infinite; border: none;
    }

    .status-open { color: #3fb950; border: 2px solid #3fb950; padding: 6px 15px; border-radius: 8px; font-weight: bold; }
    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; }
    .w-expired-label { color: #f85149; font-weight: bold; border: 1px solid #f85149; padding: 10px; border-radius: 8px; text-align: center; background: rgba(248, 81, 73, 0.1); }
    </style>
""", unsafe_allow_html=True)

# --- 4. واجهة المستخدم ---
st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-family: 'Cairo'; color: #8b949e;">
        <div>{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
        <div style="font-weight: 900; color: #58a6ff;">INFODOC TECHNOLOGY</div>
    </div>
""", unsafe_allow_html=True)

# --- 5. البحث ---
st.markdown("### 🔍 تتبع حالة جهازك")
phone_raw = st.text_input("أدخل رقم هاتفك المسجل:", placeholder="0xxxxxxxxx")

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            my_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم.")
            else:
                # --- زر التليجرام المشع في مكان ممتاز ---
                if not any(str(d.get("Telegram_ID", "")).strip() != "" for d in my_devices):
                    tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                    st.markdown(f'<a href="{tg_url}" target="_blank" class="tg-glow-button">🚀 ربط الهاتف بالتليجرام ليصلك إشعار عند الجاهزية</a>', unsafe_allow_html=True)

                for d in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = d.get("Statut", "En Cours")
                    
                    # عرض الكارد
                    st.markdown(f"""
                        <div class="device-card">
                            <div style="display: flex; justify-content: space-between;">
                                <b style="font-family: 'Orbitron'; color: #58a6ff;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span style="color: #3fb950; font-weight: bold;">{stat}</span>
                            </div>
                            <hr style="border-color: #30363d;">
                    """, unsafe_allow_html=True)

                    # منطق الضمان المحسن
                    if stat == "Livré & Payé":
                        w = get_warranty_stats(d.get("Date_Sortie"))
                        if w:
                            if w["is_expired"]:
                                st.markdown('<div class="w-expired-label">❌ ضمان منتهي (Garantie Expiré)</div>', unsafe_allow_html=True)
                            else:
                                color = "#3fb950" if w['percent'] > 20 else "#f85149"
                                st.markdown(f"""
                                    <div style="margin-top: 10px;">
                                        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: {color};">
                                            <span>🛡️ حالة الضمان (متبقي {w['remaining']} يوم)</span>
                                            <span>{int(w['percent'])}%</span>
                                        </div>
                                        <div style="width: 100%; background: #30363d; height: 12px; border-radius: 10px; margin-top: 5px;">
                                            <div style="width: {w['percent']}%; background: {color}; height: 100%; border-radius: 10px; transition: 1s;"></div>
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)

                    st.markdown(f"""
                            <div style="margin-top: 15px; font-family: 'Cairo'; font-size: 0.9rem; color: #8b949e;">
                                📍 العطل: {d.get('Panne')} | 💰 السعر: {d.get('Prix')} دج
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

# --- 6. بوت التليجرام (Thread) ---
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
                bot.reply_to(m, "✅ تم ربط حسابك بنجاح!")
    bot.polling(none_stop=True)

if "bot_running" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_running"] = True
