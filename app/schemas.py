"""Modelos de entrada (lo que envía el frontend). Son tolerantes: todo tiene
valor por defecto y se permiten campos extra, igual que el servidor original."""
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class Entrada(BaseModel):
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)


class LoginUsuarioIn(Entrada):
    identificador: str = ""
    pin: str = ""
    imei_sesion: str = ""
    es_incognito: bool = False


class RecuperarDispositivoIn(Entrada):
    identificador: str = ""
    r1: str = ""
    r2: str = ""
    r3: str = ""
    vector_facial: Optional[list[Any]] = None


class RegistrarUsuarioIn(Entrada):
    nombre: str = ""
    correo: str = ""
    pin: str = ""
    ciudad: str = ""
    saldo: Any = 2_500_000
    p1: str = ""
    p2: str = ""
    p3: str = ""
    foto_b64: str = ""
    vector_facial: Optional[list[Any]] = None


class TransaccionIn(Entrada):
    id_cliente: str = "C001"
    imei_tx: Optional[str] = None
    ciudad_tx: Optional[str] = None
    destino: str = "Comercio_Yuma"
    tipo_op: str = "transferencia_inmediata"
    monto: Any = 0


class VerificarRostroIn(Entrada):
    id_cliente: str = ""
    vector_facial: Optional[list[Any]] = None


class ConsumirNotificacionIn(Entrada):
    id_cliente: str = ""


class LoginAnalistaIn(Entrada):
    correo: str = ""
    clave: str = ""


class AccionAnalistaIn(Entrada):
    accion: Optional[str] = None
    id_cliente: Optional[str] = None
    analista: str = "Analista SOC"


class SimularTraficoIn(Entrada):
    cantidad: Any = 50
