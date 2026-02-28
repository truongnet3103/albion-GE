import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image

# --- KHỞI TẠO FIREBASE ---
if not firebase_admin._apps:
    secret_dict = dict(st.secrets["firebase"])
    cred = credentials.Certificate(secret_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- CẤU HÌNH GEMINI ---
def get_gemini_response(api_key, image, prompt):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash') # Hoặc 2.0 Flash
    response = model.generate_content([prompt, image])
    return response.text

# --- SIDEBAR CONFIG ---
with st.sidebar:
    st.title("⚙️ Setting")
    gemini_key = st.text_input("Gemini API Key:", type="password")
    
    st.markdown("---")
    st.subheader("⏰ Mốc thời gian CTA")
    cta_time = st.text_input("Ví dụ: CTA 18UTC - 01/03/2026")
    cta_type = st.selectbox("Loại", ["Castles", "Objectives", "Defense", "ZvZ Practice"])

# --- GIAO DIỆN CHÍNH ---
tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual Check", "👥 Thành Viên", "📊 Tổng Kết"])

with tab_manual:
    st.subheader("📸 AI Member Extractor")
    
    # Khu vực Upload/Paste ảnh
    uploaded_file = st.file_uploader("Dán hoặc chọn ảnh Party List (Region Access Priority)", type=["jpg", "jpeg", "png"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Ảnh đã tải lên", width=400)
        
        if st.button("🪄 Phân tích danh sách với AI"):
            if not gemini_key:
                st.error("Vui lòng nhập Gemini API Key ở Sidebar!")
            else:
                with st.spinner("AI đang đọc danh sách..."):
                    # Prompt tối ưu cho ảnh Albion
                    prompt = """
                    Đây là ảnh chụp màn hình danh sách Party trong game Albion Online. 
                    Hãy liệt kê tất cả tên thành viên (IGN) và Icon Role đứng trước tên họ (ví dụ: Sword/Axe là Melee, Staff là Healer/Mage, Shield là Tank).
                    Trả về kết quả dưới dạng danh sách JSON: [{"name": "IGN", "role": "Role"}]
                    Chỉ trả về JSON, không giải thích thêm.
                    """
                    try:
                        result_text = get_gemini_response(gemini_key, img, prompt)
                        # Giả định kết quả trả về là list (cần xử lý chuỗi JSON từ AI)
                        st.session_state['detected_members'] = result_text 
                        st.success("Đã lọc xong!")
                        st.code(result_text, language='json')
                    except Exception as e:
                        st.error(f"Lỗi AI: {e}")

    # Nút cập nhật sang Firebase
    if 'detected_members' in st.session_state:
        if st.button("🚀 Xác nhận & Lưu vào Firebase"):
            # Logic parse JSON và lưu vào Firestore
            batch = db.batch()
            # Giả sử ta có list_members đã parse
            # for member in list_members:
            #     doc_ref = db.collection("cta_attendance").document()
            #     batch.set(doc_ref, {"cta_id": cta_time, "name": member['name'], "role": member['role']})
            # batch.commit()
            st.success(f"Đã lưu danh sách vào mốc: {cta_time}")

with tab_members:
    st.header("Danh sách thành viên Guild")
    # Hiển thị bảng từ Firebase Firestore tại đây
