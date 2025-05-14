import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, date, timedelta
import streamlit.components.v1 as components
import json, random, uuid
import pandas as pd
import altair as alt
from streamlit_autorefresh import st_autorefresh

# ================================
# Definición de usuarios y áreas
# ================================
valid_users = {
    # R2R NAMER (incluye MACANO)
    "VREYES": "Reyes Escorsia Victor Manuel",
    "RCRUZ": "Cruz Madariaga Rodrigo",
    "AZENTENO": "Zenteno Perez Alejandro",
    "XGUTIERREZ": "Gutierrez Hernandez Ximena",
    "CNAPOLES": "Napoles Escalante Christopher Enrique",
    "SANTCAST": "CASTILLO ALMAZAN SANTIAGO",
    "JULIOTOR": "Julio Eduardo Torres Cano",
    "RODAVALO": "Rodrigo Avalos Muro",
    # R2R LATAM
    "MHERNANDEZ": "Hernandez Ponce Maria Guadalupe",
    "MGARCIA": "Garcia Vazquez Mariana Aketzalli",
    "PSARACHAGA": "Paula Sarachaga",
    # TL para GL NAMER & LATAM:
    "ALECCION": "TL GL NAMER LATAM",
    # R2R GRAL:
    "ANDRES": "Andres",
    "MIRIAMGRAL": "Miriam GRAL",
    "YAEL": "Yael",
    "R2RGRAL": "TL R2R GRAL",
    "MSANCHEZ": "Miriam Sanchez",
    # WOR SGBS:
    "MLOPEZ": "Miguel Lopez",
    "GMAYORAL": "Guillermo Mayoral",
    "BOSNAYA": "Becerril Osnaya",
    "JTHIAGO": "Jose Thiago",
    "IOROZCO": "Isaac Orozco",
    "WORLEAD": "TL WOR SGBS",
    # RH para WOR SGBS (monedas):
    "LARANDA": "RH - Luis Aranda",
    # FA:
    "GAVILES": "Gabriel Aviles",
    "JLOPEZ": "Jesus Lopez",
    "FALEAD": "TL FA",
    "ABARRERA": "Andres Barrera",
    # IC (se retira a Carlos):
    "LEDYANEZ": "Luis Enrique Delhumeau Yanez",
    "EIMARTINEZ": "Elizabeth Ibanez Martinez",
    "ICLEAD": "TL IC",
       "ANAHERRERA": "Ana Herrera",
    "JBECERRIL": "Jose Becerril",
    "MPEREZ": "Miguel Perez",
    "JREYES": "Jared Reyes",
    # Nuevos usuarios para IC:
    "EPALMA": "Edgar Palma",
    "DSALAZAR": "Diego Salazar",
    # Perfil KPI (este usuario mostrará el dashboard de KPIs)
    "KPI": "KPI Reporte"
}

group_namer    = {"VREYES", "RCRUZ", "AZENTENO", "XGUTIERREZ", "CNAPOLES", "SANTCAST", "JULIOTOR", "RODAVALO"}
group_latam    = {"MHERNANDEZ", "MGARCIA", "PSARACHAGA"}
group_r2r_gral = {"ANDRES", "MIRIAMGRAL", "YAEL", "R2RGRAL", "MSANCHEZ"}
group_wor      = {"MLOPEZ", "GMAYORAL", "BOSNAYA", "JTHIAGO", "IOROZCO", "WORLEAD", "LARANDA"}
group_fa       = {"GAVILES", "JLOPEZ", "FALEAD", "ABARRERA"}
group_ic       = {"LEDYANEZ", "EIMARTINEZ", "ICLEAD", "ANAHERRERA", "JBECERRIL", "MPEREZ", "JREYES", "EPALMA", "DSALAZAR"}

TL_USERS = {"ALECCION", "WORLEAD", "R2RGRAL", "FALEAD", "ICLEAD"}


# ================================
# Pantalla de Login
# ================================
if "user_code" not in st.session_state:
    st.session_state["user_code"] = None

def show_login():
    st.title("🔥 Daily Huddle - Login")
    st.write("Ingresa tu código de usuario")
    user_input = st.text_input("Código de usuario:", max_chars=20)
    if st.button("Ingresar"):
        user_input = user_input.strip().upper()
        if user_input in valid_users:
            st.session_state.user_code = user_input
            st.success(f"¡Bienvenido, {valid_users[user_input]}!")
        else:
            st.error("Código de usuario inválido. Intenta nuevamente.")

if st.session_state["user_code"] is None:
    show_login()
    st.stop()

# ================================
# Repositorio de actividades (simulado)
# ================================
activity_repo = [
    "Reunión de planificación corporativa",
    "Actualización de estrategia logística",
    "Análisis de desempeño trimestral",
    "Sesión de brainstorming para innovación"
]

# ================================
# Inicialización de Firebase usando secrets (TOML)
# ================================
def init_firebase():
    firebase_config = st.secrets["firebase"]
    if not isinstance(firebase_config, dict):
        firebase_config = firebase_config.to_dict()
    try:
        cred = credentials.Certificate(firebase_config)
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        return db
    except Exception as e:
        st.error(f"Error al inicializar Firebase: {e}")
        st.stop()

db = init_firebase()

# ================================
# Función para determinar el jefe directo
# ================================
def get_direct_boss(destinatario_code):
    if destinatario_code in (group_namer.union(group_latam)):
        return "ALECCION"
    elif destinatario_code in group_r2r_gral:
        return "R2RGRAL"
    elif destinatario_code in group_wor:
        return "WORLEAD"
    elif destinatario_code in group_fa:
        return "FALEAD"
    elif destinatario_code in group_ic:
        return "ICLEAD"
    else:
        return "N/A"

# ================================
# Función para obtener el equipo de un TL
# ================================
def get_team_for_tl(tl_code):
    if tl_code == "ALECCION":
        return [u for u in valid_users if u in group_namer.union(group_latam)]
    elif tl_code == "WORLEAD":
        return [u for u in valid_users if u in group_wor]
    elif tl_code == "R2RGRAL":
        return [u for u in valid_users if u in group_r2r_gral]
    elif tl_code == "FALEAD":
        return [u for u in valid_users if u in group_fa]
    elif tl_code == "ICLEAD":
        return [u for u in valid_users if u in group_ic]
    else:
        return [tl_code]

# ================================
# Función para obtener la "fecha activa" (día laboral)
# ================================
def get_active_date():
    today = date.today()
    if today.weekday() == 5:
        active = today - timedelta(days=1)
    elif today.weekday() == 6:
        active = today - timedelta(days=2)
    else:
        active = today
    return active.strftime("%Y-%m-%d")

# ================================
# Función para eliminar tareas en grupo
# ================================
def delete_task_group(collection, group_id):
    query = db.collection(collection).where("group_id", "==", group_id).stream()
    for doc in query:
        db.collection(collection).document(doc.id).delete()

# ================================
# Función para mostrar el timer de 30 minutos
# ================================
def show_timer():
    st_autorefresh(interval=1000, key="timer_autorefresh")
    if "timer_start" not in st.session_state:
        if st.button("Start Timer"):
            st.session_state.timer_start = datetime.now()
    if "timer_start" in st.session_state:
        elapsed = (datetime.now() - st.session_state.timer_start).total_seconds()
        remaining = max(0, 30 * 60 - elapsed)
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        st.write(f"Tiempo restante: {minutes:02d}:{seconds:02d}")

