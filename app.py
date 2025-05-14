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

# Carga índices: solo campos necesarios (GL, filtros)
@st.cache_data(ttl=300)
def load_index_data():
    db = init_firebase()
    col = db.collection("reconciliation_records")
    # Solicitar solo campos clave
    select_fields = [
        find_column_name(col, ["gl account name", "gl name", "account name"]),
        find_column_name(col, ["preparer"]),
        find_column_name(col, ["country"]),
        find_column_name(col, ["fc input", "filler"])
    ]
    select_fields = [f for f in select_fields if f]
    docs = col.stream() if not select_fields else col.select(select_fields).stream()
    records = []
    for doc in docs:
        data = doc.to_dict()
        data['_id'] = doc.id
        # mantener solo índice y filtros
        record = {k: data.get(k) for k in select_fields}
        record['_id'] = doc.id
        records.append(record)
    return pd.DataFrame(records)

# Detecta nombre de columna dinámicamente
def find_column_name(collection, keywords):
    # Obtener un documento de muestra para extraer columnas
    sample = next(collection.limit(1).stream(), None)
    if not sample:
        return None
    cols = sample.to_dict().keys()
    for kw in keywords:
        for c in cols:
            if kw.lower() in c.lower():
                return c
    return None

# Carga detalle de un solo registro por id
@st.cache_data(ttl=60)
def load_record(rec_id):
    db = init_firebase()
    doc = db.collection("reconciliation_records").document(rec_id).get()
    if not doc.exists:
        return {}
    data = doc.to_dict()
    data['_id'] = rec_id
    return data

# Obtiene comentarios ordenados por timestamp
@st.cache_data(ttl=60)
def get_comments(record_id):
    db = init_firebase()
    coll = db.collection("reconciliation_records").document(record_id).collection("comments")
    comments = []
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
    coll.add({ 'user': user, 'text': text, 'timestamp': firestore.SERVER_TIMESTAMP })

# Admin: sube Excel a Firestore
def upload_data(file):
    db = init_firebase()
    df_sheet = pd.read_excel(file)
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
    is_admin = pwd == admin_code
    if pwd:
        st.sidebar.success("Admin" if is_admin else "Clave incorrecta")
    if is_admin:
        file = st.sidebar.file_uploader("Cargar Excel (.xlsx/.xls)", type=["xlsx","xls"])
        if file and st.sidebar.button("Subir a Firestore"):
            upload_data(file)
            st.sidebar.success("Datos cargados")
            st.experimental_rerun()

    # Cargar índice de datos
    df_idx = load_index_data()
    if df_idx.empty:
        st.warning("No hay datos. Usa Admin para cargar un archivo.")
        return

    # Filtros dependientes
    st.sidebar.header("Filtros")
    for col_key in [k for k in ['preparer', 'country', 'filler'] if col_key in df_idx.columns]:
        opts = ['Todos'] + sorted(df_idx[col_key].dropna().unique())
        sel = st.sidebar.selectbox(col_key.capitalize(), opts)
        if sel != 'Todos':
            df_idx = df_idx[df_idx[col_key] == sel]

    # Mostrar cards con scroll
    st.subheader("Cuentas GL")
    container = st.container()
    for _, row in df_idx.iterrows():
        rec_id = row['_id']
        # Cargar detalle al expandirse
        with container.expander(row.get(find_column_name(db.collection("reconciliation_records"), ["gl account name", "gl name", "account name"]) , expanded=False)):
            rec = load_record(rec_id)
            # Mostrar campos detallados
            st.write(f"**Assigned Reviewer:** {rec.get('Assigned Reviewer', '')}")
            st.write(f"**Cluster:** {rec.get('Cluster', '')}")
            # Completed y fecha
            comp = rec.get('Completed', '')
            chk = st.checkbox("Completed", value=str(comp).lower() in ['yes','true','1'], key=f"chk_{rec_id}")
            date_val = rec.get('Completion Date', '')
            try:
                def_date = pd.to_datetime(date_val).date()
            except:
                def_date = datetime.date.today()
            new_date = st.date_input("Completion Date", value=def_date, key=f"date_{rec_id}")
            if st.button("Guardar cambios", key=f"save_{rec_id}"):
                updates = {}
                updates['Completed'] = 'Yes' if chk else 'No'
                updates['Completion Date'] = new_date.strftime('%Y-%m-%d')
                init_firebase().collection("reconciliation_records").document(rec_id).update(updates)
                st.success("Actualizado")
            st.markdown("---")
            # Comentarios estilo chat
            st.subheader("Comentarios")
            for c in get_comments(rec_id):
                ts = c.get('timestamp')
                t_str = ts.strftime('%Y-%m-%d %H:%M') if isinstance(ts, datetime.datetime) else ''
                st.markdown(f"**{c.get('user','Anon')}** ({t_str}): {c.get('text')}")
            comment = st.text_area("Nuevo comentario:", key=f"comment_{rec_id}")
            if st.button("Agregar comentario", key=f"add_{rec_id}"):
                if user and comment:
                    add_comment(rec_id, user, comment)
                    st.experimental_rerun()
                else:
                    st.error("Usuario y comentario requeridos.")

if __name__ == '__main__':
    main()
