import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ————————————————
# DEBUG: Mostrar claves de secrets disponibles
# ————————————————
st.sidebar.subheader("🔧 Debug Secrets")
secret_keys = list(st.secrets.keys())
st.sidebar.write("Secciones cargadas en st.secrets:", secret_keys)

# Comprueba si tus secciones existen
has_cred = "firebase" in st.secrets or "firebase_credentials" in st.secrets
st.sidebar.write("Encontró sección de credenciales:", has_cred)

# ————————————————
# Inicialización de Firebase con manejo de errores
# ————————————————
def init_firebase():
    # Ajusta esto según la sección que estés usando
    section = "firebase_credentials" if "firebase_credentials" in st.secrets else "firebase"
    st.sidebar.write(f"Usando sección de secrets: `{section}`")
    config = st.secrets[section]
    st.sidebar.write("Tipo de config:", type(config))

    try:
        # Si viene como AttrDict, convertir a dict
        cfg = config.to_dict() if hasattr(config, "to_dict") else config
        # DEBUG: mostrar campos críticos (sin private_key completo)
        st.sidebar.write("project_id:", cfg.get("project_id"))
        st.sidebar.write("client_email:", cfg.get("client_email"))
        st.sidebar.write("private_key_id:", cfg.get("private_key_id"))

        cred = credentials.Certificate(cfg)
        # Inicializar app si no existe
        if not firebase_admin._apps:
            bucket_name = st.secrets.get("firebase_storage_bucket", "<no bucket>")
            st.sidebar.write("storageBucket:", bucket_name)
            firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})
        st.sidebar.success("Firebase inicializado correctamente")
        return firestore.client(), storage.bucket()
    except Exception as e:
        st.sidebar.error("Error al inicializar Firebase:")
        st.sidebar.error(e)
        st.stop()

# Inicializamos y capturamos db y bucket
db, bucket = init_firebase()

# ————————————————
# Sidebar: perfil y carga de archivo
# ————————————————
st.sidebar.title("Control de cuentas")
role = st.sidebar.selectbox("Selecciona tu perfil", ["Filler", "Reviewer"])
excel_file = st.sidebar.file_uploader("Carga el archivo de cuentas (.xlsx)", type=["xlsx"])

if not excel_file:
    st.sidebar.warning("Por favor carga el archivo de cuentas para continuar.")
    st.stop()

# ————————————————
# Lectura de Excel y selección de cuenta
# ————————————————
try:
    df = pd.read_excel(excel_file)
    st.sidebar.success("Excel leído correctamente")
except Exception as e:
    st.sidebar.error("Error al leer Excel:")
    st.sidebar.error(e)
    st.stop()

if "Account" not in df.columns:
    st.error("La columna 'Account' NO existe en el archivo")
    st.stop()

accounts = df["Account"].unique().tolist()
selected = st.sidebar.selectbox("Seleccione cuenta", accounts)
account_data = df[df["Account"] == selected].iloc[0]

# ————————————————
# Layout principal
# ————————————————
col1, col2, col3 = st.columns([1, 3, 2])

with col2:
    st.header(f"Cuenta: {selected}")
    for field in ["Assigned Reviewer", "Cluster", "Balance in EUR at 31/3", "Comments / Risk / Exposure"]:
        st.subheader(field)
        st.write(account_data.get(field, "-"))

# ————————————————
# Zona de chat / revisión
# ————————————————
with col3:
    st.subheader("Revisión & Chat")
    try:
        comments_ref = db.collection("comments").where("account_id", "==", selected).order_by("timestamp")
        for doc in comments_ref.stream():
            c = doc.to_dict()
            ts = c["timestamp"].strftime("%Y-%m-%d %H:%M")
            st.markdown(f"**{c['user']}** *({ts})* — {c['text']}")
            if c.get("status"):
                st.caption(f"Status: {c['status']}")
    except Exception as e:
        st.error("Error al cargar comentarios:")
        st.error(e)

    new_comment = st.text_area("Agregar nuevo comentario:")
    status = st.selectbox("Cambiar status de conciliación", ["", "On hold", "Approved"])
    if st.button("Enviar comentario"):
        if new_comment.strip():
            try:
                db.collection("comments").add({
                    "account_id": selected,
                    "user": role,
                    "text": new_comment.strip(),
                    "status": status,
                    "timestamp": datetime.utcnow()
                })
                st.success("Comentario enviado")
                st.experimental_rerun()
            except Exception as e:
                st.error("Error al guardar comentario:")
                st.error(e)

# ————————————————
# Zona de adjuntos
# ————————————————
st.markdown("---")
st.header("Adjuntar conciliación finalizada")
uploaded_file = st.file_uploader("Selecciona el archivo", type=["xlsx", "pdf", "docx"])
if uploaded_file and st.button("Subir documento"):
    try:
        blob = bucket.blob(f"{selected}/{uploaded_file.name}")
        blob.upload_from_string(uploaded_file.getvalue(), content_type=uploaded_file.type)
        st.success("Archivo subido exitosamente.")
    except Exception as e:
        st.error("Error al subir documento:")
        st.error(e)
