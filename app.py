import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore, storage
import uuid
import io
from datetime import datetime
import pytz

# ---------------- Configuracion inicial ----------------
st.set_page_config(page_title="Reconciliación GL", layout="wide")
st.title("📊 Dashboard de Reconciliación GL")

# ---------------- Autenticacion por usuario ----------------
user = st.sidebar.text_input("Usuario")

USER_COUNTRY_MAPPING = {
    "Paula Sarachaga": ["Argentina", "Chile", "Guatemala"],
    "Napoles Enrique": ["Canada"],
    "Julio": ["United States of America"],
    "Guadalupe": ["Mexico", "Peru", "Panama"],
    "ADMIN": "ALL"
}

if not user:
    st.warning("Ingresa tu nombre de usuario para continuar.")
    st.stop()

# ---------------- Inicializar Firebase ----------------
@st.cache_resource
def init_firebase():
    firebase_creds = st.secrets["firebase_credentials"]
    if hasattr(firebase_creds, "to_dict"):
        firebase_creds = firebase_creds.to_dict()
    bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})
    return firestore.client(), storage.bucket()

db, bucket = init_firebase()

# ---------------- Funciones ----------------
def load_data():
    docs = db.collection("reconciliation_records").stream()
    recs = []
    for d in docs:
        data = d.to_dict()
        flat_data = {"_id": d.id}
        for k, v in data.items():
            flat_data[str(k).strip()] = v
        recs.append(flat_data)
    return pd.DataFrame(recs)

def save_comment(doc_id, new_entry):
    doc_ref = db.collection("reconciliation_records").document(doc_id)
    doc = doc_ref.get()
    previous = doc.to_dict().get("comment", "") if doc.exists else ""
    updated = f"{previous}\n{new_entry}" if previous else new_entry
    doc_ref.update({"comment": updated})

def upload_file(doc_id, uploaded_file):
    blob_path = f"supporting_files/{doc_id}/{uploaded_file.name}"
    blob = bucket.blob(blob_path)
    blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)
    db.collection("reconciliation_records").document(doc_id).update({"file_url": blob.public_url})

# ---------------- Carga y Filtro de Datos ----------------
df = load_data()

if df.empty:
    st.info("No hay datos cargados.")
    st.stop()

if USER_COUNTRY_MAPPING.get(user) != "ALL":
    allowed = USER_COUNTRY_MAPPING.get(user, [])
    df = df[df['Country'].isin(allowed)]
    if df.empty:
        st.warning("No tienes datos asignados para revisar.")
        st.stop()
else:
    st.success("Acceso como ADMIN: Puedes ver todos los registros y subir nuevos archivos.")
    with st.expander("🔼 Cargar nuevo archivo Excel a Firebase"):
        upload = st.file_uploader("Selecciona un archivo .xlsx para cargar", type=["xlsx"])
        if upload:
            new_data = pd.read_excel(upload)
            for _, row in new_data.iterrows():
                doc_id = str(uuid.uuid4())
                record = row.to_dict()
                db.collection("reconciliation_records").document(doc_id).set(record)
            st.success("Archivo cargado correctamente a Firebase")
    df = load_data()  # Recarga tras subida

# ---------------- Interfaz tipo "chat" con burbujas de comentarios ----------------
st.subheader("📋 Registros asignados")

records_per_page = 10
max_pages = (len(df) - 1) // records_per_page + 1
current_page = st.number_input("Página", min_value=1, max_value=max_pages, value=1, step=1)
start_idx = (current_page - 1) * records_per_page
end_idx = start_idx + records_per_page
paginated_df = df.iloc[start_idx:end_idx].reset_index(drop=True)

selected_index = st.session_state.get("selected_index", None)

cols = st.columns([3, 9])
with cols[0]:
    st.markdown("### 🧾 GL Accounts")
    for i, row in paginated_df.iterrows():
        if st.button(f"{row.get('GL Account', 'N/A')} - {row.get('GL NAME', 'Sin nombre')}", key=f"btn_{i}"):
            st.session_state.selected_index = i
            selected_index = i

with cols[1]:
    if selected_index is not None:
        row = paginated_df.iloc[selected_index]
        doc_id = row['_id']
        st.markdown(f"### Detalles de GL {row.get('GL Account')}")
        st.markdown(f"**GL NAME:** {row.get('GL NAME')}")
        st.markdown(f"**Balance:** {row.get('Balance  in EUR at 31/3', 'N/A')}")
        st.markdown(f"**País:** {row.get('Country', 'N/A')}")
        st.markdown(f"**Entity:** {row.get('HFM CODE Entity', 'N/A')}")

        # Refrescar el comentario directamente del documento
        live_doc = db.collection("reconciliation_records").document(doc_id).get().to_dict()
        comment_history = live_doc.get("comment", "") if live_doc else ""

        if isinstance(comment_history, str) and comment_history.strip():
            for line in comment_history.strip().split("\n"):
                st.markdown(f"<div style='background-color:#f1f1f1;padding:10px;border-radius:10px;margin-bottom:10px'>💬 {line}</div>", unsafe_allow_html=True)

        # Campo para nuevo comentario
        new_comment = st.text_area("Nuevo comentario", key=f"comment_input_{doc_id}")
        if st.button("💾 Guardar comentario", key=f"save_{doc_id}"):
            tz = pytz.timezone("America/Mexico_City")
            now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            entry = f"{user} ({now}): {new_comment}"
            save_comment(doc_id, entry)
            st.session_state["selected_index"] = selected_index
            st.query_params(updated=str(datetime.now().timestamp()))
            st.success("Comentario guardado")

        uploaded_file = st.file_uploader("📎 Subir archivo de soporte", type=None, key=f"upload_{doc_id}")
        if uploaded_file:
            upload_file(doc_id, uploaded_file)
            st.success("Archivo cargado correctamente")
            st.session_state["selected_index"] = selected_index
            st.query_params(updated=str(datetime.now().timestamp()))

        file_url = row.get("file_url")
        if file_url:
            st.markdown(f"Archivo cargado previamente: [Ver archivo]({file_url})")
    else:
        st.markdown("<br><br><h4>Selecciona un GL para ver sus detalles</h4>", unsafe_allow_html=True)
