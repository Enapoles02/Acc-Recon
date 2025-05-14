import streamlit as st
import pandas as pd
import datetime
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
@st.cache_data(ttl=300)
def load_data():
    db = init_firebase()
    col = db.collection("reconciliation_records")
    docs = col.stream()
    records = []
    for doc in docs:
        data = doc.to_dict()
        data["_id"] = doc.id
        records.append(data)
    df = pd.DataFrame(records)
    if df.empty:
        st.warning("No se encontraron datos en Firestore. Usa el modo Admin para cargar el Excel.")
    return df

# Obtiene comentarios de subcolección
@st.cache_data(ttl=60)
def get_comments(doc_id):
    db = init_firebase()
    coll = db.collection("reconciliation_records").document(doc_id).collection("comments")
    docs = coll.order_by("timestamp").stream()
    comments = []
    for d in docs:
        c = d.to_dict()
        # convertir timestamp a datetime si viene como Firestore timestamp
        ts = c.get("timestamp")
        if hasattr(ts, 'to_datetime'):
            c['timestamp'] = ts.to_datetime()
        comments.append(c)
    return comments

# Agrega un comentario en Firestore
def add_comment(doc_id, user, text):
    db = init_firebase()
    coll = db.collection("reconciliation_records").document(doc_id).collection("comments")
    coll.add({
        "user": user,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

# Encuentra columna por palabra clave
def find_column(df, keywords):
    for kw in keywords:
        for col in df.columns:
            if kw.lower() in col.lower():
                return col
    return None

# Subida Admin: lee una sola hoja de Excel y la sube a la colección única
def upload_data(file):
    db = init_firebase()
    df_sheet = pd.read_excel(file)
    df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.lower().str.contains('powerappsid')]
    df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.startswith('Unnamed')]
    col = db.collection("reconciliation_records")
    # Eliminar documentos existentes
    for doc in col.stream():
        doc.reference.delete()
    # Subir nuevos registros
    for idx, row in df_sheet.iterrows():
        col.document(str(idx)).set(row.dropna().to_dict())

# App principal
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Usuario para comentarios
    user = st.sidebar.text_input("Usuario:")
    
    # Sidebar Admin
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
        st.sidebar.header("Cargar Excel a Firestore")
        file = st.sidebar.file_uploader("Excel (.xlsx/.xls)", type=["xlsx","xls"])
        if file and st.sidebar.button("Subir a Firestore"):
            try:
                upload_data(file)
                st.sidebar.success("Datos cargados correctamente.")
                st.experimental_rerun()
            except Exception as e:
                st.sidebar.error(f"Error al cargar: {e}")

    # Cargar datos
    df = load_data()
    if df.empty:
        return

    # Detectar columnas
    gl_col = find_column(df, ["gl account name", "gl name", "account name"])
    completed_col = find_column(df, ["completed"])
    completion_date_col = find_column(df, ["completion date"])

    missing = [c for c in [gl_col] if c is None]
    if missing:
        st.error(f"Faltan columnas necesarias: {missing}")
        return

    # Menú de cuentas GL como expander
    st.header("Cuentas GL")
    for idx, row in df.iterrows():
        gl_name = row.get(gl_col)
        doc_id = row.get("_id")
        if not gl_name or not doc_id:
            continue
        with st.expander(gl_name):
            # Completed checkbox y fecha
            current_completed = row.get(completed_col)
            val_completed = True if str(current_completed).lower() in ["yes", "true", "1"] else False
            new_completed = st.checkbox("Completed", value=val_completed, key=f"completed_{doc_id}")

            # Date input
            raw_date = row.get(completion_date_col)
            try:
                default_date = pd.to_datetime(raw_date).date()
            except Exception:
                default_date = datetime.date.today()
            new_date = st.date_input("Completion Date", value=default_date, key=f"date_{doc_id}")

            # Botón guardar
            if st.button("Guardar cambios", key=f"save_{doc_id}"):
                db = init_firebase()
                db.collection("reconciliation_records").document(doc_id).update({
                    completed_col: "Yes" if new_completed else "No",
                    completion_date_col: new_date.strftime("%Y-%m-%d")
                })
                st.success("Registro actualizado.")

            # Comentarios estilo chat
            st.subheader("Comentarios")
            comments = get_comments(doc_id)
            for cm in comments:
                ts = cm.get("timestamp")
                ts_str = ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, datetime.datetime) else str(ts)
                st.markdown(f"**{cm.get('user', 'Anon')}** ({ts_str}): {cm.get('text')}")
            # Nuevo comentario
            new_comment = st.text_area("Escribe un comentario...", key=f"comment_{doc_id}")
            if st.button("Agregar comentario", key=f"add_comment_{doc_id}"):
                if user and new_comment:
                    add_comment(doc_id, user, new_comment)
                    st.experimental_rerun()
                else:
                    st.error("Ingresa usuario y comentario para agregar.")

if __name__ == "__main__":
    main()
