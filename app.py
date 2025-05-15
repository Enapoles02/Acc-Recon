import streamlit as st
import firebase_admin
from firebase_admin import credentials, storage

# Obtener credenciales del secrets.toml
firebase_creds = st.secrets["firebase_credentials"]
if hasattr(firebase_creds, "to_dict"):
    firebase_creds = firebase_creds.to_dict()

# Inicializar Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_creds)
    firebase_admin.initialize_app(cred, {
        "storageBucket": st.secrets["firebase_bucket"]["firebase_bucket"]
    })

# Probar acceso al bucket
bucket = storage.bucket()
blob = bucket.blob("test.txt")
blob.upload_from_string("Hola desde Streamlit y Firebase Storage!")

st.success("✅ Archivo subido correctamente al bucket.")
