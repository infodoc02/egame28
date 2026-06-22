import streamlit as st

st.set_page_config(page_title="InfoDoc - تم التحديث", page_icon="🚀", layout="wide")

# تطبيق تصميم عصري مع أنيميشن
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #1e1b4b 100%);
        font-family: 'Cairo', sans-serif;
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
    }
    
    .container {
        text-align: center;
        animation: fadeInUp 1s ease-out;
    }
    
    .icon {
        font-size: 6rem;
        animation: float 3s ease-in-out infinite;
    }
    
    h1 {
        color: #ffffff;
        font-size: 3rem;
        font-weight: 900;
        margin: 20px 0 10px;
    }
    
    .message {
        color: #f1f5f9;
        font-size: 1.5rem;
        margin-bottom: 30px;
    }
    
    .new-link {
        background: linear-gradient(90deg, #3b82f6, #2563eb);
        color: white;
        padding: 15px 40px;
        border-radius: 50px;
        font-size: 1.4rem;
        font-weight: 700;
        text-decoration: none;
        display: inline-block;
        transition: all 0.3s ease;
        box-shadow: 0 10px 25px rgba(37, 99, 235, 0.4);
        animation: pulse 2s infinite;
    }
    
    .new-link:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 35px rgba(37, 99, 235, 0.6);
    }
    
    @keyframes fadeInUp {
        0% { opacity: 0; transform: translateY(50px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes float {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
    }
    
    @keyframes pulse {
        0%, 100% { box-shadow: 0 10px 25px rgba(37, 99, 235, 0.4); }
        50% { box-shadow: 0 15px 40px rgba(37, 99, 235, 0.7); }
    }
    
    .footer {
        color: #94a3b8;
        margin-top: 40px;
        font-size: 0.9rem;
    }
</style>

<div class="container">
    <div class="icon">🚀</div>
    <h1>InfoDoc</h1>
    <div class="message">
        البوابة القديمة لم تعد في الخدمة <br>
        لقد انتقلنا إلى منصة جديدة كلياً
        رابطها infodoc.streamlit.app
    </div>
    <a href="https://infodoc.streamlit.app" target="_blank" class="new-link">
        ✨ زيارة المنصة الجديدة
    </a>
    <div class="footer">
        © 2025 InfoDoc - جميع الحقوق محفوظة
    </div>
</div>
""", unsafe_allow_html=True)
