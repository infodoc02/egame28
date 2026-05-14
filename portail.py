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
# 1. الإعدادات والـ CSS الأسطوري (Neon Style)
# ==============================================================================
st.set_page_config(page_title="InfoDoc - Neon Portal", page_icon="⚡", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    .stApp { background: #05070a; color: white; font-family: 'Cairo', sans-serif; }
    
    /* أنيميشن التوهج للعنوان */
    .neon-title {
        font-family: 'Orbitron', sans-serif;
        font-size: 3.5rem;
        font-weight: 900;
        text-align: center;
        color: #fff;
        text-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff, 0 0 40px #00d4ff;
        animation: pulse-glow 2s infinite alternate;
        margin-bottom: 0;
    }
    @keyframes pulse-glow {
        from { text-shadow: 0 0 10px #00d4ff, 0 0 20px #00d4ff; transform: scale(1); }
        to { text-shadow: 0 0 20px #00d4ff, 0 0 50px #00d4ff; transform: scale(1.02); }
    }

    /* بطاقة الجهاز (أكشن) */
    .device-card {
        background: linear-gradient(145deg, #161b22, #0d1117);
        border: 2px solid #30363d;
        border-radius: 20px 20px 0 0;
        padding: 25px;
        margin-top: 30px;
        position: relative;
        overflow: hidden;
        transition: 0.4s;
    }
    .device-card:hover { border-color: #00d4ff; box-shadow: 0 0 20px rgba(0, 212, 255, 0.2); }

    /* تنسيق الـ Expander (الذي رددته حطبة) */
    div[data-testid="stExpander"] {
        border: 2px solid #30363d !important;
        border-top: none !important;
        border-radius: 0 0 20px 20px !important;
        background: rgba(22, 27, 34, 0.8) !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5) !important;
        transition: 0.4s;
    }
    div[data-testid="stExpander"]:hover { border-color: #00d4ff !important; }
    
    .stExpander summary p {
        color: #00d4ff !important;
        font-weight: 900 !important;
        font-size: 1.1rem !important;
        text-shadow: 0 0 5px rgba(0, 212, 255, 0.5);
    }

    /* المبالغ (Neon Box) */
    .price-tag {
        background: rgba(0, 255, 65, 0.1);
        border: 1px solid #00ff41;
        padding: 10px 20px;
        border-radius: 12px;
        color: #00ff41 !important;
        font-family: 'Orbitron';
        font-weight: 900;
        font-size: 1.5rem;
        display: inline-block;
        text-shadow: 0 0 10px #00ff41;
    }

    /* حالة المحل المضيئة */
    .status-badge {
        font-family: 'Orbitron'; padding: 8px 25px; border-radius: 50px;
        font-weight: 900; letter-spacing: 2px;
    }
    .open { color: #00ff41; border: 2px solid #00ff41; box-shadow: 0 0 15px #00ff41; }
    .closed { color: #ff3131; border: 2px solid #ff3131; box-shadow: 0 0 15px #ff3131; }

    /* زر التلغرام الأسطوري */
    .tg-pulse {
        display: block; background: #229ED9; color: white !important;
        text-align: center; padding: 18px; border-radius: 15px;
        font-weight: 900; text-decoration: none;
        animation: tg-glow 1.5s infinite;
        font-size: 1.1rem;
    }
    @keyframes tg-glow {
        0% { box-shadow: 0 0 0 0 rgba(34, 158, 217, 0.7); }
        70% { box-shadow: 0 0 0 15px rgba(34, 158, 217, 0); }
        100% { box-shadow: 0 0 0 0 rgba(34, 158, 217, 0); }
    }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. الربط والمنطق (Keep it clean)
# ==============================================================================
if not firebase_admin._apps:
    cred_dict = dict(st.secrets["firebase"])
    if "\\n" in cred_dict["private_key"]: cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
    firebase_admin.initialize_app(credentials.Certificate(cred_dict), {'databaseURL': st.secrets["DB_URL"]})

def normalize_phone(p):
    p = re.sub(r"\D", "", str(p or ""))
    return "0" + p[3:] if p.startswith("213") else p

# ==============================================================================
# 3. الواجهة الرسومية (The Visuals)
# ==============================================================================
shop_is_open = db.reference("shop_settings/is_open").get()
st.markdown('<h1 class="neon-title">INFODOC</h1>', unsafe_allow_html=True)
st.markdown(f'<div style="text-align:center;"><span class="status-badge {"open" if shop_is_open else "closed"}">{"OPEN" if shop_is_open else "CLOSED"}</span></div>', unsafe_allow_html=True)

st.write("") # فراغ

# حقل البحث (تنسيقه نيون تلقائياً من الـ CSS فوق)
user_phone = st.text_input("📱 أدخل رقم هاتفك لتفقد الحالة:", placeholder="0XXXXXXXXX")

if user_phone:
    norm_phone = normalize_phone(user_phone)
    raw = db.reference("atelier").get()
    if raw:
        my_devs = [dict(v, _id=k) for k, v in raw.items() if normalize_phone(v.get("Telephone")).endswith(norm_phone[-9:])]
        
        if my_devs:
            # زر التلغرام (الأنيميشن القوي)
            bot_user = st.secrets.get("BOT_USERNAME", "InfoDocBot")
            st.markdown(f'<a href="https://t.me/{bot_user}?start={norm_phone}" class="tg-pulse">🚀 فَعّل إشعارات التلغرام الفورية</a>', unsafe_allow_html=True)

            for d in sorted(my_devs, key=lambda x: str(x.get("ID")), reverse=True):
                stat = d.get("Statut", "En Cours")
                
                # المربع العلوي (الجهاز)
                st.markdown(f"""
                    <div class="device-card">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <h2 style="margin:0; color:#fff !important; font-family:'Cairo';">{d.get('Appareil')}</h2>
                                <span style="color:#00d4ff; font-family:'Orbitron';">#{d.get('ID')}</span>
                            </div>
                            <div style="text-align:right;">
                                <span style="display:block; font-size:0.8rem; color:#8b949e !important;">حالة الصيانة</span>
                                <b style="font-size:1.2rem; color:#00ff41 !important;">{stat}</b>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                # الأكورديون (التفاصيل الملونة)
                with st.expander("💎 تفاصيل السعر والمواعيد والضمان"):
                    st.markdown("<br>", unsafe_allow_html=True)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"🗓️ **تاريخ الاستلام:** <span style='color:#58a6ff;'>{d.get('Date_Entree')}</span>", unsafe_allow_html=True)
                        st.markdown(f"🗓️ **تاريخ التسليم:** <span style='color:#58a6ff;'>{d.get('Date_Sortie', '---')}</span>", unsafe_allow_html=True)
                    with col2:
                        st.markdown(f'<div style="text-align:center;"><p style="margin:0; font-size:0.8rem;">المبلغ الإجمالي</p><div class="price-tag">{d.get("Prix")} DA</div></div>', unsafe_allow_html=True)
                    
                    st.markdown("<hr style='border-color:#30363d;'>", unsafe_allow_html=True)
                    st.write("🔧 **نسبة الإنجاز:**")
                    prog = 1.0 if "Prêt" in stat or "Livré" in stat else 0.4
                    st.progress(prog)
