import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ————————————————
# Inicialización de Firebase
# ————————————————
if not firebase_admin._apps:
    creds_data = st.secrets["firebase_credentials"]
    creds = credentials.Certificate(
        creds_data.to_dict() if hasattr(creds_data, "to_dict") else creds_data
    )
    firebase_admin.initialize_app(creds, {
        "storageBucket": st.secrets["firebase_storage_bucket"]
    })

# Clientes de Firestore y Storage
db = firestore.client()
bucket = storage.bucket()

# ————————————————
# Sidebar: perfil y carga de archivo
# ————————————————
st.sidebar.title("Control de cuentas")
role = st.sidebar.selectbox("Selecciona tu perfil", ["Filler", "Reviewer"])
excel_file = st.sidebar.file_uploader("Carga el archivo de cuentas (.xlsx)", type=["xlsx"])

if not excel_file:
    st.sidebar.warning("Por favor carga el archivo de cuentas para continuar.")
    st.stop()

# Lectura de Excel y selección de cuenta
df = pd.read_excel(excel_file)
accounts = df["Account"].unique().tolist()
selected = st.sidebar.selectbox("Seleccione cuenta", accounts)
account_data = df[df["Account"] == selected].iloc[0]

# ————————————————
# Layout principal: tres columnas
# ————————————————
col1, col2, col3 = st.columns([1, 3, 2])

with col2:
    st.markdown(f"# {selected}")
    st.subheader("Assigned Reviewer")
    st.write(account_data["Assigned Reviewer"])
    st.subheader("Cluster")
    st.write(account_data["Cluster"])
    st.subheader("Balance in EUR at 31/3")
    st.write(account_data.get("Balance in EUR at 31/3", "-"))
    st.subheader("Comments / Risk / Exposure")
    st.write(account_data.get("Comments / Risk / Exposure", "-"))

# ————————————————
# Zona de chat / revisión
# ————————————————
with col3:
    st.markdown("## Revisión & Chat")
    comments_ref = (
        db.collection("comments")
          .where("account_id", "==", selected)
          .order_by("timestamp")
    )
    for doc in comments_ref.stream():
        c = doc.to_dict()
        ts = c["timestamp"].strftime("%Y-%m-%d %H:%M")
        st.markdown(f"**{c['user']}** *({ts})* — {c['text']}")
        if c.get("status"):
            st.caption(f"Status: {c['status']}")

    new_comment = st.text_area("Agregar nuevo comentario:")
    status = st.selectbox("Cambiar status de conciliación", ["", "On hold", "Approved"])
    if st.button("Enviar comentario"):
        if new_comment.strip():
            db.collection("comments").add({
                "account_id": selected,
                "user": role,
                "text": new_comment.strip(),
                "status": status,
                "timestamp": datetime.utcnow()
            })
            st.experimental_rerun()

# ————————————————
# Zona de adjuntos
# ————————————————
st.markdown("---")
st.markdown("## Adjuntar conciliación finalizada")
uploaded_file = st.file_uploader("Selecciona el archivo", type=["xlsx", "pdf", "docx"])
if uploaded_file:
    if st.button("Subir documento"):
        blob = bucket.blob(f"{selected}/{uploaded_file.name}")
        blob.upload_from_string(
            uploaded_file.getvalue(),
            content_type=uploaded_file.type
        )
        st.success("Archivo subido exitosamente.")