# ================================
# Dashboard KPI para usuario KPI (filtrado diario, semanal y mensual)
# ================================
def show_kpi_dashboard():
    st.header("Dashboard KPI")
    st.markdown("Resumen general de reportes:")
    period = st.radio("Filtrar por:", ["Diaria", "Semanal", "Mensual"])
    today = date.today()
    if period == "Diaria":
        start_date = today
        end_date = today
    elif period == "Semanal":
        start_date = today - timedelta(days=today.weekday())  # Lunes
        end_date = start_date + timedelta(days=6)
    else:  # Mensual
        start_date = today.replace(day=1)
        if today.month == 12:
            end_date = today.replace(year=today.year+1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month+1, day=1) - timedelta(days=1)
    st.write("Mostrando datos desde", start_date.strftime("%Y-%m-%d"), "hasta", end_date.strftime("%Y-%m-%d"))

    # Asistencia: consulta documentos en "attendance" en el rango seleccionado
    attendance_docs = []
    for doc in db.collection("attendance").stream():
        data = doc.to_dict()
        try:
            doc_date = datetime.strptime(data.get("fecha", "2100-01-01"), "%Y-%m-%d").date()
        except:
            continue
        if start_date <= doc_date <= end_date:
            attendance_docs.append(data)
    if attendance_docs:
        df_att = pd.DataFrame(attendance_docs)
        df_att["fecha"] = pd.to_datetime(df_att["fecha"])
        df_count = df_att.groupby("fecha").size().reset_index(name="Asistencias")
        chart_att = alt.Chart(df_count).mark_line(point=True).encode(
            x=alt.X("fecha:T", title="Fecha"),
            y=alt.Y("Asistencias:Q", title="Número de Asistencias"),
            tooltip=["fecha", "Asistencias"]
        ).properties(
            width=600,
            height=300,
            title="Asistencia por día"
        )
        st.altair_chart(chart_att, use_container_width=True)
    else:
        st.info("No hay registros de asistencia en el período seleccionado.")

    # Top 3: consulta documentos en "top3"
    top3_docs = []
    for doc in db.collection("top3").stream():
        data = doc.to_dict()
        try:
            doc_date = datetime.strptime(data.get("fecha_inicio", "2100-01-01"), "%Y-%m-%d").date()
        except:
            continue
        if start_date <= doc_date <= end_date:
            top3_docs.append(data)
    if top3_docs:
        df_top3 = pd.DataFrame(top3_docs)
        df_status = df_top3["status"].value_counts().reset_index()
        df_status.columns = ["Status", "Cantidad"]
        chart_top3 = alt.Chart(df_status).mark_bar().encode(
            x=alt.X("Status:N", title="Status"),
            y=alt.Y("Cantidad:Q", title="Tareas"),
            color="Status:N",
            tooltip=["Status", "Cantidad"]
        ).properties(
            width=300,
            height=300,
            title="Distribución de Status en Top 3"
        )
        st.altair_chart(chart_top3, use_container_width=True)
    else:
        st.info("No hay tareas Top 3 en el período seleccionado.")

    # Actions: consulta documentos en "actions"
    actions_docs = []
    for doc in db.collection("actions").stream():
        data = doc.to_dict()
        try:
            doc_date = datetime.strptime(data.get("fecha_inicio", "2100-01-01"), "%Y-%m-%d").date()
        except:
            continue
        if start_date <= doc_date <= end_date:
            actions_docs.append(data)
    if actions_docs:
        df_actions = pd.DataFrame(actions_docs)
        df_actions_count = df_actions.groupby("status").size().reset_index(name="Cantidad")
        chart_actions = alt.Chart(df_actions_count).mark_bar().encode(
            x=alt.X("status:N", title="Status"),
            y=alt.Y("Cantidad:Q", title="Acciones"),
            color="status:N",
            tooltip=["status", "Cantidad"]
        ).properties(
            width=300,
            height=300,
            title="Distribución de Status en Actions"
        )
        st.altair_chart(chart_actions, use_container_width=True)
    else:
        st.info("No hay acciones en el período seleccionado.")

# ================================
# Función para enviar una tarea de Action Board a Top 3
# ================================
def send_action_to_top3(action_doc):
    data_ref = action_doc
    if not hasattr(data_ref, "to_dict"):
        data_ref = action_doc.get()
    data = data_ref.to_dict()
    new_data = data.copy()
    new_data.pop("timestamp", None)
    new_data["fecha_inicio"] = datetime.now().strftime("%Y-%m-%d")
    new_data["group_id"] = str(uuid.uuid4())
    # Mapear el campo "accion" a "descripcion" si es necesario
    if "accion" in new_data and "descripcion" not in new_data:
        new_data["descripcion"] = new_data.pop("accion")
    db.collection("top3").add(new_data)
    st.success("Tarea enviada de Action Board a Top 3.")

