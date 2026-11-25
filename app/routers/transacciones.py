"""Endpoints de transacciones y del flujo de desafío (push + biometría)."""
import time

from fastapi import APIRouter

from ..config import UMBRAL_SIMILITUD_FACIAL
from ..schemas import ConsumirNotificacionIn, TransaccionIn, VerificarRostroIn
from ..services.auditoria import registrar_auditoria
from ..services.boveda import liquidar_transferencia_exitosa
from ..services.motor import evaluar_transaccion_automatica
from ..state import estado
from ..utils import calcular_similitud_vectores

router = APIRouter(tags=["Transacciones"])


@router.post("/ejecutar_transaccion")
def ejecutar_transaccion(body: TransaccionIn):
    # exclude_unset: solo pasamos lo que el cliente envió realmente
    return evaluar_transaccion_automatica(body.model_dump(exclude_unset=True))


@router.post("/verificar_rostro_en_vivo")
def verificar_rostro_en_vivo(body: VerificarRostroIn):
    cid = body.id_cliente.strip()
    usuario = estado.boveda_usuarios.get(cid)
    tx_ret = estado.transacciones_retenidas.pop(cid, None)
    estado.notificaciones_push.pop(cid, None)

    if tx_ret and tx_ret.get("id_tx"):
        estado.tx_resueltas_soc.add(tx_ret["id_tx"])

    if not usuario or not usuario.get("rostro_enrolado") or not usuario.get("vector_facial"):
        return {
            "ok": False, "coincide": False, "similitud": 0, "cerrar_sesion": True,
            "mensaje": "Sin biometría base registrada. Sesión bloqueada por seguridad.",
        }

    similitud = calcular_similitud_vectores(usuario["vector_facial"], body.vector_facial)
    coincide = similitud >= UMBRAL_SIMILITUD_FACIAL
    monto_tx = int(tx_ret["monto"]) if tx_ret else 0
    tx = tx_ret or {}

    base_evento = {
        "id_cliente": cid,
        "nombre_cliente": usuario["nombre"],
        "tipo_op": tx.get("tipo_op", "transferencia_inmediata"),
        "monto": monto_tx,
        "saldo_restante": usuario["saldo"],
        "imei_oficial": usuario["imei_vinculado"],
        "hmac_oficial": usuario["hash_rostro"][:16],
    }

    if coincide:
        destino_tx = tx.get("destino", "Destino_Verificado")
        id_tx_final = f"{tx['id_tx']}-OK" if tx_ret else f"TX-BIO-{int(time.time() * 1000) % 10000}"

        if monto_tx > 0:
            liquidar_transferencia_exitosa(cid, destino_tx, monto_tx, id_tx_final)
            registrar_auditoria({
                **base_evento,
                "id_tx": id_tx_final,
                "saldo_restante": usuario["saldo"],  # ya liquidado
                "destino": destino_tx,
                "ciudad_tx": tx.get("ciudad_tx", usuario["ciudad_habitual"]),
                "imei_tx": tx.get("imei_tx", usuario["imei_vinculado"]),
                "hmac_tx": f"BIO_MATCH_{similitud}%",
                "sello_destino": tx.get("sello_destino", "BIO_OK"),
                "puntaje": 0.05,
                "decision": "aprobar",
                "latencia_ms": 1.9,
                "razones": [
                    f"Prueba de Vida Exitosa ({similitud}% similitud): Operación retenida liberada automáticamente"
                ],
                "origen_decision": "MOTOR_BIOMETRICO_ADAPTATIVO",
                "escalado_soc": False,
            })

        return {
            "ok": True, "coincide": True, "similitud": similitud, "cerrar_sesion": False,
            "mensaje": f"Prueba de vida verificada ({similitud}% coincidencia). Transferencia por ${monto_tx:,} aprobada.",
        }

    # --- Rostro NO coincide: posible suplantación ---
    estado.errores_por_usuario[cid] += 1
    if monto_tx > 0:
        id_tx_rechazo = f"{tx['id_tx']}-RECH" if tx_ret else f"TX-IMP-{int(time.time() * 1000) % 10000}"
        registrar_auditoria({
            **base_evento,
            "id_tx": id_tx_rechazo,
            "destino": tx.get("destino", "N/A"),
            "ciudad_tx": tx.get("ciudad_tx", "DESCONOCIDA"),
            "imei_tx": tx.get("imei_tx", "NO_AUTORIZADO"),
            "hmac_tx": f"BIO_FAIL_{similitud}%",
            "sello_destino": "SUPLANTACION_FACIAL",
            "puntaje": 0.98,
            "decision": "rechazar",
            "latencia_ms": 1.7,
            "razones": [
                f"SUPLANTACIÓN DETECTADA ({similitud}% similitud < {UMBRAL_SIMILITUD_FACIAL}%): "
                "Operación rechazada, sesión cerrada y escalada al SOC"
            ],
            "origen_decision": "MOTOR_BIOMETRICO_ADAPTATIVO",
            "escalado_soc": True,
        })

    return {
        "ok": True, "coincide": False, "similitud": similitud, "cerrar_sesion": True,
        "mensaje": f"Rostro NO coincide ({similitud}% similitud). Operación rechazada, sesión bloqueada y caso escalado al SOC.",
    }


@router.post("/consumir_notificacion")
def consumir_notificacion(body: ConsumirNotificacionIn):
    cid = body.id_cliente.strip()
    notif = estado.notificaciones_push.pop(cid, None)
    tx_ret = estado.transacciones_retenidas.pop(cid, None)

    if tx_ret and tx_ret.get("id_tx"):
        estado.tx_resueltas_soc.add(tx_ret["id_tx"])
        usuario = estado.boveda_usuarios.get(cid)
        if usuario:
            registrar_auditoria({
                "id_tx": f"{tx_ret['id_tx']}-CANC",
                "id_cliente": cid,
                "nombre_cliente": usuario["nombre"],
                "tipo_op": tx_ret.get("tipo_op", "transferencia_inmediata"),
                "monto": int(tx_ret["monto"]),
                "saldo_restante": usuario["saldo"],
                "destino": tx_ret["destino"],
                "ciudad_tx": tx_ret.get("ciudad_tx", "DESCONOCIDA"),
                "imei_tx": tx_ret.get("imei_tx", "NO_AUTORIZADO"),
                "imei_oficial": usuario["imei_vinculado"],
                "hmac_tx": "CANCELADO_TITULAR",
                "hmac_oficial": usuario["hash_rostro"][:16],
                "sello_destino": "ALERTA_TITULAR",
                "puntaje": 0.95,
                "decision": "rechazar",
                "latencia_ms": 1.2,
                "razones": ["El titular rechazó la alerta push ('No fui yo'): Operación bloqueada y reportada al SOC"],
                "origen_decision": "ALERTA_PUSH_TITULAR",
                "escalado_soc": True,
            })

    return {"notificacion": notif}
