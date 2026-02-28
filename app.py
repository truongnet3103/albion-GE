import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
import pandas as pd
from datetime import datetime

# --- 1. CẤU HÌNH UI CHUYÊN NGHIỆP ---
st.set_page_config(
    page_title="GE Guild Management System", 
    layout="wide", 
    page_icon="⚔️",
    initial_sidebar_state="expanded"
)

# Custom CSS cho phong cách Gaming/High-tech
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    .stApp { background-color: #0b0e14; color: #e6edf3; }
    
    /* Style cho Metric và Cards */
    div[data-testid="stMetric"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Custom Button */
    .stButton>button {
        border-radius: 8px;
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(35, 134, 54, 0.4);
    }
    
    /* Bảng dữ liệu */
    .styled-table { margin: 25px 0; font-size: 0.9em; border-radius: 8px; overflow: hidden; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. KẾT NỐI FIREBASE (Singleton Pattern) ---
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
            sd = dict(st.secrets["firebase"])
            if "\\n" in sd["private_key"]:
                sd["private_key"] = sd["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(sd)
            return firebase_admin.initialize_app(cred)
    return firebase_admin.get_app()

init_firebase()
db = firestore.client()

# --- 3. HELPER FUNCTIONS ---
def get_api_key():
    doc = db.collection("system_config").document("gemini_api").get()
    return doc.to_dict().get("key", "").strip() if doc.exists else ""

def format_timestamp(ts):
    return ts.strftime("%d/%m/%Y %H:%M") if ts else "N/A"

# --- 4. SIDEBAR - CONTROL PANEL ---
with st.sidebar:
    st.image("https://img.icons8.com/fluent/96/shield.png", width=80)
    st.title("GE GUILD ADMIN")
    st.caption("Phiên bản Cao Cấp | Dev by TruongNET")
    
    st.divider()
    with st.expander("🤖 CẤU HÌNH AI", expanded=False):
        if st.button("⚡ Test Connection"):
            key = get_api_key()
            if key:
                try:
                    genai.configure(api_key=key)
                    m = genai.GenerativeModel('gemini-2.0-flash') # Cập nhật model mới nhất
                    m.generate_content("ping", generation_config={"max_output_tokens": 1})
                    st.success("AI Online!")
                except Exception as e: st.error("Lỗi API Key")
            else: st.warning("Chưa có Key")

    target_cta = st.number_input("🎯 Chỉ tiêu Season (lượt):", min_value=1, value=10)
    
    st.divider()
    st.subheader("📍 QUẢN LÝ MỐC (EVENT)")
    new_m = st.text_input("Tên mốc (VD: Công Thành 01/03):")
    if st.button("🆕 TẠO MỐC MỚI", use_container_width=True):
        if new_m:
            db.collection("cta_events").document(new_m).set({"name": new_m, "ts": firestore.SERVER_TIMESTAMP})
            st.toast(f"Đã tạo: {new_m}", icon="✨")
            st.rerun()

    cta_docs = db.collection("cta_events").order_by("ts", direction=firestore.Query.DESCENDING).limit(20).stream()
    cta_list = [d.id for d in cta_docs]
    sel_cta = st.selectbox("📌 Mốc đang chọn:", ["Chọn mốc..."] + cta_list)

    st.divider()
    if st.checkbox("🔓 Mở khóa Reset"):
        if st.button("🔥 WIPE DATABASE", type="primary", use_container_width=True):
            with st.spinner("Đang xóa dữ liệu..."):
                for coll in ["members", "cta_attendance", "cta_events"]:
                    docs = db.collection(coll).limit(500).stream()
                    for d in docs: d.reference.delete()
            st.success("Đã reset toàn bộ!")
            st.rerun()

# --- 5. MAIN INTERFACE ---
tabs = st.tabs(["🚀 AI SCANNER", "👥 MEMBERS", "🛠️ MODERATION", "📊 ANALYTICS"])

# --- TAB 1: AI SCANNER ---
with tabs[0]:
    st.markdown(f"### 📸 Quét Party List - Mốc: `{sel_cta}`")
    
    col_up, col_pre = st.columns([1, 1])
    with col_up:
        up = st.file_uploader("Upload ảnh chụp màn hình", type=["jpg", "png", "jpeg"], help="Chụp rõ danh sách tổ đội")
    
    if up:
        img = Image.open(up)
        with col_pre:
            st.image(img, caption="Ảnh đã tải lên", use_container_width=True)
            
        if st.button("🪄 BẮT ĐẦU PHÂN TÍCH", type="primary", use_container_width=True):
            api_key = get_api_key()
            if not api_key:
                st.error("Chưa cấu hình API Key trong Firebase!")
            elif sel_cta == "Chọn mốc...":
                st.warning("Vui lòng chọn hoặc tạo mốc trước!")
            else:
                with st.status("AI đang xử lý hình ảnh...", expanded=True) as status:
                    try:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-2.0-flash')
                        prompt = """
                        Phân tích ảnh Party List Game:
                        1. Trích xuất In-game Name (IGN).
                        2. Phân loại Role: Tank, Healer, Melee, Ranged, Support.
                        3. Trả về định dạng JSON mảng: [{"name": "...", "role": "..."}]
                        Lưu ý: Chỉ trả về JSON, không thêm văn bản khác.
                        """
                        res = model.generate_content([prompt, img])
                        clean = re.search(r'\[.*\]', res.text.replace('```json', '').replace('```', ''), re.DOTALL)
                        if clean:
                            st.session_state['temp_data'] = json.loads(clean.group())
                            status.update(label="Phân tích hoàn tất!", state="complete")
                        else:
                            status.update(label="Lỗi định dạng AI", state="error")
                    except Exception as e:
                        st.error(f"Lỗi: {str(e)}")

    if 'temp_data' in st.session_state:
        st.markdown("#### 📝 Kiểm tra dữ liệu")
        edited = st.data_editor(st.session_state['temp_data'], num_rows="dynamic", use_container_width=True)
        
        c1, c2 = st.columns(2)
        if c1.button("💾 LƯU VÀO CLOUD", type="primary", use_container_width=True):
            batch = db.batch()
            now = firestore.SERVER_TIMESTAMP
            for i in edited:
                # Lưu attendance
                att_id = f"{sel_cta}_{i['name']}".replace("/", "_")
                batch.set(db.collection("cta_attendance").document(att_id), 
                         {"cta_id": sel_cta, "name": i['name'], "role": i['role'], "ts": now})
                
                # Cập nhật Member
                m_ref = db.collection("members").document(i['name'])
                if not m_ref.get().exists:
                    batch.set(m_ref, {"name": i['name'], "count": 1, "join_date": now, "last_active": now})
                else:
                    batch.update(m_ref, {"count": firestore.Increment(1), "last_active": now})
                
                # Role history
                batch.set(m_ref.collection("role_history").document(), {"role": i['role'], "ts": now})
            
            batch.commit()
            st.success("Đã đồng bộ thành công!")
            del st.session_state['temp_data']
            st.rerun()
        if c2.button("🗑️ HỦY KẾT QUẢ", use_container_width=True):
            del st.session_state['temp_data']
            st.rerun()

# --- TAB 2: MEMBERS ---
with tabs[1]:
    st.subheader("👥 Danh sách thành viên")
    docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    
    m_data = []
    for d in docs:
        m = d.to_dict()
        count = m.get("count", 0)
        m_data.append({
            "IGN": m.get("name"),
            "Lượt Tham Gia": count,
            "Tiến Độ": f"{(count/target_cta)*100:.0f}%" if target_cta > 0 else "0%",
            "Ngày Gia Nhập": format_timestamp(m.get("join_date")),
            "Trạng Thái": "🔥 ELITE" if count >= target_cta else "📉 TRADING"
        })
    
    if m_data:
        df = pd.DataFrame(m_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Thống kê nhanh
        c1, c2, c3 = st.columns(3)
        c1.metric("Tổng Member", len(df))
        c2.metric("Đạt Chỉ Tiêu", len(df[df['Lượt Tham Gia'] >= target_cta]))
        c3.download_button("📥 Xuất Báo Cáo CSV", df.to_csv(index=False).encode('utf-8-sig'), "Guild_Report.csv", use_container_width=True)

# --- TAB 3: MODERATION ---
with tabs[2]:
    st.subheader("🛠️ Hiệu chỉnh thông tin")
    all_names = [m['IGN'] for m in m_data] if 'm_data' in locals() else []
    
    col_sel, col_val = st.columns([2, 1])
    with col_sel:
        target_edit = st.selectbox("Tìm kiếm thành viên:", [""] + all_names)
    
    if target_edit:
        curr_score = next(m['Lượt Tham Gia'] for m in m_data if m['IGN'] == target_edit)
        with col_val:
            new_score = st.number_input("Sửa điểm:", value=curr_score)
            
        c1, c2 = st.columns(2)
        if c1.button("✅ CẬP NHẬT ĐIỂM", use_container_width=True):
            db.collection("members").document(target_edit).update({"count": new_score})
            st.toast("Đã cập nhật!", icon="✅")
            st.rerun()
        if c2.button("❌ XÓA KHỎI GUILD", type="primary", use_container_width=True):
            db.collection("members").document(target_edit).delete()
            st.rerun()

# --- TAB 4: ANALYTICS ---
with tabs[3]:
    if not all_names:
        st.info("Chưa có dữ liệu để phân tích.")
    else:
        target_rep = st.selectbox("Chọn IGN xem chi tiết:", all_names, key="analysis_sel")
        if target_rep:
            info = db.collection("members").document(target_rep).get().to_dict()
            r_docs = db.collection("members").document(target_rep).collection("role_history").stream()
            roles = [r.to_dict()['role'] for r in r_docs]
            
            st.markdown(f"### Báo cáo: `{target_rep}`")
            c1, c2, c3 = st.columns(3)
            c1.metric("Tổng trận", info.get('count', 0))
            c2.metric("Ngày tham gia", info.get('join_date').strftime('%d/%m') if info.get('join_date') else "N/A")
            c3.metric("Trạng thái", "ĐẠT" if info.get('count',0) >= target_cta else "THIẾU")
            
            st.divider()
            col_chart, col_text = st.columns([1, 1])
            with col_chart:
                if roles:
                    role_counts = pd.Series(roles).value_counts()
                    st.write("**Phân bổ Role:**")
                    st.bar_chart(role_counts)
            
            with col_text:
                rc_str = ", ".join([f"{k}: {v}" for k, v in pd.Series(roles).value_counts().to_dict().items()])
                status_icon = "✅" if info.get('count', 0) >= target_cta else "⚠️"
                report_text = (
                    f"⚔️ **GE GUILD INDIVIDUAL REPORT** ⚔️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 IGN: {target_rep}\n"
                    f"📊 Tổng lượt: {info.get('count', 0)} / {target_cta}\n"
                    f"🛡️ Trạng thái: {status_icon} {'HOÀN THÀNH' if info.get('count', 0) >= target_cta else 'CẦN CỐ GẮNG'}\n"
                    f"🎭 Role sở trường: {rc_str}\n"
                    f"📅 Cập nhật: {datetime.now().strftime('%H:%M %d/%m')}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"*Generated by GE System*"
                )
                st.text_area("📋 Copy cho Discord/Zalo:", value=report_text, height=220)
