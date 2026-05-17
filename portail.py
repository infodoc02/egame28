import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
import pandas as pd
import threading
import telebot
import io
import pytz

# ==============================================================================
# 1. إعدادات الصفحة الأساسية ونظام المظهر الفاخر (Configuration & Theme)
# ==============================================================================
st.set_page_config(
    page_title="InfoDoc - Client Portal",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# تحسين الـ CSS المخصص ليواكب المظهر الزجاجي والاحترافي للتطبيق الرئيسي
st.markdown("""
    <style>
    /* تحسين الخلفية العامة للبورطاي */
    .stApp {
        background: radial-gradient(circle at top left, #1e3a8a, #0f172a);
        background-attachment: fixed;
    }
    
    /* ضبط الحاويات والبطاقات الافتراضية */
    [data-testid="stVerticalBlock"] { padding-top: 1rem !important; }
    
    /* تنسيق الأزرار بشكل مستجيب وجذاب */
    div.stButton > button:first-child {
        width: 100% !important;
        border-radius: 12px !important;
        height: 3em !important;
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%) !important;
        color: white !important;
        font-weight: 700 !important;
        border: none !important;
        box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3) !important;
        transition: all 0.3s ease !important;
    }
    div.stButton > button:first-child:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5) !important;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. الاتصال الآمن بقاعدة البيانات ونظام تتبع الزوار (Firebase & Visitor Tracking)
# ==============================================================================
@st.cache_resource
def init_db():
    """ربط التطبيق بـ Firebase مع معالجة حماية الانهيار (Fail-safe)."""
    if not firebase_admin._apps:
        try:
            # محاولة جلب البيانات من Secrets بأمان
            if "firebase" in st.secrets and "DB_URL" in st.secrets:
                cred_dict = dict(st.secrets["firebase"])
                if "\\n" in cred_dict.get("private_key", ""):
                    cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
                
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, {'databaseURL': st.secrets["DB_URL"]})
                return True
            else:
                # وضع احتياطي محلي في حال غياب السيكرتس لتجنب توقف البورطاي
                st.warning("⚠️ Mode local/limité activé (Secrets non configurés).")
                return False
        except Exception as e:
            st.error(f"❌ Erreur connexion Firebase: {e}")
            return False
    return True

# تفعيل الاتصال
db_status = init_db()

def track_visitor():
    """دالة تعقب وإحصاء زوار البورطاي بشكل فريد يومياً عبر قاعدة البيانات."""
    if not db_status: return
    try:
        tz = pytz.timezone('Africa/Algiers')
        today_str = datetime.now(tz).strftime("%Y-%m-%d")
        
        # جلب الـ IP الخاص بالزائر باستخدام الـ Headers الافتراضية
        from streamlit.web.server.server import Server
        import tornado.web
        
        # محاولة ذكية لجلب الـ IP بدون إحداث بطء في التصفح
        ip = "127.0.0.1"
        try:
            headers = st.context.headers
            ip = headers.get("X-Forwarded-For", headers.get("Remote-Addr", "127.0.0.1")).split(",")[0].strip()
        except:
            pass
            
        clean_ip = ip.replace(".", "_")
        ref = db.reference(f"visitor_tracking/{today_str}/{clean_ip}")
        ref.set({
            "timestamp": datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
            "device": "Portal_Client"
        })
    except:
        pass

# تشغيل التتبع التلقائي في الخلفية عند دخول العميل
if db_status:
    track_visitor()

# ==============================================================================
# 3. الدوال البرمجية المساعدة وإدارة الحالات والضمان (Helper Functions)
# ==============================================================================

def normalize_phone(phone: str) -> str:
    """تنسيق وتوحيد رقم الهاتف الجزائري ليطابق المخزن في السيرفر الرئيسي."""
    if not phone: return ""
    p = re.sub(r"\D", "", str(phone))
    
    if p.startswith("213"):
        p = "0" + p[3:]
    elif p.startswith("00213"):
        p = "0" + p[5:]
    
    if len(p) == 9 and p[0] in ["5", "6", "7"]:
        p = "0" + p
        
    return p

def get_warranty_stats(date_sortie_str):
    """حساب وضمان الأجهزة المستلمة بدقة رياضية متناهية."""
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None", "nan"]:
        return None
    
    date_formats = [
        "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", 
        "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d", "%d-%m-%Y", 
        "%d/%m/%Y", "%d/%m/%Y %H:%M"
    ]
    
    tz = pytz.timezone('Africa/Algiers')
    now = datetime.now(tz).replace(tzinfo=None)
    date_s = None
    
    for fmt in date_formats:
        try:
            date_s = datetime.strptime(str(date_sortie_str).strip(), fmt)
            break 
        except ValueError:
            continue
    
    if date_s:
        diff_days = (now - date_s).days
        remaining_days = max(30 - diff_days, 0)
        percent = (remaining_days / 30) * 100
        return {
            "percent": int(percent), 
            "is_expired": diff_days > 30, 
            "days_left": remaining_days,
            "actual_date": date_s.strftime("%d/%m/%Y")
        }
    
    return None

def get_status_priority(status):
    """تحديد أولوية الفرز لعرض الأجهزة الجاهزة للزبون أولاً (Dashboard Priority)."""
    s = str(status).strip()
    if s == "Prêt": return 1
    elif s == "Annulé": return 2
    elif s == "Non Réparable": return 3
    elif s == "Réparable": return 4
    elif s == "En Cours": return 5
    elif s == "En Attente": return 6
    else: return 99
# ==============================================================================
# 3. واجهة المستخدم وتتبع الزوار الذكي (UI & Visitor Tracking)
# ==============================================================================

# منطق التحقق الصارم بالـ IP لضمان الدقة ومنع التكرار في نفس الجلسة
if 'tracked' not in st.session_state:
    try:
        import requests
        # جلب الـ IP الفعلي للزائر عبر خدمة سريعة ومحمية بوقت استجابة 3 ثوانٍ
        res = requests.get('https://api.ipify.org', timeout=3)
        if res.status_code == 200:
            user_ip = res.text.replace('.', '_')
            today = datetime.now(pytz.timezone('Africa/Algiers')).strftime('%Y-%m-%d')
            
            # المرجع المباشر للـ IP الخاص باليوم في قاعدة البيانات
            check_ref = db.reference(f"stats/daily_ips/{today}/{user_ip}").get()
            
            if check_ref is None:
                # تسجيل الـ IP فوراً لمنع تكرار العداد عند إعادة تحديث الصفحة
                db.reference(f"stats/daily_ips/{today}/{user_ip}").set(True)
                
                # تحديث عداد الزوار اليومي الفريد تلقائياً
                current_count = db.reference(f"stats/daily_visitors/{today}").get() or 0
                db.reference(f"stats/daily_visitors/{today}").set(current_count + 1)
            
            st.session_state['tracked'] = True
    except:
        pass

# إعداد التوقيت المحلي والترحيب بالزبائن
algeria_tz = pytz.timezone('Africa/Algiers')
now = datetime.now(algeria_tz)
greeting = "عزيزي الزبون، صباح الخير ☀️" if 5 <= now.hour < 12 else "عزيزي الزبون، مساء الخير ✨"

# جلب حالة المحل الحالية من السيرفر الرئيسي
try:
    shop_status = db.reference("shop_settings/is_open").get()
    if shop_status is None:
        shop_status = False
except:
    shop_status = False

# تأثيرات الأنيميشن لحالة المحل (مفتوح / مغلق) منفصلة تماماً
st.markdown("""
    <style>
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; } 50% { opacity: 0.8; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; } 50% { opacity: 0.8; } }
    .badge-open { color: #3fb950; border: 2px solid #3fb950; animation: blink-green 2.5s infinite; }
    .badge-closed { color: #f85149; border: 2px solid #f85149; animation: blink-red 2.5s infinite; }
    </style>
""", unsafe_allow_html=True)

# عرض الهيدر الرئيسي (Hero Container) بتصميم زجاجي فاخر ومستقل
st.markdown(f'''
    <div style="background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%); 
                border: 1px solid #334155; border-radius: 16px; padding: 30px; 
                margin-bottom: 25px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
        <div style="color: #94a3b8; font-size: 0.95rem; font-family: 'Cairo', sans-serif; margin-bottom: 8px;">
            {greeting} | 📅 {now.strftime("%Y-%m-%d %H:%M")}
        </div>
        <div style="font-family: 'Orbitron', sans-serif; color: #3b82f6; font-size: 3.5rem; font-weight: 900; letter-spacing: 2px; text-shadow: 0 0 20px rgba(59, 130, 246, 0.4);">
            INFODOC
        </div>
        <div style="color: #cbd5e1; font-family: 'Cairo', sans-serif; font-size: 1.1rem; font-weight: 700; margin-top: 5px; margin-bottom: 20px;">
            🚀 Vente & Réparation Informatique Professionnelle
        </div>
        <span class="{"badge-open" if shop_status else "badge-closed"}" 
              style="padding: 10px 24px; border-radius: 12px; font-weight: 900; display: inline-block; font-family: 'Cairo', sans-serif; font-size: 1rem; background: rgba(0,0,0,0.2);">
            {'● OPEN - مـفـتـوح مـرحـبـاً بـكـم' if shop_status else '● CLOSED - مـغـلـق حـالـيـاً'}
        </span>
    </div>
''', unsafe_allow_html=True)


# ==============================================================================
# 4. أزرار التواصل السريع (Quick Contact Buttons)
# ==============================================================================
# تصميم مستقل تماماً لكل زر لتفادي أي تداخل برمجياً وبصرياً
st.markdown("""
    <style>
    .portal-contact-btn {
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        background: #1e293b; border: 1px solid #334155; border-radius: 14px;
        padding: 15px 10px; text-decoration: none !important; color: #e2e8f0 !important;
        transition: 0.3s all ease; height: 90px; text-align: center;
    }
    .portal-contact-btn:hover {
        background: #0f172a; border-color: #3b82f6;
        transform: translateY(-4px); box-shadow: 0 6px 20px rgba(59, 130, 246, 0.25);
        color: #3b82f6 !important;
    }
    .portal-contact-btn .icon { font-size: 1.8rem; margin-bottom: 6px; }
    .portal-contact-btn .label { font-family: 'Cairo', sans-serif; font-size: 0.95rem; font-weight: 700; }
    </style>
""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)

with c1: 
    st.markdown('<a href="tel:0798661900" class="portal-contact-btn"><span class="icon">📞</span><span class="label">اتصل بنا</span></a>', unsafe_allow_html=True)

with c2: 
    st.markdown('<a href="https://maps.app.goo.gl/RBGLbVDiCeqAdxVT8" target="_blank" class="portal-contact-btn"><span class="icon">📍</span><span class="label">موقعنا على الخريطة</span></a>', unsafe_allow_html=True)

with c3: 
    st.markdown('<a href="https://www.facebook.com/share/18dX9h9otd/" target="_blank" class="portal-contact-btn"><span class="icon">📘</span><span class="label">صفحة الفيسبوك</span></a>', unsafe_allow_html=True)

with c4: 
    st.markdown('<a href="https://tiktok.com/@infodoc02/" target="_blank" class="portal-contact-btn"><span class="icon">📱</span><span class="label">تيك توك</span></a>', unsafe_allow_html=True)


# ==============================================================================
# 5. قسم الشروط والملاحظات الهامة (Glow Expander)
# ==============================================================================
# أنيميشن ومظهر خاص للأكسباندر التحذيري ليكون مضيئاً وجاذباً للانتباه بشكل مستقل
st.markdown("""
    <style>
    @keyframes gold-glow {
        0%, 100% { border-color: #eab308; box-shadow: 0 0 6px rgba(234, 179, 8, 0.3); }
        50% { border-color: #facc15; box-shadow: 0 0 20px rgba(250, 204, 21, 0.6); }
    }
    .rules-expander {
        border: 2px solid #eab308 !important;
        animation: gold-glow 3s infinite ease-in-out !important;
        background: rgba(234, 179, 8, 0.03) !important;
        border-radius: 14px !important;
        margin-top: 25px !important;
        margin-bottom: 25px !important;
    }
    .rules-expander summary {
        direction: rtl !important; text-align: right !important;
        display: flex !important; justify-content: space-between !important;
        flex-direction: row-reverse !important; padding: 12px 20px !important;
    }
    .rules-expander summary p {
        font-family: 'Cairo', sans-serif !important; font-weight: 900 !important;
        color: #facc15 !important; font-size: 1.1rem !important; margin: 0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# إنشاء الحاوية المضيئة المخصصة للشروط
st.markdown('<div class="rules-expander">', unsafe_allow_html=True)
with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: 'Cairo', sans-serif; line-height: 2; color: #f1f5f9; padding: 15px; font-size: 0.95rem;">
            1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<b>رفض الزبون ذلك</b>، يتم دفع <b>1000 دج</b> ثمن الجهد والفحص المخبري وعمليات القياس.<br>
            2️⃣ أسعار العمل الدقيق على <b>البطاقة الأم (Carte Mère)</b> والمكونات الإلكترونية المجهرية تبدأ من <b>3000 دج</b>.<br>
            3️⃣ أسعار <b>تفليش وفتح البيوس وبرمجة السوبر آي أو (Flash BIOS / SIO)</b> تبدأ من <b>1500 دج</b> حسب جيل ونوع معالج الجهاز.<br>
            4️⃣ <b>سياسة الموافقة التلقائية:</b> نقوم بالإصلاح مباشرة وبدون الاتصال بك إذا كانت التكلفة بين 3000 و 4000 دج لتسريع التسليم. فوق ذلك نتصل بك لأخذ موافقتك مسبقاً.<br>
            5️⃣ <b>شروط الضمان:</b> الضمان الممنوح (30 يوماً) صالح <b>حصراً</b> على العيب أو العنصر الإلكتروني الذي تم إصلاحه، وأي خلل مفاجئ يمس مكوناً آخر لا يدخل ضمن الضمان.<br>
            6️⃣ <b>تحديثات فورية لهاتفك:</b> نوصي بشدة بفتح حساب في تطبيق <b>Telegram</b>، ثم الضغط على الزر الخاص بنا بالأسفل لربط حسابك لتلقي إشعارات حية حول حالة جهازك (En cours / Prêt) مباشرة وبشكل مؤتمت.
        </div>
    """, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)
st.divider()
# ==============================================================================
# 5. نظام البحث والتتبع (النسخة النهائية المستقرة والمريغلة)
# ==============================================================================

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    /* فرض اليمين على حقل إدخال الهاتف */
    div[data-testid="stTextInput"] input {
        direction: rtl !important;
        text-align: right !important;
        font-family: 'Cairo', sans-serif !important;
    }
    
    /* ضبط الأكسباندر: شفاف تماماً ومحاذاته لليمين */
    div[data-testid="stExpander"] {
        background: transparent !important;
        border: 1px solid #334155 !important;
        border-top: none !important;
        border-radius: 0 0 12px 12px !important;
        margin-top: -2px !important;
        padding: 0px !important;
    }
    div[data-testid="stExpander"] summary {
        direction: rtl !important;
        text-align: right !important;
    }
    div[data-testid="stExpander"] summary p {
        font-family: 'Cairo', sans-serif !important;
        font-weight: 700 !important;
        color: #3b82f6 !important;
        margin: 0 !important;
    }

    /* زر التلغرام العائم */
    .floating-tg-button {
        position: fixed;
        bottom: 30px;
        left: 30px;
        background: linear-gradient(135deg, #24A1DE 0%, #1d80b0 100%);
        color: white !important;
        padding: 12px 22px;
        border-radius: 50px;
        box-shadow: 0 8px 20px rgba(36, 161, 222, 0.4);
        z-index: 99999;
        font-family: 'Cairo', sans-serif;
        font-weight: bold;
        font-size: 0.95rem;
        text-decoration: none;
        display: flex;
        align-items: center;
        gap: 8px;
        animation: tg-bounce 2.5s infinite ease-in-out;
        border: 1px solid rgba(255,255,255,0.2);
    }
    @keyframes tg-bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-8px); }
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<h3 style="text-align: right; font-family: \'Cairo\', sans-serif; color: #cbd5e1; font-size: 1.2rem; margin-bottom: 5px;">🔍 تتبع حالة أجهزتك الآن:</h3>', unsafe_allow_html=True)

