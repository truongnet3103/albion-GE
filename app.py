import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Albion GE - CTA Checker", layout="wide")

# --- 2. KHỞI TẠO FIREBASE (TỪ SECRETS) ---
if not firebase_admin._apps:
    try:
        secret_dict = dict(st.secrets["firebase"])
        # Đảm bảo private_key xử lý đúng xuống dòng
        if "\\n" in secret_dict["private_key"]:
            secret_dict["private_key"] = secret_dict["private_key"].replace("\\n", "\n")
        
        cred = credentials.Certificate(secret_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"❌ Lỗi cấu hình Secrets: {e}")

# Kết nối database
try:
    db = firestore.client()
except Exception as e:
    st.error(f"❌ Không thể khởi tạo Firestore Client: {e}")

# --- 3. CẤU HÌNH API AI (LINH HOẠT) ---
# Lấy key mặc định từ secrets (nếu bạn có đặt trong mục [gemini] api_key = "...")
json_key = st.secrets.get("gemini", {}).get("api_key", "")

with st.sidebar:
    st.title("🛡️ Guild Admin Panel")
    
    # Khu vực đổi API Key nhanh (Cái này bạn muốn để thay khi hết request)
    st.subheader("🔑 Gemini API Key")
    active_key = st.text_input(
        "Nhập API Key mới tại đây:", 
        type="password", 
        value=st.session_state.get('current_key', json_key),
        help="Dán Key mới vào đây nếu Key cũ báo lỗi Quota (429)."
    )
    st.session_state['current_key'] = active_key

    st.divider()
    
    # Khu vực Quản lý Mốc CTA
    st.subheader("📅 Quản lý Mốc CTA")
    new_cta = st.text_input("Tên mốc mới (vd: 18UTC-01-03)")
    if st.button("Tạo mốc mới"):
        if new_cta:
            try:
                db.collection("cta_events").document(new_cta).set({
                    "name": new_cta,
                    "created_at": firestore.SERVER_TIMESTAMP
                })
                st.success(f"✅ Đã tạo mốc {new_cta}")
                st.rerun()
            except Exception as e:
                st.error(f"Lỗi tạo mốc: {e}")

    # Chọn mốc làm việc
    selected_cta = "Chưa có mốc"
    try:
        cta_docs = db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20).stream()
        cta_list = [d.id for d in cta_docs]
        if cta_list:
            selected_cta = st.selectbox("Làm việc với mốc:", cta_list)
        else:
            st.warning("⚠️ Hãy tạo mốc CTA đầu tiên ở trên!")
    except Exception as e:
        st.error(f"⚠️ Lỗi đọc mốc CTA từ DB. Hãy kiểm tra Rules trên Firebase!")

# --- 4. GIAO DIỆN CHÍNH ---
st.title("⚔️ Albion GE - CTA Checker")
tab_manual, tab_members, tab_summary = st.tabs(["📝 Manual (AI Check)", "👥 Thành Viên", "📊 Tổng Kết"])

