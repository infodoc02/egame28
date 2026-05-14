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

# ==============================================================================
# 3. التنسيقات البصرية (CSS) - النسخة النهائية المنظمة
# ==============================================================================
st.markdown("""
    <style>
    /* 1. الستايل العام لكل الأكسباندرز (باش ما يبقاوش كحولة بزاف) */
    div[data-testid="stExpander"] {
        border: 1px solid #30363d !important;
        background: rgba(22, 27, 34, 0.5) !important;
        border-radius: 12px !important;
        margin-bottom: 15px !important;
    }

    /* 2. أنيميشن الإضاءة الصفراء */
    @keyframes blink-yellow { 
        0%, 100% { border-color: #d29922; box-shadow: 0 0 10px #d29922; } 
        50% { border-color: #ffcc00; box-shadow: 0 0 25px #ffcc00; } 
    }

    /* 3. تطبيق الإضاءة فقط على قسم الشروط */
    .terms-section div[data-testid="stExpander"] {
        border: 2px solid #d29922 !important;
        animation: blink-yellow 2s infinite ease-in-out !important;
    }

    /* تلوين عنوان أكسباندر الشروط */
    .terms-section summary {
        color: #ffcc00 !important;
        font-weight: 900 !important;
    }
    
    /* تحسين العناوين للأكسباندرز العادية (الأجهزة) */
    div[data-testid="stExpander"] summary p {
        font-weight: bold;
        color: #c9d1d9 !important;
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
st.markdown('<div class="terms-section">', unsafe_allow_html=True)

with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: 'Cairo'; line-height: 1.8; color: #f0f6fc;">
            1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<b>رفض الزبون ذلك</b>، يتم دفع <b>1000 دج</b> ثمن الجهد والفحص.<br>
            2️⃣ أسعار العمل على <b>البطاقة الأم (Carte Mère)</b> تبدأ من <b>3000 دج</b>.<br>
            3️⃣ <b>الموافقة التلقائية:</b> نصلح مباشرة إذا كان السعر بين 3000 و 4000 دج. فوق ذلك نطلب موافقتك أولاً.
        </div>
    """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ==============================================================================
# 5. نظام البحث والتتبع
# ==============================================================================
st.markdown('<h2 style="text-align:center; color:#58a6ff; font-family:Cairo;">🔍 تتبع أجهزتك الآن</h2>', unsafe_allow_html=True)
user_phone = st.text_input("", placeholder="أدخل رقم هاتفك (مثال: 0798661900)")

if user_phone:
    norm_phone = normalize_phone(user_phone)
    if len(norm_phone) >= 9:
        raw_data = db.reference("atelier").get()
        if raw_data:
            my_devices = [dict(v, _id=k) for k, v in raw_data.items() if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لم نجد أي جهاز مرتبط بهذا الرقم.")
            else:
                # زر التلغرام
                if any(not d.get("Telegram_ID") for d in my_devices):
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                    st.markdown(f'<a href="https://t.me/{bot_user}?start={norm_phone}" class="tg-btn">🚀 ربط الإشعارات الفورية على تليغرام</a>', unsafe_allow_html=True)
                
                my_devices.sort(key=lambda x: (str(x.get("Date_Sortie", "")) != "", x.get("ID", 0)), reverse=True)
                
                for dev in my_devices:
                    status = str(dev.get("Statut", "En Cours"))
                    is_done = "Livré" in status
                    status_color = "#238636" if status == "Prêt" else "#da3633" if status == "Annulé" else "#6e7681" if is_done else "#58a6ff"
                    
                    st.markdown(f"""
                        <div class="device-box" style="border-right: 6px solid {status_color};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div><h3 style="margin:0;">{dev.get('Appareil')}</h3><small>#{dev.get('ID')}</small></div>
                                <span style="background:{status_color}; padding:5px 10px; border-radius:5px; font-size:0.8rem;">{status}</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # هذا الأكسباندر سيكون عادياً (بدون لمعان)
                    with st.expander("📄 التفاصيل والضمان"):
                        if is_done:
                            w = get_warranty_stats(dev.get("Date_Sortie"))
                            if w and not w["is_expired"]:
                                st.success(f"🛡️ الضمان سارٍ: {int(w['days_left'])} يوم")
                                st.progress(w['percent']/100)
                            else: st.error("❌ الضمان منتهٍ")
                        else:
                            st.info("🛠️ حالة الصيانة: " + status)
                        
                        st.write(f"💰 السعر: {dev.get('Prix')} دج")
                        st.write(f"📅 الاستلام: {dev.get('Date_Entree')}")
