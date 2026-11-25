"""Motor antifraude: evaluación de transacciones, telemetría y simulador."""
import hashlib
import random
import time

from ..config import (
    ESCALA_RETO, LIMITE_SLA_MS, TOPE_DIARIO_CLIENTE, TOPE_POR_OPERACION,
    UMBRAL_DESAFIO, UMBRAL_MONTO_ALTO, UMBRAL_RECHAZO,
)
from ..state import estado
from ..utils import firmar_hmac_imei, parsear_entero
from .auditoria import registrar_auditoria
from .boveda import liquidar_transferencia_exitosa


# ---------- Telemetría ----------
def obtener_estadisticas_latencia_y_trafico():
    with estado.lock:
        if estado.tiempos_evaluacion_ms:
            ordenados = sorted(estado.tiempos_evaluacion_ms)
            p50 = round(ordenados[len(ordenados) // 2], 2)
            p99 = round(ordenados[min(len(ordenados) - 1, int(len(ordenados) * 0.99))], 2)
        else:
            p50, p99 = 1.8, 4.2

        ahora = time.time()
        marcas = estado.marcas_tiempo_trafico
        while marcas and marcas[0] < ahora - 10:
            marcas.popleft()
        tps_actual = round(len(marcas) / 10.0, 1)

    return {
        "latencia_mediana_ms": p50,
        "latencia_p99_ms": p99,
        "limite_sla_ms": LIMITE_SLA_MS,
        "tps_actual": tps_actual,
        "usuarios_escala_banco": ESCALA_RETO["usuarios_activos"],
        "tx_diarias_escala_banco": ESCALA_RETO["transacciones_diarias"],
        "tps_promedio_banco": ESCALA_RETO["tps_promedio_diario"],
        "capacidad_max_motor_tps": ESCALA_RETO["capacidad_procesamiento_motor_tps"],
    }


# ---------- Motor de decisión ----------
# Para agregar una regla nueva: súmale puntaje a `puntaje` y un texto a `razones`
# dentro de evaluar_transaccion_automatica().
def evaluar_transaccion_automatica(datos: dict, es_simulacion: bool = False) -> dict:
    inicio_t = time.perf_counter()
    id_tx = f"TX-{random.randint(100000, 999999)}"
    cid = str(datos.get("id_cliente", "C001")).strip()
    usuario = estado.boveda_usuarios.get(cid)

    if not usuario:
        return {"error": "Usuario no encontrado"}
    if usuario.get("cuenta_bloqueada") and not es_simulacion:
        return {"error": "Cuenta congelada por alerta de seguridad. Contacte al SOC."}

    imei_tx = str(datos.get("imei_tx", usuario["imei_vinculado"])).strip()
    imei_oficial = usuario["imei_vinculado"]
    ciudad_tx = str(datos.get("ciudad_tx", usuario["ciudad_habitual"])).strip()
    destino = str(datos.get("destino", "Comercio_Yuma")).strip()
    tipo_op = str(datos.get("tipo_op", "transferencia_inmediata")).strip()
    monto = parsear_entero(datos.get("monto", 0))
    saldo = int(usuario["saldo"])
    gastado_hoy = int(usuario.get("gastado_hoy", 0))

    if monto <= 0:
        return {"error": "El monto debe ser mayor a $0"}

    hmac_oficial = usuario["firma_hmac_imei"]
    hmac_tx = firmar_hmac_imei(cid, imei_tx)

    tot_dest = estado.pagos_destino[destino]
    nuevos_dest = len(estado.remitentes_destino[destino])
    sello_destino = hashlib.sha256(f"{destino}:{tot_dest}:{nuevos_dest}".encode()).hexdigest()[:12]

    puntaje = 0.03
    razones = []

    # Regla: fondos y topes
    if not es_simulacion:
        if monto > saldo:
            puntaje = 0.99
            razones.append(f"Fondos insuficientes: Intento de ${monto:,} con saldo de ${saldo:,}")
        elif monto > TOPE_POR_OPERACION:
            puntaje += 0.65
            razones.append(f"Excede Tope por Operación (${TOPE_POR_OPERACION:,} COP)")
        elif (gastado_hoy + monto) > TOPE_DIARIO_CLIENTE:
            puntaje += 0.55
            razones.append(f"Excede Tope Diario Acumulado (${TOPE_DIARIO_CLIENTE:,} COP)")

    # Regla: dispositivo (IMEI/HMAC)
    if hmac_tx != hmac_oficial:
        puntaje += 0.52
        razones.append(
            f"Discrepancia IMEI/HMAC: Hardware '{imei_tx}' no coincide con enrolado '{imei_oficial}'"
        )

    # Regla: ubicación
    if ciudad_tx.lower() != usuario["ciudad_habitual"].lower():
        puntaje += 0.34
        razones.append(
            f"Ubicación atípica: Conexión desde {ciudad_tx} (Habitual: {usuario['ciudad_habitual']})"
        )

    # Regla: destino / QR
    destino_lower = destino.lower()
    if destino_lower.startswith(("http://", "https://")) or "premio" in destino_lower or "falso" in destino_lower:
        puntaje += 0.85
        razones.append(f"QR Adulterado / Phishing detectado [{sello_destino}]: URL externa no autorizada")
    elif tipo_op == "pago_qr" and tot_dest >= 2 and (tot_dest - nuevos_dest) == 0:
        puntaje += 0.42
        razones.append(
            f"QR sin Marca de Agua verificada [{sello_destino}]: Múltiples cobros sin clientes recurrentes"
        )

    # Reglas: cuenta mula y ráfaga
    if not es_simulacion:
        ratio_saldo = monto / max(saldo, 1)
        if ratio_saldo >= 0.85 and monto >= UMBRAL_MONTO_ALTO:
            puntaje += 0.45
            razones.append(f"Alerta Cuenta Mula: Intento de vaciar el {int(ratio_saldo * 100)}% del saldo")

        ahora = time.time()
        ventana = estado.historial_tx_usuario[cid]
        while ventana and ventana[0] < ahora - 120:
            ventana.popleft()
        if len(ventana) >= 2:
            puntaje += 0.36
            razones.append(f"Ráfaga de velocidad: {len(ventana) + 1} operaciones en menos de 2 minutos")
        ventana.append(ahora)

    # Decisión
    puntaje = round(min(0.99, puntaje), 2)
    if not razones:
        razones.append(f"Firma IMEI HMAC [{hmac_tx[:10]}] y Sello Destino [{sello_destino[:8]}] validados")

    if puntaje >= UMBRAL_RECHAZO:
        decision = "rechazar"
        estado.errores_por_usuario[cid] += 1
    elif puntaje >= UMBRAL_DESAFIO:
        decision = "desafiar"
        estado.errores_por_usuario[cid] += 1
    else:
        decision = "aprobar"
        if not es_simulacion:
            liquidar_transferencia_exitosa(cid, destino, monto, id_tx)

    estado.pagos_destino[destino] += 1
    estado.remitentes_destino[destino].add(cid)

    latencia_ms = round((time.perf_counter() - inicio_t) * 1000, 2)
    with estado.lock:
        estado.tiempos_evaluacion_ms.append(latencia_ms)
        estado.marcas_tiempo_trafico.append(time.time())

    evento = {
        "id_tx": id_tx,
        "id_cliente": cid,
        "nombre_cliente": usuario["nombre"],
        "tipo_op": tipo_op,
        "monto": monto,
        "saldo_restante": usuario["saldo"],
        "destino": destino,
        "ciudad_tx": ciudad_tx,
        "imei_tx": imei_tx,
        "imei_oficial": imei_oficial,
        "hmac_tx": hmac_tx[:16],
        "hmac_oficial": hmac_oficial[:16],
        "sello_destino": sello_destino,
        "puntaje": puntaje,
        "decision": decision,
        "latencia_ms": latencia_ms,
        "razones": razones,
        "origen_decision": "SIMULACION_TRAFICO_SOC" if es_simulacion else "MOTOR_AUTOMATICO_IA",
        "escalado_soc": decision in ("desafiar", "rechazar"),
    }
    registrar_auditoria(evento)

    if decision == "desafiar" and not es_simulacion:
        estado.transacciones_retenidas[cid] = evento
        estado.notificaciones_push[cid] = {
            "id_tx": id_tx,
            "id_cliente": cid,
            "monto": monto,
            "destino": destino,
            "imei_tx": imei_tx,
            "motivo": razones[0],
            "enviado_por": "Escudo Yuma 360 — Autenticación Adaptativa",
            "timestamp": time.strftime("%H:%M:%S"),
        }

    return evento


# ---------- Simulador de tráfico ----------
COMERCIOS = [
    "Supermercado_Exito", "D1_Tiendas", "Rappi_Colombia",
    "EPM_Servicios", "Uber_Trips", "Farmatodo_CO",
]


def ejecutar_rafaga_trafico(cantidad=50):
    ids_clientes = list(estado.boveda_usuarios.keys())
    resultados = {"aprobar": 0, "desafiar": 0, "rechazar": 0}

    for _ in range(max(1, min(cantidad, 500))):
        cid = random.choice(ids_clientes)
        u = estado.boveda_usuarios[cid]
        roll = random.random()

        if roll < 0.86:      # tráfico legítimo
            datos = {
                "id_cliente": cid, "imei_tx": u["imei_vinculado"],
                "ciudad_tx": u["ciudad_habitual"], "destino": random.choice(COMERCIOS),
                "tipo_op": "transferencia_inmediata", "monto": random.randint(25_000, 350_000),
            }
        elif roll < 0.94:    # dispositivo desconocido
            datos = {
                "id_cliente": cid, "imei_tx": "35999" + str(random.randint(1_000_000_000, 9_999_999_999)),
                "ciudad_tx": u["ciudad_habitual"], "destino": random.choice(COMERCIOS),
                "tipo_op": "transferencia_inmediata", "monto": random.randint(150_000, 650_000),
            }
        else:                # fraude: phishing + exterior
            datos = {
                "id_cliente": cid, "imei_tx": "35999" + str(random.randint(1_000_000_000, 9_999_999_999)),
                "ciudad_tx": "Miami (Exterior)", "destino": "https://premio-falso-yuma.co/cobro",
                "tipo_op": "pago_qr", "monto": random.randint(500_000, 1_400_000),
            }

        ev = evaluar_transaccion_automatica(datos, es_simulacion=True)
        if "decision" in ev:
            resultados[ev["decision"]] += 1
    return resultados
