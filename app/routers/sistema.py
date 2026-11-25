"""Endpoints de administración del sistema."""
from fastapi import APIRouter

from ..config import AUDIT_FILE, BOVEDA_FILE
from ..services.boveda import cargar_boveda
from ..state import estado

router = APIRouter(tags=["Sistema"])


@router.get("/health")
def health():
    return {"ok": True, "usuarios": len(estado.boveda_usuarios)}


@router.post("/reiniciar_sistema")
def reiniciar_sistema():
    with estado.lock:
        for archivo in (AUDIT_FILE, BOVEDA_FILE):
            if archivo.exists():
                archivo.unlink()
        estado.reiniciar_memoria()
        cargar_boveda()
    return {"ok": True}
