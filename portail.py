import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
import pandas as pd # سيستخدم لاحقاً لعرض البيانات
import threading
import telebot

# ==============================================================================
# 1. إعدادات الصفحة الأساسية (Configuration)
# ==============================================================================
st.set_page_config(
    page_title="InfoDoc - Client Portal",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# إضافة CSS مخصص لتحسين المظهر العام
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. الاتصال بقاعدة البيانات (Firebase Connection)
# ==============================================================================
@st.cache_resource
def init_db():
    """ربط التطبيق بـ Firebase مع معالجة الأخطاء."""
    if not firebase_admin._apps:
        try:
            # التأكد من وجود الإعدادات في secrets
            if "firebase" not in st.secrets or "DB_URL" not in st.secrets:
                st.error("⚠️ ملف الإعدادات (secrets.toml) غير مكتمل!")
                return False
                
            cred_dict = dict(st.secrets["firebase"])
            
            # معالجة الرموز الخاصة بالمفتاح السري (مهمة جداً في الاستضافة)
            if "\\n" in cred_dict.get("private_key", ""):
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': st.secrets["DB_URL"]
            })
            return True
        except Exception as e:
            st.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
            return False
    return True

# محاولة الاتصال
db_status = init_db()

# ==============================================================================
# 3. الدوال البرمجية المساعدة (Helper Functions)
# ==============================================================================

def normalize_phone(phone: str) -> str:
    """تنسيق رقم الهاتف الجزائري ليصبح بصيغة 0XXXXXXXXX."""
    if not phone: return ""
    # حذف كل ما هو ليس رقماً
    p = re.sub(r"\D", "", str(phone))
    
    # معالجة المقدمة الدولية
    if p.startswith("213"):
        p = "0" + p[3:]
    elif p.startswith("00213"):
        p = "0" + p[5:]
    
    # التأكد من أن الرقم يبدأ بـ 0 وطوله 10
    if len(p) == 9 and p[0] in ["5", "6", "7"]:
        p = "0" + p
        
    return p

def get_warranty_stats(date_sortie_str):
    """
    حساب وضع الضمان.
    الصيغة الرياضية المتبعة:
    $$\text{percent} = \left( \frac{\text{remaining\_days}}{30} \right) \times 100$$
    """
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None"]:
        return None
    
    # قائمة الصيغ المحتملة للتواريخ
    date_formats = [
        "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", 
        "%Y-%m-%d", "%d-%m-%Y", 
        "%d/%m/%Y", "%d/%m/%Y %H:%M"
    ]
    
    now = datetime.now()
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

