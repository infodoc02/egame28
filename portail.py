# --- 🟡 شريط الضمان الذهبي (يظهر إذا وجد تاريخ خروج) ---
                            warranty_shown = False
                            if d_sortie and str(d_sortie).strip() not in ["", "---", "None"]:
                                w = get_warranty_stats(d_sortie)
                                if w:
                                    # استخراج البيانات من الدالة المعرفة سابقاً
                                    val = float(w.get('percent', 0)) 
                                    is_expired = w.get('is_expired', False)
                                    b_color = "#FFD700" if not is_expired else "#6e7681"
                                    warranty_shown = True
                                    
                                    st.markdown(f"""
                                        <div style="margin-bottom: 15px; border: 1px solid #444c56; padding: 12px; border-radius: 10px; background: rgba(255, 215, 0, 0.05); direction: rtl;">
                                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center;">
                                                <div style="color: {b_color}; font-weight: bold; font-size: 0.9rem; display: flex; align-items: center; gap: 8px;">
                                                    <span>🛡️</span>
                                                    <span>{'ضمان سارٍ' if not is_expired else 'ضمان منتهي'} ({w.get('days_left')} يوم)</span>
                                                </div>
                                                <span style="color: {b_color}; font-weight: 800; font-family: 'Courier New', monospace;">{int(val)}%</span>
                                            </div>
                                            <div style="width: 100%; background: #30363d; border-radius: 20px; height: 12px; overflow: hidden; border: 1px solid #444c56; display: flex;">
                                                <div style="width: {val}%; background: {b_color}; height: 100%; transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 0 10px {b_color if not is_expired else 'transparent'};"></div>
                                            </div>
                                            <div style="display: flex; justify-content: space-between; margin-top: 8px;">
                                                <span style="color: #8b949e; font-size: 0.75rem;">تاريخ الخروج: {w.get('actual_date')}</span>
                                                <span style="color: #8b949e; font-size: 0.75rem;">نظام 30 يوم</span>
                                            </div>
                                        </div>
                                    """, unsafe_allow_html=True)
