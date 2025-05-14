import streamlit as st
import json
import traceback
from firebase_admin import credentials

st.title("🔧 Deep Debug Firebase Creds")

# Mostrar raw service_account
raw = st.secrets.get("service_account")
st.subheader("service_account raw repr (prim. 300 chars):")
st.code(repr(raw)[:300] + "…", language="python")

# Intentar parsear JSON
st.subheader("Parse JSON de service_account")
try:
    sa_info = json.loads(raw)
    st.success("✅ JSON parseado correctamente")
    st.write("Claves JSON:", list(sa_info.keys()))
except Exception as e:
    st.error("❌ Error al parsear JSON:")
    st.error(str(e))
    st.text(traceback.format_exc())
    st.stop()

# Analizar private_key
pk = sa_info.get("private_key")
st.subheader("Detalle de private_key")
st.write("Tipo de private_key:", type(pk))
if isinstance(pk, str):
    st.write("Longitud de private_key:", len(pk))
    lines = pk.split("\\n") if "\\n" in pk else pk.split("\n")
    st.write("Primeras 3 líneas de private_key:")
    for line in lines[:3]:
        st.code(line)
    st.write("Últimas 3 líneas de private_key:")
    for line in lines[-3:]:
        st.code(line)

# Intentar crear credencial
st.subheader("Inicializar credentials.Certificate()")
try:
    cred = credentials.Certificate(sa_info)
    st.success("✅ credentials.Certificate() funcionó correctamente")
except Exception as e:
    st.error("❌ credentials.Certificate falló:")
    st.error(str(e))
    st.text(traceback.format_exc())
    st.stop()

st.success("✅ ¡Todo parece correcto con las credenciales!")
