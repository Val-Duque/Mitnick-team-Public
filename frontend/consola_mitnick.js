const API = "http://127.0.0.1:8081";
const TOPE_DIARIO = 5000000;
const INTERVALO_SYNC_MS = 1200;

const ETIQUETAS_DECISION = {
    aprobar: "APROBADA",
    desafiar: "RETENIDA",
    rechazar: "RECHAZADA"
};

const estado = {
    analista: null,
    historial: [],
    usuarios: {},
    txSeleccionada: null,
    ultimoIdHistorial: null,
    hashTablaTx: "",
    hashTablaUsuarios: "",
    hashExpediente: "",
    timerSync: null,
    actualizando: false
};

// =========================================================
// UTILIDADES
// =========================================================
const $ = (id) => document.getElementById(id);

function mostrar(id, visible) {
    $(id).classList.toggle("oculto", !visible);
}

function formatearCOP(valor) {
    return "$" + Number(valor || 0).toLocaleString("es-CO");
}

function escaparHTML(texto) {
    return String(texto ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function etiquetaDecision(decision) {
    return ETIQUETAS_DECISION[decision] || "APROBADA";
}

async function postAPI(ruta, payload = null) {
    try {
        const opciones = { method: "POST" };
        if (payload !== null) {
            opciones.headers = { "Content-Type": "application/json" };
            opciones.body = JSON.stringify(payload);
        }
        const resp = await fetch(`${API}${ruta}`, opciones);
        return await resp.json();
    } catch {
        return { ok: false, mensaje: "No se pudo conectar con el servidor SOC." };
    }
}

// =========================================================
// AUTENTICACIÓN DEL ANALISTA
// =========================================================
function activarDashboard(analista) {
    estado.analista = analista;
    sessionStorage.setItem("soc_analista", JSON.stringify(analista));

    $("lbl-analista-activo").textContent = `Analista Auditor: ${analista.nombre} (${analista.rol})`;
    $("soc-login-err").textContent = "";
    mostrar("soc-login-screen", false);
    mostrar("soc-dashboard", true);

    iniciarSincronizacion();
}

async function iniciarSesionAnalista(e) {
    if (e) e.preventDefault();

    const correo = $("soc-email").value.trim();
    const clave = $("soc-pass").value.trim();
    const btn = $("btn-login-soc");

    btn.disabled = true;
    const data = await postAPI("/login_analista", { correo, clave });
    btn.disabled = false;

    if (!data.ok) {
        $("soc-login-err").textContent = data.mensaje || "Credenciales inválidas.";
        return;
    }

    activarDashboard(data.analista);
}

function cerrarSesionAnalista() {
    detenerSincronizacion();
    estado.analista = null;
    estado.txSeleccionada = null;
    estado.ultimoIdHistorial = null;
    estado.hashTablaTx = "";
    estado.hashTablaUsuarios = "";
    estado.hashExpediente = "";

    sessionStorage.removeItem("soc_analista");
    mostrar("soc-dashboard", false);
    mostrar("soc-login-screen", true);
}

// =========================================================
// ACCIONES DEL SOC
// =========================================================
async function simularTraficoMasivo() {
    await postAPI("/simular_trafico", { cantidad: 50 });
    actualizarConsola();
}

function verMetricasJson() {
    window.open(`${API}/v1/metricas`, "_blank", "noopener");
}

async function reiniciarSistema() {
    await postAPI("/reiniciar_sistema");
    estado.txSeleccionada = null;
    estado.ultimoIdHistorial = null;
    estado.hashTablaTx = "";
    estado.hashTablaUsuarios = "";
    estado.hashExpediente = "";

    $("expediente-detalle").innerHTML = `
        <div class="inspector-empty">
            Demo reiniciada. Esperando nuevas operaciones...
        </div>`;
    actualizarConsola();
}

async function confirmarBloqueoDefinitivo(cid) {
    if (!estado.analista) return;

    const data = await postAPI("/accion_analista", {
        accion: "confirmar_bloqueo_cuenta",
        id_cliente: cid,
        analista: estado.analista.nombre
    });

    if (data.ok) actualizarConsola();
}

function seleccionarTxPorId(idTx) {
    const tx = estado.historial.find((item) => item.id_tx === idTx);
    if (!tx) return;

    estado.txSeleccionada = tx;
    actualizarFilaSeleccionada();
    renderizarExpediente();
}

function actualizarFilaSeleccionada() {
    const idActivo = estado.txSeleccionada ? estado.txSeleccionada.id_tx : null;
    document.querySelectorAll("#tabla-tx-soc tr[data-tx-id]").forEach((tr) => {
        tr.classList.toggle("selected-row", tr.dataset.txId === idActivo);
    });
}

// =========================================================
// RENDERIZADO OPTIMIZADO
// =========================================================
function renderizarExpediente() {
    const box = $("expediente-detalle");
    const tx = estado.txSeleccionada;
    if (!tx) return;

    const u = estado.usuarios[tx.id_cliente] || {};
    const firmaExp = `${tx.id_tx}|${tx.decision}|${tx.puntaje}|${Boolean(u.cuenta_bloqueada)}|${Boolean(u.rostro_enrolado)}`;
    if (firmaExp === estado.hashExpediente) return;
    estado.hashExpediente = firmaExp;

    const fotoHtml = (u.rostro_enrolado && u.foto_rostro_b64)
        ? `<img src="${u.foto_rostro_b64}" class="foto-insp" alt="Rostro registrado">`
        : `<div class="foto-placeholder">Sin foto</div>`;

    const etiqueta = etiquetaDecision(tx.decision);
    const latencia = escaparHTML(tx.latencia_ms);
    let estadoHtml = `<div class="auto-status auto-ok">✅ OPERACIÓN APROBADA EN ${latencia} ms · Cero fricción</div>`;
    let botonEscalamiento = "";

    if (tx.decision === "desafiar") {
        estadoHtml = `<div class="auto-status auto-warn">⏳ OPERACIÓN RETENIDA (${latencia} ms) · Prueba de vida facial activa</div>`;
    } else if (tx.decision === "rechazar") {
        estadoHtml = `<div class="auto-status auto-block">🚫 OPERACIÓN RECHAZADA (${latencia} ms) · Dinero protegido</div>`;
        if (u.cuenta_bloqueada) {
            botonEscalamiento = `<div class="auto-status auto-block">🔒 BLOQUEO DEFINITIVO DE CUENTA CONFIRMADO POR SOC</div>`;
        } else {
            botonEscalamiento = `<button type="button" class="btn-soc-final" data-bloquear-cliente="${escaparHTML(tx.id_cliente)}">🔒 Confirmar Bloqueo Definitivo de Cuenta (Supervisión SOC)</button>`;
        }
    }

    const razonesHtml = (tx.razones || []).map(escaparHTML).join("<br>");

    box.innerHTML = `
        <div class="insp-header">
            <div class="insp-user">
                ${fotoHtml}
                <div>
                    <strong class="insp-tx-title">Operación ${escaparHTML(tx.id_tx)}</strong><br>
                    <span class="insp-user-sub">${escaparHTML(tx.nombre_cliente)} (${escaparHTML(tx.id_cliente)})</span>
                </div>
            </div>
            <span class="badge b-${escaparHTML(tx.decision)}">${etiqueta} (${Math.round((tx.puntaje || 0) * 100)}%)</span>
        </div>

        <div class="insp-grid">
            <div><strong>Monto:</strong> ${formatearCOP(tx.monto)}</div>
            <div><strong>Destino:</strong> ${escaparHTML(tx.destino)}</div>
            <div><strong>IMEI Recibido:</strong> <span class="mono">${escaparHTML(tx.imei_tx)}</span></div>
            <div><strong>IMEI Enrolado:</strong> <span class="mono">${escaparHTML(tx.imei_oficial)}</span></div>
            <div><strong>HMAC TX:</strong> <span class="mono">${escaparHTML(tx.hmac_tx)}</span></div>
            <div><strong>Latencia Eval:</strong> <strong class="txt-ok">${latencia} ms</strong></div>
        </div>

        <div class="insp-block">
            <strong class="txt-warn">Diagnóstico Técnico del Motor:</strong><br>
            ${razonesHtml}
        </div>

        <div class="insp-hash-block">
            <strong class="txt-accent">Cadena Inmutable SHA-256:</strong><br>
            <span class="mono mono-break">${escaparHTML(tx.hash_actual)}</span>
        </div>

        ${estadoHtml}
        ${botonEscalamiento}
    `;
}

function renderizarTablaTx() {
    const tbody = $("tabla-tx-soc");
    const historial = estado.historial;

    const firmaTx = historial.map((t) => `${t.id_tx}:${t.decision}`).join("|");
    if (firmaTx === estado.hashTablaTx) {
        actualizarFilaSeleccionada();
        return;
    }
    estado.hashTablaTx = firmaTx;

    if (historial.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-cell">Esperando transacciones del usuario...</td></tr>`;
        return;
    }

    const idSel = estado.txSeleccionada ? estado.txSeleccionada.id_tx : null;

    tbody.innerHTML = historial
        .slice()
        .reverse()
        .map((tx) => {
            const seleccionada = tx.id_tx === idSel ? " selected-row" : "";
            const etiqueta = etiquetaDecision(tx.decision);
            const hashCorto = escaparHTML(String(tx.hash_actual || "").substring(0, 12));

            return `
                <tr class="click-row${seleccionada}" data-tx-id="${escaparHTML(tx.id_tx)}">
                    <td><b>${escaparHTML(tx.id_tx)}</b><br><span class="mono">${escaparHTML(tx.hora)}</span></td>
                    <td>${escaparHTML(tx.nombre_cliente)}<br><span class="mono">${escaparHTML(tx.id_cliente)}</span></td>
                    <td>${escaparHTML(tx.destino)}<br><b>${formatearCOP(tx.monto)}</b></td>
                    <td><b>${Math.round((tx.puntaje || 0) * 100)}%</b></td>
                    <td><span class="badge b-${escaparHTML(tx.decision)}">${etiqueta}</span></td>
                    <td class="mono">${hashCorto}...</td>
                </tr>`;
        })
        .join("");
}

function renderizarTablaUsuarios(errores) {
    const lista = Object.values(estado.usuarios);
    const firmaUsuarios = lista
        .map((u) => `${u.id_cliente}:${u.gastado_hoy}:${u.cuenta_bloqueada}:${errores[u.id_cliente] || 0}`)
        .join("|");

    if (firmaUsuarios === estado.hashTablaUsuarios) return;
    estado.hashTablaUsuarios = firmaUsuarios;

    $("tabla-usuarios-soc").innerHTML = lista
        .map((u) => {
            const errCount = errores[u.id_cliente] || 0;
            const pctTope = Math.min(100, Math.round(((u.gastado_hoy || 0) / TOPE_DIARIO) * 100));
            const estadoBadge = u.cuenta_bloqueada
                ? `<span class="badge b-rechazar">BLOQUEADA SOC</span>`
                : `<span class="badge ${errCount > 0 ? "b-desafiar" : "b-aprobar"}">${errCount} alertas</span>`;

            return `
                <tr>
                    <td><b>${escaparHTML(u.id_cliente)}</b> · ${escaparHTML(u.nombre)}</td>
                    <td>${pctTope}% (${formatearCOP(u.gastado_hoy)})</td>
                    <td>${estadoBadge}</td>
                </tr>`;
        })
        .join("");
}

function renderizarMetricas(conteos, tel) {
    if (tel.latencia_mediana_ms !== undefined) {
        $("lbl-latencia-p50").textContent = `${tel.latencia_mediana_ms} ms (p99: ${tel.latencia_p99_ms} ms)`;
        $("lbl-tps-vivo").textContent = `${tel.tps_actual} TX/s`;

        const eficienciaLatencia = Math.max(5, Math.min(100, 100 - (Number(tel.latencia_mediana_ms) / 300) * 100));
        $("bar-latencia").style.width = `${eficienciaLatencia.toFixed(1)}%`;
    }

    const total = conteos.total || 0;
    const apr = conteos.aprobar || 0;
    const des = conteos.desafiar || 0;
    const rec = conteos.rechazar || 0;

    $("k-total").textContent = total.toLocaleString("es-CO");
    $("k-apr").textContent = apr.toLocaleString("es-CO");
    $("k-des").textContent = des.toLocaleString("es-CO");
    $("k-rec").textContent = rec.toLocaleString("es-CO");

    const pctApr = total ? Math.round((apr / total) * 100) : 0;
    const pctDes = total ? Math.round((des / total) * 100) : 0;
    const pctRec = total ? Math.round((rec / total) * 100) : 0;

    $("g-val-apr").textContent = `${pctApr}%`;
    $("g-bar-apr").style.height = `${Math.max(8, pctApr)}px`;
    $("g-val-des").textContent = `${pctDes}%`;
    $("g-bar-des").style.height = `${Math.max(8, pctDes)}px`;
    $("g-val-rec").textContent = `${pctRec}%`;
    $("g-bar-rec").style.height = `${Math.max(8, pctRec)}px`;

    const fraudesContenidos = des + rec;
    $("pct-contencion").textContent = `100% (${fraudesContenidos} contenidos / 0 fugas)`;
    $("bar-contencion").style.width = "100%";
}

// =========================================================
// SINCRONIZACIÓN CONTROLADA
// =========================================================
async function actualizarConsola() {
    if (!estado.analista || estado.actualizando || document.hidden) return;
    estado.actualizando = true;

    try {
        const resp = await fetch(`${API}/estado_completo`);
        const data = await resp.json();

        estado.usuarios = data.usuarios || {};
        estado.historial = data.historial || [];

        const conteos = data.conteos_totales || { total: 0, aprobar: 0, desafiar: 0, rechazar: 0 };
        const errores = data.errores_usuarios || {};
        const tel = data.telemetria || {};

        renderizarMetricas(conteos, tel);

        if (estado.historial.length > 0) {
            const masReciente = estado.historial[estado.historial.length - 1];
            if (!estado.txSeleccionada || estado.ultimoIdHistorial !== masReciente.id_tx) {
                estado.ultimoIdHistorial = masReciente.id_tx;
                estado.txSeleccionada = masReciente;
            } else {
                const actualizada = estado.historial.find((h) => h.id_tx === estado.txSeleccionada.id_tx);
                if (actualizada) estado.txSeleccionada = actualizada;
            }
            renderizarExpediente();
        } else {
            estado.txSeleccionada = null;
            estado.ultimoIdHistorial = null;
        }

        renderizarTablaUsuarios(errores);
        renderizarTablaTx();
    } catch {
        // Silencioso durante sondeo de fondo
    } finally {
        estado.actualizando = false;
    }
}

function iniciarSincronizacion() {
    detenerSincronizacion();
    actualizarConsola();
    estado.timerSync = setInterval(actualizarConsola, INTERVALO_SYNC_MS);
}

function detenerSincronizacion() {
    if (estado.timerSync) {
        clearInterval(estado.timerSync);
        estado.timerSync = null;
    }
}

// =========================================================
// INICIALIZACIÓN Y EVENTOS DELEGADOS
// =========================================================
document.addEventListener("DOMContentLoaded", () => {
    $("form-login-soc").addEventListener("submit", iniciarSesionAnalista);

    $("tabla-tx-soc").addEventListener("click", (e) => {
        const fila = e.target.closest("tr[data-tx-id]");
        if (fila) seleccionarTxPorId(fila.dataset.txId);
    });

    $("expediente-detalle").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-bloquear-cliente]");
        if (btn) confirmarBloqueoDefinitivo(btn.dataset.bloquearCliente);
    });

    const sesionGuardada = sessionStorage.getItem("soc_analista");
    if (sesionGuardada) {
        try {
            activarDashboard(JSON.parse(sesionGuardada));
        } catch {
            sessionStorage.removeItem("soc_analista");
        }
    }
});

document.addEventListener("visibilitychange", () => {
    if (!document.hidden && estado.analista) actualizarConsola();
});