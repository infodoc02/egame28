import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
import threading
import telebot
import pandas as pd
import io

# =================================================================
# 1. إعدادات الصفحة والاتصال بقاعدة البيانات (Firebase)
# =================================================================
st.set_page_config(
    page_title="InfoDoc - Client Portal",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

@st.cache_resource
def init_db():
    """تهيئة الاتصال بقاعدة بيانات فيربايس باستخدام Secrets"""
    if not firebase_admin._apps:
        try:
            cred_dict = dict(st.secrets["firebase"])
            if "\\n" in cred_dict["private_key"]:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
            return True
        except Exception as e:
            st.error(f"Error connecting to DB: {e}")
            return False
    return True

init_db()

# =================================================================
# 2. الدوال المساعدة (Helper Functions)
# =================================================================
def normalize_phone(phone: str) -> str:
    """تنظيف وتوحيد تنسيق رقم الهاتف الجزائري"""
    p = re.sub(r"\D", "", str(phone or ""))
    if p.startswith("213"):
        p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]:
        p = "0" + p
    return p

def get_warranty_stats(date_sortie_str):
    """حساب أيام الضمان المتبقية بناءً على تاريخ الخروج (30 يوم)"""
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None"]:
        return None
    
    date_formats = [
        "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", 
        "%Y-%m-%d", "%d-%m-%Y", 
        "%d/%m/%Y", "%d/%m/%Y %H:%M"
    ]
    
    for fmt in date_formats:
        try:
            date_s = datetime.strptime(str(date_sortie_str).strip(), fmt)
            diff_days = (datetime.now() - date_s).days
            remaining_days = max(30 - diff_days, 0)
            percent = (remaining_days / 30) * 100
            return {
                "percent": percent, 
                "is_expired": diff_days > 30, 
                "days_left": remaining_days
            }
        except:
            continue
    return None

