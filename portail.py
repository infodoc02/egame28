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
# تم ضبط الإعدادات لتكون متوافقة مع شاشات الهواتف والحاسوب
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
            # معالجة مفتاح الخصوصية إذا كان يحتوي على رموز سطر جديد
            if "\\n" in cred_dict["private_key"]:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
            return True
        except Exception as e:
            st.error(f"خطأ في الاتصال بقاعدة البيانات: {e}")
            return False
    return True

# تفعيل الاتصال
init_db()

# =================================================================
# 2. الدوال المساعدة ومعالجة البيانات (Helper Functions)
# =================================================================
def normalize_phone(phone: str) -> str:
    """تنظيف وتوحيد تنسيق رقم الهاتف الجزائري لضمان دقة البحث"""
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
    
    # تجربة عدة تنسيقات للوقت لضمان عدم حدوث خطأ
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
# 3. واجهة المستخدم والتنسيقات البصرية (CSS Styling)
# =================================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    /* الخلفية العامة للتطبيق */
    .stApp { 
        background: #0d1117; 
        color: white; 
        font-family: 'Cairo', sans-serif; 
    }
    
    /* الطلب 1: تصميم العنوان النيوني */
    .main-title {
        font-family: 'Orbitron', sans-serif;
        font-size: clamp(2rem, 8vw, 3.5rem);
        font-weight: 900;
        text-align: center;
        margin-bottom: 0px;
        color: #fff;
        text-transform: uppercase;
        letter-spacing: 5px;
        text-shadow: 0 0 10px #58a6ff, 0 0 20px #58a6ff;
        animation: glow 2s ease-in-out infinite alternate;
    }
    
    @keyframes glow {
        from { text-shadow: 0 0 10px #58a6ff, 0 0 20px #58a6ff; }
        to { text-shadow: 0 0 20px #58a6ff, 0 0 40px #58a6ff; transform: scale(1.01); }
    }

    .sub-title {
        font-family: 'Cairo', sans-serif;
        font-size: 1.1rem;
        text-align: center;
        color: #8b949e;
        margin-top: -5px;
        margin-bottom: 25px;
    }

    /* الطلب 2: حالة المحل المضيئة */
    .status-badge { 
        font-family: 'Orbitron'; 
        font-size: 1rem; 
        font-weight: 900; 
        padding: 6px 25px; 
        border-radius: 50px; 
        display: inline-block;
    }
    .status-open { 
        color: #00ff41; border: 2px solid #00ff41; 
        box-shadow: 0 0 15px rgba(0, 255, 65, 0.4);
        animation: pulse-green 1.5s infinite; 
    }
    .status-closed { 
        color: #ff3131; border: 2px solid #ff3131; 
        box-shadow: 0 0 15px rgba(255, 49, 49, 0.4);
        animation: pulse-red 1.5s infinite; 
    }
    
    @keyframes pulse-green { 0% { box-shadow: 0 0 5px #00ff41; } 50% { box-shadow: 0 0 20px #00ff41; } 100% { box-shadow: 0 0 5px #00ff41; } }
    @keyframes pulse-red { 0% { box-shadow: 0 0 5px #ff3131; } 50% { box-shadow: 0 0 20px #ff3131; } 100% { box-shadow: 0 0 5px #ff3131; } }

    /* أزرار التواصل */
    .contact-grid { 
        display: grid; 
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); 
        gap: 15px; 
        margin-top: 25px; 
    }
    .contact-btn {
        text-decoration: none !important; color: white !important; 
        background: rgba(255, 255, 255, 0.03);
        padding: 15px; border-radius: 12px; text-align: center; 
        border: 1px solid rgba(255, 255, 255, 0.1);
        transition: 0.3s; display: flex; flex-direction: column; align-items: center; gap: 8px;
    }
    .contact-btn:hover { 
        border-color: #58a6ff; background: rgba(88, 166, 255, 0.1); 
        transform: translateY(-3px); 
    }

    /* الطلب 3: حقل الهاتف */
    div[data-baseweb="input"] {
        border-radius: 12px !important;
        border: 2px solid #30363d !important;
        background: #161b22 !important;
        transition: 0.3s;
    }
    div[data-baseweb="input"]:focus-within {
        border-color: #58a6ff !important;
        box-shadow: 0 0 15px rgba(88, 166, 255, 0.2) !important;
    }

    /* الطلب 3: المربعات (تم تحسين الهيكل لمنع المشاكل) */
    .device-header {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 15px 15px 0 0;
        padding: 20px;
        margin-top: 20px;
    }
    
    .stExpander {
        border: 1px solid #30363d !important;
        border-top: none !important;
        border-radius: 0 0 15px 15px !important;
        background: #0d1117 !important;
        margin-bottom: 20px !important;
    }
    
    /* زر التلغرام */
    .tg-link-btn { 
        display: block; background: #229ED9; color: white !important; 
        text-align: center; padding: 15px; border-radius: 12px; 
        text-decoration: none; font-weight: 900; margin-bottom: 25px;
        transition: 0.3s;
    }
    .tg-link-btn:hover { box-shadow: 0 0 20px #229ED9; transform: scale(1.01); }

    .badge { 
        padding: 4px 12px; border-radius: 6px; 
        font-weight: bold; font-size: 0.8rem; font-family: 'Orbitron'; 
    }
    </style>
""", unsafe_allow_html=True)

# =================================================================
# 4. قسم الترحيب ورأس الصفحة
# =================================================================
now = datetime.now()
greet = "صباح الخير" if 5 <= now.hour < 12 else "مساء الخير"

try:
    is_open = db.reference("shop_settings/is_open").get()
except:
    is_open = True

st.markdown(f"""
    <div style="display: flex; justify-content: space-between; font-size: 0.8rem; color: #8b949e; margin-bottom: 10px;">
        <div>{greet} زبوننا الكريم | {now.strftime('%d/%m/%Y %H:%M')}</div>
        <div style="color: #58a6ff;">INFODOC CHLEF</div>
    </div>
    
    <div style="background: #161b22; border: 1px solid #30363d; border-radius: 20px; padding: 30px; margin-bottom: 25px; border-top: 4px solid #58a6ff;">
        <div style="text-align: center;">
            <div class="main-title">INFODOC</div>
            <div class="sub-title">VENTE ET REPARATION INFORMATIQUE</div>
            <div style="margin-top: 15px;">
                <span class="status-badge {'status-open' if is_open else 'status-closed'}">
                    {'OPEN' if is_open else 'CLOSED'}
                </span>
            </div>
        </div>
        
        <div class="contact-grid">
            <a href="tel:0798661900" class="contact-btn"><span>📞</span><b>اتصل بنا</b></a>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="contact-btn"><span>📍</span><b>موقعنا</b></a>
            <a href="https://www.facebook.com/100095433977319/" target="_blank" class="contact-btn"><span>📘</span><b>فيسبوك</b></a>
            <a href="https://www.tiktok.com/@infodoc02" target="_blank" class="contact-btn"><span>📱</span><b>تيك توك</b></a>
        </div>
    </div>
""", unsafe_allow_html=True)

# =================================================================
# 5. نظام البحث وعرض النتائج
# =================================================================
st.markdown('<p style="text-align: center; color: #8b949e;">أدخل رقم الهاتف المسجل في الوصل للمتابعة</p>', unsafe_allow_html=True)
phone_input = st.text_input("", placeholder="0XXXXXXXXX", key="phone_search")

if phone_input:
    phone_clean = normalize_phone(phone_input)
    
    if len(phone_clean) >= 9:
        # جلب البيانات
        db_ref = db.reference("atelier")
        all_data = db_ref.get()
        
        if all_data:
            # البحث عن الأجهزة
            found_devices = []
            for k, v in all_data.items():
                if normalize_phone(v.get("Telephone", "")).endswith(phone_clean[-9:]):
                    v["_id"] = k
                    found_devices.append(v)
            
            if not found_devices:
                st.error("❌ لا توجد أجهزة مرتبطة بهذا الرقم.")
            else:
                # ترتيب: الأجهزة قيد الصيانة أولاً
                found_devices.sort(key=lambda x: (str(x.get("Date_Sortie", "")) not in ["", "---", "None"], x.get("ID", 0)))
                
                # زر التلغرام إذا لم يتم الربط
                if any(not d.get("Telegram_ID") for d in found_devices):
                    bot_name = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                    st.markdown(f'<a href="https://t.me/{bot_name}?start={phone_clean}" target="_blank" class="tg-link-btn">🚀 تفعيل إشعارات التلغرام لهذا الرقم</a>', unsafe_allow_html=True)
                
                st.write(f"✅ تم العثور على ({len(found_devices)}) جهاز:")

                for d in found_devices:
                    stat = str(d.get("Statut", "En Cours"))
                    is_livre = "Livré" in stat
                    color = "#238636" if stat == "Prêt" else "#da3633" if stat == "Annulé" else "#6e7681" if is_livre else "#58a6ff"
                    
                    # رأس المربع (Header)
                    st.markdown(f"""
                        <div class="device-header" style="border-right: 6px solid {color};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <h3 style="margin:0; color:white;">{d.get('Appareil')}</h3>
                                    <small style="color:#8b949e;">رقم التذكرة: #{d.get('ID')}</small>
                                </div>
                                <span class="badge" style="background:{color}; color:white;">{stat.upper()}</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # محتوى المربع داخل Expander (لحل مشكلة المربعات)
                    with st.expander("📄 تفاصيل الصيانة والسعر والضمان"):
                        
                        # 1. شريط الحالة
                        if is_livre:
                            w = get_warranty_stats(d.get("Date_Sortie"))
                            if w and not w["is_expired"]:
                                st.write(f"🛡️ ضمان متبقي: {int(w['days_left'])} يوم")
                                st.progress(w['percent']/100)
                            else:
                                st.error("❌ الضمان منتهي")
                        else:
                            st.write("🛠️ حالة الصيانة:")
                            p_val = 0.3 if stat == "En Cours" else 0.7 if stat == "Réparable" else 1.0
                            st.progress(p_val)
                        
                        # 2. تفاصيل البيانات
                        st.markdown(f"""
                            <div style="background: #0d1117; padding: 15px; border-radius: 10px; border: 1px solid #30363d; margin: 10px 0;">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                                    <span><b>استلام:</b> {d.get('Date_Entree')}</span>
                                    <span><b>خروج:</b> {d.get('Date_Sortie', '---')}</span>
                                </div>
                                <div style="text-align: center; border-top: 1px solid #333; padding-top: 10px;">
                                    <span style="font-size: 1.2rem; color: #58a6ff; font-weight: 900;">السعر: {d.get('Prix')} دج</span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # 3. زر التحميل
                        try:
                            df = pd.DataFrame([{"ID": d.get('ID'), "الجهاز": d.get('Appareil'), "السعر": d.get('Prix')}])
                            buf = io.BytesIO()
                            with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
                                df.to_excel(wr, index=False)
                            st.download_button(label=f"📥 فاتورة {d.get('Appareil')}", data=buf.getvalue(), file_name=f"InfoDoc_{d.get('ID')}.xlsx", key=f"dl_{d.get('_id')}")
                        except: pass

# =================================================================
# 6. بوت التلغرام (العمل في الخلفية)
# =================================================================
def start_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return
    bot = telebot.TeleBot(token)
    
    @bot.message_handler(commands=['start'])
    def handle(m):
        txt = m.text.split()
        if len(txt) > 1:
            p = normalize_phone(txt[1])
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(p[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.reply_to(m, "✅ تم ربط جهازك بنجاح!")
    
    bot.polling(none_stop=True)

if "bot_started" not in st.session_state:
    threading.Thread(target=start_bot, daemon=True).start()
    st.session_state["bot_started"] = True
