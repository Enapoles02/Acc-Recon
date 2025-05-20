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

# Usuario y roles
user = st.sidebar.text_input("Usuario")
user_role = st.sidebar.selectbox("Rol", ["FILLER", "REVIEWER", "APPROVER"])

# Mapeo de acceso combinado
USER_ACCESS = {
    "Paula Sarachaga": {"countries": ["Argentina", "Chile", "Guatemala"], "streams": "ALL", "role": "FILLER"},
    "Napoles Enrique": {"countries": ["Canada"], "streams": ["GL"], "role": "FILLER"},
    "MSANCHEZ": {"countries": ["Canada","United States of America"], "streams": ["GL"], "role": "REVIEWER"},
    "Julio": {"countries": ["United States of America"], "streams": "ALL", "role": "FILLER"},
    "Guadalupe": {"countries": ["Mexico", "Peru", "Panama"], "streams": "ALL", "role": "FILLER"},
    "Gabriel Aviles": {"countries": ["Canada", "United States of America"], "streams": ["RTR-FA"], "role": "REVIEWER"},
    "Delhumeau Luis": {"countries": ["Canada"], "streams": ["RTR-ICO"], "role": "FILLER"},
    "Guillermo Mayoral": {"countries": "ALL", "streams": "ALL", "role": "APPROVER"},
    "Guillermo Guarneros": {"countries": "ALL", "streams": "ALL", "role": "APPROVER"},
    "ADMIN": {"countries": "ALL", "streams": "ALL", "role": "ADMIN"}
}

if not user:
    st.warning("Ingresa tu nombre de usuario para continuar.")
    st.stop()

user_info = USER_ACCESS.get(user, {"countries": [], "streams": [], "role": "FILLER"})
allowed_countries = user_info.get("countries", [])
allowed_streams = user_info.get("streams", [])
role = user_info.get("role", "FILLER")

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

# Filtros por acceso
if allowed_countries != "ALL":
    df = df[df["Country"].isin(allowed_countries)]

if allowed_streams != "ALL":
    df = df[df["Preparer Stream"].isin(allowed_streams)]

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

# Región por país
df["Region"] = df["Country"].apply(lambda x: "NAMER" if x in ["Canada", "United States of America"] else "LATAM")

# Selección de vista
modo = st.sidebar.selectbox("Selecciona vista:", ["📈 Dashboard KPI", "📋 Visor GL"])

