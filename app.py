import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(page_title="Reconciliación GL", layout="wide")
st.title("Dashboard de Reconciliación GL - Base")

# ------------------ Firebase ------------------
@st.cache_resource
def init_firebase():
    firebase_creds = st.secrets["firebase_credentials"]
    if hasattr(firebase_creds, "to_dict"):
        firebase_creds = firebase_creds.to_dict()
    bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})
    return firestore.client()

# ------------------ Cargar datos ------------------
@st.cache_data(ttl=300)
def load_data():
    db = init_firebase()
    docs = db.collection("reconciliation_records").stream()
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

@st.cache_data
def load_mapping():
    url = "https://raw.githubusercontent.com/Enapoles02/Acc-Recon/main/Mapping.csv"
    df = pd.read_csv(url, dtype=str)
    df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
    df = df.rename(columns={"GL Account": "GL Account", "Group": "ReviewGroup"})
    return df

# ------------------ App básica ------------------
def main():
    user = st.sidebar.text_input("Usuario")
    if not user:
        st.warning("Ingresa tu nombre de usuario para comenzar.")
        return

    mapping = {
        "Paula Sarachaga": ["Argentina", "Chile", "Guatemala"],
        "Napoles Enrique": ["Canada"],
        "Julio": ["United States of America"],
        "Guadalupe": ["Mexico", "Peru", "Panama"]
    }

    df = load_data()
    map_df = load_mapping()

    if "GL Account" in df.columns and "GL Account" in map_df.columns:
        df["GL Account"] = df["GL Account"].astype(str).str.strip()
        map_df["GL Account"] = map_df["GL Account"].astype(str).str.strip()
        df = df.merge(map_df, on="GL Account", how="left")
        df["ReviewGroup"] = df["ReviewGroup"].fillna("Others")
    else:
        st.error("No se encontró la columna 'GL Account' en los datos o mapping.")
        return

    if 'country' in df.columns:
        allowed = mapping.get(user, [])
        if allowed:
            df = df[df['country'].isin(allowed)]
        else:
            st.warning("Tu usuario no tiene países asignados o no hay coincidencias.")
    else:
        st.warning("No se encontró la columna 'country' en los datos.")

    st.subheader("📄 Datos cargados")
    st.write(df)

if __name__ == '__main__':
    main()
