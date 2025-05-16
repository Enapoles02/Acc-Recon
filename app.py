import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import FieldFilter
from pandas.tseries.offsets import BDay
import uuid
from datetime import datetime, timedelta
import pytz

# ---------------- Configuración inicial ----------------
st.set_page_config(page_title="Reconciliación GL", layout="wide")
st.title("📊 Dashboard de Reconciliación GL")

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

def upload_file_to_bucket(gl_account, uploaded_file):
    blob_path = f"reconciliation_records/{gl_account}/{uploaded_file.name}"
    blob = bucket.blob(blob_path)
    blob.upload_from_file(uploaded_file, content_type=uploaded_file.type)
    url = blob.generate_signed_url(expiration=timedelta(hours=2))
    return url

def log_upload(metadata):
    log_id = str(uuid.uuid4())
    db.collection("upload_logs").document(log_id).set(metadata)

# ---------------- Cargar datos ----------------
df = load_data()
mapping_df = load_mapping()

if "GL Account" in df.columns and "GL Account" in mapping_df.columns:
    df["GL Account"] = df["GL Account"].astype(str).str.zfill(10).str.strip()
    mapping_df["GL Account"] = mapping_df["GL Account"].astype(str).str.zfill(10).str.strip()
    mapping_df = mapping_df.drop_duplicates(subset=["GL Account"])
    df = df.merge(mapping_df, on="GL Account", how="left")
    df["ReviewGroup"] = df["ReviewGroup"].fillna("Others")
else:
    st.warning("No se pudo hacer el merge con Mapping.csv.")

if df.empty:
    st.info("No hay datos cargados.")
    st.stop()

# ---------------- Evaluación automática del estado "Status Mar" ----------------
now = datetime.now(pytz.timezone("America/Mexico_City"))
today = pd.Timestamp(now.date())

# Permitir a ADMIN modificar fecha límite
if USER_COUNTRY_MAPPING.get(user) == "ALL":
    st.sidebar.markdown("### ⚙️ Configuración de Fecha Límite")
    custom_day = st.sidebar.number_input("Día límite para completar (por default WD3)", min_value=1, max_value=31, value=3)
    deadline_date = pd.Timestamp(today.replace(day=1)) + BDay(custom_day - 1)
    st.sidebar.info(f"Fecha límite considerada: {deadline_date.strftime('%Y-%m-%d')}")
else:
    deadline_date = pd.Timestamp(today.replace(day=1)) + BDay(2)

# Mostrar fecha usada solo a ADMIN
if USER_COUNTRY_MAPPING.get(user) == "ALL":
    st.markdown(f"🗓️ **Fecha límite usada para evaluación:** `{deadline_date.strftime('%Y-%m-%d')}`")

# Solo actualizar status el día 1 o 4 de cada mes
if now.day in [1, 4]:
    def evaluate_status(row):
        if row.get("Completed Mar") == "Yes":
            return "On time"
        elif today > deadline_date:
            return "Delayed"
        else:
            return "Pending"

    df["Status Mar"] = df.apply(evaluate_status, axis=1)

    for _, row in df.iterrows():
        doc_id = row["_id"]
        status = row["Status Mar"]
        db.collection("reconciliation_records").document(doc_id).update({
            "Status Mar": status,
            "Deadline Used": deadline_date.strftime("%Y-%m-%d")
        })

# ---------------- Filtros ----------------

# Filtro por Status Mar
status_options = df['Status Mar'].dropna().unique().tolist()
selected_status = st.sidebar.selectbox("Filtrar por Status Mar", ["Todos"] + sorted(status_options))
if selected_status != "Todos":
    df = df[df['Status Mar'] == selected_status]

# Mostrar color en la lista según Status Mar
def status_color(status):
    return {
        'On time': '🟢',
        'Delayed': '🔴',
        'Pending': '⚪️'
    }.get(status, '⚪️')

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
        status = row.get("Status Mar", "Pending")
        color = status_color(status)
        label = f"{color} {gl_account} - {row.get('GL NAME', 'Sin nombre')}"
        if st.button(label, key=f"btn_{i}"):
            st.session_state.selected_index = i
            selected_index = i

