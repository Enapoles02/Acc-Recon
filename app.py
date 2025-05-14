import streamlit as st
import pandas as pd
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ————————————————
# Inicialización de Firebase
# ————————————————
if not firebase_admin._apps:
    cred = credentials.Certificate(st.secrets["firebase"])
    firebase_admin.initialize_app(cred, {
        "storageBucket": st.secrets["firebase_storage_bucket"]
    })

db = firestore.client()
# Usar explícitamente el nombre de bucket desde secrets
bucket = storage.bucket(st.secrets["firebase_storage_bucket"])

# ————————————————
# Paso 1: Importación inicial de la base de datos
# ————————————————
accounts_ref = db.collection("accounts")
if not accounts_ref.limit(1).get():
    st.title("🚀 Importar base de datos inicial")
    st.write("Carga tu archivo Excel con la lista de cuentas y responsables.")
    uploaded = st.file_uploader("Selecciona el .xlsx", type="xlsx")
    if uploaded and st.button("Importar base"):
        try:
            df = pd.read_excel(uploaded)
            for _, row in df.iterrows():
                data = row.to_dict()
                account_id = str(data.get("Account", "")).strip()
                if account_id:
                    accounts_ref.document(account_id).set(data)
            st.success("📥 Base importada correctamente. Recarga la página para continuar.")
        except Exception as e:
            st.error(f"Error importando base: {e}")
    st.stop()

# ————————————————
# Paso 2: App principal
# ————————————————
st.sidebar.title("Control de cuentas")
role = st.sidebar.selectbox("Perfil", ["Filler", "Reviewer"])

# Cargar cuentas desde Firestore
docs = accounts_ref.stream()
accounts = {doc.id: doc.to_dict() for doc in docs}
selected = st.sidebar.selectbox("Selecciona cuenta", list(accounts.keys()))
account_data = accounts[selected]

# ————————————————
# Detalles de la cuenta
# ————————————————
col1, col2, col3 = st.columns([1, 3, 2])
with col2:
    st.header(f"Cuenta: {selected}")
    for field in ["Assigned Reviewer", "Cluster", "Balance in EUR at 31/3", "Comments / Risk / Exposure"]:
        st.subheader(field)
        st.write(account_data.get(field, "-"))

# ————————————————
# Chat de revisión
# ————————————————
with col3:
    st.subheader("Revisión & Chat")
    for doc in db.collection("comments") \
                 .where("account_id", "==", selected) \
                 .order_by("timestamp") \
                 .stream():
        c = doc.to_dict()
        ts = c["timestamp"].strftime("%Y-%m-%d %H:%M")
        st.markdown(f"**{c['user']}** *({ts})* — {c['text']}")
        if c.get("status"):
            st.caption(f"Status: {c['status']}")

    new_comment = st.text_area("Agregar comentario:")
    status = st.selectbox("Status", ["", "On hold", "Approved"])
    if st.button("Enviar comentario"):
        if new_comment.strip():
            db.collection("comments").add({
                "account_id": selected,
                "user": role,
                "text": new_comment.strip(),
                "status": status,
                "timestamp": datetime.utcnow()
            })
            st.success("Comentario enviado")
            st.experimental_rerun()

# ————————————————
# Adjuntar conciliación final
# ————————————————
st.markdown("---")
st.header("Adjuntar archivo de conciliación")
uploaded_file = st.file_uploader("Selecciona archivo (.xlsx, .pdf, .docx)", type=["xlsx","pdf","docx"])
if uploaded_file and st.button("Subir documento"):
    blob = bucket.blob(f"{selected}/{uploaded_file.name}")
    blob.upload_from_string(
        uploaded_file.getvalue(),
        content_type=uploaded_file.type
    )
    st.success("Archivo subido exitosamente.")
