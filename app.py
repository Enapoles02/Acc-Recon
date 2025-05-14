import streamlit as st
import pandas as pd
import json
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ————————————————
# DEPURADOR: mostrar contenido de st.secrets
# ————————————————
st.sidebar.title("🔧 Debug Secrets")
st.sidebar.subheader("Keys disponibles en st.secrets:")
st.sidebar.write(list(st.secrets.keys()))

if "service_account" in st.secrets:
    raw = st.secrets["service_account"]
    st.sidebar.subheader("service_account (raw, primeros 200 chars):")
    st.sidebar.code(raw[:200] + "…")
    try:
        parsed = json.loads(raw)
        st.sidebar.success("✅ service_account es JSON válido")
        preview = {k: v for k, v in parsed.items() if k != "private_key"}
        st.sidebar.write("Contenido parseado:", preview)
    except Exception as e:
        st.sidebar.error("❌ Error al parsear JSON:")
        st.sidebar.error(str(e))

if "firebase_storage_bucket" in st.secrets:
    st.sidebar.subheader("firebase_storage_bucket:")
    st.sidebar.write(st.secrets["firebase_storage_bucket"])
else:
    st.sidebar.error("❌ No está configurado 'firebase_storage_bucket' en secrets")

# ————————————————
# Inicialización de Firebase
# ————————————————
if not firebase_admin._apps:
    sa_info = json.loads(st.secrets["service_account"])
    cred = credentials.Certificate(sa_info)
    firebase_admin.initialize_app(cred, {
        "storageBucket": st.secrets["firebase_storage_bucket"]
    })
db = firestore.client()
bucket = storage.bucket()

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
            st.write("Columnas encontradas:", df.columns.tolist())
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
# Paso 2: App principal (modificar datos)
# ————————————————
st.sidebar.title("Control de cuentas")
role = st.sidebar.selectbox("Perfil", ["Filler", "Reviewer"])

accounts = {doc.id: doc.to_dict() for doc in accounts_ref.stream()}
selected = st.sidebar.selectbox("Selecciona cuenta", sorted(accounts.keys()))
account_data = accounts[selected]

col1, col2, col3 = st.columns([1, 3, 2])
with col2:
    st.header(f"Cuenta: {selected}")
    for field in ["Assigned Reviewer", "Cluster", "Balance in EUR at 31/3", "Comments / Risk / Exposure"]:
        st.subheader(field)
        st.write(account_data.get(field, "-"))

with col3:
    st.subheader("Revisión & Chat")
    for doc in (
        db.collection("comments")
          .where("account_id", "==", selected)
          .order_by("timestamp")
          .stream()
    ):
        c = doc.to_dict()
        ts = c["timestamp"].strftime("%Y-%m-%d %H:%M")
        st.markdown(f"**{c['user']}** *({ts})* — {c['text']}")
        if c.get("status"):
            st.caption(f"Status: {c['status']}")

    new = st.text_area("Agregar comentario:")
    status = st.selectbox("Status", ["", "On hold", "Approved"])
    if st.button("Enviar comentario"):
        if new.strip():
            db.collection("comments").add({
                "account_id": selected,
                "user": role,
                "text": new.strip(),
                "status": status,
                "timestamp": datetime.utcnow()
            })
            st.success("Comentario enviado")
            st.experimental_rerun()

st.markdown("---")
st.header("Adjuntar conciliación final")
uf = st.file_uploader("Archivo (.xlsx, .pdf, .docx)", type=["xlsx", "pdf", "docx"])
if uf and st.button("Subir documento"):
    try:
        blob = bucket.blob(f"{selected}/{uf.name}")
        blob.upload_from_string(uf.getvalue(), content_type=uf.type)
        st.success("Archivo subido exitosamente.")
    except Exception as e:
        st.error(f"Error subiendo archivo: {e}")
