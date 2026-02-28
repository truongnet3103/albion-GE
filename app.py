import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import google.generativeai as genai
from PIL import Image
import json
import re
import pandas as pd
from datetime import datetime

# --- 1. CẤU HÌNH UI (GIAO DIỆN ĐẸP CỦA BẠN) ---
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

# --- 3. HÀM LẤY API KEY TỪ DATABASE ---
def get_api_key_from_db():
    try:
        doc = db.collection("system_config").document("gemini_api").get()
        return doc.to_dict().get("key", "").strip() if doc.exists else ""
    except: return ""

# --- 4. SIDEBAR QUẢN LÝ ---
with st.sidebar:
    st.title("🛡️ GE GUILD PANEL")
    
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
            except Exception as e:
                st.error(f"❌ Lỗi API: {str(e)}")

    st.divider()
    target_cta = st.number_input("🎯 Chỉ tiêu lượt/tháng:", min_value=1, value=10)
    
    st.divider()
    st.subheader("📅 Quản lý Mốc")
    new_m = st.text_input("Tên mốc mới (VD: 18UTC-01/03):")
    if st.button("✨ Xác nhận Tạo Mốc") and new_m:
        db.collection("cta_events").document(new_m).set({"name": new_m, "ts": firestore.SERVER_TIMESTAMP})
        st.success(f"Đã tạo mốc {new_m}")
        st.rerun()

    cta_docs = db.collection("cta_events").order_by("ts", direction=firestore.Query.DESCENDING).limit(30).stream()
    cta_list = [d.id for d in cta_docs]
    sel_cta = st.selectbox("📌 Chọn mốc làm việc:", cta_list) if cta_list else "Chưa có mốc"

    st.divider()
    st.subheader("⚠️ Reset Season")
    if st.checkbox("Xác nhận muốn xóa sạch database?"):
        if st.button("🔥 RESET TOÀN BỘ"):
            with st.spinner("Đang dọn dẹp..."):
                for coll in ["members", "cta_attendance", "cta_events"]:
                    docs = db.collection(coll).limit(500).stream()
                    for d in docs: d.reference.delete()
            st.success("Đã làm sạch database!")
            st.rerun()

# --- 5. GIAO DIỆN CHÍNH ---
t_check, t_members, t_admin, t_summary = st.tabs(["🚀 QUÉT AI", "👥 THÀNH VIÊN", "🛠️ SỬA ĐIỂM", "📊 TỔNG KẾT"])

# --- TAB 1: QUÉT AI ---
with t_check:
    st.subheader(f"📸 Check-in mốc: `{sel_cta}`")
    up = st.file_uploader("Kéo thả ảnh Party List", type=["jpg", "png", "jpeg"])
    
    if up:
        img = Image.open(up)
        st.image(img, width=450)
        if st.button("🪄 CHẠY AI PHÂN TÍCH", type="primary"):
            api_key = get_api_key_from_db()
            if not api_key:
                st.error("❌ Không tìm thấy API trên Firebase.")
            else:
                with st.spinner("AI Gemini 2.5 đang đọc danh sách..."):
                    try:
                        genai.configure(api_key=api_key)
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        prompt = "Extract IGN and ONE role: Tank, Healer, Melee, Ranged, Support. Return JSON: [{'name': '...', 'role': '...'}]"
                        res = model.generate_content([prompt, img])
                        # Xử lý JSON từ AI
                        clean = re.search(r'\[.*\]', res.text.replace('```json', '').replace('```', ''), re.DOTALL)
                        if clean:
                            st.session_state['temp_data'] = json.loads(clean.group())
                            st.success("Bóc tách thành công!")
                        else:
                            st.error(f"Lỗi format dữ liệu AI. Hãy thử lại.")
                    except Exception as e:
                        st.error(f"❌ Lỗi AI: {str(e)}")

    if 'temp_data' in st.session_state:
        edited = st.data_editor(st.session_state['temp_data'], num_rows="dynamic", use_container_width=True)
        if st.button("💾 XÁC NHẬN LƯU VÀ CỘNG ĐIỂM"):
            if sel_cta == "Chưa có mốc": st.error("Bạn chưa chọn mốc!")
            else:
                batch = db.batch()
                now = firestore.SERVER_TIMESTAMP
                for i in edited:
                    batch.set(db.collection("cta_attendance").document(f"{sel_cta}_{i['name']}"), {"cta_id": sel_cta, "name": i['name'], "role": i['role'], "ts": now})
                    m_ref = db.collection("members").document(i['name'])
                    if not m_ref.get().exists:
                        batch.set(m_ref, {"name": i['name'], "count": 1, "join_date": now, "last_active": now})
                    else:
                        batch.update(m_ref, {"count": firestore.Increment(1), "last_active": now})
                    batch.set(m_ref.collection("role_history").document(), {"role": i['role'], "ts": now})
                batch.commit()
                st.success("🔥 Đã đồng bộ Cloud!")
                del st.session_state['temp_data']
                st.rerun()

# --- TAB 2: THÀNH VIÊN ---
with t_members:
    docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    m_list = []
    for d in docs:
        m = d.to_dict()
        m_list.append({
            "IGN": m.get("name"),
            "Tổng Lượt": m.get("count", 0),
            "Tham Gia": m.get("join_date").strftime("%d/%m/%Y") if m.get("join_date") else "N/A",
            "Trạng Thái": "✅ ĐẠT" if m.get("count", 0) >= target_cta else "❌ CHƯA ĐẠT"
        })
    if m_list:
        df = pd.DataFrame(m_list)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("📥 Xuất file CSV", data=df.to_csv(index=False).encode('utf-8-sig'), file_name="GE_Guild_Report.csv")

# --- TAB 3: SỬA ĐIỂM ---
with t_admin:
    st.subheader("🛠️ Hiệu chỉnh Admin")
    all_names = [m['IGN'] for m in m_list] if 'm_list' in locals() and m_list else []
    target_edit = st.selectbox("Chọn người chơi:", all_names)
    if target_edit:
        curr_score = next(m['Tổng Lượt'] for m in m_list if m['IGN'] == target_edit)
        new_score = st.number_input(f"Sửa điểm cho {target_edit}:", min_value=0, value=curr_score)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🆙 Cập nhật"):
                db.collection("members").document(target_edit).update({"count": new_score})
                st.rerun()
        with col2:
            if st.button(f"🗑️ Xóa vĩnh viễn {target_edit}"):
                db.collection("members").document(target_edit).delete()
                st.rerun()

# --- TAB 4: TỔNG KẾT (FULL BÁO CÁO) ---
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
            st.write(f"📅 **Gia nhập:** {j_date}")
            if roles:
                st.write("**Bảng Role:**")
                st.table(pd.Series(roles).value_counts())
        with c2:
            if roles:
                rc = pd.Series(roles).value_counts().to_dict()
                role_summary = ", ".join([f"{k} ({v})" for k, v in rc.items()])
                status = "ĐẠT" if info.get('count', 0) >= target_cta else "CHƯA ĐẠT"
                report_text = f"⚔️ **GE GUILD REPORT** ⚔️\n👤 IGN: **{target_rep}**\n🗓️ Tham gia: {j_date}\n🔥 Tổng: {info.get('count', 0)} ({status})\n📊 Role: {role_summary}\n*Quản lý bởi TruongNET*"
                st.text_area("📋 Copy báo cáo:", value=report_text, height=200)
