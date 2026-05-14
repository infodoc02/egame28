import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime, timedelta
import threading
import telebot

# --- 1. الإعدادات والاتصال ---
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

def calculate_warranty(date_sortie_str):
    """حساب نسبة مرور شهر الضمان"""
    if not date_sortie_str or date_sortie_str == "---":
        return None
    try:
        date_s = datetime.strptime(date_sortie_str, "%Y-%m-%d")
        today = datetime.now()
        days_passed = (today - date_s).days
        
        # الضمان لمدة 30 يوم
        percent = min(max((days_passed / 30) * 100, 0), 100)
        is_expired = days_passed > 30
        return {"percent": percent, "days_left": max(30 - days_passed, 0), "is_expired": is_expired}
    except: return None

# --- 3. تصميم الـ CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    .stApp { background: #0d1117; color: white; }
    .hero-box { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; }
    .main-title { font-family: 'Orbitron'; color: #58a6ff; font-size: 2rem; font-weight: 900; }
    
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    .status-open { color: #3fb950; border: 1px solid #3fb950; padding: 4px 10px; border-radius: 6px; animation: blink 2s infinite; font-family: 'Orbitron'; }
    
    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 15px; margin-bottom: 15px; }
    
    /* ستايل شريط الضمان */
    .w-label { font-size: 0.8rem; font-family: 'Cairo'; margin-bottom: 4px; display: flex; justify-content: space-between; }
    .w-expired-text { color: #f85149; font-weight: bold; animation: blink 1s infinite; }
    
    div.stDownloadButton > button {
        background-color: #21262d !important; color: #58a6ff !important; border: 1px solid #30363d !important;
        border-radius: 8px !important; width: 100% !important; transition: 0.3s !important;
    }
    div.stDownloadButton > button:hover { background-color: #58a6ff !important; color: #0d1117 !important; }
    </style>
""", unsafe_allow_html=True)

# --- 4. الهيدر ---
st.markdown(f"""
    <div class="hero-box">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div class="main-title">INFODOC</div>
            <span class="status-open">SHOP ONLINE</span>
        </div>
        <div style="display: flex; gap: 10px; margin-top: 15px;">
            <a href="tel:0798661900" style="text-decoration:none; color:#8b949e; font-size:0.9rem;">📞 0798661900</a>
            <a href="#" style="text-decoration:none; color:#8b949e; font-size:0.9rem;">📍 Chlef, Tenes</a>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 5. البحث والمنطق ---
phone_raw = st.text_input("🔍 تتبع حالة جهازك (رقم الهاتف):")

# إعدادات الحالات
status_map = {
    "En Cours": {"color": "#1f6feb", "prog": 33},
    "Réparable": {"color": "#39c5bb", "prog": 66},
    "Prêt": {"color": "#3fb950", "prog": 100},
    "Non Réparable": {"color": "#f85149", "prog": 100},
    "Livré & Payé": {"color": "#3fb950", "prog": 100},
    "Livré (Dette)": {"color": "#d29922", "prog": 100},
    "Annulé": {"color": "#f85149", "prog": 0}
}

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            my_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not my_devices:
                st.warning("لم يتم العثور على أجهزة.")
            else:
                # زر تليغرام صغير
                if not any(d.get("Telegram_ID") for d in my_devices):
                    st.link_button("🔔 تفعيل تنبيهات تليغرام", f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}")

                for d in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = d.get("Statut", "En Cours")
                    cfg = status_map.get(stat, {"color": "#8b949e", "prog": 0})
                    
                    # معالجة حالة Annulé
                    price = d.get('Prix')
                    if stat == "Annulé":
                        price = "1000"
                        price_info = "(تكاليف الفحص)"
                    else: price_info = ""

                    st.markdown(f"""
                        <div class="device-card" style="border-right: 4px solid {cfg['color']};">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                                <b style="font-family: 'Orbitron'; color: #58a6ff;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span style="background:{cfg['color']}; color:white; padding:2px 8px; border-radius:4px; font-size:0.7rem;">{stat}</span>
                            </div>
                            
                            <!-- شريط تقدم الصيانة -->
                            <div style="margin-bottom: 15px;">
                                <div class="w-label"><span>تقدم الصيانة</span> <span>{cfg['prog']}%</span></div>
                                <div style="width:100%; background:#21262d; height:6px; border-radius:10px;">
                                    <div style="width:{cfg['prog']}%; background:{cfg['color']}; height:100%; border-radius:10px;"></div>
                                </div>
                            </div>
                    """, unsafe_allow_html=True)

                    # --- منطق الضمان (يظهر فقط عند التسليم والدفع) ---
                    if stat == "Livré & Payé":
                        w = calculate_warranty(d.get("Date_Sortie"))
                        if w:
                            w_color = "#f85149" if w['is_expired'] else "#3fb950"
                            w_text = "GARANTIE EXPIRÉ ❌" if w['is_expired'] else f"باقي من الضمان: {w['days_left']} يوم"
                            st.markdown(f"""
                                <div style="margin-top: 10px; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                                    <div class="w-label">
                                        <span style="font-weight:bold;">🛡️ حالة الضمان</span>
                                        <span class="{'w-expired-text' if w['is_expired'] else ''}">{w_text}</span>
                                    </div>
                                    <div style="width:100%; background:#21262d; height:8px; border-radius:10px;">
                                        <div style="width:{w['percent']}%; background:{w_color}; height:100%; border-radius:10px; transition: 1s;"></div>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)

                    st.markdown(f"""
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.8rem; margin-top: 10px; font-family: 'Cairo';">
                                <div>📅 الدخول: {d.get('Date_Entree')}</div>
                                <div style="color:#58a6ff;">💰 السعر: {price} دج {price_info}</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    st.download_button(f"📄 تحميل الوصل #{d.get('ID')}", f"ID: {d.get('ID')}\nStatus: {stat}\nPrice: {price}", key=f"dl_{d.get('ID')}")

# --- 6. التليغرام في الخلفية ---
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
