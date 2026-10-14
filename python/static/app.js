/**
 * Traffic CV — Frontend Application
 * Single-page app with WebSocket telemetry, chart rendering, and page routing.
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
//  WebSocket Connection
// ============================================
let ws = null;
let reconnectTimer = null;
const apiDot = document.getElementById('api-dot');
const sumoDot = document.getElementById('sumo-dot');

function connectWS() {
    ws = new WebSocket(`ws://${window.location.host}/ws/telemetry`);

    ws.onopen = () => {
        apiDot.className = 'status-dot online';
        apiDot.parentElement.lastChild.textContent = ' Online';
        clearTimeout(reconnectTimer);
    };

    ws.onclose = () => {
        apiDot.className = 'status-dot offline';
        apiDot.parentElement.lastChild.textContent = ' Offline';
        sumoDot.className = 'status-dot offline';
        sumoDot.parentElement.lastChild.textContent = ' Parado';
        // Auto-reconnect
        reconnectTimer = setTimeout(connectWS, 3000);
    };

    ws.onerror = () => {
        ws.close();
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateTelemetry(data);
    };
}

connectWS();

// ============================================
//  Telemetry State
// ============================================
// Câmera (vision) = o que a política vê; ground_truth = TraCI, só para mostrar.
let isRunning = false;
let lastSimTime = null;
let chartData = {
    timestamps: [],
    waitingTimes: [],
    rewards: [],
    haltingVehicles: [],
    phaseCounters: {}
};
const MAX_CHART_POINTS = 300;
const unityDot = document.getElementById('unity-dot');

const PHASE_LABELS = {
    EAST_WEST_GREEN: 'Verde Leste/Oeste', EAST_WEST_YELLOW: 'Amarelo Leste/Oeste', ALL_RED: 'Vermelho total',
    SOUTH_GREEN: 'Verde Sul', SOUTH_YELLOW: 'Amarelo Sul', PEDESTRIAN_GREEN: 'Verde pedestres',
    PEDESTRIAN_CLEARANCE: 'Liberação pedestres'
};
const APPROACH_LABELS = { south: 'Sul', east: 'Leste', west: 'Oeste' };
const EXIT_LABELS = { north: 'Norte', east: 'Leste', west: 'Oeste' };
let emergencyRoutes = {};

function setBadge(dot, cls, text) {
    dot.className = 'status-dot ' + cls;
    dot.parentElement.lastChild.textContent = ' ' + text;
}

function updateTelemetry(data) {
    const running = data.is_running === true;
    const t = data.telemetry;

    if (running) setBadge(sumoDot, 'online', data.status === 'rodando' ? 'Rodando' : 'Iniciando');
    else setBadge(sumoDot, 'warning', 'Parado');
    if (t && t.vision) setBadge(unityDot, 'online', 'Frames OK');
    else if (running && t) setBadge(unityDot, 'warning', 'Sem frames');
    else setBadge(unityDot, 'offline', 'Aguardando');

    if (running !== isRunning) {
        isRunning = running;
        updateButtons();
    }
    showMessage(data.error ? 'Erro: ' + data.error : '');
    if (!t) return;

    const simTime = t.sim_time || 0;
    const hours = Math.floor(simTime / 3600);
    const mins = Math.floor((simTime % 3600) / 60);
    const secs = Math.floor(simTime % 60);
    document.getElementById('sim-clock').textContent =
        `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    // Parados por aproximação vistos pela câmera (— em step sem frames).
    for (const approach of ['south', 'east', 'west']) {
        const value = t.vision ? t.vision[approach].stopped : '—';
        document.getElementById('val-' + approach).textContent = value;
    }
    const gt = t.ground_truth;
    document.getElementById('val-wait').textContent = gt.mean_wait_per_stopped_s.toFixed(1) + ' s';
    document.getElementById('val-reward').textContent = t.reward.toFixed(3);
    document.getElementById('phase-name').textContent = PHASE_LABELS[t.phase] || t.phase;
    document.getElementById('preempt-name').textContent =
        t.preempt_target ? '🚨 ' + (PHASE_LABELS[t.preempt_target] || t.preempt_target) : '—';

    if (running) {
        document.querySelectorAll('.camera-overlay').forEach(el => el.classList.add('hidden'));
        document.querySelectorAll('.camera-rec').forEach(el => el.classList.add('active'));
    }

    // Um ponto por step novo (a telemetria chega a cada 0,5 s, o step pode repetir).
    if (simTime === lastSimTime) return;
    lastSimTime = simTime;
    chartData.timestamps.push(simTime);
    chartData.waitingTimes.push(gt.mean_wait_per_stopped_s);
    chartData.rewards.push(t.reward);
    chartData.haltingVehicles.push(gt.halting_vehicles);
    chartData.phaseCounters[t.phase] = (chartData.phaseCounters[t.phase] || 0) + 1;

    if (chartData.timestamps.length > MAX_CHART_POINTS) {
        chartData.timestamps.shift();
        chartData.waitingTimes.shift();
        chartData.rewards.shift();
        chartData.haltingVehicles.shift();
    }

    const totalSteps = chartData.timestamps.length;
    document.getElementById('kpi-total-steps').textContent = totalSteps;
    const avgReward = chartData.rewards.reduce((a, b) => a + b, 0) / totalSteps;
    document.getElementById('kpi-avg-reward').textContent = avgReward.toFixed(3);
    const avgWait = chartData.waitingTimes.reduce((a, b) => a + b, 0) / totalSteps;
    document.getElementById('kpi-avg-wait').textContent = avgWait.toFixed(1) + 's';
    document.getElementById('kpi-halting').textContent = gt.halting_vehicles;

    requestAnimationFrame(renderCharts);
    updatePhaseDistribution();
}

// ============================================
//  Controls
// ============================================
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnEmergency = document.getElementById('btn-emergency');
const selScenario = document.getElementById('sel-scenario');
const selVersion = document.getElementById('sel-version');
const selPreemption = document.getElementById('sel-preemption');
const selApproach = document.getElementById('sel-approach');
const selExit = document.getElementById('sel-exit');

// Só as saídas que existem para a aproximação escolhida (rotas do sp.yaml).
function syncExitOptions() {
    const exits = emergencyRoutes[selApproach.value] || [];
    selExit.innerHTML = '<option value="">Sorteio</option>' +
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

// A v3 só existe no cenário com pedestres.
function syncVersionOptions() {
    const v3 = selVersion.querySelector('option[value="v3"]');
    if (!v3) return;
    v3.disabled = selScenario.value !== 'calibrated_ped';
    if (v3.disabled && selVersion.value === 'v3') selVersion.value = 'v2';
}

async function loadOptions() {
    try {
        const options = await (await fetch('/api/options')).json();
        selVersion.innerHTML = options.versions.map(v => `<option value="${v.id}">${v.label}</option>`).join('');
        selVersion.value = 'v2';
        syncVersionOptions();
        emergencyRoutes = options.emergency_routes || {};
        syncExitOptions();
    } catch (e) {
        showMessage('Não foi possível ler as opções da API.');
    }
}
selScenario.addEventListener('change', syncVersionOptions);

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

function resetCharts() {
    chartData = { timestamps: [], waitingTimes: [], rewards: [], haltingVehicles: [], phaseCounters: {} };
    lastSimTime = null;
    renderCharts();
    updatePhaseDistribution();
    document.getElementById('kpi-total-steps').textContent = '0';
    document.getElementById('kpi-avg-reward').textContent = '0.000';
    document.getElementById('kpi-avg-wait').textContent = '0.0s';
    document.getElementById('kpi-halting').textContent = '0';
}

btnStart.addEventListener('click', async () => {
    try {
        await post('/api/start', { scenario: selScenario.value, version: selVersion.value, preemption: selPreemption.value });
        resetCharts();
        showMessage('Iniciando: aquecimento do SUMO e depois a Unity (mantenha o Play Mode ligado).');
        isRunning = true;
        updateButtons();
    } catch (e) {
        showMessage(e.message);
    }
});

btnStop.addEventListener('click', async () => {
    await post('/api/stop').catch(e => showMessage(e.message));
    document.querySelectorAll('.camera-overlay').forEach(el => el.classList.remove('hidden'));
    document.querySelectorAll('.camera-rec').forEach(el => el.classList.remove('active'));
});

btnEmergency.addEventListener('click', async () => {
    try {
        const exit = selExit.value || null;
        await post('/api/emergency', { approach: selApproach.value, exit });
        const route = APPROACH_LABELS[selApproach.value] + (exit ? ' → ' + EXIT_LABELS[exit] : '');
        showMessage(`Viatura despachada (${route}): aviso V2I agora, entra na rede em 15 s.`);
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
function drawLineChart(canvasId, data, color, label, yLabel) {
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
    const pad = { top: 20, right: 20, bottom: 36, left: 60 };
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    ctx.clearRect(0, 0, W, H);

    if (!data || data.length === 0) {
        ctx.fillStyle = '#5c6578';
        ctx.font = '13px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Aguardando dados...', W / 2, H / 2);
        return;
    }

    // Compute bounds
    let minY = Math.min(...data);
    let maxY = Math.max(...data);
    if (minY === maxY) { minY -= 1; maxY += 1; }
    const rangeY = maxY - minY;
    minY -= rangeY * 0.1;
    maxY += rangeY * 0.1;

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.04)';
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
        ctx.fillStyle = '#5c6578';
        ctx.font = '11px JetBrains Mono, monospace';
        ctx.textAlign = 'right';
        ctx.fillText(val.toFixed(1), pad.left - 8, y + 4);
    }

    // X labels
    const xLabelCount = Math.min(6, data.length);
    ctx.fillStyle = '#5c6578';
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
    gradient.addColorStop(0, color + '25');
    gradient.addColorStop(1, color + '02');
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
    ctx.lineWidth = 2;
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
        ctx.arc(lastX, lastY, 7, 0, Math.PI * 2);
        ctx.strokeStyle = color + '40';
        ctx.lineWidth = 2;
        ctx.stroke();
    }
}

function renderCharts() {
    drawLineChart('chart-waiting', chartData.waitingTimes, '#f0b045', 'Espera', 's');
    drawLineChart('chart-reward', chartData.rewards, '#2dd4a0', 'Recompensa', '');
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
