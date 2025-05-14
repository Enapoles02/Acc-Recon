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

# Lista las colecciones de Firestore que empiezan con nuestro prefijo
@st.cache_data(ttl=600)
def list_collections():
    db = init_firebase()
    return [col.id for col in db.collections() if col.id.startswith("reconciliation_records_")]

# Carga datos de una colección en DataFrame
@st.cache_data(ttl=600)
def load_data(collection_name: str) -> pd.DataFrame:
    db = init_firebase()
    docs = db.collection(collection_name).stream()
    df = pd.DataFrame([doc.to_dict() for doc in docs])
    return df

# Admin: sube cada pestaña de Excel como colección separada
def upload_data(file):
    db = init_firebase()
    sheets = pd.read_excel(file, sheet_name=None)
    for sheet_name, df_sheet in sheets.items():
        col_name = f"reconciliation_records_{sheet_name}"
        col = db.collection(col_name)
        # eliminar existentes
        for doc in col.stream():
            doc.reference.delete()
        # subir nuevos
        for idx, row in df_sheet.iterrows():
            col.document(str(idx)).set(row.to_dict())

# Detecta columna por clave parcial
def find_column(df, keywords):
    for kw in keywords:
        for col in df.columns:
            if kw.lower() in col.lower():
                return col
    return None

# Lógica de visualización y filtros dentro de cada pestaña
def show_tab(df: pd.DataFrame, sheet_label: str):
    st.header(f"Sheet: {sheet_label}")
    if df.empty:
        st.info("No hay datos en esta pestaña.")
        return

    # Rename dinámico opcional para consistencia interna
    # Encuentra nombres de columnas clave
    gl_col = find_column(df, ["gl account name", "gl name"])
    preparer_col = find_column(df, ["preparer"])
    country_col = find_column(df, ["country"])
    filler_col = find_column(df, ["fc input", "filler"])
    completed_col = find_column(df, ["completed"])
    completion_date_col = find_column(df, ["completion date"] )

    missing = [name for name in [gl_col, preparer_col, country_col, filler_col] if name is None]
    if missing:
        st.error(f"Faltan columnas para esta pestaña: {missing}")
        return

    # Filtros dependientes dentro de la pestaña
    st.subheader("Filtros")
    df_filtered = df.copy()
    sel_preparer = st.selectbox("Preparer", ["Todos"] + sorted(df_filtered[preparer_col].dropna().unique()))
    if sel_preparer != "Todos": df_filtered = df_filtered[df_filtered[preparer_col] == sel_preparer]

    sel_country = st.selectbox("Country", ["Todos"] + sorted(df_filtered[country_col].dropna().unique()))
    if sel_country != "Todos": df_filtered = df_filtered[df_filtered[country_col] == sel_country]

    sel_filler = st.selectbox("Filler", ["Todos"] + sorted(df_filtered[filler_col].dropna().unique()))
    if sel_filler != "Todos": df_filtered = df_filtered[df_filtered[filler_col] == sel_filler]

    # Selección de GL en columna izquierda y detalle en derecha
    col1, col2 = st.columns([1, 3])
    with col1:
        st.subheader("Cuentas GL")
        gls = sorted(df_filtered[gl_col].dropna().unique())
        selected_gl = st.selectbox("Selecciona GL Account Name", gls)

    with col2:
        st.subheader(f"Detalle de '{selected_gl}'")
        detalle = df_filtered[df_filtered[gl_col] == selected_gl]
        cols_to_show = []
        if completed_col: cols_to_show.append(completed_col)
        if completion_date_col: cols_to_show.append(completion_date_col)
        st.dataframe(detalle[cols_to_show] if cols_to_show else detalle)

# App principal
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Sidebar - Admin
    ADMIN_CODE = st.secrets.get("admin_code", "ADMIN")
    admin_input = st.sidebar.text_input("Clave Admin", type="password")
    is_admin = (admin_input == ADMIN_CODE)
    if admin_input:
        if is_admin:
            st.sidebar.success("Modo Admin activado")
        else:
            st.sidebar.error("Clave incorrecta")

    if is_admin:
        st.sidebar.markdown("---")
        st.sidebar.header("Cargar nueva data")
        file = st.sidebar.file_uploader("Excel (.xlsx/.xls)", type=["xlsx", "xls"], key="admin_upload")
        if file and st.sidebar.button("Cargar a Firestore", key="upload_btn"):
            try:
                upload_data(file)
                st.sidebar.success("Datos subidos correctamente.")
            except Exception as e:
                st.sidebar.error(f"Error al subir: {e}")

    # Cargar pestañas disponibles
    collections = list_collections()
    if not collections:
        st.warning("No hay colecciones cargadas. Usa el modo Admin para subir datos.")
        return

    # Crear pestañas según sheets
    sheets = [col.replace("reconciliation_records_", "") for col in collections]
    tabs = st.tabs(sheets)
    for tab, sheet_label, col_name in zip(tabs, sheets, collections):
        with tab:
            df = load_data(col_name)
            show_tab(df, sheet_label)

if __name__ == "__main__":
    main()
