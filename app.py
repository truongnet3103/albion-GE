import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
import pandas as pd
from datetime import datetime

# --- 1. CẤU HÌNH GIAO DIỆN (UI) ---
st.set_page_config(page_title="GE Guild - Management System", layout="wide", page_icon="🛡️")

# Custom CSS cho giao diện chuyên nghiệp
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    [data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
    .stMetric { background-color: #1f2937; padding: 15px; border-radius: 10px; border: 1px solid #374151; }
    .status-card { padding: 20px; border-radius: 10px; border: 1px solid #30363d; background-color: #0d1117; margin-bottom: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; transition: 0.3s; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        background-color: #161b22; border: 1px solid #30363d; border-radius: 8px 8px 0 0; 
        padding: 10px 20px; color: #8b949e; 
    }
    .stTabs [aria-selected="true"] { background-color: #238636 !important; color: white !important; border: none; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. KHỞI TẠO FIREBASE ---
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
    
    # 🔑 Cấu hình API
    st.subheader("🔑 AI API Key")
    api_key = st.text_input("Nhập Gemini Key:", type="password", value=st.session_state.get('cur_key', st.secrets.get("gemini", {}).get("api_key", "")))
    st.session_state['cur_key'] = api_key
    
    if st.button("🔍 Kiểm tra API"):
        try:
            genai.configure(api_key=api_key)
            m = genai.GenerativeModel('gemini-2.5-flash')
            test = m.generate_content("hi", generation_config={"max_output_tokens": 1})
            st.success("✅ API hoạt động tốt!")
        except Exception as e:
            st.error(f"❌ API Lỗi: {e}")

    st.divider()

    # 🎯 Mức quy định chuyên cần
    st.subheader("🎯 Chỉ tiêu Chuyên cần")
    target_cta = st.number_input("Số lượt tối thiểu/tháng:", min_value=1, value=10)
    
    st.divider()
    
    # 📅 Quản lý mốc
    st.subheader("📅 Mốc dữ liệu")
    new_m = st.text_input("Tên mốc mới (VD: 18UTC-01/03)")
    if st.button("✨ Tạo mốc"):
        if new_m:
            db.collection("cta_events").document(new_m).set({"name": new_m, "created_at": firestore.SERVER_TIMESTAMP})
            st.rerun()

    cta_list = [d.id for d in db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20).stream()]
    sel_cta = st.selectbox("Làm việc với mốc:", cta_list) if cta_list else "None"

# --- 4. GIAO DIỆN CHÍNH ---
t_check, t_members, t_summary = st.tabs(["🚀 AI SCANNER", "👥 MEMBER LIST", "📊 FINAL REPORT"])

# --- TAB 1: AI SCANNER ---
with t_check:
    st.subheader(f"📸 Quét Party List - Mốc: {sel_cta}")
    up = st.file_uploader("Kéo thả ảnh vào đây", type=["jpg", "png", "jpeg"])
    
    if up:
        img = Image.open(up)
        st.image(img, width=400)
        if st.button("🪄 PHÂN TÍCH ẢNH", type="primary"):
            with st.spinner("AI đang làm việc..."):
                try:
                    genai.configure(api_key=st.session_state['cur_key'])
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = "Return JSON array: [{'name': 'IGN', 'role': 'Tank/Healer/Melee/Ranged/Support'}] from image."
                    res = model.generate_content([prompt, img])
                    clean = re.search(r'\[.*\]', res.text.replace('```json', '').replace('```', ''), re.DOTALL)
                    if clean:
                        st.session_state['data'] = json.loads(clean.group())
                        st.success("Xong!")
                except Exception as e: st.error(f"Lỗi: {e}")

    if 'data' in st.session_state:
        edited = st.data_editor(st.session_state['data'], num_rows="dynamic", use_container_width=True)
        if st.button("💾 LƯU DỮ LIỆU & CỘNG ĐIỂM"):
            batch = db.batch()
            for i in edited:
                # Lưu lịch sử
                batch.set(db.collection("cta_attendance").document(f"{sel_cta}_{i['name']}"), 
                          {"cta_id": sel_cta, "name": i['name'], "role": i['role'], "ts": firestore.SERVER_TIMESTAMP})
                # Cộng dồn Member
                batch.set(db.collection("members").document(i['name']), 
                          {"name": i['name'], "last_role": i['role'], "count": firestore.Increment(1), "ts": firestore.SERVER_TIMESTAMP}, merge=True)
                # Lưu chi tiết role để tính tỉ lệ
                batch.set(db.collection("members").document(i['name']).collection("roles").document(), {"role": i['role']})
            batch.commit()
            st.success("Đã cập nhật điểm chuyên cần!")
            del st.session_state['data']

# --- TAB 2: MEMBER LIST ---
with t_members:
    st.subheader("👥 Danh sách Thành Viên Master")
    m_docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    m_list = []
    for m in m_docs:
        d = m.to_dict()
        status = "✅ ĐẠT" if d.get("count", 0) >= target_cta else "❌ KHÔNG ĐẠT"
        m_list.append({"IGN": d.get("name"), "Tổng Lượt": d.get("count", 0), "Chỉ tiêu": status, "Role cuối": d.get("last_role")})
    
    if m_list:
        st.dataframe(pd.DataFrame(m_list), use_container_width=True, hide_index=True)

# --- TAB 3: FINAL REPORT (ĐÁNH GIÁ CHI TIẾT) ---
with t_summary:
    st.subheader("📊 Báo cáo đánh giá chi tiết")
    target_ign = st.selectbox("Chọn người chơi cần xem báo cáo:", [m['IGN'] for m in m_list] if m_list else [])
    
    if target_ign:
        # Lấy data người chơi
        m_info = db.collection("members").document(target_ign).get().to_dict()
        role_docs = db.collection("members").document(target_ign).collection("roles").stream()
        roles = [r.to_dict()['role'] for r in role_docs]
        
        c1, c2, c3 = st.columns(3)
        count = m_info.get("count", 0)
        c1.metric("Tổng tham gia", f"{count} lượt")
        c2.metric("Chỉ tiêu", f"{target_cta}", delta=count - target_cta)
        status_text = "ĐẠT CHỈ TIÊU" if count >= target_cta else "CHƯA ĐẠT"
        c3.info(f"Trạng thái: **{status_text}**")
        
        # Tính tỉ lệ Role
        if roles:
            st.write("**Tỉ lệ Role đã chơi:**")
            role_df = pd.Series(roles).value_counts(normalize=True).mul(100).round(1).astype(str) + '%'
            st.table(role_df)

            # Chuẩn bị nội dung Copy
            report_str = f"""⚔️ **BÁO CÁO CTA - GUILD GE** ⚔️
👤 Người chơi: **{target_ign}**
🔥 Tổng lượt tham gia: {count}
🎯 Chỉ tiêu quy định: {target_cta}
📊 Trạng thái: {status_text}
🛡️ Tỉ lệ Role: {role_df.to_dict()}
----------------------------
*Hãy tiếp tục phát huy cùng Guild nhé!*"""
            
            st.text_area("Nội dung gửi Discord/Zalo:", value=report_str, height=180)
            st.caption("Mẹo: Bôi đen toàn bộ nội dung trên để copy gửi cho người chơi.")
