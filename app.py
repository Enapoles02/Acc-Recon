import streamlit as st
import firebase_admin
from firebase_admin import credentials, storage

st.set_page_config(page_title="Firebase Upload Test", page_icon="📁")

st.title("📤 Subir archivo a Firebase Storage")

# Leer credenciales del secrets.toml
firebase_creds = st.secrets["firebase_credentials"]
if hasattr(firebase_creds, "to_dict"):
    firebase_creds = firebase_creds.to_dict()

# Inicializar Firebase solo una vez
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_creds)
    firebase_admin.initialize_app(cred, {
        "storageBucket": st.secrets["firebase_bucket"]["firebase_bucket"]
    })

# Interfaz para subir archivo
uploaded_file = st.file_uploader("Selecciona un archivo para subir a Firebase", type=None)

if uploaded_file:
    bucket = storage.bucket()
    blob_path = f"reconciliation_records/{uploaded_file.name}"
    blob = bucket.blob(blob_path)
    blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)

    # Mostrar éxito y link
    st.success(f"✅ Archivo '{uploaded_file.name}' subido correctamente.")
    public_url = f"https://storage.googleapis.com/{st.secrets['firebase_bucket']['firebase_bucket']}/{blob_path}"
    st.markdown(f"🔗 [Ver archivo en Storage]({public_url})")
