import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Albion Guild CTA Checker", layout="wide")

# --- KẾT NỐI FIREBASE ---
if not firebase_admin._apps:
    try:
        secret_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(secret_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Lỗi kết nối Firebase: {e}")

db = firestore.client()

# --- SIDEBAR: SETTING CONFIG ---
with st.sidebar:
    st.title("⚙️ Cấu hình Hệ thống")
    st.markdown("---")
    
    # Cấu hình API Gemini
    st.subheader("Gemini AI Config")
    gemini_api_key = st.text_input(
        "Nhập Gemini API Key (Free 2.5):",
        type="password",
        help="Lấy key tại Google AI Studio",
        value=st.session_state.get('gemini_api_key', '')
    )
    
    if st.button("Lưu cấu hình"):
        st.session_state['gemini_api_key'] = gemini_api_key
        st.success("Đã lưu API Key!")
    
    st.markdown("---")
    st.info("Phiên bản: 1.0.0\nGuild: Albion GE")

# --- GIAO DIỆN CHÍNH (TABS) ---
st.title("⚔️ Albion Guild CTA Management")

tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual", "👥 Thành Viên", "📊 Tổng Kết"])

# --- TAB 1: MANUAL (Nhập dữ liệu thủ công / Check CTA) ---
with tab_manual:
    st.header("Nhập dữ liệu Check CTA")
    col1, col2 = st.columns([2, 1])
    
    with col1:
        cta_content = st.text_area("Dán danh sách/Hình ảnh nội dung CTA vào đây:", height=300)
        if st.button("Phân tích dữ liệu (AI)"):
            if not gemini_api_key:
                st.warning("Vui lòng cấu hình Gemini API Key ở Sidebar!")
            else:
                st.info("Đang xử lý dữ liệu với Gemini 2.5...")
                # Logic gọi API Gemini sẽ nằm ở đây
    
    with col2:
        st.subheader("Thông tin CTA")
        cta_date = st.date_input("Ngày diễn ra")
        cta_type = st.selectbox("Loại CTA", ["ZvZ", "Ganking", "Dungeon", "Khác"])
        st.button("Lưu vào Firestore")

# --- TAB 2: THÀNH VIÊN (Quản lý danh sách thành viên) ---
with tab_members:
    st.header("Quản lý Thành Viên Guild")
    # Form thêm thành viên mới
    with st.expander("Thêm thành viên mới"):
        new_member = st.text_input("Tên Ingame (IGN)")
        member_role = st.selectbox("Role chính", ["Tank", "Healer", "DPS", "Support"])
        if st.button("Thêm vào danh sách"):
            st.write(f"Đang thêm {new_member} vào Firestore...")

    # Hiển thị bảng danh sách thành viên
    st.subheader("Danh sách hiện tại")
    # Code mẫu hiển thị bảng (Sau này sẽ fetch từ Firestore)
    st.info("Dữ liệu thành viên sẽ được tải từ Firestore tại đây.")

# --- TAB 3: TỔNG KẾT (Báo cáo, thống kê) ---
with tab_summary:
    st.header("Thống kê hoạt động CTA")
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    col_stat1.metric("Tổng CTA tháng", "24", "+2")
    col_stat2.metric("Tỷ lệ tham gia TB", "85%", "5%")
    col_stat3.metric("Thành viên tích cực", "45", "-1")

    st.subheader("Biểu đồ tham gia")
    st.bar_chart({"Thành viên": [10, 20, 15, 25, 30]}) # Biểu đồ mẫu
