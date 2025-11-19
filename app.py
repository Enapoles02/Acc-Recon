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
    .battle-sub {
        font-size: 15px;
        text-align: center;
        color: #333;
        margin-bottom: 15px;
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
# CONEXIÓN A FIREBASE (MISMA ESTRUCTURA QUE LA RIFA)
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
# PREGUNTAS DEL QUIZ (MODIFICA LOS TEXTOS A TU GUSTO)
# -------------------------------------------------
# Puedes alinear estas preguntas con los contenidos de Provence.
# Solo cambia "text", "options" y "correct_option". Mantén la estructura.

QUESTIONS = [
    {
        "id": 1,
        "text": "¿Qué es la mejora continua en pocas palabras?",
        "options": [
            "Un proyecto grande que se hace una vez al año",
            "Pequeños cambios constantes que mejoran un proceso",
            "Una certificación que solo aplica a líderes",
            "Un reporte mensual de indicadores",
        ],
        "correct_option": "Pequeños cambios constantes que mejoran un proceso",
        "reward": {"attack": 5},
        "item_label": "Cañón Kaizen (+5 ATAQUE)",
    },
    {
        "id": 2,
        "text": "En un flujo de trabajo, ¿qué sería un desperdicio típico (muda)?",
        "options": [
            "Esperas largas entre actividades",
            "Resolver un problema del cliente en el primer contacto",
            "Estandarizar un proceso",
            "Compartir buenas prácticas",
        ],
        "correct_option": "Esperas largas entre actividades",
        "reward": {"speed": 5},
        "item_label": "Turbo de Flujo (+5 VELOCIDAD)",
    },
    {
        "id": 3,
        "text": "¿Qué herramienta usarías primero para entender un problema?",
        "options": [
            "5 Porqués / análisis de causa raíz",
            "Comprar un nuevo sistema",
            "Cambiar todo el equipo de trabajo",
            "Esperar a que se resuelva solo",
        ],
        "correct_option": "5 Porqués / análisis de causa raíz",
        "reward": {"defense": 5},
        "item_label": "Escudo de Causa Raíz (+5 DEFENSA)",
    },
    {
        "id": 4,
        "text": "Cuando hablamos de estandarizar (Standardize / Seiketsu), nos referimos a...",
        "options": [
            "Documentar y alinear la mejor forma de trabajar",
            "Revisar solo cuando hay auditoría",
            "Guardar las ideas sin compartirlas",
            "Dejar que cada quien trabaje como quiera",
        ],
        "correct_option": "Documentar y alinear la mejor forma de trabajar",
        "reward": {"mobility": 5},
        "item_label": "Alas de Estandarización (+5 MOVILIDAD)",
    },
    {
        "id": 5,
        "text": "¿Qué actitud ayuda más a la mejora continua?",
        "options": [
            "Buscar culpables de los errores",
            "Ver los problemas como oportunidades de mejorar",
            "Ignorar los defectos si el cliente no se queja",
            "Hacer cambios sin avisar al equipo",
        ],
        "correct_option": "Ver los problemas como oportunidades de mejorar",
        "reward": {"attack": 3, "defense": 3, "speed": 3},
        "item_label": "Core de Mentalidad CI (+3 a TODAS LAS STATS)",
    },
]

TOTAL_QUESTIONS = len(QUESTIONS)

# -------------------------------------------------
# COLECCIONES EN FIRESTORE
# -------------------------------------------------
ROBOTS_COL = "ci_robots"
ANSWERS_COL = "ci_robot_answers"  # opcional, para auditoría de respuestas


# -------------------------------------------------
# FUNCIONES DE NEGOCIO (ROBOTS / QUIZ)
# -------------------------------------------------
def get_or_create_robot(team_name: str):
    """Obtiene un robot por nombre de equipo o lo crea si no existe."""
    if not team_name.strip():
        return None, None

    team = team_name.strip().upper()

    query = (
        db.collection(ROBOTS_COL)
        .where("team_name", "==", team)
        .limit(1)
        .stream()
    )
    for doc in query:
        data = doc.to_dict()
        data["_id"] = doc.id
        return doc.id, data

    # Crear nuevo robot
    now = datetime.now(TZ)
    base_stats = {
        "team_name": team,
        "created_at": now.isoformat(),
        "created_ts": now,
        "attack": 0,
        "defense": 0,
        "speed": 0,
        "mobility": 0,
        "items": [],
        "current_q_index": 0,
        "completed": False,
    }
    doc_ref = db.collection(ROBOTS_COL).document()
    doc_ref.set(base_stats)
    base_stats["_id"] = doc_ref.id
    return doc_ref.id, base_stats


def save_answer(robot_id: str, team_name: str, question: dict, selected: str, is_correct: bool):
    """Guarda la respuesta de un robot para fines de tracking (opcional)."""
    now = datetime.now(TZ)
    payload = {
        "robot_id": robot_id,
        "team_name": team_name,
        "question_id": question["id"],
        "question_text": question["text"],
        "selected": selected,
        "correct_option": question["correct_option"],
        "is_correct": is_correct,
        "answered_at": now.isoformat(),
        "answered_ts": now,
    }
    doc_id = str(uuid.uuid4())
    db.collection(ANSWERS_COL).document(doc_id).set(payload)


def apply_reward(robot_data: dict, question: dict):
    """Aplica el reward de la pregunta al robot y devuelve los cambios aplicados."""
    reward = question.get("reward", {}) or {}

    # Asegurar campos
    for stat in ["attack", "defense", "speed", "mobility"]:
        if stat not in robot_data or robot_data[stat] is None:
            robot_data[stat] = 0

    changes = {}

    for stat, val in reward.items():
        if stat in robot_data:
            robot_data[stat] += val
            changes[stat] = val

    items = robot_data.get("items", [])
    item_label = question.get("item_label")
    if item_label:
        items.append(item_label)
    robot_data["items"] = items

    return robot_data, changes


def update_robot_after_answer(robot_id: str, robot_data: dict, question: dict, selected_option: str):
    """Actualiza robot según la respuesta y avanza a la siguiente pregunta."""
    correct = selected_option == question["correct_option"]

    # Guardar respuesta (tracking)
    save_answer(robot_id, robot_data["team_name"], question, selected_option, correct)

    feedback = ""
    if correct:
        robot_data, changes = apply_reward(robot_data, question)
        # Mensaje de feedback amistoso
        if changes:
            gains = []
            if "attack" in changes:
                gains.append(f"+{changes['attack']} ATAQUE")
            if "defense" in changes:
                gains.append(f"+{changes['defense']} DEFENSA")
            if "speed" in changes:
                gains.append(f"+{changes['speed']} VELOCIDAD")
            if "mobility" in changes:
                gains.append(f"+{changes['mobility']} MOVILIDAD")
            gains_txt = ", ".join(gains)
            feedback = f"✅ ¡Respuesta correcta! Tu robot ganó: {gains_txt}."
        else:
            feedback = "✅ ¡Respuesta correcta! Tu robot avanzó de ronda."
    else:
        feedback = "❌ Respuesta incorrecta. Esta vez tu robot no recibe mejora, pero sigues avanzando."

    # Avanzar índice de pregunta
    current_idx = robot_data.get("current_q_index", 0)
    next_idx = current_idx + 1

    completed = next_idx >= TOTAL_QUESTIONS

    robot_data["current_q_index"] = next_idx
    robot_data["completed"] = completed

    # Actualizar en Firestore
    db.collection(ROBOTS_COL).document(robot_id).update(
        {
            "attack": robot_data["attack"],
            "defense": robot_data["defense"],
            "speed": robot_data["speed"],
            "mobility": robot_data["mobility"],
            "items": robot_data["items"],
            "current_q_index": robot_data["current_q_index"],
            "completed": robot_data["completed"],
        }
    )

    return robot_data, feedback, correct


def fetch_all_robots():
    docs = db.collection(ROBOTS_COL).stream()
    rows = []
    for d in docs:
        data = d.to_dict()
        data["_id"] = d.id
        rows.append(data)
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        if "created_ts" in df.columns:
            df = df.sort_values("created_ts")
        elif "created_at" in df.columns:
            df = df.sort_values("created_at")
    return df


# -------------------------------------------------
# CONTROL DE ADMIN (MISMO PATRÓN QUE LA RIFA)
# -------------------------------------------------
def check_is_admin():
    """Usa un password guardado en secrets para permitir el panel admin."""
    admin_pw_secret = None
    try:
        admin_pw_secret = st.secrets["raffle_admin"]["password"]
    except Exception:
        # Si no está configurado, nadie es admin (pero no rompes la app)
        return False

    entered_pw = st.session_state.get("admin_password_value", "")
    return bool(admin_pw_secret) and entered_pw == admin_pw_secret


# -------------------------------------------------
# SIDEBAR: DATOS DE USUARIO / ADMIN
# -------------------------------------------------
st.sidebar.title("🤖 Robot CI Battle")
host_name = st.sidebar.text_input("Tu nombre (host / facilitador)", value="")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔐 Admin (para panel y batallas)")
admin_pw_input = st.sidebar.text_input(
    "Código admin", type="password", key="admin_password_value"
)

is_admin = check_is_admin()
if is_admin:
    st.sidebar.success("Modo ADMIN activado.")
else:
    st.sidebar.info("Si eres admin, ingresa el código para ver el panel de batallas.")

st.sidebar.markdown("---")
st.sidebar.caption("Los robots y respuestas se guardan en Firebase en tiempo real.")

# -------------------------------------------------
# NAVEGACIÓN SUPERIOR (TABS)
# -------------------------------------------------
st.markdown("<div class='big-title'>Robot CI Battle</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='subtitle'>Responde preguntas de Mejora Continua, equipa tu robot y compite en batallas 🛠️⚙️</div>",
    unsafe_allow_html=True,
)

quiz_tab, battle_tab, admin_tab = st.tabs(
    ["🧩 Construye tu robot", "⚔️ Batalla de robots", "📊 Panel Admin"]
)

# -------------------------------------------------
# TAB 1: CONSTRUYE TU ROBOT (QUIZ)
# -------------------------------------------------
with quiz_tab:
    st.subheader("🧩 Construye tu robot CI a partir de tus respuestas")

    st.markdown(
        """
        1. Escribe el nombre de tu equipo (por ejemplo, **Team Kaizen**, **CI Avengers**, etc.).  
        2. Responde cada pregunta.  
        3. Cada respuesta correcta te da una mejora (arma, escudo, turbo, etc.).  
        4. Al final tendrás un robot único para la batalla.
        """
    )

    team_name_input = st.text_input(
        "Nombre de tu equipo / robot*",
        placeholder="Ej. TEAM KAIZEN",
        key="team_name_input",
    )

    col_btn_team, _ = st.columns([1, 3])
    with col_btn_team:
        load_robot_btn = st.button("🚀 Crear / Cargar robot")

    if load_robot_btn:
        if not team_name_input.strip():
            st.warning("Escribe un nombre de equipo para continuar.")
        else:
            robot_id, robot_data = get_or_create_robot(team_name_input)
            if robot_id:
                st.session_state["robot_id"] = robot_id
                st.session_state["team_name"] = robot_data["team_name"]
                st.session_state["robot_loaded"] = True
                st.success(f"Robot cargado para el equipo: {robot_data['team_name']}")
            else:
                st.error("No se pudo crear/cargar el robot. Intenta de nuevo.")

    # Si ya se cargó el robot previamente en la sesión
    robot_id = st.session_state.get("robot_id")
    robot_loaded = st.session_state.get("robot_loaded", False)

    if robot_loaded and robot_id:
        # Refrescar datos desde Firestore por si se abrió en varias pestañas
        doc = db.collection(ROBOTS_COL).document(robot_id).get()
        if not doc.exists:
            st.error("No se encontró el robot en la base. Vuelve a crearlo.")
        else:
            robot_data = doc.to_dict()
            st.markdown("---")

            # Mostrar stats actuales del robot
            st.markdown("### 🤖 Tu robot actualmente")

            stats_cols = st.columns(4)
            stats_cols[0].metric("ATAQUE", robot_data.get("attack", 0))
            stats_cols[1].metric("DEFENSA", robot_data.get("defense", 0))
            stats_cols[2].metric("VELOCIDAD", robot_data.get("speed", 0))
            stats_cols[3].metric("MOVILIDAD", robot_data.get("mobility", 0))

            items = robot_data.get("items", []) or []
            if items:
                st.markdown("#### 🧩 Mejoras obtenidas")
                for it in items:
                    st.markdown(f"- {it}")
            else:
                st.info("Aún no tienes mejoras. Responde preguntas para equipar a tu robot.")

            # Progreso del quiz
            current_q_index = robot_data.get("current_q_index", 0)
            st.markdown("---")
            st.markdown("### 📌 Preguntas")
            st.progress(min(current_q_index, TOTAL_QUESTIONS) / TOTAL_QUESTIONS)
            st.caption(
                f"Pregunta {min(current_q_index + 1, TOTAL_QUESTIONS)} de {TOTAL_QUESTIONS}"
                if current_q_index < TOTAL_QUESTIONS
                else f"Has respondido las {TOTAL_QUESTIONS} preguntas. ¡Tu robot está listo para la batalla!"
            )

            if current_q_index >= TOTAL_QUESTIONS:
                st.success("🎉 Has completado el quiz. Lleva este robot a la pestaña de batallas.")
            else:
                q = QUESTIONS[current_q_index]

                with st.form(key=f"question_form_{q['id']}"):
                    st.markdown("<div class='question-card'>", unsafe_allow_html=True)
                    st.markdown(f"**{q['text']}**")

                    selected_option = st.radio(
                        "Selecciona una respuesta:",
                        q["options"],
                        key=f"q_{q['id']}_radio",
                    )

                    submit_answer = st.form_submit_button("Responder")
                    st.markdown("</div>", unsafe_allow_html=True)

                if submit_answer:
                    if not selected_option:
                        st.warning("Selecciona una opción para continuar.")
                    else:
                        robot_data, feedback, correct = update_robot_after_answer(
                            robot_id, robot_data, q, selected_option
                        )
                        if correct:
                            st.success(feedback)
                        else:
                            st.error(feedback)
                        st.experimental_rerun()

# -------------------------------------------------
# TAB 2: BATALLA DE ROBOTS (PARA EL SHOW EN EL TOWNHALL)
# -------------------------------------------------
with battle_tab:
    st.subheader("⚔️ Batalla de robots")

    st.markdown(
        """
        Aquí puedes simular batallas entre robots ya creados.  
        Ideal para el cierre del Town Hall: eliges dos equipos y vemos quién gana
        con base en las estadísticas acumuladas.
        """
    )

    df_robots = fetch_all_robots()

    if df_robots.empty:
        st.info("Todavía no hay robots creados. Pídele a los equipos que completen el quiz.")
    else:
        st.markdown("### 🤖 Robots disponibles")
        st.dataframe(
            df_robots[["team_name", "attack", "defense", "speed", "mobility", "completed"]],
            use_container_width=True,
        )

        teams = df_robots["team_name"].unique().tolist()

        if len(teams) < 2:
            st.warning("Se necesitan al menos 2 robots/equipos para simular una batalla.")
        else:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                team1 = st.selectbox("Robot / Equipo 1", teams, key="battle_team1")
            with col_b2:
                # lista sin el team1 para evitar que se elija el mismo
                teams_2 = [t for t in teams if t != team1]
                team2 = st.selectbox("Robot / Equipo 2", teams_2, key="battle_team2")

            def compute_score(row):
                """Puntaje simple combinado de stats + aleatoriedad suave."""
                atk = row.get("attack", 0) or 0
                dfs = row.get("defense", 0) or 0
                spd = row.get("speed", 0) or 0
                mob = row.get("mobility", 0) or 0
                base_score = atk * 1.5 + dfs * 1.2 + spd * 1.3 + mob
                random_bonus = random.uniform(-5, 5)
                return base_score + random_bonus

            battle_btn = st.button("🔥 Simular batalla")

            if battle_btn:
                row1 = df_robots[df_robots["team_name"] == team1].iloc[0]
                row2 = df_robots[df_robots["team_name"] == team2].iloc[0]

                score1 = compute_score(row1)
                score2 = compute_score(row2)

                if score1 > score2:
                    winner_team = team1
                    loser_team = team2
                    winner_row = row1
                    loser_row = row2
                elif score2 > score1:
                    winner_team = team2
                    loser_team = team1
                    winner_row = row2
                    loser_row = row1
                else:
                    # Empate: desempatar aleatoriamente
                    winner_team = random.choice([team1, team2])
                    loser_team = team2 if winner_team == team1 else team1
                    winner_row = df_robots[df_robots["team_name"] == winner_team].iloc[0]
                    loser_row = df_robots[df_robots["team_name"] == loser_team].iloc[0]

                st.markdown(
                    f"<div class='battle-banner'>🏆 ¡Gana {winner_team}!</div>",
                    unsafe_allow_html=True,
                )

                st.markdown(
                    "<div class='battle-sub'>La combinación de mejoras, stats y un poco de suerte definió al ganador.\n"
                    "Usa esto para hablar de cómo las buenas decisiones en mejora continua van sumando ventajas.</div>",
                    unsafe_allow_html=True,
                )

                col_w, col_l = st.columns(2)

                def render_robot(col, row, title):
                    col.markdown(f"#### {title}: {row['team_name']}")
                    col.markdown("<div class='robot-card'>", unsafe_allow_html=True)
                    col.markdown(
                        f"<span class='stat-pill'>ATAQUE: {int(row.get('attack', 0) or 0)}</span> "
                        f"<span class='stat-pill'>DEFENSA: {int(row.get('defense', 0) or 0)}</span> "
                        f"<span class='stat-pill'>VELOCIDAD: {int(row.get('speed', 0) or 0)}</span> "
                        f"<span class='stat-pill'>MOVILIDAD: {int(row.get('mobility', 0) or 0)}</span>",
                        unsafe_allow_html=True,
                    )
                    items = row.get("items", []) or []
                    if items:
                        col.markdown("<br><b>Mejoras equipadas:</b>", unsafe_allow_html=True)
                        for it in items:
                            col.markdown(f"- {it}")
                    col.markdown("</div>", unsafe_allow_html=True)

                render_robot(col_w, winner_row, "Ganador")
                render_robot(col_l, loser_row, "Rival")

        st.markdown("---")
        st.caption(
            "Puedes repetir la batalla con diferentes equipos para hacer el cierre del Town Hall más dinámico."
        )

# -------------------------------------------------
# TAB 3: PANEL ADMIN (VISTA GENERAL)
# -------------------------------------------------
with admin_tab:
    st.subheader("📊 Panel Admin")

    if not is_admin:
        st.warning("Esta sección solo está disponible en modo ADMIN.")
    else:
        st.markdown(
            """
            Aquí puedes ver todos los robots, sus estadísticas y el avance del quiz.  
            Útil para revisar cuántos equipos completaron el juego y qué tan "armados" están.
            """
        )

        df_robots_admin = fetch_all_robots()
        if df_robots_admin.empty:
            st.info("Todavía no hay robots registrados.")
        else:
            st.markdown("### 📋 Listado de robots")
            st.dataframe(
                df_robots_admin[
                    [
                        "team_name",
                        "attack",
                        "defense",
                        "speed",
                        "mobility",
                        "items",
                        "current_q_index",
                        "completed",
                        "created_at",
                    ]
                ],
                use_container_width=True,
            )

            total_robots = len(df_robots_admin)
            completed_count = int(df_robots_admin["completed"].fillna(False).sum())

            col_m1, col_m2 = st.columns(2)
            col_m1.metric("Robots / Equipos creados", total_robots)
            col_m2.metric("Robots que completaron el quiz", completed_count)

        st.markdown("---")
        st.caption("Admin tip: puedes limpiar colecciones desde la consola de Firebase si quieres reiniciar el juego.")
