"""Utilidades puras: criptografía, biometría y parseo."""
import hashlib
import hmac
import math

from .config import CLAVE_MAESTRA_HSM


def parsear_entero(valor, defecto=0):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return defecto


def firmar_hmac_imei(cid, imei):
    return hmac.new(
        CLAVE_MAESTRA_HSM, f"{cid}:{imei}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


def calcular_similitud_vectores(v_base, v_actual):
    """Similitud coseno normalizada a 0-100."""
    if not v_base or not v_actual or len(v_base) != len(v_actual):
        return 0
    dot = sum(a * b for a, b in zip(v_base, v_actual))
    norm_a = math.sqrt(sum(a * a for a in v_base))
    norm_b = math.sqrt(sum(b * b for b in v_actual))
    if norm_a == 0 or norm_b == 0:
        return 0
    coseno = dot / (norm_a * norm_b)
    return max(0, min(100, round(((coseno + 1.0) / 2.0) * 100)))
