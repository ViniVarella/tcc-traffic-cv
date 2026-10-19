/**
 * TraffIQ — painel web
 * Página única: telemetria por WebSocket, câmeras, gráficos e navegação por âncora.
 */

// ============================================
//  Router
// ============================================
const pages = document.querySelectorAll('.page');
const navLinks = document.querySelectorAll('.nav-link');

function navigateTo(pageId) {
    pages.forEach(p => p.classList.remove('active'));
    navLinks.forEach(l => l.classList.remove('active'));

    const target = document.getElementById(`page-${pageId}`);
    if (target) {
        target.classList.add('active');
        // Scroll main content to top
        document.getElementById('main-content').scrollTop = 0;
    }

    const activeLink = document.querySelector(`.nav-link[data-page="${pageId}"]`);
    if (activeLink) activeLink.classList.add('active');
}

// Handle nav clicks and hash links
document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const pageId = link.getAttribute('href').replace('#', '');
        window.location.hash = pageId;
        navigateTo(pageId);
    });
});

// Handle initial hash
function handleHash() {
    const hash = window.location.hash.replace('#', '') || 'home';
    navigateTo(hash);
}
window.addEventListener('hashchange', handleHash);
handleHash();

// ============================================
//  Conexão com o servidor (telemetria a cada 0,5 s)
// ============================================
let ws = null;
let reconnectTimer = null;
const apiDot = document.getElementById('api-dot');
const sumoDot = document.getElementById('sumo-dot');
const unityDot = document.getElementById('unity-dot');

function setBadge(dot, cls, text) {
    dot.className = 'status-dot ' + cls;
    dot.parentElement.lastChild.textContent = ' ' + text;
}

