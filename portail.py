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

def get_warranty_stats(date_sortie_str):
    if not date_sortie_str or str(date_sortie_str).strip() == "---":
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            date_s = datetime.strptime(str(date_sortie_str).strip(), fmt)
            diff_days = (datetime.now() - date_s).days
            remaining_days = max(30 - diff_days, 0)
            percent = (remaining_days / 30) * 100
            expired = diff_days > 30
            return {"percent": percent, "is_expired": expired, "days_left": remaining_days}
        except: continue
    return None

# --- 3. تصميم الـ CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    .stApp { background: #0d1117; color: white; }
    .hero-box { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); border: 1px solid #30363d; border-radius: 15px; padding: 25px; margin-bottom: 20px; }
    .main-title { font-family: 'Orbitron'; color: #58a6ff; font-size: 2.2rem; font-weight: 900; }
    
    /* أنيميشن زر التلغرام العلوي */
    @keyframes pulse-blue {
        0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(34, 158, 217, 0.7); }
        70% { transform: scale(1.02); box-shadow: 0 0 0 10px rgba(34, 158, 217, 0); }
        100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(34, 158, 217, 0); }
    }

    .tg-top-btn {
        display: block; background: #229ED9; color: white !important; text-align: center;
        padding: 15px; border-radius: 12px; text-decoration: none; font-family: 'Cairo';
        font-weight: bold; margin-bottom: 20px; animation: pulse-blue 2s infinite;
        border: 1px solid rgba(255,255,255,0.1);
    }

    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; position: relative; }
    .w-expired-label { background: rgba(248, 81, 73, 0.1); color: #f85149; font-weight: bold; font-family: 'Cairo'; border: 1px solid #f85149; padding: 8px; border-radius: 8px; text-align: center; margin-top: 10px; }
    
    .status-badge { padding: 4px 12px; border-radius: 5px; font-weight: bold; font-size: 0.8rem; font-family: 'Orbitron'; }
    </style>
""", unsafe_allow_html=True)

# --- 4. العنوان الرئيسي ---
st.markdown('<div class="main-title" style="text-align:center; margin-bottom:20px;">INFODOC TECHNOLOGY</div>', unsafe_allow_html=True)

# --- 5. البحث وتدفق البيانات ---
phone_raw = st.text_input("🔍 أدخل رقم هاتفك لتتبع أجهزتك:", key="search_input", placeholder="05XXXXXXXX")

status_config = {
    "En Cours": {"color": "#1f6feb", "prog": 33},
    "Réparable": {"color": "#39c5bb", "prog": 66},
    "Prêt": {"color": "#3fb950", "prog": 100},
    "Livré & Payé": {"color": "#a371f7", "is_delivered": True},
    "Livré (Dette)": {"color": "#d29922", "is_delivered": True},
    "Non Réparable": {"color": "#f85149", "prog": 100},
    "Annulé": {"color": "#8b949e", "prog": 0}
}

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            my_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم.")
            else:
                # --- زر التلغرام العلوي (يظهر فقط إذا لم يتم الربط بعد) ---
                is_linked = any(str(d.get("Telegram_ID", "")).strip() != "" for d in my_devices)
                if not is_linked:
                    tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                    st.markdown(f'<a href="{tg_url}" target="_blank" class="tg-top-btn">🚀 ربط الهاتف بالتلغرام لتلقي الإشعارات الفورية</a>', unsafe_allow_html=True)
                
                for d in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = d.get("Statut", "En Cours")
                    cfg = status_config.get(stat, {"color": "#8b949e", "prog": 0})
                    is_delivered = cfg.get("is_delivered", False)
                    
                    st.markdown(f"""
                        <div class="device-card" style="border-right: 6px solid {cfg['color']};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <b style="font-family: 'Orbitron'; color: #58a6ff; font-size: 1.1rem;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span class="status-badge" style="background: {cfg['color']}; color: #0d1117;">{stat.upper()}</span>
                            </div>
                            <div style="margin: 15px 0;">
                    """, unsafe_allow_html=True)

                    # --- منطق تبديل الأشرطة ---
                    if is_delivered:
                        # إظهار شريط الضمان فقط
                        w = get_warranty_stats(d.get("Date_Sortie"))
                        if w:
                            if w["is_expired"]:
                                st.markdown('<div class="w-expired-label">❌ GARANTIE EXPIRÉ (الضمان منتهي)</div>', unsafe_allow_html=True)
                            else:
                                st.markdown(f"""
                                    <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #3fb950; margin-bottom: 5px; font-family:'Cairo';">
                                        <span>🛡️ شريط الضمان (متبقي: {int(w['days_left'])} يوم)</span>
                                        <span>{int(w['percent'])}%</span>
                                    </div>
                                    <div style="width: 100%; background: #21262d; height: 10px; border-radius: 10px; overflow: hidden;">
                                        <div style="width: {w['percent']}%; background: linear-gradient(90deg, #3fb950, #2ea043); height: 100%; transition: 1s;"></div>
                                    </div>
                                """, unsafe_allow_html=True)
                    else:
                        # إظهار شريط الصيانة العادي
                        prog = cfg.get("prog", 0)
                        st.markdown(f"""
                            <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #8b949e; margin-bottom: 5px;">
                                <span>🛠️ تقدم عملية الصيانة</span>
                                <span>{prog}%</span>
                            </div>
                            <div style="width: 100%; background: #21262d; height: 10px; border-radius: 10px; overflow: hidden;">
                                <div style="width: {prog}%; background: {cfg['color']}; height: 100%; transition: 0.5s;"></div>
                            </div>
                            <div style="margin-top:10px; font-size:0.9rem; color:#8b949e;">⚠️ العطل المذكور: {d.get('Panne')}</div>
                        """, unsafe_allow_html=True)

                    st.markdown(f"""
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.85rem; font-family: 'Cairo'; margin-top: 15px; border-top: 1px solid #30363d; padding-top: 10px;">
                                <div>📅 استلام: {d.get('Date_Entree')}</div>
                                <div>🕒 تسليم: {d.get('Date_Sortie', '---')}</div>
                                <div style="color: #58a6ff; font-weight: bold; font-size:1rem;">💰 السعر: {d.get('Prix')} دج</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

# --- 6. تشغيل بوت التلغرام (في الخلفية) ---
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
                bot.send_message(m.chat.id, "✅ ممتاز! تم ربط حسابك بنجاح. ستصلك الإشعارات هنا فور تغيير حالة أي جهاز خاص بك.")
    bot.polling(none_stop=True)

if "bot_running" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_running"] = True
