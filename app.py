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

@st.cache_data
def load_mapping():
    url = "https://raw.githubusercontent.com/Enapoles02/Acc-Recon/main/Mapping.csv"
    df_map = pd.read_csv(url, dtype=str)
    df_map.columns = df_map.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
    df_map = df_map.rename(columns={"Group": "ReviewGroup"})
    return df_map

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

def log_upload(metadata):
    log_id = str(uuid.uuid4())
    db.collection("upload_logs").document(log_id).set(metadata)

# ---------------- Carga y Filtro de Datos ----------------
df = load_data()
mapping_df = load_mapping()

if "GL Account" in df.columns and "GL Account" in mapping_df.columns:
    df["GL Account"] = df["GL Account"].astype(str).str.zfill(10).str.strip()
    mapping_df["GL Account"] = mapping_df["GL Account"].astype(str).str.zfill(10).str.strip()
    mapping_df = mapping_df.drop_duplicates(subset=["GL Account"])
    df = df.merge(mapping_df, on="GL Account", how="left")
    df["ReviewGroup"] = df["ReviewGroup"].fillna("Others")
else:
    st.warning("No se pudo hacer el merge con Mapping.csv. Revisa los nombres de las columnas.")

if df.empty:
    st.info("No hay datos cargados.")
    st.stop()

if USER_COUNTRY_MAPPING.get(user) != "ALL":
    allowed = USER_COUNTRY_MAPPING.get(user, [])
    df = df[df['Country'].isin(allowed)]
    country_options = sorted(df['Country'].dropna().unique())
else:
    allowed = df['Country'].dropna().unique().tolist()
    country_options = sorted(allowed)
    st.success("Acceso como ADMIN: Puedes ver todos los registros y subir nuevos archivos.")
    with st.expander("🔼 Cargar nuevo archivo Excel a Firebase"):
        upload = st.file_uploader("Selecciona un archivo .xlsx para cargar", type=["xlsx"])
        if upload:
            new_data = pd.read_excel(upload)
            now = datetime.now(pytz.timezone("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
            for _, row in new_data.iterrows():
                doc_id = str(uuid.uuid4())
                record = row.to_dict()
                record["upload_time"] = now
                gl_account = str(record.get("GL Account", "")).zfill(10)
                log_upload({"file_name": upload.name, "uploaded_at": now, "user": user, "gl_account": gl_account})
                db.collection("reconciliation_records").document(doc_id).set(record)
            
            st.success("Archivo cargado correctamente a Firebase")
    df = load_data()

# ---------------- Interfaz tipo "chat" con burbujas de comentarios ----------------

# Filtros por ReviewGroup y Country
unique_groups = df['ReviewGroup'].dropna().unique().tolist()
selected_group = st.sidebar.selectbox("Filtrar por Review Group", ["Todos"] + sorted(unique_groups))
if selected_group != "Todos":
    df = df[df['ReviewGroup'] == selected_group]

selected_country = st.sidebar.selectbox("Filtrar por Country", ["Todos"] + country_options)
if selected_country != "Todos":
    df = df[df['Country'] == selected_country]

st.subheader("📋 Registros asignados")

# Mostrar historial solo dentro del detalle de la cuenta
# Este bloque fue eliminado de aquí y será integrado individualmente por cuenta

records_per_page = 5
max_pages = (len(df) - 1) // records_per_page + 1
if "current_page" not in st.session_state:
    st.session_state.current_page = 1

col1, col2 = st.columns([1, 8])
with col1:
    if st.button("⬅️") and st.session_state.current_page > 1:
        st.session_state.current_page -= 1
with col2:
    if st.button("➡️") and st.session_state.current_page < max_pages:
        st.session_state.current_page += 1

current_page = st.session_state.current_page
start_idx = (current_page - 1) * records_per_page
end_idx = start_idx + records_per_page
paginated_df = df.iloc[start_idx:end_idx].reset_index(drop=True)

selected_index = st.session_state.get("selected_index", None)

cols = st.columns([3, 9])
with cols[0]:
    st.markdown("### 🧾 GL Accounts")
    for i, row in paginated_df.iterrows():
        gl_account = str(row.get("GL Account", "")).zfill(10)
        if st.button(f"{gl_account} - {row.get('GL NAME', 'Sin nombre')}", key=f"btn_{i}"):
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
        st.markdown(f"**Review Group:** {row.get('ReviewGroup', 'Others')}")

        # Refrescar el comentario directamente del documento
        live_doc = db.collection("reconciliation_records").document(doc_id).get().to_dict()
        comment_history = live_doc.get("comment", "") if live_doc else ""

        if isinstance(comment_history, str) and comment_history.strip():
         for line in comment_history.strip().split("\n"):

                st.markdown(f"<div style='background-color:#f1f1f1;padding:10px;border-radius:10px;margin-bottom:10px'>💬 {line}</div>", unsafe_allow_html=True)

        # Historial de cargas por cuenta
        st.markdown("---")
        st.markdown("### 📁 Historial de cargas de esta cuenta")
        log_docs = db.collection("upload_logs").where("gl_account", "==", row.get("GL Account")).order_by("uploaded_at", direction=firestore.Query.DESCENDING).stream()
        log_data = [doc.to_dict() for doc in log_docs]
        if log_data:
            for log in log_data:
                st.markdown(f"- 📎 **{log['file_name']}**  | 👤 {log['user']}  | 🕒 {log['uploaded_at']}")
        else:
            st.info("No hay archivos cargados para esta cuenta.")

        # Campo para nuevo comentario
        if uploaded_file:
            upload_file(doc_id, uploaded_file)
            st.success("Archivo cargado correctamente")
            st.session_state["selected_index"] = selected_index

        file_url = row.get("file_url")
        if file_url:
            st.markdown(f"Archivo cargado previamente: [Ver archivo]({file_url})")
    else:
        st.markdown("<br><br><h4>Selecciona un GL para ver sus detalles</h4>", unsafe_allow_html=True)
