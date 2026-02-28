import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
import pandas as pd
from datetime import datetime

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Albion GE - CTA Checker", layout="wide", page_icon="⚔️")

# --- 2. KHỞI TẠO FIREBASE ---
if not firebase_admin._apps:
    try:
        secret_dict = dict(st.secrets["firebase"])
        # Xử lý ký tự xuống dòng trong Private Key từ TOML để chạy trên Streamlit Cloud
        if "\\n" in secret_dict["private_key"]:
            secret_dict["private_key"] = secret_dict["private_key"].replace("\\n", "\n")
        
        cred = credentials.Certificate(secret_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"❌ Lỗi cấu hình Firebase: {e}")

db = firestore.client()

# --- 3. SIDEBAR: CẤU HÌNH HỆ THỐNG & QUẢN LÝ MỐC CTA ---
# Lấy API mặc định từ Secrets (JSON)
json_key = st.secrets.get("gemini", {}).get("api_key", "")

with st.sidebar:
    st.title("🛡️ Guild Admin Panel")
    
    # Cấu hình API Gemini 2.5 Flash
    st.subheader("🔑 AI Configuration")
    active_key = st.text_input(
        "Gemini API Key (2.5 Flash):", 
        type="password", 
        value=st.session_state.get('current_key', json_key),
        help="Thay Key mới tại đây khi Key cũ hết Quota (Lỗi 429)."
    )
    st.session_state['current_key'] = active_key
    
    st.divider()
    
    # Quản lý Mốc thời gian CTA
    st.subheader("📅 Quản lý Mốc CTA")
    new_cta_name = st.text_input("Tên mốc mới:", placeholder="VD: 18UTC-01/03")
    
    col_cta1, col_cta2 = st.columns(2)
    with col_cta1:
        if st.button("✨ Tạo mốc", use_container_width=True):
            if new_cta_name:
                db.collection("cta_events").document(new_cta_name).set({
                    "name": new_cta_name,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "status": "Active"
                })
                st.success("Đã tạo!")
                st.rerun()
    
    # Lấy danh sách mốc từ Firebase để chọn làm việc
    try:
        cta_docs = db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(30).stream()
        cta_list = [d.id for d in cta_docs]
        
        if cta_list:
            selected_cta = st.selectbox("📍 Chọn mốc làm việc:", cta_list)
            
            with col_cta2:
                if st.button("🗑️ Xóa mốc", use_container_width=True):
                    db.collection("cta_events").document(selected_cta).delete()
                    # Xóa luôn các attendance liên quan đến mốc này (tùy chọn)
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

# --- TAB 1: MANUAL (CHỨC NĂNG CHÍNH - NHẬN DIỆN ẢNH) ---
with tab_manual:
    st.markdown(f"### 📍 Đang ghi nhận dữ liệu cho: `{selected_cta}`")
    
    with st.container(border=True):
        uploaded_file = st.file_uploader("📸 Dán hoặc tải ảnh Party List (Region Access Priority)", type=["jpg", "png", "jpeg"])
        
        if uploaded_file:
            img = Image.open(uploaded_file)
            st.image(img, caption="Ảnh đang xử lý...", width=500)
            
            if st.button("🪄 Phân tích với Gemini 2.5 Flash", type="primary", use_container_width=True):
                if not st.session_state.get('current_key'):
                    st.error("❌ Vui lòng nhập API Key ở Sidebar!")
                else:
                    with st.spinner("🤖 AI đang bóc tách tên nhân vật..."):
                        try:
                            # Cấu hình Gemini 2.5 Flash
                            genai.configure(api_key=st.session_state['current_key'])
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            
                            prompt = """
                            Analyze this Albion Online Party List image. 
                            Task: Extract Character Name (IGN) and Role.
                            Role classification:
                            - Tank: Shield icon.
                            - Healer: Green staff/cross icon.
                            - Melee: Sword/Axe/Gloves icon.
                            - Ranged: Bow/Offensive staff icon.
                            - Support: Yellow/White staff icon.
                            Return ONLY a JSON array: [{"name": "Name", "role": "Role"}]
                            Do not include any other text.
                            """
                            
                            response = model.generate_content([prompt, img])
                            
                            # Làm sạch JSON trả về từ AI
                            clean_text = response.text.replace('```json', '').replace('```', '').strip()
                            json_match = re.search(r'\[.*\]', clean_text, re.DOTALL)
                            
                            if json_match:
                                st.session_state['raw_data'] = json.loads(json_match.group())
                                st.success("✅ AI đã hoàn tất trích xuất!")
                            else:
                                st.error("❌ AI không tìm thấy danh sách. Hãy thử ảnh rõ nét hơn.")
                        except Exception as e:
                            if "429" in str(e):
                                st.error("❌ Key này đã hết Quota! Hãy dán Key mới vào Sidebar.")
                            else:
                                st.error(f"❌ Lỗi AI: {e}")

    # Hiển thị bảng kết quả để GM chỉnh sửa trước khi lưu
    if 'raw_data' in st.session_state:
        st.subheader("🔍 Kết quả AI đọc được")
        st.info("Nhấp đúp vào ô để sửa nếu AI nhận diện sai tên hoặc role.")
        
        edited_list = st.data_editor(
            st.session_state['raw_data'], 
            num_rows="dynamic", 
            key="cta_editor_final",
            use_container_width=True
        )
        
        if st.button("💾 Xác nhận & Lưu vào Firebase", use_container_width=True, type="primary"):
            if selected_cta in ["Chưa có mốc", "Lỗi kết nối"]:
                st.error("Vui lòng tạo hoặc chọn một mốc CTA trước khi lưu!")
            else:
                with st.spinner("Đang đồng bộ dữ liệu lên Cloud..."):
                    try:
                        batch = db.batch()
                        for item in edited_list:
                            # 1. Lưu điểm danh vào buổi CTA cụ thể
                            att_id = f"{selected_cta}_{item['name']}"
                            att_ref = db.collection("cta_attendance").document(att_id)
                            batch.set(att_ref, {
                                "cta_id": selected_cta,
                                "name": item['name'],
                                "role": item['role'],
                                "timestamp": firestore.SERVER_TIMESTAMP
                            })
                            # 2. Cập nhật/Thêm mới vào Master List Thành viên
                            mem_ref = db.collection("members").document(item['name'])
                            batch.set(mem_ref, {
                                "name": item['name'],
                                "last_role": item['role'],
                                "last_active": firestore.SERVER_TIMESTAMP
                            }, merge=True)
                        
                        batch.commit()
                        st.success(f"🔥 Đã lưu thành công {len(edited_list)} thành viên!")
                        # Xóa dữ liệu tạm để sẵn sàng cho ảnh tiếp theo
                        del st.session_state['raw_data']
                    except Exception as e:
                        st.error(f"Lỗi lưu Firebase: {e}")

