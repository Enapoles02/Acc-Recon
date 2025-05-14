import streamlit as st
import pandas as pd
import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# Inicializa Firebase y retorna cliente
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        creds = st.secrets["firebase_credentials"]
        cred = credentials.Certificate(creds.to_dict() if hasattr(creds, "to_dict") else creds)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# Carga los datos desde la colección única, seleccionando solo campos necesarios para mejorar performance
@st.cache_data(ttl=300)
def load_data():
    db = init_firebase()
    # Detectar columnas clave antes de fetch (se asume esquema uniforme)
    # Necesitamos GL y campos de filtro y UI
    # Carga primero un doc para detectar columnas
    sample = next(db.collection("reconciliation_records").limit(1).stream(), None)
    if sample:
        cols = list(sample.to_dict().keys())
    else:
        cols = []
    # Determinar campos a seleccionar
    keys = []
    for key in cols:
        # incluir solo campos relevantes
        if any(k in key.lower() for k in ["gl account name", "gl name", "account name", "assigned reviewer", "reviewed by", "owner", "cluster", "completed", "completion date", "preparer", "country", "fc input", "filler"]):
            keys.append(key)
    # Siempre incluimos ID
    keys = list(set(keys))
    records = []
    # Spinner para feedback
    with st.spinner('Cargando datos de Firestore...'):  
        query = db.collection("reconciliation_records")
        try:
            # Seleccionar solo campos necesarios si la API lo soporta
            if hasattr(query, 'select') and keys:
                query = query.select(keys)
            docs = query.stream()
        except Exception:
            docs = db.collection("reconciliation_records").stream()
        for doc in docs:
            data = doc.to_dict()
            # conservar solo keys seleccionadas + _id
            filtered = {k: data.get(k) for k in keys}
            filtered['_id'] = doc.id
            records.append(filtered)
    return pd.DataFrame(records)

# Obtiene comentarios ordenados por timestamp
@st.cache_data(ttl=60)
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

# Encuentra columna por keywords
def find_column(df, keys):
    for k in keys:
        for c in df.columns:
            if k.lower() in c.lower():
                return c
    return None

# Interfaz principal
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Sidebar: usuario y admin upload
    user = st.sidebar.text_input("Usuario (para comentarios)")
    admin_code = st.secrets.get("admin_code", "ADMIN")
    pwd = st.sidebar.text_input("Clave Admin", type="password")
    is_admin = (pwd == admin_code)
    if pwd:
        st.sidebar.success("Admin" if is_admin else "Clave incorrecta")
    if is_admin:
        file = st.sidebar.file_uploader("Cargar Excel (.xlsx/.xls)", type=["xlsx","xls"])
        if file and st.sidebar.button("Subir a Firestore"):
            upload_data(file)
            st.sidebar.success("Datos cargados")
            st.experimental_rerun()

    # Cargar datos
    df = load_data()
    if df.empty:
        st.warning("No hay datos. Carga un Excel en el modo Admin.")
        return

    # Detectar columnas clave
    gl_col = find_column(df, ["gl account name", "gl name", "account name"])
    reviewer_col = find_column(df, ["assigned reviewer", "reviewed by", "owner"])
    cluster_col = find_column(df, ["cluster"])
    completed_col = find_column(df, ["completed"])
    date_col = find_column(df, ["completion date", "date"])
    filter_preparer_col = find_column(df, ["preparer"])
    filter_country_col = find_column(df, ["country"])
    filter_filler_col = find_column(df, ["fc input", "filler"])

    # Validar columna GL
    if not gl_col:
        st.error(f"No se encontró columna GL. Columnas disponibles: {df.columns.tolist()}")
        return

    # Filtros en sidebar
    df_f = df.copy()
    st.sidebar.header("Filtros")
    if filter_preparer_col:
        opts = ["Todos"] + sorted(df_f[filter_preparer_col].dropna().unique())
        sel = st.sidebar.selectbox("Preparer", opts)
        if sel != "Todos":
            df_f = df_f[df_f[filter_preparer_col] == sel]
    if filter_country_col:
        opts = ["Todos"] + sorted(df_f[filter_country_col].dropna().unique())
        sel = st.sidebar.selectbox("Country", opts)
        if sel != "Todos":
            df_f = df_f[df_f[filter_country_col] == sel]
    if filter_filler_col:
        opts = ["Todos"] + sorted(df_f[filter_filler_col].dropna().unique())
        sel = st.sidebar.selectbox("Filler", opts)
        if sel != "Todos":
            df_f = df_f[df_f[filter_filler_col] == sel]

    # Mostrar cards expandibles para cada cuenta GL
    for idx, rec in df_f.iterrows():
        gl_name = rec.get(gl_col)
        rec_id = rec.get('_id')
        if not gl_name or not rec_id:
            continue
        with st.expander(gl_name):
            # Campos principales
            if reviewer_col:
                st.write(f"**Assigned Reviewer:** {rec.get(reviewer_col)}")
            if cluster_col:
                st.write(f"**Cluster:** {rec.get(cluster_col)}")
            # Completed y fecha
            completed = str(rec.get(completed_col)).lower() in ['yes','true','1'] if completed_col else False
            chk_key = f"chk_{rec_id}"
            new_completed = st.checkbox("Completed", value=completed, key=chk_key)
            date_key = f"date_{rec_id}"
            default_date = datetime.date.today()
            if date_col:
                try:
                    default_date = pd.to_datetime(rec.get(date_col)).date()
                except:
                    pass
            new_date = st.date_input("Completion Date", value=default_date, key=date_key)
            save_key = f"save_{rec_id}"
            if st.button("Guardar cambios", key=save_key):
                updates = {}
                if completed_col:
                    updates[completed_col] = 'Yes' if new_completed else 'No'
                if date_col:
                    updates[date_col] = new_date.strftime('%Y-%m-%d')
                if updates:
                    db = init_firebase()
                    db.collection("reconciliation_records").document(rec_id).update(updates)
                    st.success("Registro actualizado.")
            st.markdown("---")
            # Comentarios estilo chat
            st.subheader("Comentarios")
            for c in get_comments(rec_id):
                ts = c.get('timestamp')
                t_str = ts.strftime('%Y-%m-%d %H:%M') if isinstance(ts, datetime.datetime) else ''
                st.markdown(f"**{c.get('user','Anon')}** ({t_str}): {c.get('text')}")
            c_key = f"comment_{rec_id}"
            new_c = st.text_area("Nuevo comentario:", key=c_key)
            add_key = f"add_{rec_id}"
            if st.button("Agregar comentario", key=add_key):
                if user and new_c:
                    add_comment(rec_id, user, new_c)
                    st.experimental_rerun()
                else:
                    st.error("Proporciona usuario y comentario.")

if __name__ == '__main__':
    main()
