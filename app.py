#!/usr/bin/env python3
# debug_simple.py — prueba mínima de conexión a Firestore

import sys
import firebase_admin
from firebase_admin import credentials, firestore

def main():
    try:
        # 1) Asegúrate de tener el JSON en la misma carpeta con este nombre:
        SERVICE_ACCOUNT = 'serviceAccount.json'
        
        # 2) Inicializa la app
        cred = credentials.Certificate(SERVICE_ACCOUNT)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase Admin inicializado correctamente.")
        
        # 3) Instancia cliente de Firestore
        db = firestore.client()
        
        # 4) “Ping” sencillo: intenta leer un doc que no existe
        doc = db.collection('ping_test').document('ping').get()
        print(f"✅ Firestore responde (doc.exists = {doc.exists}). Conexión OK.")
        
    except Exception as e:
        print("❌ Error conectando a Firestore:")
        print(e)
        sys.exit(1)

if __name__ == '__main__':
    main()