with cols[1]:
    if selected_index is not None:
        row = paginated_df.iloc[selected_index]
        doc_id = row['_id']
        gl_account = str(row.get("GL Account", "")).zfill(10)

        st.markdown(f"### Detalles de GL {gl_account}")
        st.markdown(f"**GL NAME:** {row.get('GL NAME')}")
        st.markdown(f"**Balance:** {row.get('Balance  in EUR at 31/3', 'N/A')}")
        st.markdown(f"**País:** {row.get('Country', 'N/A')}")
        st.markdown(f"**Entity:** {row.get('HFM CODE Entity', 'N/A')}")
        st.markdown(f"**Review Group:** {row.get('ReviewGroup', 'Others')}")

        live_doc_ref = db.collection("reconciliation_records").document(doc_id)
        live_doc = live_doc_ref.get().to_dict()

        completed_val = live_doc.get("Completed Mar", "No")
        completed_checked = completed_val == "Yes"
        new_check = st.checkbox("✅ Completed", value=completed_checked, key=f"completed_{doc_id}")

        if new_check != completed_checked:
            new_status = "Yes" if new_check else "No"
            now = datetime.now(pytz.timezone("America/Mexico_City"))
            timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

            today = pd.Timestamp(now.date())
            wd3 = pd.Timestamp(today.replace(day=1)) + BDay(2)
            status_result = "On time" if today <= wd3 else "Delayed"

            live_doc_ref.update({
                "Completed Mar": new_status,
                "Completed Timestamp": timestamp_str,
                "Status Mar": status_result
            })

            st.success(f"✔️ Estado actualizado: {new_status} | {status_result}")
            st.session_state["refresh_timestamp"] = datetime.now().timestamp()

        current_status = live_doc.get("Status Mar", "Pending")
        st.markdown(f"**status:** {current_status}")

        comment_history = live_doc.get("comment", "") or ""
        if isinstance(comment_history, str) and comment_history.strip():
            for line in comment_history.strip().split("
"):
                st.markdown(f"<div style='background-color:#f1f1f1;padding:10px;border-radius:10px;margin-bottom:10px'>💬 {line}</div>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("### 📁 Historial de cargas de esta cuenta")
        log_docs = db.collection("upload_logs").where(
            filter=FieldFilter("gl_account", "==", gl_account)
        ).stream()
        log_data = sorted(
            [doc.to_dict() for doc in log_docs],
            key=lambda x: x.get("uploaded_at", ""),
            reverse=True
        )
        if log_data:
            st.markdown(f"🔁 **Reintentos:** {len(log_data)}")
            for log in log_data:
                st.markdown(f"- 📎 **{log['file_name']}** | 👤 {log['user']} | 🕒 {log['uploaded_at']} | [🔽 Descargar]({log.get('file_url', '#')})")
        else:
            st.info("No hay archivos cargados para esta cuenta.")

        new_comment = st.text_area("Nuevo comentario", key=f"comment_input_{doc_id}")
        if st.button("💾 Guardar comentario", key=f"save_{doc_id}"):
            now = datetime.now(pytz.timezone("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
            entry = f"{user} ({now}): {new_comment}"
            save_comment(doc_id, entry)
            st.success("Comentario guardado")
            st.session_state["refresh_timestamp"] = datetime.now().timestamp()

        uploaded_file = st.file_uploader("📎 Subir archivo de soporte", type=None, key=f"upload_{doc_id}")
        if uploaded_file:
            if st.button("✅ Confirmar carga de archivo", key=f"confirm_upload_{doc_id}"):
                file_url = upload_file_to_bucket(gl_account, uploaded_file)
                db.collection("reconciliation_records").document(doc_id).update({"file_url": file_url})
                now = datetime.now(pytz.timezone("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
                log_upload({
                    "file_name": uploaded_file.name,
                    "uploaded_at": now,
                    "user": user,
                    "gl_account": gl_account,
                    "file_url": file_url
                })
                st.success("Archivo cargado correctamente")
                st.session_state["refresh_timestamp"] = datetime.now().timestamp()

        file_url = row.get("file_url")
        if file_url:
            st.markdown(f"📄 Archivo cargado previamente: [Ver archivo]({file_url})")
    else:
        st.markdown("<br><br><h4>Selecciona un GL para ver sus detalles</h4>", unsafe_allow_html=True)

unique_groups = df['ReviewGroup'].dropna().unique().tolist()
selected_group = st.sidebar.selectbox("Filtrar por Review Group", ["Todos"] + sorted(unique_groups))
if selected_group != "Todos":
    df = df[df['ReviewGroup'] == selected_group]

selected_country = st.sidebar.selectbox("Filtrar por Country", ["Todos"] + sorted(df['Country'].dropna().unique()))
if selected_country != "Todos":
    df = df[df['Country'] == selected_country]
