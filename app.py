import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore, storage
import uuid
import io

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
@st.cache_data(ttl=300)
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

def save_comment(doc_id, comment):
    db.collection("reconciliation_records").document(doc_id).update({"comment": comment})

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

# ---------------- Interfaz Principal con Paginación ----------------
st.subheader("📋 Registros asignados")

records_per_page = 10
max_pages = (len(df) - 1) // records_per_page + 1
current_page = st.number_input("Página", min_value=1, max_value=max_pages, value=1, step=1)
start_idx = (current_page - 1) * records_per_page
end_idx = start_idx + records_per_page
paginated_df = df.iloc[start_idx:end_idx]

for index, row in paginated_df.iterrows():
    with st.container():
        cols = st.columns([3, 7])
        with cols[0]:
            st.markdown(f"**GL Account:** {row.get('GL Account', 'N/A')}")
            st.markdown(f"**GL NAME:** {row.get('GL NAME', 'Sin nombre')}")
            st.markdown(f"**Balance:** {row.get('Balance  in EUR at 31/3', 'N/A')}")
            st.markdown(f"**País:** {row.get('Country', 'N/A')}")
            st.markdown(f"**Entity:** {row.get('HFM CODE Entity', 'N/A')}")
        with cols[1]:
            current_comment = row.get("comment", "")
            comment = st.text_area("Comentario", value=current_comment, key=f"comment_{index}")
            if st.button("💾 Guardar comentario", key=f"save_{index}"):
                save_comment(row['_id'], comment)
                st.success("Comentario guardado")

            uploaded_file = st.file_uploader("📎 Subir archivo de soporte", type=None, key=f"upload_{index}")
            if uploaded_file:
                upload_file(row['_id'], uploaded_file)
                st.success("Archivo cargado correctamente")

            file_url = row.get("file_url")
            if file_url:
                st.markdown(f"Archivo cargado previamente: [Ver archivo]({file_url})")
