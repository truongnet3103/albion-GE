import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re

# --- 1. KHỞI TẠO FIREBASE ---
if not firebase_admin._apps:
    secret_dict = dict(st.secrets["firebase"])
    cred = credentials.Certificate(secret_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- 2. HÀM XỬ LÝ AI ---
def process_with_gemini(api_key, image):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = """
        Phân tích ảnh Party List Albion Online này. 
        Trích xuất danh sách gồm: Tên nhân vật (IGN) và Role (Dựa vào icon vũ khí: Tank, Healer, Melee DPS, Ranged DPS, Support).
        Trả về DUY NHẤT định dạng JSON mảng: [{"name": "Tên", "role": "Role"}]
        """
        response = model.generate_content([prompt, image])
        # Dùng regex để lọc lấy phần JSON trong trường hợp AI trả kèm text thừa
        json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return []
    except Exception as e:
        st.error(f"Lỗi AI: {e}")
        return []

# --- 3. SIDEBAR: CẤU HÌNH & QUẢN LÝ MỐC CTA ---
with st.sidebar:
    st.title("🛡️ Guild Admin")
    
    # Cấu hình API Key
    gemini_key = st.text_input("Gemini API Key:", type="password", value=st.session_state.get('gemini_key', ''))
    if gemini_key:
        st.session_state['gemini_key'] = gemini_key

    st.divider()
    st.subheader("📅 Quản lý Mốc CTA")
    
    # Thêm mốc CTA mới
    new_cta_name = st.text_input("Tên mốc mới (vd: 18UTC-01/03)")
    if st.button("Tạo mốc mới"):
        if new_cta_name:
            db.collection("cta_events").document(new_cta_name).set({
                "created_at": firestore.SERVER_TIMESTAMP,
                "status": "active"
            })
            st.success("Đã tạo!")
            st.rerun()

    # Chọn mốc CTA hiện có để làm việc
    cta_docs = db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).stream()
    cta_list = [d.id for d in cta_docs]
    selected_cta = st.selectbox("Chọn mốc CTA để check:", cta_list)

# --- 4. GIAO DIỆN CHÍNH ---
tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual Check", "👥 Thành Viên", "📊 Tổng Kết"])

with tab_manual:
    st.header(f"📍 Đang check cho: {selected_cta}")
    
    # Chatbox-style Upload
    uploaded_file = st.file_uploader("Dán ảnh hoặc chọn ảnh Party List...", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Ảnh đang xử lý", width=300)
        
        if st.button("🪄 Chạy AI & Trích xuất"):
            if not st.session_state.get('gemini_key'):
                st.warning("Vui lòng nhập API Key ở Sidebar!")
            else:
                with st.spinner("AI đang đọc dữ liệu..."):
                    results = process_with_gemini(st.session_state['gemini_key'], img)
                    st.session_state['temp_list'] = results

    # Hiển thị kết quả lọc được và cho phép chỉnh sửa trước khi lưu
    if 'temp_list' in st.session_state and st.session_state['temp_list']:
        st.subheader("✅ Kết quả lọc")
        edited_data = st.data_editor(st.session_state['temp_list'], num_rows="dynamic")
        
        if st.button("💾 Xác nhận & Lưu vào Firebase"):
            batch = db.batch()
            for member in edited_data:
                # Lưu vào attendance của mốc CTA đã chọn
                doc_id = f"{selected_cta}_{member['name']}"
                doc_ref = db.collection("cta_attendance").document(doc_id)
                batch.set(doc_ref, {
                    "cta_id": selected_cta,
                    "name": member['name'],
                    "role": member['role'],
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                
                # Đồng thời cập nhật/tạo mới thông tin trong danh sách Thành Viên (Master List)
                member_ref = db.collection("members").document(member['name'])
                batch.set(member_ref, {
                    "name": member['name'],
                    "last_role": member['role'],
                    "last_active": firestore.SERVER_TIMESTAMP
                }, merge=True)
                
            batch.commit()
            st.success(f"Đã cập nhật {len(edited_data)} thành viên vào mốc {selected_cta}!")
            del st.session_state['temp_list']

# --- CÁC TAB CÒN LẠI ---
with tab_members:
    st.header("Danh sách Thành Viên")
    members = db.collection("members").stream()
    member_data = [m.to_dict() for m in members]
    if member_data:
        st.table(member_data)

with tab_summary:
    st.write("Dữ liệu tổng hợp sẽ hiển thị ở đây.")