# ==============================================================================
# 3. التنسيقات البصرية (CSS) - النسخة النهائية المنظمة
# ==============================================================================
st.markdown("""
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    .stApp { background: #0d1117; color: white; font-family: 'Cairo', sans-serif; }
    
    /* الحاوية الرئيسية */
    .hero-container {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #30363d; border-radius: 15px; padding: 25px;
        margin-bottom: 20px; text-align: center;
    }

    .main-title {
        font-family: 'Orbitron', sans-serif; color: #58a6ff;
        font-size: clamp(2rem, 8vw, 3.5rem); font-weight: 900;
        text-shadow: 0 0 15px rgba(88, 166, 255, 0.5); margin-bottom: 5px;
    }

    /* أزرار التواصل - النسخة المعدلة والمضمونة */
    .custom-btn {
        display: flex !important;
        flex-direction: column !important; /* تجعل الأيقونة فوق النص */
        align-items: center !important;
        justify-content: center !important;
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 15px !important;
        padding: 15px !important;
        text-decoration: none !important;
        color: white !important;
        transition: 0.3s !important;
        min-height: 110px !important;
        width: 100% !important;
        margin-bottom: 10px !important;
    }

    .custom-btn:hover {
        border-color: #58a6ff !important;
        background: rgba(88, 166, 255, 0.15) !important;
        transform: translateY(-5px) !important;
    }

    /* تنسيق الأيقونات داخل الأزرار رغما عن المتصفح */
    .custom-btn i {
        font-size: 2.2rem !important; /* تكبير الأيقونة */
        margin-bottom: 10px !important; /* مسافة واضحة تحت الأيقونة */
        display: block !important;
    }

    .custom-btn b {
        font-size: 0.9rem !important;
        font-weight: 700 !important;
        display: block !important;
    }

    /* 1. الستايل العام لكل الأكسباندرز (باش ما يبقاوش كحولة بزاف) */
    div[data-testid="stExpander"] {
        border: 1px solid #30363d !important;
        background: rgba(22, 27, 34, 0.5) !important;
        border-radius: 12px !important;
        margin-bottom: 15px !important;
    }

    /* أنيميشن الإضاءة */
    @keyframes yellow-glow {
        0%, 100% { border-color: #d29922; box-shadow: 0 0 5px #d29922; }
        50% { border-color: #ffcc00; box-shadow: 0 0 20px #ffcc00; }
    }

    /* استهداف الأكسباندر الأول فقط في الصفحة (اللي هو تاع الشروط) */
    /* أو استهداف الأكسباندر اللي يحتوي على نص معين */
    div[data-testid="stExpander"]:first-of-type {
        border: 2px solid #d29922 !important;
        animation: yellow-glow 3s infinite ease-in-out !important;
        background: rgba(210, 153, 34, 0.05) !important;
        direction: rtl !important; /* لضمان الاتجاه من اليمين */
    }

    /* تنسيق العنوان (اضغط هنا...) */
    div[data-testid="stExpander"]:first-of-type summary {
        direction: rtl !important;
        text-align: right !important;
        display: flex !important;
        flex-direction: row !important; /* ترتيب العناصر داخله */
        justify-content: flex-start !important;
        gap: 15px !important;
    }

    div[data-testid="stExpander"]:first-of-type summary p {
        font-family: 'Cairo', sans-serif !important;
        font-weight: 900 !important;
        color: #ffcc00 !important;
        font-size: 1.1rem !important;
        margin: 0 !important;
    }
    
    /* إذا حبيت تنحي السهم كامل وتقلبو جهة اليسار */
    div[data-testid="stExpander"] summary {
        flex-direction: row-reverse;
        justify-content: space-between;
    }
    </style>
""", unsafe_allow_html=True)
# ==============================================================================
# 5. واجهة المستخدم الرأسية (Header Section)
# ==============================================================================

# الترحيب والوقت
now = datetime.now()
if 5 <= now.hour < 12:
    greeting = "صباح الخير"
elif 12 <= now.hour < 18:
    greeting = "طاب يومك"
else:
    greeting = "مساء الخير"

# جلب حالة المحل من Firebase مع معالجة حالة عدم الاتصال
try:
    # أضفت .get() مع التحقق من القيمة
    shop_ref = db.reference("shop_settings/is_open").get()
    shop_status = True if shop_ref is True else False
except Exception:
    shop_status = True # افتراضياً مفتوح إذا فشل الاتصال

# 4. واجهة الهيدر
st.markdown(f'''
    <div class="hero-container">
        <div style="color: #8b949e; font-size: 0.9rem;">{greeting} | {now.strftime("%Y-%m-%d %H:%M")}</div>
        <div class="main-title">INFODOC</div>
        <div class="sub-title" style="color: #8b949e; margin-bottom: 20px;">Vente & Réparation Informatique</div>
        <span class="status-badge {'status-open' if shop_status else 'status-closed'}">
            {'● OPEN - مـفـتـوح' if shop_status else '● CLOSED - مـغـلـق'}
        </span>
    </div>
''', unsafe_allow_html=True)

# 2. أزرار التواصل السريع (Quick Actions)
# أزرار التواصل السريع (Quick Actions)
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown('''
        <a href="tel:0798661900" class="custom-btn">
            <i class="fas fa-phone-alt" style="color: #3fb950;"></i>
            <span style="font-size: 0.9rem;">اتصل بنا</span>
        </a>
    ''', unsafe_allow_html=True)

with col2:
    st.markdown('''
        <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="custom-btn">
            <i class="fas fa-map-marker-alt" style="color: #f85149;"></i>
            <span style="font-size: 0.9rem;">موقعنا</span>
        </a>
    ''', unsafe_allow_html=True)

