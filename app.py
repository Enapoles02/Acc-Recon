import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# Inicializar Firebase Admin SDK si no está inicializado
def init_firebase():
    if not firebase_admin._apps:
        # Usa las credenciales desde secrets.toml
        creds = st.secrets["firebase_credentials"]
        # Si secrets se carga como AttrDict, conviértelo a dict
        cred = credentials.Certificate(creds.to_dict() if hasattr(creds, "to_dict") else creds)
        firebase_admin.initialize_app(cred)

# Función para explorar el DataFrame
def explorar_df(df: pd.DataFrame):
    st.subheader("Vista Previa de Datos")
    st.dataframe(df)

    st.subheader("Información General")
    info = pd.DataFrame({
        "Tipo de Dato": df.dtypes,
        "Valores Únicos": df.nunique(),
        "Valores Nulos": df.isna().sum()
    })
    st.dataframe(info)

    st.subheader("Estadísticas Descriptivas")
    try:
        st.dataframe(df.describe(include='all').T)
    except Exception:
        st.write("No se pudieron generar estadísticas descriptivas para todos los tipos.")

    if st.checkbox("Mostrar valores únicos de una columna"):  
        col = st.selectbox("Selecciona columna", df.columns)
        st.write(df[col].unique())

# App principal
def main():
    st.title("Explorador de Base de Datos")
    st.markdown("Carga un archivo de Excel para explorar su contenido de forma interactiva.")

    # Inicializa Firebase (si planeas usar Firestore más adelante)
    init_firebase()

    # Subida de archivo Excel
    uploaded_file = st.file_uploader(
        "📁 Selecciona un archivo Excel (.xlsx, .xls)", 
        type=["xlsx", "xls"]
    )

    if uploaded_file is not None:
        try:
            df = pd.read_excel(uploaded_file)
            explorar_df(df)
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

    else:
        st.info("Espera un archivo para comenzar la exploración.")

if __name__ == '__main__':
    main()
