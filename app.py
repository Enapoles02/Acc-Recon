import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import FieldFilter
from pandas.tseries.offsets import BDay
import uuid
from datetime import datetime, timedelta
import pytz
import plotly.express as px

st.set_page_config(page_title="Reconciliación GL", layout="wide")

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
    return 3

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

# Región
df["Region"] = df["Country"].apply(lambda x: "NAMER" if x in ["Canada", "United States of America"] else "LATAM")

# Vista seleccionable
modo = st.sidebar.selectbox("Selecciona vista:", ["📈 Dashboard KPI", "📋 Visor GL"])

# -------------------------------
# KPI DASHBOARD
# -------------------------------
if modo == "📈 Dashboard KPI":
    st.title("📊 Dashboard KPI - Estado de Conciliaciones")

    region_filter = st.sidebar.selectbox("🌎 Región", ["Todas"] + sorted(df["Region"].unique()))
    filtered_df = df.copy()

    if region_filter != "Todas":
        filtered_df = filtered_df[filtered_df["Region"] == region_filter]

    available_countries = sorted(filtered_df["Country"].dropna().unique())
    selected_countries = st.sidebar.multiselect("🌍 País", available_countries, default=available_countries)
    filtered_df = filtered_df[filtered_df["Country"].isin(selected_countries)]

    available_companies = sorted(filtered_df["HFM CODE Entity"].dropna().unique())
    selected_companies = st.sidebar.multiselect("🏢 Company Code", available_companies, default=available_companies)
    filtered_df = filtered_df[filtered_df["HFM CODE Entity"].isin(selected_companies)]

    reviewer_options = sorted(filtered_df["ReviewGroup"].dropna().unique())
    reviewer_group = st.sidebar.selectbox("👥 Reviewer Group", ["Todos"] + reviewer_options)
    if reviewer_group != "Todos":
        filtered_df = filtered_df[filtered_df["ReviewGroup"] == reviewer_group]

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📌 Estado general (Pending vs Completed)")

        pie_data = filtered_df[filtered_df["Status Mar"].isin(["Pending", "On time", "Completed/Delayed"])].copy()
        pie_data["Status Simplified"] = pie_data["Status Mar"].apply(
            lambda x: "Completed" if x in ["On time", "Completed/Delayed"] else "Pending"
        )

        if not pie_data.empty:
            pie_counts = pie_data["Status Simplified"].value_counts().reset_index()
            pie_counts.columns = ["Status", "Count"]

            pie_fig = px.pie(
                pie_counts,
                names="Status",
                values="Count",
                title="Estado General",
                hover_data=["Count"]
            )
            pie_fig.update_traces(
                textinfo='label+value+percent',
                hovertemplate='%{label}: %{value} cuentas (%{percent})'
            )
            st.plotly_chart(pie_fig, use_container_width=True)
        else:
            st.info("No hay datos suficientes para la gráfica de pastel.")

    with col2:
        st.subheader("⏱️ Desempeño (Solo líneas completadas)")
        bar_data = filtered_df[filtered_df["Status Mar"].isin(["On time", "Delayed", "Completed/Delayed"])]
        if not bar_data.empty:
            bar_counts = bar_data["Status Mar"].value_counts().reset_index()
            bar_counts.columns = ["Status", "Count"]
            bar_fig = px.bar(bar_counts, x="Status", y="Count",
                 title="⏱️ Desempeño por Status",
                 color="Status", height=350)

            st.plotly_chart(bar_fig, use_container_width=True)
        else:
            st.info("No hay datos suficientes para la gráfica de barras.")

    st.markdown("🔍 Este dashboard refleja el estado de conciliaciones según los filtros aplicados.")

# -------------------------------
# VISOR GL
# -------------------------------
if modo == "📋 Visor GL":
    # Filtrar por país según usuario
    user_countries = USER_COUNTRY_MAPPING.get(user, [])
    if user_countries != "ALL":
        df = df[df["Country"].isin(user_countries)]

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

    # Filtros por país, entidad y estado
    with st.sidebar:
        st.markdown("### 🔎 Filtros")
        unique_countries = sorted(df["Country"].dropna().unique())
        selected_countries = st.multiselect("🌍 País", unique_countries, default=unique_countries)

        unique_entities = sorted(df["HFM CODE Entity"].dropna().unique())
        selected_entities = st.multiselect("🏢 Entity", unique_entities, default=unique_entities)

        unique_status = sorted(df["Status Mar"].dropna().unique())
        selected_status = st.multiselect("📌 Status", unique_status, default=unique_status)

        df = df[df["Country"].isin(selected_countries)]
        df = df[df["HFM CODE Entity"].isin(selected_entities)]
        df = df[df["Status Mar"].isin(selected_status)]

    def status_color(status):
        color_map = {
            'On time': '🟢',
            'Delayed': '🔴',
            'Pending': '⚪️',
            'Completed/Delayed': '🟢',
            'Review Required': '🟡'
        }
        return color_map.get(status, '⚪️')

    cols = st.columns([3, 9])
    with cols[0]:
        st.markdown("### 🧾 GL Accounts")
        for i, row in paginated_df.iterrows():
            gl_account = str(row.get("GL Account", "")).zfill(10)
            status = row.get("Status Mar", "Pending")
            color = status_color(status)
            gl_name = str(row.get("GL NAME", "Sin nombre"))
            if gl_name is None or gl_name == "Ellipsis" or gl_name == str(...):
                gl_name = "Sin nombre"
            label = f"{color} {gl_account} - {gl_name}"
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
                deadline_date = pd.Timestamp(today.replace(day=1)) + BDay(get_stored_deadline_day() - 1)

                if new_check:
                    status_result = "On time" if today <= deadline_date else "Completed/Delayed"
                else:
                    status_result = "Pending" if today <= deadline_date else "Delayed"

                live_doc_ref.update({
                    "Completed Mar": new_status,
                    "Completed Timestamp": timestamp_str,
                    "Status Mar": status_result,
                    "Deadline Used": deadline_date.strftime("%Y-%m-%d")
                })

                st.success(f"✔️ Estado actualizado: {new_status} | {status_result}")
                st.session_state["refresh_timestamp"] = datetime.now().timestamp()

            current_status = live_doc.get("Status Mar", "Pending")
            st.markdown(f"**status:** {current_status}")

            # Nuevo botón de revisión
            review_required = current_status == "Review Required"
            new_review = st.checkbox("⚠️ Review Required", value=review_required, key=f"review_required_{doc_id}")

            if new_review != review_required:
                new_status = "Review Required" if new_review else "Pending"
                update_fields = {"Status Mar": new_status}
                if new_review:
                    update_fields["Completed Mar"] = "No"
                live_doc_ref.update(update_fields)
                st.success(f"✔️ Estado actualizado a: {new_status}")
                st.session_state["refresh_timestamp"] = datetime.now().timestamp()

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