with col3:
    st.markdown('''
        <a href="https://www.facebook.com/100095433977319/" target="_blank" class="custom-btn">
            <i class="fab fa-facebook-f" style="color: #1877f2;"></i>
            <span style="font-size: 0.9rem;">فيسبوك</span>
        </a>
    ''', unsafe_allow_html=True)

with col4:
    st.markdown('''
        <a href="https://www.tiktok.com/@infodoc02" target="_blank" class="custom-btn">
            <i class="fab fa-tiktok" style="color: #ffffff;"></i>
            <span style="font-size: 0.9rem;">تيك توك</span>
        </a>
    ''', unsafe_allow_html=True)

st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)

# 3. صندوق ملاحظات الصيانة (Maintenance Policy)
with st.expander("⚠️ ملاحظات وشروط الصيانة الهامة (يرجى القراءة)"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: 'Cairo'; line-height: 2; padding: 10px; color: #e6edf3;">
            <div style="border-right: 3px solid #d29922; padding-right: 15px;">
                <p>✅ <b>الفحص والتشخيص:</b> إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<b>رفض الزبون ذلك</b>، يتم دفع <b>1000 دج</b> مقابل جهد التقني.</p>
                <p>⚙️ <b>البطاقة الأم:</b> أسعار صيانة البطاقة الأم (Carte Mère) تبدأ من <b>3000 دج</b> حسب نوع العطل.</p>
                <p>⚡ <b>الموافقة التلقائية:</b> نقوم بالتصليح مباشرة إذا كانت التكلفة بين <b>3000 و 4000 دج</b>. ما فوق ذلك، نتصل بك لأخذ الموافقة.</p>
                <p>🔔 <b>التنبيهات:</b> نوصي بشدة بربط حسابك بـ <b>Telegram</b> لتلقي إشعار فوري عند انتهاء الصيانة.</p>
            </div>
        </div>
    """, unsafe_allow_html=True)
# ==============================================================================
# 6. نظام البحث وتتبع الأجهزة (Tracking System)
# ==============================================================================

st.markdown("""
    <div style="text-align: center; margin-top: 30px; margin-bottom: 10px;">
        <h2 style="font-family: 'Cairo', sans-serif; color: #58a6ff; font-weight: 900;">
            <i class="fas fa-search"></i> تتبع أجهزتك الآن
        </h2>
        <p style="color: #8b949e;">أدخل رقم هاتفك المسجل لدينا لمتابعة حالة الصيانة</p>
    </div>
""", unsafe_allow_html=True)

# استخدام st.form لمنع البحث المتكرر مع كل حرف
with st.form("search_form", clear_on_submit=False):
    user_phone = st.text_input("", placeholder="0XXXXXXXXX", label_visibility="collapsed")
    submit_search = st.form_submit_button("🔍 ابحث عن أجهزتي")

if submit_search and user_phone:
    norm_phone = normalize_phone(user_phone)
    if len(norm_phone) < 9:
        st.error("⚠️ يرجى إدخال رقم هاتف صحيح")
    else:
        with st.spinner("⏳ جاري جلب بيانات أجهزتك..."):
            db_ref = db.reference("atelier")
            raw_data = db_ref.get()
            
            if raw_data:
                # تصفية ذكية للأجهزة المرتبطة بالرقم (آخر 9 أرقام لضمان الدقة)
                my_devices = [
                    dict(v, _id=k) for k, v in raw_data.items() 
                    if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])
                ]
                
                if not my_devices:
                    st.warning("⚠️ لم نجد أي جهاز مرتبط بهذا الرقم في قاعدة بياناتنا.")
                else:
                    # 1. خيار ربط التلغرام (يظهر مرة واحدة في الأعلى)
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                    st.markdown(f'''
                        <div style="background: rgba(34, 158, 217, 0.1); padding: 15px; border-radius: 12px; border: 1px solid #229ED9; margin-bottom: 20px;">
                            <p style="margin-bottom:10px; text-align:center;">🚀 احصل على إشعارات فورية عند جاهزية جهازك!</p>
                            <a href="https://t.me/{bot_user}?start={norm_phone}" target="_blank" class="tg-btn">
                                <i class="fab fa-telegram-plane"></i> تفعيل إشعارات تليغرام
                            </a>
                        </div>
                    ''', unsafe_allow_html=True)
                    
                    # 2. عرض الأجهزة (الجديد أولاً)
                    my_devices.sort(key=lambda x: str(x.get("ID", "0")), reverse=True)
                    
                    for dev in my_devices:
                        status = str(dev.get("Statut", "En Cours"))
                        is_done = "Livré" in status or "Prêt" in status
                        
                        # تحديد اللون بناءً على الحالة
                        status_map = {
                            "Prêt": "#238636",      # أخضر
                            "Annulé": "#da3633",    # أحمر
                            "En Cours": "#58a6ff",  # أزرق
                            "Livré": "#6e7681"      # رمادي
                        }
                        color = status_map.get(status, "#58a6ff")
                        
                        # تصميم بطاقة الجهاز
                        st.markdown(f"""
                            <div class="device-box" style="border-right: 6px solid {color};">
                                <div style="display: flex; justify-content: space-between; align-items: center;">
                                    <div>
                                        <h3 style="margin:0; color:white; font-family:'Cairo';">{dev.get('Appareil', 'جهاز غير معروف')}</h3>
                                        <code style="color:#8b949e;">ID: #{dev.get('ID', '000')}</code>
                                    </div>
                                    <span class="badge-label" style="background:{color}; color:white; border:none;">
                                        {status}
                                    </span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        with st.expander("🔍 تفاصيل الصيانة والضمان"):
                            # حساب الضمان باستخدام الدالة التي طورناها في الجزء الأول
                            if "Livré" in status:
                                w = get_warranty_stats(dev.get("Date_Sortie"))
                                if w:
                                    if not w["is_expired"]:
                                        st.success(f"🛡️ الضمان سارٍ: متبقي {w['days_left']} يوم (ينتهي في {w['actual_date']})")
                                        st.progress(w['percent']/100)
                                    else:
                                        st.error(f"❌ انتهى الضمان في تاريخ {w['actual_date']}")
                            
                            # تفاصيل مالية
                            c1, c2 = st.columns(2)
                            c1.metric("تاريخ الاستلام", dev.get('Date_Entree', '---'))
                            c2.metric("التكلفة الإجمالية", f"{dev.get('Prix', '0')} دج")
                            
                            if dev.get('Panne'):
                                st.info(f"📝 وصف العطل: {dev.get('Panne')}")

# ==============================================================================
# 7. تشغيل بوت التلغرام (المصحح)
# ==============================================================================
@st.cache_resource
def start_telegram_bot():
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return "Missing Token"

    try:
        bot = telebot.TeleBot(token)

        @bot.message_handler(commands=['start'])
        def handle_start(m):
            try:
                command_parts = m.text.split()
                if len(command_parts) > 1:
                    client_phone = normalize_phone(command_parts[1])
                    ref = db.reference("atelier")
                    data = ref.get()
                    if data:
                        linked = False
                        for k, v in data.items():
                            # تصفية ذكية: التأكد من مطابقة آخر 9 أرقام
                            db_phone = normalize_phone(v.get("Telephone", ""))
                            if db_phone.endswith(client_phone[-9:]):
                                ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                                linked = True
                        
                        if linked:
                            bot.reply_to(m, "✅ تم ربط حسابك بنجاح! ستصلك إشعارات فورية هنا عند جاهزية أجهزتك.")
                        else:
                            bot.reply_to(m, "❌ عذراً، لم نجد أي جهاز مسجل بهذا الرقم في نظامنا.")
                else:
                    bot.reply_to(m, "مرحباً بك في InfoDoc! يرجى الدخول عبر الرابط المرسل لك لتفعيل الإشعارات.")
            except Exception as e:
                print(f"Error logic: {e}")

        # تشغيل البوت في خيط منفصل
        thread = threading.Thread(target=bot.infinity_polling, daemon=True)
        thread.start()
        return "Bot Started"
    except Exception as e:
        return f"Error: {e}"

# تشغيل البوت
if "TELEGRAM_TOKEN" in st.secrets:
    start_telegram_bot()
