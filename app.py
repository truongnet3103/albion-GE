import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
from datetime import datetime

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Albion GE - CTA Checker", layout="wide", page_icon="⚔️")

# --- 2. KHỞI TẠO FIREBASE (KẾT NỐI AN TOÀN) ---
if not firebase_admin._apps:
    try:
        secret_dict = dict(st.secrets["firebase"])
        # Xử lý ký tự xuống dòng trong Private Key từ TOML
        if "\\n" in secret_dict["private_key"]:
            secret_dict["private_key"] = secret_dict["private_key"].replace("\\n", "\n")
        
        cred = credentials.Certificate(secret_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"❌ Lỗi kết nối Firebase: {e}")

db = firestore.client()

# --- 3. SIDEBAR: CẤU HÌNH API & QUẢN LÝ MỐC CTA ---
# Lấy API mặc định từ Secrets nếu có
json_key = st.secrets.get("gemini", {}).get("api_key", "")

with st.sidebar:
    st.title("🛡️ Guild Admin Panel")
    
    # Khu vực đổi API Key (Dành cho Gemini 2.5 Flash Free)
    st.subheader("🔑 AI Configuration")
    active_key = st.text_input(
        "Gemini API Key (2.5 Flash):", 
        type="password", 
        value=st.session_state.get('current_key', json_key),
        help="Dán Key mới vào đây khi Key cũ hết Quota (Lỗi 429)."
    )
    st.session_state['current_key'] = active_key
    
    st.divider()
    
    # Khu vực Quản lý Mốc thời gian CTA
    st.subheader("📅 Quản lý Mốc CTA")
    new_cta_name = st.text_input("Tên mốc mới:", placeholder="VD: 18UTC-01/03")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("✨ Tạo mốc", use_container_width=True):
            if new_cta_name:
                db.collection("cta_events").document(new_cta_name).set({
                    "name": new_cta_name,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "status": "Active"
                })
                st.success("Đã tạo!")
                st.rerun()
    
    # Lấy danh sách mốc từ Firebase
    try:
        cta_docs = db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20).stream()
        cta_list = [d.id for d in cta_docs]
        
        if cta_list:
            selected_cta = st.selectbox("📍 Chọn mốc làm việc:", cta_list)
            
            with col_btn2:
                if st.button("🗑️ Xóa mốc", use_container_width=True):
                    db.collection("cta_events").document(selected_cta).delete()
                    st.warning(f"Đã xóa {selected_cta}")
                    st.rerun()
        else:
            selected_cta = "Chưa có mốc"
            st.info("Hãy tạo mốc CTA đầu tiên.")
    except Exception as e:
        selected_cta = "Lỗi kết nối"
        st.error(f"Lỗi DB: {e}")

# --- 4. GIAO DIỆN CHÍNH (TABS) ---
st.title("⚔️ Albion Guild GE - CTA System")

tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual (AI Check)", "👥 Thành Viên", "📊 Tổng Kết"])

