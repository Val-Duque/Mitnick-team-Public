# Mitnick Sentinel 360™ + Yuma Pay — API FastAPI

## Arrancar
```bash
pip install -r requirements.txt
python run.py                 # http://127.0.0.1:8081
```
Documentación interactiva (probar endpoints desde el navegador): **http://127.0.0.1:8081/docs**

Credenciales demo: cliente `C001` / PIN `1234` · analista `analista@mitnick.co` / `Mitnick2026`

## Endpoints (mismas rutas y JSON que el servidor original)
| Método | Ruta | Archivo |
|---|---|---|
| POST | `/login_usuario`, `/recuperar_dispositivo`, `/registrar_usuario` | `routers/clientes.py` |
| POST | `/ejecutar_transaccion`, `/verificar_rostro_en_vivo`, `/consumir_notificacion` | `routers/transacciones.py` |
| POST | `/login_analista`, `/accion_analista`, `/simular_trafico` | `routers/soc.py` |
| GET  | `/estado_completo`, `/v1/metricas` | `routers/soc.py` |
| POST/GET | `/reiniciar_sistema`, `/health` | `routers/sistema.py` |

## Estructura
```
run.py                  arranque
app/main.py             crea la app y registra los routers
app/config.py          topes, umbrales, claves, analistas, rutas de archivos
app/state.py            estado en memoria (objeto `estado`)
app/schemas.py          modelos de entrada (Pydantic)
app/utils.py            HMAC, similitud facial, parseo
app/services/           lógica de negocio (boveda, auditoria, motor antifraude)
app/routers/            endpoints agrupados por tema
data/                   se crea solo: bóveda JSON + auditoría .jsonl
```

## Cómo agregar una función nueva
**Un endpoint nuevo en un módulo existente** — en `app/routers/soc.py`:
```python
@router.get("/usuarios/{cid}")
def ver_usuario(cid: str):
    return estado.boveda_usuarios.get(cid) or {"error": "No existe"}
```
**Un grupo nuevo de endpoints** — crea `app/routers/reportes.py` con `router = APIRouter(tags=["Reportes"])`
y agrega `reportes` a la lista `ROUTERS` en `app/main.py`.

**Una regla antifraude nueva** — en `services/motor.py`, dentro de `evaluar_transaccion_automatica`,
suma a `puntaje` y agrega un texto a `razones` (ver las reglas existentes como ejemplo).

**Cambiar topes/umbrales** — solo `app/config.py` (también por variables de entorno: `MITNICK_PORT`, `MITNICK_HSM_KEY`, `MITNICK_DATA_DIR`).

**Un campo nuevo en un body** — agrégalo a la clase correspondiente en `app/schemas.py`.