with st.form("search_form", clear_on_submit=False):
    user_phone = st.text_input("", placeholder="أدخل رقم هاتفك هنا (مثال: 0798661900)", label_visibility="collapsed")
    submit_search = st.form_submit_button("⚡ ابحث عن أجهزتي في الورشة")

if submit_search and user_phone:
    norm_phone = normalize_phone(user_phone)
    if len(norm_phone) < 9:
        st.error("⚠️ يرجى إدخال رقم هاتف صحيح.")
    else:
        with st.spinner("⏳ جاري فحص السيرفر..."):
            db_ref = db.reference("atelier")
            raw_data = db_ref.get()
            
            if raw_data:
                my_devices = [
                    dict(v, _id=k) for k, v in raw_data.items() 
                    if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])
                ]
                
                if not my_devices:
                    st.warning("⚠️ لم نجد أي جهاز مسجل بهذا الرقم.")
                else:
                    # 1. زر التلغرام العائم
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDoc_Workshop_Bot")
                    st.markdown(f'''
                        <a href="https://t.me/{bot_user}?start={norm_phone}" target="_blank" class="floating-tg-button">
                            <span>📢 تفعيل الإشعارات (Telegram)</span>
                        </a>
                    ''', unsafe_allow_html=True)
                
                    # 2. ترتيب التذاكر تنازلياً
                    my_devices.sort(key=lambda x: -int(x.get("ID", 0)) if str(x.get("ID", 0)).isdigit() else 0)
                
                    for dev in my_devices:
                        status_raw = str(dev.get("Statut", "En Attente")).strip()
                        status_lower = status_raw.lower()
                        
                        # --- إرجاع الألوان الأصلية وتوحيد المقاسات بالتنظيم الجديد ---
                        if "prêt" in status_lower or "pret" in status_lower:
                            s_color, s_bg, s_text = "#22c55e", "rgba(34, 197, 94, 0.15)", "🟢 Prêt"
                        elif "réparable" in status_lower or "reparable" in status_lower:
                            s_color, s_bg, s_text = "#3b82f6", "rgba(59, 130, 246, 0.15)", "🔧 Réparable"
                        elif "annulé" in status_lower or "annule" in status_lower:
                            s_color, s_bg, s_text = "#ef4444", "rgba(239, 68, 68, 0.15)", "❌ Annulé"
                        elif "non réparable" in status_lower or "non reparable" in status_lower:
                            s_color, s_bg, s_text = "#ef4444", "rgba(239, 68, 68, 0.15)", "⚠️ Non Réparable"
                        elif "en cours" in status_lower:
                            s_color, s_bg, s_text = "#3b82f6", "rgba(59, 130, 246, 0.15)", "⚙️ En Cours"
                        elif "en attente" in status_lower:
                            s_color, s_bg, s_text = "#facc15", "rgba(250, 204, 21, 0.15)", "🟡 En Attente"
                        elif "livré" in status_lower or "livre" in status_lower or "payé" in status_lower or "paye" in status_lower:
                            if "dette" in status_lower or "credit" in status_lower:
                                s_color, s_bg, s_text = "#a855f7", "rgba(168, 85, 247, 0.15)", "📦 Livré (Dette)"
                            else:
                                s_color, s_bg, s_text = "#a855f7", "rgba(168, 85, 247, 0.15)", "✅ Livré & Payé"
                        else:
                            s_color, s_bg, s_text = "#94a3b8", "rgba(148, 163, 184, 0.15)", status_raw

                        # --- تنسيق السعر بخط Orbitron ومنع الانعكاس ---
                        raw_prix = dev.get('Prix', 0)
                        if "en cours" in status_lower or "en attente" in status_lower:
                            prix_html = '<span style="color: #94a3b8; font-size: 0.95rem; font-family: \'Cairo\';">⚙️ قيد الفحص...</span>'
                        else:
                            try:
                                formatted_p = f"{int(float(raw_prix)):,}".replace(',', ' ')
                                prix_html = f'<div style="display: inline-block; direction: ltr;"><span style="font-family: \'Orbitron\', sans-serif; font-size: 1.35rem; color: #facc15; font-weight: 900;">{formatted_p}</span> <span style="font-family: \'Cairo\', sans-serif; font-size: 0.95rem; color: #facc15; font-weight: bold;">DA</span></div>'
                            except: 
                                prix_html = '<div style="display: inline-block; direction: ltr;"><span style="font-family: \'Orbitron\', sans-serif; font-size: 1.35rem; color: #facc15;">0</span> <span style="font-family: \'Cairo\', sans-serif; font-size: 0.95rem; color: #facc15;">DA</span></div>'

                        # --- الكرت العلوي للجهاز (عرض ثابت ومحاذاة لليمين) ---
                        st.markdown(f"""
                            <div style="background: #1e293b; border: 1px solid #334155; border-right: 5px solid {s_color}; 
                                        border-radius: 12px 12px 0 0; padding: 12px 16px; margin-top: 10px; 
                                        font-family: 'Cairo', sans-serif; direction: rtl; text-align: right;">
                                <div style="display: flex; justify-content: space-between; align-items: center; flex-direction: row-reverse; gap: 10px;">
                                    <!-- العرض الثابت الموحد للحالات (150px) لمنع اختلاف الأحجام -->
                                    <div style="background: {s_bg}; border: 1px solid {s_color}; color: {s_color}; 
                                                padding: 6px 0px; border-radius: 8px; font-weight: 900; font-size: 0.9rem;
                                                min-width: 150px; text-align: center; flex-shrink: 0; box-sizing: border-box;">
                                        {s_text}
                                    </div>
                                    <div style="text-align: right; width: 100%;">
                                        <h3 style="margin: 0; color: #ffffff; font-size: 1.3rem; font-weight: 900;">{dev.get('Appareil', 'جهاز غير معروف')}</h3>
                                        <div style="color: #94a3b8; font-size: 0.9rem; font-family: monospace; margin-top: 1px;">تذكرة رقم: #{dev.get('ID', '0000')}</div>
                                    </div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # --- الأكسباندر الشفاف المدمج بدون فراغات ميتة ---
                        with st.expander("📄 عرض تفاصيل التقرير والمستحقات الفنية"):
                            
                            d_sortie = dev.get("Date_Sortie")
                            panne_text = dev.get('Panne', dev.get('Defaut', 'غير محدد'))
                            
                            st.markdown(f'<div style="background: transparent; padding: 8px 12px; font-family: \'Cairo\', sans-serif; direction: rtl; text-align: right;">', unsafe_allow_html=True)

                            # --- 1. نظام الضمان (النسبة المئوية بخط Orbitron) ---
                            if ("livré" in status_lower or "livre" in status_lower or "payé" in status_lower) and d_sortie and str(d_sortie).strip() not in ["", "---", "None"]:
                                w = get_warranty_stats(d_sortie)
                                if w:
                                    val = float(w.get('percent', 0)) 
                                    is_expired = w.get('is_expired', False)
                                    w_color = "#eab308" if not is_expired else "#64748b"
                                    w_status_txt = "🛡️ الضمان ساري" if not is_expired else "🛑 الضمان انتهى"
                                    
                                    st.markdown(f"""
                                        <div style="margin-bottom: 12px; border: 1px solid {w_color}; padding: 10px; border-radius: 8px; background: {w_color}0A; direction: rtl; text-align: right;">
                                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px; align-items: center; flex-direction: row-reverse;">
                                                <div style="color: {w_color}; font-family: 'Orbitron', sans-serif; font-weight: 900; font-size: 1.35rem; display: inline-block; direction: ltr;">{int(val)}%</div>
                                                <span style="color: {w_color}; font-weight: bold; font-size: 0.95rem;">{w_status_txt}</span>
                                            </div>
                                            <div style="width: 100%; background: #1e293b; border-radius: 10px; height: 8px; overflow: hidden;">
                                                <div style="width: {val}%; background: {w_color}; height: 100%;"></div>
                                            </div>
                                            <div style="display: flex; justify-content: space-between; margin-top: 6px; color: #94a3b8; font-size: 0.85rem; flex-direction: row-reverse;">
                                                <span>⏳ المتبقي: {w.get('days_left')} يوم</span>
                                                <span>📅 الاستلام: {w.get('actual_date')}</span>
                                            </div>
                                        </div>
                                    """, unsafe_allow_html=True)

                            # --- 2. نظام أشرطة التقدم (النسبة المئوية بخط Orbitron) ---
                            elif not any(x in status_lower for x in ["annulé", "annule", "non réparable", "non reparable", "prêt", "pret"]):
                                prog_map = {"en attente": 20, "en cours": 50, "réparable": 80}
                                p_val = prog_map.get(status_lower, 30)
                                st.markdown(f"""
                                    <div style="margin-bottom: 12px;">
                                        <div style="display: flex; justify-content: space-between; direction: rtl; margin-bottom: 4px; align-items: center; flex-direction: row-reverse;">
                                            <div style="color:#3b82f6; font-weight: 900; font-family: 'Orbitron', sans-serif; font-size: 1.35rem; display: inline-block; direction: ltr;">{p_val}%</div>
                                            <span style="color:#cbd5e1; font-size: 0.9rem;">⚙️ تقدم الصيانة:</span>
                                        </div>
                                        <div style="width: 100%; background: #1e293b; border-radius: 10px; height: 8px; overflow: hidden;">
                                            <div style="width: {p_val}%; background: #3b82f6; height: 100%;"></div>
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)

                            # --- 3. جدول البيانات المبسط النظيف والمحاذاة كاملة لليمين ---
                            st.markdown(f"""
                                <table style="width:100%; direction: rtl; text-align: right; border-collapse: collapse; font-size: 0.95rem;">
                                    <tr style="border-bottom: 1px solid #1e293b;">
                                        <td style="padding: 6px 0; color: #94a3b8; font-family: 'Cairo', sans-serif;">📅 تاريخ الدخول:</td>
                                        <td style="text-align: left; color: #f1f5f9; font-family: sans-serif; font-weight: bold;">{dev.get('Date_Entree', '---')}</td>
                                    </tr>
                                    <tr style="border-bottom: 1px solid #1e293b;">
                                        <td style="padding: 6px 0; color: #94a3b8; font-family: 'Cairo', sans-serif;">📅 تاريخ الخروج:</td>
                                        <td style="text-align: left; color: #f1f5f9; font-family: sans-serif; font-weight: bold;">{dev.get('Date_Sortie', '---')}</td>
                                    </tr>
                                    <tr style="border-bottom: 1px solid #1e293b;">
                                        <td style="padding: 6px 0; color: #94a3b8; font-family: 'Cairo', sans-serif;">🛠️ العطل المسجل:</td>
                                        <td style="text-align: left; color: #ef4444; font-weight: bold; font-family: 'Cairo', sans-serif;">{panne_text}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px 0 0 0; color: #facc15; font-weight: bold; font-family: 'Cairo', sans-serif;">💰 المستحقات:</td>
                                        <td style="text-align: left; padding-top: 10px;">{prix_html}</td>
                                    </tr>
                                </table>
                            """, unsafe_allow_html=True)
                            
                            st.markdown('</div>', unsafe_allow_html=True)
