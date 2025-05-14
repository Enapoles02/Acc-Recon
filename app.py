# ————————————————
# Paso 1: Importación inicial de la base de datos
# ————————————————
accounts_ref = db.collection("accounts")

# Si la colección está vacía, mostramos el formulario de carga
if not accounts_ref.limit(1).get():
    st.title("🚀 Importar base de datos inicial")
    st.write("Carga tu archivo Excel con la lista de cuentas y responsables.")

    uploaded = st.file_uploader("Selecciona el .xlsx", type="xlsx")
    if uploaded and st.button("Importar base"):
        try:
            df = pd.read_excel(uploaded)
            st.write("Columnas encontradas:", df.columns.tolist())
            for _, row in df.iterrows():
                data = row.to_dict()
                account_id = str(data.get("Account", "")).strip()
                if account_id:
                    # Guarda cada fila bajo un documento con ID = Account
                    accounts_ref.document(account_id).set(data)
            st.success("📥 Base importada correctamente. Recarga la página para continuar.")
        except Exception as e:
            st.error(f"Error importando base: {e}")
    # Detenemos la ejecución para que solo se vea esta pantalla
    st.stop()
