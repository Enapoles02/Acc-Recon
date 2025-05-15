import streamlit as st
import firebase_admin
from firebase_admin import credentials, storage

st.set_page_config(page_title="Subida a Firebase", page_icon="📁")
st.title("📤 Subir archivo a Firebase Storage")

# Cargar credenciales del secret
firebase_creds = st.secrets["firebase_credentials"]
if hasattr(firebase_creds, "to_dict"):
    firebase_creds = firebase_creds.to_dict()

# Mostrar bucket actual (debug visual)
bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]
st.info(f"📦 Usando bucket: `{bucket_name}`")

# Inicializar Firebase si no está ya inicializado
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_creds)
    firebase_admin.initialize_app(cred, {
        "storageBucket": bucket_name
    })

# Uploader de archivo
uploaded_file = st.file_uploader("Selecciona un archivo para subir", type=None)

if uploaded_file:
    # Subida a la carpeta reconciliation_records/
    bucket = storage.bucket()
    blob_path = f"reconciliation_records/{uploaded_file.name}"
    blob = bucket.blob(blob_path)
    
    # Subir contenido
    blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)

    # Confirmación
    st.success(f"✅ Archivo '{uploaded_file.name}' subido correctamente.")
    
    # Generar URL pública (si tienes reglas abiertas)
    public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_path}"
    st.markdown(f"🔗 [Ver archivo en Storage]({public_url})")
