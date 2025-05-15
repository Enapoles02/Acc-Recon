import streamlit as st
import firebase_admin
from firebase_admin import credentials, storage

# Configuración e inicialización de Firebase desde secrets.toml
creds = st.secrets["firebase_credentials"]
if hasattr(creds, "to_dict"):
    creds = creds.to_dict()

# Inicializa Firebase solo una vez
if not firebase_admin._apps:
    cred = credentials.Certificate(creds)
    firebase_admin.initialize_app(cred, {
        "storageBucket": st.secrets["firebase_bucket"]["firebase_bucket"]
    })

# Subida de archivo al bucket
bucket = storage.bucket()
blob = bucket.blob("reconciliation_records/test.txt")
blob.upload_from_string("Hola desde Streamlit y Firebase Storage!")

st.success("✅ Archivo subido correctamente al bucket.")
