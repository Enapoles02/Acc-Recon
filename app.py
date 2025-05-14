#!/usr/bin/env python3
# debug.py — Verifica la conexión a Firestore con Firebase Admin SDK

import json
import sys

import firebase_admin
from firebase_admin import credentials, firestore

# Ruta a tu JSON de credenciales
SERVICE_ACCOUNT_PATH = 'serviceAccount.json'

def main():
    try:
        # Carga las credenciales
        with open(SERVICE_ACCOUNT_PATH, 'r', encoding='utf-8') as f:
            service_account_info = json.load(f)

        # Inicializa la app de Firebase Admin
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin SDK inicializado correctamente.")

        # Obtiene el cliente de Firestore
        db = firestore.client()

        # Haz una operación sencilla: listar las colecciones de nivel raíz
        print("🔍 Listando colecciones de Firestore:")
        collections = db.collections()
        for coll in collections:
            print(f" • {coll.id}")

        print("🎉 Conexión a Firestore verificada con éxito.")
        sys.exit(0)

    except Exception as e:
        print("❌ Error conectando a Firestore:")
        print(e)
        sys.exit(1)

if __name__ == '__main__':
    main()
