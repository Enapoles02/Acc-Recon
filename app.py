import streamlit as st
import json

# ————————————————
# DEPURADOR: mostrar contenido de st.secrets
# ————————————————
st.sidebar.title("🔧 Debug Secrets")

# Listar todas las keys disponibles
st.sidebar.subheader("Keys disponibles en st.secrets:")
st.sidebar.write(list(st.secrets.keys()))

# Si existe 'service_account', mostrar los primeros 200 caracteres y parsear JSON
if "service_account" in st.secrets:
    raw = st.secrets["service_account"]
    st.sidebar.subheader("service_account (raw, primeros 200 chars):")
    st.sidebar.code(raw[:200] + "…")
    try:
        parsed = json.loads(raw)
        st.sidebar.success("✅ service_account es JSON válido")
        # Mostrar todos menos la clave privada
        preview = {k: v for k, v in parsed.items() if k != "private_key"}
        st.sidebar.write("Contenido parseado:", preview)
    except Exception as e:
        st.sidebar.error("❌ Error al parsear JSON:")
        st.sidebar.error(str(e))

# Mostrar el bucket configurado
if "firebase_storage_bucket" in st.secrets:
    st.sidebar.subheader("firebase_storage_bucket:")
    st.sidebar.write(st.secrets["firebase_storage_bucket"])
else:
    st.sidebar.error("❌ No está configurado 'firebase_storage_bucket' en secrets")
