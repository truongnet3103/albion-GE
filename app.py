import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
import pandas as pd
from datetime import datetime

# --- 1. CẤU HÌNH UI (GIAO DIỆN) ---
st.set_page_config(page_title="GE Guild Admin - TRUONGNET", layout="wide", page_icon="⚔️")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .stTabs [data-baseweb="tab-list"] { background-color: #161b22; padding: 10px; border-radius: 10px; }
    .stTabs [aria-selected="true"] { background-color: #238636 !important; }
    div[data-testid="stMetric"] { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 10px; }
    .stButton>button { border-radius: 8px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. KẾT NỐI FIREBASE ---
if not firebase_admin._apps:
    try:
        sd = dict(st.secrets["firebase"])
        if "\\n" in sd["private_key"]: sd["private_key"] = sd["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(sd)
        firebase_admin.initialize_app(cred)
    except Exception as e: st.error(f"Lỗi kết nối Firebase: {e}")

db = firestore.client()

# --- 3. HÀM LẤY API KEY TỪ DATABASE (CHẤT XÁM CỦA BẠN) ---
def get_api_key_from_db():
    try:
        # Truy cập collection 'system_config', document 'gemini_api' để lấy key bạn dán trên Firebase
        doc = db.collection("system_config").document("gemini_api").get()
        if doc.exists:
            return doc.to_dict().get("key", "")
        return ""
    except:
        return ""

# --- 4. SIDEBAR QUẢN LÝ ---
with st.sidebar:
    st.title("🛡️ GE GUILD PANEL")
    
    # NÚT CHECK API (Để người dùng biết khi nào cần gọi bạn)
    st.subheader("🤖 Hệ thống AI Scan")
    if st.button("🔍 Kiểm tra trạng thái AI"):
        current_key = get_api_key_from_db()
        if not current_key:
            st.error("❌ Hệ thống chưa cấu hình API. Liên hệ **TruongNET**.")
        else:
            try:
                genai.configure(api_key=current_key)
                m = genai.GenerativeModel('gemini-2.5-flash')
                m.generate_content("hi", generation_config={"max_output_tokens": 1})
                st.success("✅ Hệ thống AI sẵn sàng hoạt động!")
            except:
                st.error("❌ API đã hết hạn hoặc bị khóa. Hãy liên hệ **TruongNET** để cập nhật.")

    st.divider()
    
    # Cấu hình chuyên cần
    target_cta = st.number_input("🎯 Chỉ tiêu lượt/tháng:", min_value=1, value=10)
    
    st.divider()

    # Quản lý Mốc (History Events)
    st.subheader("📅 Quản lý Mốc")
    new_m = st.text_input("Tên mốc mới (VD: 18UTC-01/03):")
    if st.button("✨ Xác nhận Tạo Mốc"):
        if new_m:
            db.collection("cta_events").document(new_m).set({"name": new_m, "ts": firestore.SERVER_TIMESTAMP})
            st.success(f"Đã tạo mốc {new_m}")
            st.rerun()

    # Load danh sách mốc
    cta_docs = db.collection("cta_events").order_by("ts", direction=firestore.Query.DESCENDING).limit(30).stream()
    cta_list = [d.id for d in cta_docs]
    sel_cta = st.selectbox("📌 Chọn mốc làm việc:", cta_list) if cta_list else "Chưa có mốc"

    st.divider()

    # NÚT RESET MÙA
    st.subheader("⚠️ Reset Season")
    if st.checkbox("Xác nhận muốn xóa sạch database?"):
        if st.button("🔥 RESET TOÀN BỘ"):
            with st.spinner("Đang xóa..."):
                for coll in ["members", "cta_attendance", "cta_events"]:
                    docs = db.collection(coll).limit(500).stream()
                    for d in docs: d.reference.delete()
            st.success("Đã làm sạch database mùa cũ!")
            st.rerun()

# --- 5. GIAO DIỆN CHÍNH ---
t_check, t_members, t_admin, t_summary = st.tabs(["🚀 QUÉT AI", "👥 THÀNH VIÊN", "🛠️ SỬA ĐIỂM", "📊 TỔNG KẾT"])

# --- TAB 1: QUÉT AI ---
with t_check:
    st.subheader(f"📸 Check-in Party List mốc: `{sel_cta}`")
    up = st.file_uploader("Kéo thả ảnh vào đây", type=["jpg", "png", "jpeg"])
    
    if up:
        img = Image.open(up)
        st.image(img, width=450)
        if st.button("🪄 CHẠY AI PHÂN TÍCH", type="primary"):
            api_key = get_api_key_from_db()
            if not api_key:
                st.error("❌ Không tìm thấy API. Vui lòng liên hệ **TruongNET**.")
            else:
                with st.spinner("AI đang đọc danh sách..."):
                    try:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        # Prompt ép AI chọn đúng 1 Role
                        prompt = "Extract IGN and exactly ONE role: Tank, Healer, Melee, Ranged, Support. Return JSON: [{'name': 'IGN', 'role': 'RoleName'}]"
                        res = model.generate_content([prompt, img])
                        clean = re.search(r'\[.*\]', res.text.replace('```json', '').replace('```', ''), re.DOTALL)
                        if clean:
                            st.session_state['temp_data'] = json.loads(clean.group())
                            st.success("Đã bóc tách dữ liệu thành công!")
                    except:
                        st.error("❌ Lỗi xử lý ảnh. Có thể API đã hết hạn. Hãy liên hệ **TruongNET**.")

    if 'temp_data' in st.session_state:
        st.info("💡 Bạn có thể sửa trực tiếp Role hoặc Tên nếu AI nhận diện nhầm:")
        edited = st.data_editor(st.session_state['temp_data'], num_rows="dynamic", use_container_width=True)
        if st.button("💾 XÁC NHẬN LƯU VÀ CỘNG ĐIỂM"):
            if sel_cta == "Chưa có mốc":
                st.error("Bạn chưa tạo mốc ở Sidebar!")
            else:
                batch = db.batch()
                now = firestore.SERVER_TIMESTAMP
                for i in edited:
                    # Lưu lịch sử mốc
                    batch.set(db.collection("cta_attendance").document(f"{sel_cta}_{i['name']}"), {"cta_id": sel_cta, "name": i['name'], "role": i['role'], "ts": now})
                    # Cập nhật Member (Join date & Last active)
                    m_ref = db.collection("members").document(i['name'])
                    m_snap = m_ref.get()
                    if not m_snap.exists:
                        batch.set(m_ref, {"name": i['name'], "count": 1, "join_date": now, "last_active": now})
                    else:
                        batch.update(m_ref, {"count": firestore.Increment(1), "last_active": now})
                    # Lưu lịch sử Role chi tiết
                    batch.set(m_ref.collection("role_history").document(), {"role": i['role'], "ts": now, "cta_id": sel_cta})
                batch.commit()
                st.success("🔥 Đã đồng bộ lên Cloud!")
                del st.session_state['temp_data']
                st.rerun()

# --- TAB 2: DANH SÁCH THÀNH VIÊN ---
with t_members:
    st.subheader("👥 Bảng Điểm Chuyên Cần")
    docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    m_list = []
    for d in docs:
        m = d.to_dict()
        m_list.append({
            "IGN": m.get("name"),
            "Tổng Lượt": m.get("count", 0),
            "Tham Gia Từ": m.get("join_date").strftime("%d/%m/%Y") if m.get("join_date") else "N/A",
            "Trạng Thái": "✅ ĐẠT" if m.get("count", 0) >= target_cta else "❌ CHƯA ĐẠT"
        })
    if m_list:
        df = pd.DataFrame(m_list)
        st.dataframe(df, use_container_width=True, hide_index=True)
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Xuất file Excel (CSV)", data=csv, file_name=f"GE_Guild_Report_{datetime.now().date()}.csv")

# --- TAB 3: SỬA ĐIỂM (ADMIN EDIT) ---
with t_admin:
    st.subheader("🛠️ Hiệu chỉnh dữ liệu thủ công")
    all_names = [m['IGN'] for m in m_list] if 'm_list' in locals() and m_list else []
    target_edit = st.selectbox("Chọn người chơi cần sửa:", all_names)
    
    if target_edit:
        col1, col2 = st.columns(2)
        with col1:
            curr_score = next(m['Tổng Lượt'] for m in m_list if m['IGN'] == target_edit)
            new_score = st.number_input(f"Sửa điểm cho {target_edit}:", min_value=0, value=curr_score)
            if st.button("🆙 Cập nhật con số mới"):
                db.collection("members").document(target_edit).update({"count": new_score})
                st.success("Đã cập nhật!")
                st.rerun()
        with col2:
            st.warning("Xóa thành viên sẽ mất toàn bộ lịch sử!")
            if st.button(f"🗑️ Xóa vĩnh viễn {target_edit}"):
                db.collection("members").document(target_edit).delete()
                st.rerun()

# --- TAB 4: TỔNG KẾT ---
with t_summary:
    target_rep = st.selectbox("Xem báo cáo chi tiết:", all_names)
    if target_rep:
        info = db.collection("members").document(target_rep).get().to_dict()
        r_docs = db.collection("members").document(target_rep).collection("role_history").stream()
        roles = [r.to_dict()['role'] for r in r_docs]
        
        j_date = info.get('join_date').strftime('%d/%m/%Y') if info.get('join_date') else "N/A"
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Tổng tham gia", f"{info.get('count', 0)} lần")
            st.write(f"📅 **Bắt đầu từ:** {j_date}")
            if roles:
                st.write("**Số lần chơi Role:**")
                st.table(pd.Series(roles).value_counts())
        
        with c2:
            if roles:
                rc = pd.Series(roles).value_counts().to_dict()
                role_summary = ", ".join([f"{k} ({v})" for k, v in rc.items()])
                status = "ĐẠT" if info.get('count', 0) >= target_cta else "CHƯA ĐẠT"
                
                report = f"""⚔️ **GE GUILD REPORT** ⚔️
━━━━━━━━━━━━━━━━━━━━
👤 IGN: **{target_rep}**
🗓️ Tham gia từ: {j_date}
🔥 Tổng lượt: {info.get('count', 0)}
🎯 Chỉ tiêu: {target_cta} ({status})
📊 Chi tiết Role: {role_summary}
━━━━━━━━━━━━━━━━━━━━
*Dữ liệu được quản lý bởi TruongNET*"""
                st.text_area("📋 Copy nội dung gửi thành viên:", value=report, height=220)
