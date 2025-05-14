import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ————————————————
# DEBUG: Mostrar qué secretos hay disponibles
# ————————————————
st.sidebar.subheader("🔧 Debug Secrets")
secret_keys = list(st.secrets.keys())
st.sidebar.write("Secciones cargadas en st.secrets:", secret_keys)

# ————————————————
# Inicialización de Firebase con debug y manejo de errores
# ————————————————
def init_firebase():
    # Determinar sección de credenciales
    section = "firebase_credentials" if "firebase_credentials" in st.secrets else "firebase"
    st.sidebar.write(f"Usando sección de secrets: `{section}`")
    config = st.secrets[section]
    st.sidebar.write("Tipo de config:", type(config))

    # Convertir a dict si es un AttrDict
    cfg = config.to_dict() if hasattr(config, "to_dict") else config
    # Mostrar campos esenciales (sin imprimir la clave completa)
    for key in ("project_id", "client_email", "private_key_id"):
        st.sidebar.write(f"{key}:", cfg.get(key))

    # Leer nombre de bucket
    bucket_name = st.secrets.get("firebase_storage_bucket")
    if bucket_name:
        st.sidebar.write("Storage bucket:", bucket_name)
    else:
        st.sidebar.error("❌ No encontré 'firebase_storage_bucket' en tus secrets")

    # Inicializar app de Firebase
    try:
        cred = credentials.Certificate(cfg)
        init_args = {}
        if bucket_name:
            init_args["storageBucket"] = bucket_name
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, init_args)
        st.sidebar.success("✅ Firebase SDK inicializado")
    except Exception as e:
        st.sidebar.error("❌ Error al inicializar Firebase SDK:")
        st.sidebar.error(e)
        st.stop()

    # Conectar Firestore
    try:
        db = firestore.client()
        st.sidebar.success("✅ Conexión a Firestore OK")
    except Exception as e:
        st.sidebar.error("❌ Error al conectar Firestore:")
        st.sidebar.error(e)
        st.stop()

    # Conectar Storage (opcional, solo si bucket existe)
    bucket = None
    if bucket_name:
        try:
            bucket = storage.bucket()
            st.sidebar.success("✅ Conexión a Storage OK")
        except Exception as e:
            st.sidebar.error("❌ Error al obtener bucket de Storage:")
            st.sidebar.error(e)

    return db, bucket

db, bucket = init_firebase()

# ————————————————
# Sidebar: perfil y carga de archivo
# ————————————————
st.sidebar.title("Control de cuentas")
role = st.sidebar.selectbox("Perfil", ["Filler", "Reviewer"])
excel_file = st.sidebar.file_uploader("Carga el archivo de cuentas (.xlsx)", type=["xlsx"])

if not excel_file:
    st.sidebar.warning("Carga el archivo para continuar.")
    st.stop()

# ————————————————
# Lectura de Excel y selección de cuenta
# ————————————————
try:
    df = pd.read_excel(excel_file)
    st.sidebar.success("✅ Excel leído correctamente")
except Exception as e:
    st.sidebar.error("❌ Error al leer Excel:")
    st.sidebar.error(e)
    st.stop()

if "Account" not in df.columns:
    st.error("La columna 'Account' no existe en tu Excel.")
    st.stop()

accounts = df["Account"].dropna().unique().tolist()
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
        for doc in db.collection("comments")\
                     .where("account_id", "==", selected)\
                     .order_by("timestamp")\
                     .stream():
            c = doc.to_dict()
            ts = c["timestamp"].strftime("%Y-%m-%d %H:%M")
            st.markdown(f"**{c['user']}** *({ts})* — {c['text']}")
            if c.get("status"):
                st.caption(f"Status: {c['status']}")
    except Exception as e:
        st.error("❌ Error al cargar comentarios:")
        st.error(e)

    new_comment = st.text_area("Nuevo comentario:")
    status = st.selectbox("Status", ["", "On hold", "Approved"])
    if st.button("Enviar"):
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
                st.error("❌ Error al guardar comentario:")
                st.error(e)

# ————————————————
# Zona de adjuntos
# ————————————————
st.markdown("---")
st.header("Adjuntar conciliación")
uploaded_file = st.file_uploader("Selecciona archivo", type=["xlsx", "pdf", "docx"])
if uploaded_file and st.button("Subir"):
    if bucket:
        try:
            blob = bucket.blob(f"{selected}/{uploaded_file.name}")
            blob.upload_from_string(uploaded_file.getvalue(), content_type=uploaded_file.type)
            st.success("Archivo subido")
        except Exception as e:
            st.error("❌ Error al subir archivo:")
            st.error(e)
    else:
        st.error("No hay bucket configurado; revisa tu secret 'firebase_storage_bucket'.")
