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
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None"]:
        return None
    # تجربة عدة صيغ للتاريخ لضمان عملها
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
    
    /* أنيميشن زر التلغرام */
    @keyframes pulse-blue {
        0% { transform: scale(1); box-shadow: 0 0 10px rgba(34, 158, 217, 0.4); }
        50% { transform: scale(1.02); box-shadow: 0 0 25px rgba(34, 158, 217, 0.8); }
        100% { transform: scale(1); box-shadow: 0 0 10px rgba(34, 158, 217, 0.4); }
    }

    .tg-link-btn {
        display: block; background: #229ED9; color: white !important; 
        text-align: center; padding: 18px; border-radius: 15px; 
        text-decoration: none; font-family: 'Cairo'; font-weight: 900;
        margin: 20px 0; animation: pulse-blue 2s infinite;
        font-size: 1.1rem; border: 2px solid rgba(255,255,255,0.2);
    }

    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; }
    .w-expired-box { background: rgba(248, 81, 73, 0.1); color: #f85149; font-weight: bold; font-family: 'Cairo'; border: 1px solid #f85149; padding: 12px; border-radius: 10px; text-align: center; margin-top: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 4. واجهة التطبيق ---
st.markdown('<h1 style="text-align:center; font-family:Orbitron; color:#58a6ff;">INFODOC TECHNOLOGY</h1>', unsafe_allow_html=True)

phone_raw = st.text_input("🔍 أدخل رقم هاتفك لتتبع أجهزتك:", key="search_input")

status_config = {
    "En Cours": {"color": "#1f6feb", "prog": 33},
    "Réparable": {"color": "#39c5bb", "prog": 66},
    "Prêt": {"color": "#3fb950", "prog": 100},
    "Non Réparable": {"color": "#f85149", "prog": 100},
    "Annulé": {"color": "#8b949e", "prog": 0}
}

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            # جلب الأجهزة المرتبطة بالرقم
            my_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم.")
            else:
                # --- منطق زر التلغرام (يظهر إذا وجدنا جهاز واحد على الأقل غير مربوط) ---
                has_unlinked = any(str(d.get("Telegram_ID", "")).strip() in ["", "None"] for d in my_devices)
                if has_unlinked:
                    tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                    st.markdown(f'<a href="{tg_url}" target="_blank" class="tg-link-btn">🚀 ربط الهاتف بالتلغرام لتلقي إشعارات فورية</a>', unsafe_allow_html=True)
                
                for d in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = str(d.get("Statut", "En Cours"))
                    # التحقق إذا كانت الحالة هي تسليم (بأي شكل من الأشكال)
                    is_delivered = "Livré" in stat
                    cfg = status_config.get(stat, {"color": "#a371f7", "prog": 100})
                    
                    st.markdown(f"""
                        <div class="device-card" style="border-right: 6px solid {cfg['color'] if not is_delivered else '#3fb950'};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <b style="font-family: 'Orbitron'; color: #58a6ff; font-size: 1.1rem;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span style="background: {cfg['color'] if not is_delivered else '#3fb950'}; color: #0d1117; padding: 4px 12px; border-radius: 5px; font-weight: bold; font-size: 0.8rem;">{stat.upper()}</span>
                            </div>
                            <div style="margin: 15px 0;">
                    """, unsafe_allow_html=True)

                    if is_delivered:
                        # --- شريط الضمان ---
                        w = get_warranty_stats(d.get("Date_Sortie"))
                        if w:
                            if w["is_expired"]:
                                st.markdown('<div class="w-expired-box">❌ GARANTIE EXPIRÉE (الضمان منتهي)</div>', unsafe_allow_html=True)
                            else:
                                st.markdown(f"""
                                    <div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: #3fb950; margin-bottom: 8px; font-family:'Cairo'; font-weight:bold;">
                                        <span>🛡️ شريط الضمان (متبقي: {int(w['days_left'])} يوم)</span>
                                        <span>{int(w['percent'])}%</span>
                                    </div>
                                    <div style="width: 100%; background: #21262d; height: 12px; border-radius: 10px; overflow: hidden; border: 1px solid rgba(63, 185, 80, 0.3);">
                                        <div style="width: {w['percent']}%; background: linear-gradient(90deg, #3fb950, #2ea043); height: 100%; transition: 1.5s;"></div>
                                    </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.info("🕒 في انتظار تسجيل تاريخ الخروج لتفعيل الضمان.")
                    else:
                        # --- شريط الصيانة ---
                        prog = cfg.get("prog", 0)
                        st.markdown(f"""
                            <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #8b949e; margin-bottom: 5px;">
                                <span>🛠️ تقدم عملية الصيانة</span>
                                <span>{prog}%</span>
                            </div>
                            <div style="width: 100%; background: #21262d; height: 10px; border-radius: 10px; overflow: hidden;">
                                <div style="width: {prog}%; background: {cfg['color']}; height: 100%;"></div>
                            </div>
                            <div style="margin-top:10px; font-size:0.9rem; color:#8b949e;">⚠️ المشكل: {d.get('Panne')}</div>
                        """, unsafe_allow_html=True)

                    st.markdown(f"""
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.85rem; font-family: 'Cairo'; margin-top: 15px; border-top: 1px solid #30363d; padding-top: 10px;">
                                <div>📅 دخول: {d.get('Date_Entree')}</div>
                                <div>🕒 خروج: {d.get('Date_Sortie', '---')}</div>
                                <div style="color: #58a6ff; font-weight: bold;">💰 السعر: {d.get('Prix')} دج</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

# --- 6. بوت التلغرام ---
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
