import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
import pandas as pd
from datetime import datetime

# --- 1. CẤU HÌNH UI & THEME ---
st.set_page_config(page_title="GE Guild - Management System", layout="wide", page_icon="🛡️")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: #161b22; padding: 10px; border-radius: 10px; }
    .stTabs [data-baseweb="tab"] { border-radius: 5px; padding: 8px 16px; font-weight: bold; }
    .stTabs [aria-selected="true"] { background-color: #238636 !important; color: white !important; }
    div[data-testid="stExpander"] { border: 1px solid #30363d; background-color: #161b22; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. KẾT NỐI FIREBASE (FIX) ---
if not firebase_admin._apps:
    try:
        sd = dict(st.secrets["firebase"])
        if "\\n" in sd["private_key"]: sd["private_key"] = sd["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(sd)
        firebase_admin.initialize_app(cred)
    except Exception as e: st.error(f"Lỗi kết nối Firebase: {e}")

db = firestore.client()

# --- 3. SIDEBAR CỐ ĐỊNH ---
with st.sidebar:
    st.title("🛡️ GE GUILD ADMIN")
    
    # Kiểm tra API Key
    st.subheader("🔑 AI API Key")
    api_key = st.text_input("Nhập Gemini Key:", type="password", value=st.session_state.get('cur_key', st.secrets.get("gemini", {}).get("api_key", "")))
    st.session_state['cur_key'] = api_key
    
    col_api1, col_api2 = st.columns([2,1])
    if col_api1.button("🔍 Check API Status"):
        try:
            genai.configure(api_key=api_key)
            m = genai.GenerativeModel('gemini-2.5-flash')
            m.generate_content("test", generation_config={"max_output_tokens": 1})
            st.success("✅ Sẵn sàng!")
        except Exception as e: st.error("❌ Hết Quota/Sai Key")

    st.divider()
    st.subheader("🎯 Mức Chuyên Cần")
    target_cta = st.number_input("Chỉ tiêu (lượt/tháng):", min_value=1, value=10)

    st.divider()
    st.subheader("📅 Quản lý Mốc")
    new_m = st.text_input("Tên mốc (VD: 18UTC-01/03)")
    if st.button("✨ Tạo mốc mới"):
        if new_m:
            db.collection("cta_events").document(new_m).set({"name": new_m, "created_at": firestore.SERVER_TIMESTAMP})
            st.rerun()

    # Tải danh sách mốc
    cta_list = [d.id for d in db.collection("cta_events").order_by("created_at", direction=firestore.Query.DESCENDING).limit(30).stream()]
    sel_cta = st.selectbox("📌 Chọn mốc làm việc:", cta_list) if cta_list else "None"

# --- 4. CÁC HÀM LẤY DỮ LIỆU TỪ FIREBASE (QUAN TRỌNG NHẤT) ---
def get_all_members():
    # Luôn lấy từ Firebase, không dùng cache để tránh mất dữ liệu khi load lại
    docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    return [d.to_dict() for d in docs]

# --- 5. GIAO DIỆN CHÍNH ---
t_check, t_members, t_summary = st.tabs(["🚀 QUÉT ẢNH AI", "👥 DANH SÁCH THÀNH VIÊN", "📊 BÁO CÁO CÁ NHÂN"])

# --- TAB 1: QUÉT ẢNH AI ---
with t_check:
    st.subheader(f"📸 Ghi nhận Party List: `{sel_cta}`")
    up = st.file_uploader("Kéo ảnh vào đây", type=["jpg", "png", "jpeg"])
    
    if up:
        img = Image.open(up)
        st.image(img, width=450)
        if st.button("🪄 CHẠY AI (GEMINI 2.5 FLASH)", type="primary"):
            with st.spinner("AI đang bóc tách tên..."):
                try:
                    genai.configure(api_key=st.session_state['cur_key'])
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = "Return ONLY JSON array: [{'name': 'IGN', 'role': 'Tank/Healer/Melee/Ranged/Support'}]"
                    res = model.generate_content([prompt, img])
                    clean = re.search(r'\[.*\]', res.text.replace('```json', '').replace('```', ''), re.DOTALL)
                    if clean:
                        st.session_state['temp_data'] = json.loads(clean.group())
                        st.success("Đã trích xuất xong!")
                except Exception as e: st.error(f"Lỗi: {e}")

    if 'temp_data' in st.session_state:
        st.info("💡 Bạn có thể sửa trực tiếp tên/role trong bảng dưới:")
        edited = st.data_editor(st.session_state['temp_data'], num_rows="dynamic", use_container_width=True)
        
        if st.button("💾 XÁC NHẬN LƯU & CỘNG ĐIỂM"):
            if sel_cta == "None":
                st.error("Chưa chọn mốc CTA!")
            else:
                batch = db.batch()
                for i in edited:
                    # Lưu lịch sử buổi đó
                    batch.set(db.collection("cta_attendance").document(f"{sel_cta}_{i['name']}"), 
                              {"cta_id": sel_cta, "name": i['name'], "role": i['role'], "ts": firestore.SERVER_TIMESTAMP})
                    # Cập nhật số lượt cộng dồn vào Member
                    batch.set(db.collection("members").document(i['name']), 
                              {"name": i['name'], "last_role": i['role'], "count": firestore.Increment(1), "ts": firestore.SERVER_TIMESTAMP}, merge=True)
                batch.commit()
                st.success("🔥 Đã lưu vĩnh viễn vào Database!")
                del st.session_state['temp_data']
                st.rerun()

# --- TAB 2: DANH SÁCH THÀNH VIÊN (DỮ LIỆU THẬT TỪ FIREBASE) ---
with t_members:
    st.subheader("👥 Bảng Điểm Guild GE")
    members = get_all_members() # Lấy data mới nhất từ Firebase
    
    if members:
        # Chuẩn bị DataFrame
        df_list = []
        for m in members:
            count = m.get("count", 0)
            df_list.append({
                "Tên Nhân Vật (IGN)": m.get("name"),
                "Tổng Lượt": count,
                "Trạng Thái": "✅ ĐẠT" if count >= target_cta else "❌ CHƯA ĐẠT",
                "Role Cuối": m.get("last_role"),
                "Cập Nhật": m.get("ts").strftime("%d/%m %H:%M") if m.get("ts") else "N/A"
            })
        st.dataframe(pd.DataFrame(df_list), use_container_width=True, hide_index=True)
    else:
        st.warning("Chưa có dữ liệu thành viên nào trong Database.")

# --- TAB 3: BÁO CÁO CÁ NHÂN & COPY ---
with t_summary:
    st.subheader("📊 Trích xuất báo cáo cá nhân")
    members = get_all_members()
    names = [m.get("name") for m in members]
    
    target_name = st.selectbox("Chọn người chơi:", names) if names else None
    
    if target_name:
        # Lấy info người được chọn
        m_info = next(m for m in members if m['name'] == target_name)
        count = m_info.get("count", 0)
        status = "ĐẠT CHỈ TIÊU" if count >= target_cta else "CHƯA ĐẠT"
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Tham gia", f"{count} lượt")
        c2.metric("Chỉ tiêu", f"{target_cta}")
        c3.info(f"Kết quả: **{status}**")
        
        # Tạo văn bản Copy
        report_text = f"""⚔️ **GE GUILD - CTA REPORT** ⚔️
━━━━━━━━━━━━━━━━━━
👤 Người chơi: **{target_name}**
🔥 Tổng lượt tham gia: `{count}`
🎯 Chỉ tiêu tháng: `{target_cta}`
📊 Trạng thái: **{status}**
🛡️ Role cuối: {m_info.get('last_role', 'N/A')}
━━━━━━━━━━━━━━━━━━
*Hãy tiếp tục cống hiến cùng Guild nhé!*"""
        
        st.text_area("Copy đoạn này gửi cho thành viên:", value=report_text, height=200)
