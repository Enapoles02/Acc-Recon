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
    docs = col.stream()
    recs = []
    for d in docs:
        data = d.to_dict()
        flat_data = {"_id": d.id}
        for k, v in data.items():
            flat_data[str(k).strip()] = str(v).strip() if v is not None else None
        recs.append(flat_data)
    df = pd.DataFrame(recs)
    df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
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
    st.sidebar.title("🔐 Acceso")
    user = st.sidebar.text_input("Usuario")
    pwd = st.sidebar.text_input("Admin Key", type="password")
    is_admin = (pwd == st.secrets.get("admin_code", "ADMIN"))

    df = load_index_data()
    map_df = load_mapping()

    df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
    map_df.columns = map_df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)

    if is_admin:
        with st.expander("🛠 Depuración de columnas"):
            st.write("**Columnas en df (desde Firebase):**")
            st.write(df.columns.tolist())
            st.dataframe(df, use_container_width=True)
            st.write("**Columnas en map_df (desde Mapping.csv):**")
            st.write(map_df.columns.tolist())
            st.dataframe(map_df, use_container_width=True)

    if "GL Account" in df.columns and "GL Account" in map_df.columns:
        df["GL Account"] = df["GL Account"].astype(str).str.strip()
        map_df["GL Account"] = map_df["GL Account"].astype(str).str.strip()
        df = df.merge(map_df, on="GL Account", how="left")
        df["ReviewGroup"] = df["ReviewGroup"].fillna("Others")
    else:
        st.error("❌ No se encontró la columna 'GL Account' en los datos o en el mapping.")
        return

    if not user:
        st.warning("Ingresa tu usuario para filtrar tareas.")
        return

    mapping = {
        "Paula Sarachaga": ["Argentina", "Chile", "Guatemala"],
        "Napoles Enrique": ["Canada"],
        "Julio": ["United States of America"],
        "Guadalupe": ["Mexico", "Peru", "Panama"]
    }

    if 'country' in df.columns and df['country'].notna().any():
        allowed = mapping.get(user, [c for c in df['country'].unique() if c not in sum(mapping.values(), [])])
        df = df[df['country'].isin(allowed)]
        if not is_admin and df.empty:
            st.warning("No hay datos disponibles para tu país o usuario.")
    else:
        allowed = []
        if not is_admin:
            st.warning("No se encontró la columna 'country' o está vacía.")
        df = df.iloc[0:0] if not is_admin else df

    st.sidebar.markdown("---")
    q = st.sidebar.text_input("Buscar cuenta")
    review_filter = st.sidebar.selectbox("Grupo de revisión", options=["All"] + sorted(df["ReviewGroup"].unique().tolist()))

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
            label = f"{r.get('gl_name', '')} - {r.get('GL Account', '')} ({abbr(r.get('country', ''))})"
            if st.button(label, key=key):
                st.session_state['selected'] = key

    with colR:
        sel = st.session_state.get('selected')
        if not sel:
            st.info("Selecciona una cuenta del panel izquierdo.")
        else:
            rec = load_record(sel)
            st.subheader(f"{rec.get('gl_name')} - {rec.get('GL Account', '')} ({abbr(rec.get('country', ''))})")
            for f in ['Assigned Reviewer', 'Cluster']:
                if f in rec:
                    st.write(f"**{f}:** {rec[f]}")
            comp = str(rec.get('Completed', '')).lower() in ['yes', 'true', '1']
            nv = st.checkbox("Completed", value=comp)
            try:
                dv = pd.to_datetime(rec.get('Completion Date')).date()
            except:
                dv = datetime.date.today()
            nd = st.date_input("Completion Date", value=dv)

            deadline_base = datetime.date.today().replace(day=1) + datetime.timedelta(days=30)
            wd_day = st.sidebar.number_input("Working Day para Deadline (WD+X):", min_value=1, max_value=10, value=3)
            deadline = deadline_base + datetime.timedelta(days=wd_day)
            status = "Delay" if not nv and nd > deadline else "On time"
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

    if is_admin:
        st.markdown("---")
        st.subheader("📦 Data combinada completa")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Descargar Data combinada",
            data=csv,
            file_name="data_combinada.csv",
            mime='text/csv'
        )

if __name__ == '__main__':
    main()
