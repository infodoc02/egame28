import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime, timedelta
import threading
import telebot

# --- 1. الإعدادات الأساسية ---
st.set_page_config(page_title="InfoDoc Pro Ultimate V3", page_icon="📱", layout="wide")

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

def calculate_warranty(date_sortie_str):
    if not date_sortie_str or date_sortie_str == "---": return None
    try:
        date_s = datetime.strptime(date_sortie_str, "%Y-%m-%d")
        days_passed = (datetime.now() - date_s).days
        percent = min(max((days_passed / 30) * 100, 0), 100)
        return {"percent": percent, "is_expired": days_passed > 30, "days_left": max(30 - days_passed, 0)}
    except: return None

# --- 3. تصميم CSS (الوميض + الأزرار + الحالات) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    .stApp { background: #0d1117; color: white; }
    
    /* الوميض */
    @keyframes blink { 0%, 100% { opacity: 1; box-shadow: 0 0 10px #3fb950; } 50% { opacity: 0.5; box-shadow: none; } }
    @keyframes blink-red { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    .status-open { color: #3fb950; border: 2px solid #3fb950; padding: 5px 15px; border-radius: 8px; animation: blink 2s infinite; font-family: 'Orbitron'; }
    .garantie-expired { color: #f85149; font-weight: 900; animation: blink-red 1s infinite; text-align: center; display: block; }

    /* البطاقة والأزرار */
    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 15px; }
    
    div.stDownloadButton > button {
        background-color: #1f6feb !important; color: white !important;
        border: none !important; border-radius: 8px !important; font-weight: bold !important; width: 100%;
    }
    div.stDownloadButton > button:hover { background-color: #388bfd !important; }

    .premium-btn { text-decoration: none; color: white !important; background: #21262d; border: 1px solid #30363d; padding: 10px; border-radius: 8px; text-align: center; display: flex; align-items: center; justify-content: center; gap: 8px; font-family: 'Cairo'; }
    </style>
""", unsafe_allow_html=True)

# --- 4. الهيدر ---
try: is_open = db.reference("shop_settings/is_open").get()
except: is_open = True
status_label = '<span class="status-open">ATELIER OUVERT</span>' if is_open else '<span style="color:#f85149; border:2px solid #f85149; padding:5px 15px; border-radius:8px;">FERMÉ</span>'

st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h1 style="font-family: 'Orbitron'; color: #58a6ff; margin:0;">INFODOC PRO</h1>
        {status_label}
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 25px;">
        <a href="tel:0798661900" class="premium-btn">📞 0798661900</a>
        <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="premium-btn">📍 TENES, CHLEF</a>
        <a href="https://www.facebook.com/100095433977319/" target="_blank" class="premium-btn">📘 Facebook</a>
    </div>
""", unsafe_allow_html=True)

# --- 5. منطق البحث والعرض ---
phone_input = st.text_input("🔍 أدخل رقم هاتفك لتتبع أجهزتك:", placeholder="0798661900")

status_config = {
    "En Cours": {"color": "#1f6feb", "prog": 33},
    "Réparable": {"color": "#39c5bb", "prog": 66},
    "Prêt": {"color": "#3fb950", "prog": 100},
    "Non Réparable": {"color": "#f85149", "prog": 100},
    "Livré & Payé": {"color": "#3fb950", "prog": 100},
    "Livré (Dette)": {"color": "#d29922", "prog": 100},
    "Annulé": {"color": "#f85149", "prog": 0}
}

if phone_input:
    phone_n = normalize_phone(phone_input)
    if len(phone_n) >= 9:
        data = db.reference("atelier").get()
        if data:
            devices = [dict(v, _id=k) for k, v in data.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if devices:
                # زر التليغرام (صغير ومركزي)
                if not any(d.get("Telegram_ID") for d in devices):
                    c1, c2, c3 = st.columns([1, 1, 1])
                    with c2: st.link_button("🔔 تفعيل التليغرام", f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}")

                for d in sorted(devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = d.get("Statut", "En Cours")
                    cfg = status_config.get(stat, {"color": "#8b949e", "prog": 0})
                    
                    # منطق السعر لـ Annulé
                    price = "1000" if stat == "Annulé" else d.get('Prix', '0')
                    price_note = " (حق الفحص والتشخيص)" if stat == "Annulé" else ""

                    st.markdown(f"""
                        <div class="device-card" style="border-right: 5px solid {cfg['color']};">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <b style="font-size: 1.2rem; color: #58a6ff;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span style="background: {cfg['color']}; padding: 3px 10px; border-radius: 5px; font-weight: bold; font-size: 0.8rem;">{stat}</span>
                            </div>
                            
                            <!-- شريط الصيانة (يصل لـ 100% عند Prêt) -->
                            <div style="margin-bottom: 15px;">
                                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #8b949e;">
                                    <span>تقدم الصيانة</span> <span>{cfg['prog']}%</span>
                                </div>
                                <div style="width:100%; background:#21262d; height:8px; border-radius:10px;">
                                    <div style="width:{cfg['prog']}%; background:{cfg['color']}; height:100%; border-radius:10px;"></div>
                                </div>
                            </div>
                    """, unsafe_allow_html=True)

                    # --- شريط الضمان (يظهر فقط في Livré & Payé) ---
                    if stat == "Livré & Payé":
                        w = calculate_warranty(d.get("Date_Sortie"))
                        if w:
                            if w['is_expired']:
                                st.markdown('<span class="garantie-expired">⚠️ GARANTIE EXPIRÉ</span>', unsafe_allow_html=True)
                            else:
                                st.markdown(f"""
                                    <div style="margin-top: 10px; border-top: 1px solid #30363d; padding-top: 10px;">
                                        <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #3fb950;">
                                            <span>🛡️ عدّاد الضمان (30 يوم)</span> <span>باقي {w['days_left']} يوم</span>
                                        </div>
                                        <div style="width:100%; background:#21262d; height:8px; border-radius:10px; margin-top:5px;">
                                            <div style="width:{w['percent']}%; background:#3fb950; height:100%; border-radius:10px;"></div>
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)

                    st.markdown(f"""
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.9rem; margin-top: 10px; font-family: 'Cairo';">
                                <div>📅 الدخول: {d.get('Date_Entree')}</div>
                                <div style="color: #58a6ff; font-weight: bold;">💰 السعر: {price} دج <small style="font-size:0.6rem; color:#8b949e;">{price_note}</small></div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    st.download_button(f"📄 تحميل الوصل #{d.get('ID')}", f"ID: {d.get('ID')}\nDevice: {d.get('Appareil')}\nPrice: {price} DZD", key=f"dl_{d.get('_id')}")
            else:
                st.error("لم يتم العثور على أي أجهزة.")

# --- 6. تليغرام بوت في الخلفية ---
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
                bot.reply_to(m, "✅ تم ربط الحساب بنجاح!")
    bot.polling(none_stop=True)

if "bot_running" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_running"] = True
