"""Mitnick Sentinel 360™ + Yuma Pay — API FastAPI.

Arranque:  python run.py        |   uvicorn app.main:app --port 8081 --reload
Docs:      http://127.0.0.1:8081/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import FRONTEND_DIR
from .routers import clientes, sistema, soc, transacciones
from .services.boveda import cargar_boveda, cargar_pool_imeis_reto

# Para agregar un grupo nuevo de endpoints: crea app/routers/mi_modulo.py
# y añádelo a esta lista.
ROUTERS = [clientes, transacciones, soc, sistema]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    cargar_pool_imeis_reto()
    cargar_boveda()
    print("=" * 57)
    print("🛡️  Mitnick Sentinel 360™ + Yuma Pay activo")
    print("👤  Cliente demo : C001 / PIN: 1234")
    print("🔎  Analista SOC : analista@mitnick.co / Mitnick2026")
    print("🏦  App cliente  : http://127.0.0.1:8081/usuario")
    print("🔎  Consola SOC  : http://127.0.0.1:8081/consola")
    print("📖  Documentación: http://127.0.0.1:8081/docs")
    print("=" * 57)
    yield


app = FastAPI(title="Mitnick Sentinel 360™ + Yuma Pay", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

for modulo in ROUTERS:
    app.include_router(modulo.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request, exc):
    # Mantiene el formato de error del servidor original
    return JSONResponse({"ok": False, "error": "Ruta no encontrada" if exc.status_code == 404 else exc.detail},
                        status_code=exc.status_code)


# ---------- Frontend (HTML/CSS/JS) servido por la misma API ----------
# Los archivos están en la carpeta /frontend. Agrega aquí nuevas pantallas
# simplemente copiando el .html a esa carpeta.
PAGINA_INICIO = """<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Mitnick Sentinel 360™</title>
<style>body{font-family:'Segoe UI',Arial,sans-serif;background:#0b1120;color:#e2e8f0;display:flex;
flex-direction:column;align-items:center;justify-content:center;min-height:100vh;margin:0;gap:14px}
a{display:block;width:300px;text-align:center;padding:14px;border-radius:10px;text-decoration:none;
font-weight:bold;color:#fff;background:#0284c7}a.b{background:#004080}a.c{background:#334155}</style></head>
<body><h1>🛡️ Mitnick Sentinel 360™</h1>
<a class="b" href="/usuario">🏦 App Cliente — Yuma Pay</a>
<a href="/consola">🔎 Consola SOC Antifraude</a>
<a class="c" href="/docs">📖 Documentación API</a></body></html>"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def inicio():
    return PAGINA_INICIO


@app.get("/usuario", include_in_schema=False)
def ir_usuario():
    return RedirectResponse("/app/app_usuario.htm")


@app.get("/consola", include_in_schema=False)
def ir_consola():
    return RedirectResponse("/app/consola_mitnick.html")


app.mount("/app", StaticFiles(directory=FRONTEND_DIR), name="frontend")
