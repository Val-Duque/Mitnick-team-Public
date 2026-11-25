"""Estado en memoria compartido (un único objeto `estado`)."""
import threading
from collections import defaultdict, deque

from .config import IMEIS_POR_DEFECTO


class Estado:
    def __init__(self):
        self.lock = threading.RLock()
        self.pool_imeis_reto = list(IMEIS_POR_DEFECTO)
        self.reiniciar_memoria()

    def reiniciar_memoria(self):
        self.boveda_usuarios = {}
        self.pagos_destino = defaultdict(int)
        self.remitentes_destino = defaultdict(set)
        self.historial_tx_usuario = defaultdict(deque)
        self.errores_por_usuario = defaultdict(int)
        self.notificaciones_push = {}
        self.transacciones_retenidas = {}
        self.tx_resueltas_soc = set()
        self.hash_cadena_auditoria = "0" * 64
        self.tiempos_evaluacion_ms = deque(maxlen=500)
        self.marcas_tiempo_trafico = deque()


estado = Estado()
