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
def load_data():
    db = init_firebase()
    COLLECTION_NAME = "reconciliation_records"  # Ajusta si tu colección tiene otro nombre
    docs = db.collection(COLLECTION_NAME).stream()
    data = [doc.to_dict() for doc in docs]
    df = pd.DataFrame(data)
    if df.empty:
        st.warning("No se encontraron datos en Firestore. ¿Has cargado la colección correctamente?")
    return df

# Función para reemplazar toda la colección con nuevo DataFrame
def upload_data(df: pd.DataFrame):
    db = init_firebase()
    col = db.collection("reconciliation_records")
    for doc in col.stream():
        doc.reference.delete()
    for idx, row in df.iterrows():
        col.document(str(idx)).set(row.to_dict())

# App principal
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Modo Admin para cargar datos
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
                df_new = pd.read_excel(file)
                upload_data(df_new)
                st.sidebar.success("Datos cargados correctamente.")
            except Exception as e:
                st.sidebar.error(f"Error al cargar datos: {e}")

    # Cargar y validar datos
    df = load_data()
    if df.empty:
        return

    # Renombrar columnas conocidas si existen\    
    rename_map = {
        "GL Account name": "gl_name",
        "Completed": "completed",
        "Completion date": "completion_date",
        "Preparer from team": "preparer",
        "FC Input": "filler",
        "Country": "country"
    }
    df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns}, inplace=True)

    # Detectar columnas dinámicas para filtros y GL
    preparer_col = "preparer" if "preparer" in df.columns else next((c for c in df.columns if "Preparer" in c), None)
    country_col = "country" if "country" in df.columns else next((c for c in df.columns if c.lower() == "country"), None)
    filler_col = "filler" if "filler" in df.columns else next((c for c in df.columns if "FC Input" in c), None)
    gl_col = "gl_name" if "gl_name" in df.columns else next((c for c in df.columns if "GL Account name" in c), None)

    # Validar columnas necesarias
    missing = [name for name in [preparer_col, country_col, filler_col, gl_col] if name is None]
    if missing:
        st.error(f"No se encontraron columnas necesarias: {missing}. Columnas disponibles: {df.columns.tolist()}")
        return

    # Filtros dependientes en sidebar
    st.sidebar.markdown("---")
    st.sidebar.header("Filtros")
    preparers = ["Todos"] + sorted(df[preparer_col].dropna().unique().tolist())
    sel_preparer = st.sidebar.selectbox("Preparer", preparers)
    if sel_preparer != "Todos": df = df[df[preparer_col] == sel_preparer]

    countries = ["Todos"] + sorted(df[country_col].dropna().unique().tolist())
    sel_country = st.sidebar.selectbox("Country", countries)
    if sel_country != "Todos": df = df[df[country_col] == sel_country]

    fillers = ["Todos"] + sorted(df[filler_col].dropna().unique().tolist())
    sel_filler = st.sidebar.selectbox("Filler", fillers)
    if sel_filler != "Todos": df = df[df[filler_col] == sel_filler]

    # Layout principal: GL selector y detalle
    col1, col2 = st.columns([1, 3])
    with col1:
        st.subheader("Cuentas GL")
        gls = sorted(df[gl_col].dropna().unique().tolist())
        selected_gl = st.selectbox("Selecciona GL Account Name", gls)

    with col2:
        st.subheader(f"Detalle de '{selected_gl}'")
        detalle = df[df[gl_col] == selected_gl]
        if not detalle.empty:
            st.dataframe(detalle[[
                rename_map.get("Completed", "Completed" ),
                rename_map.get("Completion date", "Completion date")
            ]])
        else:
            st.write("No hay datos para la cuenta seleccionada.")

if __name__ == "__main__":
    main()
