# app.py
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(page_title="Test Conexión Firebase", layout="centered")
st.title("🔌 Test de Conexión a Firebase")

# 1) Cargar credenciales desde secrets.toml
creds = st.secrets["firebase_credentials"]
# En algunos entornos st.secrets devuelve un AttrDict:
creds_dict = creds.to_dict() if hasattr(creds, "to_dict") else creds

# 2) Intentar inicializar la app de Firebase
try:
    # Si ya hay una app inicializada, la reutiliza
    if not firebase_admin._apps:
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred)
    # Crear cliente de Firestore solo para confirmar que funciona
    db = firestore.client()
    # Intentar una operación simple: listar colecciones (sin leer datos sensibles)
    _ = db.collections()
    st.success("✅ Conectado a Firebase correctamente")
except Exception as e:
    st.error("❌ No se pudo conectar a Firebase:")
    st.write(f"```\n{e}\n```")
