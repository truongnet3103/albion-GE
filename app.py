import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re

# --- 1. CONFIG TRANG ---
st.set_page_config(page_title="Albion GE - CTA Checker", layout="wide")

# --- 2. KHỞI TẠO FIREBASE ---
if not firebase_admin._apps:
    try:
        secret_dict = dict(st.secrets["firebase"])
        if "\\n" in secret_dict["private_key"]:
            secret_dict["private_key"] = secret_dict["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(secret_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"❌ Lỗi Secrets Firebase: {e}")

db = firestore.client()

# --- 3. SIDEBAR (QUẢN LÝ API & MỐC CTA) ---
json_key = st.secrets.get("gemini", {}).get("api_key", "")

with st.sidebar:
    st.title("🛡️ Guild Admin Panel")
    
    st.subheader("🔑 Gemini API Key (Free 2.0)")
    active_key = st.text_input(
        "Nhập API Key mới:", 
        type="password", 
        value=st.session_state.get('current_key', json_key),
        help="Dán Key mới vào đây nếu Key cũ hết lượt dùng (Quota 429)."
    )
    st.session_state['current_key'] = active_key

    st.divider()
    
    st.subheader("📅 Quản lý Mốc CTA")
    new_cta = st.text_input("Tên mốc mới (vd: 18UTC-01-03)")
    if st.button("Tạo mốc mới"):
        if new_cta:
            db.collection("cta_events").document(new_cta).set({
                "name": new_cta,
                "created_at": firestore.SERVER_TIMESTAMP
            })
            st.success(f"✅ Đã tạo mốc {new_cta}")
            st.rerun()

    # Chọn mốc làm việc
    try:
        cta_docs = db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20).stream()
        cta_list = [d.id for d in cta_docs]
        if cta_list:
            selected_cta = st.selectbox("Làm việc với mốc:", cta_list)
        else:
            selected_cta = "Chưa có mốc"
    except:
        selected_cta = "Lỗi kết nối DB"

# --- 4. GIAO DIỆN CHÍNH ---
st.title("⚔️ Albion GE - CTA Checker")
tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual (AI Check)", "👥 Thành Viên", "📊 Tổng Kết"])

# --- TAB 1: MANUAL (CHỨC NĂNG CHÍNH) ---
with tab_manual:
    st.info(f"📍 Đang ghi nhận cho mốc: **{selected_cta}**")
    
    uploaded_file = st.file_uploader("📸 Tải ảnh hoặc Dán ảnh Party List (Region Access Priority)", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Ảnh đang chờ xử lý", width=500)
        
        if st.button("🪄 Chạy AI Phân Tích (Gemini 2.0 Flash)"):
            if not st.session_state.get('current_key'):
                st.error("❌ Vui lòng nhập API Key ở Sidebar!")
            else:
                with st.spinner("🤖 AI đang đọc danh sách thành viên..."):
                    try:
                        # Cấu hình AI
                        genai.configure(api_key=st.session_state['current_key'])
                        model = genai.GenerativeModel('gemini-2.0-flash') # Dùng bản 2.0 ổn định nhất
                        
                        prompt = """
                        Đây là ảnh Party List từ game Albion Online. 
                        Nhiệm vụ: Trích xuất chính xác Tên nhân vật (IGN) và Role.
                        Phân loại Role dựa trên biểu tượng vũ khí:
                        - Tank: Biểu tượng Khiên (Shield).
                        - Healer: Biểu tượng Gậy xanh lá/Thánh giá.
                        - Melee: Biểu tượng Kiếm/Rìu/Găng tay.
                        - Ranged: Biểu tượng Cung/Gậy phép công.
                        - Support: Biểu tượng Gậy vàng/Trượng.
                        Trả về duy nhất định dạng JSON mảng: [{"name": "Tên", "role": "Role"}]
                        """
                        
                        response = model.generate_content([prompt, img])
                        
                        # Làm sạch chuỗi trả về (xóa các ký tự thừa như ```json)
                        clean_text = response.text.replace('```json', '').replace('```', '').strip()
                        json_match = re.search(r'\[.*\]', clean_text, re.DOTALL)
                        
                        if json_match:
                            st.session_state['raw_data'] = json.loads(json_match.group())
                            st.success("✅ Đã trích xuất xong! Hãy kiểm tra lại bảng bên dưới.")
                        else:
                            st.error("AI không nhận diện được danh sách. Hãy thử ảnh rõ nét hơn.")
                    except Exception as e:
                        st.error(f"❌ Lỗi AI: {e}")

    # Bảng chỉnh sửa và lưu dữ liệu
    if 'raw_data' in st.session_state:
        st.subheader("🔍 Kết quả dự đoán")
        edited_list = st.data_editor(st.session_state['raw_data'], num_rows="dynamic", key="cta_editor")
        
        if st.button("💾 Xác nhận & Đồng bộ Firebase"):
            if selected_cta in ["Chưa có mốc", "Lỗi kết nối DB"]:
                st.error("Vui lòng tạo mốc CTA trước khi lưu!")
            else:
                with st.spinner("Đang lưu dữ liệu..."):
                    try:
                        batch = db.batch()
                        for item in edited_list:
                            # 1. Lưu điểm danh
                            att_id = f"{selected_cta}_{item['name']}"
                            att_ref = db.collection("cta_attendance").document(att_id)
                            batch.set(att_ref, {
                                "cta_id": selected_cta,
                                "name": item['name'],
                                "role": item['role'],
                                "timestamp": firestore.SERVER_TIMESTAMP
                            })
                            # 2. Cập nhật Master List
                            mem_ref = db.collection("members").document(item['name'])
                            batch.set(mem_ref, {
                                "name": item['name'],
                                "last_role": item['role'],
                                "last_active": firestore.SERVER_TIMESTAMP
                            }, merge=True)
                        
                        batch.commit()
                        st.success(f"🔥 Đã lưu {len(edited_list)} thành viên vào Firebase!")
                        del st.session_state['raw_data']
                    except Exception as e:
                        st.error(f"Lỗi Firebase: {e}")

# --- TAB 2: THÀNH VIÊN ---
with tab_members:
    st.header("👥 Danh sách Thành Viên Master")
    try:
        members_stream = db.collection("members").order_by("name").stream()
        member_list = [m.to_dict() for m in members_stream]
        if member_list:
            st.dataframe(member_list, use_container_width=True)
        else:
            st.info("Chưa có dữ liệu thành viên.")
    except:
        st.error("Không thể tải danh sách từ Firebase.")

# --- TAB 3: TỔNG KẾT ---
with tab_summary:
    st.header("📊 Thống kê")
    st.write("Dữ liệu chuyên cần sẽ được tổng hợp tại đây.")
