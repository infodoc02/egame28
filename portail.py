import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime, timedelta
import threading
import telebot

# --- 1. إعدادات الصفحة ---
st.set_page_config(page_title="InfoDoc Portal", page_icon="📱", layout="wide")

# --- 2. تهيئة Firebase ---
@st.cache_resource
def init_firebase():
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

init_firebase()

# --- 3. الدوال البرمجية ---
def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if p.startswith("213"): p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]: p = "0" + p
    return p

def check_warranty(status, date_sortie_str):
    """الضمان يظهر فقط في حالة LIVRE ET PAYE ويحسب لمدة شهر"""
    if status != "LIVRE ET PAYE" or not date_sortie_str or date_sortie_str == "---":
        return None # لا يظهر الضمان نهائياً
    
    try:
        date_sortie = datetime.strptime(date_sortie_str, "%Y-%m-%d")
        expiry_date = date_sortie + timedelta(days=30)
        is_expired = datetime.now() > expiry_date
        return {"expiry": expiry_date.strftime("%Y-%m-%d"), "expired": is_expired}
    except:
        return None

# --- 4. التصميم (CSS) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700&display=swap');
    .stApp { background: #0d1117; color: #c9d1d9; }
    
    /* الوماض */
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .status-online { color: #3fb950; border: 1px solid #238636; padding: 4px 12px; border-radius: 50px; animation: blink 1.5s infinite; font-weight: bold; font-size: 0.8rem; }
    .status-offline { color: #f85149; border: 1px solid #f85149; padding: 4px 12px; border-radius: 50px; font-weight: bold; font-size: 0.8rem; }

    .hero-title { font-family: 'Orbitron'; color: #58a6ff; font-size: 2rem; margin-bottom: 0; }
    
    /* بطاقة الجهاز */
    .device-card {
        background: #161b22; border: 1px solid #30363d; border-radius: 12px; 
        padding: 18px; margin-bottom: 15px; border-right: 4px solid #30363d;
    }
    .card-paid { border-right: 4px solid #3fb950 !important; }
    
    .warranty-tag { padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; font-weight: bold; display: inline-block; margin-top: 10px; }
    .w-active { background: rgba(63, 185, 80, 0.1); color: #3fb950; border: 1px solid #3fb950; }
    .w-expired { background: rgba(248, 81, 73, 0.1); color: #f85149; border: 1px solid #f85149; text-decoration: line-through; }

    .contact-btn {
        text-decoration: none; color: white !important; background: #21262d;
        border: 1px solid #30363d; padding: 8px 15px; border-radius: 8px;
        font-size: 0.9rem; transition: 0.3s; display: inline-block;
    }
    .contact-btn:hover { border-color: #58a6ff; background: #30363d; }
    </style>
""", unsafe_allow_html=True)

# --- 5. الهيدر ---
h_col1, h_col2 = st.columns([2, 1])
with h_col1:
    greeting = "صباح الخير ☀️" if datetime.now().hour < 12 else "مساء الخير 🌙"
    st.markdown(f"<div style='color:#8b949e; font-family:Cairo;'>{greeting}، مرحبا بك في</div>", unsafe_allow_html=True)
    st.markdown("<div class='hero-title'>INFODOC TECHNOLOGY</div>", unsafe_allow_html=True)
with h_col2:
    try: is_open = db.reference("shop_settings/is_open").get()
    except: is_open = True
    st.markdown(f"<div style='text-align:right; margin-top:20px;'><span class='{'status-online' if is_open else 'status-offline'}'>{'ATELIER OUVERT' if is_open else 'ATELIER FERMÉ'}</span></div>", unsafe_allow_html=True)

# أزرار التواصل
st.markdown(f"""
    <div style="margin: 15px 0; display: flex; gap: 10px; flex-wrap: wrap;">
        <a href="tel:0798661900" class="contact-btn">📞 0798661900</a>
        <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="contact-btn">📍 Local</a>
        <a href="https://www.facebook.com/InfoDoc" target="_blank" class="contact-btn">📘 Facebook</a>
    </div>
""", unsafe_allow_html=True)

st.divider()

# --- 6. التتبع والاستعلام ---
phone_input = st.text_input("🔍 أدخل رقم هاتفك للمتابعة:", placeholder="0XXXXXXXXX")

if phone_input:
    phone_n = normalize_phone(phone_input)
    if len(phone_n) >= 9:
        raw_data = db.reference("atelier").get()
        if raw_data:
            my_devices = [dict(v, _id=k) for k, v in raw_data.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not my_devices:
                st.info("لا توجد أجهزة مسجلة بهذا الرقم.")
            else:
                # أ) التحقق من الربط بالتليغرام (زر واحد فقط)
                is_linked = any(str(dev.get("Telegram_ID", "")).strip() != "" for dev in my_devices)
                
                if not is_linked:
                    st.warning("⚠️ حسابك غير مرتبط بالتليغرام لتلقي الإشعارات.")
                    tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                    st.link_button("🚀 ربط الحساب بالتليغرام الآن", tg_url, type="primary", use_container_width=True)
                else:
                    st.success("✅ حسابك مرتبط بنجاح، ستصلك الإشعارات فوراً.")

                st.markdown("---")
                
                # ب) عرض الأجهزة
                for dev in sorted(my_devices, key=lambda x: int(x.get("ID", 0)), reverse=True):
                    status = str(dev.get("Statut", "")).upper()
                    
                    # حساب النسبة المئوية
                    prog_map = {"EN ATTENTE": 0, "ENCOURS": 33, "REPARABLE": 66, "PRET": 100, "LIVRE ET PAYE": 100}
                    prog = prog_map.get(status, 0)
                    color = "#3fb950" if prog == 100 else "#58a6ff" if prog > 0 else "#8b949e"
                    card_class = "card-paid" if status == "LIVRE ET PAYE" else ""

                    # حساب الضمان
                    w_info = check_warranty(status, dev.get("Date_Sortie"))
                    warranty_html = ""
                    if w_info:
                        w_cls = "w-expired" if w_info["expired"] else "w-active"
                        w_txt = "ضمان منتهي" if w_info["expired"] else f"الضمان ساري إلى: {w_info['expiry']}"
                        warranty_html = f"<div class='warranty-tag {w_cls}'>🛡️ {w_txt}</div>"

                    st.markdown(f"""
                        <div class="device-card {card_class}">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <b style="font-family:Cairo; color:#58a6ff;">#{dev.get('ID')} | {dev.get('Appareil')}</b>
                                <span style="font-size:0.8rem; background:{color}; color:white; padding:2px 8px; border-radius:4px;">{status}</span>
                            </div>
                            <div style="margin-top:10px;">
                                <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:#8b949e;">
                                    <span>الحالة: {prog}%</span>
                                    <span>المشكلة: {dev.get('Panne')}</span>
                                </div>
                                <div style="background:#21262d; height:6px; border-radius:10px; margin-top:4px;">
                                    <div style="background:{color}; width:{prog}%; height:100%; border-radius:10px;"></div>
                                </div>
                            </div>
                            <div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; font-size:0.85rem; gap:5px;">
                                <span>📅 دخول: {dev.get('Date_Entree')}</span>
                                <span>🕒 خروج: {dev.get('Date_Sortie', '---')}</span>
                                <b style="color:white;">💰 السعر: {dev.get('Prix')} دج</b>
                            </div>
                            {warranty_html}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # زر تحميل الفاتورة (يظهر للكل)
                    if st.button(f"📄 تحميل بيانات الجهاز #{dev.get('ID')}", key=f"btn_{dev.get('ID')}"):
                        summary = f"ID: {dev.get('ID')}\nDevice: {dev.get('Appareil')}\nStatus: {status}\nPrice: {dev.get('Prix')} DZD"
                        st.download_button("تأكيد التحميل", summary, file_name=f"InfoDoc_{dev.get('ID')}.txt")

# --- 7. بوت التليغرام ---
def run_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return
    bot = telebot.TeleBot(token)
    @bot.message_handler(commands=['start'])
    def sync(m):
        args = m.text.split()
        if len(args) > 1:
            p = normalize_phone(args[1])
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.send_message(m.chat.id, "✅ تم ربط جهازك! ستصلك رسالة عند التغيير.")
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
