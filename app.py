# 🚀 Robot CI Battle – Versión con MÓDULOS VISUALES
# -------------------------------------------------
# Esta versión permite que, cuando un equipo responda correctamente,
# se le muestre una SELECCIÓN DE MÓDULOS VISUALES (alas, ruedas, cañones, shields, etc.)
# Cada módulo otorga diferentes stats y aparece como item instalado.
# -------------------------------------------------

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
st.set_page_config(page_title="Robot CI Battle", layout="wide")

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
    .robot-card {
        background-color: #f5f5f5;
        border-radius: 18px;
        padding: 14px 18px;
        margin: 6px 0;
        font-size: 15px;
    }
    .stat-pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        background-color: #eee;
        font-size: 12px;
        margin: 2px;
    }
    .battle-banner {
        background: linear-gradient(135deg, #00f2fe, #4facfe);
        border-radius: 20px;
        padding: 18px;
        text-align: center;
        color: #fff;
        font-weight: 800;
        font-size: 24px;
        margin-bottom: 10px;
    }
    .question-card {
        background-color: #ffffff;
        border-radius: 18px;
        padding: 18px 20px;
        margin-top: 10px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.06);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# CONEXIÓN FIREBASE (MISMO PUENTE DE TU RIFA)
# -------------------------------------------------
@st.cache_resource
def init_firebase():
    firebase_creds = st.secrets["firebase_credentials"]
    if hasattr(firebase_creds, "to_dict"):
        firebase_creds = firebase_creds.to_dict()
    bucket_name = st.secrets["firebase_bucket"]["firebase_bucket"]

    if not firebase_admin._apps:
        cred = credentials.Certificate(firebase_creds)
        firebase_admin.initialize_app(cred, {"storageBucket": bucket_name})

    return firestore.client(), storage.bucket()

db, bucket = init_firebase()
TZ = pytz.timezone("America/Mexico_City")

# -------------------------------------------------
# PREGUNTAS DEL QUIZ
# -------------------------------------------------
QUESTIONS = [
    {
        "id": 1,
        "text": "¿Qué es mejora continua?",
        "options": ["Cambios pequeños constantes", "Un reporte mensual", "Una auditoría", "Un dashboard"],
        "correct_option": "Cambios pequeños constantes",
    },
    {
        "id": 2,
        "text": "¿Cuál es un desperdicio (muda)?",
        "options": ["Esperas largas", "Solucionar al primer contacto", "Estandarizar", "Mejorar un layout"],
        "correct_option": "Esperas largas",
    },
    {
        "id": 3,
        "text": "¿Qué herramienta inicia análisis causa raíz?",
        "options": ["5 Porqués", "Comprar software", "Cambiar equipo", "Esperar"],
        "correct_option": "5 Porqués",
    },
]
TOTAL_QUESTIONS = len(QUESTIONS)

# -------------------------------------------------
# MÓDULOS VISUALES
# Cada módulo se instala SOLO cuando la respuesta es correcta.
# -------------------------------------------------
MODULES = [
    {
        "name": "🔥 Cañón Laser",
        "stats": {"attack": 7},
        "desc": "+7 ATAQUE",
    },
    {
        "name": "🛡️ Blindaje Titanio",
        "stats": {"defense": 7},
        "desc": "+7 DEFENSA",
    },
    {
        "name": "🚀 Ruedas Turbo",
        "stats": {"speed": 7},
        "desc": "+7 VELOCIDAD",
    },
    {
        "name": "✈️ Alas Aerodinámicas",
        "stats": {"mobility": 7},
        "desc": "+7 MOVILIDAD",
    },
]

# -------------------------------------------------
# FIRESTORE COLLECTIONS
# -------------------------------------------------
ROBOTS_COL = "ci_robots"

# -------------------------------------------------
# FUNCIONES PRINCIPALES
# -------------------------------------------------
def get_or_create_robot(team_name: str):
    team = team_name.strip().upper()

    q = db.collection(ROBOTS_COL).where("team_name", "==", team).limit(1).stream()
    for d in q:
        data = d.to_dict(); data["_id"] = d.id
        return d.id, data

    now = datetime.now(TZ)
    base = {
        "team_name": team,
        "created_ts": now,
        "attack": 0,
        "defense": 0,
        "speed": 0,
        "mobility": 0,
        "items": [],
        "current_q_index": 0,
        "awaiting_module": False,
        "last_correct_question_id": None,
    }
    ref = db.collection(ROBOTS_COL).document()
    ref.set(base)
    base["_id"] = ref.id
    return ref.id, base


def apply_module(robot_data: dict, module: dict):
    for stat, val in module["stats"].items():
        robot_data[stat] = robot_data.get(stat, 0) + val
    robot_data["items"].append(f"{module['name']} ({module['desc']})")
    return robot_data


def update_robot(robot_id, data):
    db.collection(ROBOTS_COL).document(robot_id).update(data)


def fetch_all_robots():
    docs = db.collection(ROBOTS_COL).stream()
    rows = []
    for d in docs:
        di = d.to_dict(); di["_id"] = d.id
        rows.append(di)
    return pd.DataFrame(rows) if rows else pd.DataFrame()

# -------------------------------------------------
# ADMIN LOGIN
# -------------------------------------------------
def check_is_admin():
    try:
        pw = st.secrets["raffle_admin"]["password"]
    except:
        return False
    return st.session_state.get("admin_password_value", "") == pw

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------
st.sidebar.title("🤖 Robot CI Battle – Módulos Visuales")
host = st.sidebar.text_input("Tu nombre", "")
st.sidebar.markdown("---")
admin_pw = st.sidebar.text_input("Código admin", type="password", key="admin_password_value")
IS_ADMIN = check_is_admin()
if IS_ADMIN:
    st.sidebar.success("Modo admin activado.")
else:
    st.sidebar.info("Ingresa el código admin si corresponde.")

# -------------------------------------------------
# TABS
# -------------------------------------------------
st.markdown("<div class='big-title'>Robot CI Battle</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>Construye tu robot eligiendo módulos visuales</div>", unsafe_allow_html=True)

quiz_tab, battle_tab, admin_tab = st.tabs(["🧩 Quiz & Módulos", "⚔️ Batallas", "📊 Admin"])

# -------------------------------------------------
# TAB: QUIZ + MÓDULOS
# -------------------------------------------------
with quiz_tab:
    st.subheader("🧩 Construye tu robot con módulos visuales")

    team_name = st.text_input("Nombre de equipo")
    if st.button("Cargar / Crear robot"):
        if not team_name.strip():
            st.warning("Escribe un nombre")
        else:
            robot_id, robot_data = get_or_create_robot(team_name)
            st.session_state["robot_id"] = robot_id
            st.success(f"Robot listo: {robot_data['team_name']}")

    robot_id = st.session_state.get("robot_id")
    if robot_id:
        doc = db.collection(ROBOTS_COL).document(robot_id).get()
        if not doc.exists:
            st.error("Robot no encontrado")
        else:
            robot = doc.to_dict()

            st.markdown("---")
            st.subheader("Stats actuales")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("ATAQUE", robot.get("attack", 0))
            c2.metric("DEFENSA", robot.get("defense", 0))
            c3.metric("VELOCIDAD", robot.get("speed", 0))
            c4.metric("MOVILIDAD", robot.get("mobility", 0))

            st.markdown("### Módulos instalados")
            for item in robot.get("items", []):
                st.markdown(f"- {item}")

            st.markdown("---")
            idx = robot.get("current_q_index", 0)
            awaiting = robot.get("awaiting_module", False)

            if awaiting:
                st.markdown("### ⭐ Selecciona un módulo visual")

                selected = st.radio("Elige tu módulo", [m["name"] for m in MODULES])

                if st.button("Instalar módulo"):
                    module = next(m for m in MODULES if m["name"] == selected)
                    robot = apply_module(robot, module)

                    update_robot(robot_id, {
                        "attack": robot["attack"],
                        "defense": robot["defense"],
                        "speed": robot["speed"],
                        "mobility": robot["mobility"],
                        "items": robot["items"],
                        "awaiting_module": False,
                    })

                    st.success(f"Módulo instalado: {module['name']} {module['desc']}")
                    st.rerun()

            elif idx < TOTAL_QUESTIONS:
                q = QUESTIONS[idx]
                st.markdown(f"### Pregunta {idx+1}")
                                   st.markdown(f"**{q['text']}**")

                with st.form(f"qform{idx}"):
                    resp = st.radio("Selecciona una opción", q["options"], key=f"resp_{idx}")
                    submit = st.form_submit_button("Responder")

                if submit:
                    if resp == q["correct_option"]:
                        st.success("¡Correcto! Ahora elige tu módulo visual.")
                        update_robot(robot_id, {
                            "awaiting_module": True,
                            "last_correct_question_id": q["id"],
                        })
                    else:
                        st.error("Incorrecto, pero puedes continuar.")
                        update_robot(robot_id, {"current_q_index": idx + 1})

                    st.rerun()

            else:
                st.success("🎉 Terminaste el quiz. Ve a la pestaña de batallas.")

# -------------------------------------------------
# TAB: BATALLAS
# -------------------------------------------------
with battle_tab:
    st.subheader("⚔️ Batallas de Robots")
    df = fetch_all_robots()
    if df.empty:
        st.info("Aún no hay robots")
    else:
        teams = df["team_name"].tolist()

        t1 = st.selectbox("Robot 1", teams)
        t2 = st.selectbox("Robot 2", [t for t in teams if t != t1])

        def score(r):
            return (
                (r.get("attack", 0) * 1.4)
                + (r.get("defense", 0) * 1.2)
                + (r.get("speed", 0) * 1.3)
                + (r.get("mobility", 0) * 1.1)
                + random.uniform(-5, 5)
            )

        if st.button("Simular Batalla"):
            r1 = df[df.team_name == t1].iloc[0]
            r2 = df[df.team_name == t2].iloc[0]

            s1 = score(r1)
            s2 = score(r2)

            winner = t1 if s1 > s2 else t2

            st.markdown(f"<div class='battle-banner'>🏆 Gana {winner}</div>", unsafe_allow_html=True)

# -------------------------------------------------
# TAB: ADMIN
# -------------------------------------------------
with admin_tab:
    if not IS_ADMIN:
        st.warning("Solo admin")
    else:
        st.subheader("📊 Panel Admin")
        df = fetch_all_robots()
        if df.empty:
            st.info("No hay robots")
        else:
            st.dataframe(df, use_container_width=True)
