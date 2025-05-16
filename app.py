import streamlit as st
import pandas as pd
import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# ------------------ Configuración general ------------------
st.set_page_config(page_title="Reconciliación GL", layout="wide")
st.title("Dashboard de Reconciliación GL")

# ------------------ Inicializar Firebase ------------------
@st.cache_resource
def init_firebase():
    firebase_creds = st.secrets["firebase_credentials"]
    if hasattr(firebase_creds, "to_dict"):
        firebase_creds = firebase_creds.to_dict()
    bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})
    return firestore.client(), bucket_name

# ------------------ Cargar Mapping desde GitHub ------------------
@st.cache_data
def load_mapping():
    url = "https://raw.githubusercontent.com/Enapoles02/Acc-Recon/main/Mapping.csv"
    df = pd.read_csv(url, dtype=str)
    df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
    df = df.rename(columns={"GL Account": "GL Account", "Group": "ReviewGroup"})
    return df

# ------------------ Cargar datos desde Firebase ------------------
@st.cache_data(ttl=300)
def load_index_data():
    db, _ = init_firebase()
    col = db.collection("reconciliation_records")
    docs = col.stream()
    recs = []
    for d in docs:
        data = d.to_dict()
        flat_data = {"_id": d.id}
        for k, v in data.items():
            flat_data[str(k).strip()] = str(v).strip() if v is not None else None
        recs.append(flat_data)
    df = pd.DataFrame(recs)
    df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
    return df

# ------------------ Función para mostrar nombre corto país ------------------
def abbr(country):
    m = {
        "United States of America": "USA",
        "Canada": "CA",
        "Argentina": "ARG",
        "Chile": "CL",
        "Guatemala": "GT",
        "Mexico": "MX",
        "Peru": "PE",
        "Panama": "PA"
    }
    return m.get(country, country[:3].upper())

# ------------------ App principal ------------------
def main():
    st.sidebar.title("🔐 Acceso")
    user = st.sidebar.text_input("Usuario")
    pwd = st.sidebar.text_input("Admin Key", type="password")
    is_admin = (pwd == st.secrets.get("admin_code", "ADMIN"))

    df = load_index_data()
    map_df = load_mapping()

    df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
    map_df.columns = map_df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)

    # Validación GL Account
    if "GL Account" in df.columns and "GL Account" in map_df.columns:
        df["GL Account"] = df["GL Account"].astype(str).str.strip()
        map_df["GL Account"] = map_df["GL Account"].astype(str).str.strip()
        df = df.merge(map_df, on="GL Account", how="left")
        df["ReviewGroup"] = df["ReviewGroup"].fillna("Others")
    else:
        st.error("❌ No se encontró la columna 'GL Account' en los datos o en el mapping.")
        return

    if not user:
        st.warning("Ingresa tu usuario para filtrar tareas.")
        return

    # Asignación de países por usuario
    mapping = {
        "Paula Sarachaga": ["Argentina", "Chile", "Guatemala"],
        "Napoles Enrique": ["Canada"],
        "Julio": ["United States of America"],
        "Guadalupe": ["Mexico", "Peru", "Panama"]
    }

    if "country" in df.columns:
        df["country"] = df["country"].astype(str).str.strip()
        allowed = df["country"].unique().tolist() if is_admin else mapping.get(user, [])
        df = df[df["country"].isin(allowed)]

        if df.empty:
            st.warning("No hay datos disponibles para tu país o usuario.")
    else:
        if not is_admin:
            st.warning("No se encontró la columna 'country' y no se pueden aplicar filtros.")
            df = df.iloc[0:0]

    st.sidebar.markdown("---")
    q = st.sidebar.text_input("Buscar cuenta")
    review_filter = st.sidebar.selectbox("Grupo de revisión", options=["All"] + sorted(df["ReviewGroup"].unique().tolist()))

    if q:
        df = df[df["gl_name"].str.contains(q, case=False, na=False)]
    if review_filter != "All":
        df = df[df["ReviewGroup"] == review_filter]

    # Mostrar lista
    if "start" not in st.session_state:
        st.session_state["start"] = 0

    colL, colR = st.columns([1, 3])
    with colL:
        st.markdown("### Cuentas GL")
        if st.button("↑") and st.session_state["start"] > 0:
            st.session_state["start"] -= 1
        if st.button("↓") and st.session_state["start"] < len(df) - 5:
            st.session_state["start"] += 1
        sub = df.iloc[st.session_state["start"]:st.session_state["start"] + 5]
        for idx, r in sub.iterrows():
            key = f"sel_{idx}_{r['_id']}"
            label = f"{r.get('gl_name', '')} - {r.get('GL Account', '')} ({abbr(r.get('country', ''))})"
            if st.button(label, key=key):
                st.session_state['selected'] = r['_id']

    with colR:
        sel = st.session_state.get('selected')
        if not sel:
            st.info("Selecciona una cuenta del panel izquierdo.")
        else:
            rec = df[df['_id'] == sel].iloc[0].to_dict()
            st.subheader(f"{rec.get('gl_name')} - {rec.get('GL Account')} ({abbr(rec.get('country', ''))})")
            st.write(f"**Assigned Reviewer:** {rec.get('Assigned Reviewer', '')}")
            st.write(f"**Cluster:** {rec.get('Cluster', '')}")
            st.checkbox("Completed", value=rec.get("Completed", "").lower() in ['yes', 'true', '1'])
            st.date_input("Completion Date", value=datetime.date.today())

    # Debug solo visible para admin
    if is_admin:
        with st.expander("🛠 Depuración Admin"):
            st.write("Columnas actuales:", df.columns.tolist())
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("⬇️ Descargar Data combinada", data=csv, file_name="data_combinada.csv", mime='text/csv')

if __name__ == '__main__':
    main()
