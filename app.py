import streamlit as st
import pandas as pd
import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# Inicializa Firebase y retorna cliente
def init_firebase():
    if not firebase_admin._apps:
        creds = st.secrets["firebase_credentials"]
        cred = credentials.Certificate(creds.to_dict() if hasattr(creds, "to_dict") else creds)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# Carga los datos desde la colección única
def load_data():
    db = init_firebase()
    docs = db.collection("reconciliation_records").stream()
    records = []
    for doc in docs:
        data = doc.to_dict()
        data['_id'] = doc.id
        records.append(data)
    df = pd.DataFrame(records)
    if df.empty:
        st.warning("No se encontraron datos. Usa el modo Admin para cargar un Excel.")
    return df

# Obtiene comentarios ordenados por timestamp
def get_comments(record_id):
    db = init_firebase()
    comments = []
    coll = db.collection("reconciliation_records").document(record_id).collection("comments")
    for d in coll.order_by("timestamp").stream():
        c = d.to_dict()
        ts = c.get('timestamp')
        if hasattr(ts, 'to_datetime'):
            c['timestamp'] = ts.to_datetime()
        comments.append(c)
    return comments

# Agrega un comentario con SERVER_TIMESTAMP
def add_comment(record_id, user, text):
    db = init_firebase()
    coll = db.collection("reconciliation_records").document(record_id).collection("comments")
    coll.add({
        'user': user,
        'text': text,
        'timestamp': firestore.SERVER_TIMESTAMP
    })

# Encuentra columna por keywords
def find_column(df, keys):
    for k in keys:
        for c in df.columns:
            if k.lower() in c.lower():
                return c
    return None

# Admin: sube Excel a Firestore
def upload_data(file):
    db = init_firebase()
    df_sheet = pd.read_excel(file)
    # eliminar PowerAppsId y Unnamed
    df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.lower().str.contains('powerappsid')]
    df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.startswith('Unnamed')]
    col = db.collection("reconciliation_records")
    for doc in col.stream():
        doc.reference.delete()
    for idx, row in df_sheet.iterrows():
        col.document(str(idx)).set(row.dropna().to_dict())

# Interfaz principal
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Sidebar: usuario y admin
    user = st.sidebar.text_input("Usuario (para comentarios)")
    admin_code = st.secrets.get("admin_code", "ADMIN")
    pwd = st.sidebar.text_input("Clave Admin", type="password")
    is_admin = (pwd == admin_code)
    if pwd:
        st.sidebar.success("Admin" if is_admin else "Clave incorrecta")
    if is_admin:
        file = st.sidebar.file_uploader("Cargar Excel", type=["xlsx","xls"])
        if file and st.sidebar.button("Subir a Firestore"):
            upload_data(file)
            st.sidebar.success("Datos cargados")
            st.experimental_rerun()

    # DataFrame principal
    df = load_data()
    if df.empty:
        return

    # Columnas clave
    gl_col = find_column(df, ["gl account name", "gl name", "account name"])
    reviewer_col = find_column(df, ["assigned reviewer", "reviewed by", "owner"])
    cluster_col = find_column(df, ["cluster"])
    completed_col = find_column(df, ["completed"])
    date_col = find_column(df, ["completion date", "date"])
    comment_key = "comments"

    if not gl_col:
        st.error(f"No se encontró columna GL en: {df.columns.tolist()}")
        return

    # Layout: menú izquierdo y panel derecho
    col1, col2 = st.columns([1.5, 3])
    # Menú de cuentas GL
    with col1:
        st.header("Cuentas GL")
        gl_list = sorted(df[gl_col].dropna().unique())
        selected = st.radio("", gl_list)

    # Panel de detalles
    with col2:
        st.header(selected)
        rec = df[df[gl_col] == selected].iloc[0]
        rec_id = rec.get('_id')
        # Mostrar campos principales
        if reviewer_col:
            st.write(f"**Assigned Reviewer:** {rec.get(reviewer_col)}")
        if cluster_col:
            st.write(f"**Cluster:** {rec.get(cluster_col)}")
        # Completed y Fecha
        completed = str(rec.get(completed_col)).lower() in ['yes','true','1'] if completed_col else False
        chk = st.checkbox("Completed", value=completed)
        # Fecha
        default_date = datetime.date.today()
        if date_col:
            try:
                default_date = pd.to_datetime(rec.get(date_col)).date()
            except:
                pass
        new_dt = st.date_input("Completion Date", value=default_date)
        if st.button("Guardar cambios"):
            updates = {}
            if completed_col:
                updates[completed_col] = 'Yes' if chk else 'No'
            if date_col:
                updates[date_col] = new_dt.strftime('%Y-%m-%d')
            if updates:
                db = init_firebase()
                db.collection("reconciliation_records").document(rec_id).update(updates)
                st.success("Datos actualizados")
        st.markdown("---")
        # Comentarios estilo chat
        st.subheader("Comentarios")
        for c in get_comments(rec_id):
            ts = c.get('timestamp')
            t_str = ts.strftime('%Y-%m-%d %H:%M') if isinstance(ts, datetime.datetime) else ''
            st.markdown(f"**{c.get('user','Anon')}** ({t_str}): {c.get('text')}  ")
        new_c = st.text_area("Nuevo comentario:")
        if st.button("Agregar comentario"):
            if user and new_c:
                add_comment(rec_id, user, new_c)
                st.experimental_rerun()
            else:
                st.error("Proporciona usuario y comentario.")

if __name__ == '__main__':
    main()
