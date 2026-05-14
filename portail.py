import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime, timedelta
import threading
import telebot
from io import BytesIO

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
    """الضمان يظهر فقط في حالة LIVRE ET PAYE ولمدة شهر"""
    if status != "LIVRE ET PAYE" or not date_sortie_str or date_sortie_str == "---":
        return None
    try:
        date_s = datetime.strptime(date_sortie_str, "%Y-%m-%d")
        expiry = date_s + timedelta(days=30)
        expired = datetime.now() > expiry
        return {"expiry": expiry.strftime("%Y-%m-%d"), "is_expired": expired}
    except: return None

# --- 3. تصميم الـ CSS الاحترافي (الوميض + الأزرار) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    .stApp { background: #0d1117; color: white; }

    /* الهيدر والوميض */
    .hero-box { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); border: 1px solid #30363d; border-radius: 15px; padding: 25px; margin-bottom: 20px; }
    .main-title { font-family: 'Orbitron'; color: #58a6ff; font-size: 2.2rem; font-weight: 900; }
    
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; opacity: 1; } 50% { box-shadow: none; opacity: 0.7; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; opacity: 1; } 50% { box-shadow: none; opacity: 0.7; } }
    
    .status-open { color: #3fb950; border: 2px solid #3fb950; padding: 6px 15px; border-radius: 8px; animation: blink-green 2s infinite; font-weight: bold; font-family: 'Orbitron'; }
    .status-closed { color: #f85149; border: 2px solid #f85149; padding: 6px 15px; border-radius: 8px; animation: blink-red 2s infinite; font-weight: bold; font-family: 'Orbitron'; }

    /* أزرار التواصل الـ Premium */
    .contact-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-top: 20px; }
    .premium-btn {
        text-decoration: none; color: white !important; background: #21262d; border: 1px solid #30363d;
        padding: 15px; border-radius: 12px; text-align: center; font-family: 'Cairo'; font-weight: 700;
        transition: 0.3s all ease-in-out; display: flex; align-items: center; justify-content: center; gap: 10px;
    }
    .premium-btn:hover { background: #30363d; border-color: #58a6ff; transform: translateY(-5px); box-shadow: 0 5px 15px rgba(88, 166, 255, 0.2); }

    /* بطاقة الجهاز */
    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 20px; }
    .card-livre { border-right: 6px solid #3fb950; }
    
    /* الضمان */
    .w-active { color: #3fb950; font-weight: bold; font-family: 'Cairo'; border: 1px solid #3fb950; padding: 5px 10px; border-radius: 8px; display: inline-block; }
    .w-expired { color: #f85149; text-decoration: line-through; border: 1px solid #f85149; padding: 5px 10px; border-radius: 8px; display: inline-block; opacity: 0.7; }
    
    .stTextInput input { background: #0d1117 !important; border: 1px solid #30363d !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# --- 4. الترحيب والمعلومات العلوية ---
curr_h = datetime.now().hour
greet = "صباح الخير" if 5 <= curr_h < 12 else "مساء الخير"
st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-family: 'Cairo'; color: #8b949e;">
        <div>{greet} زبوننا الكريم | الوقت الآن: {datetime.now().strftime('%H:%M')}</div>
        <div style="font-weight: 900; color: #58a6ff;">CHLEF, ALGERIA</div>
    </div>
""", unsafe_allow_html=True)

# الهيدر مع الوميض
try: is_open = db.reference("shop_settings/is_open").get()
except: is_open = True
status_html = f'<span class="status-open">ATELIER OUVERT</span>' if is_open else f'<span class="status-closed">ATELIER FERMÉ</span>'

st.markdown(f"""
    <div class="hero-box">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            {status_html}
        </div>
        <div class="contact-grid">
            <a href="tel:0798661900" class="premium-btn">📞 0798661900</a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="premium-btn">📍 موقع المحل (الشلف)</a>
            <a href="https://www.facebook.com/InfoDoc" target="_blank" class="premium-btn">📘 Facebook Page</a>
            <a href="https://www.tiktok.com/@infodoc02" target="_blank" class="premium-btn">📱 TikTok Channel</a>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 5. البحث والتتبع ---
st.markdown("### 🔍 تتبع حالة جهازك")
phone_raw = st.text_input("أدخل رقم هاتفك المسجل (مثال: 0798661900):", key="search_input")

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            my_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم.")
            else:
                # أ) زر التليغرام الموحد (يظهر فقط إذا لم يكن هناك أي جهاز مربوط)
                already_linked = any(str(d.get("Telegram_ID", "")).strip() != "" for d in my_devices)
                if not already_linked:
                    st.info("💡 لم تصلك إشعارات بعد؟ اربط حسابك بالتليغرام الآن.")
                    tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                    st.link_button("🚀 ربط الحساب بالتليغرام", tg_url, type="primary", use_container_width=True)
                
                # ب) عرض الأجهزة
                for d in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    stat = str(d.get("Statut", "")).upper()
                    
                    # منطق شريط التقدم
                    p_map = {"EN ATTENTE": 0, "ENCOURS": 33, "REPARABLE": 66, "PRET": 100, "LIVRE ET PAYE": 100}
                    prog = p_map.get(stat, 0)
                    prog_color = "#3fb950" if prog == 100 else "#1f6feb" if prog > 0 else "#8b949e"
                    
                    # منطق الضمان (فقط لـ LIVRE ET PAYE)
                    w_info = get_warranty_info(stat, d.get("Date_Sortie"))
                    w_html = ""
                    if w_info:
                        w_class = "w-expired" if w_info["is_expired"] else "w-active"
                        w_text = f"🛡️ ضمان منتهي ({w_info['expiry']})" if w_info["is_expired"] else f"🛡️ ضمان ساري إلى: {w_info['expiry']}"
                        w_html = f'<div class="{w_class}">{w_text}</div>'

                    card_cls = "card-livre" if stat == "LIVRE ET PAYE" else ""

                    st.markdown(f"""
                        <div class="device-card {card_cls}">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <b style="font-family: 'Orbitron'; color: #58a6ff; font-size: 1.1rem;">#{d.get('ID')} | {d.get('Appareil')}</b>
                                <span style="background: {prog_color}; padding: 4px 12px; border-radius: 5px; font-weight: bold; font-size: 0.8rem;">{stat}</span>
                            </div>
                            <div style="margin: 15px 0;">
                                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #8b949e; margin-bottom: 5px;">
                                    <span>تقدم العمل: {prog}%</span>
                                    <span>العطل: {d.get('Panne')}</span>
                                </div>
                                <div style="width: 100%; background: #21262d; height: 10px; border-radius: 10px; overflow: hidden;">
                                    <div style="width: {prog}%; background: {prog_color}; height: 100%; transition: 0.5s;"></div>
                                </div>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.9rem; font-family: 'Cairo';">
                                <div>📅 الدخول: {d.get('Date_Entree')}</div>
                                <div>🕒 الخروج: {d.get('Date_Sortie', '---')}</div>
                                <div style="color: #58a6ff; font-weight: bold;">💰 التكلفة: {d.get('Prix')} دج</div>
                                <div>{w_html}</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # زر تحميل الفاتورة
                    inv_data = f"INFODOC TECHNOLOGY\nID: {d.get('ID')}\nDevice: {d.get('Appareil')}\nPrice: {d.get('Prix')} DZD\nWarranty: 1 Month from {d.get('Date_Sortie')}"
                    st.download_button(f"📄 تحميل فاتورة #{d.get('ID')}", inv_data, file_name=f"InfoDoc_{d.get('ID')}.txt", key=f"inv_{d.get('ID')}")

# --- 6. بوت التليغرام (خلفية) ---
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
                bot.reply_to(m, "✅ تم ربط جهازك بنجاح! ستصلك الإشعارات هنا فور جاهزيته.")
    bot.polling(none_stop=True)

if "bot_running" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_running"] = True
