import streamlit as st
import pandas as pd
import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage

st.write(st.secrets)


# ------------------ Firebase Setup ------------------
import json

@st.cache_resource
def init_firebase():
    """
    Inicializa Firebase Admin con Firestore y Cloud Storage.
    Usa firebase_bucket de secrets o infiere del project_id.
    """
    if not firebase_admin._apps:
        # Leer credenciales JSON desde secrets
        raw = st.secrets.get("firebase_credentials")
        if isinstance(raw, str):
            try:
                cred_dict = json.loads(raw)
            except Exception as e:
                st.error(f"Error parsing firebase_credentials JSON: {e}")
                st.stop()
        else:
            cred_dict = raw.to_dict() if hasattr(raw, "to_dict") else raw
        # Inferir bucket: usa secreto o project_id.appspot.com
        project_id = cred_dict.get("project_id")
        bucket_name = st.secrets.get("firebase_bucket") or f"{project_id}.appspot.com"
        # Inicializar app con Storage bucket
        try:
            firebase_admin.initialize_app(
                credentials.Certificate(cred_dict),
                {"storageBucket": bucket_name}
            )
        except Exception as e:
            st.error(f"Error inicializando Firebase Admin SDK: {e}")
            st.stop()
    return firestore.client()

# ------------------ Data Loading ------------------
@st.cache_data(ttl=300)
def load_index_data():
    """
    Carga índice con GL NAME y Country desde Firestore.
    """
    db = init_firebase()
    col = db.collection("reconciliation_records")
    sample = next(col.limit(1).stream(), None)
    if not sample:
        return pd.DataFrame()
    data_keys = sample.to_dict().keys()
    # Columnas fijas según tu Excel
    gl_col = "GL NAME"
    country_col = "Country"
    if gl_col not in data_keys or country_col not in data_keys:
        st.error(f"Columnas faltantes. Esperaba: {gl_col}, {country_col}. Encontradas: {list(data_keys)}")
        return pd.DataFrame()
    try:
        docs = col.select([gl_col, country_col]).stream()
    except Exception:
        docs = col.stream()
    records = []
    for d in docs:
        record = d.to_dict()
        records.append({
            "_id": d.id,
            "gl_name": record.get(gl_col),
            "country": record.get(country_col)
        })
    return pd.DataFrame(records)

@st.cache_data(ttl=60)
def load_record(rec_id):
    """
    Carga detalle completo de un registro.
    """
    db = init_firebase()
    doc = db.collection("reconciliation_records").document(rec_id).get()
    if not doc.exists:
        return {}
    rec = doc.to_dict()
    rec["_id"] = rec_id
    return rec

# ------------------ Comments ------------------
@st.cache_data(ttl=60)
def get_comments(rec_id):
    db = init_firebase()
    coll = db.collection("reconciliation_records").document(rec_id).collection("comments")
    comments = []
    for d in coll.order_by("timestamp").stream():
        c = d.to_dict()
        ts = c.get("timestamp")
        if hasattr(ts, "to_datetime"):
            c["timestamp"] = ts.to_datetime()
        comments.append(c)
    return comments

