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
let isRunning = false;
let chartData = {
    timestamps: [],
    waitingTimes: [],
    rewards: [],
    haltingVehicles: [],
    phaseCounters: {}
};
const MAX_CHART_POINTS = 300;

function updateTelemetry(data) {
    const running = data.is_running === true;

    // Update SUMO status
    if (running) {
        sumoDot.className = 'status-dot online';
        sumoDot.parentElement.lastChild.textContent = ' Rodando';
    } else {
        sumoDot.className = 'status-dot warning';
        sumoDot.parentElement.lastChild.textContent = ' Parado';
    }

    // Update running state + buttons
    if (running !== isRunning) {
        isRunning = running;
        updateButtons();
    }

    // Simulation clock
    const simTime = data.sim_time || 0;
    const hours = Math.floor(simTime / 3600);
    const mins = Math.floor((simTime % 3600) / 60);
    const secs = Math.floor(simTime % 60);
    document.getElementById('sim-clock').textContent =
        `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    // Metrics on Simulation page
    updateMetricValue('val-south', data.south_queue, 0);
    updateMetricValue('val-east', data.east_queue, 0);
    updateMetricValue('val-west', data.west_queue, 0);

    const waitVal = data.avg_waiting_time != null ? data.avg_waiting_time.toFixed(1) + ' s' : '— s';
    document.getElementById('val-wait').textContent = waitVal;

    const rewardVal = data.reward != null ? data.reward.toFixed(3) : '—';
    document.getElementById('val-reward').textContent = rewardVal;

    // Policy & Phase
    const policyMap = { 'dqn': 'DQN (IA)', 'fixed': 'Ciclo Fixo', 'max_pressure': 'Max Pressure' };
    document.getElementById('policy-name').textContent = policyMap[data.current_policy] || data.current_policy || '—';
    document.getElementById('phase-name').textContent = data.phase || '—';

    // Camera overlays
    if (running && simTime > 0) {
        document.querySelectorAll('.camera-overlay').forEach(el => el.classList.add('hidden'));
        document.querySelectorAll('.camera-rec').forEach(el => el.classList.add('active'));
    }

    // Accumulate chart data
    if (running && simTime > 0) {
        chartData.timestamps.push(simTime);
        chartData.waitingTimes.push(data.avg_waiting_time || 0);
        chartData.rewards.push(data.reward || 0);
        chartData.haltingVehicles.push(data.south_queue || 0);

        // Phase counting
        const phase = data.phase || 'unknown';
        chartData.phaseCounters[phase] = (chartData.phaseCounters[phase] || 0) + 1;

        // Trim to max points
        if (chartData.timestamps.length > MAX_CHART_POINTS) {
            chartData.timestamps.shift();
            chartData.waitingTimes.shift();
            chartData.rewards.shift();
            chartData.haltingVehicles.shift();
        }

        // Dashboard KPIs
        const totalSteps = chartData.timestamps.length;
        document.getElementById('kpi-total-steps').textContent = totalSteps;

        const avgReward = chartData.rewards.reduce((a, b) => a + b, 0) / totalSteps;
        document.getElementById('kpi-avg-reward').textContent = avgReward.toFixed(3);
        const rewardEl = document.getElementById('kpi-trend-reward');
        rewardEl.textContent = avgReward >= -0.3 ? '↑ Bom' : '↓ Melhorar';
        rewardEl.className = 'kpi-trend ' + (avgReward >= -0.3 ? 'up' : 'down');

        const avgWait = chartData.waitingTimes.reduce((a, b) => a + b, 0) / totalSteps;
        document.getElementById('kpi-avg-wait').textContent = avgWait.toFixed(1) + 's';

        document.getElementById('kpi-halting').textContent = data.south_queue || 0;

        // Update charts (throttled)
        requestAnimationFrame(renderCharts);

        // Update phase distribution
        updatePhaseDistribution();
    }
}

function updateMetricValue(id, value, fallback) {
    const el = document.getElementById(id);
    if (el) el.textContent = value != null ? value : fallback;
}

// ============================================
//  Controls
// ============================================
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnEmergency = document.getElementById('btn-emergency');

function updateButtons() {
    btnStart.disabled = isRunning;
    btnStop.disabled = !isRunning;
    btnEmergency.disabled = !isRunning;
}

btnStart.addEventListener('click', () => {
    fetch('/api/control/start', { method: 'POST' });
    // Optimistic update
    isRunning = true;
    updateButtons();
});

btnStop.addEventListener('click', () => {
    fetch('/api/control/stop', { method: 'POST' });
    isRunning = false;
    updateButtons();
    document.querySelectorAll('.camera-overlay').forEach(el => el.classList.remove('hidden'));
    document.querySelectorAll('.camera-rec').forEach(el => el.classList.remove('active'));
});

btnEmergency.addEventListener('click', () => {
    fetch('/api/control/inject_emergency', { method: 'POST' });
    btnEmergency.style.background = 'rgba(240, 176, 69, 0.25)';
    setTimeout(() => { btnEmergency.style.background = ''; }, 800);
});

document.getElementById('btn-reset-charts').addEventListener('click', () => {
    chartData = { timestamps: [], waitingTimes: [], rewards: [], haltingVehicles: [], phaseCounters: {} };
    renderCharts();
    updatePhaseDistribution();
    document.getElementById('kpi-total-steps').textContent = '0';
    document.getElementById('kpi-avg-reward').textContent = '0.000';
    document.getElementById('kpi-avg-wait').textContent = '0.0s';
    document.getElementById('kpi-halting').textContent = '0';
});

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

    // Group into South / East+West / Transition
    let southCount = 0, eastCount = 0, transCount = 0;
    for (const [phase, count] of Object.entries(counters)) {
        const lower = phase.toLowerCase();
        if (lower.includes('south') || lower.includes('sul')) {
            southCount += count;
        } else if (lower.includes('east') || lower.includes('west') || lower.includes('leste') || lower.includes('oeste')) {
            eastCount += count;
        } else {
            transCount += count;
        }
    }

    const sPct = (southCount / total * 100).toFixed(0);
    const ePct = (eastCount / total * 100).toFixed(0);
    const tPct = (transCount / total * 100).toFixed(0);

    document.getElementById('phase-bar-south').style.width = sPct + '%';
    document.getElementById('phase-pct-south').textContent = sPct + '%';
    document.getElementById('phase-bar-east').style.width = ePct + '%';
    document.getElementById('phase-pct-east').textContent = ePct + '%';
    document.getElementById('phase-bar-trans').style.width = tPct + '%';
    document.getElementById('phase-pct-trans').textContent = tPct + '%';
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
