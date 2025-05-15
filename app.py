import streamlit as st
import datetime
import firebase_admin
from firebase_admin import credentials, storage

# Configurar layout antes de cualquier otra llamada Streamlit
st.set_page_config(layout="centered")

# Inicializar Firebase
@st.cache_resource
def init_firebase():
    st.write("🔧 Inicializando Firebase...")
    raw = st.secrets.get("firebase_credentials")
    if isinstance(raw, str):
        import json
        cred_dict = json.loads(raw)
    else:
        cred_dict = raw.to_dict() if hasattr(raw, "to_dict") else raw

    bucket_raw = st.secrets.get("firebase_bucket")
    if not bucket_raw:
        st.error("❌ `firebase_bucket` no definido en secrets.")
        st.stop()

    bucket_name = bucket_raw.removeprefix("gs://")
    st.write(f"📦 Usando bucket: `{bucket_name}`")

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(cred_dict),
            {"storageBucket": bucket_name}
        )
    return storage.bucket()

# Verificación
def test_bucket(bucket):
    st.write(f"✅ Conectado a bucket real: `{bucket.name}`")

    test_blob = bucket.blob("debug/test-upload.txt")
    content = f"Archivo de prueba generado: {datetime.datetime.utcnow()}"
    test_blob.upload_from_string(content)

    st.success("🎉 Archivo de prueba subido correctamente.")
    url = test_blob.generate_signed_url(datetime.timedelta(minutes=10))
    st.markdown(f"[🔗 Ver archivo en el bucket]({url})")

# Main
st.title("🧪 Depurador de Firebase Bucket")
try:
    bucket = init_firebase()
    test_bucket(bucket)
except Exception as e:
    st.error(f"🚨 Error accediendo al bucket:\n```\n{e}\n```")
