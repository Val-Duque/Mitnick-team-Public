"""Bóveda de usuarios: creación, búsqueda, persistencia y liquidación."""
import csv
import json
import random
import time

from ..config import BOVEDA_FILE, IMEIS_POR_DEFECTO, RUTAS_CLIENTES_CSV
from ..state import estado
from ..utils import firmar_hmac_imei


# ---------- IMEIs ----------
def cargar_pool_imeis_reto():
    pool = []
    archivo_csv = next((r for r in RUTAS_CLIENTES_CSV if r.exists()), None)
    if archivo_csv:
        try:
            with open(archivo_csv, mode="r", encoding="utf-8-sig") as f:
                for fila in csv.DictReader(f):
                    imei = fila.get("imei") or fila.get("id_dispositivo") or fila.get("dispositivo_habitual")
                    if imei and str(imei).strip():
                        pool.append(str(imei).strip())
            print(f"[CSV] Cargados {len(pool)} IMEIs desde: {archivo_csv}")
        except Exception as err:
            print(f"[CSV] No se pudo leer {archivo_csv}: {err}")
    estado.pool_imeis_reto = pool or list(IMEIS_POR_DEFECTO)


def obtener_imei_del_reto(excluir=None):
    candidatos = [i for i in estado.pool_imeis_reto if i != excluir]
    return random.choice(candidatos or estado.pool_imeis_reto)


# ---------- Usuarios ----------
def crear_estructura_usuario(
    cid, nombre, correo, pin, ciudad, saldo, preguntas,
    rostro_enrolado=False, foto_b64="", vector_facial=None,
    hash_rostro="PENDIENTE_CAPTURA_CAMARA",
):
    imei = obtener_imei_del_reto()
    return {
        "id_cliente": cid,
        "nombre": nombre,
        "correo": correo.lower(),
        "pin": pin,
        "ciudad_habitual": ciudad,
        "imei_vinculado": imei,
        "firma_hmac_imei": firmar_hmac_imei(cid, imei),
        "saldo": int(saldo),
        "gastado_hoy": 0,
        "rostro_enrolado": rostro_enrolado,
        "foto_rostro_b64": foto_b64,
        "vector_facial": vector_facial if vector_facial is not None else [],
        "hash_rostro": hash_rostro,
        "preguntas_seguridad": preguntas,
        "cuenta_bloqueada": False,
        "movimientos": [{
            "id_tx": "APERTURA",
            "tipo": "entrada",
            "contraparte": "Abono Inicial Yuma Pay",
            "monto": int(saldo),
            "hora": time.strftime("%H:%M:%S"),
            "fecha": time.strftime("%d/%m/%Y"),
        }],
        "fecha_registro": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def buscar_usuario_por_identificador(identificador):
    ref = str(identificador).strip().lower()
    if not ref:
        return None
    for cid, u in estado.boveda_usuarios.items():
        if cid.lower() == ref or u.get("correo", "").lower() == ref:
            return u
    return None


def buscar_destinatario_interno(destino_texto, excluir_cid=""):
    ref = str(destino_texto).strip().lower()
    if not ref:
        return None
    for cid, u in estado.boveda_usuarios.items():
        if cid == excluir_cid:
            continue
        if cid.lower() == ref or u.get("correo", "").lower() == ref or u.get("nombre", "").strip().lower() == ref:
            return u
    return None


def siguiente_id_cliente():
    n = len(estado.boveda_usuarios) + 1
    while f"C{n:03d}" in estado.boveda_usuarios:
        n += 1
    return f"C{n:03d}"


# ---------- Persistencia ----------
def guardar_boveda():
    with estado.lock:
        with open(BOVEDA_FILE, "w", encoding="utf-8") as f:
            json.dump(estado.boveda_usuarios, f, ensure_ascii=False, indent=2)


# Usuarios demo: (id, nombre, correo, pin, ciudad, saldo, preguntas)
USUARIOS_INICIALES = [
    ("C001", "Carlos Mendoza", "carlos@yuma.co", "1234", "Medellin", 3_500_000,
     {"p1": "medellin", "p2": "max", "p3": "4821"}),
    ("C002", "Valentina Rios", "valentina@yuma.co", "1234", "Bogota", 4_200_000,
     {"p1": "bogota", "p2": "luna", "p3": "9032"}),
    ("C003", "Andres Restrepo", "andres@yuma.co", "1234", "Medellin", 1_800_000,
     {"p1": "envigado", "p2": "rocky", "p3": "1154"}),
    ("C004", "Mariana Ospina", "mariana@yuma.co", "1234", "Cali", 2_900_000,
     {"p1": "cali", "p2": "toby", "p3": "7740"}),
]


def cargar_boveda():
    if BOVEDA_FILE.exists():
        try:
            with open(BOVEDA_FILE, "r", encoding="utf-8") as f:
                estado.boveda_usuarios = json.load(f)
        except Exception:
            estado.boveda_usuarios = {}

    if not estado.boveda_usuarios:
        for cid, nombre, correo, pin, ciudad, saldo, preguntas in USUARIOS_INICIALES:
            estado.boveda_usuarios[cid] = crear_estructura_usuario(
                cid, nombre, correo, pin, ciudad, saldo, preguntas
            )
        guardar_boveda()
        return

    # Migración: completa campos nuevos en bóvedas antiguas
    modificado = False
    for u in estado.boveda_usuarios.values():
        defectos = {
            "rostro_enrolado": bool(u.get("rostro_real_capturado", False)),
            "foto_rostro_b64": "",
            "preguntas_seguridad": {"p1": "medellin", "p2": "max", "p3": "1234"},
            "cuenta_bloqueada": False,
            "movimientos": [],
        }
        for clave, valor in defectos.items():
            if clave not in u:
                u[clave] = valor
                modificado = True
    if modificado:
        guardar_boveda()


# ---------- Movimientos ----------
def registrar_movimiento_cliente(cid, tipo, contraparte, monto, id_tx):
    usuario = estado.boveda_usuarios.get(cid)
    if not usuario:
        return
    usuario.setdefault("movimientos", [])
    usuario["movimientos"].insert(0, {
        "id_tx": id_tx,
        "tipo": tipo,
        "contraparte": contraparte,
        "monto": int(monto),
        "hora": time.strftime("%H:%M:%S"),
        "fecha": time.strftime("%d/%m/%Y"),
    })
    usuario["movimientos"] = usuario["movimientos"][:40]


def liquidar_transferencia_exitosa(cid_origen, destino_texto, monto, id_tx):
    usuario = estado.boveda_usuarios.get(cid_origen)
    if not usuario:
        return
    with estado.lock:
        usuario["saldo"] = max(0, int(usuario["saldo"]) - monto)
        usuario["gastado_hoy"] = int(usuario.get("gastado_hoy", 0)) + monto

        receptor = buscar_destinatario_interno(destino_texto, excluir_cid=cid_origen)
        if receptor:
            nombre_dest = f"{receptor['nombre']} ({receptor['id_cliente']})"
            receptor["saldo"] = int(receptor["saldo"]) + monto
            registrar_movimiento_cliente(cid_origen, "salida", nombre_dest, monto, id_tx)
            registrar_movimiento_cliente(
                receptor["id_cliente"], "entrada",
                f"{usuario['nombre']} ({cid_origen})", monto, id_tx,
            )
        else:
            registrar_movimiento_cliente(cid_origen, "salida", destino_texto, monto, id_tx)
        guardar_boveda()
