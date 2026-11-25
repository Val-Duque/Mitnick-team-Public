// =========================================================
// CONFIGURACIÓN Y ESTADO GLOBAL
// =========================================================
const CONFIG = {
    API: "http://127.0.0.1:8081",
    TOPE_DIARIO: 5000000,
    INTERVALO_SYNC_MS: 1200,
    TAM_RECORTE_ROSTRO: 240, // Balance entre nitidez para face_recognition y bajo peso en red
    CALIDAD_JPEG: 0.78
};

const estado = {
    usuarios: {},
    notificaciones: {},
    usuarioId: null,
    imeiActual: null,
    streamCam: null,
    timerQR: null,
    timerSync: null,
    sincronizando: false,
    ocupado: false,
    pushActivoId: null,
    ultimoHashMovs: null,
    ultimoIdBloqueado: null
};

// =========================================================
// UTILIDADES GENERALES, FORMATO Y SEGURIDAD HTML
// =========================================================
const $ = (id) => document.getElementById(id);

function mostrar(id, visible) {
    $(id).classList.toggle("oculto", !visible);
}

function formatearCOP(valor) {
    return "$" + Number(valor || 0).toLocaleString("es-CO");
}

function escaparHTML(texto) {
    const amp = "\u0026";
    return String(texto ?? "")
        .replace(/&/g, `${amp}amp;`)
        .replace(/</g, `${amp}lt;`)
        .replace(/>/g, `${amp}gt;`)
        .replace(/"/g, `${amp}quot;`)
        .replace(/'/g, `${amp}#39;`);
}

function mostrarAlerta(zonaId, tipo, titulo, cuerpoHtml) {
    $(zonaId).innerHTML = `<div class="alert alert-${tipo}"><strong>${titulo}</strong><br>${cuerpoHtml}</div>`;
}

// =========================================================
// RED Y DETECCIÓN DE ENTORNO
// =========================================================
async function postAPI(ruta, payload) {
    try {
        const resp = await fetch(`${CONFIG.API}${ruta}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        return await resp.json();
    } catch {
        return {
            ok: false,
            error: "No se pudo conectar con el servidor Yuma Pay.",
            mensaje: "No se pudo conectar con el servidor Yuma Pay."
        };
    }
}

function obtenerHuellaDispositivo(idUsuario) {
    return localStorage.getItem(`yuma_hw_imei_${idUsuario.toUpperCase()}`) || "";
}

async function detectarIncognito() {
    if ("storage" in navigator && "estimate" in navigator.storage) {
        const { quota } = await navigator.storage.estimate();
        return Boolean(quota && quota < 120000000);
    }
    return false;
}

// =========================================================
// CÁMARA Y CAPTURA BIOMÉTRICA (COMPATIBLE CON PYTHON)
// =========================================================
function detenerCam() {
    if (estado.timerQR) {
        clearInterval(estado.timerQR);
        estado.timerQR = null;
    }
    if (estado.streamCam) {
        estado.streamCam.getTracks().forEach((t) => t.stop());
        estado.streamCam = null;
    }
}

async function encenderCamara(videoId, opcionesVideo = true) {
    detenerCam();
    const vid = $(videoId);
    try {
        estado.streamCam = await navigator.mediaDevices.getUserMedia({ video: opcionesVideo });
        vid.srcObject = estado.streamCam;
        mostrar(videoId, true);
        return true;
    } catch {
        alert("Permite el acceso a la cámara web.");
        return false;
    }
}

function calcularVectorLigero(videoEl, sx, sy, minDim) {
    const size = 16;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    ctx.filter = "blur(1px)";
    ctx.drawImage(videoEl, sx, sy, minDim, minDim, 0, 0, size, size);

    const data = ctx.getImageData(0, 0, size, size).data;
    const vec = [];
    let suma = 0;

    for (let i = 0; i < data.length; i += 4) {
        const gris = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
        vec.push(gris);
        suma += gris;
    }

    const prom = suma / vec.length;
    const varianza = vec.reduce((acc, v) => acc + (v - prom) ** 2, 0) / vec.length;
    const desv = Math.sqrt(varianza) || 1;
    return vec.map((v) => Math.round(((v - prom) / desv) * 100) / 100);
}

function capturarDatosFaciales(videoEl) {
    const minDim = Math.min(videoEl.videoWidth, videoEl.videoHeight) * 0.65;
    const sx = (videoEl.videoWidth - minDim) / 2;
    const sy = (videoEl.videoHeight - minDim) / 2;

    const fotoCanvas = document.createElement("canvas");
    fotoCanvas.width = CONFIG.TAM_RECORTE_ROSTRO;
    fotoCanvas.height = CONFIG.TAM_RECORTE_ROSTRO;
    fotoCanvas.getContext("2d").drawImage(
        videoEl,
        sx,
        sy,
        minDim,
        minDim,
        0,
        0,
        CONFIG.TAM_RECORTE_ROSTRO,
        CONFIG.TAM_RECORTE_ROSTRO
    );

    return {
        vector: calcularVectorLigero(videoEl, sx, sy, minDim),
        foto_b64: fotoCanvas.toDataURL("image/jpeg", CONFIG.CALIDAD_JPEG)
    };
}

function validarYCapturarCamara(videoId, zonaMsg, instruccionHtml) {
    const vid = $(videoId);
    if (!vid || vid.classList.contains("oculto") || vid.videoWidth === 0) {
        mostrarAlerta(zonaMsg, "warn", "📸 Cámara Requerida", instruccionHtml);
        return null;
    }
    const captura = capturarDatosFaciales(vid);
    detenerCam();
    mostrar(videoId, false);
    return captura;
}

// =========================================================
// NAVEGACIÓN Y BLOQUEO DE CUENTA
// =========================================================
function verTabAuth(tab, el) {
    detenerCam();
    document.querySelectorAll("#pantalla-login .tab").forEach((t) => t.classList.remove("active"));
    if (el) el.classList.add("active");

    ["login", "crear", "recuperar"].forEach((nombre) => mostrar(`auth-${nombre}`, nombre === tab));
    mostrar("vid-reg", false);
    mostrar("vid-rec", false);
    $("zona-msg-auth").innerHTML = "";
}

function verTabApp(nombre, el) {
    detenerCam();
    document.querySelectorAll("#pantalla-app .tab").forEach((t) => t.classList.remove("active"));
    if (el) el.classList.add("active");

    ["transferir", "qr", "movimientos"].forEach((tab) => mostrar(`tab-${tab}`, tab === nombre));
    mostrar("vid-qr", false);
    $("zona-mensaje").innerHTML = "";
    renderizarMovimientos();
}

function irARecuperarCuenta() {
    const tabRec = document.querySelector('#pantalla-login .tab[onclick*="recuperar"]');
    verTabAuth("recuperar", tabRec);
    if (estado.ultimoIdBloqueado && $("rec-id")) {
        $("rec-id").value = estado.ultimoIdBloqueado;
    }
}

function notificarBloqueoCuenta({
    idUsuario = "",
    titulo = "🔒 Cuenta Bloqueada Preventivamente",
    motivo = "Tu cuenta fue congelada por el Centro de Operaciones (SOC) por actividad inusual.",
    origen = "Sistema de Seguridad Yuma Pay"
} = {}) {
    estado.ultimoIdBloqueado = idUsuario || "";

    const idSeguro = escaparHTML(idUsuario || "N/D");
    const motivoSeguro = escaparHTML(motivo);
    const origenSeguro = escaparHTML(origen);
    const hora = new Date().toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });

    if (estado.usuarioId) {
        cerrarSesionUsuario();
    }

    const cuerpoHtml = `
        <div style="margin-top: 6px; line-height: 1.45;">
            <p style="margin: 0 0 8px 0;">${motivoSeguro}</p>
            <div style="font-size: 0.85em; padding: 8px; background: rgba(0, 0, 0, 0.06); border-radius: 6px; margin-bottom: 10px;">
                <div><strong>Cuenta afectada:</strong> ${idSeguro}</div>
                <div><strong>Origen:</strong> ${origenSeguro} · ${hora}</div>
            </div>
            <button type="button" class="btn" style="width: 100%;" onclick="irARecuperarCuenta()">
                🪪 Validar Identidad y Desbloquear
            </button>
        </div>
    `;

    mostrarAlerta("zona-msg-auth", "err", titulo, cuerpoHtml);
}

// =========================================================
// SESIÓN, REGISTRO Y RECUPERACIÓN
// =========================================================
function abrirAppConUsuario(usuario, imei) {
    estado.usuarioId = usuario.id_cliente;
    estado.imeiActual = imei;
    estado.ultimoHashMovs = null;

    mostrar("pantalla-login", false);
    mostrar("pantalla-app", true);
    $("tx-ciudad").value = usuario.ciudad_habitual;

    iniciarSincronizacion();
}

async function iniciarSesionUsuario() {
    if (estado.ocupado) return;
    estado.ocupado = true;

    try {
        const identificador = $("log-id").value.trim();
        const pin = $("log-pin").value.trim();
        const es_incognito = await detectarIncognito();
        const imei_sesion = es_incognito ? "" : obtenerHuellaDispositivo(identificador);

        const data = await postAPI("/login_usuario", { identificador, pin, imei_sesion, es_incognito });
        if (!data.ok) {
            const esBloqueo = Boolean(data.cuenta_bloqueada) ||
                (data.mensaje && data.mensaje.toLowerCase().includes("bloqueada"));

            if (esBloqueo) {
                notificarBloqueoCuenta({
                    idUsuario: identificador.toUpperCase(),
                    titulo: "🔒 Acceso Restringido · Cuenta Bloqueada",
                    motivo: data.mensaje,
                    origen: "Control de Acceso"
                });
            } else {
                mostrarAlerta("zona-msg-auth", "err", "🚫 Acceso Denegado", escaparHTML(data.mensaje));
            }
            return;
        }

        let imeiFinal = data.imei_sesion;
        if (!es_incognito) {
            localStorage.setItem(`yuma_hw_imei_${data.usuario.id_cliente}`, data.usuario.imei_vinculado);
            imeiFinal = data.usuario.imei_vinculado;
        }

        abrirAppConUsuario(data.usuario, imeiFinal);
    } finally {
        estado.ocupado = false;
    }
}

async function registrarUsuario() {
    if (estado.ocupado) return;

    const captura = validarYCapturarCamara(
        "vid-reg",
        "zona-msg-auth",
        'Primero presiona <b>"Activar Cámara para Registrar Rostro"</b> para capturar tu foto y enviarla a verificación.'
    );
    if (!captura) return;

    estado.ocupado = true;
    try {
        const payload = {
            nombre: $("reg-nombre").value.trim() || "Nuevo Cliente Yuma",
            correo: $("reg-correo").value.trim(),
            pin: $("reg-pin").value.trim() || "1234",
            ciudad: $("reg-ciudad").value,
            saldo: Number($("reg-saldo").value || 2500000),
            p1: $("reg-p1").value.trim() || "medellin",
            p2: $("reg-p2").value.trim() || "max",
            p3: $("reg-p3").value.trim() || "1234",
            vector_facial: captura.vector,
            foto_b64: captura.foto_b64
        };

        const data = await postAPI("/registrar_usuario", payload);
        if (!data.ok) {
            mostrarAlerta("zona-msg-auth", "err", "🚫 Error de Registro", escaparHTML(data.mensaje));
            return;
        }

        const idCreado = data.usuario.id_cliente;
        localStorage.setItem(`yuma_hw_imei_${idCreado}`, data.usuario.imei_vinculado);

        mostrarAlerta(
            "zona-msg-auth",
            "ok",
            `🪪 Cuenta Creada (${escaparHTML(idCreado)})`,
            `Rostro procesado y dispositivo vinculado.<br>Inicia sesión con ID <b>${escaparHTML(idCreado)}</b>.`
        );
        $("log-id").value = idCreado;
        $("log-pin").value = payload.pin;
    } finally {
        estado.ocupado = false;
    }
}

async function verificarPreguntasYRecuperar() {
    if (estado.ocupado) return;

    const captura = validarYCapturarCamara(
        "vid-rec",
        "zona-msg-auth",
        'Primero presiona <b>"Activar Cámara para Cotejo Facial"</b> para verificar tu rostro.'
    );
    if (!captura) return;

    estado.ocupado = true;
    try {
        const data = await postAPI("/recuperar_dispositivo", {
            identificador: $("rec-id").value.trim(),
            r1: $("rec-p1").value.trim(),
            r2: $("rec-p2").value.trim(),
            r3: $("rec-p3").value.trim(),
            vector_facial: captura.vector,
            foto_b64: captura.foto_b64
        });

        if (!data.ok) {
            mostrarAlerta("zona-msg-auth", "err", "🚫 Validación Fallida", escaparHTML(data.mensaje));
            return;
        }

        data.usuario.cuenta_bloqueada = false;
        estado.usuarios[data.usuario.id_cliente] = data.usuario;
        estado.ultimoIdBloqueado = null;

        localStorage.setItem(`yuma_hw_imei_${data.usuario.id_cliente}`, data.nuevo_imei);
        abrirAppConUsuario(data.usuario, data.nuevo_imei);
        mostrarAlerta(
            "zona-mensaje",
            "ok",
            `✅ Cuenta Desbloqueada y Equipo Vinculado (${escaparHTML(data.nuevo_imei)})`,
            `Preguntas y cotejo facial (${escaparHTML(data.similitud)}%) aprobados.`
        );
    } finally {
        estado.ocupado = false;
    }
}

function cerrarSesionUsuario() {
    detenerSincronizacion();
    detenerCam();

    estado.usuarioId = null;
    estado.imeiActual = null;
    estado.pushActivoId = null;
    estado.ultimoHashMovs = null;
    estado.ocupado = false;

    mostrar("pantalla-app", false);
    mostrar("pantalla-login", true);
    $("zona-push").innerHTML = "";
    $("zona-msg-auth").innerHTML = "";
    $("zona-mensaje").innerHTML = "";
}

// =========================================================
// RENDERIZADO DE PERFIL, MOVIMIENTOS Y PUSH
// =========================================================
function renderizarMovimientos() {
    const u = estado.usuarios[estado.usuarioId];
    if (!u) return;

    const movs = u.movimientos || [];
    const hashActual = `${movs.length}:${movs.map((m) => m.id_tx).join(",")}`;
    if (hashActual === estado.ultimoHashMovs) return;
    estado.ultimoHashMovs = hashActual;

    let totalRecibido = 0;
    let totalEnviado = 0;
    for (const m of movs) {
        if (m.tipo === "entrada") totalRecibido += Number(m.monto || 0);
        else totalEnviado += Number(m.monto || 0);
    }

    $("lbl-total-recibido").textContent = "+" + formatearCOP(totalRecibido);
    $("lbl-total-enviado").textContent = "-" + formatearCOP(totalEnviado);

    const cont = $("lista-movimientos");
    if (!movs.length) {
        cont.innerHTML = `<div class="mov-vacio">Aún no tienes movimientos registrados en tu cuenta.</div>`;
        return;
    }

    cont.innerHTML = movs.map((m) => {
        const esEntrada = m.tipo === "entrada";
        const icono = esEntrada ? "⬇️" : "⬆️";
        const contraparte = escaparHTML(m.contraparte);
        const titulo = esEntrada ? `Recibido de ${contraparte}` : `Enviado a ${contraparte}`;
        const signo = esEntrada ? "+" : "-";
        const claseMonto = esEntrada ? "monto-in" : "monto-out";

        return `
            <div class="mov-item">
                <div>
                    <div class="mov-titulo">${icono} ${titulo}</div>
                    <div class="mov-meta">${escaparHTML(m.fecha)} · ${escaparHTML(m.hora)} · ${escaparHTML(m.id_tx)}</div>
                </div>
                <div class="${claseMonto}">${signo}${formatearCOP(m.monto)}</div>
            </div>`;
    }).join("");
}

function renderizarPush(push) {
    const zonaPush = $("zona-push");

    if (!push) {
        if (estado.pushActivoId) {
            estado.pushActivoId = null;
            detenerCam();
        }
        zonaPush.innerHTML = "";
        return;
    }

    if (estado.pushActivoId === push.id_tx) return;
    estado.pushActivoId = push.id_tx;

    zonaPush.innerHTML = `
        <div class="push-overlay">
            <div class="push-header">
                <span>🔔 VERIFICACIÓN FACIAL REQUERIDA</span>
                <span>${escaparHTML(push.timestamp)}</span>
            </div>
            <div class="push-body">
                <strong>${escaparHTML(push.enviado_por)}</strong> solicita cotejar tu rostro para autorizar <b>${formatearCOP(push.monto)}</b> hacia <b>${escaparHTML(push.destino)}</b>.<br>
                <small>Motivo: ${escaparHTML(push.motivo)}</small>
            </div>
            <video id="vid-push-live" class="selfie vid-push" autoplay playsinline></video>
            <div class="row-2">
                <button type="button" class="btn btn-green" onclick="verificarPushConCamara()">📸 Verificar Rostro</button>
                <button type="button" class="btn btn-red" onclick="rechazarPush()">❌ No fui yo</button>
            </div>
        </div>`;

    navigator.mediaDevices.getUserMedia({ video: true }).then((s) => {
        estado.streamCam = s;
        const vp = $("vid-push-live");
        if (vp) vp.srcObject = s;
    }).catch(() => {});
}

function renderizarPerfil() {
    const u = estado.usuarios[estado.usuarioId];
    if (!u) return;

    if (u.cuenta_bloqueada) {
        notificarBloqueoCuenta({
            idUsuario: u.id_cliente,
            titulo: "🔒 Cuenta Bloqueada por SOC",
            motivo: u.motivo_bloqueo || "Tu cuenta fue congelada preventivamente por el Centro de Operaciones.",
            origen: "Monitoreo SOC en tiempo real"
        });
        return;
    }

    $("lbl-saludo").textContent = `${u.id_cliente} · ${u.nombre}`;
    $("lbl-saldo").textContent = formatearCOP(u.saldo);
    $("lbl-imei").textContent = `IMEI: ${estado.imeiActual}`;
    $("lbl-ciudad").textContent = `📍 ${u.ciudad_habitual}`;
    $("lbl-gastado").textContent = formatearCOP(u.gastado_hoy);

    const pctTope = Math.min(100, Math.round(((u.gastado_hoy || 0) / CONFIG.TOPE_DIARIO) * 100));
    $("bar-tope").style.width = `${pctTope}%`;

    renderizarMovimientos();
    renderizarPush(estado.notificaciones[estado.usuarioId]);
}

// =========================================================
// OPERACIONES Y VERIFICACIÓN EN VIVO
// =========================================================
async function verificarPushConCamara() {
    if (estado.ocupado) return;
    const captura = validarYCapturarCamara("vid-push-live", "zona-mensaje", "Activa la cámara para verificar.");
    if (!captura) return;

    estado.ocupado = true;
    estado.pushActivoId = null;
    $("zona-push").innerHTML = "";

    try {
        const data = await postAPI("/verificar_rostro_en_vivo", {
            id_cliente: estado.usuarioId,
            vector_facial: captura.vector,
            foto_b64: captura.foto_b64
        });

        if (data.cerrar_sesion) {
            notificarBloqueoCuenta({
                idUsuario: estado.usuarioId,
                titulo: "🚨 Cuenta Bloqueada por Suplantación",
                motivo: data.mensaje || "El rostro capturado no coincide con el titular registrado.",
                origen: "Verificación Biométrica en Vivo"
            });
        } else {
            mostrarAlerta("zona-mensaje", "ok", "✅ IDENTIDAD CONFIRMADA", escaparHTML(data.mensaje));
            sincronizar();
        }
    } finally {
        estado.ocupado = false;
    }
}

async function rechazarPush() {
    detenerCam();
    estado.pushActivoId = null;
    $("zona-push").innerHTML = "";

    await postAPI("/consumir_notificacion", { id_cliente: estado.usuarioId });
    mostrarAlerta("zona-mensaje", "err", "🛑 Operación Cancelada", "Has bloqueado esta transacción preventiva.");
}

async function activarCamaraQR() {
    const encendida = await encenderCamara("vid-qr", { facingMode: "environment" });
    if (!encendida || !("BarcodeDetector" in window)) return;

    const vid = $("vid-qr");
    const detector = new BarcodeDetector({ formats: ["qr_code"] });

    estado.timerQR = setInterval(async () => {
        try {
            const codes = await detector.detect(vid);
            if (codes.length > 0) {
                $("qr-destino").value = codes[0].rawValue;
                detenerCam();
                mostrar("vid-qr", false);
            }
        } catch {}
    }, 350);
}

async function realizarOperacion(esQR) {
    if (estado.ocupado) return;
    estado.ocupado = true;

    try {
        const payload = {
            id_cliente: estado.usuarioId,
            tipo_op: esQR ? "pago_qr" : "transferencia_inmediata",
            monto: Number($(esQR ? "qr-monto" : "tx-monto").value),
            destino: $(esQR ? "qr-destino" : "tx-destino").value.trim(),
            ciudad_tx: $("tx-ciudad").value,
            imei_tx: estado.imeiActual
        };

        const r = await postAPI("/ejecutar_transaccion", payload);
        if (r.error) {
            mostrarAlerta("zona-mensaje", "err", "⚠️ Error", escaparHTML(r.error));
            return;
        }

        const idTx = escaparHTML(r.id_tx);
        if (r.decision === "aprobar") {
            mostrarAlerta(
                "zona-mensaje",
                "ok",
                `✅ Operación Exitosa (${idTx})`,
                `Envío de <b>${formatearCOP(r.monto)}</b> a <b>${escaparHTML(r.destino)}</b> completado al instante.`
            );
        } else if (r.decision === "desafiar") {
            mostrarAlerta(
                "zona-mensaje",
                "warn",
                `⏳ Transferencia Retenida (${idTx})`,
                "Completa la verificación facial superior para liberar el dinero."
            );
        } else {
            const razones = (r.razones || []).map(escaparHTML).join("<br>");
            mostrarAlerta("zona-mensaje", "err", `🚫 Operación Bloqueada (${idTx})`, razones);
        }

        sincronizar();
    } finally {
        estado.ocupado = false;
    }
}

// =========================================================
// SINCRONIZACIÓN CONTROLADA
// =========================================================
async function sincronizar() {
    if (!estado.usuarioId || estado.sincronizando || document.hidden) return;
    estado.sincronizando = true;

    try {
        const resp = await fetch(`${CONFIG.API}/estado_completo`);
        const data = await resp.json();
        estado.usuarios = data.usuarios || {};
        estado.notificaciones = data.notificaciones || {};
        renderizarPerfil();
    } catch {
        // Silencioso durante sondeo de fondo
    } finally {
        estado.sincronizando = false;
    }
}

function iniciarSincronizacion() {
    detenerSincronizacion();
    sincronizar();
    estado.timerSync = setInterval(sincronizar, CONFIG.INTERVALO_SYNC_MS);
}

function detenerSincronizacion() {
    if (estado.timerSync) {
        clearInterval(estado.timerSync);
        estado.timerSync = null;
    }
}

document.addEventListener("visibilitychange", () => {
    if (!document.hidden && estado.usuarioId) sincronizar();
});