import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# Inicializa Firebase Admin SDK y retorna cliente
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        creds = st.secrets["firebase_credentials"]
        cred_dict = creds.to_dict() if hasattr(creds, "to_dict") else creds
        firebase_admin.initialize_app(credentials.Certificate(cred_dict))
    return firestore.client()

# Carga datos de la colección única en DataFrame
def load_data():
    db = init_firebase()
    col = db.collection("reconciliation_records")
    docs = col.stream()
    df = pd.DataFrame([doc.to_dict() for doc in docs])
    if df.empty:
        st.warning("No se encontraron datos en Firestore. Usa el modo Admin para cargar el Excel.")
    return df

# Subida Admin: lee una sola hoja de Excel y la sube a la colección única
def upload_data(file):
    db = init_firebase()
    # Lee primera hoja por defecto
    df_sheet = pd.read_excel(file)
    # Eliminar campos reservados y columnas Unnamed
    df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.lower().str.contains('powerappsid')]
    df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.startswith('Unnamed')]
    col = db.collection("reconciliation_records")
    # Eliminar documentos existentes
    for doc in col.stream():
        doc.reference.delete()
    # Subir nuevos registros
    for idx, row in df_sheet.iterrows():
        col.document(str(idx)).set(row.dropna().to_dict())

# Encuentra columna por palabra clave
def find_column(df, keywords):
    for kw in keywords:
        for col in df.columns:
            if kw.lower() in col.lower():
                return col
    return None

# App principal
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Sidebar: modo Admin
    ADMIN_CODE = st.secrets.get("admin_code", "ADMIN")
    admin_input = st.sidebar.text_input("Clave Admin", type="password")
    is_admin = admin_input == ADMIN_CODE
    if admin_input:
        if is_admin:
            st.sidebar.success("Modo Admin activado")
        else:
            st.sidebar.error("Clave incorrecta")
    if is_admin:
        st.sidebar.markdown("---")
        st.sidebar.header("Cargar Excel a Firestore")
        file = st.sidebar.file_uploader("Excel (.xlsx/.xls)", type=["xlsx","xls"], key="admin_upload")
        if file and st.sidebar.button("Subir a Firestore"):
            try:
                upload_data(file)
                st.sidebar.success("Datos cargados correctamente.")
            except Exception as e:
                st.sidebar.error(f"Error al cargar: {e}")

    # Cargar datos
    df = load_data()
    if df.empty:
        return

    # Detectar columnas
    gl_col = find_column(df, ["gl account name", "gl name", "account name"])
    preparer_col = find_column(df, ["preparer"])
    country_col = find_column(df, ["country"])
    filler_col = find_column(df, ["fc input", "filler"])
    completed_col = find_column(df, ["completed"])
    completion_date_col = find_column(df, ["completion date"])
    missing = [c for c in [gl_col, preparer_col, country_col, filler_col] if c is None]
    if missing:
        st.error(f"Faltan columnas necesarias: {missing}")
        return

    # Filtros dependientes en sidebar
    st.sidebar.markdown("---")
    st.sidebar.header("Filtros")
    df_f = df.copy()
    preparers = ["Todos"] + sorted(df_f[preparer_col].dropna().unique())
    sel_preparer = st.sidebar.selectbox("Preparer", preparers)
    if sel_preparer != "Todos":
        df_f = df_f[df_f[preparer_col] == sel_preparer]
    countries = ["Todos"] + sorted(df_f[country_col].dropna().unique())
    sel_country = st.sidebar.selectbox("Country", countries)
    if sel_country != "Todos":
        df_f = df_f[df_f[country_col] == sel_country]
    fillers = ["Todos"] + sorted(df_f[filler_col].dropna().unique())
    sel_filler = st.sidebar.selectbox("Filler", fillers)
    if sel_filler != "Todos":
        df_f = df_f[df_f[filler_col] == sel_filler]

    # Layout: GL selector y detalle
    col1, col2 = st.columns([1, 3])
    with col1:
        st.subheader("Cuentas GL")
        gls = sorted(df_f[gl_col].dropna().unique())
        selected_gl = st.selectbox("Selecciona GL Account Name", gls)
    with col2:
        st.subheader(f"Detalle de '{selected_gl}'")
        detail = df_f[df_f[gl_col] == selected_gl]
        cols_show = []
        if completed_col:
            cols_show.append(completed_col)
        if completion_date_col:
            cols_show.append(completion_date_col)
        st.dataframe(detail[cols_show] if cols_show else detail)

if __name__ == "__main__":
    main()
