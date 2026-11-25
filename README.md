# 🛡️ Mitnick Sentinel 360™ + Yuma Pay

API antifraude bancaria (FastAPI) con dos pantallas web: la **app del cliente** (Yuma Pay) y la **consola SOC** para analistas. Es una demo: el estado vive en memoria y en archivos locales.

---

## 1. Inicio rápido

```bash
# (recomendado) entorno virtual
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
python run.py
```

| URL | Qué es |
|---|---|
| http://127.0.0.1:8081/ | Página de inicio con los accesos |
| http://127.0.0.1:8081/usuario | App cliente Yuma Pay |
| http://127.0.0.1:8081/consola | Consola SOC antifraude |
| http://127.0.0.1:8081/docs | Documentación interactiva (Swagger): permite probar cada endpoint |

**Credenciales demo**

| Rol | Usuario | Clave |
|---|---|---|
| Cliente | `C001` (o `carlos@yuma.co`) | `1234` |
| Clientes extra | `C002`, `C003`, `C004` | `1234` |
| Analista SOC | `analista@mitnick.co` | `Mitnick2026` |
| Analista SOC | `soc@yumapay.co` | `Yuma2026` |

> Abre siempre las pantallas por `http://127.0.0.1:8081/...` y no con doble clic en el `.html`. Así comparten servidor y la cámara funciona (el navegador solo la permite en `localhost`/`127.0.0.1` o HTTPS).

---

## 2. Estructura del proyecto

```
mitnick_api/
├── run.py                     Arranque (uvicorn con recarga automática)
├── requirements.txt           fastapi, uvicorn
├── frontend/                  Pantallas web (HTML/CSS/JS)
│   ├── app_usuario.htm        App del cliente
│   ├── diseno-usuario.css
│   ├── funcion.js             Lógica de la app del cliente
│   ├── consola_mitnick.html   Consola SOC
│   ├── consola_mitnick.css
│   └── consola_mitnick.js     Lógica de la consola SOC
├── app/
│   ├── main.py                Crea la app, CORS, routers y sirve el frontend
│   ├── config.py              Constantes, umbrales, claves, rutas de archivos
│   ├── state.py               Estado en memoria compartido (objeto `estado`)
│   ├── schemas.py             Modelos de entrada (Pydantic)
│   ├── utils.py               HMAC, similitud facial, parseo
│   ├── services/              Lógica de negocio
│   │   ├── boveda.py          Usuarios: crear, buscar, guardar, liquidar
│   │   ├── auditoria.py       Cadena de auditoría SHA-256
│   │   └── motor.py           Motor antifraude, telemetría, simulador
│   └── routers/               Endpoints agrupados por tema
│       ├── clientes.py        login / registro / recuperar dispositivo
│       ├── transacciones.py   transacciones y flujo de desafío
│       ├── soc.py             analistas, estado, métricas, simulador
│       └── sistema.py         health y reinicio
└── data/                      Se crea solo al arrancar
    ├── boveda_rostros_yuma.json        Usuarios (persistente)
    └── auditoria_inmutable_sha256.jsonl  Auditoría (solo se agrega al final)
```

**Regla general:** los *routers* reciben y responden HTTP; los *services* contienen la lógica; `state.py` guarda los datos en memoria; `config.py` guarda lo que se ajusta.

---

## 3. Conceptos clave

- **Bóveda de usuarios:** diccionario `id_cliente → usuario`. Se guarda en `data/boveda_rostros_yuma.json` y se carga al arrancar. Si no existe, se crean 4 clientes demo (C001–C004).
- **IMEI vinculado:** cada usuario tiene un dispositivo "oficial". Se firma con **HMAC-SHA256** (`firma_hmac_imei`) usando la clave `MITNICK_HSM_KEY`. Si una transacción llega desde otro IMEI, la firma no coincide y sube el riesgo.
- **Biometría facial:** el frontend calcula un vector del rostro y lo envía. El servidor compara con el vector guardado usando **similitud coseno** normalizada a 0–100. Se acepta con **≥ 72 %**.
- **Auditoría inmutable:** cada decisión se encadena al hash anterior (como una mini blockchain). Alterar una línea rompe la cadena.
- **Desafío:** si el riesgo es medio, la transacción **no se ejecuta**: queda retenida y al cliente le llega una notificación push que lo obliga a probar su identidad con el rostro.

---

## 4. Motor antifraude

Archivo: `app/services/motor.py` → `evaluar_transaccion_automatica()`.

Cada transacción empieza con un puntaje base de **0.03** y suma según las reglas:

