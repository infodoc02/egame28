# ==============================================================================
# 5. نظام البحث والتتبع (النسخة الأصلية الملتزمة بالتعديلات المطلوبة فقط)
# ==============================================================================

# استدعاء الخطوط وتعديل المحاذاة لليمين فقط للأجزاء المطلوبة
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&family=Orbitron:wght@700;900&display=swap');
    
    /* محاذاة حقل إدخال الهاتف إلى اليمين */
    div[data-testid="stTextInput"] input {
        direction: rtl !important;
        text-align: right !important;
    }
    /* محاذاة عنوان الأكسباندر إلى اليمين */
    div[data-testid="stExpander"] summary {
        direction: rtl !important;
        text-align: right !important;
    }
    /* جعل خلفية الأكسباندر شفافة تماماً وإلغاء اللون الداكن */
    div[data-testid="stExpander"] {
        background: transparent !important;
        border: 1px solid #334155 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<h3 style="text-align: right; font-family: \'Cairo\', sans-serif; color: #cbd5e1; font-size: 1.3rem;">🔍 تتبع حالة أجهزتك الآن:</h3>', unsafe_allow_html=True)

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
                    # زر التلغرام العائم الأصلي كما هو
                    bot_user = st.secrets.get("BOT_USERNAME", "InfoDoc_Workshop_Bot")
                    st.markdown(f'''
                        <a href="https://t.me/{bot_user}?start={norm_phone}" target="_blank" 
                           style="position: fixed; bottom: 30px; left: 30px; background: linear-gradient(135deg, #24A1DE, #1d80b0); color: white; 
                                  padding: 12px 22px; border-radius: 50px; text-decoration: none; font-family: 'Cairo', sans-serif; font-weight: bold; 
                                  box-shadow: 0 8px 20px rgba(36, 161, 222, 0.4); z-index: 99999; display: flex; align-items: center; gap: 8px;">
                            📢 تفعيل الإشعارات (Telegram)
                        </a>
                    ''', unsafe_allow_html=True)
                
                    # ترتيب الأجهزة الأصلي
                    my_devices.sort(key=lambda x: -int(x.get("ID", 0)) if str(x.get("ID", 0)).isdigit() else 0)
                
                    for dev in my_devices:
                        status_raw = str(dev.get("Statut", "En Attente")).strip()
                        status_lower = status_raw.lower()
                        
                        # دالة الألوان الأصلية الخاصة بك تماماً مع ضبط مقاس ثابت موحد (min-width) لمنع التفاوت
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

                        # تنسيق السعر الأصلي بخط Orbitron ومنع الانعكاس
                        raw_prix = dev.get('Prix', 0)
                        if "en cours" in status_lower or "en attente" in status_lower:
                            prix_html = '<span style="color: #94a3b8; font-family: \'Cairo\';">⚙️ قيد الفحص...</span>'
                        else:
                            try:
                                formatted_p = f"{int(float(raw_prix)):,}".replace(',', ' ')
                                prix_html = f'<div style="display: inline-block; direction: ltr;"><span style="font-family: \'Orbitron\', sans-serif; font-size: 1.4rem; color: #facc15; font-weight: 900;">{formatted_p}</span> <span style="font-family: \'Cairo\', sans-serif; color: #facc15; font-weight: bold;">DA</span></div>'
                            except: 
                                prix_html = f'<div style="display: inline-block; direction: ltr;"><span style="font-family: \'Orbitron\', sans-serif; font-size: 1.4rem; color: #facc15;">0</span> <span style="font-family: \'Cairo\', sans-serif; color: #facc15;">DA</span></div>'

                        # الكرت العلوي الأصلي الخاص بك مع إدراج الخاصية min-width لتوحيد حجم الحالات
                        st.markdown(f"""
                            <div style="background: #1e293b; border: 1px solid #334155; border-right: 5px solid {s_color}; 
                                        border-radius: 12px 12px 0 0; padding: 16px; margin-top: 15px; 
                                        font-family: 'Cairo', sans-serif; direction: rtl; text-align: right;">
                                <div style="display: flex; justify-content: space-between; align-items: center; flex-direction: row-reverse; gap: 10px;">
                                    <div style="background: {s_bg}; border: 1px solid {s_color}; color: {s_color}; 
                                                padding: 6px 12px; border-radius: 8px; font-weight: 900; font-size: 0.95rem;
                                                min-width: 160px; text-align: center; flex-shrink: 0; box-sizing: border-box;">
                                        {s_text}
                                    </div>
                                    <div style="text-align: right; width: 100%;">
                                        <h3 style="margin: 0; color: #ffffff; font-size: 1.4rem; font-weight: 900;">{dev.get('Appareil', 'جهاز غير معروف')}</h3>
                                        <div style="color: #94a3b8; font-size: 0.95rem; font-family: monospace; margin-top: 2px;">تذكرة رقم: #{dev.get('ID', '0000')}</div>
                                    </div>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # الأكسباندر الأصلي الخاص بك (تم تعديل الخلفية لتصبح شفافة بالكامل عبر الـ CSS العلوي)
                        with st.expander("📄 عرض تفاصيل التقرير والمستحقات الفنية"):
                            
                            d_sortie = dev.get("Date_Sortie")
                            panne_text = dev.get('Panne', dev.get('Defaut', 'غير محدد'))
                            
                            st.markdown(f'<div style="padding: 10px; font-family: \'Cairo\', sans-serif; direction: rtl; text-align: right;">', unsafe_allow_html=True)

                            # 1. نظام الضمان الأصلي (تعديل الخط للنسبة المئوية ليصبح Orbitron)
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
                                                <!-- النسبة المئوية بخط Orbitron المطلوب -->
                                                <div style="color: {w_color}; font-family: 'Orbitron', sans-serif; font-weight: 900; font-size: 1.4rem; display: inline-block; direction: ltr;">{int(val)}%</div>
                                                <span style="color: {w_color}; font-weight: bold;">{w_status_txt}</span>
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

                            # 2. نظام أشرطة التقدم الأصلي (تعديل الخط للنسبة المئوية ليصبح Orbitron)
                            elif not any(x in status_lower for x in ["annulé", "annule", "non réparable", "non reparable", "prêt", "pret"]):
                                prog_map = {"en attente": 20, "en cours": 50, "réparable": 80}
                                p_val = prog_map.get(status_lower, 30)
                                st.markdown(f"""
                                    <div style="margin-bottom: 12px;">
                                        <div style="display: flex; justify-content: space-between; direction: rtl; margin-bottom: 4px; align-items: center; flex-direction: row-reverse;">
                                            <!-- النسبة المئوية بخط Orbitron المطلوب -->
                                            <div style="color:#3b82f6; font-weight: 900; font-family: 'Orbitron', sans-serif; font-size: 1.4rem; display: inline-block; direction: ltr;">{p_val}%</div>
                                            <span style="color:#cbd5e1; font-size: 0.95rem;">⚙️ تقدم الصيانة:</span>
                                        </div>
                                        <div style="width: 100%; background: #1e293b; border-radius: 10px; height: 8px; overflow: hidden;">
                                            <div style="width: {p_val}%; background: #3b82f6; height: 100%;"></div>
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)

                            # 3. جدول البيانات الأصلي الخاص بك تماماً ومحاذاته لليمين مع إضافة خانة العطل (Panne)
                            st.markdown(f"""
                                <table style="width:100%; direction: rtl; text-align: right; border-collapse: collapse; font-size: 0.95rem;">
                                    <tr style="border-bottom: 1px solid #1e293b;">
                                        <td style="padding: 6px 0; color: #94a3b8;">📅 تاريخ الدخول:</td>
                                        <td style="text-align: left; color: #f1f5f9; font-family: sans-serif; font-weight: bold;">{dev.get('Date_Entree', '---')}</td>
                                    </tr>
                                    <tr style="border-bottom: 1px solid #1e293b;">
                                        <td style="padding: 6px 0; color: #94a3b8;">📅 تاريخ الخروج:</td>
                                        <td style="text-align: left; color: #f1f5f9; font-family: sans-serif; font-weight: bold;">{dev.get('Date_Sortie', '---')}</td>
                                    </tr>
                                    <tr style="border-bottom: 1px solid #1e293b;">
                                        <td style="padding: 6px 0; color: #94a3b8;">🛠️ العطل المسجل:</td>
                                        <td style="text-align: left; color: #ef4444; font-weight: bold;">{panne_text}</td>
                                    </tr>
                                    <tr>
                                        <td style="padding: 10px 0 0 0; color: #facc15; font-weight: bold;">💰 المستحقات:</td>
                                        <td style="text-align: left; padding-top: 10px;">{prix_html}</td>
                                    </tr>
                                </table>
                            """, unsafe_allow_html=True)
                            
                            st.markdown('</div>', unsafe_allow_html=True)
