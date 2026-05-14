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
# 1. إعدادات الصفحة والاتصال (Config & DB)
# ==============================================================================
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
        except Exception as e:
            st.error(f"خطأ في الاتصال: {e}")
            return False
    return True

init_db()

# ==============================================================================
# 2. الدوال المساعدة
# ==============================================================================
def normalize_phone(phone: str) -> str:
    p = re.sub(r"\D", "", str(phone or ""))
    if p.startswith("213"): p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]: p = "0" + p
    return p

def get_warranty_stats(date_sortie_str):
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None"]: return None
    date_formats = ["%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d/%m/%Y %H:%M"]
    for fmt in date_formats:
        try:
            date_s = datetime.strptime(str(date_sortie_str).strip(), fmt)
            diff_days = (datetime.now() - date_s).days
            remaining_days = max(30 - diff_days, 0)
            return {"percent": (remaining_days / 30) * 100, "is_expired": diff_days > 30, "days_left": remaining_days}
        except: continue
    return None

# 1. دالة تحديد الأولوية (حطها الفوق مع الدوال المساعدة أو مباشرة قبل الفرز)
def get_status_priority(status):
    s = str(status).strip()
    if s == "Prêt": return 1
    elif s == "Annulé": return 2
    elif s == "Non Réparable": return 3
    elif s == "Réparable": return 4
    elif s == "En Cours": return 5
    elif s == "En Attente": return 6
    elif "Livré" in s: return 7  # يجمع Livré & Payé و Livré (Dette)
    else: return 99  # أي حالة غير معروفة تجي مع اللخر

