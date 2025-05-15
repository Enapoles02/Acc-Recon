import streamlit as st
import pandas as pd
import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# ------------------ Firebase Setup ------------------
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        creds = st.secrets["firebase_credentials"]
        cred = credentials.Certificate(creds.to_dict() if hasattr(creds, "to_dict") else creds)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ------------------ Data Loading ------------------
@st.cache_data(ttl=300)
def load_index_data():
    # Carga solo GL y Country para índice
    db = init_firebase()
    col_ref = db.collection("reconciliation_records")
    sample = next(col_ref.limit(1).stream(), None)
    if not sample:
        return pd.DataFrame()
    cols = sample.to_dict().keys()
    # Detectar columnas
    def find(keys):
        for k in keys:
            for c in cols:
                if k.lower() in c.lower(): return c
        return None
    gl_col = find(["gl account name","gl name","account name"])
    country_col = find(["country"])
    if not gl_col or not country_col:
        return pd.DataFrame()
    # Stream con selección
    try:
        docs = col_ref.select([gl_col, country_col]).stream()
    except Exception:
        docs = col_ref.stream()
    records = []
    for d in docs:
        data = d.to_dict()
        records.append({"_id": d.id, gl_col: data.get(gl_col), country_col: data.get(country_col)})
    df = pd.DataFrame(records)
    df.columns = ["_id", "gl_name", "country"]
    return df

@st.cache_data(ttl=60)
def load_record(rec_id):
    db = init_firebase()
    doc = db.collection("reconciliation_records").document(rec_id).get()
    if not doc.exists:
        return {}
    data = doc.to_dict()
    data['_id'] = rec_id
    return data

# ------------------ Comments ------------------
@st.cache_data(ttl=60)
def get_comments(rec_id):
    db = init_firebase()
    coll = db.collection("reconciliation_records").document(rec_id).collection("comments")
    comments = []
    for d in coll.order_by("timestamp").stream():
        c = d.to_dict()
        ts = c.get('timestamp')
        if hasattr(ts, 'to_datetime'):
            c['timestamp'] = ts.to_datetime()
        comments.append(c)
    return comments

def add_comment(rec_id, user, text):
    db = init_firebase()
    coll = db.collection("reconciliation_records").document(rec_id).collection("comments")
    coll.add({ 'user': user, 'text': text, 'timestamp': firestore.SERVER_TIMESTAMP })

# ------------------ Admin Upload ------------------
def upload_data(file):
    df_sheet = pd.read_excel(file)
    df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.lower().str.contains('powerappsid')]
    df_sheet = df_sheet.loc[:, ~df_sheet.columns.str.startswith('Unnamed')]
    db = init_firebase()
    col_ref = db.collection("reconciliation_records")
    for d in col_ref.stream(): d.reference.delete()
    for idx, row in df_sheet.iterrows():
        col_ref.document(str(idx)).set(row.dropna().to_dict())

# ------------------ Main App ------------------
def main():
    st.set_page_config(layout="wide")
    st.title("Dashboard de Reconciliación GL")

    # Sidebar inputs
    user = st.sidebar.text_input("Usuario (para filtrar por Country)")
    admin_pwd = st.sidebar.text_input("Clave Admin", type="password")
    is_admin = (admin_pwd == st.secrets.get("admin_code","ADMIN"))
    if admin_pwd:
        st.sidebar.warning("Modo Admin activado" if is_admin else "Clave incorrecta")
    if is_admin:
        file = st.sidebar.file_uploader("Cargar Excel (.xlsx/.xls)", type=["xlsx","xls"])
        if file and st.sidebar.button("Subir a Firestore"):
            upload_data(file)
            st.sidebar.success("Datos cargados correctamente.")
            # Limpiar caché de datos e inicializar paginación
            try:
                load_index_data.clear()
            except Exception:
                pass
            st.session_state['start'] = 0

    # Require user
    if not user:
        st.warning("Ingresa tu nombre de usuario en la sidebar.")
        return

    # Load index and filter by mapping
    df_idx = load_index_data()
    if df_idx.empty:
        st.error("Error cargando datos o faltan columnas GL/Country.")
        return
    country_map = {
        "Paula Sarachaga": ["Argentina","Chile","Guatemala"],
        "Napoles Enrique": ["Canada"],
        "Julio": ["United States of America"],
        "Guadalupe": ["Mexico","Peru","Panama"]
    }
    allowed = country_map.get(user, [c for c in df_idx['country'].unique() if c not in sum(country_map.values(), [])])
    df_idx = df_idx[df_idx['country'].isin(allowed)]
    n = len(df_idx)

    # Initialize paging
    if 'start' not in st.session_state:
        st.session_state['start'] = 0
    # Paging controls
    col1, col2, col3 = st.columns([1,2,1])
    with col1:
        if st.button("⟵", key="prev") and st.session_state.start > 0:
            st.session_state.start -= 1
    with col2:
        st.write(f"Mostrando {st.session_state.start+1}-{min(st.session_state.start+5, n)} de {n}")
    with col3:
        if st.button("⟶", key="next") and st.session_state.start < n-5:
            st.session_state.start += 1

    # Display window of 5
    subset = df_idx.iloc[st.session_state.start:st.session_state.start+5]
    for _, row in subset.iterrows():
        rec_id = row['_id']
        gl_name = row['gl_name']
        with st.expander(gl_name):
            rec = load_record(rec_id)
            # Display fields
            for field in [f for f in ['Assigned Reviewer','Cluster'] if f in rec]:
                st.write(f"**{field}:** {rec.get(field)}")
            # Completed and date
            comp = str(rec.get('Completed','')).lower() in ['yes','true','1']
            new_c = st.checkbox("Completed", value=comp, key=f"c_{rec_id}")
            try:
                def_date = pd.to_datetime(rec.get('Completion Date')).date()
            except:
                def_date = datetime.date.today()
            new_date = st.date_input("Completion Date", value=def_date, key=f"d_{rec_id}")
            if st.button("Guardar", key=f"s_{rec_id}"):
                updates = {'Completed': 'Yes' if new_c else 'No', 'Completion Date': new_date.strftime('%Y-%m-%d')}
                init_firebase().collection("reconciliation_records").document(rec_id).update(updates)
                st.success("Actualizado")
            st.markdown("---")
            st.subheader("Comentarios")
            for c in get_comments(rec_id):
                ts = c.get('timestamp'); txt = ts.strftime('%Y-%m-%d %H:%M') if hasattr(ts,'strftime') else ''
                st.markdown(f"**{c.get('user')}** ({txt}): {c.get('text')}")
            new_txt = st.text_area("Nuevo comentario:", key=f"ct_{rec_id}")
            if st.button("Agregar comentario", key=f"a_{rec_id}"):
                if user and new_txt:
                    add_comment(rec_id, user, new_txt)
                    st.experimental_rerun()
                else:
                    st.error("Ingresa usuario y comentario.")

if __name__ == '__main__':
    main()
