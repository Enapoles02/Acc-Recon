import streamlit as st
import json
import traceback
from firebase_admin import credentials, firestore, storage, initialize_app, _apps
import firebase_admin

st.title("🔧 Ultra-Debug Firebase Creds")

raw = st.secrets.get("service_account", "")
st.subheader("1) Raw service_account (repr 300 chars)")
st.code(repr(raw)[:300] + "…", language="python")

# 2) Parse JSON
st.subheader("2) Parse JSON")
try:
    sa_info = json.loads(raw)
    st.success("✅ JSON válido")
    st.write("Claves encontradas:", list(sa_info.keys()))
except Exception as e:
    st.error("❌ Error parseando JSON:")
    st.error(str(e))
    st.text(traceback.format_exc())
    st.stop()

# 3) Detalles de private_key sin modificar
pk = sa_info.get("private_key", "")
st.subheader("3) Detalles ORIGINAL private_key")
st.write("Tipo:", type(pk), "Longitud:", len(pk))
lines = pk.splitlines()
st.write("Líneas totales:", len(lines))
st.write("Encabezado:", lines[0])
st.write("Footer:", lines[-1])

# 4) Limpieza: quitar indentación y asegurar saltos de línea
clean_lines = [line.strip() for line in lines if line.strip() != ""]
clean_pk = "\n".join(clean_lines) + "\n"
sa_info["private_key"] = clean_pk

st.subheader("4) private_key tras limpieza")
cl = clean_pk.splitlines()
st.write("Encabezado:", cl[0])
st.write("Footer:", cl[-1])
st.write("Líneas totales tras limpieza:", len(cl))

# 5) Intentar Certificate() ANTES y DESPUÉS de la limpieza
st.subheader("5) Probar credentials.Certificate")

# 5a) Sin limpieza (reconstruir de antes)
try:
    credentials.Certificate({**sa_info, "private_key": "\n".join(lines) + "\n"})
    st.warning("⚠️ Sin limpieza PASÓ (sorprendente)")
except Exception as e:
    st.info("🔍 Sin limpieza falló como antes:")
    st.error(str(e))

# 5b) Con limpieza
try:
    cred = credentials.Certificate(sa_info)
    st.success("✅ Con limpieza funcionó correctamente")
    # Inicializar solo para confirmar
    if not _apps:
        initialize_app(cred, {"storageBucket": st.secrets["firebase_storage_bucket"]})
    st.success("🔥 Firebase SDK inicializado")
except Exception as e:
    st.error("❌ Con limpieza SIGUE fallando:")
    st.error(str(e))
    st.text(traceback.format_exc())
    st.stop()

# 6) Conexión Firestore y Storage
db = firestore.client()
bucket = storage.bucket()
st.success("🚀 ¡Todo listo! Firestore y Storage conectados.")
