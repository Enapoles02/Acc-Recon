import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import FieldFilter
import uuid
from datetime import datetime
import pytz
import random

# -------------------------------------------------
# CONFIGURACIÓN BÁSICA
# -------------------------------------------------
st.set_page_config(page_title="Rifa de Fin de Año", layout="wide")

st.markdown(
    """
    <style>
    .big-title {
        font-size: 40px;
        font-weight: 800;
        text-align: center;
        margin-bottom: 0px;
    }
    .subtitle {
        font-size: 18px;
        text-align: center;
        color: #555;
        margin-bottom: 30px;
    }
    .participant-card {
        background-color: #f5f5f5;
        border-radius: 18px;
        padding: 10px 14px;
        margin: 6px 0;
        text-align: center;
        font-weight: 600;
        font-size: 16px;
    }
    .winner-banner {
        background: linear-gradient(135deg, #ffaf00, #ffdd55);
        border-radius: 20px;
        padding: 20px;
        text-align: center;
        color: #000;
        font-weight: 800;
        font-size: 26px;
        margin-bottom: 15px;
    }
    .winner-sub {
        font-size: 16px;
        text-align: center;
        color: #333;
        margin-bottom: 20px;
    }
    .pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        background-color: #eee;
        font-size: 12px;
        margin: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------------------------------------
# CONEXIÓN A FIREBASE (MISMA BASE QUE USABAS)
# -------------------------------------------------
@st.cache_resource
def init_firebase():
    firebase_creds = st.secrets["firebase_credentials"]
    # En Streamlit Cloud suele venir como AttrDict
    if hasattr(firebase_creds, "to_dict"):
        firebase_creds = firebase_creds.to_dict()
    bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]
    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})
    return firestore.client(), storage.bucket()

db, bucket = init_firebase()

# Zona horaria MX
TZ = pytz.timezone("America/Mexico_City")

# -------------------------------------------------
# UTILIDADES FIREBASE PARA LA RIFA
# -------------------------------------------------
PARTICIPANTS_COL = "raffle_participants"
RESULTS_COL = "raffle_results"

def register_participant(name: str, email: str = "", area: str = "", team: str = ""):
    """Registra un participante en la colección raffle_participants."""
    if not name.strip():
        return False, "El nombre es obligatorio."

    name = name.strip().upper()

    # Evitar duplicados exactos por nombre+email (modo simple)
    docs = db.collection(PARTICIPANTS_COL).where("name", "==", name).stream()
    for d in docs:
        data = d.to_dict()
        if email and data.get("email", "").strip().lower() == email.strip().lower():
            return False, "Ya estás registrado con ese correo."

    doc_id = str(uuid.uuid4())
    now = datetime.now(TZ)

    payload = {
        "name": name,
        "email": email.strip(),
        "area": area.strip(),
        "team": team.strip(),
        "created_at": now.isoformat(),
        "created_at_ts": now,
        "has_won": False,
        "prize": None,
        "active": True,
    }
    db.collection(PARTICIPANTS_COL).document(doc_id).set(payload)
    return True, doc_id

def fetch_participants(include_winners: bool = True):
    """Trae todos los participantes; si include_winners=False, filtra en Python."""
    docs = db.collection(PARTICIPANTS_COL).stream()
    rows = []
    for d in docs:
        data = d.to_dict()
        data["_id"] = d.id
        rows.append(data)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        # Orden por fecha
        if "created_at_ts" in df.columns:
            df = df.sort_values("created_at_ts")
        elif "created_at" in df.columns:
            df = df.sort_values("created_at")
        if not include_winners and "has_won" in df.columns:
            df = df[~df["has_won"].fillna(False)]
    return df

def fetch_recent_participants(limit: int = 12):
    """Últimos participantes (para la vista tipo Kahoot)."""
    docs = (
        db.collection(PARTICIPANTS_COL)
        .order_by("created_at_ts", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    rows = []
    for d in docs:
        data = d.to_dict()
        data["_id"] = d.id
        rows.append(data)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    return df

def fetch_winners(limit: int = 50):
    """Historial de ganadores."""
    docs = (
        db.collection(RESULTS_COL)
        .order_by("drawn_at_ts", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    rows = []
    for d in docs:
        data = d.to_dict()
        data["_id"] = d.id
        rows.append(data)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    return df

def draw_winner(prize: str, admin_name: str = "ADMIN"):
    """Selecciona ganador aleatorio entre quienes no han ganado aún."""
    if not prize.strip():
        return None, "Define un premio para esta ronda."

    df = fetch_participants(include_winners=False)
    if df.empty:
        return None, "No hay participantes disponibles (o ya todos ganaron)."

    winner_row = df.sample(1).iloc[0]
    winner_id = winner_row["_id"]
    winner_name = winner_row["name"]

    now = datetime.now(TZ)

    # Actualizar al participante (marcar como ganador)
    db.collection(PARTICIPANTS_COL).document(winner_id).update(
        {
            "has_won": True,
            "prize": prize.strip(),
        }
    )

    # Registrar resultado en la colección de resultados
    result_payload = {
        "participant_id": winner_id,
        "name": winner_name,
        "prize": prize.strip(),
        "drawn_at": now.isoformat(),
        "drawn_at_ts": now,
        "drawn_by": admin_name,
    }
    result_id = str(uuid.uuid4())
    db.collection(RESULTS_COL).document(result_id).set(result_payload)

    return winner_row, None

def get_last_winner():
    """Último ganador registrado."""
    df = fetch_winners(limit=1)
    if df.empty:
        return None
    return df.iloc[0]

# -------------------------------------------------
# CONTROL DE ADMIN (PUENTE CON SECRETS)
# -------------------------------------------------
def check_is_admin():
    """Usa un password guardado en secrets para permitir girar la ruleta."""
    admin_pw_secret = None
    try:
        admin_pw_secret = st.secrets["raffle_admin"]["password"]
    except Exception:
        # Si no está configurado, nadie es admin (pero no rompas la app)
        return False

    entered_pw = st.session_state.get("admin_password_value", "")
    return bool(admin_pw_secret) and entered_pw == admin_pw_secret

# -------------------------------------------------
# SIDEBAR: DATOS DE USUARIO / ADMIN
# -------------------------------------------------
st.sidebar.title("🎄 Rifa de Fin de Año")
host_name = st.sidebar.text_input("Tu nombre (host / admin / invitado)", value="")
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔐 Admin (solo para girar ruleta)")
admin_pw_input = st.sidebar.text_input(
    "Código admin", type="password", key="admin_password_value"
)
is_admin = check_is_admin()
if is_admin:
    st.sidebar.success("Modo ADMIN activado.")
else:
    st.sidebar.info("Si eres admin, ingresa el código para poder girar la ruleta.")

st.sidebar.markdown("---")
st.sidebar.caption("La información se guarda en Firebase en tiempo real.")

# -------------------------------------------------
# NAVEGACIÓN SUPERIOR (TABS)
# -------------------------------------------------
st.markdown("<div class='big-title'>Rifa de Fin de Año</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='subtitle'>Regístrate, mira la rifa en vivo y celebra a los ganadores 🎁</div>",
    unsafe_allow_html=True,
)

tab_registro, tab_rifa, tab_wall = st.tabs(
    ["🙋 Regístrate", "🎰 Rifa en tiempo real", "📺 Muro en vivo (tipo Kahoot)"]
)

# -------------------------------------------------
# TAB 1: REGISTRO DE PARTICIPANTES
# -------------------------------------------------
with tab_registro:
    st.subheader("🙋 Regístrate para la rifa")

    st.markdown(
        "Completa tus datos para participar en la rifa de fin de año. "
        "Solo necesitas registrarte **una vez**."
    )

    with st.form("registration_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            name = st.text_input("Nombre completo*", placeholder="Ej. ENRIQUE NÁPOLES")
            email = st.text_input("Correo (opcional)", placeholder="empresa@correo.com")
        with col_b:
            area = st.text_input("Área / Departamento", placeholder="Ej. R2R, PTP, OTC...")
            team = st.text_input("Equipo / Sede", placeholder="Ej. NAMER, LATAM, CDMX...")

        submitted = st.form_submit_button("✅ Registrarme")
        if submitted:
            ok, msg = register_participant(name, email, area, team)
            if ok:
                st.success("Registro completado. ¡Ya estás participando en la rifa! 🎉")
                st.balloons()
            else:
                st.error(msg)

    st.markdown("---")

    # Resumen rápido
    df_all = fetch_participants(include_winners=True)
    total_participants = len(df_all)
    unique_names = df_all["name"].nunique() if not df_all.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Participantes registrados", total_participants)
    col2.metric("Personas únicas", unique_names)
    col3.metric(
        "Ganadores hasta ahora",
        fetch_winners(limit=500).shape[0]
    )

    if not df_all.empty:
        with st.expander("Ver listado de participantes"):
            st.dataframe(
                df_all[["name", "email", "area", "team", "has_won", "prize"]],
                use_container_width=True,
            )

# -------------------------------------------------
# TAB 2: RIFA EN TIEMPO REAL (ADMIN GIRA, TODOS VEN)
# -------------------------------------------------
with tab_rifa:
    st.subheader("🎰 Rifa en tiempo real")

    last_winner = get_last_winner()
    if last_winner is not None:
        st.markdown(
            f"<div class='winner-banner'>🎉 ¡Último ganador: {last_winner['name']}! 🎉</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='winner-sub'>Premio: <b>{last_winner['prize']}</b> | "
            f"Sorteado por: <b>{last_winner.get('drawn_by', 'ADMIN')}</b></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Aún no hay ganadores. ¡Sé el primero en girar la ruleta (modo admin)!")

    # Vista general de participantes y ganadores
    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.markdown("#### Participantes disponibles para ganar")

        df_no_winners = fetch_participants(include_winners=False)
        if df_no_winners.empty:
            st.warning("No hay participantes disponibles (o todos ya ganaron).")
        else:
            st.write(f"Participantes disponibles: **{len(df_no_winners)}**")
            names_preview = df_no_winners["name"].tolist()
            # Mostrar algunos nombres en "píldoras"
            pills_html = " ".join(
                [f"<span class='pill'>{n}</span>" for n in names_preview[:60]]
            )
            st.markdown(pills_html, unsafe_allow_html=True)

    with col_right:
        st.markdown("#### Ganadores (historial)")
        df_winners = fetch_winners(limit=20)
        if df_winners.empty:
            st.write("Sin ganadores aún.")
        else:
            st.dataframe(
                df_winners[["name", "prize", "drawn_at"]],
                use_container_width=True,
                height=300,
            )

    st.markdown("---")

    # Controles de ruleta (solo ADMIN puede disparar el sorteo)
    st.markdown("### 🎛 Control de ruleta")

    prize_input = st.text_input("Premio para este sorteo", placeholder="Ej. Tarjeta de Amazon, Día libre, etc.")
    col_btn1, col_btn2 = st.columns([1, 3])

    with col_btn1:
        spin_btn = st.button("🎰 Girar ruleta")

    if spin_btn:
        if not is_admin:
            st.error("Solo un usuario con código ADMIN puede girar la ruleta.")
        else:
            admin_name = host_name.strip() or "ADMIN"
            winner_row, err = draw_winner(prize_input, admin_name=admin_name)
            if err:
                st.error(err)
            else:
                st.success("¡Tenemos ganador! 🎉")
                st.balloons()
                st.markdown(
                    f"<div class='winner-banner'>🎉 {winner_row['name']} 🎉</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div class='winner-sub'>Premio: <b>{prize_input}</b></div>",
                    unsafe_allow_html=True,
                )

# -------------------------------------------------
# TAB 3: MURO EN VIVO (ESTILO KAHOOT)
# -------------------------------------------------
with tab_wall:
    st.subheader("📺 Muro en vivo (tipo Kahoot)")

    st.markdown(
        "Ideal para proyectar en pantalla grande y ver cómo se va llenando la rifa en tiempo real."
    )

    df_all = fetch_participants(include_winners=True)
    total_participants = len(df_all)
    total_winners = fetch_winners(limit=500).shape[0]
    df_recent = fetch_recent_participants(limit=30)

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Participantes registrados", total_participants)
    col_b.metric("Ganadores", total_winners)
    col_c.metric("Últimos mostrados en el muro", len(df_recent))

    st.markdown("---")
    st.markdown("### 🧑‍🤝‍🧑 Últimos participantes que se han registrado")

    if df_recent.empty:
        st.info("Todavía no hay registros. Pídele a la gente que se inscriba en la pestaña **Regístrate**.")
    else:
        # Mostrar en estilo “tarjetas” en una cuadrícula tipo Kahoot
        colors = [
            "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF",
            "#D7BDE2", "#F9E79F", "#A9DFBF", "#AED6F1", "#F5B7B1"
        ]

        cols = st.columns(5)
        for idx, (_, row) in enumerate(df_recent.iterrows()):
            c = cols[idx % len(cols)]
            name = row.get("name", "SIN NOMBRE")
            area = row.get("area", "")
            team = row.get("team", "")
            color = colors[idx % len(colors)]

            card_html = f"""
            <div style="
                background-color:{color};
                border-radius:22px;
                padding:14px;
                margin:8px 4px;
                text-align:center;
                font-weight:700;
                font-size:18px;
                box-shadow:0 4px 8px rgba(0,0,0,0.15);
            ">
                {name}
                <div style="font-size:12px;font-weight:400;margin-top:6px;">
                    {area or ''} {('<br>' + team) if team else ''}
                </div>
            </div>
            """
            c.markdown(card_html, unsafe_allow_html=True)

    st.markdown("---")
    st.caption(
        "Tip: puedes recargar la página o presionar el botón de recarga del navegador "
        "para ver los nuevos participantes en tiempo casi real."
    )
