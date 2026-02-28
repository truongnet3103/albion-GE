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
st.set_page_config(page_title="GE Guild Admin - TRUONGNET System", layout="wide", page_icon="🛡️")

# --- 2. KẾT NỐI FIREBASE ---
if not firebase_admin._apps:
    try:
        sd = dict(st.secrets["firebase"])
        if "\\n" in sd["private_key"]: sd["private_key"] = sd["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(sd)
        firebase_admin.initialize_app(cred)
    except Exception as e: st.error(f"Lỗi kết nối Firebase: {e}")

db = firestore.client()

# --- 3. HÀM LẤY CẤU HÌNH HỆ THỐNG (API & LICENSE) ---
def get_system_config():
    # Lấy API Key bí mật
    api_doc = db.collection("system_config").document("gemini_api").get()
    api_key = api_doc.to_dict().get("key", "") if api_doc.exists else ""
    return api_key

def verify_license(code):
    # Kiểm tra mã License trên Firebase
    if not code: return False
    lic_doc = db.collection("licenses").document(code).get()
    if lic_doc.exists:
        data = lic_doc.to_dict()
        # Kiểm tra xem mã còn hiệu lực không (status: True/False)
        return data.get("active", False)
    return False

# --- 4. SIDEBAR QUẢN TRỊ ---
with st.sidebar:
    st.title("🛡️ GE PREMIUM PANEL")
    
    # NHẬP LICENSE
    user_license = st.text_input("🔑 Nhập mã License:", type="password")
    is_valid = verify_license(user_license)
    
    if is_valid:
        st.success("✅ Bản quyền hợp lệ!")
    elif user_license:
        st.error("❌ Mã sai hoặc hết hạn. Liên hệ **TruongNET**.")

    st.divider()
    
    # Cài đặt chỉ tiêu
    target_cta = st.number_input("🎯 Chỉ tiêu chuyên cần:", min_value=1, value=10)
    
    st.divider()
    
    # Quản lý Mốc (History Events)
    st.subheader("📅 Quản lý Mốc")
    new_m = st.text_input("Tên mốc mới (VD: 18UTC-01/03):")
    if st.button("✨ Tạo mốc") and is_valid:
        if new_m:
            db.collection("cta_events").document(new_m).set({"name": new_m, "ts": firestore.SERVER_TIMESTAMP})
            st.rerun()

    cta_docs = db.collection("cta_events").order_by("ts", direction=firestore.Query.DESCENDING).limit(30).stream()
    cta_list = [d.id for d in cta_docs]
    sel_cta = st.selectbox("📌 Mốc đang chọn:", cta_list) if cta_list else "Chưa có mốc"

# --- 5. GIAO DIỆN CHÍNH (TABS) ---
t_check, t_members, t_admin, t_summary = st.tabs(["🚀 QUÉT AI", "👥 THÀNH VIÊN", "🛠️ QUẢN TRỊ ĐIỂM", "📊 BÁO CÁO"])

# --- TAB 1: QUÉT AI (GIỮ NGUYÊN LOGIC BẢO MẬT API) ---
with t_check:
    if not is_valid:
        st.warning("Vui lòng kích hoạt License để sử dụng.")
    else:
        up = st.file_uploader("Upload ảnh Party List", type=["jpg", "png", "jpeg"])
        if up:
            img = Image.open(up)
            st.image(img, width=400)
            if st.button("🪄 CHẠY AI SCAN", type="primary"):
                api_key = get_system_config()
                if not api_key: st.error("Lỗi hệ thống (API). Liên hệ TruongNET.")
                else:
                    with st.spinner("AI đang làm việc..."):
                        try:
                            genai.configure(api_key=api_key)
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            prompt = "Extract IGN and ONE role: Tank, Healer, Melee, Ranged, Support. JSON: [{'name': '...', 'role': '...'}]"
                            res = model.generate_content([prompt, img])
                            clean = re.search(r'\[.*\]', res.text.replace('```json', '').replace('```', ''), re.DOTALL)
                            if clean:
                                st.session_state['temp_data'] = json.loads(clean.group())
                        except: st.error("Hệ thống bảo trì. Liên hệ TruongNET.")

        if 'temp_data' in st.session_state:
            edited = st.data_editor(st.session_state['temp_data'], num_rows="dynamic", use_container_width=True)
            if st.button("💾 LƯU DỮ LIỆU"):
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
                st.success("Đã lưu điểm thành công!")
                del st.session_state['temp_data']
                st.rerun()

# --- TAB 2: DANH SÁCH THÀNH VIÊN (VIEWER) ---
with t_members:
    m_docs = db.collection("members").order_by("count", direction=firestore.Query.DESCENDING).stream()
    m_list = []
    for m in m_docs:
        d = m.to_dict()
        m_list.append({
            "IGN": d.get("name"), 
            "Tổng Lượt": d.get("count", 0), 
            "Ngày Tham Gia": d.get("join_date").strftime("%d/%m/%Y") if d.get("join_date") else "N/A",
            "Trạng Thái": "✅ ĐẠT" if d.get("count", 0) >= target_cta else "❌ CHƯA ĐẠT"
        })
    if m_list:
        df_members = pd.DataFrame(m_list)
        st.dataframe(df_members, use_container_width=True, hide_index=True)
        # Nút xuất Excel cho cả Guild
        csv = df_members.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Tải Bảng Điểm Toàn Guild (CSV)", data=csv, file_name=f"GE_Guild_Points_{datetime.now().date()}.csv")

# --- TAB 3: QUẢN TRỊ ĐIỂM (EDIT/DELETE) ---
with t_admin:
    st.subheader("🛠️ Chỉnh sửa thủ công (Chỉ dành cho Admin)")
    if is_valid:
        target_edit = st.selectbox("Chọn thành viên cần sửa:", [m['IGN'] for m in m_list] if 'm_list' in locals() else [])
        if target_edit:
            col1, col2 = st.columns(2)
            with col1:
                new_score = st.number_input("Sửa tổng số lượt tham gia:", min_value=0, value=next(m['Tổng Lượt'] for m in m_list if m['IGN'] == target_edit))
                if st.button("🆙 Cập nhật điểm"):
                    db.collection("members").document(target_edit).update({"count": new_score})
                    st.success(f"Đã sửa điểm cho {target_edit}")
                    st.rerun()
            with col2:
                st.warning("Hành động xóa không thể hoàn tác!")
                if st.button(f"🗑️ Xóa vĩnh viễn {target_edit}"):
                    db.collection("members").document(target_edit).delete()
                    st.success(f"Đã xóa {target_edit}")
                    st.rerun()
    else:
        st.error("Tính năng này yêu cầu License.")

# --- TAB 4: BÁO CÁO CHI TIẾT ---
with t_summary:
    target_rep = st.selectbox("Xem báo cáo cá nhân:", [m['IGN'] for m in m_list] if 'm_list' in locals() else [])
    if target_rep:
        m_info = db.collection("members").document(target_rep).get().to_dict()
        r_docs = db.collection("members").document(target_rep).collection("role_history").stream()
        r_list = [r.to_dict()['role'] for r in r_docs]
        raw_date = m_info.get('join_date'); fmt_date = raw_date.strftime('%d/%m/%Y') if raw_date else "N/A"
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Tổng tham gia", f"{m_info.get('count', 0)} lần")
            if r_list: st.table(pd.Series(r_list).value_counts())
        with c2:
            if r_list:
                rc = pd.Series(r_list).value_counts().to_dict(); role_str = ", ".join([f"{k} ({v})" for k, v in rc.items()]); status = "ĐẠT" if m_info.get('count', 0) >= target_cta else "CHƯA ĐẠT"
                report = f"⚔️ **GE GUILD REPORT** ⚔️\n👤: **{target_rep}**\n🗓️ Tham gia từ: {fmt_date}\n🔥 Tổng lượt: {m_info.get('count', 0)}\n🎯 Chỉ tiêu: {target_cta} ({status})\n📊 Chi tiết Role: {role_str}\n━━━━━━━━━━━━━━━━━━━━"
                st.text_area("📋 Copy nội dung:", value=report, height=220)
