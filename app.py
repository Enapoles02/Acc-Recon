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
    """
    Carga solo las columnas necesarias (GL y Country) para el índice y mejora rendimiento.
    """
    db = init_firebase()
    col_ref = db.collection("reconciliation_records")
    # Detectar nombres de columna
    sample = next(col_ref.limit(1).stream(), None)
    if not sample:
        return pd.DataFrame()
    cols = list(sample.to_dict().keys())
    # Encontrar columna GL y Country
    def find_col(keys):
        for k in keys:
            for c in cols:
                if k.lower() in c.lower(): return c
        return None
    gl_col = find_col(["gl account name","gl name","account name"])
    country_col = find_col(["country"])
    if not gl_col or not country_col:
        return pd.DataFrame()
    # Stream docs con selección
    try:
        docs = col_ref.select([gl_col, country_col]).stream()
    except Exception:
        docs = col_ref.stream()
    records = []
    for d in docs:
        data = d.to_dict()
        records.append({
            "_id": d.id,
            gl_col: data.get(gl_col),
            country_col: data.get(country_col)
        })
    df = pd.DataFrame(records)
    return df

@st.cache_data(ttl=60)
def load_record(rec_id):
    """
    Carga todos los campos de un solo registro (al expandirse).
    """
    db = init_firebase()
    doc = db.collection("reconciliation_records").document(rec_id).get()
    if not doc.exists:
        return {}
    rec = doc.to_dict()
    rec['_id'] = rec_id
    return rec

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

# ------------------ Upload Admin ------------------
def upload_data(file):
    df_sheet = pd.read_excel(file)
    # Eliminar PowerAppsId y Unnamed
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

    # Sidebar: Usuario y Admin
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
            st.experimental_rerun()

    # Validar usuario
    if not user:
        st.warning("Por favor ingresa tu nombre de usuario en la sidebar para filtrar.")
        return

    # Mapping usuario -> lista de países
    mapping = {
        "Paula Sarachaga": ["Argentina","Chile","Guatemala"],
        "Napoles Enrique": ["Canada"],
        "Julio": ["United states of america"],
        "Guadalupe": ["Mexico","Peru","Panama"]
    }

    # Cargar índice y filtrar por Country
    df_idx = load_index_data()
    if df_idx.empty:
        st.error("No se pudo cargar datos de índice o faltan columnas.")
        return

    # Encontrar nombre exacto de columna Country
    country_col = [c for c in df_idx.columns if c.lower().startswith("country")][0]
    # Determinar países permitidos
    if user in mapping:
        allowed = mapping[user]
    else:
        # Otros países: todos los que no están en mapping
        all_c = df_idx[country_col].dropna().unique().tolist()
        used = sum(mapping.values(), [])
        allowed = [c for c in all_c if c not in used]
    # Filtrar índice
    df_idx = df_idx[df_idx[country_col].isin(allowed)]

    # Mostrar cards expandibles
    st.subheader("Tus Cuentas GL")
    for _, row in df_idx.iterrows():
        rec_id = row['_id']
        gl_name = row[[c for c in df_idx.columns if c.lower().startswith("gl")][0]]
        with st.expander(f"{gl_name}"):
            rec = load_record(rec_id)
            # Mostrar detalles básicos
            for field in [k for k in rec.keys() if k.lower().startswith(('assigned reviewer','cluster','balance'))]:
                st.write(f"**{field}:** {rec.get(field)}")
            # Completed
            comp = rec.get('Completed','')
            checked = str(comp).lower() in ['yes','true','1']
            new_c = st.checkbox("Completed", value=checked, key=f"c_{rec_id}")
            # Fecha
            dt_key = f"date_{rec_id}"
            try:
                default = pd.to_datetime(rec.get('Completion Date')).date()
            except:
                default = datetime.date.today()
            new_date = st.date_input("Completion Date", value=default, key=dt_key)
            if st.button("Guardar", key=f"save_{rec_id}"):
                updates = {
                    'Completed': 'Yes' if new_c else 'No',
                    'Completion Date': new_date.strftime('%Y-%m-%d')
                }
                init_firebase().collection("reconciliation_records").document(rec_id).update(updates)
                st.success("Actualizado.")
            st.markdown("---")
            # Chat de comentarios
            st.subheader("Comentarios")
            for c in get_comments(rec_id):
                ts = c.get('timestamp')
                txt_ts = ts.strftime('%Y-%m-%d %H:%M') if hasattr(ts,'strftime') else ''
                st.markdown(f"**{c.get('user','Anon')}** ({txt_ts}): {c.get('text')}")
            new_txt = st.text_area("Nuevo comentario", key=f"ct_{rec_id}")
            if st.button("Agregar comentario", key=f"add_{rec_id}"):
                if user and new_txt:
                    add_comment(rec_id, user, new_txt)
                    st.experimental_rerun()
                else:
                    st.error("Debes ingresar usuario y texto.")

if __name__ == '__main__':
    main()
