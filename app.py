import streamlit as st
import pandas as pd
import json
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ————————————————
# DEBUG: Mostrar todo st.secrets
# ————————————————
st.sidebar.title("🔧 Debug Secrets")
st.sidebar.subheader("Keys disponibles:")
st.sidebar.write(list(st.secrets.keys()))

# Si existe service_account, mostrar el tipo y un preview
if "service_account" in st.secrets:
    sa = st.secrets["service_account"]
    st.sidebar.subheader("service_account (raw):")
    st.sidebar.code(sa[:200] + "…")
    try:
        sa_json = json.loads(sa)
        st.sidebar.success("service_account parseable JSON")
        st.sidebar.write({k: v for k, v in sa_json.items() if k != "private_key"})
    except Exception as e:
        st.sidebar.error(f"JSON parse error: {e}")

# Mostrar firebase_storage_bucket si existe
if "firebase_storage_bucket" in st.secrets:
    st.sidebar.subheader("firebase_storage_bucket:")
    st.sidebar.write(st.secrets["firebase_storage_bucket"])
else:
    st.sidebar.error("No hay firebase_storage_bucket en secrets")

# ————————————————
# Inicialización de Firebase
# ————————————————
if not firebase_admin._apps:
    try:
        # Cargar credenciales desde service_account JSON
        sa_json = json.loads(st.secrets["service_account"])
        cred = credentials.Certificate(sa_json)
        firebase_admin.initialize_app(cred, {
            "storageBucket": st.secrets["firebase_storage_bucket"]
        })
        st.sidebar.success("Firebase inicializado OK")
    except Exception as e:
        st.sidebar.error("Error inicializando Firebase:")
        st.sidebar.error(e)
        st.stop()

db = firestore.client()
bucket = storage.bucket()

# ————————————————
# Paso 1: Importación inicial
# ————————————————
accounts_ref = db.collection("accounts")
if not accounts_ref.limit(1).get():
    st.title("🚀 Importar base de datos inicial")
    uploaded = st.file_uploader("Selecciona tu Excel (.xlsx)", type="xlsx")
    if uploaded and st.button("Importar base"):
        df = pd.read_excel(uploaded)
        st.write("Columnas encontradas:", df.columns.tolist())
        for _, row in df.iterrows():
            data = row.to_dict()
            acct = str(data.get("Account", "")).strip()
            if acct:
                accounts_ref.document(acct).set(data)
        st.success("Importación completada. Recarga para continuar.")
    st.stop()

# ————————————————
# Paso 2: App principal
# ————————————————
st.sidebar.title("Control de cuentas")
role = st.sidebar.selectbox("Perfil", ["Filler", "Reviewer"])

# Cargar cuentas
accounts = {doc.id: doc.to_dict() for doc in accounts_ref.stream()}
st.sidebar.subheader("Cantidad de cuentas:")
st.sidebar.write(len(accounts))

selected = st.sidebar.selectbox("Selecciona cuenta", sorted(accounts.keys()))
data = accounts[selected]

# Layout
col1, col2, col3 = st.columns([1, 3, 2])
with col2:
    st.header(f"Cuenta: {selected}")
    for f in ["Assigned Reviewer","Cluster","Balance in EUR at 31/3","Comments / Risk / Exposure"]:
        st.subheader(f)
        st.write(data.get(f, "-"))

with col3:
    st.header("Chat & Revisión")
    comments = list(db.collection("comments")
                   .where("account_id","==",selected)
                   .order_by("timestamp")
                   .stream())
    st.write(f"Comentarios encontrados: {len(comments)}")
    for cdoc in comments:
        c = cdoc.to_dict()
        ts = c["timestamp"].strftime("%Y-%m-%d %H:%M")
        st.markdown(f"**{c['user']}** *({ts})* — {c['text']}")
        if c.get("status"):
            st.caption(f"Status: {c['status']}")

    new = st.text_area("Comentario")
    st_status = st.selectbox("Status", ["","On hold","Approved"])
    if st.button("Enviar"):
        if new.strip():
            db.collection("comments").add({
                "account_id": selected,
                "user": role,
                "text": new.strip(),
                "status": st_status,
                "timestamp": datetime.utcnow()
            })
            st.experimental_rerun()

# Adjuntos
st.markdown("---")
st.header("Adjuntar conciliación")
uf = st.file_uploader("Archivo (.xlsx,.pdf,.docx)", type=["xlsx","pdf","docx"])
if uf and st.button("Subir"):
    blob = bucket.blob(f"{selected}/{uf.name}")
    blob.upload_from_string(uf.getvalue(), content_type=uf.type)
    st.success("Archivo subido.")
