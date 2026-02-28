import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
import pandas as pd
from datetime import datetime

# --- 1. CẤU HÌNH GIAO DIỆN ---
st.set_page_config(page_title="GE Guild Admin - Pro", layout="wide", page_icon="🛡️")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .stTabs [data-baseweb="tab-list"] { background-color: #161b22; padding: 10px; border-radius: 10px; }
    .stTabs [aria-selected="true"] { background-color: #238636 !important; }
    div[data-testid="stMetric"] { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. KẾT NỐI FIREBASE (ĐẢM BẢO KHÔNG MẤT DATA) ---
if not firebase_admin._apps:
    try:
        sd = dict(st.secrets["firebase"])
        if "\\n" in sd["private_key"]: sd["private_key"] = sd["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(sd)
        firebase_admin.initialize_app(cred)
    except Exception as e: st.error(f"Lỗi Firebase: {e}")

db = firestore.client()

# --- 3. SIDEBAR CỐ ĐỊNH ---
with st.sidebar:
    st.title("🛡️ GE GUILD PANEL")
    
    # Check API Gemini 2.5 Flash
    st.subheader("🔑 AI Configuration")
    api_key = st.text_input("Gemini Key:", type="password", value=st.session_state.get('cur_key', st.secrets.get("gemini", {}).get("api_key", "")))
    st.session_state['cur_key'] = api_key
    if st.button("🔍 Kiểm tra API"):
        try:
            genai.configure(api_key=api_key)
            m = genai.GenerativeModel('gemini-2.5-flash')
            m.generate_content("hi", generation_config={"max_output_tokens": 1})
            st.success("✅ API OK")
        except: st.error("❌ Key Lỗi/Hết Quota")

    st.divider()
    
    # Quản lý Chỉ tiêu
    target_cta = st.number_input("Chỉ tiêu (lượt/tháng):", min_value=1, value=10)

    st.divider()
    
    # QUẢN LÝ MỐC (KHÔNG ĐƯỢC MẤT)
    st.subheader("📅 Quản lý Mốc CTA")
    new_m = st.text_input("Tạo mốc mới (VD: 18UTC-01/03):")
    if st.button("✨ Xác nhận Tạo Mốc"):
        if new_m:
            db.collection("cta_events").document(new_m).set({
                "name": new_m, 
                "ts": firestore.SERVER_TIMESTAMP
            })
            st.success(f"Đã tạo mốc {new_m}")
            st.rerun()

    # Lấy danh sách mốc từ DB
    try:
        cta_docs = db.collection("cta_events").order_by("ts", direction=firestore.Query.DESCENDING).limit(30).stream()
        cta_list = [d.id for d in cta_docs]
        sel_cta = st.selectbox("📌 Chọn mốc làm việc:", cta_list) if cta_list else "Chưa có mốc"
    except:
        sel_cta = "Lỗi DB"

# --- 4. GIAO DIỆN CHÍNH ---
t_check, t_members, t_summary = st.tabs(["🚀 QUÉT ẢNH AI", "👥 DANH SÁCH THÀNH VIÊN", "📊 TỔNG KẾT CHI TIẾT"])

# --- TAB 1: QUÉT ẢNH AI ---
with t_check:
    st.subheader(f"📸 Ghi nhận Party List mốc: `{sel_cta}`")
    up = st.file_uploader("Upload ảnh tại đây", type=["jpg", "png", "jpeg"])
    
    if up:
        img = Image.open(up)
        st.image(img, width=400)
        if st.button("🪄 CHẠY AI SCAN", type="primary"):
            with st.spinner("Đang đọc ảnh..."):
                try:
                    genai.configure(api_key=st.session_state['cur_key'])
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = "Return JSON array: [{'name': 'IGN', 'role': 'Tank/Healer/Melee/Ranged/Support'}]"
                    res = model.generate_content([prompt, img])
                    clean = re.search(r'\[.*\]', res.text.replace('```json', '').replace('```', ''), re.DOTALL)
                    if clean:
                        st.session_state['temp_data'] = json.loads(clean.group())
                        st.success("Xong! Kiểm tra bảng bên dưới.")
                except Exception as e: st.error(f"Lỗi: {e}")

    if 'temp_data' in st.session_state:
        edited = st.data_editor(st.session_state['temp_data'], num_rows="dynamic", use_container_width=True)
        if st.button("💾 XÁC NHẬN LƯU VĨNH VIỄN"):
            if sel_cta in ["Chưa có mốc", "Lỗi DB"]:
                st.error("Bạn phải tạo mốc ở Sidebar trước!")
            else:
                batch = db.batch()
                for i in edited:
                    # 1. Lưu vào attendance (Lịch sử mốc)
                    att_ref = db.collection("cta_attendance").document(f"{sel_cta}_{i['name']}")
                    batch.set(att_ref, {"cta_id": sel_cta, "name": i['name'], "role": i['role'], "ts": firestore.SERVER_TIMESTAMP})
                    
                    # 2. Cộng điểm Master Member
                    m_ref = db.collection("members").document(i['name'])
                    batch.set(m_ref, {"name": i['name'], "count": firestore.Increment(1)}, merge=True)
                    
                    # 3. Lưu lịch sử Role để tính toán
                    role_ref = m_ref.collection("role_history").document()
                    batch.set(role_ref, {"role": i['role'], "ts": firestore.SERVER_TIMESTAMP, "cta_id": sel_cta})
                
                batch.commit()
                st.success("🔥 Đã đồng bộ lên Cloud thành công!")
                del st.session_state['temp_data']
                st.rerun()

# --- TAB 2: DANH SÁCH THÀNH VIÊN ---
with t_members:
    st.subheader("👥 Bảng Điểm Guild (Dữ liệu Cloud)")
    m_docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    m_data = []
    for m in m_docs:
        d = m.to_dict()
        cnt = d.get("count", 0)
        m_data.append({
            "IGN": d.get("name"),
            "Tổng Lượt": cnt,
            "Chuyên Cần": "✅ ĐẠT" if cnt >= target_cta else "❌ CHƯA ĐẠT"
        })
    if m_data:
        st.dataframe(pd.DataFrame(m_data), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có thành viên nào. Hãy quét ảnh ở Tab 1.")

# --- TAB 3: TỔNG KẾT CHI TIẾT (YÊU CẦU QUAN TRỌNG) ---
with t_summary:
    st.subheader("📊 Phân tích Chi tiết & Copy Báo cáo")
    all_names = [m['IGN'] for m in m_data] if 'm_data' in locals() and m_data else []
    target = st.selectbox("Chọn thành viên để xem chi tiết:", all_names)
    
    if target:
        # Lấy data Master
        m_info = db.collection("members").document(target).get().to_dict()
        # Lấy chi tiết Role từ sub-collection
        r_docs = db.collection("members").document(target).collection("role_history").stream()
        r_list = [r.to_dict()['role'] for r in r_docs]
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.metric("Tổng tham gia", f"{m_info.get('count', 0)} lần")
            if r_list:
                role_counts = pd.Series(r_list).value_counts().reset_index()
                role_counts.columns = ['Role', 'Số lần']
                st.write("**Thống kê Role:**")
                st.table(role_counts)
            else:
                st.write("Chưa có dữ liệu role.")

        with col2:
            if r_list:
                # Tính toán chuỗi role cho báo cáo
                rc = pd.Series(r_list).value_counts().to_dict()
                role_str = ", ".join([f"{k} ({v})" for k, v in rc.items()])
                status = "ĐẠT CHỈ TIÊU" if m_info.get('count', 0) >= target_cta else "CHƯA ĐẠT"
                
                # NỘI DUNG COPY
                report = f"""⚔️ **GE GUILD - CHI TIẾT CTA** ⚔️
━━━━━━━━━━━━━━━━━━━━
👤 Người chơi: **{target}**
🔥 Tổng tham gia: **{m_info.get('count', 0)}** lượt
🎯 Chỉ tiêu: {target_cta} -> **{status}**
📊 Chi tiết Role: {role_str}
━━━━━━━━━━━━━━━━━━━━
*Dữ liệu được cập nhật tự động bởi GE System*"""
                
                st.text_area("📋 Copy nội dung gửi thành viên:", value=report, height=220)
                st.info("💡 Mẹo: Bôi đen đoạn trên và nhấn Ctrl+C để gửi vào Discord/Zalo.")