# ==============================================================================
# 7. تشغيل بوت التلغرام الاحترافي (المطور لـ InfoDoc)
# ==============================================================================
@st.cache_resource
def start_telegram_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: 
        return "Missing Token"

    try:
        bot = telebot.TeleBot(token, parse_mode="Markdown")

        @bot.message_handler(commands=['start'])
        def handle_start(m):
            try:
                command_parts = m.text.split()
                if len(command_parts) > 1:
                    client_phone = normalize_phone(command_parts[1])
                    ref = db.reference("atelier")
                    data = ref.get()
                    
                    if data:
                        linked_devices = []
                        for k, v in data.items():
                            # المطابقة الذكية لأحدث 9 أرقام لضمان الدقة الكاملة
                            db_phone = normalize_phone(v.get("Telephone", ""))
                            if db_phone.endswith(client_phone[-9:]):
                                ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                                # جمع أسماء الأجهزة المرتبطة لعرضها للزبون في رسالة التأكيد
                                device_name = v.get("Appareil", "جهاز غير معروف")
                                ticket_id = v.get("ID", "0000")
                                linked_devices.append(f"• *{device_name}* (تذكرة #{ticket_id})")
                        
                        if linked_devices:
                            devices_list_str = "\n".join(linked_devices)
                            success_msg = (
                                "🔔 *تفعيل الإشعارات الفورية - InfoDoc*\n\n"
                                "✅ *تم ربط حسابك بنجاح!*\n"
                                "ستصلك إشعارات تلقائية وفورية هنا على التلغرام بمجرد حدوث أي تغيير في حالة أجهزتك (فحص، قيد الصيانة، أو جاهز للتسليم).\n\n"
                                "📦 *الأجهزة المرتبطة حالياً:*\n"
                                f"{devices_list_str}\n\n"
                                "⏱️ _شكراً لثقتكم في خدماتنا._"
                            )
                            bot.reply_to(m, success_msg)
                        else:
                            error_msg = (
                                "❌ *خطأ في عملية الربط*\n\n"
                                "عذراً، لم نجد أي جهاز مسجل برقم الهاتف هذا في قاعدة بيانات الورشة حالياً.\n"
                                "يرجى التأكد من الرقم الذي سجلت به عند تسليم الجهاز."
                            )
                            bot.reply_to(m, error_msg)
                    else:
                        bot.reply_to(m, "⚠️ قاعدة البيانات فارغة حالياً أو غير متصلة.")
                else:
                    # رسالة الترحيب العامة إذا دخل البوت مباشرة بدون رابط التطبيق
                    welcome_msg = (
                        "👋 *مرحباً بك في بوت ورشة InfoDoc الفنية!*\n\n"
                        "هذا البوت مخصص لإرسال إشعارات تلقائية وفورية لزبائننا لتتبع حالة صيانة أجهزتهم (لابتوب / كمبيوتر).\n\n"
                        "ℹ️ *كيفية تفعيل الخدمة:*\n"
                        "1️⃣ اذهب إلى موقعنا الإلكتروني.\n"
                        "2️⃣ ابحث عن أجهزتك باستخدام رقم هاتفك.\n"
                        "3️⃣ اضغط على زر *🚀 تفعيل إشعارات التلغرام* العائم ليربط حسابك تلقائياً."
                    )
                    bot.reply_to(m, welcome_msg)
            except Exception as e:
                print(f"Error in Telegram logic: {e}")

        # تشغيل البوت في خيط (Thread) منفصل لضمان استقرار Streamlit
        thread = threading.Thread(target=bot.infinity_polling, daemon=True)
        thread.start()
        return "Bot Started Successfully"
    except Exception as e:
        return f"Error: {e}"

# تشغيل وتنشيط البوت تلقائياً عند إقلاع التطبيق
if "TELEGRAM_TOKEN" in st.secrets:
    start_telegram_bot()
