import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import re
from datetime import datetime
import threading
import telebot
import pandas as pd
import io
import pytz

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
            
            # حساب النسب
            p_left = (remaining_days / 30) * 100
            p_consumed = min((diff_days / 30) * 100, 100) if diff_days >= 0 else 0
            
            return {
                "percent": p_left,          # المفتاح القديم (للموافقة)
                "percent_left": p_left,     # المفتاح الجديد
                "consumed_percent": p_consumed, # عمود النقصان (الأصفر)
                "is_expired": diff_days > 30, 
                "days_left": remaining_days
            }
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
algeria_tz = pytz.timezone('Africa/Algiers')
now = datetime.now(algeria_tz)
greeting = "عزيزي الزبون صباح الخير" if 5 <= now.hour < 12 else "عزيزي الزبون مساء الخير"

# 2. جلب الحالة من قاعدة البيانات (كما هي)
try:
    # جلب القيمة مباشرة (تأكد أن التطبيق الرئيسي يرفعها كـ True أو False)
    shop_status = db.reference("shop_settings/is_open").get()
    
    # في حال كانت القيمة فارغة في القاعدة لأي سبب
    if shop_status is None:
        shop_status = False
except Exception as e:
    shop_status = False # حالة احتياطية

# 3. التحية بناءً على وقت الجزائر
greeting = "عزيزي الزبون صباح الخير" if 5 <= now.hour < 12 else "عزيزي الزبون مساء الخير"

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

# أزرار التواصل
c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown('<a href="tel:0798661900" class="custom-btn"><span>📞</span><b>اتصل بنا</b></a>', unsafe_allow_html=True)
with c2: 
    st.markdown("""<a href="https://maps.app.goo.gl/RBGLbVDiCeqAdxVT8"><span>📍</span><b>موقعنا</b></a>""", unsafe_allow_html=True)
with c3: st.markdown('<a href="https://www.facebook.com/share/18dX9h9otd/" target="_blank" class="custom-btn"><span>📘</span><b>فيسبوك</b></a>', unsafe_allow_html=True)
with c4: st.markdown('<a href="https://tiktok.com/@infodoc02/" target="_blank" class="custom-btn"><span>📱</span><b>تيك توك</b></a>', unsafe_allow_html=True)

