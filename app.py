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

# Lista las colecciones de Firestore válidas para tabs
@st.cache_data(ttl=600)
def list_collections():
    db = init_firebase()
    cols = [col.id for col in db.collections() if col.id == "reconciliation_records" or col.id.startswith("reconciliation_records_")]
    return cols

# Carga datos de una colección en DataFrame
def load_data(collection_name: str) -> pd.DataFrame:
    db = init_firebase()
    docs = db.collection(collection_name).stream()
    df = pd.DataFrame([doc.to_dict() for doc in docs])
    return df

# Subida Admin: cada pestaña de Excel como colección separada
def upload_data(file):
    db = init_firebase()
    sheets = pd.read_excel(file, sheet_name=None)
    for sheet_name, df_sheet in sheets.items():
        # Eliminar campos reservados y columnas 'Unnamed'
        df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.lower().str.contains('powerappsid')]
        df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.startswith('Unnamed')]

        # Definir nombre de colección: genérico para Americas
        if sheet_name.lower() == "americas":
            col_name = "reconciliation_records"
        else:
            col_name = f"reconciliation_records_{sheet_name}"

        col = db.collection(col_name)
        # Eliminar documentos existentes
        for doc in col.stream():
            doc.reference.delete()
        # Subir nuevos registros
        for idx, row in df_sheet.iterrows():
            try:
                col.document(str(idx)).set(row.dropna().to_dict())
            except Exception as e:
                st.sidebar.error(f"Error subiendo fila {idx}: {e}")

# Encuentra columna por palabra clave
def find_column(df, keywords):
    for kw in keywords:
        for col in df.columns:
            if kw.lower() in col.lower():
                return col
    return None

# Muestra datos y filtros en una pestaña
def show_tab(df: pd.DataFrame, sheet_label: str):
    st.header(f"Pestaña: {sheet_label}")
    if df.empty:
        st.info("No hay datos en esta pestaña.")
        return

    # Detectar columnas clave
    gl_col = find_column(df, ["gl account name", "gl name", "account name"])
    preparer_col = find_column(df, ["preparer"])
    country_col = find_column(df, ["country"])
    filler_col = find_column(df, ["fc input", "filler"])
    completed_col = find_column(df, ["completed"])
    completion_date_col = find_column(df, ["completion date"])

    missing = [name for name in [gl_col, preparer_col, country_col, filler_col] if name is None]
    if missing:
        st.error(f"Faltan columnas: {missing}")
        return

    # Filtros dependientes
    df_f = df.copy()
    sel_preparer = st.selectbox("Preparer", ["Todos"] + sorted(df_f[preparer_col].dropna().unique()))
    if sel_preparer != "Todos":
        df_f = df_f[df_f[preparer_col] == sel_preparer]
    sel_country = st.selectbox("Country", ["Todos"] + sorted(df_f[country_col].dropna().unique()))
    if sel_country != "Todos":
        df_f = df_f[df_f[country_col] == sel_country]
    sel_filler = st.selectbox("Filler", ["Todos"] + sorted(df_f[filler_col].dropna().unique()))
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

# App principal
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Sidebar Admin
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
        st.sidebar.header("Cargar nueva data")
        file = st.sidebar.file_uploader("Excel (.xlsx/.xls)", type=["xlsx", "xls"], key="admin_upload")
        if file and st.sidebar.button("Subir a Firestore"):
            upload_data(file)
            st.sidebar.success("Datos subidos correctamente.")

    # Crear tabs desde colecciones
    collections = list_collections()
    if not collections:
        st.warning("No hay datos. Usa Admin para subir Excel con pestaña 'Americas'.")
        return
    sheets = []
    for col in collections:
        if col == "reconciliation_records":
            sheets.append("Americas")
        else:
            sheets.append(col.replace("reconciliation_records_", ""))
    tabs = st.tabs(sheets)
    for tab, sheet_label, col in zip(tabs, sheets, collections):
        with tab:
            df = load_data(col)
            show_tab(df, sheet_label)

if __name__ == "__main__":
    main()
