"""Endpoints del cliente: login, recuperar dispositivo, registro."""
import hashlib

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..config import UMBRAL_SIMILITUD_FACIAL
from ..schemas import LoginUsuarioIn, RecuperarDispositivoIn, RegistrarUsuarioIn
from ..services.boveda import (
    buscar_usuario_por_identificador, crear_estructura_usuario,
    guardar_boveda, obtener_imei_del_reto, siguiente_id_cliente,
)
from ..state import estado
from ..utils import calcular_similitud_vectores, firmar_hmac_imei, parsear_entero

router = APIRouter(tags=["Clientes"])


def _error(mensaje: str, code: int):
    return JSONResponse({"ok": False, "mensaje": mensaje}, status_code=code)


@router.post("/login_usuario")
def login_usuario(body: LoginUsuarioIn):
    usuario = buscar_usuario_por_identificador(body.identificador)
    if not usuario or usuario.get("pin") != body.pin.strip():
        if usuario:
            estado.errores_por_usuario[usuario["id_cliente"]] += 1
        return _error("Usuario o PIN incorrecto.", 401)

    if usuario.get("cuenta_bloqueada"):
        return _error(
            "Cuenta bloqueada preventivamente por suplantación facial. Requiere revisión del SOC.", 403
        )

    if body.es_incognito:
        imei_usado = obtener_imei_del_reto(excluir=usuario["imei_vinculado"])
    else:
        imei_usado = body.imei_sesion.strip() or usuario["imei_vinculado"]

    return {"ok": True, "usuario": usuario, "imei_sesion": imei_usado}


@router.post("/recuperar_dispositivo")
def recuperar_dispositivo(body: RecuperarDispositivoIn):
    usuario = buscar_usuario_por_identificador(body.identificador)
    if not usuario:
        return _error("Cliente no encontrado.", 404)

    cid = usuario["id_cliente"]
    if usuario.get("cuenta_bloqueada"):
        return _error("Cuenta bloqueada por el SOC. No se permite vincular equipos.", 403)

    pregs = usuario.get("preguntas_seguridad", {})
    respuestas = [
        body.r1.strip().lower() == str(pregs.get("p1", "")).strip().lower(),
        body.r2.strip().lower() == str(pregs.get("p2", "")).strip().lower(),
        body.r3.strip().lower() == str(pregs.get("p3", "")).strip().lower(),
    ]
    aciertos = sum(respuestas)
    if aciertos < 3:
        estado.errores_por_usuario[cid] += 1
        return _error(f"Respuestas de seguridad incorrectas ({aciertos}/3). Cambio de dispositivo bloqueado.", 401)

    if not usuario.get("rostro_enrolado") or not usuario.get("vector_facial"):
        return _error("Esta cuenta no tiene biometría base enrolada para validar el cambio de equipo.", 400)

    if not body.vector_facial:
        return _error("Debes capturar tu rostro en vivo antes de vincular el nuevo celular.", 400)

    similitud = calcular_similitud_vectores(usuario["vector_facial"], body.vector_facial)
    if similitud < UMBRAL_SIMILITUD_FACIAL:
        estado.errores_por_usuario[cid] += 1
        return _error(
            f"Biometría NO coincide ({similitud}% similitud < {UMBRAL_SIMILITUD_FACIAL}%). "
            "Intento rechazado y reportado al SOC.", 401
        )

    nuevo_imei = obtener_imei_del_reto(excluir=usuario["imei_vinculado"])
    usuario["imei_vinculado"] = nuevo_imei
    usuario["firma_hmac_imei"] = firmar_hmac_imei(cid, nuevo_imei)
    guardar_boveda()

    return {"ok": True, "similitud": similitud, "usuario": usuario, "nuevo_imei": nuevo_imei}


@router.post("/registrar_usuario")
def registrar_usuario(body: RegistrarUsuarioIn):
    if not body.vector_facial:
        return _error(
            "Debes capturar tu rostro con la cámara para registrar la cuenta en la Base de Datos Biométrica.", 400
        )

    with estado.lock:
        cid = siguiente_id_cliente()
        preguntas = {
            "p1": body.p1.strip().lower() or "medellin",
            "p2": body.p2.strip().lower() or "max",
            "p3": body.p3.strip().lower() or "1234",
        }
        estado.boveda_usuarios[cid] = crear_estructura_usuario(
            cid=cid,
            nombre=body.nombre.strip() or "Cliente Yuma",
            correo=body.correo.strip().lower() or f"{cid.lower()}@yuma.co",
            pin=body.pin.strip() or "1234",
            ciudad=body.ciudad.strip() or "Medellin",
            saldo=parsear_entero(body.saldo, 2_500_000),
            preguntas=preguntas,
            rostro_enrolado=True,
            foto_b64=body.foto_b64,
            vector_facial=body.vector_facial,
            hash_rostro=hashlib.sha256(",".join(map(str, body.vector_facial)).encode()).hexdigest(),
        )
        guardar_boveda()

    return {"ok": True, "usuario": estado.boveda_usuarios[cid]}
