import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
import pandas as pd
from datetime import datetime

# --- 1. CẤU HÌNH UI ---
st.set_page_config(page_title="GE Guild - Professional Admin", layout="wide", page_icon="🛡️")

# --- 2. KẾT NỐI FIREBASE (Đảm bảo không mất dữ liệu) ---
if not firebase_admin._apps:
    try:
        sd = dict(st.secrets["firebase"])
        if "\\n" in sd["private_key"]: sd["private_key"] = sd["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(sd)
        firebase_admin.initialize_app(cred)
    except Exception as e: st.error(f"Lỗi Firebase: {e}")

db = firestore.client()

# --- 3. SIDEBAR: CẤU HÌNH & CHECK API ---
with st.sidebar:
    st.title("🛡️ GE GUILD PANEL")
    api_key = st.text_input("Gemini Key:", type="password", value=st.session_state.get('cur_key', st.secrets.get("gemini", {}).get("api_key", "")))
    st.session_state['cur_key'] = api_key
    
    if st.button("🔍 Check API Status"):
        try:
            genai.configure(api_key=api_key)
            m = genai.GenerativeModel('gemini-2.5-flash')
            m.generate_content("hi", generation_config={"max_output_tokens": 1})
            st.success("✅ API OK")
        except: st.error("❌ Key Lỗi/Hết Quota")

    st.divider()
    target_cta = st.number_input("Chỉ tiêu (lượt/tháng):", min_value=1, value=10)
    
    st.divider()
    new_m = st.text_input("Tạo mốc mới:")
    if st.button("✨ Tạo mốc"):
        if new_m:
            db.collection("cta_events").document(new_m).set({"name": new_m, "ts": firestore.SERVER_TIMESTAMP})
            st.rerun()

    cta_list = [d.id for d in db.collection("cta_events").order_by("ts", direction=firestore.Query.DESCENDING).limit(30).stream()]
    sel_cta = st.selectbox("📌 Mốc làm việc:", cta_list) if cta_list else "None"

# --- 4. TABS GIAO DIỆN ---
t_check, t_members, t_summary = st.tabs(["🚀 QUÉT ẢNH AI", "👥 DANH SÁCH THÀNH VIÊN", "📊 TỔNG KẾT & CHI TIẾT ROLE"])

# --- TAB 1: QUÉT ẢNH AI ---
with t_check:
    st.subheader(f"📸 Ghi nhận Party List: `{sel_cta}`")
    up = st.file_uploader("Kéo ảnh vào đây", type=["jpg", "png", "jpeg"])
    
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
                        st.success("Xong!")
                except Exception as e: st.error(f"Lỗi: {e}")

    if 'temp_data' in st.session_state:
        edited = st.data_editor(st.session_state['temp_data'], num_rows="dynamic", use_container_width=True)
        if st.button("💾 XÁC NHẬN LƯU DỮ LIỆU"):
            batch = db.batch()
            for i in edited:
                # 1. Lưu lịch sử buổi CTA
                batch.set(db.collection("cta_attendance").document(f"{sel_cta}_{i['name']}"), 
                          {"cta_id": sel_cta, "name": i['name'], "role": i['role'], "ts": firestore.SERVER_TIMESTAMP})
                
                # 2. Cập nhật Master Member & Tăng số lượt
                m_ref = db.collection("members").document(i['name'])
                batch.set(m_ref, {"name": i['name'], "count": firestore.Increment(1)}, merge=True)
                
                # 3. LƯU ROLE VÀO SUB-COLLECTION (Để tính toán số lần dùng role)
                role_ref = m_ref.collection("role_history").document()
                batch.set(role_ref, {"role": i['role'], "ts": firestore.SERVER_TIMESTAMP, "cta_id": sel_cta})
                
            batch.commit()
            st.success("🔥 Đã lưu vĩnh viễn!")
            del st.session_state['temp_data']
            st.rerun()

# --- TAB 2: DANH SÁCH THÀNH VIÊN (Lấy data Realtime) ---
with t_members:
    st.subheader("👥 Bảng Điểm Guild")
    # Luôn fetch mới từ DB để tránh mất data khi restart app
    m_docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    m_data = []
    for m in m_docs:
        d = m.to_dict()
        cnt = d.get("count", 0)
        m_data.append({
            "IGN": d.get("name"),
            "Tổng Lượt": cnt,
            "Trạng Thái": "✅ ĐẠT" if cnt >= target_cta else "❌ CHƯA ĐẠT"
        })
    if m_data:
        st.dataframe(pd.DataFrame(m_data), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có dữ liệu thành viên.")

# --- TAB 3: TỔNG KẾT & CHI TIẾT ROLE ---
with t_summary:
    st.subheader("📊 Phân tích chi tiết người chơi")
    all_names = [m['IGN'] for m in m_data] if 'm_data' in locals() and m_data else []
    target = st.selectbox("Chọn thành viên:", all_names)
    
    if target:
        # 1. Lấy thông tin tổng quát
        m_info = db.collection("members").document(target).get().to_dict()
        
        # 2. Lấy LỊCH SỬ ROLE từ Sub-collection
        r_docs = db.collection("members").document(target).collection("role_history").stream()
        r_list = [r.to_dict()['role'] for r in r_docs]
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.metric("Tổng tham gia", f"{m_info.get('count', 0)} lần")
            st.write("**Số lần sử dụng Role:**")
            if r_list:
                role_counts = pd.Series(r_list).value_counts().reset_index()
                role_counts.columns = ['Role', 'Số lần']
                st.table(role_counts)
            else:
                st.write("Chưa có dữ liệu role.")

        with col2:
            if r_list:
                # Tính toán nội dung để COPY
                role_summary = pd.Series(r_list).value_counts().to_dict()
                role_str = ", ".join([f"{k}: {v} lần" for k, v in role_summary.items()])
                
                status = "ĐẠT CHỈ TIÊU" if m_info.get('count', 0) >= target_cta else "CHƯA ĐẠT"
                
                report = f"""⚔️ **GE GUILD REPORT** ⚔️
👤: **{target}**
🔥 Tổng: {m_info.get('count', 0)} lượt
🎯 Chỉ tiêu: {target_cta} ({status})
📊 Chi tiết Role: {role_str}
━━━━━━━━━━━━━━━━━━"""
                st.text_area("Nội dung Copy gửi thành viên:", value=report, height=200)