# Opciones exclusivas para ADMIN
if user == "ADMIN":
    st.sidebar.markdown("## ⚙️ Opciones de Admin")

    # Asegurar que el valor no sea mayor a 10 para evitar errores
    current_deadline = min(get_stored_deadline_day(), 10)

    new_deadline = st.sidebar.number_input("📅 Día límite (WD)", min_value=1, max_value=10, value=current_deadline, step=1)
    if new_deadline != current_deadline:
        set_stored_deadline_day(new_deadline)
        st.sidebar.success(f"Día límite actualizado a WD{new_deadline}")

    # Botón para reiniciar todos los estados del mes
    if st.sidebar.button("♻️ Resetear estados del mes"):
        docs = list(db.collection("reconciliation_records").stream())
        total = len(docs)
        progress = st.sidebar.progress(0, text="Reiniciando estados...")

        for i, doc in enumerate(docs):
            doc.reference.update({
                "Completed Mar": "No",
                "Status Mar": "Pending",
                "Completed Timestamp": firestore.DELETE_FIELD,
                "Deadline Used": firestore.DELETE_FIELD
            })
            progress.progress((i + 1) / total)

        progress.empty()
        st.sidebar.success("Todos los estados fueron reiniciados.")

    # Botón para forzar evaluación de estatus "On time" / "Completed/Delayed"
    if st.sidebar.button("📌 Forzar evaluación de 'On time' / 'Delayed'"):
        wd = get_stored_deadline_day()
        today = pd.Timestamp(datetime.now(pytz.timezone("America/Mexico_City")).date())
        deadline_date = pd.Timestamp(today.replace(day=1)) + BDay(wd - 1)

        docs = list(db.collection("reconciliation_records").stream())
        total = len(docs)
        progress = st.sidebar.progress(0, text="Evaluando estatus...")

        for i, doc in enumerate(docs):
            data = doc.to_dict()
            completed = data.get("Completed Mar", "No").strip().upper()
            current_status = data.get("Status Mar", "Pending")

            if completed == "YES":
                completed_date_str = data.get("Completed Timestamp")
                if completed_date_str:
                    completed_date = pd.to_datetime(completed_date_str)
                    status = "On time" if completed_date <= deadline_date else "Completed/Delayed"
                    doc.reference.update({
                        "Status Mar": status,
                        "Deadline Used": deadline_date.strftime("%Y-%m-%d")
                    })

            elif completed == "NO" and current_status == "Pending" and today > deadline_date:
                doc.reference.update({
                    "Status Mar": "Delayed",
                    "Deadline Used": deadline_date.strftime("%Y-%m-%d")
                })

            progress.progress((i + 1) / total)

        progress.empty()
        st.sidebar.success("Evaluación de estado completada.")
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

    available_streams = sorted(filtered_df["Preparer Stream"].dropna().unique())
    selected_streams = st.sidebar.multiselect("🧩 Preparer Stream", available_streams, default=available_streams)
    filtered_df = filtered_df[filtered_df["Preparer Stream"].isin(selected_streams)]

    reviewer_options = sorted(filtered_df["ReviewGroup"].dropna().unique())
    reviewer_group = st.sidebar.selectbox("👥 Reviewer Group", ["Todos"] + reviewer_options)
    if reviewer_group != "Todos":
        filtered_df = filtered_df[filtered_df["ReviewGroup"] == reviewer_group]

    # --- KPI visual de revisión requerida ---
    review_count = filtered_df[filtered_df["Status Mar"] == "Review Required"].shape[0]
    if review_count > 0:
        st.markdown(f"""
            <div style='
                background-color:#fff3cd;
                color:#856404;
                padding:15px;
                border-left: 5px solid #ffc107;
                border-radius:5px;
                margin-top:10px;
                font-size:18px;
            '>
            ⚠️ <strong>{review_count}</strong> cuentas están marcadas como <strong>Review Required</strong>.
            </div>
        """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📌 Estado general (Pending vs Completed vs Review)")
        pie_data = filtered_df[filtered_df["Status Mar"].isin(["Pending", "On time", "Completed/Delayed", "Review Required"])].copy()
        pie_data["Status Simplified"] = pie_data["Status Mar"].apply(
            lambda x: "Completed" if x in ["On time", "Completed/Delayed"] else (
                "Review Required" if x == "Review Required" else "Pending")
        )

        if not pie_data.empty:
            pie_counts = pie_data["Status Simplified"].value_counts().reset_index()
            pie_counts.columns = ["Status", "Count"]

            pie_fig = px.pie(
                pie_counts,
                names="Status",
                values="Count",
                title="Estado General",
                hover_data=["Count"],
                color="Status",
                color_discrete_map={
                    "Completed": "green",
                    "Pending": "gray",
                    "Review Required": "gold"
                }
            )
            pie_fig.update_traces(
                textinfo='label+value+percent',
                hovertemplate='%{label}: %{value} cuentas (%{percent})'
            )
            st.plotly_chart(pie_fig, use_container_width=True)
        else:
            st.info("No hay datos suficientes para la gráfica de pastel.")

    with col2:
        st.subheader("⏱️ Desempeño por Status (completados y revisión)")
        bar_data = filtered_df[filtered_df["Status Mar"].isin(["On time", "Delayed", "Completed/Delayed", "Review Required"])]
        if not bar_data.empty:
            bar_counts = bar_data["Status Mar"].value_counts().reset_index()
            bar_counts.columns = ["Status", "Count"]

            bar_fig = px.bar(
                bar_counts, x="Status", y="Count",
                title="⏱️ Desempeño por Status",
                color="Status", height=350,
                color_discrete_map={
                    "On time": "green",
                    "Completed/Delayed": "lightgreen",
                    "Delayed": "red",
                    "Review Required": "gold"
                }
            )

            st.plotly_chart(bar_fig, use_container_width=True)
        else:
            st.info("No hay datos suficientes para la gráfica de barras.")

    # Drilldown de cuentas pendientes de revisión
    review_pending_df = filtered_df[filtered_df["Status Mar"] == "Review Required"]
    if not review_pending_df.empty:
        with st.expander("🔍 Ver cuentas pendientes de revisión"):
            st.markdown("Estas cuentas están marcadas con **⚠️ Review Required**.")
            st.dataframe(
                review_pending_df[[
                    "GL Account", "GL NAME", "Country", "ReviewGroup", "HFM CODE Entity"
                ]].sort_values("GL Account"),
                use_container_width=True
            )

    # Cuadro resumen por persona y WD solo para ADMIN
    if role == "ADMIN":
        st.markdown("### 📅 Desempeño diario por WD")
    
        # Extraer fecha de completado y nombre
        df_wd = df[df["Completed Mar"].str.upper() == "YES"].copy()
        df_wd["Fecha"] = pd.to_datetime(df_wd["Completed Timestamp"], errors="coerce")
        df_wd["WD"] = df_wd["Fecha"].apply(lambda x: f"WD{sum((x >= d for d in workdays))}" if pd.notnull(x) else "N/A")
    
        resumen = df_wd.groupby(["User", "WD"]).size().unstack(fill_value=0)
        resumen = resumen.reindex(columns=[f"WD{i+1}" for i in range(len(workdays))], fill_value=0)
        selected_user = st.text_input("Buscar persona", "")
        if selected_user:
            resumen = resumen[resumen.index.str.contains(selected_user, case=False)]
    
        st.dataframe(resumen.style.highlight_max(axis=1), use_container_width=True)




    
    st.markdown("🔍 Este dashboard refleja el estado de conciliaciones según los filtros aplicados.")
# -------------------------------
# VISOR GL
# -------------------------------
if modo == "📋 Visor GL":
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

    # ✅ Buscador de GL Account
    search_gl = st.text_input("🔍 Buscar GL Account (número):").strip()

    # ✅ Filtros por país, entidad, status y preparer stream
    with st.sidebar:
        st.markdown("### 🔎 Filtros")
        unique_countries = sorted(df["Country"].dropna().unique())
        selected_countries = st.multiselect("🌍 País", unique_countries, default=unique_countries)

        unique_entities = sorted(df["HFM CODE Entity"].dropna().unique())
        selected_entities = st.multiselect("🏢 Entity", unique_entities, default=unique_entities)

        unique_status = sorted(df["Status Mar"].dropna().unique())
        selected_status = st.multiselect("📌 Status", unique_status, default=unique_status)

        unique_streams = sorted(df["Preparer Stream"].dropna().unique())
        selected_streams = st.multiselect("🔧 Preparer Stream", unique_streams, default=unique_streams)

    # ✅ Aplicar los filtros
    df = df[
        df["Country"].isin(selected_countries)
        & df["HFM CODE Entity"].isin(selected_entities)
        & df["Status Mar"].isin(selected_status)
        & df["Preparer Stream"].isin(selected_streams)
    ]

    # ✅ Aplicar búsqueda si hay input
   if search_gl:
    filtered_gl_df = df[df["GL Account"].str.contains(search_gl.zfill(10), na=False)]
    paginated_df = filtered_gl_df.reset_index(drop=True)
    max_pages = 1
    st.session_state.current_page = 1
    selected_index = st.session_state.get("selected_index", None)  # ✅ Añadido aquí
else:
    paginated_df = df.iloc[start_idx:end_idx].reset_index(drop=True)
    selected_index = st.session_state.get("selected_index", None)

       

    # ✅ Aplicar los filtros al dataframe
    df = df[
        df["Country"].isin(selected_countries)
        & df["HFM CODE Entity"].isin(selected_entities)
        & df["Status Mar"].isin(selected_status)
        & df["Preparer Stream"].isin(selected_streams)
    ]
    def status_color(status):
        color_map = {
            'On time': '🟢',
            'Delayed': '🔴',
            'Pending': '⚪️',
            'Completed/Delayed': '🟢',
            'Review Required': '🟡',
            'SUBMITTED': '🔵',
            'ON HOLD': '🟠',
            'REVIEWED': '🟣',
            'APPROVED': '🟢✔️'
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
            st.markdown(f"**Preparer Stream:** {row.get('Preparer Stream', 'N/A')}")

            live_doc_ref = db.collection("reconciliation_records").document(doc_id)
            live_doc = live_doc_ref.get().to_dict()

            # Mostrar estatus actual
            current_status = live_doc.get("Status Mar", "Pending")
            st.markdown(f"**Estatus actual:** `{current_status}`")

            # CONTROL DE STATUS por ROL
            def password_required(action_label):
                return st.text_input(f"🔒 Contraseña para {action_label}:", type="password", key=f"pw_{doc_id}_{action_label}")
            
            if role in ["REVIEWER", "APPROVER", "FILLER"]:
                # Opciones por rol
                if role == "REVIEWER":
                    options = ["ON HOLD", "REVIEWED"]
                elif role == "APPROVER":
                    options = ["APPROVED"]
                else:
                    options = ["SUBMITTED"]
            
                selected_status = st.selectbox("🧭 Cambiar estatus", options, index=options.index(current_status) if current_status in options else 0)

                password_input = ""
                allowed = True
                if selected_status in ["ON HOLD", "REVIEWED"] and role != "REVIEWER":
                    allowed = False
                if selected_status == "APPROVED" and role != "APPROVER":
                    allowed = False
                if selected_status in ["ON HOLD", "REVIEWED", "APPROVED"]:
                    password_input = password_required(selected_status)

                if st.button("✅ Actualizar estatus", key=f"update_status_{doc_id}") and allowed:
                    if selected_status in ["ON HOLD", "REVIEWED", "APPROVED"]:
                        if password_input != st.secrets["role_passwords"]["reviewer_password"]:
                            st.error("❌ Contraseña incorrecta.")
                        else:
                            update_fields = {"Status Mar": selected_status}
                            if selected_status == "APPROVED":
                                now = datetime.now(pytz.timezone("America/Mexico_City"))
                                timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
                                update_fields["Completed Mar"] = "Yes"
                                update_fields["Completed Timestamp"] = timestamp_str
                            live_doc_ref.update(update_fields)
                            st.success(f"✅ Estatus actualizado a: {selected_status}")
                            st.session_state["refresh_timestamp"] = datetime.now().timestamp()
                    else:
                        live_doc_ref.update({"Status Mar": selected_status})
                        st.success(f"✅ Estatus actualizado a: {selected_status}")
                        st.session_state["refresh_timestamp"] = datetime.now().timestamp()

            # Mostrar botón de revisión solo si no es APPROVER
            if role != "APPROVER":
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

            # Mostrar Plan de Acción
            current_action = live_doc.get("Plan de Acción", "No")
            plan_required = current_action == "Yes"
            plan_toggle = st.checkbox("📝 Plan de Acción requerido", value=plan_required, key=f"plan_{doc_id}")
            if plan_toggle != plan_required:
                update_val = "Yes" if plan_toggle else "No"
                live_doc_ref.update({"Plan de Acción": update_val})
                st.success(f"📌 Plan de Acción actualizado a: {update_val}")

            # Comentarios
            comment_history = live_doc.get("comment", "") or ""
            if isinstance(comment_history, str) and comment_history.strip():
                for line in comment_history.strip().split("\n"):
                    st.markdown(f"<div style='background-color:#f1f1f1;padding:10px;border-radius:10px;margin-bottom:10px'>💬 {line}</div>", unsafe_allow_html=True)

            new_comment = st.text_area("Nuevo comentario", key=f"comment_input_{doc_id}")
            if st.button("💾 Guardar comentario", key=f"save_{doc_id}"):
                now = datetime.now(pytz.timezone("America/Mexico_City")).strftime("%Y-%m-%d %H:%M:%S")
                entry = f"{user} ({now}): {new_comment}"
                save_comment(doc_id, entry)
                st.success("Comentario guardado")
                st.session_state["refresh_timestamp"] = datetime.now().timestamp()

            # Carga de archivo
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