| Regla | Suma | Cuándo aplica |
|---|---|---|
| Fondos insuficientes | puntaje = **0.99** | `monto > saldo` |
| Excede tope por operación | +0.65 | `monto > $2.000.000` |
| Excede tope diario | +0.55 | `gastado_hoy + monto > $5.000.000` |
| IMEI / HMAC no coincide | +0.52 | El dispositivo no es el enrolado |
| Ubicación atípica | +0.34 | `ciudad_tx` ≠ ciudad habitual |
| QR adulterado / phishing | +0.85 | Destino empieza por `http(s)://` o contiene "premio" / "falso" |
| QR sin marca verificada | +0.42 | `pago_qr` con 2+ cobros previos sin clientes recurrentes |
| Cuenta mula | +0.45 | Intenta mover ≥ 85 % del saldo y monto ≥ $800.000 |
| Ráfaga de velocidad | +0.36 | 2+ operaciones previas del cliente en los últimos 120 s |

El puntaje se limita a **0.99** y se redondea a 2 decimales.

| Puntaje | Decisión | Qué pasa |
|---|---|---|
| `< 0.30` | `aprobar` | Se descuenta el saldo, se acredita al destinatario si es cliente interno y se registra el movimiento |
| `0.30 – 0.81` | `desafiar` | Se retiene la transacción y se envía push al cliente |
| `≥ 0.82` | `rechazar` | Se bloquea y se escala al SOC |

> Las reglas de fondos/topes, cuenta mula y ráfaga **no** se aplican en modo simulación (`/simular_trafico`), y las simulaciones nunca modifican saldos.

Todos los umbrales y topes están en `app/config.py`.

---

## 5. Referencia de endpoints

Todos devuelven JSON. Los errores de autenticación/validación usan `{"ok": false, "mensaje": "..."}`.

### Cliente (`routers/clientes.py`)

**`POST /login_usuario`**
```json
{ "identificador": "C001", "pin": "1234", "imei_sesion": "", "es_incognito": false }
```
- `identificador`: ID o correo. `es_incognito: true` simula entrar desde otro dispositivo (asigna un IMEI distinto).
- ✅ `{"ok": true, "usuario": {...}, "imei_sesion": "..."}`
- ❌ 401 PIN/usuario incorrecto · 403 cuenta bloqueada por el SOC.

**`POST /registrar_usuario`**
```json
{ "nombre": "Sofía", "correo": "sofia@yuma.co", "pin": "1234", "ciudad": "Cali",
  "saldo": 2500000, "p1": "cali", "p2": "max", "p3": "4821",
  "foto_b64": "data:image/jpeg;base64,...", "vector_facial": [0.12, -0.4, ...] }
```
- `vector_facial` es **obligatorio** (400 si falta). Crea el siguiente ID libre (`C005`, `C006`…).
- ✅ `{"ok": true, "usuario": {...}}`

**`POST /recuperar_dispositivo`** — vincula un celular nuevo.
```json
{ "identificador": "C001", "r1": "medellin", "r2": "max", "r3": "4821", "vector_facial": [...] }
```
Exige las **3 respuestas correctas** y que el rostro coincida (≥ 72 %). Si todo está bien asigna un IMEI nuevo y firma de nuevo el HMAC.
- ✅ `{"ok": true, "similitud": 91, "usuario": {...}, "nuevo_imei": "..."}`
- ❌ 404 no existe · 403 bloqueada · 401 respuestas o rostro incorrectos · 400 sin biometría base o sin captura.

### Transacciones (`routers/transacciones.py`)

**`POST /ejecutar_transaccion`**
```json
{ "id_cliente": "C001", "imei_tx": "864920118472615", "ciudad_tx": "Medellin",
  "destino": "Supermercado_Exito", "tipo_op": "transferencia_inmediata", "monto": 120000 }
```
- `tipo_op`: `transferencia_inmediata` o `pago_qr`. Si no se envían `imei_tx` / `ciudad_tx`, se usan los del usuario.
- ✅ Devuelve el evento completo: `id_tx`, `decision`, `puntaje`, `razones[]`, `latencia_ms`, `hash_actual`, etc.
- ⚠️ Errores de negocio (usuario inexistente, monto ≤ 0, cuenta congelada) responden **200** con `{"error": "..."}` (comportamiento heredado del servidor original que el frontend ya espera).

**`POST /verificar_rostro_en_vivo`** — prueba de vida tras un desafío.
```json
{ "id_cliente": "C001", "vector_facial": [...] }
```
- Si coincide: libera la transacción retenida, liquida el saldo y audita como aprobada.
- Si no coincide: rechaza, devuelve `cerrar_sesion: true` y escala al SOC.
- ✅ `{"ok": true, "coincide": true|false, "similitud": 88, "cerrar_sesion": false, "mensaje": "..."}`