# قسم الشروط (المضيء فقط)
with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: 'Cairo'; line-height: 1.8; color: #f0f6fc;">
            1️⃣ إذا تم فحص الجهاز وتبين أنه قابل للتصليح و<b>رفض الزبون ذلك</b>، يتم دفع <b>1000 دج</b> ثمن الجهد والفحص.<br>
            2️⃣ أسعار العمل على <b>البطاقة الأم (Carte Mère)</b> تبدأ من <b>3000 دج</b>.<br>
            3️⃣ أسعار <b>تفليش وفتح البيوس (Flash BIOS)</b> تبدأ من <b>1500 دج</b> حسب نوع الجهاز وجيله.<br>
            4️⃣ <b>الموافقة التلقائية:</b> نصلح مباشرة إذا كان السعر بين 3000 و 4000 دج. فوق ذلك نطلب موافقتك أولاً.<br>
            5️⃣ <b>سياسة الضمان:</b> الضمان صالح <b>فقط</b> على العنصر الذي تم إصلاحه، وأي خلل يمس عنصراً آخر خلال فترة الضمان لا يؤخذ بعين الاعتبار.<br>
            6️⃣ <b>تنبيهات تلقائية:</b> ننصحك بتحميل تطبيق <b>Telegram</b> وفتح حساب فيه، ثم الضغط على الزر الأزرق العائم بالأسفل لربط جهازك لتصلك تحديثات حالة الصيانة فوراً.
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
            # 1. فلترة الأجهزة المرتبطة بالرقم
            my_devices = [dict(v, _id=k) for k, v in raw_data.items() if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])]
            
            if not my_devices:
                st.error("⚠️ عذراً، لم نجد أي جهاز مرتبط بهذا الرقم في نظامنا.")
            else:
                # 2. عرض زر التلغرام العائم (فقط إذا لم يكن مربوطاً مسبقاً)
                if any(not d.get("Telegram_ID") for d in my_devices):
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                    st.markdown(f'''
                        <a href="https://t.me/{bot_user}?start={norm_phone}" target="_blank" class="floating-tg-btn">
                            🚀 تفعيل إشعارات التلغرام
                        </a>
                    ''', unsafe_allow_html=True)
                
                # 3. ترتيب الأجهزة حسب الأولوية (الجديد والمستعجل أولاً)
                my_devices.sort(
                    key=lambda x: (
                        get_status_priority(x.get("Statut", "En Cours")), 
                        -int(x.get("ID", 0)) if str(x.get("ID", 0)).isdigit() else 0
                    )
                )
                
                # 4. حلقة عرض الأجهزة
                for dev in my_devices:
                    status = str(dev.get("Statut", "En Cours"))
                    is_done = "Livré" in status
                    
                    # --- إضافة الأيقونات بناءً على الحالة ---
                    status_icon = "⏳" # الافتراضي
                    if status == "Prêt": status_icon = "✅"
                    elif status == "Annulé": status_icon = "❌"
                    elif status == "Non Réparable": status_icon = "⚠️"
                    elif status == "Réparable": status_icon = "🛠️"
                    elif is_done: status_icon = "📦"

                    # تحديد الألوان
                    status_color = "#238636" if status == "Prêt" else "#da3633" if status == "Annulé" else "#6e7681" if is_done else "#58a6ff"
                    
                    # تحسين عرض السعر داخل الحلقة (Loop)
                    raw_prix = dev.get('Prix')
                    prix_display = f"{raw_prix} د.ج" if raw_prix and str(raw_prix).isdigit() and int(raw_prix) > 0 else "قيد التقييم..."

                    # 1. رأس البطاقة
                    st.markdown(f"""
                        <div class="device-header" style="border-right: 6px solid {status_color};">
                            <div>
                                <h3 class="device-title">{dev.get('Appareil')}</h3>
                                <div class="device-id">Ticket #{dev.get('ID')}</div>
                            </div>
                            <div class="status-badge-mini" style="background-color: {status_color};">
                                {status_icon} {status}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # 2. تفاصيل الجهاز
                    with st.expander("📄 عرض التفاصيل والمستحقات"):
                        if status == "Livre et payé":
                            # (نفس كود الضمان السابق اللي درناه...)
                            w = get_warranty_stats(dev.get("Date_Sortie"))
                            if w:
                                val, is_expired = w['percent_left'], w['is_expired']
                                b_color = "#FFD700" if not is_expired else "#4b4b4b"
                                status_text = "🛡️ الضمان سارٍ" if not is_expired else "<del style='color: #f85149;'>❌ فترة الضمان منتهية</del>"
                                st.markdown(f'<div style="width: 100%; background: #30363d; border-radius: 10px; height: 8px;"><div style="width: {val}%; background: {b_color}; height: 100%; border-radius: 10px;"></div></div>', unsafe_allow_html=True)

                        elif status == "Non Réparable":
                            # حالة الحزن: الجهاز غير قابل للتصليح
                            st.markdown(f"""
                                <div style="text-align: center; padding: 15px; background: rgba(248, 81, 73, 0.05); border: 1px dashed #f85149; border-radius: 12px; margin-bottom: 10px;">
                                    <div style="font-size: 2rem;">🥀</div>
                                    <b style="color: #f85149; font-family: 'Cairo';">للأسف، الجهاز غير قابل للتصليح</b><br>
                                    <small style="color: #8b949e;">بذلنا قصارى جهدنا، لكن الضرر كان بليغاً.</small>
                                    <div style="width: 100%; background: #30363d; border-radius: 10px; height: 8px; margin-top: 10px;">
                                        <div style="width: 100%; background: #4b4b4b; height: 100%; border-radius: 10px;"></div>
                                    </div>
                                    <span style="font-size: 10px; color: #8b949e;">تم إنهاء الفحص بنسبة 100%</span>
                                </div>
                            """, unsafe_allow_html=True)

                        else:
                            # حالة الصيانة العادية: (0%, 33%, 66%, 100%)
                            prog_map = {
                                "En attente": {"val": 0.0, "pct": "0%"},
                                "En Cours":   {"val": 0.33, "pct": "33%"},
                                "Réparable":  {"val": 0.66, "pct": "66%"},
                                "Prêt":       {"val": 1.0, "pct": "100%"}
                            }
                            p_data = prog_map.get(status, {"val": 0.1, "pct": "..."})

                            st.markdown(f"""
                                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                    <span style="color: #8b949e; font-size: 0.9rem; font-weight: bold;">🛠️ تقدم الصيانة</span>
                                    <span style="color: #00d4ff; font-family: 'Orbitron'; font-weight: 900;">{p_data['pct']}</span>
                                </div>
                            """, unsafe_allow_html=True)
                            st.progress(p_data['val'])

                        # الجدول السفلي (المبلغ والتواريخ)
                        st.markdown(f"""
                            <table style="width:100%; margin-top: 15px; border-collapse: collapse; font-family: 'Cairo';">
                                <tr style="border-bottom: 1px solid #30363d;">
                                    <td style="padding: 8px; color: #8b949e;">📅 تاريخ الدخول</td>
                                    <td style="text-align: left;">{dev.get('Date_Entree', '---')}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 8px; color: #8b949e;">💰 تكلفة الفحص</td>
                                    <td style="text-align: left; color: #f85149; font-weight: 900;">{dev.get('Prix', '0')} DZD</td>
                                </tr>
                            </table>
                        """, unsafe_allow_html=True)