# =================================================================
# 3. واجهة المستخدم (Advanced CSS Design)
# =================================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    /* الخلفية العامة */
    .stApp { 
        background: #0d1117; 
        color: white; 
        font-family: 'Cairo', sans-serif; 
    }
    
    /* تصميم العنوان الخرافي (الطلب 1) */
    .main-title {
        font-family: 'Orbitron', sans-serif;
        font-size: 3.5rem;
        font-weight: 900;
        text-align: center;
        margin-bottom: 0px;
        color: #fff;
        text-transform: uppercase;
        letter-spacing: 8px;
        text-shadow: 0 0 10px #58a6ff, 0 0 20px #58a6ff, 0 0 40px #58a6ff;
        animation: glow 2.5s ease-in-out infinite alternate;
    }
    
    @keyframes glow {
        from { text-shadow: 0 0 10px #58a6ff, 0 0 20px #58a6ff; }
        to { text-shadow: 0 0 20px #58a6ff, 0 0 40px #58a6ff, 0 0 60px #58a6ff; transform: scale(1.02); }
    }

    .sub-title {
        font-family: 'Cairo', sans-serif;
        font-size: 1.3rem;
        text-align: center;
        color: #8b949e;
        margin-top: -10px;
        margin-bottom: 30px;
        letter-spacing: 2px;
    }

    /* حالة المحل المضيئة (الطلب 2) */
    .status-container { text-align: center; margin: 20px 0; }
    .status-badge { 
        font-family: 'Orbitron'; 
        font-size: 1.2rem; 
        font-weight: 900; 
        padding: 8px 35px; 
        border-radius: 50px; 
        display: inline-block; 
    }
    .status-open { 
        color: #00ff41; 
        border: 3px solid #00ff41; 
        box-shadow: 0 0 20px #00ff41; 
        animation: neon-pulse-green 1.5s infinite; 
    }
    .status-closed { 
        color: #ff3131; 
        border: 3px solid #ff3131; 
        box-shadow: 0 0 20px #ff3131; 
        animation: neon-pulse-red 1.5s infinite; 
    }
    
    @keyframes neon-pulse-green { 
        0%, 100% { box-shadow: 0 0 10px #00ff41; opacity: 1; } 
        50% { box-shadow: 0 0 30px #00ff41; opacity: 0.7; } 
    }
    @keyframes neon-pulse-red { 
        0%, 100% { box-shadow: 0 0 10px #ff3131; opacity: 1; } 
        50% { box-shadow: 0 0 30px #ff3131; opacity: 0.7; } 
    }

    /* أزرار التواصل */
    .contact-grid { 
        display: grid; 
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); 
        gap: 20px; 
        margin-top: 30px; 
    }
    .contact-btn {
        text-decoration: none !important; 
        color: white !important; 
        background: rgba(255, 255, 255, 0.05);
        padding: 20px; 
        border-radius: 15px; 
        text-align: center; 
        border: 1px solid rgba(255, 255, 255, 0.1);
        transition: 0.4s; 
        display: flex; 
        flex-direction: column; 
        align-items: center; 
        gap: 10px;
    }
    .contact-btn:hover { 
        border-color: #58a6ff; 
        background: rgba(88, 166, 255, 0.1); 
        transform: translateY(-5px);
        box-shadow: 0 10px 20px rgba(0,0,0,0.5);
    }

    /* حقل إدخال الهاتف (الطلب 3) */
    div[data-baseweb="input"] {
        border-radius: 15px !important;
        border: 2px solid #30363d !important;
        background: #161b22 !important;
        padding: 5px !important;
        transition: 0.3s;
    }
    div[data-baseweb="input"]:focus-within {
        border-color: #58a6ff !important;
        box-shadow: 0 0 20px rgba(88, 166, 255, 0.2) !important;
    }

    /* بطاقة الجهاز والاكسباندر */
    .device-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 20px;
        padding: 25px;
        margin-bottom: 20px;
        transition: 0.3s;
    }
    .stExpander {
        border: 1px solid #30363d !important;
        border-radius: 15px !important;
        background: #0d1117 !important;
        margin-top: 15px !important;
        overflow: hidden;
    }
    
    /* زر التلغرام */
    .tg-link-btn { 
        display: block; 
        background: linear-gradient(90deg, #0088cc, #229ED9); 
        color: white !important; 
        text-align: center; 
        padding: 18px; 
        border-radius: 15px; 
        text-decoration: none; 
        font-weight: 900; 
        font-size: 1.1rem;
        margin-bottom: 30px;
        box-shadow: 0 4px 15px rgba(34, 158, 217, 0.3);
        transition: 0.3s;
    }
    .tg-link-btn:hover { 
        box-shadow: 0 0 30px #229ED9; 
        transform: scale(1.02); 
    }

    .badge { 
        padding: 6px 15px; 
        border-radius: 8px; 
        font-weight: bold; 
        font-size: 0.85rem; 
        font-family: 'Orbitron'; 
    }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 4. قسم رأس الصفحة (Header)
# =================================================================
# جلب وقت النظام
now = datetime.now()
greet = "صباح الخير" if 5 <= now.hour < 12 else "مساء الخير"

# جلب حالة المحل من قاعدة البيانات
try:
    is_open = db.reference("shop_settings/is_open").get()
except:
    is_open = True

status_class = "status-open" if is_open else "status-closed"
status_text = "OPEN" if is_open else "CLOSED"

st.markdown(f"""
    <div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: #8b949e; margin-bottom: 10px; padding: 0 10px;">
        <div>{greet} زبوننا الكريم | {now.strftime('%Y-%m-%d %H:%M')}</div>
        <div style="color: #58a6ff; font-weight: bold;">CHLEF, ALGERIA</div>
    </div>
    
    <div style="background: #161b22; border: 1px solid #30363d; border-radius: 25px; padding: 40px; margin-bottom: 30px; border-top: 5px solid #58a6ff; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
        <div style="text-align: center;">
            <div class="main-title">INFODOC</div>
            <div class="sub-title">Vente & Reparation de Matériel Informatique</div>
            <div class="status-container">
                <span class="status-badge {status_class}">{status_text}</span>
            </div>
        </div>
        
        <div class="contact-grid">
            <a href="tel:0798661900" class="contact-btn"><span style="font-size:2rem;">📞</span><b>اتصل بنا</b></a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="contact-btn"><span style="font-size:2rem;">📍</span><b>موقعنا</b></a>
            <a href="https://www.facebook.com/100095433977319/" target="_blank" class="contact-btn"><span style="font-size:2rem;">📘</span><b>فيسبوك</b></a>
            <a href="https://www.tiktok.com/@infodoc02" target="_blank" class="contact-btn"><span style="font-size:2rem;">📱</span><b>تيك توك</b></a>
        </div>
    </div>
""", unsafe_allow_html=True)

# =================================================================
# 5. محرك البحث ومعالجة البيانات
# =================================================================
st.markdown('<p style="text-align: center; color: #58a6ff; font-size: 1.2rem; font-weight: bold;">🔎 تتبع أجهزتك برقم الهاتف</p>', unsafe_allow_html=True)

# حقل الهاتف المزين (الطلب 3)
phone_input = st.text_input("", placeholder="مثال: 0798661900", key="user_phone")

if phone_input:
    phone_clean = normalize_phone(phone_input)
    
    if len(phone_clean) >= 9:
        # جلب البيانات من فيربايس
        db_ref = db.reference("atelier")
        raw_data = db_ref.get()
        
        if raw_data:
            # تصفية الأجهزة المطابقة للرقم
            user_devices = []
            for k, v in raw_data.items():
                if normalize_phone(v.get("Telephone", "")).endswith(phone_clean[-9:]):
                    v["_fb_key"] = k
                    user_devices.append(v)
            
            if not user_devices:
                st.warning("❌ عذراً، لا يوجد أي جهاز مسجل بهذا الرقم في قاعدتنا.")
            else:
                # ترتيب الأجهزة: الأجهزة التي لم تخرج أولاً
                user_devices.sort(key=lambda x: (str(x.get("Date_Sortie", "")) not in ["", "---", "None"], x.get("ID", 0)))
                
                # التحقق من ربط التلغرام
                if any(str(d.get("Telegram_ID", "")).strip() in ["", "None"] for d in user_devices):
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                    tg_url = f"https://t.me/{bot_user}?start={phone_clean}"
                    st.markdown(f'<a href="{tg_url}" target="_blank" class="tg-link-btn">🔔 تفعيل إشعارات التلغرام لهذا الرقم</a>', unsafe_allow_html=True)
                
                st.markdown("---")
                
                # عرض كل جهاز في بطاقة منفصلة
                for device in user_devices:
                    status = str(device.get("Statut", "En Cours"))
                    is_delivered = "Livré" in status
                    
                    # تحديد اللون بناءً على الحالة
                    color = "#238636" if status == "Prêt" else "#da3633" if status == "Annulé" else "#6e7681" if is_delivered else "#30363d"
                    
                    # تصميم الكارت
                    st.markdown(f"""
                        <div class="device-card" style="border-right: 8px solid {color};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <h2 style="margin:0; color:white; font-family:'Cairo';">{device.get('Appareil', 'Unknown')}</h2>
                                    <code style="color:#8b949e; font-size:1rem;">رقم الجهاز: #{device.get('ID', '000')}</code>
                                </div>
                                <span class="badge" style="background:{color}; color:white;">{status.upper()}</span>
                            </div>
                    """, unsafe_allow_html=True)
                    
                    # الأكورديون (الاكسباندر) المزين (الطلب 3)
                    with st.expander("📄 تفاصيل الصيانة، المبالغ والضمان"):
                        
                        # قسم الضمان أو التقدم
                        if is_delivered:
                            w_info = get_warranty_stats(device.get("Date_Sortie"))
                            if w_info and not w_info["is_expired"]:
                                st.markdown(f"🛡️ **الضمان ساري المفعول:** {int(w_info['days_left'])} يوم متبقي")
                                st.progress(w_info['percent']/100)
                            elif w_info and w_info["is_expired"]:
                                st.error("❌ فترة الضمان (30 يوم) قد انتهت.")
                        else:
                            prog_val = 0.33 if status == "En Cours" else 0.66 if status == "Réparable" else 1.0
                            st.write("🛠️ **حالة تقدم العملية:**")
                            st.progress(prog_val)
                        
                        # جدول المبالغ والتواريخ
                        st.markdown(f"""
                            <div style="background: #0d1117; padding: 20px; border-radius: 12px; border: 1px solid #30363d; margin: 15px 0;">
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; text-align: center;">
                                    <div>
                                        <small style="color:#8b949e;">تاريخ الدخول</small><br>
                                        <b>{device.get('Date_Entree', '---')}</b>
                                    </div>
                                    <div>
                                        <small style="color:#8b949e;">تاريخ الخروج</small><br>
                                        <b>{device.get('Date_Sortie', '---')}</b>
                                    </div>
                                </div>
                                <div style="margin-top: 20px; text-align: center; border-top: 1px solid #333; padding-top: 15px;">
                                    <span style="font-size: 1.1rem;">المبلغ الإجمالي المستحق:</span><br>
                                    <span style="font-size: 2rem; color: #58a6ff; font-weight: 900;">{device.get('Prix', '0')} DA</span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # زر تحميل الفاتورة
                        try:
                            df_excel = pd.DataFrame([{"ID": device.get('ID'), "Device": device.get('Appareil'), "Price": device.get('Prix'), "Status": status}])
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                                df_excel.to_excel(writer, index=False)
                            st.download_button(
                                label=f"📥 تحميل فاتورة جهاز {device.get('Appareil')}",
                                data=output.getvalue(),
                                file_name=f"InfoDoc_{device.get('ID')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"btn_{device.get('_fb_key')}"
                            )
                        except:
                            st.info("خدمة تحميل الفاتورة غير متوفرة حالياً لهذا الجهاز.")

                    st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.error("⚠️ فشل في الاتصال بقاعدة البيانات. حاول لاحقاً.")

# =================================================================
# 6. تشغيل بوت التلغرام في الخلفية (Background Thread)
# =================================================================
def run_telegram_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token:
        return
        
    bot = telebot.TeleBot(token)
    
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        msg_text = message.text
        if len(msg_text.split()) > 1:
            p_num = normalize_phone(msg_text.split()[1])
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                found = False
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p_num[-9:]):
                        ref.child(k).update({"Telegram_ID": str(message.chat.id)})
                        found = True
                if found:
                    bot.reply_to(message, "✅ تم ربط حسابك بنجاح! ستصلك إشعارات عند جاهزية أجهزتك.")
                else:
                    bot.reply_to(message, "❌ لم نجد أجهزة مسجلة بهذا الرقم.")
        else:
            bot.reply_to(message, "مرحباً بك في InfoDoc. يرجى استخدام الرابط من الموقع لربط حسابك.")

    bot.polling(none_stop=True)

# تشغيل البوت مرة واحدة فقط
if "bot_thread_started" not in st.session_state:
    try:
        thread = threading.Thread(target=run_telegram_bot, daemon=True)
        thread.start()
        st.session_state["bot_thread_started"] = True
    except:
        pass
