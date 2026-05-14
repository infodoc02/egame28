import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
import threading
import telebot

# --- 1. الإعدادات والربط ---
st.set_page_config(page_title="InfoDoc - Client Portal", layout="wide")

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

# --- 3. تصميم الـ CSS المخصص ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
    .stApp { background: #0d1117; color: white; font-family: 'Cairo', sans-serif; }
    
    /* نمط الكارت (المربع المستقل) */
    .device-card { 
        background: #161b22; 
        border: 1px solid #30363d; 
        border-radius: 12px; 
        padding: 20px; 
        margin-bottom: 25px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    }
    
    /* زر التلغرام */
    .tg-link-btn {
        display: block; background: #229ED9; color: white !important; 
        text-align: center; padding: 15px; border-radius: 10px; 
        text-decoration: none; font-weight: 900; margin-bottom: 20px;
    }

    /* نصوص التنبيه */
    .exp-red { color: #f85149; font-weight: 900; border: 2px solid #f85149; padding: 10px; border-radius: 8px; text-align: center; margin-top: 10px; }
    
    /* بادج الحالة */
    .badge { padding: 5px 12px; border-radius: 6px; font-weight: bold; font-size: 0.85rem; }
    </style>
""", unsafe_allow_html=True)

# --- 4. واجهة المستخدم ---
st.markdown('<h1 style="text-align:center; color:#58a6ff;">INFODOC TECHNOLOGY</h1>', unsafe_allow_html=True)

phone_raw = st.text_input("🔍 أدخل رقم هاتفك المعتمد:", placeholder="0XXXXXXXXX")

if phone_raw:
    phone_n = normalize_phone(phone_raw)
    if len(phone_n) >= 9:
        raw_db = db.reference("atelier").get()
        if raw_db:
            # فلترة الأجهزة وتحديد الترتيب (الأجهزة بدون تاريخ خروج أولاً)
            all_devices = [dict(v, _id=k) for k, v in raw_db.items() if normalize_phone(v.get("Telephone", "")).endswith(phone_n[-9:])]
            
            if not all_devices:
                st.warning("⚠️ لم يتم العثور على أجهزة لهذا الرقم.")
            else:
                # ترتيب: الأجهزة التي ليس لها تاريخ خروج (أو تاريخها فارغ) تأتي أولاً
                sorted_devices = sorted(all_devices, key=lambda x: (str(x.get("Date_Sortie", "")) not in ["", "---", "None"], x.get("ID", 0)), reverse=False)

                # زر التلغرام (يظهر إذا لم يتم الربط)
                if any(str(d.get("Telegram_ID", "")).strip() in ["", "None"] for d in all_devices):
                    tg_url = f"https://t.me/{st.secrets.get('BOT_USERNAME')}?start={phone_n}"
                    st.markdown(f'<a href="{tg_url}" target="_blank" class="tg-link-btn">📱 ربط الحساب بالتلغرام لتلقي الإشعارات</a>', unsafe_allow_html=True)

                for d in sorted_devices:
                    # --- داخل حلقة التكرار للأجهزة (for d in sorted_devices) ---

stat = str(d.get("Statut", "En Cours"))
is_delivered = "Livré" in stat
bg_color = "#6e7681" if is_delivered else "#30363d" # رمادي إذا تم التسليم

st.markdown(f"""
    <div class="device-card" style="border-top: 4px solid {bg_color};">
        <!-- الرأس: اسم الجهاز والحالة -->
        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
            <div>
                <h3 style="margin:0; color:#58a6ff; font-family:'Cairo';">{d.get('Appareil')}</h3>
                <code style="color:#8b949e;">رقم التذكرة: #{d.get('ID')}</code>
            </div>
            <span class="badge" style="background:{bg_color}; color:white;">{stat.upper()}</span>
        </div>

        <!-- شريط الضمان أو الصيانة -->
""")

if is_delivered:
    w = get_warranty_stats(d.get("Date_Sortie"))
    if w:
        if w["is_expired"]:
            st.markdown('<div class="exp-red">❌ GARANTIE EXPIRÉE (الضمان منتهي)</div>', unsafe_allow_html=True)
        else:
            st.markdown(f"""
                <div style="margin-bottom:5px; color:#d29922; font-weight:bold; font-size:0.9rem;">🛡️ شريط الضمان (متبقي {int(w['days_left'])} يوم)</div>
                <div style="width: 100%; background: #21262d; height: 12px; border-radius: 10px; overflow: hidden; margin-bottom: 15px;">
                    <div style="width: {w['percent']}%; background: #d29922; height: 100%; transition: 1s;"></div>
                </div>
            """, unsafe_allow_html=True)
else:
    # شريط الصيانة الأخضر
    prog = 33 if stat == "En Cours" else 66 if stat == "Réparable" else 100
    st.markdown(f"""
        <div style="margin-bottom:5px; color:#238636; font-weight:bold; font-size:0.9rem;">🛠️ تقدم الصيانة</div>
        <div style="width: 100%; background: #21262d; height: 12px; border-radius: 10px; overflow: hidden; margin-bottom: 10px;">
            <div style="width: {prog}%; background: #238636; height: 100%;"></div>
        </div>
    """, unsafe_allow_html=True)

# القسم السفلي: التواريخ والمبلغ (داخل نفس المربع)
st.markdown(f"""
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.85rem; background:#0d1117; padding:12px; border-radius:8px; border: 1px solid #30363d;">
            <div style="color:#8b949e;">📅 <b>استلام:</b> {d.get('Date_Entree')}</div>
            <div style="color:#8b949e;">🕒 <b>خروج:</b> {d.get('Date_Sortie', '---')}</div>
            <div style="color: #ffffff; font-weight: 900; font-size:1.2rem; grid-column: span 2; text-align:center; border-top:1px solid #30363d; padding-top:8px; margin-top:5px;">
                المبلغ: <span style="color:#58a6ff;">{d.get('Prix')} دج</span>
            </div>
        </div>
    </div> <!-- نهاية المربع الكبير -->
""", unsafe_allow_html=True)
# --- 5. بوت التلغرام (نفس المنطق) ---
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
