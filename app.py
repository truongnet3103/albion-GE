import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re

# --- 1. KHỞI TẠO FIREBASE ---
if not firebase_admin._apps:
    try:
        secret_dict = dict(st.secrets["firebase"])
        cred = credentials.Certificate(secret_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Lỗi cấu hình Secrets: {e}")

db = firestore.client()

# --- 2. CẤU HÌNH API AI (ƯU TIÊN LINH HOẠT) ---
# Lấy key mặc định từ secrets nếu có
json_key = st.secrets.get("gemini", {}).get("api_key", "")

with st.sidebar:
    st.title("🛡️ Guild Admin Panel")
    
    # Khu vực đổi API Key nhanh
    st.subheader("🔑 AI API Key")
    active_key = st.text_input(
        "Gemini API Key:", 
        type="password", 
        value=st.session_state.get('current_key', json_key),
        help="Dán Key mới vào đây nếu Key cũ hết lượt dùng."
    )
    st.session_state['current_key'] = active_key

    st.divider()
    
    # Khu vực Quản lý Mốc CTA
    st.subheader("📅 Quản lý Mốc CTA")
    new_cta = st.text_input("Tên mốc mới (vd: 18UTC-01/03)")
    if st.button("Tạo mốc"):
        if new_cta:
            db.collection("cta_events").document(new_cta).set({
                "name": new_cta,
                "created_at": firestore.SERVER_TIMESTAMP
            })
            st.success(f"Đã tạo mốc {new_cta}")
            st.rerun()

    # Chọn mốc làm việc
    try:
        cta_docs = db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(10).stream()
        cta_list = [d.id for d in cta_docs]
        if cta_list:
            selected_cta = st.selectbox("Làm việc với mốc:", cta_list)
        else:
            selected_cta = "Chưa có mốc"
            st.warning("Hãy tạo mốc CTA đầu tiên!")
    except:
        selected_cta = "Lỗi kết nối DB"

# --- 3. GIAO DIỆN CHÍNH ---
st.title("⚔️ Albion GE - CTA Checker")
tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual (AI)", "👥 Thành Viên", "📊 Tổng Kết"])

# --- TAB 1: MANUAL (CHỨC NĂNG CHÍNH) ---
with tab_manual:
    st.info(f"📍 Đang ghi nhận dữ liệu cho mốc: **{selected_cta}**")
    
    # Chatbox Upload
    uploaded_file = st.file_uploader("📸 Dán hoặc tải ảnh Party List (Region Access Priority)", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Ảnh chờ xử lý", width=400)
        
        if st.button("🪄 Chạy AI Phân Tích"):
            if not st.session_state['current_key']:
                st.error("Chưa có API Key! Hãy nhập ở Sidebar.")
            else:
                with st.spinner("AI đang đọc tên thành viên..."):
                    try:
                        genai.configure(api_key=st.session_state['current_key'])
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        prompt = "Extract list of players and their roles (Tank, Healer, Melee, Ranged, Support) from this Albion Online party list. Return ONLY JSON: [{'name': 'IGN', 'role': 'Role'}]"
                        response = model.generate_content([prompt, img])
                        
                        # Parse JSON từ kết quả AI
                        json_str = re.search(r'\[.*\]', response.text, re.DOTALL).group()
                        st.session_state['raw_data'] = json.loads(json_str)
                    except Exception as e:
                        st.error(f"Lỗi xử lý: {e}. Thử đổi API Key khác ở Sidebar!")

    # Hiển thị và lưu dữ liệu
    if 'raw_data' in st.session_state:
        st.subheader("🔍 Kết quả AI đọc được")
        st.write("Bạn có thể sửa trực tiếp vào bảng dưới đây:")
        edited_list = st.data_editor(st.session_state['raw_data'], num_rows="dynamic", key="editor")
        
        if st.button("💾 Xác nhận & Lưu về Firebase"):
            batch = db.batch()
            for item in edited_list:
                # 1. Lưu vào danh sách tham gia CTA
                att_ref = db.collection("cta_attendance").document(f"{selected_cta}_{item['name']}")
                batch.set(att_ref, {
                    "cta_id": selected_cta,
                    "name": item['name'],
                    "role": item['role'],
                    "time": firestore.SERVER_TIMESTAMP
                })
                # 2. Cập nhật vào Master List Thành viên
                mem_ref = db.collection("members").document(item['name'])
                batch.set(mem_ref, {
                    "name": item['name'],
                    "last_role": item['role'],
                    "last_seen": firestore.SERVER_TIMESTAMP
                }, merge=True)
            
            batch.commit()
            st.success(f"🔥 Đã đồng bộ {len(edited_list)} thành viên vào Firebase!")
            del st.session_state['raw_data']

# --- TAB 2: THÀNH VIÊN ---
with tab_members:
    st.header("👥 Danh sách Thành Viên Guild")
    try:
        members = db.collection("members").order_by("name").stream()
        member_list = [m.to_dict() for m in members]
        if member_list:
            st.dataframe(member_list, use_container_width=True)
        else:
            st.info("Chưa có thành viên nào trong dữ liệu.")
    except Exception as e:
        st.error(f"Không thể tải danh sách: {e}")

# --- TAB 3: TỔNG KẾT ---
with tab_summary:
    st.header("📊 Thống kê CTA")
    st.write("Tính năng đang phát triển: Tính điểm chuyên cần (Participation %)...")