# --- TAB 2: QUẢN LÝ THÀNH VIÊN ---
with tab_members:
    st.header("👥 Danh sách Thành Viên Guild")
    try:
        members_stream = db.collection("members").order_by("name").stream()
        member_data = []
        for m in members_stream:
            d = m.to_dict()
            if d.get("last_active"):
                # Chuyển đổi Firestore Timestamp sang chuỗi ngày tháng
                d["last_active"] = d["last_active"].strftime("%d-%m-%Y %H:%M")
            member_data.append(d)
            
        if member_data:
            df_members = pd.DataFrame(member_data)
            st.dataframe(df_members, use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có thành viên nào trong database.")
    except Exception as e:
        st.error(f"Lỗi tải dữ liệu: {e}")

# --- TAB 3: TỔNG KẾT (TÍNH TOÁN CHUYÊN CẦN) ---
with tab_summary:
    st.header("📊 Bảng Tổng Kết Chuyên Cần")
    
    if st.button("🔄 Cập nhật & Tính toán dữ liệu", use_container_width=True):
        with st.spinner("Đang quét toàn bộ database..."):
            try:
                # 1. Đếm tổng số buổi CTA đã tổ chức
                all_ctas = db.collection("cta_events").stream()
                total_cta_count = len([c for c in all_ctas])
                
                # 2. Lấy toàn bộ dữ liệu điểm danh
                attendance_stream = db.collection("cta_attendance").stream()
                att_list = [a.to_dict() for a in attendance_stream]
                
                if att_list:
                    df_att = pd.DataFrame(att_list)
                    
                    # Group by Name để tính toán
                    summary_df = df_att.groupby('name').agg({
                        'cta_id': 'count',  # Đếm số lần tham gia
                        'role': lambda x: x.mode()[0] if not x.mode().empty else "N/A" # Role chơi nhiều nhất
                    }).reset_index()
                    
                    summary_df.columns = ['Tên (IGN)', 'Số buổi tham gia', 'Role hay chơi']
                    
                    # Tính % chuyên cần dựa trên tổng số buổi đã tạo
                    if total_cta_count > 0:
                        summary_df['Tỉ lệ tham gia (%)'] = (summary_df['Số buổi tham gia'] / total_cta_count * 100).round(1)
                    else:
                        summary_df['Tỉ lệ tham gia (%)'] = 0.0
                    
                    # Sắp xếp từ cao xuống thấp
                    summary_df = summary_df.sort_values(by='Số buổi tham gia', ascending=False)
                    
                    st.success(f"📌 Đã tổ chức tổng cộng: **{total_cta_count}** buổi CTA.")
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)
                    
                    # Nút tải file CSV
                    csv_data = summary_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 Tải Bảng Tổng Kết (Excel/CSV)",
                        data=csv_data,
                        file_name=f"CTA_Summary_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.warning("Chưa có dữ liệu điểm danh nào để thống kê.")
            except Exception as e:
                st.error(f"Lỗi tính toán: {e}")
