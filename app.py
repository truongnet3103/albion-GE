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
        st.error(f"❌ Lỗi Firebase: {e}")

db = firestore.client()

# --- 3. SIDEBAR: API KEY & MỐC CTA ---
# Lấy API mặc định từ JSON Secrets (nếu có)
json_key = st.secrets.get("gemini", {}).get("api_key", "")

with st.sidebar:
    st.title("🛡️ Admin Panel")
    
    st.subheader("🔑 Gemini 1.5 Flash Key")
    active_key = st.text_input(
        "Dán API Key mới tại đây:", 
        type="password", 
        value=st.session_state.get('current_key', json_key),
        help="Khi báo lỗi 429 (Hết Quota), hãy dán Key mới vào đây."
    )
    st.session_state['current_key'] = active_key

    st.divider()
    
    st.subheader("📅 Mốc CTA")
    new_cta = st.text_input("Tạo mốc (vd: 18UTC-01/03)")
    if st.button("Tạo"):
        if new_cta:
            db.collection("cta_events").document(new_cta).set({
                "name": new_cta,
                "created_at": firestore.SERVER_TIMESTAMP
            })
            st.rerun()

    try:
        cta_docs = db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(15).stream()
        cta_list = [d.id for d in cta_docs]
        selected_cta = st.selectbox("Chọn mốc làm việc:", cta_list) if cta_list else "Chưa có mốc"
    except:
        selected_cta = "Lỗi kết nối DB"

# --- 4. GIAO DIỆN CHÍNH ---
tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual (AI)", "👥 Thành Viên", "📊 Tổng Kết"])

with tab_manual:
    st.info(f"📍 Đang check: **{selected_cta}**")
    uploaded_file = st.file_uploader("📸 Tải ảnh Party List", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Ảnh chờ AI đọc", width=450)
        
        if st.button("🪄 Phân tích với Gemini 1.5 Flash"):
            if not st.session_state.get('current_key'):
                st.error("Chưa có API Key!")
            else:
                with st.spinner("Đang đọc dữ liệu..."):
                    try:
                        # Cấu hình Model 1.5 Flash
                        genai.configure(api_key=st.session_state['current_key'])
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        # Prompt cực ngắn để tiết kiệm Token
                        prompt = "Extract IGN and Role (Tank, Healer, Melee, Ranged, Support) from this Albion party list. Return ONLY JSON array: [{'name': '...', 'role': '...'}]"
                        
                        response = model.generate_content([prompt, img])
                        
                        # Làm sạch code JSON
                        clean_text = response.text.replace('```json', '').replace('```', '').strip()
                        json_match = re.search(r'\[.*\]', clean_text, re.DOTALL)
                        
                        if json_match:
                            st.session_state['raw_data'] = json.loads(json_match.group())
                            st.success("✅ Đã đọc xong!")
                        else:
                            st.error("AI không tìm thấy data. Thử ảnh khác rõ hơn.")
                    except Exception as e:
                        if "429" in str(e):
                            st.error("❌ Key này đã hết Quota! Hãy thay Key mới ở Sidebar.")
                        else:
                            st.error(f"❌ Lỗi AI: {e}")

    # Bảng chỉnh sửa và lưu
    if 'raw_data' in st.session_state:
        edited_list = st.data_editor(st.session_state['raw_data'], num_rows="dynamic")
        
        if st.button("💾 Lưu vào Firebase"):
            if selected_cta == "Chưa có mốc":
                st.error("Hãy tạo mốc CTA trước!")
            else:
                batch = db.batch()
                for item in edited_list:
                    # Lưu Attendance
                    att_ref = db.collection("cta_attendance").document(f"{selected_cta}_{item['name']}")
                    batch.set(att_ref, {"cta_id": selected_cta, "name": item['name'], "role": item['role'], "timestamp": firestore.SERVER_TIMESTAMP})
                    # Cập nhật Member Master
                    mem_ref = db.collection("members").document(item['name'])
                    batch.set(mem_ref, {"name": item['name'], "last_role": item['role'], "last_active": firestore.SERVER_TIMESTAMP}, merge=True)
                
                batch.commit()
                st.success("🔥 Đã đồng bộ thành công!")
                del st.session_state['raw_data']

# --- TAB 2 & 3 ---
with tab_members:
    try:
        members = db.collection("members").order_by("name").stream()
        data = [m.to_dict() for m in members]
        if data: st.dataframe(data, use_container_width=True)
    except: st.write("Chưa có dữ liệu.")

with tab_summary:
    st.write("Bảng tổng kết chuyên cần sẽ hiển thị ở đây.")
