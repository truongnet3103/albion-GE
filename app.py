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
st.set_page_config(page_title="GE Guild Admin - Season Management", layout="wide", page_icon="🛡️")

# --- 2. KẾT NỐI FIREBASE ---
if not firebase_admin._apps:
    try:
        sd = dict(st.secrets["firebase"])
        if "\\n" in sd["private_key"]: sd["private_key"] = sd["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(sd)
        firebase_admin.initialize_app(cred)
    except Exception as e: st.error(f"Lỗi kết nối Firebase: {e}")

db = firestore.client()

# --- 3. SIDEBAR: CẤU HÌNH & RESET MÙA ---
with st.sidebar:
    st.title("🛡️ GE GUILD PANEL")
    
    # Cấu hình AI
    st.subheader("🔑 AI Configuration")
    api_key = st.text_input("Key:", type="password", value=st.session_state.get('cur_key', st.secrets.get("gemini", {}).get("api_key", "")))
    st.session_state['cur_key'] = api_key
    
    st.divider()
    
    # Quản lý Chỉ tiêu & Reset
    target_cta = st.number_input("Chỉ tiêu (lượt/tháng):", min_value=1, value=10)
    
    st.divider()
    
    # NÚT RESET DATABASE (DÙNG CHO MÙA MỚI)
    st.subheader("⚠️ Vùng Nguy Hiểm")
    confirm_reset = st.checkbox("Tôi muốn xóa sạch dữ liệu mùa cũ")
    if st.button("🔥 RESET TOÀN BỘ DATABASE"):
        if confirm_reset:
            with st.spinner("Đang xóa dữ liệu..."):
                # Xóa Members, Attendance, Events
                for coll in ["members", "cta_attendance", "cta_events"]:
                    docs = db.collection(coll).limit(500).stream()
                    for d in docs: d.reference.delete()
            st.success("Đã xóa sạch database cho mùa mới!")
            st.rerun()
        else:
            st.warning("Vui lòng tích vào ô xác nhận trước khi xóa.")

    st.divider()
    
    # Quản lý Mốc
    st.subheader("📅 Quản lý Mốc CTA")
    new_m = st.text_input("Tạo mốc mới:")
    if st.button("✨ Xác nhận Tạo"):
        if new_m:
            db.collection("cta_events").document(new_m).set({"name": new_m, "ts": firestore.SERVER_TIMESTAMP})
            st.rerun()

    # Lấy danh sách mốc (Fix lỗi hiển thị khi DB trống)
    try:
        cta_list = [d.id for d in db.collection("cta_events").order_by("ts", direction=firestore.Query.DESCENDING).limit(30).stream()]
        sel_cta = st.selectbox("📌 Chọn mốc làm việc:", cta_list) if cta_list else "Chưa có mốc"
    except:
        sel_cta = "Chưa có mốc"

# --- 4. GIAO DIỆN CHÍNH ---
t_check, t_members, t_summary = st.tabs(["🚀 QUÉT ẢNH AI", "👥 THÀNH VIÊN", "📊 BÁO CÁO CHI TIẾT"])

# --- TAB 1: QUÉT ẢNH AI (FIX ROLE PROMPT) ---
with t_check:
    st.subheader(f"📸 Ghi nhận Party List: `{sel_cta}`")
    up = st.file_uploader("Upload ảnh Party List", type=["jpg", "png", "jpeg"])
    
    if up:
        img = Image.open(up)
        st.image(img, width=400)
        if st.button("🪄 CHẠY AI SCAN", type="primary"):
            with st.spinner("AI đang phân tích..."):
                try:
                    genai.configure(api_key=st.session_state['cur_key'])
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    # Prompt thắt chặt để tránh lấy cả cụm Tank/Healer/...
                    prompt = """
                    Analyze the Albion Party List. Extract Character Name (IGN) and exactly ONE role for each.
                    Choose only from: Tank, Healer, Melee, Ranged, Support. 
                    Based on the class icon. If unsure, pick the closest one.
                    Return ONLY JSON array: [{"name": "IGN", "role": "Single Role Name"}]
                    """
                    res = model.generate_content([prompt, img])
                    clean = re.search(r'\[.*\]', res.text.replace('```json', '').replace('```', ''), re.DOTALL)
                    if clean:
                        st.session_state['temp_data'] = json.loads(clean.group())
                        st.success("Đã trích xuất! Hãy kiểm tra bảng bên dưới.")
                except Exception as e: st.error(f"Lỗi AI: {e}")

    if 'temp_data' in st.session_state:
        edited = st.data_editor(st.session_state['temp_data'], num_rows="dynamic", use_container_width=True)
        if st.button("💾 XÁC NHẬN LƯU"):
            if sel_cta == "Chưa có mốc":
                st.error("Phải tạo mốc ở Sidebar trước!")
            else:
                batch = db.batch()
                now = firestore.SERVER_TIMESTAMP
                for i in edited:
                    # 1. Lưu attendance
                    batch.set(db.collection("cta_attendance").document(f"{sel_cta}_{i['name']}"), 
                              {"cta_id": sel_cta, "name": i['name'], "role": i['role'], "ts": now})
                    
                    # 2. Cập nhật Master Member (Thêm ngày bắt đầu/kết thúc)
                    m_ref = db.collection("members").document(i['name'])
                    m_data = m_ref.get()
                    
                    if not m_data.exists:
                        # Người mới: Set ngày bắt đầu
                        batch.set(m_ref, {
                            "name": i['name'], "count": 1, 
                            "join_date": now, "last_active": now
                        })
                    else:
                        # Người cũ: Tăng count và cập nhật ngày cuối
                        batch.update(m_ref, {
                            "count": firestore.Increment(1),
                            "last_active": now
                        })
                    
                    # 3. Lưu lịch sử Role
                    batch.set(m_ref.collection("role_history").document(), {"role": i['role'], "ts": now})
                
                batch.commit()
                st.success("Đã đồng bộ Cloud!")
                del st.session_state['temp_data']
                st.rerun()

# --- TAB 2: DANH SÁCH THÀNH VIÊN ---
with t_members:
    st.subheader("👥 Thống kê chuyên cần mùa này")
    m_docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    m_list = []
    for m in m_docs:
        d = m.to_dict()
        m_list.append({
            "IGN": d.get("name"),
            "Tổng Lượt": d.get("count", 0),
            "Ngày Tham Gia": d.get("join_date").strftime("%d/%m/%Y") if d.get("join_date") else "N/A",
            "Hoạt Động Cuối": d.get("last_active").strftime("%d/%m/%Y") if d.get("last_active") else "N/A",
            "Trạng Thái": "✅ ĐẠT" if d.get("count", 0) >= target_cta else "❌ CHƯA ĐẠT"
        })
    if m_list:
        st.dataframe(pd.DataFrame(m_list), use_container_width=True, hide_index=True)

# --- TAB 3: BÁO CÁO CHI TIẾT ---
with t_summary:
    st.subheader("📊 Phân tích Role & Copy Report")
    target = st.selectbox("Chọn thành viên:", [m['IGN'] for m in m_list] if 'm_list' in locals() else [])
    
    if target:
        m_info = db.collection("members").document(target).get().to_dict()
        r_docs = db.collection("members").document(target).collection("role_history").stream()
        r_list = [r.to_dict()['role'] for r in r_docs]
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Tổng tham gia", f"{m_info.get('count', 0)} lần")
            st.write(f"📅 **Bắt đầu:** {m_info.get('join_date').strftime('%d/%m/%Y') if m_info.get('join_date') else 'N/A'}")
            if r_list:
                role_counts = pd.Series(r_list).value_counts().reset_index()
                role_counts.columns = ['Role', 'Số lần']
                st.table(role_counts)

        with c2:
            if r_list:
                rc = pd.Series(r_list).value_counts().to_dict()
                role_str = ", ".join([f"{k} ({v})" for k, v in rc.items()])
                status = "ĐẠT" if m_info.get('count', 0) >= target_cta else "CHƯA ĐẠT"
                
                report = f"""⚔️ **GE GUILD REPORT** ⚔️
👤: **{target}**
🗓️ Tham gia từ: {m_info.get('join_date').strftime('%d/%m/%Y')}
🔥 Tổng lượt: {m_info.get('count', 0)}
🎯 Chỉ tiêu: {target_cta} ({status})
📊 Chi tiết Role: {role_str}
━━━━━━━━━━━━━━━━━━━━"""
                st.text_area("📋 Copy nội dung:", value=report, height=220)