function connectWS() {
    ws = new WebSocket(`ws://${window.location.host}/ws/telemetry`);
    ws.onopen = () => {
        setBadge(apiDot, 'online', 'Conectado');
        clearTimeout(reconnectTimer);
    };
    ws.onclose = () => {
        setBadge(apiDot, 'offline', 'Desconectado');
        setBadge(sumoDot, 'offline', 'Parada');
        reconnectTimer = setTimeout(connectWS, 3000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (event) => updateTelemetry(JSON.parse(event.data));
}

connectWS();

// ============================================
//  Telemetria & Benchmarks
// ============================================
// vision = o que a IA vê pelas câmeras; ground_truth = medido pelo simulador, só para mostrar.
let isRunning = false;
let lastSimTime = null;
let lastError = null;
let chartData = { timestamps: [], waitingTimes: [], haltingVehicles: [], phaseCounters: {} };
const MAX_CHART_POINTS = 300;
const APPROACHES = ['west', 'south', 'east'];

// Espera por veículo do tempo fixo na avaliação oficial, por cenário, e a amostra
// mínima antes de mostrar a redução: vêm de /api/options (fonte única no backend).
let fixedTimeReferenceS = {};
let minSampleS = 600;
let runningRequest = null;  // cenário e controlador em execução (data.request)
let lastDispatchedCount = -1;

/** Referência do tempo fixo do cenário em execução ou, parado, do selecionado. */
function fixedTimeReference() {
    const scenario = isRunning && runningRequest ? runningRequest.scenario : selScenario.value;
    return fixedTimeReferenceS[scenario] ?? null;
}

function updateReferenceLabels() {
    const reference = fixedTimeReference();
    const text = reference == null ? '—' : reference.toFixed(1) + ' s';
    document.getElementById('legend-baseline-val').textContent = text;
    document.getElementById('kpi-baseline-ref').textContent = `tempo fixo na avaliação: ${text}`;
}

const PHASE_LABELS = {
    EAST_WEST_GREEN: 'Verde para Leste e Oeste', EAST_WEST_YELLOW: 'Amarelo para Leste e Oeste',
    ALL_RED: 'Vermelho geral', SOUTH_GREEN: 'Verde para o Sul', SOUTH_YELLOW: 'Amarelo para o Sul',
    PEDESTRIAN_GREEN: 'Travessia de pedestres', PEDESTRIAN_CLEARANCE: 'Liberação da travessia'
};
// Verde que a prioridade segura → ruas atendidas.
const PRIORITY_APPROACHES = { EAST_WEST_GREEN: ['east', 'west'], SOUTH_GREEN: ['south'] };
const APPROACH_LABELS = { south: 'Sul', east: 'Leste', west: 'Oeste' };
const EXIT_LABELS = { north: 'Norte', east: 'Leste', west: 'Oeste' };
let emergencyRoutes = {};
let announceBeforeS = null;
// Ambulância acionada pelo botão: a contagem até ela entrar na via segue o
// relógio da simulação (sim_time do registro em `dispatched`).
let pendingAmbulance = null;

function updateAmbulanceCountdown(dispatched, simTime) {
    if (!pendingAmbulance || announceBeforeS == null) return;
    if (pendingAmbulance.enterAt == null) {
        if (dispatched.length <= pendingAmbulance.countBefore) return;  // o servidor ainda não processou o pedido
        pendingAmbulance.enterAt = dispatched[dispatched.length - 1].sim_time + announceBeforeS;
    }
    const remaining = Math.ceil(pendingAmbulance.enterAt - simTime);
    const base = `🚑 Ambulância acionada (${pendingAmbulance.route}). Aviso de aproximação enviado ao semáforo.`;
    if (remaining > 0) {
        showMessage(`${base} Entrada na via em ${remaining} s.`);
    } else {
        showMessage(`🚑 Ambulância na via (${pendingAmbulance.route}).`);
        pendingAmbulance = null;
    }
}

function formatClock(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function updateCameras(t) {
    const priority = PRIORITY_APPROACHES[t.preempt_target] || [];
    for (const approach of APPROACHES) {
        const color = t.signals ? t.signals[approach] : '';
        const card = document.querySelector(`.camera-card[data-camera="${approach}"]`);
        card.classList.remove('signal-green', 'signal-yellow', 'signal-red');
        if (color) card.classList.add('signal-' + color);
        card.classList.toggle('priority', priority.includes(approach));
        document.getElementById('signal-' + approach).className = 'signal-light ' + (color || '');
        // Parados vistos pela câmera ("—" num instante sem imagem).
        const stopped = t.vision ? t.vision[approach].stopped : null;
        const count = document.getElementById('stopped-' + approach);
        count.textContent = stopped == null ? '—' : stopped;
        count.nextSibling.textContent = stopped === 1 ? ' parado' : ' parados';
    }
    if (modalCamera && t.signals) {
        document.getElementById('modal-signal').className = 'signal-light ' + t.signals[modalCamera];
    }
}

function updateTelemetry(data) {
    const running = data.is_running === true;
    const t = data.telemetry;

    if (running) setBadge(sumoDot, 'online', data.status === 'rodando' ? 'Em execução' : 'Iniciando');
    else setBadge(sumoDot, 'warning', 'Parada');
    if (t && t.vision) setBadge(unityDot, 'online', 'Recebendo imagens');
    else if (running && t) setBadge(unityDot, 'warning', 'Sem imagens');
    else setBadge(unityDot, 'offline', 'Aguardando');

    if (running !== isRunning) {
        isRunning = running;
        updateButtons();
    }
    if (data.error !== lastError) {
        lastError = data.error;
        if (data.error) showMessage('Erro: ' + data.error);
    }
    const dispatchedList = data.dispatched || [];
    if (dispatchedList.length !== lastDispatchedCount) {
        lastDispatchedCount = dispatchedList.length;
        document.getElementById('val-dispatched').textContent = lastDispatchedCount;
        document.getElementById('kpi-emergency-val').textContent = lastDispatchedCount;
    }
    if (!running) pendingAmbulance = null;
    runningRequest = running ? data.request : null;
    if (!t) return;

    document.getElementById('sim-clock').textContent = formatClock(t.sim_time || 0);
    updateAmbulanceCountdown(dispatchedList, t.sim_time || 0);
    updateCameras(t);
    const gt = t.ground_truth;
    document.getElementById('val-halting').textContent = gt.halting_vehicles;
    document.getElementById('val-wait').textContent = gt.mean_wait_per_stopped_s.toFixed(1) + ' s';
    document.getElementById('phase-name').textContent = PHASE_LABELS[t.phase] || t.phase;
    const priority = PRIORITY_APPROACHES[t.preempt_target];
    document.getElementById('preempt-name').textContent = priority
        ? '🚑 verde para ' + priority.map(a => APPROACH_LABELS[a]).join(' e ') : '—';

    if (running) document.querySelectorAll('.camera-overlay').forEach(el => el.classList.add('hidden'));

    // Um ponto por instante novo da simulação (a telemetria pode repetir o mesmo).
    if (t.sim_time === lastSimTime) return;
    lastSimTime = t.sim_time;
    // Espera por veículo desde o aquecimento: a mesma métrica da avaliação oficial.
    const trip = t.trip || {};
    const meanWait = trip.mean_waiting_time_s;
    chartData.timestamps.push(t.sim_time);
    if (meanWait != null) chartData.waitingTimes.push(meanWait);
    chartData.haltingVehicles.push(gt.halting_vehicles);
    chartData.phaseCounters[t.phase] = (chartData.phaseCounters[t.phase] || 0) + 1;
    for (const series of [chartData.timestamps, chartData.waitingTimes, chartData.haltingVehicles]) {
        if (series.length > MAX_CHART_POINTS) series.shift();
    }

    updateReferenceLabels();
    const sampled = trip.sampled_s || 0;
    document.getElementById('kpi-total-steps').textContent =
        `${Math.floor(sampled / 60)}:${String(Math.floor(sampled % 60)).padStart(2, '0')}`;
    document.getElementById('kpi-avg-wait').textContent = meanWait == null ? '—' : meanWait.toFixed(1) + ' s';
    updateReduction(meanWait, sampled);

    requestAnimationFrame(renderCharts);
    updatePhaseDistribution();
}

// ============================================
//  Câmera ampliada
// ============================================
const modal = document.getElementById('camera-modal');
const modalImg = document.getElementById('camera-modal-img');
let modalCamera = null;

function openCamera(approach) {
    modalCamera = approach;
    document.getElementById('camera-modal-title').textContent = APPROACH_LABELS[approach];
    modalImg.src = '/api/video/' + approach;
    modal.hidden = false;
}

function closeCamera() {
    modal.hidden = true;
    modalImg.removeAttribute('src');  // encerra o stream extra
    modalCamera = null;
}

// Sem servidor de vídeo, esconde o ícone de imagem quebrada atrás do aviso.
document.querySelectorAll('.camera-viewport img').forEach(img => {
    img.addEventListener('error', () => { img.style.visibility = 'hidden'; });
    img.addEventListener('load', () => { img.style.visibility = 'visible'; });
});

// Os streams MJPEG nunca terminam: ligados no HTML, seguram o evento load e
// a aba fica "carregando" para sempre. Só começam depois que a página carregou.
function startCameraStreams() {
    document.querySelectorAll('.camera-viewport img[data-stream]').forEach(img => { img.src = img.dataset.stream; });
}
if (document.readyState === 'complete') startCameraStreams();
else window.addEventListener('load', startCameraStreams);

document.querySelectorAll('.camera-viewport').forEach(el => {
    el.addEventListener('click', () => openCamera(el.dataset.camera));
});
document.getElementById('camera-modal-close').addEventListener('click', closeCamera);
modal.addEventListener('click', (e) => { if (e.target === modal) closeCamera(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.hidden) closeCamera(); });

// ============================================
//  Controles
// ============================================
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnEmergency = document.getElementById('btn-emergency');
const selScenario = document.getElementById('sel-scenario');
const selVersion = document.getElementById('sel-version');
const selPreemption = document.getElementById('sel-preemption');
const selApproach = document.getElementById('sel-approach');
const selExit = document.getElementById('sel-exit');

// Só as saídas que existem para a rua escolhida (rotas do sp.yaml).
function syncExitOptions() {
    const exits = emergencyRoutes[selApproach.value] || [];
    selExit.innerHTML = '<option value="">Aleatório</option>' +
        exits.map(name => `<option value="${name}">${EXIT_LABELS[name] || name}</option>`).join('');
}
selApproach.addEventListener('change', syncExitOptions);

function showMessage(text) {
    document.getElementById('control-message').textContent = text;
}

function updateButtons() {
    btnStart.disabled = isRunning;
    btnStop.disabled = !isRunning;
    btnEmergency.disabled = !isRunning;
    [selScenario, selVersion, selPreemption].forEach(el => { el.disabled = isRunning; });
}

async function loadOptions() {
    try {
        const options = await (await fetch('/api/options')).json();
        selVersion.innerHTML = options.versions.map(v => `<option value="${v.id}">${v.label}</option>`).join('');
        emergencyRoutes = options.emergency_routes || {};
        announceBeforeS = options.announce_before_s;
        fixedTimeReferenceS = options.fixed_time_reference_s || {};
        minSampleS = options.min_sample_s ?? minSampleS;
        if (options.generic_detector) {
            // Sem a classe de viatura, a câmera não pede prioridade: só o V2I.
            for (const option of selPreemption.options) {
                if (option.value === 'vision' || option.value === 'both') option.disabled = true;
            }
            selPreemption.value = 'v2i';
            showMessage('Detector genérico em uso: sem detecção visual de ambulâncias (prioridade só pelo V2I).');
        }
        syncExitOptions();
        updateReferenceLabels();
        renderCharts();
    } catch (e) {
        showMessage('Não foi possível conectar ao servidor do painel.');
    }
}

async function post(url, body) {
    const response = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (!response.ok) {
        const detail = (await response.json().catch(() => ({}))).detail;
        throw new Error(detail || response.statusText);
    }
}

// Limpa só os gráficos: os indicadores vêm do coletor da rodada inteira no servidor
// e se atualizam na próxima telemetria.
function resetCharts() {
    chartData = { timestamps: [], waitingTimes: [], haltingVehicles: [], phaseCounters: {} };
    lastSimTime = null;
    renderCharts();
    updatePhaseDistribution();
}

selScenario.addEventListener('change', () => { updateReferenceLabels(); renderCharts(); });

btnStart.addEventListener('click', async () => {
    try {
        await post('/api/start', { scenario: selScenario.value, version: selVersion.value, preemption: selPreemption.value });
        resetCharts();
        showMessage('Iniciando a simulação. As imagens serão exibidas em alguns segundos.');
        isRunning = true;
        updateButtons();
    } catch (e) {
        showMessage(e.message);
    }
});

btnStop.addEventListener('click', async () => {
    await post('/api/stop').catch(e => showMessage(e.message));
    showMessage('Demonstração encerrada.');
    document.querySelectorAll('.camera-overlay').forEach(el => el.classList.remove('hidden'));
});

btnEmergency.addEventListener('click', async () => {
    try {
        const exit = selExit.value || null;
        const countBefore = Number(document.getElementById('val-dispatched').textContent) || 0;
        await post('/api/emergency', { approach: selApproach.value, exit });
        const route = 'origem: ' + APPROACH_LABELS[selApproach.value] + (exit ? ', destino: ' + EXIT_LABELS[exit] : '');
        const delay = announceBeforeS == null ? '' : ` Entrada na via em ${announceBeforeS} s.`;
        showMessage(`🚑 Ambulância acionada (${route}). Aviso de aproximação enviado ao semáforo.${delay}`);
        pendingAmbulance = { route, countBefore, enterAt: null };
    } catch (e) {
        showMessage(e.message);
    }
});

document.getElementById('btn-reset-charts').addEventListener('click', resetCharts);

loadOptions();
updateButtons();

// ============================================
//  Chart Rendering (Canvas-based, no library)
// ============================================
function drawLineChart(canvasId, data, color, label, yLabel, baselineVal = null) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Handle high DPI
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = 260 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '260px';
    ctx.scale(dpr, dpr);

    const W = rect.width;
    const H = 260;
    const pad = { top: 24, right: 20, bottom: 36, left: 56 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    // Com um ponto só não há reta (e as divisões por length − 1 dariam NaN).
    if (!data || data.length < 2) {
        ctx.fillStyle = '#5c6578';
        ctx.font = '13px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Aguardando dados da demonstração…', W / 2, H / 2);
        return;
    }

    // Compute bounds (incorporando a linha de baseline para não cortar)
    let minY = Math.min(...data);
    let maxY = Math.max(...data);
    if (baselineVal !== null) {
        minY = Math.min(minY, baselineVal);
        maxY = Math.max(maxY, baselineVal);
    }
    if (minY === maxY) { minY -= 1; maxY += 1; }
    const rangeY = maxY - minY;
    minY = Math.max(0, minY - rangeY * 0.1);
    maxY += rangeY * 0.18;

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.lineWidth = 1;
    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
        const y = pad.top + (plotH / gridLines) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(W - pad.right, y);
        ctx.stroke();

        // Y labels
        const val = maxY - ((maxY - minY) / gridLines) * i;
        ctx.fillStyle = '#6b778d';
        ctx.font = '11px JetBrains Mono, monospace';
        ctx.textAlign = 'right';
        ctx.fillText(val.toFixed(1), pad.left - 8, y + 4);
    }

    // Baseline horizontal line
    if (baselineVal !== null && data.length >= 2) {
        const baselineY = pad.top + plotH - ((baselineVal - minY) / (maxY - minY)) * plotH;
        ctx.save();
        ctx.setLineDash([6, 5]);
        ctx.strokeStyle = '#f06565';
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(pad.left, baselineY);
        ctx.lineTo(W - pad.right, baselineY);
        ctx.stroke();

        // Tag sobre a linha
        ctx.fillStyle = '#f06565';
        ctx.font = '600 11px JetBrains Mono, monospace';
        ctx.textAlign = 'right';
        ctx.fillText(`Tempo fixo: ${baselineVal.toFixed(1)}s`, W - pad.right - 8, baselineY - 6);
        ctx.restore();
    }

    // X labels
    const xLabelCount = Math.min(6, data.length);
    ctx.fillStyle = '#6b778d';
    ctx.font = '11px JetBrains Mono, monospace';
    ctx.textAlign = 'center';
    for (let i = 0; i < xLabelCount; i++) {
        const idx = Math.floor((data.length - 1) * i / (xLabelCount - 1));
        const x = pad.left + (plotW * idx / (data.length - 1));
        const t = chartData.timestamps[idx] || 0;
        const m = Math.floor(t / 60);
        const s = Math.floor(t % 60);
        ctx.fillText(`${m}:${String(s).padStart(2, '0')}`, x, H - 8);
    }

    // Plot area gradient fill
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
        const x = pad.left + (plotW * i / (data.length - 1));
        const y = pad.top + plotH - ((data[i] - minY) / (maxY - minY)) * plotH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.lineTo(pad.left, pad.top + plotH);
    ctx.closePath();

    const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
    gradient.addColorStop(0, color + '28');
    gradient.addColorStop(1, color + '00');
    ctx.fillStyle = gradient;
    ctx.fill();

    // Line
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
        const x = pad.left + (plotW * i / (data.length - 1));
        const y = pad.top + plotH - ((data[i] - minY) / (maxY - minY)) * plotH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.2;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // Latest value dot
    if (data.length > 0) {
        const lastX = pad.left + plotW;
        const lastY = pad.top + plotH - ((data[data.length - 1] - minY) / (maxY - minY)) * plotH;
        ctx.beginPath();
        ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(lastX, lastY, 8, 0, Math.PI * 2);
        ctx.strokeStyle = color + '40';
        ctx.lineWidth = 2;
        ctx.stroke();
    }
}

/** Redução da espera contra o tempo fixo do cenário: só com amostra suficiente e
 *  nunca para o próprio tempo fixo (seria comparar a referência com ela mesma). */
function updateReduction(meanWait, sampled) {
    const value = document.getElementById('kpi-reduction-val');
    const note = document.getElementById('kpi-reduction-note');
    const reference = fixedTimeReference();
    value.className = 'kpi-value text-green';
    value.textContent = '—';
    if (runningRequest && runningRequest.version === 'baseline') {
        note.textContent = 'o tempo fixo é a própria referência';
    } else if (reference == null || meanWait == null || sampled < minSampleS) {
        note.textContent = `aguardando ${Math.round(minSampleS / 60)} min de amostra (${Math.floor(sampled / 60)} min)`;
    } else {
        const pct = (reference - meanWait) / reference * 100;
        value.textContent = (pct >= 0 ? '−' : '+') + Math.abs(pct).toFixed(0) + '%';
        if (pct < 0) value.className = 'kpi-value text-amber';
        note.textContent = 'estimativa desta demonstração, contra o tempo fixo na avaliação';
    }
}

function renderCharts() {
    drawLineChart('chart-waiting', chartData.waitingTimes, '#2dd4a0', 'Espera', 's', fixedTimeReference());
    drawLineChart('chart-halting', chartData.haltingVehicles, '#4f8ff7', 'Veículos', '');
}

function updatePhaseDistribution() {
    const counters = chartData.phaseCounters;
    const total = Object.values(counters).reduce((a, b) => a + b, 0) || 1;
    const share = names => names.reduce((sum, name) => sum + (counters[name] || 0), 0) / total * 100;
    const groups = {
        south: share(['SOUTH_GREEN']),
        east: share(['EAST_WEST_GREEN']),
        trans: share(['EAST_WEST_YELLOW', 'SOUTH_YELLOW', 'ALL_RED']),
        ped: share(['PEDESTRIAN_GREEN', 'PEDESTRIAN_CLEARANCE'])
    };
    for (const [key, pct] of Object.entries(groups)) {
        document.getElementById('phase-bar-' + key).style.width = pct.toFixed(0) + '%';
        document.getElementById('phase-pct-' + key).textContent = pct.toFixed(0) + '%';
    }
}

// Render empty charts on load
renderCharts();

// Re-render charts when navigating to dashboard
window.addEventListener('hashchange', () => {
    if (window.location.hash === '#dashboard') {
        setTimeout(renderCharts, 50);
    }
});
// Also handle resize
window.addEventListener('resize', () => {
    requestAnimationFrame(renderCharts);
});
