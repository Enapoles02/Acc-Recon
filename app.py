import streamlit as st
import pandas as pd
import datetime
import firebase_admin
from firebase_admin import credentials, firestore, storage
from io import BytesIO

# ------------------ Configuración general ------------------
st.set_page_config(page_title="Reconciliación GL", layout="wide")
st.title("Dashboard de Reconciliación GL")

# ------------------ Inicializar Firebase ------------------
@st.cache_resource
def init_firebase():
    firebase_creds = st.secrets["firebase_credentials"]
    if hasattr(firebase_creds, "to_dict"):
        firebase_creds = firebase_creds.to_dict()
    bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})
    return firestore.client(), bucket_name

# ------------------ Cargar Mapping desde GitHub ------------------
@st.cache_data
def load_mapping():
    url = "https://raw.githubusercontent.com/Enapoles02/Acc-Recon/main/Mapping.csv"
    df = pd.read_csv(url, dtype=str)
    df.columns = df.columns.str.strip()
    df = df.rename(columns={"GL Account": "GL Account", "Group": "ReviewGroup"})
    return df

# ------------------ Funciones de carga ------------------
@st.cache_data(ttl=300)
def load_index_data():
    db, _ = init_firebase()
    col = db.collection("reconciliation_records")
    sample = next(col.limit(1).stream(), None)
    if not sample:
        return pd.DataFrame()
    gl_col = "GL NAME"
    acc_col = "GL ACCOUNT"
    country_col = "Country"
    try:
        docs = col.select([gl_col, acc_col, country_col]).stream()
    except Exception:
        docs = col.stream()
    recs = []
    for d in docs:
        data = d.to_dict()
        recs.append({
            "_id": d.id,
            "gl_name": data.get(gl_col),
            "GL Account": str(data.get(acc_col)).strip(),
            "country": data.get(country_col)
        })
    df = pd.DataFrame(recs)
    df.columns = df.columns.str.strip()
    return df

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
        "filename": file.name,
        "uploaded_by": user,
        "timestamp": firestore.SERVER_TIMESTAMP
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

# ------------------ App principal ------------------
def main():
    user = st.sidebar.text_input("Usuario")
    pwd = st.sidebar.text_input("Admin Key", type="password")
    is_admin = (pwd == st.secrets.get("admin_code", "ADMIN"))

    wd_day = st.sidebar.number_input("Working Day para Deadline (WD+X):", min_value=1, max_value=10, value=3)
    deadline_base = datetime.date.today().replace(day=1) + datetime.timedelta(days=30)
    deadline = deadline_base + datetime.timedelta(days=wd_day)

    df = load_index_data()
    map_df = load_mapping()

    # 🔍 DEPURACIÓN: Revisión de nombres de columnas
    st.subheader("🛠 Depuración de columnas")
    st.write("Columnas en `df` (desde Firebase):")
    st.code(df.columns.tolist())

    st.write("Columnas en `map_df` (desde Mapping.csv):")
    st.code(map_df.columns.tolist())

    # Forzar limpieza profunda de nombres de columnas
    df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
    map_df.columns = map_df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)

    if "GL Account" not in df.columns:
        st.error("❌ 'GL Account' NO encontrada en `df`. Verifica nombres exactos.")
    if "GL Account" not in map_df.columns:
        st.error("❌ 'GL Account' NO encontrada en `map_df`. Verifica nombres exactos.")

    df["GL Account"] = df["GL Account"].astype(str).str.strip()
    map_df["GL Account"] = map_df["GL Account"].astype(str).str.strip()
    df = df.merge(map_df, on="GL Account", how="left")
    df["ReviewGroup"] = df["ReviewGroup"].fillna("Others")

    mapping = {
        "Paula Sarachaga": ["Argentina", "Chile", "Guatemala"],
        "Napoles Enrique": ["Canada"],
        "Julio": ["United States of America"],
        "Guadalupe": ["Mexico", "Peru", "Panama"]
    }

    if not user:
        st.warning("Ingresa tu usuario para filtrar tareas.")
        return

    if df.empty:
        st.error("Sin datos o columnas faltantes.")
        return

    allowed = mapping.get(user, [c for c in df['country'].unique() if c not in sum(mapping.values(), [])])
    df = df[df['country'].isin(allowed)]

    q = st.sidebar.text_input("Buscar cuenta")
    review_filter = st.sidebar.selectbox("Grupo de revisión", options=["All"] + sorted(df["ReviewGroup"].dropna().unique().tolist()))

    if q:
        df = df[df['gl_name'].str.contains(q, case=False, na=False)]
    if review_filter != "All":
        df = df[df["ReviewGroup"] == review_filter]

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
        sub = df.iloc[st.session_state['start']:st.session_state['start'] + 5]
        for _, r in sub.iterrows():
            key = r['_id']
            label = f"{r['gl_name']} - {r['GL Account']} ({abbr(r['country'])})"
            if st.button(label, key=key):
                st.session_state['selected'] = key

    with colR:
        sel = st.session_state.get('selected')
        if not sel:
            st.info("Selecciona una cuenta del panel izquierdo.")
        else:
            rec = load_record(sel)
            st.subheader(f"{rec.get('gl_name')} - {rec.get('GL ACCOUNT', '')} ({abbr(rec.get('country', ''))})")
            for f in ['Assigned Reviewer', 'Cluster']:
                if f in rec: st.write(f"**{f}:** {rec[f]}")
            comp = str(rec.get('Completed', '')).lower() in ['yes', 'true', '1']
            nv = st.checkbox("Completed", value=comp)
            try:
                dv = pd.to_datetime(rec.get('Completion Date')).date()
            except:
                dv = datetime.date.today()
            nd = st.date_input("Completion Date", value=dv)

            status = "Delay" if not comp and nd > deadline else "On time"
            st.write(f"⏱ Estado: `{status}` (Deadline: {deadline})")

            if st.button("Guardar cambios"):
                updates = {
                    'Completed': 'Yes' if nv else 'No',
                    'Completion Date': nd.strftime('%Y-%m-%d'),
                    'Status': status
                }
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
