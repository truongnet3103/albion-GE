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
st.set_page_config(page_title="Albion GE - Admin System", layout="wide", page_icon="⚔️")

# CSS để làm giao diện đẹp hơn
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #ff4b4b; color: white; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #262730; border-radius: 5px 5px 0px 0px; color: white; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; }
    div[data-testid="stExpander"] { border: 1px solid #444; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

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

# --- 3. SIDEBAR: CẤU HÌNH ---
json_key = st.secrets.get("gemini", {}).get("api_key", "")

with st.sidebar:
    st.title("🛡️ GUILD GE ADMIN")
    st.subheader("🔑 AI Configuration")
    active_key = st.text_input("Gemini API Key:", type="password", value=st.session_state.get('current_key', json_key))
    st.session_state['current_key'] = active_key
    
    st.divider()
    st.subheader("📅 Quản lý Mốc Lịch Sử")
    new_cta = st.text_input("Tên mốc mới (vd: 18UTC-01/03)")
    if st.button("✨ Tạo mốc dữ liệu"):
        if new_cta:
            db.collection("cta_events").document(new_cta).set({"name": new_cta, "created_at": firestore.SERVER_TIMESTAMP})
            st.success("Đã tạo mốc lưu trữ!")
            st.rerun()

    try:
        cta_docs = db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20).stream()
        cta_list = [d.id for d in cta_docs]
        selected_cta = st.selectbox("📍 Mốc lưu hiện tại:", cta_list) if cta_list else "Chưa có mốc"
    except:
        selected_cta = "Lỗi kết nối"

# --- 4. GIAO DIỆN CHÍNH ---
tab_manual, tab_members, tab_history = st.tabs(["🚀 CHECK-IN AI", "👥 THÀNH VIÊN & ĐIỂM", "📂 LỊCH SỬ MỐC"])

# --- TAB 1: CHECK-IN AI ---
with tab_manual:
    st.subheader(f"📸 Quét Party List - Mốc: {selected_cta}")
    
    with st.expander("⬆️ Upload hoặc Dán ảnh tại đây", expanded=True):
        uploaded_file = st.file_uploader("", type=["jpg", "png", "jpeg"])
    
    if uploaded_file:
        img = Image.open(uploaded_file)
        st.image(img, caption="Ảnh đang chờ xử lý", use_container_width=True)
        
        if st.button("🪄 CHẠY AI PHÂN TÍCH (GEMINI 2.5 FLASH)", type="primary"):
            with st.spinner("🤖 Đang bóc tách dữ liệu nhân vật..."):
                try:
                    genai.configure(api_key=st.session_state['current_key'])
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = "Extract Character Name (IGN) and Role (Tank, Healer, Melee, Ranged, Support) from image. Return ONLY JSON array: [{'name': '...', 'role': '...'}]"
                    response = model.generate_content([prompt, img])
                    clean_text = response.text.replace('```json', '').replace('```', '').strip()
                    json_match = re.search(r'\[.*\]', clean_text, re.DOTALL)
                    if json_match:
                        st.session_state['raw_data'] = json.loads(json_match.group())
                        st.success("✅ Đã trích xuất xong!")
                except Exception as e:
                    st.error(f"Lỗi: {e}")

    if 'raw_data' in st.session_state:
        st.subheader("🔍 Kiểm tra lại danh sách")
        edited_list = st.data_editor(st.session_state['raw_data'], num_rows="dynamic", use_container_width=True)
        
        if st.button("💾 XÁC NHẬN & CỘNG ĐIỂM CHUYÊN CẦN"):
            if selected_cta == "Chưa có mốc":
                st.error("Vui lòng tạo mốc ở Sidebar trước!")
            else:
                with st.spinner("Đang cập nhật điểm số..."):
                    batch = db.batch()
                    for item in edited_list:
                        # 1. Lưu vào Lịch sử (Để xem lại sau này)
                        att_ref = db.collection("cta_attendance").document(f"{selected_cta}_{item['name']}")
                        batch.set(att_ref, {"cta_id": selected_cta, "name": item['name'], "role": item['role'], "timestamp": firestore.SERVER_TIMESTAMP})
                        
                        # 2. Cập nhật Master List & Cộng dồn điểm
                        member_ref = db.collection("members").document(item['name'])
                        # Dùng Increment của Firestore để cộng dồn số lần tham gia tự động
                        batch.set(member_ref, {
                            "name": item['name'],
                            "last_role": item['role'],
                            "total_participation": firestore.Increment(1),
                            "last_active": firestore.SERVER_TIMESTAMP
                        }, merge=True)
                    
                    batch.commit()
                    st.success(f"🔥 Đã ghi nhận và cộng điểm cho {len(edited_list)} thành viên!")
                    del st.session_state['raw_data']

# --- TAB 2: THÀNH VIÊN & ĐIỂM (CỘNG DỒN) ---
with tab_members:
    st.header("👥 Bảng Điểm Chuyên Cần")
    try:
        members_stream = db.collection("members").order_by("total_participation", direction=firestore.Query.DESCENDING).stream()
        member_data = []
        for m in members_stream:
            d = m.to_dict()
            # Đảm bảo có cột participation nếu thành viên cũ chưa có
            d.setdefault("total_participation", 0)
            member_data.append({
                "Tên Nhân Vật (IGN)": d.get("name"),
                "Tổng Lượt Tham Gia": d.get("total_participation"),
                "Role Cuối": d.get("last_role"),
                "Hoạt Động Cuối": d.get("last_active").strftime("%d/%m/%Y %H:%M") if d.get("last_active") else "N/A"
            })
        
        if member_data:
            df = pd.DataFrame(member_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Xuất Excel bảng điểm
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Tải bảng điểm (CSV)", data=csv, file_name="Diem_Chuyen_Can_Guild.csv", mime="text/csv")
        else:
            st.info("Chưa có thành viên nào.")
    except Exception as e:
        st.error(f"Lỗi: {e}")

# --- TAB 3: LỊCH SỬ MỐC (CHỈ ĐỂ XEM LẠI) ---
with tab_history:
    st.header("📂 Dữ liệu lưu trữ theo mốc")
    view_cta = st.selectbox("Chọn mốc muốn xem lại:", cta_list if 'cta_list' in locals() else [])
    
    if view_cta:
        history_docs = db.collection("cta_attendance").where("cta_id", "==", view_cta).stream()
        h_data = [{"Tên": h.to_dict().get("name"), "Role": h.to_dict().get("role")} for h in history_docs]
        if h_data:
            st.table(h_data)
        else:
            st.write("Mốc này chưa có dữ liệu.")
