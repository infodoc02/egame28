
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
# 1. إعدادات الصفحة الأساسية (Configuration)
# ==============================================================================
st.set_page_config(
    page_title="InfoDoc - Client Portal",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==============================================================================
# 2. الاتصال بقاعدة البيانات (Firebase Connection)
# ==============================================================================
@st.cache_resource
def init_db():
    """
    وظيفة لربط التطبيق بقاعدة بيانات فيربايس.
    يتم جلب الإعدادات من ملف secrets.toml الخاص بـ Streamlit.
    """
    if not firebase_admin._apps:
        try:
            cred_dict = dict(st.secrets["firebase"])
            # معالجة الرموز الخاصة بالمفتاح السري
            if "\\n" in cred_dict["private_key"]:
                cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': st.secrets["DB_URL"]
            })
            return True
        except Exception as e:
            st.error(f"خطأ في الاتصال: {e}")
            return False
    return True

init_db()

# ==============================================================================
# 3. الدوال البرمجية المساعدة (Helper Functions)
# ==============================================================================
def normalize_phone(phone: str) -> str:
    """تنسيق رقم الهاتف ليكون موحداً (0XXXXXXXXX)"""
    p = re.sub(r"\D", "", str(phone or ""))
    if p.startswith("213"):
        p = "0" + p[3:]
    if len(p) == 9 and p[0] in ["5", "6", "7"]:
        p = "0" + p
    return p

def get_warranty_stats(date_sortie_str):
    """حساب النسبة المئوية والأيام المتبقية للضمان (30 يوم)"""
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
        except:
            continue
    return None

