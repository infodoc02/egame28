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
import requests
import hashlib
import uuid
from collections import defaultdict

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
# 3. نظام تتبع الزوار (Visitor Tracking System)
# ==============================================================================

def get_client_ip():
    """الحصول على IP الزائر من طلب HTTP."""
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=3)
        if response.status_code == 200:
            return response.json()['ip']
    except:
        pass
    return "UNKNOWN"

def hash_ip(ip: str) -> str:
    """تشفير IP للحفاظ على الخصوصية."""
    return hashlib.sha256(ip.encode()).hexdigest()[:16]

def track_visitor():
    """تسجيل زيارة الزائر في Firebase."""
    try:
        ip_address = get_client_ip()
        ip_hash = hash_ip(ip_address)
        
        algeria_tz = pytz.timezone('Africa/Algiers')
        visit_time = datetime.now(algeria_tz).isoformat()
        
        visit_data = {
            "ip_hash": ip_hash,
            "timestamp": visit_time,
            "session_id": st.session_state.get("session_id", "UNKNOWN")
        }
        
        ref = db.reference("visitors")
        ref.push(visit_data)
        return True
    except Exception as e:
        print(f"❌ خطأ في تسجيل الزيارة: {e}")
        return False

def get_visitor_stats():
    """جلب إحصائيات الزوار من Firebase."""
    try:
        ref = db.reference("visitors")
        visitors = ref.get()
        
        if not visitors:
            return {
                "total_visits": 0,
                "unique_ips": 0,
                "today_visits": 0,
                "visits_by_hour": {},
                "recent_visits": []
            }
        
        total_visits = len(visitors)
        unique_ips = len(set(v.get("ip_hash") for v in visitors.values() if v))
        
        algeria_tz = pytz.timezone('Africa/Algiers')
        today = datetime.now(algeria_tz).date()
        today_visits = 0
        visits_by_hour = defaultdict(int)
        
        for visit in visitors.values():
            if visit:
                try:
                    visit_dt = datetime.fromisoformat(visit.get("timestamp", ""))
                    if visit_dt.date() == today:
                        today_visits += 1
                        visits_by_hour[visit_dt.hour] += 1
                except:
                    pass
        
        recent = sorted(
            [v for v in visitors.values() if v],
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:10]
        
        return {
            "total_visits": total_visits,
            "unique_ips": unique_ips,
            "today_visits": today_visits,
            "visits_by_hour": dict(visits_by_hour),
            "recent_visits": recent
        }
    except Exception as e:
        print(f"❌ خطأ في جلب الإحصائيات: {e}")
        return None

def init_visitor_tracking():
    """تهيئة نظام تتبع الزوار."""
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
    
    track_visitor()

# تهيئة النظام
init_visitor_tracking()

# ==============================================================================
# 4. الدوال البرمجية المساعدة (Helper Functions)
# ==============================================================================

def normalize_phone(phone: str) -> str:
    """تنسيق رقم الهاتف الجزائري ليصبح بصيغة 0XXXXXXXXX."""
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
    """
    حساب وضع الضمان.
    الصيغة الرياضية المتبعة:
    $$\text{percent} = \left( \frac{\text{remaining\_days}}{30} \right) \times 100$$
    """
    if not date_sortie_str or str(date_sortie_str).strip() in ["", "---", "None"]:
        return None
    
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

def get_status_priority(status):
    """دالة تحديد الأولوية (Livré يجب أن يكون في الآخر)"""
    s = str(status).strip()
    if s == "Prêt": return 1
    elif s == "Annulé": return 2
    elif s == "Non Réparable": return 3
    elif s == "Réparable": return 4
    elif s == "En Cours": return 5
    elif s == "En Attente": return 6
    elif "Livré" in s: return 99  # الأخير
    else: return 98

