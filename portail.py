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
# 1. إعدادات الصفحة والتنسيق البصري (Global CSS)
# ==============================================================================
st.set_page_config(page_title="InfoDoc - Client Portal", page_icon="📱", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    /* الخلفية والخطوط الأساسية */
    .stApp { background: #05070a; color: white; font-family: 'Cairo', sans-serif; }
    
    /* تصميم العنوان النيوني المتحرك */
    .neon-title {
        font-family: 'Orbitron', sans-serif; font-size: clamp(2rem, 8vw, 3.5rem);
        font-weight: 900; text-align: center; color: #fff;
        text-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff;
        animation: pulse-glow 2s infinite alternate; margin-bottom: 0;
    }
    @keyframes pulse-glow {
        from { text-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff; transform: scale(1); }
        to { text-shadow: 0 0 20px #00d4ff, 0 0 40px #00d4ff; transform: scale(1.01); }
    }

    /* كرت الجهاز العلوي */
    .device-box {
        background: linear-gradient(145deg, #161b22, #0d1117);
        border: 2px solid #30363d; border-radius: 20px 20px 0 0;
        padding: 25px; margin-top: 25px; border-bottom: none;
    }

    /* تنسيق الأكورديون ليلتصق بالكرت */
    div[data-testid="stExpander"] {
        border: 2px solid #30363d !important; border-top: none !important;
        border-radius: 0 0 20px 20px !important;
        background: rgba(22, 27, 34, 0.8) !important;
        margin-bottom: 15px;
    }
    
    .stExpander summary p {
        color: #00d4ff !important; font-weight: 900 !important; font-size: 1.1rem !important;
    }

    /* حالة المحل */
    .status-badge { font-family: 'Orbitron'; padding: 5px 20px; border-radius: 50px; font-weight: 900; }
    .open { color: #00ff41; border: 1px solid #00ff41; box-shadow: 0 0 10px rgba(0,255,65,0.3); }
    .closed { color: #ff3131; border: 1px solid #ff3131; }

    /* زر التلغرام المشع */
    .tg-pulse {
        display: block; background: #229ED9; color: white !important;
        text-align: center; padding: 15px; border-radius: 12px;
        font-weight: 900; text-decoration: none; animation: tg-glow 1.5s infinite;
    }
    @keyframes tg-glow { 0% { box-shadow: 0 0 0 0 rgba(34, 158, 217, 0.5); } 70% { box-shadow: 0 0 0 10px rgba(34, 158, 217, 0); } 100% { box-shadow: 0 0 0 0 rgba(34, 158, 217, 0); } }

    /* حقول الإدخال */
    .stTextInput input { background: #0d1117 !important; color: white !important; border: 1px solid #30363d !important; border-radius: 10px !important; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. الدوال البرمجية والربط (Firebase Logic)
# ==============================================================================
@st.cache_resource
def init_connection():
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

init_connection()

def normalize_phone(p):
    p = re.sub(r"\D", "", str(p or ""))
    return "0" + p[3:] if p.startswith("213") else p

# ==============================================================================
# 3. الهيدر وحالة المحل
# ==============================================================================
try:
    is_open = db.reference("shop_settings/is_open").get()
except:
    is_open = True

st.markdown('<h1 class="neon-title">INFODOC</h1>', unsafe_allow_html=True)
st.markdown(f'<div style="text-align:center;"><span class="status-badge {"open" if is_open else "closed"}">{"ATELIER OUVERT" if is_open else "ATELIER FERMÉ"}</span></div>', unsafe_allow_html=True)

# شروط الصيانة (Expander منفصل علوي)
with st.expander("⚠️ شروط وملاحظات الصيانة"):
    st.markdown("""
        <div style="direction: rtl; text-align: right; font-size: 0.9rem; color: #8b949e;">
            • فحص الجهاز المصلح المرفوض: <b>1000 دج</b> ثمن الفحص والجهد.<br>
            • تبدأ أسعار العمل على البطاقة الأم من <b>3000 دج</b>.<br>
            • يرجى تفعيل بوت التلغرام لتلقي الإشعارات فور الجاهزية.
        </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 4. محرك البحث وعرض الأجهزة (Core System)
# ==============================================================================
st.write("---")
col_s1, col_s2, col_s3 = st.columns([1, 2, 1])
with col_s2:
    user_phone = st.text_input("🔍 أدخل رقم هاتفك لتتبع أجهزتك:", placeholder="مثال: 0798661900")

if user_phone:
    norm_phone = normalize_phone(user_phone)
    if len(norm_phone) >= 9:
        raw_data = db.reference("atelier").get()
        if raw_data:
            # تصفية الأجهزة بناءً على الرقم
            my_devices = [dict(v, _id=k) for k, v in raw_data.items() 
                          if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لم يتم العثور على أجهزة مسجلة بهذا الرقم.")
            else:
                # زر التلغرام
                bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                st.markdown(f'<a href="https://t.me/{bot_user}?start={norm_phone}" class="tg-pulse">🚀 ربط الحساب بالإشعارات الفورية على تليغرام</a>', unsafe_allow_html=True)
                
                # عرض كل جهاز في بلوك خاص به
                for dev in sorted(my_devices, key=lambda x: str(x.get("ID")), reverse=True):
                    status = dev.get("Statut", "En Cours")
                    
                    # 1. كرت رأس الجهاز
                    st.markdown(f"""
                        <div class="device-box">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <h2 style="margin:0; color:#fff !important;">{dev.get('Appareil')}</h2>
                                    <span style="color:#00d4ff; font-family:'Orbitron'; font-weight:bold;">#{dev.get('ID')}</span>
                                </div>
                                <div style="text-align: right;">
                                    <span style="color:#8b949e; font-size:0.8rem; display:block;">حالة الجهاز الحالية:</span>
                                    <b style="color:#00ff41; font-size:1.1rem;">{status}</b>
                                </div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 2. الأكورديون المخصص (البداية بالعمود 25)
                    with st.expander("📊 تفاصيل التقدم، المبالغ والضمان"):
                        
                        # --- جزء النسبة المئوية (العمود 25) ---
                        raw_prog = dev.get('Progression', 0) # تأكد أن الاسم في فيربايس مطابق
                        try:
                            prog_pct = float(str(raw_prog).replace('%', '').strip())
                        except:
                            prog_pct = 0
                            
                        st.markdown(f"""
                            <div style="margin-top: 10px; margin-bottom: 5px; display: flex; justify-content: space-between;">
                                <span style="font-weight: bold; color: #8b949e;">⚙️ نسبة إنجاز العمل:</span>
                                <span style="color: #00ff41; font-family: 'Orbitron'; font-weight: 900;">{int(prog_pct)}%</span>
                            </div>
                        """, unsafe_allow_html=True)
                        st.progress(min(prog_pct / 100, 1.0))
                        
                        # --- جزء المبالغ والتواريخ (Grid) ---
                        st.markdown(f"""
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px; 
                                        padding: 15px; background: rgba(255,255,255,0.03); border-radius: 12px; border: 1px solid #30363d;">
                                <div style="text-align: center;">
                                    <p style="margin:0; color:#8b949e; font-size:0.8rem;">المبلغ الإجمالي</p>
                                    <b style="color:#58a6ff; font-size:1.3rem; font-family:'Orbitron';">{dev.get('Prix')} <small>DA</small></b>
                                </div>
                                <div style="text-align: center; border-right: 1px solid #333;">
                                    <p style="margin:0; color:#8b949e; font-size:0.8rem;">تاريخ الاستلام</p>
                                    <b style="color:#fff; font-size:0.9rem;">{dev.get('Date_Entree')}</b>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # --- جزء الضمان (إن وجد) ---
                        if "Livré" in status:
                            st.markdown(f"<div style='text-align:center; margin-top:10px; color:#00ff41;'>🛡️ ضمان لمدة 30 يوم من تاريخ {dev.get('Date_Sortie')}</div>", unsafe_allow_html=True)

                        # زر تحميل الوصل (Excel)
                        excel_buf = io.BytesIO()
                        with pd.ExcelWriter(excel_buf, engine='xlsxwriter') as writer:
                            pd.DataFrame([dev]).to_excel(writer, index=False)
                        st.download_button(label=f"📥 تحميل وصل {dev.get('Appareil')}", 
                                         data=excel_buf.getvalue(), 
                                         file_name=f"InfoDoc_{dev.get('ID')}.xlsx", 
                                         key=f"dl_{dev.get('_id')}")

# ==============================================================================
# 5. بوت التلغرام في الخلفية (Background Thread)
# ==============================================================================
def bot_polling():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return
    bot = telebot.TeleBot(token)
    
    @bot.message_handler(commands=['start'])
    def handle_start(m):
        cmd = m.text.split()
        if len(cmd) > 1:
            phone = normalize_phone(cmd[1])
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(phone[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.reply_to(m, "✅ تم الربط بنجاح! ستصلك الإشعارات هنا.")
    
    try: bot.polling(none_stop=True)
    except: pass

if "bot_started" not in st.session_state:
    threading.Thread(target=bot_polling, daemon=True).start()
    st.session_state["bot_started"] = True
