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

def get_warranty_info(status, date_sortie_str):
    """الضمان يظهر حصراً في حالة Livré & Payé"""
    if status != "Livré & Payé" or not date_sortie_str or date_sortie_str == "---":
        return None
    try:
        date_s = datetime.strptime(date_sortie_str, "%Y-%m-%d")
        expiry = date_s + timedelta(days=30)
        expired = datetime.now() > expiry
        return {"expiry": expiry.strftime("%Y-%m-%d"), "is_expired": expired}
    except: return None

# --- 3. تصميم الـ CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    .stApp { background: #0d1117; color: white; }

    /* الوميض والهيدر */
    .hero-box { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; }
    .main-title { font-family: 'Orbitron'; color: #58a6ff; font-size: 2rem; font-weight: 900; }
    
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; opacity: 1; } 50% { box-shadow: none; opacity: 0.7; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; opacity: 1; } 50% { box-shadow: none; opacity: 0.7; } }
    
    .status-open { color: #3fb950; border: 2px solid #3fb950; padding: 5px 12px; border-radius: 8px; animation: blink-green 2s infinite; font-family: 'Orbitron'; font-size: 0.9rem; }
    .status-closed { color: #f85149; border: 2px solid #f85149; padding: 5px 12px; border-radius: 8px; animation: blink-red 2s infinite; font-family: 'Orbitron'; font-size: 0.9rem; }

    /* أزرار التحميل */
    div.stDownloadButton > button {
        background-color: #58a6ff !important; color: #0d1117 !important;
        border-radius: 8px !important; width: 100% !important; font-weight: bold !important;
        border: none !important; padding: 8px !important; transition: 0.3s !important;
    }
    div.stDownloadButton > button:hover { background-color: #3fb950 !important; }

    /* بطاقة الجهاز */
    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 18px; margin-bottom: 15px; }
    
    /* ستايلات الضمان */
    .w-box { margin-top: 10px; padding: 8px; border-radius: 8px; text-align: center; font-family: 'Cairo'; font-size: 0.85rem; }
    .w-active { background: rgba(63, 185, 80, 0.1); color: #3fb950; border: 1px solid #3fb950; }
    .w-expired { background: rgba(248, 81, 73, 0.1); color: #f85149; border: 1px solid #f85149; text-decoration: line-through; opacity: 0.8; }

    .premium-btn { text-decoration: none; color: white !important; background: #21262d; border: 1px solid #30363d; padding: 12px; border-radius: 10px; text-align: center; font-family: 'Cairo'; font-weight: 700; transition: 0.3s; display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 0.9rem; }
    .premium-btn:hover { background: #30363d; border-color: #58a6ff; }
    </style>
""", unsafe_allow_html=True)

# --- 4. واجهة المحل ---
st.markdown(f"""
    <div style="display: flex; justify-content: space-between; font-family: 'Cairo'; color: #8b949e; font-size: 0.8rem; margin-bottom: 5px;">
        <div>📍 CHLEF, TENES | {datetime.now().strftime('%H:%M')}</div>
        <div style="color: #58a6ff; font-weight: bold;">INFODOC TECHNOLOGY</div>
    </div>
""", unsafe_allow_html=True)

try: is_open = db.reference("shop_settings/is_open").get()
except: is_open = True
status_html = f'<span class="status-open">OUVERT</span>' if is_open else f'<span class="status-closed">FERMÉ</span>'

st.markdown(f"""
    <div class="hero-box">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
            <div class="main-title">INFODOC</div>
            {status_html}
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px;">
            <a href="tel:0798661900" class="premium-btn">📞 إتصال</a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="premium-btn">📍 الموقع</a>
            <a href="https://www.facebook.com/100095433977319/" target="_blank" class="premium-btn">📘 فيسبوك</a>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 5. البحث والنتائج ---
phone_raw = st.text_input("🔍 أدخل رقم هاتفك لتتبع أجهزتك:", placeholder="0798661900")

status_config = {
    "En Cours": {"color": "#1f6feb", "prog": 33},
    "Réparable": {"color": "#39c5bb", "prog": 66},
    "Prêt": {"color": "#3fb950", "prog": 100},
    "Non Réparable": {"color": "#f85149", "prog": 100},
    "Livré & Payé": {"color": "#3fb950", "prog": 100},
    "Livré (Dette)": {"color": "#d29922", "prog": 100},
    "Annulé": {"color": "#f85149", "prog": 0} # اللون الأحمر للإلغاء
}

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            my_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not my_devices:
                st.error("❌ لا يوجد جهاز مسجل بهذا الرقم.")
            else:
                # زر التليغرام (صغير وفي مكان واضح)
                if not any(str(d.get("Telegram_ID", "")).strip() != "" for d in my_devices):
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                        st.link_button("🔔 تفعيل إشعارات تليغرام", tg_url, type="primary", use_container_width=True)

                for d in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = d.get("Statut", "En Cours")
                    cfg = status_config.get(stat, {"color": "#8b949e", "prog": 0})
                    
                    # منطق السعر في حالة Annulé
                    display_price = d.get('Prix')
                    price_note = ""
                    if stat == "Annulé":
                        display_price = "1000"
                        price_note = "(تكاليف الفحص والتشخيص)"

                    # منطق الضمان
                    w_info = get_warranty_info(stat, d.get("Date_Sortie"))
                    w_html = ""
                    if w_info:
                        w_cls = "w-expired" if w_info["is_expired"] else "w-active"
                        w_txt = f"🛡️ ضمان منتهي: {w_info['expiry']}" if w_info["is_expired"] else f"🛡️ ضمان ساري لغاية: {w_info['expiry']}"
                        w_html = f'<div class="w-box {w_cls}">{w_txt}</div>'

                    st.markdown(f"""
                        <div class="device-card" style="border-left: 5px solid {cfg['color']};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <b style="font-family: 'Orbitron'; color: #58a6ff;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span style="background: {cfg['color']}; color: #0d1117; padding: 2px 10px; border-radius: 4px; font-weight: bold; font-size: 0.75rem;">{stat.upper()}</span>
                            </div>
                            <div style="margin: 10px 0;">
                                <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: #8b949e;">
                                    <span>الإنجاز: {cfg['prog']}%</span>
                                    <span>المشكلة: {d.get('Panne')}</span>
                                </div>
                                <div style="width: 100%; background: #21262d; height: 6px; border-radius: 5px; margin-top: 5px;">
                                    <div style="width: {cfg['prog']}%; background: {cfg['color']}; height: 100%; border-radius: 5px;"></div>
                                </div>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.85rem; font-family: 'Cairo';">
                                <div>📅 دخول: {d.get('Date_Entree')}</div>
                                <div>🕒 خروج: {d.get('Date_Sortie', '---')}</div>
                                <div style="color: {cfg['color'] if stat == 'Annulé' else '#58a6ff'}; font-weight: bold;">💰 المبلغ: {display_price} دج <small>{price_note}</small></div>
                                <div></div>
                            </div>
                            {w_html}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    inv_text = f"INFODOC TECHNOLOGY\nID: {d.get('ID')}\nDevice: {d.get('Appareil')}\nPrice: {display_price} DZD\nStatus: {stat}"
                    st.download_button(f"📄 تحميل وصل رقم #{d.get('ID')}", inv_text, file_name=f"InfoDoc_{d.get('ID')}.txt", key=f"inv_{d.get('ID')}")

# --- 6. بوت التليغرام ---
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
                bot.reply_to(m, "✅ تم تفعيل الإشعارات بنجاح!")
    bot.polling(none_stop=True)

if "bot_running" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_running"] = True
