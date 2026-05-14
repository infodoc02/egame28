import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
import threading
import telebot
import pandas as pd
import io

# ==============================================================================
# 1. إعدادات الصفحة والأنماط (Config & CSS)
# ==============================================================================
st.set_page_config(page_title="InfoDoc - Portail Client", page_icon="📱", layout="wide")

# دمج كل التنسيقات في قالب واحد نظيف
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    /* الأساسيات */
    .stApp { background: #0d1117; color: white; font-family: 'Cairo', sans-serif; }
    p, span, div, label, h3 { color: white !important; }
    
    /* العنوان النيوني */
    .main-title {
        font-family: 'Orbitron', sans-serif; font-size: clamp(1.8rem, 5vw, 3rem); font-weight: 900;
        text-align: center; color: #58a6ff; text-shadow: 0 0 20px rgba(88, 166, 255, 0.4);
        margin-bottom: 5px;
    }

    /* كرت الجهاز العلوي */
    .device-box {
        background: #161b22; border: 1px solid #30363d; 
        border-radius: 15px 15px 0 0; /* زوايا دائرية من الأعلى فقط */
        padding: 20px; margin-top: 20px;
    }

    /* تنسيق الأكورديون ليلتصق بالكرت */
    div[data-testid="stExpander"] {
        background: #0d1117 !important;
        border: 1px solid #30363d !important;
        border-top: none !important;
        border-radius: 0 0 15px 15px !important;
        margin-bottom: 10px;
    }
    
    /* حالة المحل */
    .status-badge { padding: 5px 15px; border-radius: 8px; font-weight: bold; font-family: 'Orbitron'; }
    .status-open { color: #3fb950 !important; border: 1px solid #3fb950; animation: glow-g 2s infinite; }
    .status-closed { color: #f85149 !important; border: 1px solid #f85149; }
    @keyframes glow-g { 50% { box-shadow: 0 0 15px rgba(63, 185, 80, 0.4); } }

    /* زر التلغرام المشع */
    .tg-btn {
        display: block; background: #229ED9; color: white !important; text-align: center;
        padding: 12px; border-radius: 10px; text-decoration: none; font-weight: bold;
        animation: pulse-blue 2s infinite; margin: 10px 0;
    }
    @keyframes pulse-blue {
        0% { transform: scale(1); }
        50% { transform: scale(1.02); box-shadow: 0 0 20px rgba(34, 158, 217, 0.5); }
        100% { transform: scale(1); }
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. الدوال البرمجية (Logic Functions)
# ==============================================================================
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
        except Exception as e:
            st.error(f"Error: {e}")
    return True

init_db()

def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if p.startswith("213"): p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]: p = "0" + p
    return p

def get_warranty_stats(date_sortie_str):
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None"]: return None
    for fmt in ["%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d", "%d-%m-%Y"]:
        try:
            date_s = datetime.strptime(str(date_sortie_str).strip(), fmt)
            diff = (datetime.now() - date_s).days
            rem = max(30 - diff, 0)
            return {"percent": (rem/30)*100, "is_expired": diff > 30, "days_left": rem}
        except: continue
    return None

# ==============================================================================
# 3. الهيدر وحالة المحل (Header Section)
# ==============================================================================
shop_status = db.reference("shop_settings/is_open").get()
status_class = "status-open" if shop_status else "status-closed"
status_text = "OPEN" if shop_status else "CLOSED"

st.markdown(f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <div class="main-title">INFODOC TECHNOLOGY</div>
        <span class="status-badge {status_class}">ATELIER {status_text}</span>
    </div>
""", unsafe_allow_html=True)

# الملاحظات الهامة
with st.expander("⚠️ ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-size: 0.9rem; line-height: 1.6;">
            • فحص الجهاز القابل للتصليح في حال الرفض: <b>1000 دج</b><br>
            • أسعار صيانة اللوحة الأم تبدأ من: <b>3000 دج</b><br>
            • ضماننا العادي هو <b>30 يوماً</b> على العطل المصلح.
        </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 4. محرك البحث والعرض (Search Engine)
# ==============================================================================
st.markdown("<br>", unsafe_allow_html=True)
user_phone = st.text_input("🔍 تتبع أجهزتك برقم الهاتف:", placeholder="07XXXXXXXX")

if user_phone:
    norm_phone = normalize_phone(user_phone)
    if len(norm_phone) >= 9:
        raw_data = db.reference("atelier").get()
        if raw_data:
            my_devices = [dict(v, _id=k) for k, v in raw_data.items() 
                          if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لا توجد أجهزة مسجلة بهذا الرقم.")
            else:
                # زر التلغرام
                bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                st.markdown(f'<a href="https://t.me/{bot_user}?start={norm_phone}" class="tg-btn">🔔 تفعيل إشعارات تليغرام لهذا الرقم</a>', unsafe_allow_html=True)

                # عرض الأجهزة
                for dev in sorted(my_devices, key=lambda x: str(x.get("ID")), reverse=True):
                    status = dev.get("Statut", "En Cours")
                    is_done = "Livré" in status or "Prêt" in status
                    
                    # 1. كرت الجهاز (الرأس)
                    st.markdown(f"""
                        <div class="device-box">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <h3 style="margin:0;">{dev.get('Appareil')}</h3>
                                    <code style="color:#58a6ff;">ID: #{dev.get('ID')}</code>
                                </div>
                                <div style="text-align: right;">
                                    <span style="color:#8b949e; font-size:0.8rem; display:block;">الحالة:</span>
                                    <b style="color:#58a6ff;">{status}</b>
                                </div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 2. الأكورديون (التفاصيل)
                    with st.expander("📄 المبالغ، المواعيد والضمان"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"📅 دخول: {dev.get('Date_Entree')}")
                            st.write(f"💰 السعر: **{dev.get('Prix')} DA**")
                        with col2:
                            st.write(f"📅 خروج: {dev.get('Date_Sortie', '---')}")
                            
                        # الضمان والتقدم
                        if "Livré" in status:
                            w = get_warranty_stats(dev.get("Date_Sortie"))
                            if w:
                                st.write(f"🛡️ الضمان: {'✅ سارٍ' if not w['is_expired'] else '❌ منتهٍ'} ({int(w['days_left'])} يوم)")
                                st.progress(w['percent']/100)
                        else:
                            p = 0.3 if "Cours" in status else 0.7 if "Réparable" in status else 1.0
                            st.write("⚙️ تقدم العملية:")
                            st.progress(p)

# ==============================================================================
# 5. البوت (Background Bot)
# ==============================================================================
def run_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return
    bot = telebot.TeleBot(token)
    @bot.message_handler(commands=['start'])
    def handle(m):
        phone = normalize_phone(m.text.split()[1]) if len(m.text.split())>1 else None
        if phone:
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(phone[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.reply_to(m, "✅ تم ربط جهازك! ستصلك رسالة فور جاهزيته.")
    bot.polling(none_stop=True)

if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