# --- TAB 1: MANUAL (CHỨC NĂNG CHÍNH - CHATBOX STYLE) ---
with tab_manual:
    st.markdown(f"### Đang làm việc tại mốc: `{selected_cta}`")
    
    # Chatbox-style File Uploader
    with st.container(border=True):
        uploaded_file = st.file_uploader("📥 Dán hoặc tải ảnh Party List (Region Access Priority)", type=["jpg", "png", "jpeg"])
        
        if uploaded_file:
            img = Image.open(uploaded_file)
            st.image(img, caption="Ảnh đang chờ xử lý...", width=500)
            
            if st.button("🚀 Phân tích với Gemini 2.5 Flash", type="primary"):
                if not st.session_state.get('current_key'):
                    st.error("❌ Vui lòng nhập API Key ở Sidebar!")
                else:
                    with st.spinner("🤖 AI đang đọc dữ liệu..."):
                        try:
                            # Cấu hình Gemini 2.5 Flash
                            genai.configure(api_key=st.session_state['current_key'])
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            
                            prompt = """
                            Analyze this Albion Online Party List. 
                            Task: Extract Character Name (IGN) and Role.
                            Identify roles by weapon icons: Tank, Healer, Melee, Ranged, Support.
                            Output ONLY a JSON array: [{"name": "Name", "role": "Role"}]
                            Do not include any other text.
                            """
                            
                            response = model.generate_content([prompt, img])
                            
                            # Làm sạch JSON trả về
                            clean_text = response.text.replace('```json', '').replace('```', '').strip()
                            json_match = re.search(r'\[.*\]', clean_text, re.DOTALL)
                            
                            if json_match:
                                st.session_state['raw_data'] = json.loads(json_match.group())
                                st.success("✅ AI đã lọc xong danh sách!")
                            else:
                                st.error("❌ AI không tìm thấy dữ liệu. Hãy thử ảnh rõ hơn.")
                        except Exception as e:
                            if "429" in str(e):
                                st.error("❌ Hết Quota! Hãy thay API Key mới ở Sidebar.")
                            else:
                                st.error(f"❌ Lỗi: {e}")

    # Bảng chỉnh sửa và lưu dữ liệu
    if 'raw_data' in st.session_state:
        st.subheader("🔍 Danh sách lọc được")
        st.info("Bạn có thể chỉnh sửa trực tiếp tên hoặc role nếu AI nhận diện sai.")
        
        edited_list = st.data_editor(
            st.session_state['raw_data'], 
            num_rows="dynamic", 
            key="editor_v3",
            use_container_width=True
        )
        
        if st.button("💾 Xác nhận & Lưu vào Firebase", use_container_width=True):
            if selected_cta == "Chưa có mốc" or selected_cta == "Lỗi kết nối":
                st.error("Vui lòng tạo mốc CTA trước khi lưu!")
            else:
                with st.spinner("Đang đồng bộ dữ liệu..."):
                    try:
                        batch = db.batch()
                        for item in edited_list:
                            # 1. Lưu vào điểm danh buổi CTA
                            att_id = f"{selected_cta}_{item['name']}"
                            att_ref = db.collection("cta_attendance").document(att_id)
                            batch.set(att_ref, {
                                "cta_id": selected_cta,
                                "name": item['name'],
                                "role": item['role'],
                                "timestamp": firestore.SERVER_TIMESTAMP
                            })
                            # 2. Cập nhật Master List Thành viên
                            mem_ref = db.collection("members").document(item['name'])
                            batch.set(mem_ref, {
                                "name": item['name'],
                                "last_role": item['role'],
                                "last_active": firestore.SERVER_TIMESTAMP
                            }, merge=True)
                        
                        batch.commit()
                        st.success(f"🔥 Đã lưu thành công {len(edited_list)} thành viên!")
                        del st.session_state['raw_data']
                    except Exception as e:
                        st.error(f"Lỗi Firebase: {e}")

# --- TAB 2: QUẢN LÝ THÀNH VIÊN ---
with tab_members:
    st.header("👥 Danh sách Thành Viên Master")
    try:
        members_stream = db.collection("members").order_by("name").stream()
        member_data = []
        for m in members_stream:
            d = m.to_dict()
            # Định dạng ngày tháng cho dễ nhìn
            if d.get("last_active"):
                d["last_active"] = d["last_active"].strftime("%Y-%m-%d %H:%M")
            member_data.append(d)
            
        if member_data:
            st.dataframe(member_data, use_container_width=True)
        else:
            st.info("Chưa có thành viên nào trong database.")
    except Exception as e:
        st.error(f"Lỗi tải dữ liệu: {e}")

# --- TAB 3: TỔNG KẾT ---
with tab_summary:
    st.header("📊 Thống kê Hoạt động")
    # Tính năng này sẽ đếm số lần xuất hiện của mỗi Name trong cta_attendance
    if st.button("🔄 Cập nhật Thống kê"):
        st.info("Tính năng tính điểm chuyên cần (Participation) đang được xử lý dữ liệu...")