**`POST /consumir_notificacion`** — la app consulta/descarta la push (o el cliente responde "No fui yo").
```json
{ "id_cliente": "C001" }
```
- ✅ `{"notificacion": {...} | null}`. Si había una transacción retenida, la cancela y registra un rechazo `origen_decision: ALERTA_PUSH_TITULAR`.

### SOC (`routers/soc.py`)

| Endpoint | Descripción |
|---|---|
| `POST /login_analista` | Body `{correo, clave}` → `{ok, analista:{correo,nombre,rol}}` · 401 si es inválido |
| `POST /accion_analista` | Body `{accion, id_cliente, analista}`. Acciones: `confirmar_bloqueo_cuenta`, `desbloquear_cuenta` · 400 si no es válida |
| `GET /estado_completo` | Todo lo que pinta la consola: `usuarios`, `historial` (últimas 40), `conteos_totales`, `notificaciones`, `errores_usuarios`, `telemetria`, `topes` |
| `GET /v1/metricas` | Resumen para el reto: totales, % sin fricción, latencias p50/p99, último hash de la cadena |
| `POST /simular_trafico` | Body `{cantidad}` (1–500). Genera tráfico: 86 % legítimo, 8 % dispositivo desconocido, 6 % fraude phishing |

### Sistema (`routers/sistema.py`)

| Endpoint | Descripción |
|---|---|
| `GET /health` | `{ok, usuarios}` — para verificar que el servidor está vivo |
| `POST /reiniciar_sistema` | Borra bóveda y auditoría, limpia la memoria y recrea los 4 usuarios demo |

---

## 6. Flujos principales

**Transferencia normal**
`App → /ejecutar_transaccion → motor → aprobar → saldo actualizado → auditoría`

**Transferencia sospechosa (desafío)**
```
App → /ejecutar_transaccion → motor: puntaje medio → "desafiar"
   → tx queda retenida + push al cliente
App → /verificar_rostro_en_vivo
   ├─ rostro coincide  → liquida, audita "aprobar"
   └─ rostro no coincide → rechaza, cierra sesión, escala al SOC
App → /consumir_notificacion ("No fui yo") → cancela y audita "rechazar"
```

**Cambio de celular**
`App → /recuperar_dispositivo` (3 preguntas + rostro) → nuevo IMEI + nueva firma HMAC.

**Supervisión SOC**
`Consola → /estado_completo (cada ~1,2 s)` → muestra transacciones; el analista puede `confirmar_bloqueo_cuenta` sobre un rechazo.

---

## 7. Auditoría inmutable

Archivo `data/auditoria_inmutable_sha256.jsonl`, una línea JSON por evento (solo con `monto > 0`). Cada bloque calcula:

```
hash_actual = SHA256( hash_previo | id_tx | decision | puntaje | razones separadas por ";" )
```

El primer bloque parte de 64 ceros. En el JSON se guardan `hash_previo` (16 caracteres) y `hash_actual` (completo). Las rutas que escriben son `registrar_auditoria()` (en `services/auditoria.py`) y se llaman desde el motor y desde los flujos biométricos.

---

## 8. Frontend

El frontend es HTML/JS puro (sin frameworks). Lo sirve FastAPI en `/app/*`.

| Archivo | Función |
|---|---|
| `app_usuario.htm` + `funcion.js` + `diseno-usuario.css` | App del cliente: login, crear cuenta (con cámara), nuevo equipo, transferir, pagar QR, movimientos, alertas push |
| `consola_mitnick.html` + `consola_mitnick.js` + `consola_mitnick.css` | Consola SOC: login, KPIs, gráfica de decisiones, monitor de transacciones, expediente forense, simulador |

- La URL de la API está en `funcion.js` (`CONFIG.API`) y en `consola_mitnick.js` (`const API`). Ambas apuntan a `http://127.0.0.1:8081`; **si cambias el puerto, cámbialo en los dos**.
- La consola consulta `/estado_completo` cada 1,2 s y solo redibuja lo que cambió.
- Una pantalla nueva: copia el `.html` (y su css/js) a `frontend/`; queda disponible en `/app/<archivo>`.

---

## 9. Configuración (`app/config.py`)

| Constante | Valor por defecto | Qué controla |
|---|---|---|
| `TOPE_POR_OPERACION` | 2.000.000 | Máximo por transferencia |
| `TOPE_DIARIO_CLIENTE` | 5.000.000 | Máximo acumulado por día |
| `UMBRAL_MONTO_ALTO` | 800.000 | Monto mínimo para la regla de cuenta mula |
| `UMBRAL_SIMILITUD_FACIAL` | 72 | % mínimo para aceptar un rostro |
| `UMBRAL_RECHAZO` | 0.82 | Puntaje desde el cual se rechaza |
| `UMBRAL_DESAFIO` | 0.30 | Puntaje desde el cual se desafía |
| `LIMITE_SLA_MS` | 300 | Límite de latencia mostrado en métricas |
| `ANALISTAS_AUTORIZADOS` | 2 analistas | Credenciales del SOC |