# ==============================================================================
# 4. التنسيقات البصرية المتقدمة (CSS Styling)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    /* تنسيق التطبيق العام */
    .stApp { background: #0d1117; color: white; font-family: 'Cairo', sans-serif; }
    
    /* تصميم العنوان النيوني */
    .main-title {
        font-family: 'Orbitron', sans-serif; font-size: clamp(2.5rem, 10vw, 4rem); font-weight: 900;
        text-align: center; margin-bottom: 0px; color: #fff; text-transform: uppercase;
        letter-spacing: 5px; text-shadow: 0 0 15px #58a6ff, 0 0 30px #58a6ff;
        animation: glow 2s ease-in-out infinite alternate;
    }
    
    @keyframes glow {
        from { text-shadow: 0 0 10px #58a6ff, 0 0 20px #58a6ff; }
        to { text-shadow: 0 0 20px #58a6ff, 0 0 50px #58a6ff; transform: scale(1.02); }
    }

    /* حالة المحل المضيئة */
    .status-badge { 
        font-family: 'Orbitron'; font-size: 1.1rem; font-weight: 900; 
        padding: 8px 30px; border-radius: 50px; display: inline-block; 
    }
    .status-open { color: #00ff41; border: 2px solid #00ff41; animation: blink-g 1.5s infinite; }
    .status-closed { color: #ff3131; border: 2px solid #ff3131; animation: blink-r 1.5s infinite; }
    
    @keyframes blink-g { 50% { box-shadow: 0 0 20px #00ff41; } }
    @keyframes blink-r { 50% { box-shadow: 0 0 20px #ff3131; } }

    /* أزرار التواصل (تصحيح المربعات) */
    .custom-btn {
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px; padding: 15px; text-decoration: none !important; color: white !important;
        transition: 0.3s ease-in-out; width: 100%; min-height: 100px;
    }
    .custom-btn:hover { border-color: #58a6ff; background: rgba(88, 166, 255, 0.15); transform: translateY(-5px); }
    .custom-btn i { font-size: 2rem; margin-bottom: 10px; }

    /* حقل الهاتف والاكسباندر */
    div[data-baseweb="input"] { border-radius: 12px !important; border: 2px solid #30363d !important; background: #161b22 !important; }
    div[data-baseweb="input"]:focus-within { border-color: #58a6ff !important; box-shadow: 0 0 15px rgba(88, 166, 255, 0.2) !important; }

    .device-box {
        background: #161b22; border: 1px solid #30363d; border-radius: 15px; 
        padding: 20px; margin-top: 25px; margin-bottom: 0px;
    }
    
    .stExpander {
        background: #0d1117 !important; border: 1px solid #30363d !important;
        border-top: none !important; border-radius: 0 0 15px 15px !important;
    }
    
    /* زر التلغرام */
    .tg-btn { 
        display: block; background: #229ED9; color: white !important; text-align: center; 
        padding: 15px; border-radius: 12px; text-decoration: none; font-weight: 900; 
        margin-top: 10px; margin-bottom: 20px; transition: 0.3s;
    }
    .tg-btn:hover { box-shadow: 0 0 25px #229ED9; }

    .badge-label { padding: 4px 12px; border-radius: 6px; font-weight: bold; font-size: 0.8rem; font-family: 'Orbitron'; }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 5. واجهة المستخدم الرأسية (Header Section)
# ==============================================================================
# الترحيب الذكي
now = datetime.now()
greeting = "صباح الخير" if 5 <= now.hour < 12 else "مساء الخير"

# جلب حالة المحل
try:
    shop_status = db.reference("shop_settings/is_open").get()
except:
    shop_status = True

st.markdown(f'<div style="text-align: center; color: #8b949e; font-size: 0.9rem;">{greeting} | {now.strftime("%Y-%m-%d %H:%M")}</div>', unsafe_allow_html=True)
st.markdown('<div class="main-title">INFODOC</div>', unsafe_allow_html=True)
st.markdown('<div style="text-align: center; color: #8b949e; margin-bottom: 20px;">Vente & Réparation Informatique</div>', unsafe_allow_html=True)

# عرض حالة المحل
st.markdown(f"""
    <div style="text-align: center; margin-bottom: 30px;">
        <span class="status-badge {'status-open' if shop_status else 'status-closed'}">
            {'OPEN - مـفـتـوح' if shop_status else 'CLOSED - مـغـلـق'}
        </span>
    </div>
""", unsafe_allow_html=True)

st.markdown(f"""
    <div class="hero-container">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div class="main-title">INFODOC TECHNOLOGY</div>
            <div class="{status_class}">{status_text}</div>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; margin-top: 15px;">
            <div class="contact-item">📞 <b>الهاتف:</b> 0798661900</div>
            <a href="https://maps.google.com/?q=36.1648,1.3317" target="_blank" style="text-decoration: none;">
                <div style="background: #238636; color: white; text-align: center; padding: 10px; border-radius: 8px; font-weight: bold; transition: 0.3s;">
                    📍 اتبع المسار إلى المحل (Google Maps)
                </div>
            </a>
            <div class="contact-item">🔵 <b>Facebook:</b> InfoDoc</div>
            <div class="contact-item">⚫ <b>TikTok:</b> @infodoc02</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- 6. الشروط الموضحة ---
with st.expander("⚠️ اضغط هنا لقراءة ملاحظات وشروط الصيانة الهامة"):
    st.markdown("""
        <div style="text-align: right; direction: rtl; font-family: Cairo; line-height: 1.8;">
            1️⃣ فحص الجهاز المرفوض تصليحه: <b>1000 دج</b>.<br>
            2️⃣ صيانة البطاقة الأم تبدأ من <b>3000 دج</b>.<br>
            3️⃣ الموافقة التلقائية بين 3000 و 4000 دج، ما فوق ذلك نتصل بك.<br>
            4️⃣ يرجى ربط <b>Telegram</b> لتصلك الإشعارات فوراً.
        </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 6. نظام البحث وتتبع الأجهزة (Tracking System)
# ==============================================================================
st.markdown("""
    <div style="text-align: center; margin-top: 50px; margin-bottom: 20px;">
        <h2 style="
            font-family: 'Cairo', sans-serif; 
            color: #58a6ff; 
            text-shadow: 0 0 10px rgba(88, 166, 255, 0.3);
            font-weight: 900;
            letter-spacing: 1px;
        ">
            🔍 تتبع أجهزتك الآن
        </h2>
        <p style="color: #8b949e; font-size: 0.9rem; margin-top: -10px;">
            أدخل رقم الهاتف المسجل لتفقد حالة الصيانة والضمان
        </p>
    </div>
""", unsafe_allow_html=True)
user_phone = st.text_input("", placeholder="أدخل رقم هاتفك هنا (مثال: 0798661900)", key="phone_input_unique")
if user_phone:
    norm_phone = normalize_phone(user_phone)
    if len(norm_phone) >= 9:
        # الاتصال بجلب البيانات
        db_ref = db.reference("atelier")
        raw_data = db_ref.get()
        
        if raw_data:
            # تصفية النتائج
            my_devices = [dict(v, _id=k) for k, v in raw_data.items() if normalize_phone(v.get("Telephone", "")).endswith(norm_phone[-9:])]
            
            if not my_devices:
                st.warning("⚠️ لم نجد أي جهاز مرتبط بهذا الرقم.")
            else:
                # عرض زر التلغرام إذا لم يتم الربط بعد
                if any(not d.get("Telegram_ID") for d in my_devices):
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
                    st.markdown(f'<a href="https://t.me/{bot_user}?start={norm_phone}" target="_blank" class="tg-btn">🚀 ربط الإشعارات الفورية على تليغرام</a>', unsafe_allow_html=True)
                
                # ترتيب الأجهزة (الجديد أولاً)
                my_devices.sort(key=lambda x: (str(x.get("Date_Sortie", "")) != "", x.get("ID", 0)), reverse=True)
                
                for dev in my_devices:
                    status = str(dev.get("Statut", "En Cours"))
                    is_done = "Livré" in status
                    status_color = "#238636" if status == "Prêt" else "#da3633" if status == "Annulé" else "#6e7681" if is_done else "#58a6ff"
                    
                    # المربع الرئيسي (Header)
                    st.markdown(f"""
                        <div class="device-box" style="border-right: 6px solid {status_color};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <h3 style="margin:0; color:white;">{dev.get('Appareil')}</h3>
                                    <small style="color:#8b949e;">رقم الوصل: #{dev.get('ID')}</small>
                                </div>
                                <span class="badge-label" style="background:{status_color}; color:white;">{status.upper()}</span>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # الأكورديون (الذي يكمل المربع)
                    with st.expander("📄 تفاصيل السعر، الضمان والمواعيد"):
                        # شريط الحالة والضمان
                        if is_done:
                            warranty = get_warranty_stats(dev.get("Date_Sortie"))
                            if warranty and not warranty["is_expired"]:
                                st.write(f"🛡️ الضمان سارٍ: متبقي {int(warranty['days_left'])} يوم")
                                st.progress(warranty['percent']/100)
                            else:
                                st.error("❌ فترة الضمان منتهية")
                        else:
                            st.write("🛠️ حالة الصيانة الحالية:")
                            p_level = 0.3 if status == "En Cours" else 0.7 if status == "Réparable" else 1.0
                            st.progress(p_level)
                        
                        # جدول البيانات المالي والزمني
                        st.markdown(f"""
                            <div style="background: rgba(255,255,255,0.03); padding: 15px; border-radius: 10px; margin: 10px 0; border: 1px solid #30363d;">
                                <table style="width: 100%; text-align: center; border-collapse: collapse;">
                                    <tr>
                                        <td style="color: #8b949e; padding: 5px;">تاريخ الاستلام</td>
                                        <td style="color: #8b949e; padding: 5px;">تاريخ التسليم</td>
                                    </tr>
                                    <tr>
                                        <td style="font-weight: bold;">{dev.get('Date_Entree')}</td>
                                        <td style="font-weight: bold;">{dev.get('Date_Sortie', '---')}</td>
                                    </tr>
                                </table>
                                <div style="text-align: center; margin-top: 15px; padding-top: 10px; border-top: 1px solid #333;">
                                    <span style="font-size: 1.3rem; color: #58a6ff; font-weight: 900;">السعر الإجمالي: {dev.get('Prix')} دج</span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # زر تحميل الفاتورة
                        try:
                            pdf_data = pd.DataFrame([{"رقم": dev.get('ID'), "الجهاز": dev.get('Appareil'), "السعر": dev.get('Prix')}])
                            excel_buf = io.BytesIO()
                            with pd.ExcelWriter(excel_buf, engine='xlsxwriter') as wr:
                                pdf_data.to_excel(wr, index=False)
                            st.download_button(
                                label=f"📥 تحميل وصل {dev.get('Appareil')}",
                                data=excel_buf.getvalue(),
                                file_name=f"InfoDoc_{dev.get('ID')}.xlsx",
                                key=f"dl_{dev.get('_id')}"
                            )
                        except:
                            pass

# ==============================================================================
# 7. تشغيل بوت التلغرام (Telegram Bot Thread)
# ==============================================================================
def run_bot():
    """وظيفة لتشغيل البوت في مسار منفصل لعدم تعطيل الموقع"""
    token = st.secrets.get("TELEGRAM_TOKEN")
    if not token: return
    bot = telebot.TeleBot(token)
    
    @bot.message_handler(commands=['start'])
    def handle_start(m):
        txt = m.text.split()
        if len(txt) > 1:
            phone = normalize_phone(txt[1])
            ref = db.reference("atelier")
            data = ref.get()
            if data:
                for k, v in data.items():
                    if normalize_phone(v.get("Telephone", "")).endswith(phone[-9:]):
                        ref.child(k).update({"Telegram_ID": str(m.chat.id)})
                bot.reply_to(m, "✅ تم ربط الحساب بنجاح! ستصلك الإشعارات هنا.")
    
    bot.polling(none_stop=True)

# بدء البوت في خلفية النظام
if "bot_active" not in st.session_state:
    threading.Thread(target=run_bot, daemon=True).start()
    st.session_state["bot_active"] = True