# ==============================================================================
# 5. التنسيقات البصرية (CSS)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    .stApp { background: #0d1117; color: white; font-family: 'Cairo', sans-serif; }
    
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

    .custom-btn {
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px; padding: 15px; text-decoration: none !important; color: white !important;
        transition: 0.3s; min-height: 100px; margin-bottom: 10px;
    }
    .custom-btn:hover { border-color: #58a6ff; background: rgba(88, 166, 255, 0.15); transform: translateY(-3px); }

    @keyframes blink-green { 0%, 100% { box-shadow: 0 0 15px #3fb950; } 50% { opacity: 0.7; } }
    @keyframes blink-red { 0%, 100% { box-shadow: 0 0 15px #f85149; } 50% { opacity: 0.7; } }
    
    .status-badge { padding: 8px 20px; border-radius: 10px; font-weight: bold; display: inline-block; font-family: 'Cairo'; }
    .status-open { color: #3fb950; border: 2px solid #3fb950; animation: blink-green 2s infinite; }
    .status-closed { color: #f85149; border: 2px solid #f85149; animation: blink-red 2s infinite; }

    div[data-testid="stExpander"] {
        border: 1px solid #30363d !important;
        background: rgba(22, 27, 34, 0.5) !important;
        border-radius: 12px !important;
        margin-bottom: 15px !important;
    }

    @keyframes yellow-glow {
        0%, 100% { border-color: #d29922; box-shadow: 0 0 5px #d29922; }
        50% { border-color: #ffcc00; box-shadow: 0 0 20px #ffcc00; }
    }

    div[data-testid="stExpander"]:first-of-type {
        border: 2px solid #d29922 !important;
        animation: yellow-glow 3s infinite ease-in-out !important;
        background: rgba(210, 153, 34, 0.05) !important;
        direction: rtl !important;
    }
    
    input[aria-label=""] {
        color: white !important;
        background-color: #1c2128 !important;
        border: 1px solid #444c56 !important;
    }
    
    button[kind="primaryFormSubmit"] {
        background-color: #58a6ff !important;
        color: white !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: bold !important;
        height: 3rem !important;
        transition: 0.3s background-color !important;
    }

    button[kind="primaryFormSubmit"]:hover {
        background-color: #1f6feb !important;
        box-shadow: 0 0 10px rgba(88, 166, 255, 0.5) !important;
    }

    div[data-testid="stForm"] {
        border: none !important;
        padding: 0 !important;
    }

    div[data-testid="stExpander"]:first-of-type summary {
        direction: rtl !important;
        text-align: right !important;
        display: flex !important;
        flex-direction: row !important;
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
    
    div[data-testid="stExpander"] summary {
        flex-direction: row-reverse;
        justify-content: space-between;
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 6. واجهة المستخدم (UI)
# ==============================================================================

algeria_tz = pytz.timezone('Africa/Algiers')
now = datetime.now(algeria_tz)
greeting = "عزيزي الزبون صباح الخير" if 5 <= now.hour < 12 else "عزيزي الزبون مساء الخير"

try:
    shop_status = db.reference("shop_settings/is_open").get()
    if shop_status is None:
        shop_status = False
except Exception as e:
    shop_status = False

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

st.markdown("""
    <style>
    .custom-btn {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        background: #21262d;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 12px 5px;
        text-decoration: none !important;
        color: #adbac7 !important;
        transition: 0.3s all ease;
        height: 80px;
    }
    .custom-btn:hover {
        background: #30363d;
        border-color: #58a6ff;
        transform: translateY(-3px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        color: #58a6ff !important;
    }
    .custom-btn span { font-size: 1.5rem; margin-bottom: 5px; }
    .custom-btn b { font-family: 'Cairo'; font-size: 0.8rem; }
    </style>
""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)

with c1: 
    st.markdown('<a href="tel:0798661900" class="custom-btn"><span>📞</span><b>اتصل بنا</b></a>', unsafe_allow_html=True)

with c2: 
    st.markdown('<a href="https://maps.app.goo.gl/RBGLbVDiCeqAdxVT8" target="_blank" class="custom-btn"><span>📍</span><b>موقعنا</b></a>', unsafe_allow_html=True)

with c3: 
    st.markdown('<a href="https://www.facebook.com/share/18dX9h9otd/" target="_blank" class="custom-btn"><span>📘</span><b>فيسبوك</b></a>', unsafe_allow_html=True)

with c4: 
    st.markdown('<a href="https://tiktok.com/@infodoc02/" target="_blank" class="custom-btn"><span>📱</span><b>تيك توك</b></a>', unsafe_allow_html=True)

with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.write("1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح ورفض الزبون ذلك، يتم دفع **1000 دج** ثمن الجهد والفحص.")
    st.write("2️⃣ أسعار العمل على **البطاقة الأم (Carte Mère)** تبدأ من **3000 دج**.")
    st.write("3️⃣ أسعار **تفليش وفتح البيوس (Flash BIOS)** تبدأ من **1500 دج** حسب نوع الجهاز وجيله.")
    st.write("4️⃣ **الموافقة التلقائية:** نصلح مباشرة إذا كان السعر بين 3000 و 4000 دج. فوق ذلك نطلب موافقتك أولاً.")
    st.write("5️⃣ **سياسة الضمان:** الضمان صالح **فقط** على العنصر الذي تم إصلاحه، وأي خلل يمس عنصراً آخر غير مشمول.")
    st.write("6️⃣ **تنبيهات تلقائية:** ننصحك بتحميل تطبيق **Telegram** وتفعيل الإشعارات من خلال الزر الأزرق العائم.")

# ==============================================================================
# 7. نظام البحث والتتبع
# ==============================================================================

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Changa:wght@400;700&family=Orbitron:wght@400;700&display=swap');

    * {
        font-family: 'Cairo', sans-serif !important;
    }

    .floating-tg-btn {
        position: fixed;
        bottom: 30px;
        left: 30px;
        background: #0088cc;
        color: white !important;
        padding: 14px 28px;
        border-radius: 50px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.4);
        z-index: 9999;
        font-family: 'Cairo', sans-serif !important;
        font-weight: 900 !important;
        font-size: 1.1rem;
        text-decoration: none;
        display: flex;
        align-items: center;
        gap: 12px;
        border: 2px solid rgba(255,255,255,0.1);
    }

    .details-table { width: 100%; border-collapse: collapse; margin-top: 10px; background: #161b22; border-radius: 8px; overflow: hidden; }
    .details-table td { padding: 12px; border-bottom: 1px solid #30363d; text-align: center; color: #c9d1d9; }
    .details-table td:first-child { border-left: 1px solid #30363d; font-weight: bold; color: #8b949e; text-align: right; width: 40%; }

    .details-table td { 
        padding: 15px !important; 
        color: #f0f6fc !important; 
        font-size: 1rem !important;
        font-family: 'Cairo', sans-serif !important;
    }
    
    .details-table td:first-child { 
        font-weight: 700 !important; 
        color: #8b949e !important; 
        background: rgba(255,255,255,0.03);
    }

    p, span, label {
        font-family: 'Cairo', sans-serif !important;
        font-weight: 600;
    }
    </style>
""", unsafe_allow_html=True)

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
                my_devices = [
                    dict(v, _id=k) for k, v in raw_data.items() 
                    if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])
                ]
                
                if not my_devices:
                    st.warning("⚠️ لم نجد أي جهاز مرتبط بهذا الرقم في قاعدة بياناتنا.")
                else:
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                    st.markdown(f'''
                        <a href="https://t.me/{bot_user}?start={norm_phone}" target="_blank" class="floating-tg-btn">
                            🚀 تفعيل إشعارات التلغرام
                        </a>
                    ''', unsafe_allow_html=True)
                
                    my_devices.sort(
                        key=lambda x: (
                            get_status_priority(x.get("Statut", "En Cours")), 
                            -int(x.get("ID", 0)) if str(x.get("ID", 0)).isdigit() else 0
                        )
                    )
                    
                    for dev in my_devices:
                        status = str(dev.get("Statut", "En Cours"))
                        is_delivered = any(word in status for word in ["Livré", "Livre", "payé"])
                        
                        if status == "Prêt":
                            status_color, status_icon = "#238636", "✅"
                        elif status == "Annulé":
                            status_color, status_icon = "#da3633", "❌"
                        elif status == "Non Réparable":
                            status_color, status_icon = "#6e7681", "⚠️"
                        elif is_delivered:
                            status_color, status_icon = "#8b949e", "📦"
                        else:
                            status_color, status_icon = "#58a6ff", "⏳"

                        raw_prix = dev.get('Prix', 0)
                        prix_display = f"{raw_prix} د.ج" if raw_prix and str(raw_prix).replace('.','').isdigit() and float(raw_prix) > 0 else "قيد التقييم..."

                        st.markdown(f"""
                            <div style="border-right: 6px solid {status_color}; padding: 12px; background: #161b22; border-radius: 10px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <h3 style="margin: 0; color: #f0f6fc; font-size: 1.1rem;">{dev.get('Appareil', 'جهاز غير معروف')}</h3>
                                    <div style="color: #8b949e; font-size: 0.8rem; font-family: monospace;">Ticket #{dev.get('ID', '0000')}</div>
                                </div>
                                <div style="background-color: {status_color}; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: bold; display: flex; align-items: center; gap: 5px;">
                                    {status_icon} {status}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        with st.expander("📄 عرض التفاصيل والمستحقات"):
                            d_sortie = dev.get("Date_Sortie")
                            
                            if is_delivered:
                                if d_sortie and str(d_sortie).strip() not in ["", "---", "None"]:
                                    w = get_warranty_stats(d_sortie)
                                    if w:
                                        val = float(w.get('percent', 0)) 
                                        is_expired = w.get('is_expired', False)
                                        b_color = "#FFD700" if not is_expired else "#6e7681"
                                        
                                        st.markdown(f"""
                                        <div style="margin-bottom: 15px; border: 1px solid #444c56; padding: 12px; border-radius: 10px; background: rgba(255, 215, 0, 0.05); clear: both; display: block;">
                                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center;">
                                                <div style="color: {b_color}; font-weight: bold; font-size: 0.9rem; display: flex; align-items: center; gap: 8px;">
                                                    <span>🛡️</span>
                                                    <span>{'ضمان سارٍ' if not is_expired else 'ضمان منتهي'}</span>
                                                </div>
                                                <span style="color: {b_color}; font-weight: 800; font-family: monospace;">{int(val)}%</span>
                                            </div>
                                            <div style="width: 100%; background: #30363d; border-radius: 20px; height: 12px; overflow: hidden; border: 1px solid #444c56;">
                                                <div style="width: {val}%; background: {b_color}; height: 100%;"></div>
                                            </div>
                                            <div style="display: flex; justify-content: space-between; margin-top: 8px; color: #8b949e; font-size: 0.75rem;">
                                                <span>الخروج: {w.get('actual_date')}</span>
                                                <span>باقي: {w.get('days_left')} يوم</span>
                                            </div>
                                        </div>""", unsafe_allow_html=True)
                                        
                            elif status == "Non Réparable":
                                st.markdown("""
                                <div style="text-align: center; padding: 12px; background: rgba(248, 81, 73, 0.1); border: 1px dashed #f85149; border-radius: 10px; margin-bottom: 15px; display: block; clear: both;">
                                    <b style="color: #f85149;">⚠️ الجهاز غير قابل للتصليح</b>
                                </div>""", unsafe_allow_html=True)

                            elif status != "Annulé":
                                prog_map = {
                                    "En attente": {"val": 15, "color": "#58a6ff"},
                                    "En Cours":   {"val": 45, "color": "#58a6ff"},
                                    "Réparable":  {"val": 75, "color": "#58a6ff"},
                                    "Prêt":       {"val": 100, "color": "#238636"}
                                }
                                p_data = prog_map.get(status, {"val": 20, "color": "#58a6ff"})
                                st.markdown(f"""
                                <div style="margin-bottom: 15px; display: block; clear: both;">
                                    <div style="margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center;">
                                        <span style="color:#c9d1d9; font-size: 0.85rem; font-weight:bold;">🛠️ حالة الصيانة</span>
                                        <span style="color:{p_data['color']}; font-weight: 800;">{p_data['val']}%</span>
                                    </div>
                                    <div style="width: 100%; background: #30363d; border-radius: 20px; height: 10px; overflow: hidden; border: 1px solid #444c56;">
                                        <div style="width: {p_data['val']}%; background: {p_data['color']}; height: 100%;"></div>
                                    </div>
                                </div>""", unsafe_allow_html=True)

                            st.markdown(f"""
                            <div style="background: rgba(22, 27, 34, 0.5); border-radius: 10px; padding: 12px; border: 1px solid #30363d; display: block; clear: both; width: 100%;">
                                <table style="width:100%; border-collapse: collapse; direction: rtl; border: none;">
                                    <tr style="border-bottom: 1px solid #21262d;">
                                        <td style="padding: 8px 0; color: #8b949e; font-size: 0.9rem; text-align: right;">📅 تاريخ الدخول</td>
                                        <td style="text-align: left; color: #f0f6fc; font-weight: 500;">{dev.get('Date_Entree', '---')}</td>
                                    </tr>
                                    <tr style="border-bottom: 1px solid #21262d;">
                                        <td style="padding: 8px 0; color: #8b949e; font-size: 0.9rem; text-align: right;">📅 تاريخ الخروج</td>
                                        <td style="text-align: left; color: #f0f6fc; font-weight: 500;">{d_sortie if d_sortie else '---'}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px 0 0 0; color: #8b949e; font-size: 0.9rem; text-align: right;">💰 المستحقات</td>
                                        <td style="text-align: left; color: #ffd700; font-weight: 900; font-size: 1.2rem; padding-top: 10px;">{prix_display}</td>
                                    </tr>
                                </table>
                            </div>""", unsafe_allow_html=True)

# ==============================================================================
# 8. تشغيل بوت التلغرام
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

        thread = threading.Thread(target=bot.infinity_polling, daemon=True)
        thread.start()
        return "Bot Started"
    except Exception as e:
        return f"Error: {e}"

if "TELEGRAM_TOKEN" in st.secrets:
    start_telegram_bot()