def add_comment(rec_id, user, text):
    db = init_firebase()
    db.collection("reconciliation_records").document(rec_id).collection("comments").add({
        "user": user,
        "text": text,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

# ------------------ Documents ------------------
@st.cache_data(ttl=60)
def get_docs(rec_id):
    """
    Lista y firma URLs de documentos en Cloud Storage.
    """
    # Usa el bucket configurado al iniciar Firebase
    bucket = storage.bucket()
    prefix = f"reconciliation_records/{rec_id}/"
    blobs = bucket.list_blobs(prefix=prefix)
    docs = []
    for b in blobs:
        name = b.name.replace(prefix, "")
        url = b.generate_signed_url(expiration=datetime.timedelta(hours=1))
        docs.append({"filename": name, "url": url})
    return docs

def upload_doc(rec_id, file, user):
    # Usa el bucket configurado al iniciar Firebase
    bucket = storage.bucket()
    blob = bucket.blob(f"reconciliation_records/{rec_id}/{file.name}")
    blob.upload_from_file(file, content_type=file.type)
    db = init_firebase()
    db.collection("reconciliation_records").document(rec_id).collection("documents").add({
        "filename": file.name,
        "uploaded_by": user,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    # Limpiar caché de documentos
    get_docs.clear()

# ------------------ Admin Upload ------------------
def upload_data(file):
    df = pd.read_excel(file)
    df = df.loc[:, ~df.columns.str.lower().str.contains('powerappsid')]
    df = df.loc[:, ~df.columns.str.startswith('Unnamed')]
    db = init_firebase()
    col_ref = db.collection("reconciliation_records")
    for d in col_ref.stream():
        d.reference.delete()
    for i, row in df.iterrows():
        col_ref.document(str(i)).set(row.dropna().to_dict())
    load_index_data.clear()

# ------------------ Abbreviations ------------------
def abbr(country):
    m = {
        "United States of America": "USA",
        "Canada": "CA",
        "Argentina": "ARG",
        "Chile": "CL",
        "Guatemala": "GT",
        "Mexico": "MX",
        "Peru": "PE",
        "Panama": "PA"
    }
    return m.get(country, country[:3].upper())

# ------------------ Main App ------------------
def main():
    st.set_page_config(layout="wide")
    # CSS uniforme para botones
    st.markdown("""
    <style>
    .stButton>button {
        min-height: 40px;
        max-height: 80px;
        width: auto;
        max-width: 300px;
        white-space: normal;
        overflow: hidden;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)
    st.title("Dashboard de Reconciliación GL")

    user = st.sidebar.text_input("Usuario")
    pwd = st.sidebar.text_input("Admin Key", type="password")
    is_admin = (pwd == st.secrets.get("admin_code", "ADMIN"))
    if is_admin:
        file = st.sidebar.file_uploader("Cargar Excel", type=["xlsx", "xls"])
        if file and st.sidebar.button("Subir a Firestore"):
            upload_data(file)
            st.sidebar.success("Datos cargados correctamente.")

    st.sidebar.markdown("---")
    mapping = {
        "Paula Sarachaga": ["Argentina", "Chile", "Guatemala"],
        "Napoles Enrique": ["Canada"],
        "Julio": ["United States of America"],
        "Guadalupe": ["Mexico", "Peru", "Panama"]
    }
    if not user:
        st.warning("Ingresa tu usuario para filtrar tareas.")
        return

    df = load_index_data()
    if df.empty:
        st.error("Sin datos o columnas faltantes.")
        return
    allowed = mapping.get(user, [c for c in df['country'].unique() if c not in sum(mapping.values(), [])])
    df = df[df['country'].isin(allowed)]
    q = st.sidebar.text_input("Buscar cuenta")
    if q:
        df = df[df['gl_name'].str.contains(q, case=False, na=False)]

    if 'start' not in st.session_state:
        st.session_state['start'] = 0
    n = len(df)

    colL, colR = st.columns([1, 3])
    with colL:
        st.markdown("### Cuentas GL")
        if st.button("↑") and st.session_state['start'] > 0:
            st.session_state['start'] -= 1
        if st.button("↓") and st.session_state['start'] < n - 5:
            st.session_state['start'] += 1
        sub = df.iloc[st.session_state['start']:st.session_state['start']+5]
        for _, r in sub.iterrows():
            key = r['_id']
            label = f"{r['gl_name']} ({abbr(r['country'])})"
            if st.button(label, key=key):
                st.session_state['selected'] = key

    with colR:
        sel = st.session_state.get('selected')
        if not sel:
            st.info("Selecciona una cuenta del panel izquierdo.")
        else:
            rec = load_record(sel)
            st.subheader(f"{rec.get('gl_name')} - {abbr(rec.get('country',''))}")
            for f in ['Assigned Reviewer', 'Cluster']:
                if f in rec:
                    st.write(f"**{f}:** {rec[f]}")
            comp = str(rec.get('Completed','')).lower() in ['yes','true','1']
            nv = st.checkbox("Completed", value=comp)  
            try:
                dv = pd.to_datetime(rec.get('Completion Date')).date()
            except:
                dv = datetime.date.today()
            nd = st.date_input("Completion Date", value=dv)
            if st.button("Guardar cambios"):
                updates = {
                    'Completed': 'Yes' if nv else 'No',
                    'Completion Date': nd.strftime('%Y-%m-%d')
                }
                init_firebase().collection("reconciliation_records").document(sel).update(updates)
                st.success("Registro actualizado")
            st.markdown("---")
            st.subheader("Documentos")
            docs = get_docs(sel)
            st.write(f"Cargados: {len(docs)}")
            for d in docs:
                st.markdown(f"- [{d['filename']}]({d['url']})")
            up = st.file_uploader("Subir documento", key=f"doc_{sel}")
            if up and st.button("Agregar documento", key=f"adddoc_{sel}"):
                upload_doc(sel, up, user)
                st.success("Documento subido")
            st.markdown("---")
            st.subheader("Comentarios")
            for c in get_comments(sel):
                ts = c.get('timestamp')
                txt = ts.strftime('%Y-%m-%d %H:%M') if hasattr(ts,'strftime') else ''
                st.markdown(f"**{c.get('user')}** ({txt}): {c.get('text')}")
            nc = st.text_area("Nuevo comentario", key=f"com_{sel}")
            if st.button("Agregar comentario", key=f"addcom_{sel}"):
                if user and nc:
                    add_comment(sel, user, nc)
                    st.success("Comentario agregado")
                else:
                    st.error("Usuario y texto requeridos.")

if __name__ == '__main__':
    main()
