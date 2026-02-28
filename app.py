import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re

# --- 1. CẤU HÌNH TRANG ---
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

# --- 3. SIDEBAR (API & MỐC CTA) ---
json_key = st.secrets.get("gemini", {}).get("api_key", "")

with st.sidebar:
    st.title("🛡️ Admin Panel")
    
    st.subheader("🔑 Gemini 2.5 Flash Key")
    # Ô nhập Key để thay đổi nóng khi hết quota
    active_key = st.text_input(
        "Nhập API Key mới tại đây:", 
        type="password", 
        value=st.session_state.get('current_key', json_key),
        help="Sử dụng Gemini 2.5 Flash để có hiệu suất tốt nhất."
    )
    st.session_state['current_key'] = active_key

    st.divider()
    
    st.subheader("📅 Mốc thời gian CTA")
    new_cta = st.text_input("Tên mốc mới (vd: 18UTC-01/03)")
    if st.button("Tạo mốc"):
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
        selected_cta = st.selectbox("Chọn mốc làm việc:", cta_list) if cta_list else "Chưa có mốc"
    except:
        selected_cta = "Lỗi kết nối DB"

# --- 4. GIAO DIỆN CHÍNH ---
tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual (AI)", "👥 Thành Viên", "📊 Tổng Kết"])

# --- TAB 1: MANUAL (CHỨC NĂNG CHÍNH) ---
with tab_manual:
    st.info(f"📍 Đang ghi nhận cho mốc: **{selected_cta}**")
    
    uploaded_file = st.file_uploader("📸 Tải hoặc Dán ảnh Party List", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Ảnh đang chờ xử lý", width=500)
        
        if st.button("🪄 Phân tích với Gemini 2.5 Flash"):
            if not st.session_state.get('current_key'):
                st.error("❌ Vui lòng nhập API Key ở Sidebar!")
            else:
                with st.spinner("🤖 AI Gemini 2.5 đang đọc danh sách..."):
                    try:
                        # Cấu hình Model 2.5 Flash
                        genai.configure(api_key=st.session_state['current_key'])
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        
                        prompt = """
                        Phân tích ảnh Party List Albion Online. 
                        Trích xuất: Character Name (IGN) và Role.
                        Roles: Tank, Healer, Melee, Ranged, Support.
                        Trả về duy nhất định dạng JSON mảng: [{"name": "Tên", "role": "Role"}]
                        """
                        
                        response = model.generate_content([prompt, img])
                        
                        # Làm sạch chuỗi trả về
                        clean_text = response.text.replace('```json', '').replace('```', '').strip()
                        json_match = re.search(r'\[.*\]', clean_text, re.DOTALL)
                        
                        if json_match:
                            st.session_state['raw_data'] = json.loads(json_match.group())
                            st.success("✅ Đã trích xuất xong!")
                        else:
                            st.error("AI không tìm thấy danh sách. Hãy thử ảnh rõ hơn.")
                    except Exception as e:
                        if "429" in str(e):
                            st.error("❌ Hết Quota! Vui lòng thay API Key khác ở Sidebar.")
                        elif "404" in str(e):
                            st.error("❌ Lỗi 404: Model 'gemini-2.5-flash' chưa khả dụng hoặc sai tên. Hãy kiểm tra lại vùng quốc gia của API Key.")
                        else:
                            st.error(f"❌ Lỗi: {e}")

    # Bảng chỉnh sửa và lưu
    if 'raw_data' in st.session_state:
        st.subheader("🔍 Kết quả dự đoán")
        edited_list = st.data_editor(st.session_state['raw_data'], num_rows="dynamic", key="cta_editor_v2")
        
        if st.button("💾 Xác nhận & Lưu Firebase"):
            if selected_cta in ["Chưa có mốc", "
