import streamlit as st
import pandas as pd
import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage

# ------------------ Config ------------------
st.set_page_config(page_title="Reconciliación GL", layout="wide")
st.title("Dashboard de Reconciliación GL")

# ------------------ Firebase Init ------------------
@st.cache_resource

def init_firebase():
    firebase_creds = st.secrets["firebase_credentials"]
    if hasattr(firebase_creds, "to_dict"):
        firebase_creds = firebase_creds.to_dict()
    bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred, {
            "storageBucket": bucket_name
        })
    return firestore.client(), bucket_name

# ------------------ Funciones ------------------
@st.cache_data(ttl=300)
def load_index_data():
    db, _ = init_firebase()
    col = db.collection("reconciliation_records")
    sample = next(col.limit(1).stream(), None)
    if not sample:
        return pd.DataFrame()
    gl_col = "GL NAME"
    country_col = "Country"
    try:
        docs = col.select([gl_col, country_col]).stream()
    except Exception:
        docs = col.stream()
    recs = []
    for d in docs:
        data = d.to_dict()
        recs.append({"_id": d.id, "gl_name": data.get(gl_col), "country": data.get(country_col)})
    return pd.DataFrame(recs)

@st.cache_data(ttl=60)
def load_record(rec_id):
    db, _ = init_firebase()
    doc = db.collection("reconciliation_records").document(rec_id).get()
    if not doc.exists:
        return {}
    d = doc.to_dict()
    d["_id"] = rec_id
    return d

@st.cache_data(ttl=60)
def get_comments(rec_id):
    db, _ = init_firebase()
    coll = db.collection("reconciliation_records").document(rec_id).collection("comments")
    coms = []
    for d in coll.order_by("timestamp").stream():
        c = d.to_dict()
        ts = c.get("timestamp")
        if hasattr(ts, "to_datetime"):
            c["timestamp"] = ts.to_datetime()
        coms.append(c)
    return coms

def add_comment(rec_id, user, text):
    db, _ = init_firebase()
    db.collection("reconciliation_records").document(rec_id).collection("comments").add({
        "user": user, "text": text, "timestamp": firestore.SERVER_TIMESTAMP
    })

@st.cache_data(ttl=60)
def get_docs(rec_id):
    _, bucket_name = init_firebase()
    bucket = storage.bucket()
    prefix = f"reconciliation_records/{rec_id}/"
    docs = []
    for b in bucket.list_blobs(prefix=prefix):
        name = b.name.replace(prefix, "")
        url = b.generate_signed_url(expiration=datetime.timedelta(hours=1))
        docs.append({"filename": name, "url": url})
    return docs

def upload_doc(rec_id, file, user):
    _, bucket_name = init_firebase()
    bucket = storage.bucket()
    blob = bucket.blob(f"reconciliation_records/{rec_id}/{file.name}")
    blob.upload_from_file(file, content_type=file.type)
    db, _ = init_firebase()
    db.collection("reconciliation_records").document(rec_id).collection("documents").add({
        "filename": file.name, "uploaded_by": user, "timestamp": firestore.SERVER_TIMESTAMP
    })
    get_docs.clear()

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

# ------------------ App ------------------
def main():
    user = st.sidebar.text_input("Usuario")
    pwd = st.sidebar.text_input("Admin Key", type="password")
    is_admin = (pwd == st.secrets.get("admin_code", "ADMIN"))
    if is_admin:
        file = st.sidebar.file_uploader("Cargar Excel", type=["xlsx", "xls"])
        if file and st.sidebar.button("Subir a Firestore"):
            df = pd.read_excel(file)
            df = df.loc[:, ~df.columns.str.lower().str.contains('powerappsid')]
            df = df.loc[:, ~df.columns.str.startswith('Unnamed')]
            db, _ = init_firebase()
            col_ref = db.collection("reconciliation_records")
            for d in col_ref.stream(): d.reference.delete()
            for i, row in df.iterrows(): col_ref.document(str(i)).set(row.dropna().to_dict())
            load_index_data.clear()
            st.sidebar.success("Datos cargados")

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

    if 'start' not in st.session_state: st.session_state['start'] = 0
    n = len(df)
    colL, colR = st.columns([1, 3])
    with colL:
        st.markdown("### Cuentas GL")
        if st.button("↑") and st.session_state['start'] > 0:
            st.session_state['start'] -= 1
        if st.button("↓") and st.session_state['start'] < n - 5:
            st.session_state['start'] += 1
        sub = df.iloc[st.session_state['start']:st.session_state['start'] + 5]
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
            st.subheader(f"{rec.get('gl_name')} - {abbr(rec.get('country', ''))}")
            for f in ['Assigned Reviewer', 'Cluster']:
                if f in rec: st.write(f"**{f}:** {rec[f]}")
            comp = str(rec.get('Completed', '')).lower() in ['yes', 'true', '1']
            nv = st.checkbox("Completed", value=comp)
            try:
                dv = pd.to_datetime(rec.get('Completion Date')).date()
            except:
                dv = datetime.date.today()
            nd = st.date_input("Completion Date", value=dv)
            if st.button("Guardar cambios"):
                updates = {'Completed': 'Yes' if nv else 'No', 'Completion Date': nd.strftime('%Y-%m-%d')}
                init_firebase()[0].collection("reconciliation_records").document(sel).update(updates)
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
                txt = ts.strftime('%Y-%m-%d %H:%M') if hasattr(ts, 'strftime') else ''
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
