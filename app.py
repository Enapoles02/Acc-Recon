import streamlit as st
import firebase_admin
from firebase_admin import credentials, storage

st.set_page_config(page_title="Subida a Firebase", page_icon="📁")
st.title("📤 Subir archivo a Firebase Storage")

# Leer credenciales del secret
firebase_creds = st.secrets["firebase_credentials"]
if hasattr(firebase_creds, "to_dict"):
    firebase_creds = firebase_creds.to_dict()

# Verificar bucket desde secrets
bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]
st.info(f"📦 Usando bucket: `{bucket_name}`")

# Inicializar Firebase si no está activo
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_creds)
    firebase_admin.initialize_app(cred, {
        "storageBucket": bucket_name
    })

# Subir archivo
uploaded_file = st.file_uploader("Selecciona un archivo para subir", type=None)

if uploaded_file:
    try:
        bucket = storage.bucket()
        blob_path = f"reconciliation_records/{uploaded_file.name}"
        blob = bucket.blob(blob_path)
        blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)

        st.success(f"✅ Archivo '{uploaded_file.name}' subido correctamente.")
        public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_path}"
        st.markdown(f"🔗 [Ver archivo en Storage]({public_url})")

    except Exception as e:
        st.error(f"❌ Error al subir: {e}")