# --- TAB 1: MANUAL (CHỨC NĂNG CHÍNH - CHATBOX STYLE) ---
with tab_manual:
    st.info(f"📍 Đang ghi nhận dữ liệu cho mốc: **{selected_cta}**")
    
    # Khu vực Upload/Paste ảnh
    uploaded_file = st.file_uploader("📸 Dán ảnh hoặc tải ảnh Party List (Region Access Priority)", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Ảnh đang xử lý", width=500)
        
        if st.button("🪄 Chạy AI Phân Tích Ảnh"):
            if not st.session_state.get('current_key'):
                st.error("❌ Chưa có API Key! Hãy nhập vào ô ở Sidebar bên trái.")
            else:
                with st.spinner("🤖 AI đang đọc tên và role..."):
                    try:
                        genai.configure(api_key=st.session_state['current_key'])
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        prompt = """
                        Đây là ảnh Party List trong game Albion Online. 
                        Hãy trích xuất danh sách gồm: Tên nhân vật (IGN) và Role.
                        Role dựa trên icon vũ khí: Tank (Khiên), Healer (Gậy xanh), Melee (Kiếm/Rìu), Ranged (Cung/Gậy phép), Support (Gậy vàng/trắng).
                        Trả về DUY NHẤT định dạng JSON mảng: [{"name": "Tên", "role": "Role"}]
                        Không giải thích gì thêm.
                        """
                        
                        response = model.generate_content([prompt, img])
                        
                        # Sử dụng Regex để lọc chuỗi JSON từ kết quả trả về của AI
                        json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                        if json_match:
                            st.session_state['raw_data'] = json.loads(json_match.group())
                            st.success("✅ AI đã đọc xong! Vui lòng kiểm tra lại bảng bên dưới.")
                        else:
                            st.error("AI không trả về định dạng đúng. Hãy thử lại hoặc dùng ảnh rõ hơn.")
                    except Exception as e:
                        st.error(f"❌ Lỗi AI: {e}. Nếu báo lỗi 429 hoặc Quota, hãy đổi API Key ở Sidebar!")

    # Hiển thị bảng để sửa lỗi và lưu
    if 'raw_data' in st.session_state:
        st.subheader("🔍 Kết quả AI dự đoán")
        st.write("Bạn có thể click vào ô để sửa nếu AI đọc sai tên hoặc role:")
        edited_list = st.data_editor(st.session_state['raw_data'], num_rows="dynamic", key="data_editor_table")
        
        if st.button("💾 Xác nhận & Lưu toàn bộ vào Firebase"):
            if selected_cta == "Chưa có mốc" or selected_cta == "Lỗi kết nối DB":
                st.error("Vui lòng tạo hoặc chọn mốc CTA trước khi lưu!")
            else:
                with st.spinner("Đang đồng bộ dữ liệu..."):
                    try:
                        batch = db.batch()
                        for item in edited_list:
                            # 1. Lưu vào điểm danh buổi CTA đó
                            att_id = f"{selected_cta}_{item['name']}"
                            att_ref = db.collection("cta_attendance").document(att_id)
                            batch.set(att_ref, {
                                "cta_id": selected_cta,
                                "name": item['name'],
                                "role": item['role'],
                                "timestamp": firestore.SERVER_TIMESTAMP
                            })
                            
                            # 2. Cập nhật vào Master List Thành viên (Để sau này xem ai còn trong guild)
                            mem_ref = db.collection("members").document(item['name'])
                            batch.set(mem_ref, {
                                "name": item['name'],
                                "last_role": item['role'],
                                "last_active": firestore.SERVER_TIMESTAMP
                            }, merge=True)
                        
                        batch.commit()
                        st.success(f"🔥 Đã lưu thành công {len(edited_list)} người vào Firebase!")
                        # Xóa dữ liệu tạm sau khi lưu thành công
                        del st.session_state['raw_data']
                    except Exception as e:
                        st.error(f"Lỗi khi lưu vào Firebase: {e}")

# --- TAB 2: THÀNH VIÊN ---
with tab_members:
    st.header("👥 Danh sách Thành Viên Master")
    try:
        members_stream = db.collection("members").order_by("name").stream()
        member_data = []
        for m in members_stream:
            d = m.to_dict()
            # Format lại thời gian hiển thị cho dễ nhìn
            if "last_active" in d and d["last_active"]:
                d["last_active"] = d["last_active"].strftime("%Y-%m-%d %H:%M")
            member_data.append(d)
            
        if member_data:
            st.dataframe(member_data, use_container_width=True)
        else:
            st.info("Chưa có dữ liệu thành viên nào.")
    except Exception as e:
        st.error(f"Không thể tải danh sách thành viên: {e}")

# --- TAB 3: TỔNG KẾT ---
with tab_summary:
    st.header("📊 Thống kê Hoạt động")
    st.write("Phần này sẽ hiển thị tổng số buổi CTA mà mỗi thành viên tham gia (Sẽ sớm cập nhật).")
