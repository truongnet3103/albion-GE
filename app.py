import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

# Khởi tạo Firebase từ Secrets
if not firebase_admin._apps:
    # Chuyển đổi secrets sang dictionary
    secret_dict = dict(st.secrets["firebase"])
    # Fix lỗi xuống dòng của key
    secret_dict["private_key"] = secret_dict["private_key"].replace("\\n", "\n")
    
    cred = credentials.Certificate(secret_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

st.success("Kết nối Firebase thành công rực rỡ! 🚀")