# ================================
# App Principal
# ================================
def show_main_app():
    user_code = st.session_state["user_code"]

    # Si el usuario es KPI, mostrar el dashboard de KPIs y detener la ejecución del resto
    if user_code == "KPI":
        show_kpi_dashboard()
        return

    # Mostrar timer si es TL o asignado como Timekeeper
    if user_code in TL_USERS or ("roles" in st.session_state and st.session_state["roles"].get("Timekeeper") == user_code):
        st.subheader("⏱ Timer (30 min)")
        show_timer()

    # Botón de Asignar Roles para TL
    if user_code in TL_USERS:
        if st.button("Asignar Roles"):
            if user_code == "ALECCION":
                posibles = [code for code in valid_users if code not in {"ALECCION", "WORLEAD", "LARANDA", "R2RGRAL", "FALEAD", "ICLEAD", "KPI"}]
            elif user_code == "WORLEAD":
                posibles = [code for code in valid_users if code not in {"WORLEAD", "ALECCION", "LARANDA", "R2RGRAL", "FALEAD", "ICLEAD", "KPI"} and code in group_wor]
            elif user_code == "R2RGRAL":
                posibles = [code for code in valid_users if code not in {"R2RGRAL", "ALECCION", "WORLEAD", "LARANDA", "FALEAD", "ICLEAD", "KPI"} and code in group_r2r_gral]
            elif user_code == "FALEAD":
                posibles = [code for code in valid_users if code not in {"FALEAD", "ALECCION", "WORLEAD", "LARANDA", "R2RGRAL", "ICLEAD", "KPI"} and code in group_fa]
            elif user_code == "ICLEAD":
                posibles = [code for code in valid_users if code not in {"ICLEAD", "ALECCION", "WORLEAD", "LARANDA", "R2RGRAL", "FALEAD", "KPI"} and code in group_ic]
            roles_asignados = random.sample(possibles, 3) if user_code in {"ALECCION", "WORLEAD", "ICLEAD"} else random.sample(possibles, 2)
            st.session_state["roles"] = {
                "Timekeeper": roles_asignados[0],
                "ActionTaker": roles_asignados[1],
                "Coach": roles_asignados[2] if len(roles_asignados) == 3 else None
            }
            st.json(st.session_state["roles"])

    st.image("http://bulk-distributor.com/wp-content/uploads/2016/01/DB-Schenker-Hub-Salzburg.jpg",
             caption="DB Schenker", use_container_width=True)
    
    st.title("🔥 Daily Huddle")
    st.markdown(f"**Usuario:** {valid_users[user_code]}  ({user_code})")
    
    menu_options = ["Asistencia", "Top 3", "Action Board", "Escalation", "Recognition", 
                    "Store DBSCHENKER", "Wallet", "Communications", "Calendar", "Compliance", "Todas las Tareas",
                    "Consultorio Optimizacion", "Contacto"]
    if user_code in {"ALECCION", "WORLEAD", "R2RGRAL", "FALEAD", "ICLEAD"}:
        menu_options.append("Roles")
    menu_choice = st.sidebar.selectbox("📌 Selecciona una pestaña:", menu_options)

    # ------------------- Asistencia -------------------
    if menu_choice == "Asistencia":
        if user_code not in TL_USERS:
            st.subheader("📝 Registro de Asistencia")
            today_date = datetime.now().strftime("%Y-%m-%d")
            attendance_doc = db.collection("attendance").document(user_code).get()
            if attendance_doc.exists:
                data = attendance_doc.to_dict()
                if data.get("fecha") != today_date:
                    db.collection("attendance").document(user_code).delete()
            st.write("💡 ¿Cómo te sientes hoy?")
            feelings = {"😃": "Feliz", "😐": "Normal", "😔": "Triste", "😡": "Molesto", "😴": "Cansado", "🤒": "Enfermo"}
            selected_feeling = st.radio("Selecciona tu estado de ánimo:", list(feelings.keys()))
            health_problem = st.radio("❓ ¿Te has sentido con problemas de salud esta semana?", ["Sí", "No"])
            st.write("Nivel de energía (elige entre 20, 40, 60, 80 o 100):")
            energy_options = [20, 40, 60, 80, 100]
            energy_level = st.radio("Nivel de energía:", options=energy_options, horizontal=True)
            battery_html = f"""
            <div style="display: inline-block; border: 2px solid #000; width: 40px; height: 100px; position: relative;">
              <div style="position: absolute; bottom: 0; width: 100%; height: {energy_level}%; background-color: #00ff00;"></div>
            </div>
            """
            st.markdown(battery_html, unsafe_allow_html=True)
            if st.button("✅ Registrar asistencia"):
                db.collection("attendance").document(user_code).set({
                    "fecha": today_date,
                    "estado_animo": feelings[selected_feeling],
                    "problema_salud": health_problem,
                    "energia": energy_level,
                    "usuario": user_code
                })
                st.success("Asistencia registrada correctamente.")
        else:
            st.subheader("📊 Resumen de Asistencia de tu equipo")
            active_date = get_active_date()
            team = get_team_for_tl(user_code)
            attendance_list = []
            for u in team:
                doc = db.collection("attendance").document(u).get()
                if doc.exists and doc.to_dict().get("fecha") == active_date:
                    info = doc.to_dict()
                    attendance = "✅"
                    feeling = info.get("estado_animo", "N/A")
                    fecha = info.get("fecha", "N/A")
                    pregunta = info.get("problema_salud", "N/A")
                    energia = f"{info.get('energia', 0)}%"
                else:
                    attendance = "❌"
                    feeling = "N/A"
                    fecha = active_date
                    pregunta = "N/A"
                    energia = "N/A"
                attendance_list.append({
                    "Nombre": valid_users.get(u, u),
                    "Asistencia": attendance,
                    "Feeling": feeling,
                    "Fecha": fecha,
                    "Pregunta de la semana": pregunta,
                    "Nivel de energía": energia
                })
            if attendance_list:
                df_attendance = pd.DataFrame(attendance_list).reset_index(drop=True)
                st.dataframe(df_attendance)
            else:
                st.info("No hay registros para la fecha activa: " + active_date)
    
    # ------------------- Top 3 -------------------
    elif menu_choice == "Top 3":
        st.subheader("📌 Top 3 Prioridades - Resumen")
        if user_code in TL_USERS:
            team = get_team_for_tl(user_code)
            tasks = []
            for task in db.collection("top3").stream():
                data = task.to_dict()
                usuario = data.get("usuario")
                primary = usuario[0] if isinstance(usuario, list) else usuario
                if primary in team:
                    tasks.append(task)
        else:
            tasks = list(db.collection("top3").where("usuario", "==", user_code).stream())
        groups = {}
        for task in tasks:
            data = task.to_dict()
            data["id"] = task.id
            usuario = data.get("usuario")
            primary = usuario[0] if isinstance(usuario, list) else usuario
            groups.setdefault(primary, []).append(data)
        status_colors = {"Pendiente": "red", "En proceso": "orange", "Completado": "green"}
        def get_status(selected, custom):
            return custom.strip() if custom and custom.strip() != "" else selected
        for u, t_list in groups.items():
            st.markdown(f"**Usuario: {valid_users.get(u, u)}**")
            for task_data in t_list:
                st.markdown(f"- [TOP 3] {task_data.get('descripcion','(Sin descripción)')}")
                st.write(f"Inicio: {task_data.get('fecha_inicio','')}, Compromiso: {task_data.get('fecha_compromiso','')}, Real: {task_data.get('fecha_real','')}")
                # Calcular indicador delayed automáticamente
                compromiso = task_data.get("fecha_compromiso", None)
                if compromiso:
                    comp_date = datetime.strptime(compromiso, "%Y-%m-%d").date()
                    delay_indicator = "Delayed" if comp_date < date.today() else "On time"
                else:
                    delay_indicator = "N/A"
                current_usuario = task_data.get("usuario", "")
                if user_code in TL_USERS:
                    new_usuario = st.selectbox("Modificar usuario", options=list(get_team_for_tl(current_usuario)), 
                                                index=list(get_team_for_tl(current_usuario)).index(current_usuario),
                                                key=f"mod_usuario_top3_{task_data.get('id')}")
                    if new_usuario != current_usuario:
                        db.collection("top3").document(task_data.get("id")).update({"usuario": new_usuario})
                        st.success("Usuario actualizado.")
                origen_field = task_data.get("origen", None)
                if origen_field:
                    st.markdown(f"**Usuario:** {valid_users.get(current_usuario, current_usuario)} (Colaborador) - Creado por: {valid_users.get(origen_field, origen_field)}")
                else:
                    st.markdown(f"**Usuario:** {valid_users.get(current_usuario, current_usuario)}")
                st.markdown(f"**Status:** <span style='color:{status_colors.get(task_data.get('status',''), 'black')};'>{task_data.get('status','')}</span> - <strong>{delay_indicator}</strong>", unsafe_allow_html=True)
                edit_key = f"edit_top3_{task_data.get('id')}"
                if st.session_state.get(edit_key, False):
                    new_status = st.selectbox("Nuevo status", ["Pendiente", "En proceso", "Completado"], key=f"top3_status_{task_data.get('id')}")
                    custom_status = st.text_input("Status personalizado (opcional)", key=f"top3_custom_{task_data.get('id')}")
                    if st.button("Guardar cambios", key=f"save_top3_{task_data.get('id')}"):
                        final_status = get_status(new_status, custom_status)
                        compromiso = task_data.get("fecha_compromiso", "")
                        if compromiso:
                            comp_date = datetime.strptime(compromiso, "%Y-%m-%d").date()
                            time_label = "On time" if comp_date >= date.today() else "Delayed"
                        else:
                            time_label = "N/A"
                        fecha_real = datetime.now().strftime("%Y-%m-%d") if final_status.lower() == "completado" else task_data.get("fecha_real", "")
                        db.collection("top3").document(task_data.get("id")).update({
                            "status": final_status,
                            "fecha_real": fecha_real,
                            "time_label": time_label
                        })
                        st.success("Status actualizado.")
                        st.session_state[edit_key] = False
                else:
                    if st.button("Editar status", key=f"edit_btn_top3_{task_data.get('id')}"):
                        st.session_state[edit_key] = True
                if st.button("🗑️ Eliminar", key=f"delete_top3_{task_data.get('id')}"):
                    group_id = task_data.get("group_id")
                    if group_id:
                        delete_task_group("top3", group_id)
                    else:
                        db.collection("top3").document(task_data.get("id")).delete()
                    st.success("Tarea eliminada.")
                st.markdown("---")
        if st.button("➕ Agregar Tarea de Top 3"):
            st.session_state.show_top3_form = True
        if st.session_state.get("show_top3_form"):
            with st.form("top3_add_form"):
                st.markdown("### Nueva Tarea - Top 3")
                selected_activity = st.selectbox("Selecciona actividad predefinida (opcional)", [""] + activity_repo)
                p = selected_activity if selected_activity != "" else st.text_input("Descripción")
                ti = st.date_input("Fecha de inicio")
                tc = st.date_input("Fecha compromiso")
                s = st.selectbox("Status", ["Pendiente", "En proceso", "Completado"], key="top3_new_status")
                custom_status = st.text_input("Status personalizado (opcional)", key="top3_new_custom")
                
                # Opción de equipo: "IC TEAM", "FA TEAM" o "GL TEAM"
                team_options = ["IC TEAM", "FA TEAM", "GL TEAM"]
                if user_code in group_ic:
                    base_collab = list(group_ic - {user_code})
                elif user_code in group_fa:
                    base_collab = list(group_fa - {user_code})
                else:
                    base_collab = list(group_namer.union(group_latam) - {user_code})
                all_collab_options = base_collab + team_options
                
                colaboradores = st.multiselect("Colaboradores (opcional)", 
                                               options=all_collab_options,
                                               format_func=lambda x: valid_users.get(x, x) if x in valid_users else x)
                privado = st.checkbox("Marcar como privado")
                submit_new_top3 = st.form_submit_button("Guardar tarea")
            if submit_new_top3:
                final_status = get_status(s, custom_status)
                fecha_real = datetime.now().strftime("%Y-%m-%d") if final_status.lower() == "completado" else ""
                group_id = str(uuid.uuid4()) if colaboradores else None
                
                # Expandir los TEAM: si se selecciona "IC TEAM", "FA TEAM" o "GL TEAM"
                final_collaborators = []
                for c in colaboradores:
                    if c == "IC TEAM":
                        final_collaborators.extend(list(group_ic - {user_code}))
                    elif c == "FA TEAM":
                        final_collaborators.extend(list(group_fa - {user_code}))
                    elif c == "GL TEAM":
                        final_collaborators.extend(list(group_namer.union(group_latam) - {user_code}))
                    else:
                        final_collaborators.append(c)
                final_collaborators = list(set(final_collaborators))
                
                data = {
                    "usuario": user_code,
                    "descripcion": p,
                    "fecha_inicio": ti.strftime("%Y-%m-%d"),
                    "fecha_compromiso": tc.strftime("%Y-%m-%d"),
                    "fecha_real": fecha_real,
                    "status": final_status,
                    "privado": privado,
                    "timestamp": datetime.now(),
                    "group_id": group_id
                }
                db.collection("top3").add(data)
                if final_collaborators:
                    for collab in final_collaborators:
                        data_collab = data.copy()
                        data_collab["usuario"] = collab
                        data_collab["origen"] = user_code
                        db.collection("top3").add(data_collab)
                st.success("Tarea de Top 3 guardada.")
                st.session_state.show_top3_form = False

    # ------------------- Action Board -------------------
    elif menu_choice == "Action Board":
        st.subheader("✅ Acciones y Seguimiento - Resumen")
        if user_code in TL_USERS:
            team = get_team_for_tl(user_code)
            actions = []
            for action in db.collection("actions").stream():
                data = action.to_dict()
                usuario = data.get("usuario")
                primary = usuario[0] if isinstance(usuario, list) else usuario
                if primary in team:
                    actions.append(action)
        else:
            actions = list(db.collection("actions").where("usuario", "==", user_code).stream())
        groups_actions = {}
        for action in actions:
            data = action.to_dict()
            data["id"] = action.id
            usuario = data.get("usuario")
            primary = usuario[0] if isinstance(usuario, list) else usuario
            groups_actions.setdefault(primary, []).append(data)
        status_colors = {"Pendiente": "red", "En proceso": "orange", "Completado": "green"}
        def get_status(selected, custom):
            return custom.strip() if custom and custom.strip() != "" else selected
        for u, acts in groups_actions.items():
            st.markdown(f"**Usuario: {valid_users.get(u, u)}**")
            for act_data in acts:
                st.markdown(f"- [Action Board] {act_data.get('accion','(Sin descripción)')}")
                st.write(f"Inicio: {act_data.get('fecha_inicio','')}, Compromiso: {act_data.get('fecha_compromiso','')}, Real: {act_data.get('fecha_real','')}")
                # Calcular indicador delayed automáticamente
                compromiso = act_data.get("fecha_compromiso", None)
                if compromiso:
                    comp_date = datetime.strptime(compromiso, "%Y-%m-%d").date()
                    delay_indicator = "Delayed" if comp_date < date.today() else "On time"
                else:
                    delay_indicator = "N/A"
                current_usuario = act_data.get("usuario", "")
                if user_code in TL_USERS:
                    new_usuario = st.selectbox("Modificar usuario", options=list(get_team_for_tl(current_usuario)), 
                                                index=list(get_team_for_tl(current_usuario)).index(current_usuario),
                                                key=f"mod_usuario_action_{act_data.get('id')}")
                    if new_usuario != current_usuario:
                        db.collection("actions").document(act_data.get("id")).update({"usuario": new_usuario})
                        st.success("Usuario actualizado.")
                origen_field = act_data.get("origen", None)
                if origen_field:
                    st.markdown(f"**Usuario:** {valid_users.get(current_usuario, current_usuario)} (Colaborador) - Creado por: {valid_users.get(origen_field, origen_field)}")
                else:
                    st.markdown(f"**Usuario:** {valid_users.get(current_usuario, current_usuario)}")
                st.markdown(f"**Status:** <span style='color:{status_colors.get(act_data.get('status',''), 'black')};'>{act_data.get('status','')}</span> - <strong>{delay_indicator}</strong>", unsafe_allow_html=True)
                edit_key = f"edit_action_{act_data.get('id')}"
                if st.session_state.get(edit_key, False):
                    new_status = st.selectbox("Nuevo status", ["Pendiente", "En proceso", "Completado"], key=f"action_status_{act_data.get('id')}")
                    custom_status = st.text_input("Status personalizado (opcional)", key=f"action_custom_{act_data.get('id')}")
                    if st.button("Guardar cambios", key=f"save_action_{act_data.get('id')}"):
                        final_status = get_status(new_status, custom_status)
                        compromiso = act_data.get("fecha_compromiso", "")
                        if compromiso:
                            comp_date = datetime.strptime(compromiso, "%Y-%m-%d").date()
                            time_label = "On time" if comp_date >= date.today() else "Delayed"
                        else:
                            time_label = "N/A"
                        fecha_real = datetime.now().strftime("%Y-%m-%d") if final_status.lower() == "completado" else act_data.get("fecha_real", "")
                        db.collection("actions").document(act_data.get("id")).update({
                            "status": final_status,
                            "fecha_real": fecha_real,
                            "time_label": time_label
                        })
                        st.success("Status actualizado.")
                        st.session_state[edit_key] = False
                else:
                    if st.button("Editar status", key=f"edit_btn_action_{act_data.get('id')}"):
                        st.session_state[edit_key] = True
                if st.button("🗑️ Eliminar", key=f"delete_action_{act_data.get('id')}"):
                    group_id = act_data.get("group_id")
                    if group_id:
                        delete_task_group("actions", group_id)
                    else:
                        db.collection("actions").document(act_data.get("id")).delete()
                    st.success("Acción eliminada.")
                if st.button("Enviar a Top3", key=f"send_to_top3_{act_data.get('id')}"):
                    send_action_to_top3(db.collection("actions").document(act_data.get("id")))
                st.markdown("---")
        if st.button("➕ Agregar Acción"):
            st.session_state.show_action_form = True
        if st.session_state.get("show_action_form"):
            with st.form("action_add_form"):
                st.markdown("### Nueva Acción")
                accion = st.text_input("Descripción de la acción")
                ti = st.date_input("Fecha de inicio")
                tc = st.date_input("Fecha compromiso")
                s = st.selectbox("Status", ["Pendiente", "En proceso", "Completado"], key="action_new_status")
                custom_status = st.text_input("Status personalizado (opcional)", key="action_new_custom")
                
                # Opción de equipo para colaboradores: "IC TEAM", "FA TEAM" o "GL TEAM"
                team_options = ["IC TEAM", "FA TEAM", "GL TEAM"]
                if user_code in group_ic:
                    base_collab = list(group_ic - {user_code})
                elif user_code in group_fa:
                    base_collab = list(group_fa - {user_code})
                else:
                    base_collab = list(group_namer.union(group_latam) - {user_code})
                all_collab_options = base_collab + team_options
                
                colaboradores = st.multiselect("Colaboradores (opcional)", 
                                                 options=all_collab_options,
                                                 format_func=lambda x: valid_users.get(x, x) if x in valid_users else x)
                privado = st.checkbox("Marcar como privado")
                submit_new_action = st.form_submit_button("Guardar acción")
            if submit_new_action:
                final_status = get_status(s, custom_status)
                fecha_real = datetime.now().strftime("%Y-%m-%d") if final_status.lower() == "completado" else ""
                group_id = str(uuid.uuid4()) if colaboradores else None
                
                # Expandir TEAM: si se selecciona "IC TEAM", "FA TEAM" o "GL TEAM", se añaden todos los miembros del grupo
                final_collaborators = []
                for c in colaboradores:
                    if c == "IC TEAM":
                        final_collaborators.extend(list(group_ic - {user_code}))
                    elif c == "FA TEAM":
                        final_collaborators.extend(list(group_fa - {user_code}))
                    elif c == "GL TEAM":
                        final_collaborators.extend(list(group_namer.union(group_latam) - {user_code}))
                    else:
                        final_collaborators.append(c)
                final_collaborators = list(set(final_collaborators))
                
                data = {
                    "usuario": user_code,
                    "accion": accion,
                    "fecha_inicio": ti.strftime("%Y-%m-%d"),
                    "fecha_compromiso": tc.strftime("%Y-%m-%d"),
                    "fecha_real": fecha_real,
                    "status": final_status,
                    "privado": privado,
                    "timestamp": datetime.now(),
                    "group_id": group_id
                }
                db.collection("actions").add(data)
                
                if final_collaborators:
                    for collab in final_collaborators:
                        data_collab = data.copy()
                        data_collab["usuario"] = collab
                        data_collab["origen"] = user_code
                        db.collection("actions").add(data_collab)
                st.success("Acción guardada.")
                st.session_state.show_action_form = False

    # ------------------- Escalation -------------------
    elif menu_choice == "Escalation":
        st.subheader("⚠️ Escalation")
        escalador = user_code
        common_options = {"MLOPEZ", "GMAYORAL", "LARANDA"}
        if user_code in group_fa:
            additional = {"ABARRERA"}
        elif user_code in group_ic:
            additional = {"YAEL"}
        elif user_code in (group_namer.union(group_latam)):
            additional = {"MSANCHEZ"}
        elif user_code in group_wor:
            additional = set()
        else:
            additional = set()
        para_quien_options = sorted(list(common_options.union(additional)))
        para_quien = st.selectbox("¿Para quién?", para_quien_options, format_func=lambda x: f"{valid_users.get(x, x)} ({x})")
        with st.form("escalation_form"):
            razon = st.text_area("Razón")
            con_quien = st.multiselect("¿Con quién se tiene el tema?", options=[code for code in valid_users if code != escalador],
                                         format_func=lambda x: f"{valid_users.get(x, x)} ({x})")
            submit_escalation = st.form_submit_button("Enviar escalación")
        if submit_escalation:
            involucrados = [escalador, para_quien]
            if con_quien:
                involucrados.extend(con_quien)
            involucrados = list(set(involucrados))
            escalacion_data = {
                "escalador": escalador,
                "razon": razon,
                "para_quien": para_quien,
                "con_quien": con_quien,
                "involucrados": involucrados,
                "fecha": datetime.now().strftime("%Y-%m-%d")
            }
            db.collection("escalations").add(escalacion_data)
            st.success("Escalación registrada.")
            st.warning(f"Notificación: Se ha enviado un escalation a {valid_users.get(para_quien, para_quien)}.")
        st.markdown("### Escalaciones en las que estás involucrado")
        escalations = list(db.collection("escalations").stream())
        count = 0
        for esc in escalations:
            esc_data = esc.to_dict()
            if user_code in esc_data.get("involucrados", []):
                count += 1
                st.markdown(f"**Escalación:** {esc_data.get('razon','(Sin razón)')}")
                st.write(f"Escalador: {esc_data.get('escalador','')}, Para quién: {esc_data.get('para_quien','')}, Con quién: {esc_data.get('con_quien','')}")
                st.write(f"Fecha: {esc_data.get('fecha','')}")
                st.warning("¡Estás involucrado en esta escalación!")
                st.markdown("---")
        if count == 0:
            st.info("No tienes escalaciones asignadas.")
    
    # ------------------- Recognition -------------------
    elif menu_choice == "Recognition":
        if user_code not in TL_USERS:
            st.subheader("Reconocimientos otorgados")
            recs = [doc.to_dict() for doc in db.collection("recognitions").stream() if doc.to_dict().get("destinatario") == user_code]
            if recs:
                for rec in recs:
                    st.markdown(f"**De:** {valid_users.get(rec.get('usuario'), rec.get('usuario'))}  |  **Asunto:** {rec.get('asunto','')}")
                    st.write(f"Mensaje: {rec.get('mensaje','')}")
                    st.write(f"Fecha: {rec.get('fecha','')}")
                    st.markdown("---")
            else:
                st.info("No has recibido reconocimientos.")
            with st.form("recognition_form"):
                st.markdown("**Enviar Reconocimiento**")
                st.markdown(f"**De:** {valid_users[user_code]} ({user_code})")
                destinatario = st.selectbox("Para:", [code for code in valid_users if code != user_code],
                                              format_func=lambda x: f"{valid_users[x]} ({x})")
                jefe_directo = get_direct_boss(destinatario)
                st.markdown(f"**Jefe Directo:** {valid_users.get(jefe_directo, jefe_directo)} ({jefe_directo})")
                kudo_options = [
                    "Great Job! – ¡Excelente trabajo!",
                    "Well Done! – ¡Bien hecho!",
                    "Outstanding! – ¡Sobresaliente!",
                    "Keep it up! – ¡Sigue así!"
                ]
                kudo_card = st.selectbox("Kudo Card:", kudo_options)
                subject = st.text_input("Asunto:", value="Kudo Card de Daily Huddle")
                mensaje = st.text_area("Mensaje:")
                submit_recognition = st.form_submit_button("Enviar Reconocimiento")
            if submit_recognition:
                body = f"KUDO CARD: {kudo_card}\n\n{mensaje}"
                recognition_data = {
                    "usuario": user_code,
                    "destinatario": destinatario,
                    "jefe_directo": jefe_directo,
                    "asunto": subject,
                    "mensaje": body,
                    "fecha": datetime.now().strftime("%Y-%m-%d")
                }
                db.collection("recognitions").add(recognition_data)
                st.success("Reconocimiento enviado.")
                st.warning(f"Notificación: Se ha enviado un reconocimiento a {valid_users.get(destinatario, destinatario)}.")
        else:
            st.subheader("Reconocimientos de tu equipo")
            team = get_team_for_tl(user_code)
            recs = [doc.to_dict() for doc in db.collection("recognitions").stream() if doc.to_dict().get("destinatario") in team]
            if recs:
                for rec in recs:
                    st.markdown(f"**De:** {valid_users.get(rec.get('usuario'), rec.get('usuario'))}  |  **Para:** {valid_users.get(rec.get('destinatario'), rec.get('destinatario'))}  |  **Asunto:** {rec.get('asunto','')}")
                    st.write(f"Mensaje: {rec.get('mensaje','')}")
                    st.write(f"Fecha: {rec.get('fecha','')}")
                    st.markdown("---")
            else:
                st.info("No hay reconocimientos para mostrar.")
    
    # ------------------- Store DBSCHENKER -------------------
    elif menu_choice == "Store DBSCHENKER":
        st.subheader("🛍️ Store DBSCHENKER")
        st.write("Productos corporativos (prototipo):")
        products = [
            {"name": "Taza DBS", "price": 10, "image": "https://via.placeholder.com/150?text=Taza+DBS"},
            {"name": "Playera DBS", "price": 20, "image": "https://via.placeholder.com/150?text=Playera+DBS"},
            {"name": "Gorra DBS", "price": 15, "image": "https://via.placeholder.com/150?text=Gorra+DBS"}
        ]
        for prod in products:
            st.image(prod["image"], width=150)
            st.markdown(f"**{prod['name']}** - {prod['price']} DB COINS")
            if st.button(f"Comprar {prod['name']}", key=f"buy_{prod['name']}"):
                st.info("Función de compra no implementada.")
            st.markdown("---")
    
    # ------------------- Wallet -------------------
    elif menu_choice == "Wallet":
        st.subheader("💰 Mi Wallet (DB COINS)")
        wallet_ref = db.collection("wallets").document(user_code)
        doc = wallet_ref.get()
        current_coins = 0
        if doc.exists:
            current_coins = doc.to_dict().get("coins", 0)
        st.write(f"**Saldo actual:** {current_coins} DB COINS")
        if user_code == "LARANDA":
            add_coins = st.number_input("Generar DB COINS:", min_value=1, step=1, value=10)
            if st.button("Generar DB COINS"):
                new_balance = current_coins + add_coins
                wallet_ref.set({"coins": new_balance})
                st.success(f"Generados {add_coins} DB COINS. Nuevo saldo: {new_balance}.")
            st.markdown("### Funciones Administrativas")
            admin_key = st.text_input("Clave Admin", type="password")
            if admin_key == "ADMIN123":
                if st.button("Resetear todas las monedas a 0"):
                    for u in valid_users:
                        db.collection("wallets").document(u).set({"coins": 0})
                target = st.selectbox("Generar monedas para el usuario:", list(valid_users.keys()),
                                        format_func=lambda x: f"{valid_users[x]} ({x})")
                amt = st.number_input("Cantidad de DB COINS a generar:", min_value=1, step=1, value=10)
                if st.button("Generar para usuario seleccionado"):
                    target_ref = db.collection("wallets").document(target)
                    doc_target = target_ref.get()
                    current = 0
                    if doc_target.exists:
                        current = doc_target.to_dict().get("coins", 0)
                    target_ref.set({"coins": current + amt})
                    st.success(f"Generados {amt} DB COINS para {valid_users[target]}.")
    
    # ------------------- Communications -------------------
    elif menu_choice == "Communications":
        st.subheader("📢 Mensajes Importantes")
        mensaje = st.text_area("📝 Escribe un mensaje o anuncio")
        if st.button("📩 Enviar mensaje"):
            db.collection("communications").document().set({
                "usuario": user_code,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "mensaje": mensaje
            })
            st.success("Mensaje enviado.")
    
    # ------------------- Calendar -------------------
    elif menu_choice == "Calendar":
        st.subheader("📅 Calendario")
        cal_option = st.radio("Selecciona una opción", ["Crear Evento", "Ver Calendario"])
        if cal_option == "Crear Evento":
            st.markdown("### Crear Evento")
            evento = st.text_input("📌 Nombre del evento")
            start_date, end_date = st.date_input("Selecciona el rango de fechas", value=(date.today(), date.today()))
            tipo_evento = st.radio("Tipo de evento", ["Público", "Privado"])
            if st.button("✅ Agendar evento"):
                event_data = {
                    "usuario": user_code,
                    "evento": evento,
                    "fecha": start_date.strftime("%Y-%m-%d"),
                    "fecha_fin": end_date.strftime("%Y-%m-%d"),
                    "publico": True if tipo_evento == "Público" else False
                }
                db.collection("calendar").document().set(event_data)
                st.success("Evento agendado.")
        else:
            st.markdown("### Ver Calendario")
            start_date, end_date = st.date_input("Selecciona el rango de fechas para ver eventos", value=(date.today(), date.today()))
            events = []
            for doc in db.collection("calendar").stream():
                data = doc.to_dict()
                if data.get("fecha"):
                    event_date = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
                    if start_date <= event_date <= end_date:
                        title = data.get("evento", "Evento")
                        if not data.get("publico", False):
                            title += f" (Privado - {data.get('usuario','')})"
                        events.append({
                            "title": title,
                            "start": data.get("fecha")
                        })
            events_json = json.dumps(events)
            calendar_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset='utf-8' />
              <link href='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.css' rel='stylesheet' />
              <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js'></script>
              <style>
                body {{
                  margin: 0;
                  padding: 0;
                }}
                #calendar {{
                  max-width: 900px;
                  margin: 40px auto;
                }}
              </style>
            </head>
            <body>
              <div id='calendar'></div>
              <script>
                document.addEventListener('DOMContentLoaded', function() {{
                  var calendarEl = document.getElementById('calendar');
                  var calendar = new FullCalendar.Calendar(calendarEl, {{
                    initialView: 'dayGridMonth',
                    events: {events_json}
                  }});
                  calendar.render();
                }});
              </script>
            </body>
            </html>
            """
            components.html(calendar_html, height=600, scrolling=True)
    
    # ------------------- Consultorio Optimizacion -------------------
    elif menu_choice == "Consultorio Optimizacion":
        st.subheader("Consultorio de Optimización")
        st.markdown("Envía un archivo y/o un mensaje para requerir apoyo. Esto se enviará a **CNAPOLES**.")
        with st.form("consultorio_form"):
            mensaje_consult = st.text_area("Describe tu requerimiento o tarea:")
            archivo = st.file_uploader("Adjuntar archivo (opcional)")
            submit_consult = st.form_submit_button("Enviar Consulta")
        if submit_consult:
            data_consult = {
                "usuario": user_code,
                "mensaje": mensaje_consult,
                "archivo": archivo.name if archivo is not None else None,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "destinatario": "CNAPOLES"
            }
            db.collection("consultorio").add(data_consult)
            st.success("Consulta enviada a CNAPOLES.")
    
    # ------------------- Contacto -------------------
    elif menu_choice == "Contacto":
        st.subheader("Contacto / Reporte de Problemas")
        st.markdown("Si tienes algún problema con la aplicación, por favor envía tu reporte aquí.")
        with st.form("contacto_form"):
            asunto_contact = st.text_input("Asunto:")
            mensaje_contact = st.text_area("Describe tu problema o sugerencia:")
            submit_contact = st.form_submit_button("Enviar Reporte")
        if submit_contact:
            data_contact = {
                "usuario": user_code,
                "asunto": asunto_contact,
                "mensaje": mensaje_contact,
                "fecha": datetime.now().strftime("%Y-%m-%d")
            }
            db.collection("contacto").add(data_contact)
            st.success("Reporte enviado. Gracias por tu feedback.")
    
    # ------------------- Roles -------------------
    elif menu_choice == "Roles":
        if user_code in {"ALECCION", "WORLEAD", "R2RGRAL", "FALEAD", "ICLEAD"}:
            st.subheader("📝 Asignación de Roles Semanal")
            if st.button("Asignar Roles"):
                if user_code == "ALECCION":
                    posibles = [code for code in valid_users if code not in {"ALECCION", "WORLEAD", "LARANDA", "R2RGRAL", "FALEAD", "ICLEAD", "KPI"}]
                elif user_code == "WORLEAD":
                    posibles = [code for code in valid_users if code not in {"WORLEAD", "ALECCION", "LARANDA", "R2RGRAL", "FALEAD", "ICLEAD", "KPI"} and code in group_wor]
                elif user_code == "R2RGRAL":
                    posibles = [code for code in valid_users if code not in {"R2RGRAL", "ALECCION", "WORLEAD", "LARANDA", "FALEAD", "ICLEAD", "KPI"} and code in group_r2r_gral]
                elif user_code == "FALEAD":
                    posibles = [code for code in valid_users if code not in {"FALEAD", "ALECCION", "WORLEAD", "LARANDA", "R2RGRAL", "ICLEAD", "KPI"} and code in group_fa]
                elif user_code == "ICLEAD":
                    posibles = [code for code in valid_users if code not in {"ICLEAD", "ALECCION", "WORLEAD", "LARANDA", "R2RGRAL", "FALEAD", "KPI"} and code in group_ic]
                roles_asignados = random.sample(possibles, 3) if user_code in {"ALECCION", "WORLEAD", "ICLEAD"} else random.sample(possibles, 2)
                st.session_state["roles"] = {
                    "Timekeeper": roles_asignados[0],
                    "ActionTaker": roles_asignados[1],
                    "Coach": roles_asignados[2] if len(roles_asignados) == 3 else None
                }
                st.json(st.session_state["roles"])
        else:
            st.error("Acceso denegado. Esta opción es exclusiva para los TL.")
    
    # ------------------- Compliance -------------------
    elif menu_choice == "Compliance":
        if user_code in {"ALECCION", "WORLEAD", "R2RGRAL", "FALEAD", "ICLEAD"} or ("roles" in st.session_state and st.session_state["roles"].get("Coach") == user_code):
            st.subheader("📝 Compliance - Feedback")
            feedback_options = [code for code in valid_users if code != user_code]
            target_user = st.selectbox("Dar feedback a:", feedback_options, format_func=lambda x: f"{valid_users.get(x, x)} ({x})")
            feedback = st.text_area("Feedback:")
            if st.button("Enviar Feedback"):
                db.collection("compliance").add({
                    "from": user_code,
                    "to": target_user,
                    "feedback": feedback,
                    "fecha": datetime.now().strftime("%Y-%m-%d")
                })
                st.success("Feedback enviado.")
        else:
            st.error("Acceso denegado. Esta opción es exclusiva para los TL o el Coach.")
    
    # ------------------- Todas las Tareas (solo para TL) -------------------
    elif menu_choice == "Todas las Tareas":
        if user_code not in TL_USERS:
            st.error("Esta opción es exclusiva para perfiles de Team Lead.")
        else:
            st.subheader("🗂️ Todas las Tareas")
            st.markdown("### Tareas TOP3")
            tasks_top3 = [task for task in db.collection("top3").stream() 
                          if (task.to_dict().get("usuario")[0] if isinstance(task.to_dict().get("usuario"), list)
                              else task.to_dict().get("usuario")) in get_team_for_tl(user_code)]
            if tasks_top3:
                for task in tasks_top3:
                    task_data = task.to_dict()
                    st.markdown(f"**[TOP 3] {task_data.get('descripcion','(Sin descripción)')}**")
                    st.write(f"Inicio: {task_data.get('fecha_inicio','')}, Compromiso: {task_data.get('fecha_compromiso','')}, Real: {task_data.get('fecha_real','')}")
                    compromiso = task_data.get("fecha_compromiso", None)
                    if compromiso:
                        comp_date = datetime.strptime(compromiso, "%Y-%m-%d").date()
                        delay_indicator = "Delayed" if comp_date < date.today() else "On time"
                    else:
                        delay_indicator = "N/A"
                    current_usuario = task_data.get("usuario", "")
                    if user_code in TL_USERS:
                        new_usuario = st.selectbox("Modificar usuario", options=list(get_team_for_tl(current_usuario)), 
                                                    index=list(get_team_for_tl(current_usuario)).index(current_usuario),
                                                    key=f"mod_usuario_top3_{task_data.get('id')}")
                        if new_usuario != current_usuario:
                            db.collection("top3").document(task_data.get("id")).update({"usuario": new_usuario})
                            st.success("Usuario actualizado.")
                    origen_field = task_data.get("origen", None)
                    if origen_field:
                        st.markdown(f"**Usuario:** {valid_users.get(current_usuario, current_usuario)} (Colaborador) - Creado por: {valid_users.get(origen_field, origen_field)}")
                    else:
                        st.markdown(f"**Usuario:** {valid_users.get(current_usuario, current_usuario)}")
                    st.markdown(f"**Status:** <span style='color:{status_colors.get(task_data.get('status',''), 'black')};'>{task_data.get('status','')}</span> - <strong>{delay_indicator}</strong>", unsafe_allow_html=True)
                    edit_key = f"edit_top3_{task_data.get('id')}"
                    if st.session_state.get(edit_key, False):
                        new_status = st.selectbox("Nuevo status", ["Pendiente", "En proceso", "Completado"], key=f"top3_status_{task_data.get('id')}")
                        custom_status = st.text_input("Status personalizado (opcional)", key=f"top3_custom_{task_data.get('id')}")
                        if st.button("Guardar cambios", key=f"save_top3_{task_data.get('id')}"):
                            final_status = get_status(new_status, custom_status)
                            compromiso = task_data.get("fecha_compromiso", "")
                            if compromiso:
                                comp_date = datetime.strptime(compromiso, "%Y-%m-%d").date()
                                time_label = "On time" if comp_date >= date.today() else "Delayed"
                            else:
                                time_label = "N/A"
                            fecha_real = datetime.now().strftime("%Y-%m-%d") if final_status.lower() == "completado" else task_data.get("fecha_real", "")
                            db.collection("top3").document(task_data.get("id")).update({
                                "status": final_status,
                                "fecha_real": fecha_real,
                                "time_label": time_label
                            })
                            st.success("Status actualizado.")
                            st.session_state[edit_key] = False
                    else:
                        if st.button("Editar status", key=f"edit_btn_top3_{task_data.get('id')}"):
                            st.session_state[edit_key] = True
                    if st.button("🗑️ Eliminar", key=f"delete_top3_{task_data.get('id')}"):
                        group_id = task_data.get("group_id")
                        if group_id:
                            delete_task_group("top3", group_id)
                        else:
                            db.collection("top3").document(task_data.get("id")).delete()
                        st.success("Tarea eliminada.")
                    st.markdown("---")
            else:
                st.info("No hay tareas TOP3 asignadas.")
            
            st.markdown("### Tareas Action Board")
            tasks_actions = [action for action in db.collection("actions").stream() 
                             if (action.to_dict().get("usuario")[0] if isinstance(action.to_dict().get("usuario"), list)
                                 else action.to_dict().get("usuario")) in get_team_for_tl(user_code)]
            if tasks_actions:
                for action in tasks_actions:
                    action_data = action.to_dict()
                    st.markdown(f"**[Action Board] {action_data.get('accion','(Sin descripción)')}**")
                    st.write(f"Inicio: {action_data.get('fecha_inicio','')}, Compromiso: {action_data.get('fecha_compromiso','')}, Real: {action_data.get('fecha_real','')}")
                    compromiso = action_data.get("fecha_compromiso", None)
                    if compromiso:
                        comp_date = datetime.strptime(compromiso, "%Y-%m-%d").date()
                        delay_indicator = "Delayed" if comp_date < date.today() else "On time"
                    else:
                        delay_indicator = "N/A"
                    current_usuario = action_data.get("usuario", "")
                    if user_code in TL_USERS:
                        new_usuario = st.selectbox("Modificar usuario", options=list(get_team_for_tl(current_usuario)), 
                                                    index=list(get_team_for_tl(current_usuario)).index(current_usuario),
                                                    key=f"mod_usuario_action_{action_data.get('id')}")
                        if new_usuario != current_usuario:
                            db.collection("actions").document(action_data.get("id")).update({"usuario": new_usuario})
                            st.success("Usuario actualizado.")
                    origen_field = action_data.get("origen", None)
                    if origen_field:
                        st.markdown(f"**Usuario:** {valid_users.get(current_usuario, current_usuario)} (Colaborador) - Creado por: {valid_users.get(origen_field, origen_field)}")
                    else:
                        st.markdown(f"**Usuario:** {valid_users.get(current_usuario, current_usuario)}")
                    st.markdown(f"**Status:** <span style='color:{status_colors.get(action_data.get('status',''), 'black')};'>{action_data.get('status','')}</span> - <strong>{delay_indicator}</strong>", unsafe_allow_html=True)
                    edit_key = f"edit_action_{action_data.get('id')}"
                    if st.session_state.get(edit_key, False):
                        new_status = st.selectbox("Nuevo status", ["Pendiente", "En proceso", "Completado"], key=f"action_status_{action_data.get('id')}")
                        custom_status = st.text_input("Status personalizado (opcional)", key=f"action_custom_{action_data.get('id')}")
                        if st.button("Guardar cambios", key=f"save_action_{action_data.get('id')}"):
                            final_status = get_status(new_status, custom_status)
                            compromiso = action_data.get("fecha_compromiso", "")
                            if compromiso:
                                comp_date = datetime.strptime(compromiso, "%Y-%m-%d").date()
                                time_label = "On time" if comp_date >= date.today() else "Delayed"
                            else:
                                time_label = "N/A"
                            fecha_real = datetime.now().strftime("%Y-%m-%d") if final_status.lower() == "completado" else action_data.get("fecha_real", "")
                            db.collection("actions").document(action_data.get("id")).update({
                                "status": final_status,
                                "fecha_real": fecha_real,
                                "time_label": time_label
                            })
                            st.success("Status actualizado.")
                            st.session_state[edit_key] = False
                    else:
                        if st.button("Editar status", key=f"edit_btn_action_{action_data.get('id')}"):
                            st.session_state[edit_key] = True
                    if st.button("🗑️ Eliminar", key=f"delete_action_{action_data.get('id')}"):
                        group_id = action_data.get("group_id")
                        if group_id:
                            delete_task_group("actions", group_id)
                        else:
                            db.collection("actions").document(action_data.get("id")).delete()
                        st.success("Acción eliminada.")
                    if st.button("Enviar a Top3", key=f"send_to_top3_{action_data.get('id')}"):
                        send_action_to_top3(db.collection("actions").document(action_data.get("id")))
                    st.markdown("---")
            else:
                st.info("No hay tareas Action Board asignadas.")
    
    # ------------------- Store DBSCHENKER -------------------
    elif menu_choice == "Store DBSCHENKER":
        st.subheader("🛍️ Store DBSCHENKER")
        st.write("Productos corporativos (prototipo):")
        products = [
            {"name": "Taza DBS", "price": 10, "image": "https://via.placeholder.com/150?text=Taza+DBS"},
            {"name": "Playera DBS", "price": 20, "image": "https://via.placeholder.com/150?text=Playera+DBS"},
            {"name": "Gorra DBS", "price": 15, "image": "https://via.placeholder.com/150?text=Gorra+DBS"}
        ]
        for prod in products:
            st.image(prod["image"], width=150)
            st.markdown(f"**{prod['name']}** - {prod['price']} DB COINS")
            if st.button(f"Comprar {prod['name']}", key=f"buy_{prod['name']}"):
                st.info("Función de compra no implementada.")
            st.markdown("---")
    
    # ------------------- Wallet -------------------
    elif menu_choice == "Wallet":
        st.subheader("💰 Mi Wallet (DB COINS)")
        wallet_ref = db.collection("wallets").document(user_code)
        doc = wallet_ref.get()
        current_coins = 0
        if doc.exists:
            current_coins = doc.to_dict().get("coins", 0)
        st.write(f"**Saldo actual:** {current_coins} DB COINS")
        if user_code == "LARANDA":
            add_coins = st.number_input("Generar DB COINS:", min_value=1, step=1, value=10)
            if st.button("Generar DB COINS"):
                new_balance = current_coins + add_coins
                wallet_ref.set({"coins": new_balance})
                st.success(f"Generados {add_coins} DB COINS. Nuevo saldo: {new_balance}.")
            st.markdown("### Funciones Administrativas")
            admin_key = st.text_input("Clave Admin", type="password")
            if admin_key == "ADMIN123":
                if st.button("Resetear todas las monedas a 0"):
                    for u in valid_users:
                        db.collection("wallets").document(u).set({"coins": 0})
                target = st.selectbox("Generar monedas para el usuario:", list(valid_users.keys()),
                                        format_func=lambda x: f"{valid_users[x]} ({x})")
                amt = st.number_input("Cantidad de DB COINS a generar:", min_value=1, step=1, value=10)
                if st.button("Generar para usuario seleccionado"):
                    target_ref = db.collection("wallets").document(target)
                    doc_target = target_ref.get()
                    current = 0
                    if doc_target.exists:
                        current = doc_target.to_dict().get("coins", 0)
                    target_ref.set({"coins": current + amt})
                    st.success(f"Generados {amt} DB COINS para {valid_users[target]}.")
    
    # ------------------- Communications -------------------
    elif menu_choice == "Communications":
        st.subheader("📢 Mensajes Importantes")
        mensaje = st.text_area("📝 Escribe un mensaje o anuncio")
        if st.button("📩 Enviar mensaje"):
            db.collection("communications").document().set({
                "usuario": user_code,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "mensaje": mensaje
            })
            st.success("Mensaje enviado.")
    
    # ------------------- Calendar -------------------
    elif menu_choice == "Calendar":
        st.subheader("📅 Calendario")
        cal_option = st.radio("Selecciona una opción", ["Crear Evento", "Ver Calendario"])
        if cal_option == "Crear Evento":
            st.markdown("### Crear Evento")
            evento = st.text_input("📌 Nombre del evento")
            start_date, end_date = st.date_input("Selecciona el rango de fechas", value=(date.today(), date.today()))
            tipo_evento = st.radio("Tipo de evento", ["Público", "Privado"])
            if st.button("✅ Agendar evento"):
                event_data = {
                    "usuario": user_code,
                    "evento": evento,
                    "fecha": start_date.strftime("%Y-%m-%d"),
                    "fecha_fin": end_date.strftime("%Y-%m-%d"),
                    "publico": True if tipo_evento == "Público" else False
                }
                db.collection("calendar").document().set(event_data)
                st.success("Evento agendado.")
        else:
            st.markdown("### Ver Calendario")
            start_date, end_date = st.date_input("Selecciona el rango de fechas para ver eventos", value=(date.today(), date.today()))
            events = []
            for doc in db.collection("calendar").stream():
                data = doc.to_dict()
                if data.get("fecha"):
                    event_date = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
                    if start_date <= event_date <= end_date:
                        title = data.get("evento", "Evento")
                        if not data.get("publico", False):
                            title += f" (Privado - {data.get('usuario','')})"
                        events.append({
                            "title": title,
                            "start": data.get("fecha")
                        })
            events_json = json.dumps(events)
            calendar_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset='utf-8' />
              <link href='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.css' rel='stylesheet' />
              <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js'></script>
              <style>
                body {{
                  margin: 0;
                  padding: 0;
                }}
                #calendar {{
                  max-width: 900px;
                  margin: 40px auto;
                }}
              </style>
            </head>
            <body>
              <div id='calendar'></div>
              <script>
                document.addEventListener('DOMContentLoaded', function() {{
                  var calendarEl = document.getElementById('calendar');
                  var calendar = new FullCalendar.Calendar(calendarEl, {{
                    initialView: 'dayGridMonth',
                    events: {events_json}
                  }});
                  calendar.render();
                }});
              </script>
            </body>
            </html>
            """
            components.html(calendar_html, height=600, scrolling=True)
    
    # ------------------- Consultorio Optimizacion -------------------
    elif menu_choice == "Consultorio Optimizacion":
        st.subheader("Consultorio de Optimización")
        st.markdown("Envía un archivo y/o un mensaje para requerir apoyo. Esto se enviará a **CNAPOLES**.")
        with st.form("consultorio_form"):
            mensaje_consult = st.text_area("Describe tu requerimiento o tarea:")
            archivo = st.file_uploader("Adjuntar archivo (opcional)")
            submit_consult = st.form_submit_button("Enviar Consulta")
        if submit_consult:
            data_consult = {
                "usuario": user_code,
                "mensaje": mensaje_consult,
                "archivo": archivo.name if archivo is not None else None,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
                "destinatario": "CNAPOLES"
            }
            db.collection("consultorio").add(data_consult)
            st.success("Consulta enviada a CNAPOLES.")
    
    # ------------------- Contacto -------------------
    elif menu_choice == "Contacto":
        st.subheader("Contacto / Reporte de Problemas")
        st.markdown("Si tienes algún problema con la aplicación, por favor envía tu reporte aquí.")
        with st.form("contacto_form"):
            asunto_contact = st.text_input("Asunto:")
            mensaje_contact = st.text_area("Describe tu problema o sugerencia:")
            submit_contact = st.form_submit_button("Enviar Reporte")
        if submit_contact:
            data_contact = {
                "usuario": user_code,
                "asunto": asunto_contact,
                "mensaje": mensaje_contact,
                "fecha": datetime.now().strftime("%Y-%m-%d")
            }
            db.collection("contacto").add(data_contact)
            st.success("Reporte enviado. Gracias por tu feedback.")
    
show_main_app()
