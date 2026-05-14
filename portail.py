import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime, timedelta
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
    # تجربة أكثر من صيغة للتاريخ لضمان المرونة
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            date_s = datetime.strptime(str(date_sortie_str).strip(), fmt)
            diff_days = (datetime.now() - date_s).days
            # حساب النسبة المتبقية من الشهر (30 يوم)
            # إذا مر 0 يوم النسبة 100%، إذا مر 30 يوم النسبة 0%
            remaining_days = max(30 - diff_days, 0)
            percent = (remaining_days / 30) * 100
            expired = diff_days > 30
            return {"percent": percent, "is_expired": expired, "days_left": remaining_days}
        except: continue
    return None

# --- 3. تصميم الـ CSS المطور ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    .stApp { background: #0d1117; color: white; }
    .hero-box { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); border: 1px solid #30363d; border-radius: 15px; padding: 25px; margin-bottom: 20px; }
    .main-title { font-family: 'Orbitron'; color: #58a6ff; font-size: 2.2rem; font-weight: 900; }
    
    /* أنيميشن الحالات */
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; opacity: 1; } 50% { box-shadow: none; opacity: 0.7; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; opacity: 1; } 50% { box-shadow: none; opacity: 0.7; } }
    
    /* أنيميشن زر التلغرام المشع */
    @keyframes tg-glow {
        0% { box-shadow: 0 0 5px #229ED9; transform: scale(1); }
        50% { box-shadow: 0 0 20px #229ED9; transform: scale(1.05); }
        100% { box-shadow: 0 0 5px #229ED9; transform: scale(1); }
    }

    /* الزر العائم */
    .floating-tg {
        position: fixed;
        bottom: 30px;
        right: 30px;
        background: #229ED9;
        color: white !important;
        padding: 12px 20px;
        border-radius: 50px;
        text-decoration: none;
        font-family: 'Cairo';
        font-weight: bold;
        z-index: 999;
        display: flex;
        align-items: center;
        gap: 10px;
        animation: tg-glow 2s infinite;
        border: 2px solid rgba(255,255,255,0.2);
    }

    .status-open { color: #3fb950; border: 2px solid #3fb950; padding: 6px 15px; border-radius: 8px; animation: blink-green 2s infinite; font-weight: bold; font-family: 'Orbitron'; }
    .status-closed { color: #f85149; border: 2px solid #f85149; padding: 6px 15px; border-radius: 8px; animation: blink-red 2s infinite; font-weight: bold; font-family: 'Orbitron'; }

    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; }
    .w-expired-label { color: #f85149; font-weight: bold; font-family: 'Cairo'; border: 1px solid #f85149; padding: 5px; border-radius: 5px; text-align: center; margin-top:10px; }
    </style>
""", unsafe_allow_html=True)

# --- 4. الترحيب والمعلومات ---
curr_h = datetime.now().hour
greet = "صباح الخير" if 5 <= curr_h < 12 else "مساء الخير"
st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-family: 'Cairo'; color: #8b949e;">
        <div>{greet} زبوننا الكريم | الوقت الآن: {datetime.now().strftime('%H:%M')}</div>
        <div style="font-weight: 900; color: #58a6ff;">CHLEF, ALGERIA</div>
    </div>
""", unsafe_allow_html=True)

try: is_open = db.reference("shop_settings/is_open").get()
except: is_open = True
status_html = f'<span class="status-open">ATELIER OUVERT</span>' if is_open else f'<span class="status-closed">ATELIER FERMÉ</span>'

st.markdown(f"""
    <div class="hero-box">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            {status_html}
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-top: 20px;">
            <a href="tel:0798661900" style="text-decoration:none; color:white; background:#21262d; padding:10px; border-radius:8px; text-align:center;">📞 0798661900</a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" style="text-decoration:none; color:white; background:#21262d; padding:10px; border-radius:8px; text-align:center;">📍 موقع المحل</a>
            <a href="https://www.facebook.com/100095433977319/" target="_blank" style="text-decoration:none; color:white; background:#21262d; padding:10px; border-radius:8px; text-align:center;">📘 Facebook</a>
            <a href="https://www.tiktok.com/@infodoc02" target="_blank" style="text-decoration:none; color:white; background:#21262d; padding:10px; border-radius:8px; text-align:center;">📱 TikTok</a>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 5. البحث وتوزيع الألوان ---
st.markdown("### 🔍 تتبع حالة جهازك")
phone_raw = st.text_input("أدخل رقم هاتفك المسجل:", key="search_input")

status_config = {
    "En Cours": {"color": "#1f6feb", "prog": 33},
    "Réparable": {"color": "#39c5bb", "prog": 66},
    "Prêt": {"color": "#3fb950", "prog": 100},
    "Livré & Payé": {"color": "#a371f7", "prog": 100},
    "Livré (Dette)": {"color": "#d29922", "prog": 100},
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
                # زر التلغرام العائم يظهر هنا
                tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                st.markdown(f'<a href="{tg_url}" class="floating-tg">🚀 ربط التلغرام</a>', unsafe_allow_html=True)
                
                for d in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = d.get("Statut", "En Cours")
                    cfg = status_config.get(stat, {"color": "#8b949e", "prog": 0})
                    
                    st.markdown(f"""
                        <div class="device-card" style="border-right: 6px solid {cfg['color']};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <b style="font-family: 'Orbitron'; color: #58a6ff; font-size: 1.1rem;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span style="background: {cfg['color']}; color: #0d1117; padding: 4px 12px; border-radius: 5px; font-weight: bold; font-size: 0.8rem;">{stat.upper()}</span>
                            </div>
                            <div style="margin: 15px 0;">
                                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #8b949e; margin-bottom: 5px;">
                                    <span>تقدم الصيانة: {cfg['prog']}%</span>
                                    <span>العطل: {d.get('Panne')}</span>
                                </div>
                                <div style="width: 100%; background: #21262d; height: 10px; border-radius: 10px; overflow: hidden;">
                                    <div style="width: {cfg['prog']}%; background: {cfg['color']}; height: 100%; transition: 0.5s;"></div>
                                </div>
                            </div>
                    """, unsafe_allow_html=True)

                    # --- تعديل الضمان: يظهر لأي حالة تحتوي كلمة Livré ---
                    if "Livré" in stat:
                        w = get_warranty_stats(d.get("Date_Sortie"))
                        if w:
                            if w["is_expired"]:
                                st.markdown('<div class="w-expired-label">⚠️ Garantie expirée (الضمان منتهي)</div>', unsafe_allow_html=True)
                            else:
                                st.markdown(f"""
                                    <div style="margin-top: 15px; background: rgba(63, 185, 80, 0.1); padding: 10px; border-radius: 10px; border: 1px solid #3fb950;">
                                        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #3fb950; margin-bottom: 5px; font-family:'Cairo';">
                                            <span>🛡️ عداد الضمان (المتبقي: {int(w['days_left'])} يوم)</span>
                                            <span>{int(w['percent'])}%</span>
                                        </div>
                                        <div style="width: 100%; background: #21262d; height: 8px; border-radius: 10px; overflow: hidden;">
                                            <div style="width: {w['percent']}%; background: #3fb950; height: 100%; transition: 1s;"></div>
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)

                    st.markdown(f"""
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.9rem; font-family: 'Cairo'; margin-top: 10px;">
                                <div>📅 الدخول: {d.get('Date_Entree')}</div>
                                <div>🕒 الخروج: {d.get('Date_Sortie', '---')}</div>
                                <div style="color: #58a6ff; font-weight: bold;">💰 السعر: {d.get('Prix')} دج</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

# --- 6. بوت التليغرام (نفس المنطق) ---
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
