import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import FieldFilter
from pandas.tseries.offsets import BDay
import uuid
from datetime import datetime, timedelta
import pytz

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

def get_stored_deadline_day():
    doc = db.collection("config").document("general_settings").get()
    if doc.exists and "deadline_day" in doc.to_dict():
        return int(doc.to_dict()["deadline_day"])
    return 3  # Default to WD3

def set_stored_deadline_day(day: int):
    db.collection("config").document("general_settings").set({"deadline_day": day}, merge=True)

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
    return blob.generate_signed_url(expiration=timedelta(hours=2))

def log_upload(metadata):
    log_id = str(uuid.uuid4())
    db.collection("upload_logs").document(log_id).set(metadata)

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

now = datetime.now(pytz.timezone("America/Mexico_City"))
today = pd.Timestamp(now.date())

def get_workdays(year, month):
    first_day = pd.Timestamp(f"{year}-{month:02d}-01")
    workdays = pd.date_range(first_day, first_day + BDay(10), freq=BDay())
    return workdays

workdays = get_workdays(today.year, today.month)
day_is_wd1 = today == workdays[0]
day_is_wd4 = len(workdays) >= 4 and today == workdays[3]

if USER_COUNTRY_MAPPING.get(user) == "ALL":
    st.sidebar.markdown("### ⚙️ Configuración de Fecha Límite")

    current_deadline = get_stored_deadline_day()
    custom_day = st.sidebar.number_input("Día límite para completar (por default WD3)", min_value=1, max_value=31, value=current_deadline)
    deadline_date = pd.Timestamp(today.replace(day=1)) + BDay(custom_day - 1)

    if custom_day != current_deadline:
        set_stored_deadline_day(custom_day)

    st.sidebar.info(f"📅 Fecha límite considerada: {deadline_date.strftime('%Y-%m-%d')}")
    st.markdown(f"🗓️ **Fecha límite usada para evaluación:** `{deadline_date.strftime('%Y-%m-%d')}`")

    if st.sidebar.checkbox("Estoy seguro que quiero reiniciar el mes"):
        if st.sidebar.button("🔁 Forzar reinicio del mes"):
            for doc in db.collection("reconciliation_records").stream():
                db.collection("reconciliation_records").document(doc.id).update({
                    "Completed Mar": "No",
                    "Completed Timestamp": "",
                    "Status Mar": "Pending",
                    "Deadline Used": ""
                })
            st.sidebar.success("✅ Todos los registros han sido reiniciados.")

if st.sidebar.button("🔄 Forzar evaluación de Status Mar"):
    with st.spinner("Recalculando estados desde Firebase con nueva fecha límite..."):
        records = db.collection("reconciliation_records").stream()
        for doc in records:
            data = doc.to_dict()
            completed = str(data.get("Completed Mar", "")).strip().upper()
            timestamp_str = str(data.get("Completed Timestamp", "")).strip()

            if completed == "YES":
                if timestamp_str:
                    try:
                        completed_ts = pd.to_datetime(timestamp_str)
                        status = "On time" if completed_ts <= deadline_date else "Completed/Delayed"
                    except Exception:
                        status = "Completed/Delayed"
                else:
                    status = "Completed/Delayed"
            else:
                # Not completed, evaluate if still within time or too late
                status = "Pending" if today <= deadline_date else "Delayed"

            db.collection("reconciliation_records").document(doc.id).update({
                "Status Mar": status,
                "Deadline Used": deadline_date.strftime("%Y-%m-%d")
            })

    st.sidebar.success("✅ Estados sobrescritos en Firebase con la nueva fecha límite.")


else:
    deadline_date = pd.Timestamp(today.replace(day=1)) + BDay(2)

if day_is_wd1:
    for doc in db.collection("reconciliation_records").stream():
        db.collection("reconciliation_records").document(doc.id).update({
            "Completed Mar": "No",
            "Completed Timestamp": "",
            "Status Mar": "Pending",
            "Deadline Used": ""
        })

if day_is_wd4:
    def evaluate_status(row):
        completed = str(row.get("Completed Mar", "")).strip().upper()
        timestamp_str = str(row.get("Completed Timestamp", "")).strip()
        if completed == "YES" and timestamp_str:
            try:
                completed_ts = pd.to_datetime(timestamp_str)
                return "On time" if completed_ts <= deadline_date else "Completed/Delayed"
            except:
                return "Completed/Delayed"
        elif completed == "YES":
            return "Completed/Delayed"
        return "Delayed"

    df["Status Mar"] = df.apply(evaluate_status, axis=1)

    for _, row in df.iterrows():
        db.collection("reconciliation_records").document(row["_id"]).update({
            "Status Mar": row["Status Mar"],
            "Deadline Used": deadline_date.strftime("%Y-%m-%d")
        })
# ---------------- Filtros ----------------
unique_groups = df['ReviewGroup'].dropna().unique().tolist()
selected_group = st.sidebar.selectbox("Filtrar por Review Group", ["Todos"] + sorted(unique_groups))
if selected_group != "Todos":
    df = df[df['ReviewGroup'] == selected_group]

selected_country = st.sidebar.selectbox("Filtrar por Country", ["Todos"] + sorted(df['Country'].dropna().unique()))
if selected_country != "Todos":
    df = df[df['Country'] == selected_country]

status_options = df['Status Mar'].dropna().unique().tolist()
selected_status = st.sidebar.selectbox("Filtrar por Status Mar", ["Todos"] + sorted(status_options))
if selected_status != "Todos":
    df = df[df['Status Mar'] == selected_status]

def status_color(status):
    return {
        'On time': '🟢',
        'Delayed': '🔴',
        'Pending': '⚪️',
        'Completed/Delayed': '🟢🔴'
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
        completed_checked = completed_val.strip().upper() == "YES"
        new_check = st.checkbox("✅ Completed", value=completed_checked, key=f"completed_{doc_id}")

        if new_check != completed_checked:
            new_status = "Yes" if new_check else "No"
            now = datetime.now(pytz.timezone("America/Mexico_City"))
            timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
            today = pd.Timestamp(now.date())
            status_result = "On time" if new_check and today <= deadline_date else "Completed/Delayed" if new_check else "Delayed"

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
            for line in comment_history.strip().split("\n"):
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