**Variables de entorno (opcionales)**

| Variable | Defecto | Uso |
|---|---|---|
| `MITNICK_HOST` | `127.0.0.1` | Host de escucha |
| `MITNICK_PORT` | `8081` | Puerto |
| `MITNICK_HSM_KEY` | clave demo | Clave para firmar los HMAC |
| `MITNICK_DATA_DIR` | `./data` | Dónde guardar bóveda y auditoría |

Ejemplo: `MITNICK_PORT=9000 python run.py` (recuerda cambiar la URL en los dos `.js`).

---

## 10. Cómo extender el proyecto

**Agregar un endpoint a un módulo existente** (`app/routers/soc.py`):
```python
@router.get("/usuarios/{cid}")
def ver_usuario(cid: str):
    return estado.boveda_usuarios.get(cid) or {"error": "No existe"}
```

**Crear un grupo nuevo de endpoints**
1. Crea `app/routers/reportes.py` con `router = APIRouter(tags=["Reportes"])`.
2. Impórtalo en `app/main.py` y agrégalo a la lista `ROUTERS`.

**Agregar una regla antifraude** — en `evaluar_transaccion_automatica()` (`services/motor.py`):
```python
if monto == 1_000_000:
    puntaje += 0.20
    razones.append("Monto redondo sospechoso")
```

**Agregar un campo a un body** — añádelo a la clase en `app/schemas.py`:
```python
class TransaccionIn(Entrada):
    ...
    canal: str = "app"
```

**Agregar un campo a los usuarios** — en `crear_estructura_usuario()` (`services/boveda.py`) y, para bóvedas ya guardadas, en el diccionario `defectos` de `cargar_boveda()`, que completa los campos faltantes (migración).

**Cambiar umbrales o topes** — solo `app/config.py`.

---

## 11. Probar desde la terminal

```bash
# Salud
curl http://127.0.0.1:8081/health

# Login
curl -X POST http://127.0.0.1:8081/login_usuario \
  -H "Content-Type: application/json" \
  -d '{"identificador":"C001","pin":"1234"}'

# Transferencia
curl -X POST http://127.0.0.1:8081/ejecutar_transaccion \
  -H "Content-Type: application/json" \
  -d '{"id_cliente":"C001","destino":"Rappi","monto":50000}'

# Provocar un desafío (otra ciudad) y un rechazo (phishing)
curl -X POST http://127.0.0.1:8081/ejecutar_transaccion -H "Content-Type: application/json" \
  -d '{"id_cliente":"C001","destino":"X","monto":100000,"ciudad_tx":"Cali"}'
curl -X POST http://127.0.0.1:8081/ejecutar_transaccion -H "Content-Type: application/json" \
  -d '{"id_cliente":"C001","destino":"https://premio-falso.co","monto":500000,"ciudad_tx":"Miami"}'
```

---

## 12. Problemas comunes

| Síntoma | Solución |
|---|---|
| `ModuleNotFoundError: No module named 'uvicorn'` | Falta instalar: `pip install -r requirements.txt` (mejor dentro de un `venv`) |
| `externally-managed-environment` al instalar | Usa un entorno virtual (ver sección 1) |
| `Address already in use` | Otro proceso usa el puerto 8081: ciérralo o cambia `MITNICK_PORT` (y la URL en los `.js`) |
| La cámara no se activa | Abre la app por `http://127.0.0.1:8081/usuario` (no `file://`) y acepta el permiso del navegador |
| La consola dice "No se pudo conectar" | El servidor no está corriendo o el puerto de los `.js` no coincide |
| Quiero empezar de cero | Botón **Reiniciar Demo** en la consola, o `POST /reiniciar_sistema`, o borrar la carpeta `data/` |

---

## 13. Notas de seguridad (es una demo)

Antes de usar algo parecido fuera de un entorno controlado:
- El PIN se guarda y se devuelve en **texto plano**; usa hash con sal (bcrypt/argon2).
- `/estado_completo` y el login devuelven el usuario completo (PIN, vector facial, foto). Filtra esos campos.
- Los endpoints del SOC (`/estado_completo`, `/accion_analista`, `/reiniciar_sistema`, `/simular_trafico`) **no exigen autenticación**: agrega tokens/sesiones.
- Las credenciales de analistas y la clave HMAC están en código/valores por defecto; muévelas a un gestor de secretos.
- CORS está abierto (`*`); restríngelo a tus dominios.
- El estado en memoria y el archivo JSON no soportan varios procesos/réplicas; usa una base de datos.