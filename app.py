import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

st.set_page_config(page_title="Export Firestore to CSV", layout="wide")

# --- Inicializa Firebase ---
if not firebase_admin._apps:
    cred = credentials.Certificate(st.secrets["firebase_credentials"].to_dict())
    firebase_admin.initialize_app(cred)

db = firestore.client()

st.title("📤 Export Firestore Data to CSV")

@st.cache_data
def fetch_reconciliation_records():
    docs = db.collection("reconciliation_records").stream()
    data = []
    for doc in docs:
        record = doc.to_dict()
        record["id"] = doc.id
        data.append(record)
    return pd.DataFrame(data)

# --- Descargar data ---
with st.spinner("Cargando datos desde Firestore..."):
    df = fetch_reconciliation_records()

if not df.empty:
    st.success(f"Se cargaron {len(df)} registros.")
    st.dataframe(df.head(), use_container_width=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Descargar CSV",
        data=csv,
        file_name=f"reconciliation_export_{datetime.now().date()}.csv",
        mime="text/csv"
    )
else:
    st.warning("No se encontraron registros en Firestore.")
