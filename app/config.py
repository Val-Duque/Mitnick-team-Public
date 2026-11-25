"""Configuración y constantes. Todo lo "ajustable" de la demo vive aquí."""
import os
from pathlib import Path

HOST = os.getenv("MITNICK_HOST", "127.0.0.1")
PORT = int(os.getenv("MITNICK_PORT", "8081"))

# --- Seguridad (en producción vendría de un HSM / gestor de secretos) ---
CLAVE_MAESTRA_HSM = os.getenv(
    "MITNICK_HSM_KEY", "YumaPay_HSM_SecretKey_2026_AES256_SHA256"
).encode("utf-8")

ANALISTAS_AUTORIZADOS = {
    "analista@mitnick.co": {
        "clave": "Mitnick2026",
        "nombre": "Kevin Mitnick (Lead SOC)",
        "rol": "Analista Senior Antifraude",
    },
    "soc@yumapay.co": {
        "clave": "Yuma2026",
        "nombre": "Laura Gómez (SOC Nivel 2)",
        "rol": "Especialista Respuesta a Incidentes",
    },
}

# --- Archivos ---
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = Path(os.getenv("MITNICK_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_FILE = DATA_DIR / "auditoria_inmutable_sha256.jsonl"
BOVEDA_FILE = DATA_DIR / "boveda_rostros_yuma.json"
RUTAS_CLIENTES_CSV = [
    DATA_DIR / "clientes.csv",
    BASE_DIR / "Usuario" / "clientes.csv",
    BASE_DIR / "clientes.csv",
    BASE_DIR / "03_Datos" / "clientes.csv",
]

# --- Reglas del motor antifraude ---
TOPE_POR_OPERACION = 2_000_000
TOPE_DIARIO_CLIENTE = 5_000_000
UMBRAL_MONTO_ALTO = 800_000
UMBRAL_SIMILITUD_FACIAL = 72
UMBRAL_RECHAZO = 0.82   # puntaje >= esto  -> rechazar
UMBRAL_DESAFIO = 0.30   # puntaje >= esto  -> desafiar (push + biometría)

# --- Datos de escala que se muestran en métricas/telemetría ---
ESCALA_RETO = {
    "usuarios_activos": 4_200_000,
    "transacciones_diarias": 1_800_000,
    "tps_promedio_diario": 20.8,
    "capacidad_procesamiento_motor_tps": 1_250,
}
LIMITE_SLA_MS = 300.0

IMEIS_POR_DEFECTO = [
    "358942110482910", "354109882716543", "867530091827364",
    "359012448712309", "352891004728192", "864920118472615",
]
