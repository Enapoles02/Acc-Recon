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

USER_ACCESS = {
    "Paula Sarachaga": {"countries": ["Argentina", "Chile", "Guatemala"], "streams": "ALL"},
    "Napoles Enrique": {"countries": ["Canada"], "streams": ["GL"]},
    "Julio": {"countries": ["United States of America"], "streams": "ALL"},
    "Guadalupe": {"countries": ["Mexico", "Peru", "Panama"], "streams": "ALL"},
    "Gabriel Aviles": {"countries": ["Canada", "United States of America"], "streams": ["RTR-FA"]},
    "Delhumeau Luis": {"countries": ["Canada"], "streams": ["RTR-ICO"]},
    "ADMIN": {"countries": "ALL", "streams": "ALL"}
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

# Aplicar acceso filtrado por país y preparer stream
user_info = USER_ACCESS.get(user, {})
allowed_countries = user_info.get("countries", [])
allowed_streams = user_info.get("streams", [])

if allowed_countries != "ALL":
    df = df[df["Country"].isin(allowed_countries)]

if allowed_streams != "ALL":
    df = df[df["Preparer Stream"].isin(allowed_streams)]

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

    region_filter = st.sidebar.selectbox("🌎 Región", ["Todas"] + sorted(df["Region"].dropna().unique()))
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

    # Filtro adicional por Preparer Stream
    if "Preparer Stream" in filtered_df.columns:
        unique_streams = sorted(filtered_df["Preparer Stream"].dropna().unique())
        selected_streams = st.sidebar.multiselect("🔁 Preparer Stream", unique_streams, default=unique_streams)
        filtered_df = filtered_df[filtered_df["Preparer Stream"].isin(selected_streams)]

    # KPI visual de revisión requerida
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

    # DRILLDOWN DE CUENTAS EN REVISIÓN
    review_pending_df = filtered_df[filtered_df["Status Mar"] == "Review Required"]
    if not review_pending_df.empty:
        with st.expander("🔍 Ver cuentas pendientes de revisión"):
            st.markdown("Estas cuentas están marcadas con **⚠️ Review Required**.")
            st.dataframe(
                review_pending_df[[
                    "GL Account", "GL NAME", "Country", "ReviewGroup", "HFM CODE Entity", "Preparer Stream"
                ]].sort_values("GL Account"),
                use_container_width=True
            )

    st.markdown("🔍 Este dashboard refleja el estado de conciliaciones según los filtros aplicados.")
