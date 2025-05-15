import streamlit as st
import pandas as pd
import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage
from io import BytesIO

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
    df.columns = df.columns.str.strip()
    df = df.rename(columns={"GL Account": "GL Account", "Group": "ReviewGroup"})
    return df

# ------------------ Funciones de carga ------------------
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

    if "GL Account" in df.columns:
        df["GL Account"] = df["GL Account"].astype(str).str.strip()
    if "GL Account" in map_df.columns:
        map_df["GL Account"] = map_df["GL Account"].astype(str).str.strip()

    if st.checkbox("🔍 Ver datos brutos de Firebase"):
        st.dataframe(df)

    if st.checkbox("📄 Ver Mapping completo (sin combinar)"):
        st.dataframe(map_df)

    if "GL Account" in df.columns and "GL Account" in map_df.columns:
        df = df.merge(map_df, on="GL Account", how="left")
        df["ReviewGroup"] = df["ReviewGroup"].fillna("Others")

        st.subheader("🧭 Comparación de Mapping")
        st.write(f"Total cuentas distintas en Mapping: {map_df['GL Account'].nunique()}")
        st.write(f"Total cuentas distintas en Firebase: {df['GL Account'].nunique()}")
        st.write(f"Total líneas en Firebase: {len(df)}")

        missing = set(df['GL Account'].unique()) - set(map_df['GL Account'].unique())
        if missing:
            st.warning(f"⚠️ Cuentas en Firebase NO encontradas en Mapping: {len(missing)}")
            st.dataframe(sorted(missing))
        else:
            st.success("✅ Todas las cuentas están presentes en Mapping.")

        if st.checkbox("📊 Mostrar Data combinada"):
            st.dataframe(df)
    else:
        st.error("❌ No se encontró la columna 'GL Account' en los datos.")

if __name__ == '__main__':
    main()
