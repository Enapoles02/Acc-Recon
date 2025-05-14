# app.py
import streamlit as st

# 1) Configuración de página
st.set_page_config(page_title="🔌 Test Conexión Firebase", layout="centered")
st.title("🔌 Test de Conexión a Firebase")
st.markdown("Pulsa el botón para comprobar si tu app se conecta correctamente a Firebase.")

# 2) Botón para lanzar el diagnóstico
if st.button("▶️ Probar conexión"):
    with st.spinner("Intentando conectar a Firebase…"):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            # 3) Carga de credenciales desde secrets.toml
            creds = st.secrets["firebase_credentials"]
            creds_dict = creds.to_dict() if hasattr(creds, "to_dict") else creds

            # 4) Inicializar sólo una vez
            if not firebase_admin._apps:
                cred = credentials.Certificate(creds_dict)
                firebase_admin.initialize_app(cred)

            # 5) Operación mínima para validar la conexión
            db = firestore.client()
            _ = db.collections()

            st.success("✅ Conectado a Firebase correctamente")
        except Exception as e:
            st.error("❌ No se pudo conectar a Firebase:")
            st.code(str(e))

# 6) Si quieres ver los logs de errores más detallados
st.info("Si sigue en blanco, revisa los logs en ‘Manage app’ y asegúrate de que:\n"
        "1. Has añadido correctamente tu `[firebase_credentials]` en la sección de Secrets de Streamlit Cloud.\n"
        "2. Tu `requirements.txt` incluye:\n"
        "```txt\n"
        "streamlit>=1.18.0\n"
        "firebase-admin>=5.2.0\n"
        "```")