# ==============================================================================
# 3. التنسيقات البصرية (CSS) - النسخة النهائية المنظمة
# ==============================================================================
st.markdown("""
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

    /* أزرار التواصل */
    .custom-btn {
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px; padding: 15px; text-decoration: none !important; color: white !important;
        transition: 0.3s; min-height: 100px; margin-bottom: 10px;
    }
    .custom-btn:hover { border-color: #58a6ff; background: rgba(88, 166, 255, 0.15); transform: translateY(-3px); }

    /* أنيميشن الحالة */
    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; } 50% { opacity: 0.7; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; } 50% { opacity: 0.7; } }
    
    .status-badge { padding: 8px 20px; border-radius: 10px; font-weight: bold; display: inline-block; font-family: 'Cairo'; }
    .status-open { color: #3fb950; border: 2px solid #3fb950; animation: blink-green 2s infinite; }
    .status-closed { color: #f85149; border: 2px solid #f85149; animation: blink-red 2s infinite; }


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
# 4. واجهة المستخدم (UI)
# ==============================================================================

# الهيدر
now = datetime.now()
greeting = "صباح الخير" if 5 <= now.hour < 12 else "مساء الخير"
try: shop_status = db.reference("shop_settings/is_open").get()
except: shop_status = True

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

# أزرار التواصل
c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown('<a href="tel:0798661900" class="custom-btn"><span>📞</span><b>اتصل بنا</b></a>', unsafe_allow_html=True)
with c2: st.markdown('<a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" class="custom-btn"><span>📍</span><b>موقعنا</b></a>', unsafe_allow_html=True)
with c3: st.markdown('<a href="https://fb.com/..." target="_blank" class="custom-btn"><span>📘</span><b>فيسبوك</b></a>', unsafe_allow_html=True)
with c4: st.markdown('<a href="https://tiktok.com/..." target="_blank" class="custom-btn"><span>📱</span><b>تيك توك</b></a>', unsafe_allow_html=True)

# قسم الشروط (المضيء فقط)

with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: 'Cairo'; line-height: 1.8; color: #f0f6fc;">
            1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<b>رفض الزبون ذلك</b>، يتم دفع <b>1000 دج</b> ثمن الجهد والفحص.<br>
            2️⃣ أسعار العمل على <b>البطاقة الأم (Carte Mère)</b> تبدأ من <b>3000 دج</b>.<br>
            3️⃣ <b>الموافقة التلقائية:</b> نصلح مباشرة إذا كان السعر بين 3000 و 4000 دج. فوق ذلك نطلب موافقتك أولاً.
        </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 5. نظام البحث والتتبع (بتصميم البطاقات الاحترافية)
# ==============================================================================

# --- 1. CSS خاص بهذا القسم (لزر التلغرام العائم والبطاقات المدمجة) ---
st.markdown("""
    <style>
    /* زر التلغرام العائم */
    .floating-tg-btn {
        position: fixed;
        bottom: 30px;
        left: 30px; /* تقدر تبدلها right: 30px إذا حبيت */
        background: linear-gradient(135deg, #229ED9, #1c7cb3);
        color: white !important;
        padding: 15px 25px;
        border-radius: 50px;
        box-shadow: 0 10px 20px rgba(34, 158, 217, 0.4);
        z-index: 9999;
        font-family: 'Cairo', sans-serif;
        font-weight: 900;
        font-size: 1.1rem;
        text-decoration: none;
        display: flex;
        align-items: center;
        gap: 10px;
        animation: float-pulse 2s infinite ease-in-out;
        border: 1px solid rgba(255,255,255,0.2);
    }
    
    .floating-tg-btn:hover {
        transform: translateY(-5px) scale(1.05);
        box-shadow: 0 15px 30px rgba(34, 158, 217, 0.6);
    }

    @keyframes float-pulse {
        0% { transform: translateY(0); }
        50% { transform: translateY(-8px); box-shadow: 0 15px 25px rgba(34, 158, 217, 0.5); }
        100% { transform: translateY(0); }
    }

    /* رأس البطاقة (المربع الخاص بالجهاز) */
    .device-header {
        background: #161b22;
        border: 1px solid #30363d;
        border-bottom: none; /* نحيو الخط التحتاني باش يلصق مع الأكسباندر */
        border-radius: 12px 12px 0 0; /* تقويس من الفوق فقط */
        padding: 20px;
        margin-top: 30px; /* مسافة بين كل جهاز والآخر */
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 -5px 15px rgba(0,0,0,0.2);
    }

    .device-title { margin: 0; color: #ffffff; font-family: 'Orbitron', 'Cairo'; font-size: 1.4rem; font-weight: bold; }
    .device-id { color: #8b949e; font-size: 0.9rem; font-family: 'Courier New', monospace; }
    
    .status-badge-mini {
        padding: 6px 15px;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 900;
        font-family: 'Orbitron', 'Cairo';
        color: white;
        text-transform: uppercase;
        box-shadow: inset 0 0 10px rgba(255,255,255,0.1);
    }

    /* تعديل الأكسباندر ليلتصق بالبطاقة */
    div[data-testid="stExpander"] {
        background: #0d1117 !important;
        border: 1px solid #30363d !important;
        border-top: 1px dashed #30363d !important; /* خط متقطع يفصل بين العنوان والتفاصيل */
        border-radius: 0 0 12px 12px !important; /* تقويس من التحت فقط */
        box-shadow: 0 10px 15px rgba(0,0,0,0.3) !important;
        margin-bottom: 0px !important;
    }
    
    /* جدول التفاصيل الداخلية */
    .details-table { width: 100%; border-collapse: collapse; margin-top: 10px; background: #161b22; border-radius: 8px; overflow: hidden; }
    .details-table td { padding: 12px; border-bottom: 1px solid #30363d; text-align: center; color: #c9d1d9; }
    .details-table td:first-child { border-left: 1px solid #30363d; font-weight: bold; color: #8b949e; text-align: right; width: 40%; }
    </style>
""", unsafe_allow_html=True)

# --- 2. واجهة البحث ---
st.markdown('<h2 style="text-align:center; color:#58a6ff; font-family:Cairo; font-weight: 900; margin-top: 40px; text-shadow: 0 0 20px rgba(88,166,255,0.3);">🔍 تتبع أجهزتك الآن</h2>', unsafe_allow_html=True)

user_phone = st.text_input("", placeholder="📱 أدخل رقم هاتفك هنا (مثال: 0798661900)")

if user_phone:
    norm_phone = normalize_phone(user_phone)
    if len(norm_phone) >= 9:
        raw_data = db.reference("atelier").get()
        if raw_data:
            # فلترة الأجهزة
            my_devices = [dict(v, _id=k) for k, v in raw_data.items() if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])]
            prix_display = f"{my_devices.get('Prix')} دج" if dev.get('Prix') else "قيد التقييم"
            if not my_devices:
                st.error("⚠️ عذراً، لم نجد أي جهاز مرتبط بهذا الرقم في نظامنا.")
            else:
                # عرض زر التلغرام العائم إذا كان هناك جهاز غير مربوط
                if any(not d.get("Telegram_ID") for d in my_devices):
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                    st.markdown(f'''
                        <a href="https://t.me/{bot_user}?start={norm_phone}" target="_blank" class="floating-tg-btn">
                            🚀 تفعيل إشعارات التلغرام
                        </a>
                    ''', unsafe_allow_html=True)
                
                # ترتيب الأجهزة (التي قيد الصيانة أولاً)
                my_devices.sort(
                    key=lambda x: (
                        get_status_priority(x.get("Statut", "En Cours")), 
                        -int(x.get("ID", 0)) if str(x.get("ID", 0)).isdigit() else 0
                    )
                )
                
                # عرض الأجهزة
                for dev in my_devices:
                    status = str(dev.get("Statut", "En Cours"))
                    is_done = "Livré" in status
                    # تحديد الألوان بناءً على الحالة
                    status_color = "#238636" if status == "Prêt" else "#da3633" if status == "Annulé" else "#6e7681" if is_done else "#58a6ff"
                    border_color = status_color
                    
                    # 1. رأس البطاقة (مع الخط الجانبي الملون)
                    st.markdown(f"""
                        <div class="device-header" style="border-right: 6px solid {border_color};">
                            <div>
                                <h3 class="device-title">{dev.get('Appareil')}</h3>
                                <div class="device-id">Ticket #{dev.get('ID')}</div>
                            </div>
                            <div class="status-badge-mini" style="background-color: {status_color};">
                                {status}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 2. الأكسباندر (سيلتصق بالرأس ليبدو كبطاقة واحدة)
                    with st.expander("📄 عرض التفاصيل والمستحقات"):
                        
                        # شريط الحالة والضمان
                        if is_done:
                            w = get_warranty_stats(dev.get("Date_Sortie"))
                            if w and not w["is_expired"]:
                                st.success(f"🛡️ **الضمان سارٍ:** متبقي {int(w['days_left'])} يوم")
                                st.progress(w['percent']/100)
                            else:
                                st.error("❌ **فترة الضمان منتهية**")
                        else:
                            st.info(f"🛠️ **حالة الصيانة الحالية:** {status}")
                            # شريط تقدم وهمي بناء على الحالة
                            progress_val = 0.3 if status == "En Cours" else 0.7 if status == "Réparable" else 1.0
                            st.progress(progress_val)
                        
                        # جدول التفاصيل الاحترافي
                        st.markdown(f"""
                            <table class="details-table">
                                <tr>
                                    <td>📅 تاريخ الاستلام</td>
                                    <td>{dev.get('Date_Entree', '---')}</td>
                                </tr>
                                <tr>
                                    <td>📅 تاريخ التسليم</td>
                                    <td>{dev.get('Date_Sortie', '---')}</td>
                                </tr>
                                <tr>
                                    <td>💰 التكلفة الإجمالية</td>
                                    <td style="color: #58a6ff; font-weight: 900; font-size: 1.2rem;">
                                        {dev.get('Prix', '0')} د.ج
                                    </td>
                                </tr>
                            </table>
                        """, unsafe_allow_html=True)
