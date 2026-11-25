"""Auditoría inmutable encadenada con SHA-256 (archivo .jsonl)."""
import hashlib
import json
import time

from ..config import AUDIT_FILE
from ..state import estado


def registrar_auditoria(evento: dict):
    if int(evento.get("monto", 0)) <= 0:
        return estado.hash_cadena_auditoria

    with estado.lock:
        bloque_previo = estado.hash_cadena_auditoria
        cadena = (
            f"{bloque_previo}|{evento['id_tx']}|{evento['decision']}|"
            f"{evento['puntaje']}|{';'.join(evento['razones'])}"
        )
        hash_actual = hashlib.sha256(cadena.encode("utf-8")).hexdigest()
        estado.hash_cadena_auditoria = hash_actual

        evento["hash_previo"] = bloque_previo[:16]
        evento["hash_actual"] = hash_actual
        evento["hora"] = time.strftime("%H:%M:%S")

        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False) + "\n")
        return hash_actual


def leer_eventos_auditoria():
    eventos = []
    if not AUDIT_FILE.exists():
        return eventos
    with estado.lock:
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            for linea in f:
                try:
                    ev = json.loads(linea)
                    if int(ev.get("monto", 0)) > 0:
                        eventos.append(ev)
                except Exception:
                    continue
    return eventos
