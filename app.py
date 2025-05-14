import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# Inicializa Firebase Admin SDK
def init_firebase():
    if not firebase_admin._apps:
        creds = st.secrets["firebase_credentials"]
        cred_dict = creds.to_dict() if hasattr(creds, "to_dict") else creds
        firebase_admin.initialize_app(credentials.Certificate(cred_dict))
    return firestore.client()

# Carga los datos desde Firestore a un DataFrame
@st.cache_data(ttl=600)
def load_data():
    db = init_firebase()
    COLLECTION_NAME = "reconciliation_records"
    docs = db.collection(COLLECTION_NAME).stream()
    return pd.DataFrame([doc.to_dict() for doc in docs])

# Función para reemplazar toda la colección con nuevo DataFrame
def upload_data(df: pd.DataFrame):
    db = init_firebase()
    col = db.collection("reconciliation_records")
    # Elimina documentos existentes
    for doc in col.stream():
        doc.reference.delete()
    # Carga nuevos registros
    for idx, row in df.iterrows():
        col.document(str(idx)).set(row.to_dict())

# App principal
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Admin mode
    ADMIN_CODE = st.secrets.get("admin_code", "ADMIN")
    admin_input = st.sidebar.text_input("Clave Admin", type="password")
    is_admin = (admin_input == ADMIN_CODE)
    if admin_input:
        if is_admin:
            st.sidebar.success("Modo Admin activado")
        else:
            st.sidebar.error("Clave incorrecta")

    # En modo admin, mostrar uploader para actualizar la base
    if is_admin:
        st.sidebar.markdown("---")
        st.sidebar.header("Cargar nueva data")
        file = st.sidebar.file_uploader("Excel (.xlsx/.xls)", type=["xlsx", "xls"], key="admin_upload")
        if file and st.sidebar.button("Cargar a Firestore", key="upload_btn"):
            try:
                df_new = pd.read_excel(file)
                upload_data(df_new)
                st.sidebar.success("Datos cargados correctamente.")
            except Exception as e:
                st.sidebar.error(f"Error al cargar datos: {e}")

    # Carga y prepara datos
    df = load_data()
    df = df.rename(columns={
        "GL Account name": "gl_name",
        "Completed": "completed",
        "Completion date": "completion_date",
        "Preparer from team": "preparer",
        "Country": "country",
        "FC Input": "filler"
    })

    # Filtros dependientes
    st.sidebar.markdown("---")
    st.sidebar.header("Filtros")
    preparers = ["Todos"] + sorted(df["preparer"].dropna().unique().tolist())
    sel_preparer = st.sidebar.selectbox("Preparer", preparers)
    if sel_preparer != "Todos": df = df[df["preparer"] == sel_preparer]

    countries = ["Todos"] + sorted(df["country"].dropna().unique().tolist())
    sel_country = st.sidebar.selectbox("Country", countries)
    if sel_country != "Todos": df = df[df["country"] == sel_country]

    fillers = ["Todos"] + sorted(df["filler"].dropna().unique().tolist())
    sel_filler = st.sidebar.selectbox("Filler", fillers)
    if sel_filler != "Todos": df = df[df["filler"] == sel_filler]

    # Layout principal
    col1, col2 = st.columns([1, 3])
    with col1:
        st.subheader("Cuentas GL")
        gls = sorted(df["gl_name"].dropna().unique().tolist())
        selected_gl = st.selectbox("Selecciona GL Account Name", gls)
    with col2:
        st.subheader(f"Detalle de '{selected_gl}'")
        detalle = df[df["gl_name"] == selected_gl]
        if not detalle.empty:
            st.write(detalle[["completed", "completion_date"]])
        else:
            st.write("No hay datos para la cuenta seleccionada.")

if __name__ == "__main__":
    main()
