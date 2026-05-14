import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
import threading
import telebot
import pandas as pd
import io

# --- 1. الإعدادات والربط ---
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

# --- 2. الدوال المساعدة ---
def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if p.startswith("213"): p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]: p = "0" + p
    return p

def get_warranty_stats(date_sortie_str):
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None"]:
        return None
    date_formats = ["%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%Y %H:%M"]
    for fmt in date_formats:
        try:
            date_s = datetime.strptime(str(date_sortie_str).strip(), fmt)
            diff_days = (datetime.now() - date_s).days
            remaining_days = max(30 - diff_days, 0)
            percent = (remaining_days / 30) * 100
            return {"percent": percent, "is_expired": diff_days > 30, "days_left": remaining_days}
        except: continue
    return None

# --- 3. تصميم الـ CSS الشامل ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    .stApp { background: #0d1117; color: white; font-family: 'Cairo', sans-serif; }
    
    .main-title {
        font-family: 'Orbitron', sans-serif;
        font-size: 3.5rem;
        font-weight: 900;
        text-align: center;
        margin-bottom: 0px;
        color: #fff;
        text-transform: uppercase;
        letter-spacing: 5px;
        text-shadow: 0 0 10px #58a6ff, 0 0 20px #58a6ff, 0 0 40px #58a6ff;
        animation: glow 2s ease-in-out infinite alternate;
    }
    
    .sub-title {
        font-family: 'Cairo', sans-serif;
        font-size: 1.2rem;
        text-align: center;
        color: #8b949e;
        margin-top: -10px;
        margin-bottom: 20px;
        letter-spacing: 2px;
        font-weight: 400;
    }

    @keyframes glow {
        from { text-shadow: 0 0 10px #58a6ff, 0 0 20px #58a6ff, 0 0 30px #005cc5; }
        to { text-shadow: 0 0 20px #58a6ff, 0 0 40px #58a6ff, 0 0 60px #005cc5; transform: scale(1.02); }
    }

    /* تحسين أزرار التواصل */
    .contact-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 15px;
        margin-top: 25px;
    }
    .contact-btn {
        text-decoration: none !important;
        color: white !important;
        background: rgba(255, 255, 255, 0.05);
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        border: 1px solid rgba(255, 255, 255, 0.1);
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 5px;
        font-weight: bold;
        backdrop-filter: blur(5px);
    }
    .contact-btn:hover {
        border-color: #58a6ff;
        background: rgba(88, 166, 255, 0.1);
        box-shadow: 0 8px 25px rgba(88, 166, 255, 0.2);
        transform: translateY(-5px);
    }

    /* حالة المحل المضيئة */
    .status-badge {
        font-family: 'Orbitron', sans-serif;
        font-size: 1.2rem;
        font-weight: 900;
        padding: 8px 25px;
        border-radius: 50px;
        display: inline-block;
        letter-spacing: 2px;
    }
    .status-open {
        color: #00ff41;
        border: 2px solid #00ff41;
        box-shadow: 0 0 10px #00ff41, inset 0 0 5px #00ff41;
        animation: neon-pulse-green 1.5s infinite;
    }
    .status-closed {
        color: #ff3131;
        border: 2px solid #ff3131;
        box-shadow: 0 0 10px #ff3131, inset 0 0 5px #ff3131;
        animation: neon-pulse-red 1.5s infinite;
    }
    @keyframes neon-pulse-green {
        0%, 100% { box-shadow: 0 0 15px #00ff41, inset 0 0 10px #00ff41; opacity: 1; }
        50% { box-shadow: 0 0 30px #00ff41, inset 0 0 15px #00ff41; opacity: 0.8; }
    }
    @keyframes neon-pulse-red {
        0%, 100% { box-shadow: 0 0 15px #ff3131, inset 0 0 10px #ff3131; opacity: 1; }
        50% { box-shadow: 0 0 30px #ff3131, inset 0 0 15px #ff3131; opacity: 0.8; }
    }

    .device-card { background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 25px; transition: 0.3s; }
    .device-card:hover { border-color: #58a6ff; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
    
    .tg-link-btn { 
        display: block; background: #229ED9; color: white !important; 
        text-align: center; padding: 15px; border-radius: 12px; 
        text-decoration: none; font-weight: 900; margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(34, 158, 217, 0.3);
        transition: 0.3s;
    }
    .tg-link-btn:hover { box-shadow: 0 0 30px #229ED9; transform: scale(1.02); }
    
    .stDownloadButton button {
        width: 100%; background-color: #21262d !important; color: #58a6ff !important;
        border: 1px solid #30363d !important; border-radius: 8px !important;
        transition: 0.3s !important; font-weight: bold !important;
    }
    .stDownloadButton button:hover {
        border-color: #58a6ff !important;
        box-shadow: 0 0 15px rgba(88, 166, 255, 0.3) !important;
        color: white !important;
    }

    .exp-red { background: rgba(248, 81, 73, 0.1); color: #f85149; font-weight: 900; border: 2px solid #f85149; padding: 12px; border-radius: 10px; text-align: center; }
    .badge { padding: 4px 10px; border-radius: 5px; font-weight: bold; font-size: 0.8rem; font-family: 'Orbitron'; }
    </style>
""", unsafe_allow_html=True)

# --- 4. الترحيب وحالة المحل ---
curr_h = datetime.now().hour
greet = "صباح الخير" if 5 <= curr_h < 12 else "مساء الخير"
try: is_open = db.reference("shop_settings/is_open").get()
except: is_open = True
status_html = '<span class="status-badge status-open">OPEN</span>' if is_open else '<span class="status-badge status-closed">CLOSED</span>'

st.markdown(f"""
    <div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: #8b949e; margin-bottom: 10px;">
        <div>{greet} زبوننا الكريم | {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
        <div style="color: #58a6ff; font-weight: bold;">CHLEF, ALGERIA</div>
    </div>
    <div style="background: #161b22; border: 1px solid #30363d; border-radius: 20px; padding: 30px; margin-bottom: 25px; border-top: 4px solid #58a6ff;">
        <div style="text-align: center;">
            <div class="main-title">INFODOC</div>
            <div class="sub-title">Vente & Reparation</div>
            <div style="margin: 20px 0;">
                {status_html}
            </div>
        </div>
        <div class="contact-grid">
            <a href="tel:0798661900" class="contact-btn"><span style="font-size:1.5rem;">📞</span><span>اتصل بنا</span></a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="contact-btn"><span style="font-size:1.5rem;">📍</span><span>موقعنا</span></a>
            <a href="https://www.facebook.com/100095433977319/" target="_blank" class="contact-btn"><span style="font-size:1.5rem;">📘</span><span>فيسبوك</span></a>
            <a href="https://www.tiktok.com/@infodoc02" target="_blank" class="contact-btn"><span style="font-size:1.5rem;">📱</span><span>تيك توك</span></a>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- باقي الكود كما هو تماماً ---
phone_raw = st.text_input("🔍 أدخل رقم هاتفك لتتبع أجهزتك:", placeholder="0XXXXXXXXX")

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            all_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not all_devices:
                st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم.")
            else:
                sorted_devices = sorted(all_devices, key=lambda x: (str(x.get("Date_Sortie", "")) not in ["", "---", "None"], x.get("ID", 0)))

                if any(str(d.get("Telegram_ID", "")).strip() in ["", "None"] for d in all_devices):
                    tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                    st.markdown(f'<a href="{tg_url}" target="_blank" class="tg-link-btn">🚀 ربط الحساب بالتلغرام للإشعارات الفورية</a>', unsafe_allow_html=True)

                st.markdown("---")

                for d in sorted_devices:
                    stat = str(d.get("Statut", "En Cours"))
                    is_delivered = "Livré" in stat
                    bg_color = "#238636" if stat == "Prêt" else "#da3633" if stat == "Annulé" else "#6e7681" if is_delivered else "#30363d"
                    with st.container():
                         st.markdown(f"""
                             <div class="device-card" style="border-top: 5px solid {bg_color}; background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 20px; margin-bottom: 5px;">
                                 <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 15px;">
                                     <div>
                                         <h3 style="margin:0; color:#58a6ff; font-family:'Cairo';">{d.get('Appareil')}</h3>
                                         <code style="color:#8b949e;">رقم التذكرة: #{d.get('ID')}</code>
                                     </div>
                                     <span class="badge" style="background:{bg_color}; color:white; padding: 5px 10px; border-radius: 5px;">{stat.upper()}</span>
                                 </div>
                         """, unsafe_allow_html=True)

                         if is_delivered:
                             w = get_warranty_stats(d.get("Date_Sortie"))
                             if w and not w["is_expired"]:
                                 st.markdown(f"""
                                     <div style="margin-bottom:8px; color:#d29922; font-weight:bold; font-size:0.95rem;">🛡️ شريط الضمان (متبقي {int(w['days_left'])} يوم)</div>
                                     <div style="width: 100%; background: #21262d; height: 14px; border-radius: 10px; overflow: hidden; margin-bottom: 20px;">
                                         <div style="width: {w['percent']}%; background: #d29922; height: 100%;"></div>
                                     </div>
                                 """, unsafe_allow_html=True)
                             elif w and w["is_expired"]:
                                 st.markdown('<div style="background: rgba(248, 81, 73, 0.1); color: #f85149; border: 1px solid #f85149; padding: 10px; border-radius: 10px; text-align: center; margin-bottom: 15px;">❌ GARANTIE EXPIRÉE</div>', unsafe_allow_html=True)
                         else:
                             prog = 33 if stat == "En Cours" else 66 if stat == "Réparable" else 100
                             st.markdown(f"""
                                 <div style="margin-bottom:8px; color:#238636; font-weight:bold; font-size:0.95rem;">🛠️ تقدم الصيانة</div>
                                 <div style="width: 100%; background: #21262d; height: 14px; border-radius: 10px; overflow: hidden; margin-bottom: 15px;">
                                     <div style="width: {prog}%; background: #238636; height: 100%;"></div>
                                 </div>
                             """, unsafe_allow_html=True)

                         st.markdown(f"""
                             <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.9rem; background:#0d1117; padding:15px; border-radius:10px; border: 1px solid #30363d; margin-bottom: 15px;">
                                 <div style="color:#8b949e;">📅 <b>استلام:</b><br>{d.get('Date_Entree')}</div>
                                 <div style="color:#8b949e;">🕒 <b>خروج:</b><br>{d.get('Date_Sortie', '---')}</div>
                                 <div style="color: #ffffff; font-weight: 900; font-size:1.3rem; grid-column: span 2; text-align:center; border-top:1px solid #30363d; padding-top:10px; margin-top:5px;">
                                     المبلغ: <span style="color:#58a6ff;">{d.get('Prix')} دج</span>
                                 </div>
                             </div>
                         """, unsafe_allow_html=True)

                         try:
                             s_data = {"ID": [d.get('ID')], "Appareil": [d.get('Appareil')], "Prix": [d.get('Prix')]}
                             df_s = pd.DataFrame(s_data)
                             buf = io.BytesIO()
                             with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
                                 df_s.to_excel(wr, index=False)
                             st.download_button(label=f"📥 فاتورة {d.get('Appareil')}", data=buf.getvalue(), file_name=f"InfoDoc_{d.get('ID')}.xlsx", key=f"dl_{d.get('_id')}")
                         except: pass
                         st.markdown("</div>", unsafe_allow_html=True)

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
                bot.reply_to(m, "✅ تم الربط بنجاح!")
    bot.polling(none_stop=True)

if "bot_running" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_running"] = True
