"""
نظام تتبع الزوار عن طريق IP Address
يحفظ بيانات الزوار في Firebase Realtime Database
"""

import streamlit as st
from firebase_admin import db
from datetime import datetime
import pytz
import requests
import hashlib
from collections import defaultdict

# ==============================================================================
# 1. الحصول على IP الزائر
# ==============================================================================

def get_client_ip():
    """الحصول على IP الزائر من طلب HTTP."""
    try:
        # محاولة الحصول على IP من headers في بيئة الاستضافة
        if "X-Forwarded-For" in st.session_state:
            return st.session_state["X-Forwarded-For"].split(",")[0].strip()
        
        # محاولة الحصول من متغيرات البيئة أو الطلب
        response = requests.get('https://api.ipify.org?format=json', timeout=3)
        if response.status_code == 200:
            return response.json()['ip']
    except:
        pass
    
    return "UNKNOWN"

# ==============================================================================
# 2. معالجة IP (تشفير + تجزئة للخصوصية)
# ==============================================================================

def hash_ip(ip: str) -> str:
    """تشفير IP للحفاظ على الخصوصية مع الاحتفاظ بالقيمة المميزة."""
    return hashlib.sha256(ip.encode()).hexdigest()[:16]

# ==============================================================================
# 3. تسجيل زيارة جديدة
# ==============================================================================

def track_visitor():
    """تسجيل زيارة الزائر في Firebase."""
    try:
        # الحصول على IP
        ip_address = get_client_ip()
        ip_hash = hash_ip(ip_address)
        
        # الحصول على الوقت الحالي بتوقيت الجزائر
        algeria_tz = pytz.timezone('Africa/Algiers')
        visit_time = datetime.now(algeria_tz).isoformat()
        
        # البيانات المراد حفظها
        visit_data = {
            "ip_hash": ip_hash,
            "timestamp": visit_time,
            "user_agent": st.session_state.get("user_agent", "UNKNOWN"),
            "session_id": st.session_state.get("session_id", "UNKNOWN")
        }
        
        # حفظ في Firebase تحت مسار الزوار
        ref = db.reference("visitors")
        ref.push(visit_data)
        
        return True
    except Exception as e:
        print(f"❌ خطأ في تسجيل الزيارة: {e}")
        return False

# ==============================================================================
# 4. الحصول على إحصائيات الزوار
# ==============================================================================

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
        
        # معالجة البيانات
        total_visits = len(visitors)
        unique_ips = len(set(v.get("ip_hash") for v in visitors.values() if v))
        
        # حساب الزيارات اليومية
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
        
        # أحدث الزيارات
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

# ==============================================================================
# 5. عرض لوحة المعلومات (Dashboard)
# ==============================================================================

def show_visitor_dashboard():
    """عرض لوحة معلومات الزوار (للإدارة فقط)."""
    st.markdown("### 📊 لوحة معلومات الزوار")
    
    stats = get_visitor_stats()
    
    if stats:
        # عرض الإحصائيات الرئيسية
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="👥 إجمالي الزيارات",
                value=stats["total_visits"],
                delta=None
            )
        
        with col2:
            st.metric(
                label="🌍 عناوين IP فريدة",
                value=stats["unique_ips"],
                delta=None
            )
        
        with col3:
            st.metric(
                label="📅 زيارات اليوم",
                value=stats["today_visits"],
                delta=None
            )
        
        with col4:
            st.metric(
                label="⏰ الساعة الأكثر نشاطاً",
                value=max(stats["visits_by_hour"].items(), key=lambda x: x[1])[0] if stats["visits_by_hour"] else "---",
                delta=None
            )
        
        # رسم بياني للزيارات بالساعة
        if stats["visits_by_hour"]:
            st.subheader("📈 الزيارات حسب الساعة")
            st.bar_chart(stats["visits_by_hour"])
        
        # أحدث الزيارات
        if stats["recent_visits"]:
            st.subheader("🔔 أحدث الزيارات")
            for visit in stats["recent_visits"]:
                with st.container():
                    col1, col2, col3 = st.columns([2, 3, 2])
                    with col1:
                        st.text(f"**IP Hash:** {visit.get('ip_hash', 'UNKNOWN')[:8]}...")
                    with col2:
                        st.text(f"**الوقت:** {visit.get('timestamp', 'UNKNOWN')}")
                    with col3:
                        st.text(f"**Session:** {visit.get('session_id', 'UNKNOWN')[:8]}...")
    else:
        st.warning("⚠️ لا توجد بيانات زوار حالياً")

# ==============================================================================
# 6. دالة التهيئة
# ==============================================================================

def init_visitor_tracking():
    """تهيئة نظام تتبع الزوار."""
    # تعيين معرف الجلسة إذا لم يكن موجوداً
    if "session_id" not in st.session_state:
        import uuid
        st.session_state["session_id"] = str(uuid.uuid4())
    
    # تسجيل الزيارة
    track_visitor()
