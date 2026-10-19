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
let isPaused = false;
let lastSimTime = null;
let lastError = null;
// waitingTimesAt: instante de cada ponto de espera (a série só começa no primeiro veículo concluído).
let chartData = { timestamps: [], waitingTimes: [], waitingTimesAt: [], haltingVehicles: [], phaseCounters: {} };
const MAX_CHART_POINTS = 300;
const APPROACHES = ['west', 'south', 'east'];

// Espera por veículo do tempo fixo na avaliação oficial, por cenário, e a amostra
// mínima antes de mostrar a redução: vêm de /api/options (fonte única no backend).
let fixedTimeReferenceS = {};
let minSampleS = 600;
let warmupS = 300;
let referenceWarmupS = 300;  // aquecimento da avaliação oficial (a referência)
let runningRequest = null;  // cenário e controlador em execução (data.request)
let lastRunScenario = null;  // cenário dos dados no gráfico (mantido depois do Parar)

/** Referência do tempo fixo do cenário dos dados mostrados: o em execução, o da última
 *  rodada enquanto o gráfico tiver dados dela, ou (sem dados) o selecionado. */
function fixedTimeReference() {
    let scenario = selScenario.value;
    if (isRunning && runningRequest) scenario = runningRequest.scenario;
    else if (chartData.waitingTimes.length && lastRunScenario) scenario = lastRunScenario;
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
// Lista das ambulâncias a caminho (botão e agenda automática), vinda da telemetria:
// cada uma com a própria contagem, no relógio da simulação.
function renderAmbulances(board, simTime, preemptionOn) {
    const list = document.getElementById('ambulance-list');
    const vehicles = (board && board.vehicles) || [];
    list.hidden = vehicles.length === 0;
    list.innerHTML = vehicles.map(vehicle => {
        const route = APPROACH_LABELS[vehicle.approach] + (vehicle.exit ? ' → ' + EXIT_LABELS[vehicle.exit] : '');
        const kind = vehicle.automatic ? ' <span class="ambulance-tag">automática</span>' : '';
        let status;
        if (vehicle.state === 'anunciada') {
            status = `entrada na via em ${Math.max(1, Math.ceil(vehicle.enter_at_s - simTime))} s`;
        } else if (vehicle.state === 'entrando') {
            status = 'entrando na via';
        } else if (vehicle.state === 'na_via') {
            status = vehicle.served ? 'na via, verde garantido' : preemptionOn ? 'na via, aguardando a vez' : 'na via';
        } else {
            status = 'cruzou o semáforo';
        }
        return `<div class="ambulance-item ${vehicle.served ? 'served' : ''}">🚑 ${route}${kind}: <strong>${status}</strong></div>`;
    }).join('');
}

function updateAmbulanceCounts(board) {
    const counts = (board && board.counts) || { manual: 0, automatic: 0 };
    const total = counts.manual + counts.automatic;
    document.getElementById('val-dispatched').textContent = total;
    document.getElementById('kpi-emergency-val').textContent = total;
    document.getElementById('kpi-emergency-sub').textContent = counts.automatic
        ? `${counts.manual} pelo botão · ${counts.automatic} automáticas` : 'nesta demonstração';
}

function minutesClock(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function formatClock(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// live: rodada em andamento e já no tempo de teste. Fora disso as câmeras mostram o
// ícone de espera, e moldura, luz e contagem ficam neutras para não sugerir imagens.
function updateCameras(t, live) {
    const priority = live ? PRIORITY_APPROACHES[t.preempt_target] || [] : [];
    for (const approach of APPROACHES) {
        const color = live && t.signals ? t.signals[approach] : '';
        const card = document.querySelector(`.camera-card[data-camera="${approach}"]`);
        card.classList.remove('signal-green', 'signal-yellow', 'signal-red');
        if (color) card.classList.add('signal-' + color);
        card.classList.toggle('priority', priority.includes(approach));
        document.getElementById('signal-' + approach).className = 'signal-light ' + (color || '');
        // Parados vistos pela câmera ("—" num instante sem imagem).
        const stopped = live && t.vision ? t.vision[approach].stopped : null;
        const count = document.getElementById('stopped-' + approach);
        count.textContent = stopped == null ? '—' : stopped;
        count.nextSibling.textContent = stopped === 1 ? ' parado' : ' parados';
    }
    if (modalCamera && live && t.signals) {
        document.getElementById('modal-signal').className = 'signal-light ' + t.signals[modalCamera];
    }
}

function updateTelemetry(data) {
    const running = data.is_running === true;
    const t = data.telemetry;

    const paused = running && data.paused === true;
    if (paused) setBadge(sumoDot, 'warning', 'Pausada');
    else if (running) setBadge(sumoDot, 'online', data.status === 'rodando' ? 'Em execução' : 'Iniciando');
    else setBadge(sumoDot, 'warning', 'Parada');
    if (t && t.vision) setBadge(unityDot, 'online', 'Recebendo imagens');
    else if (running && t) setBadge(unityDot, 'warning', 'Sem imagens');
    else setBadge(unityDot, 'offline', 'Aguardando');
    if (t && t.vision && waitingFirstImages) {
        waitingFirstImages = false;
        showMessage('');
    }

    if (running !== isRunning || paused !== isPaused) {
        isRunning = running;
        isPaused = paused;
        updateButtons();
    }
    if (data.error !== lastError) {
        lastError = data.error;
        if (data.error) showMessage('Erro: ' + data.error);
    }
    runningRequest = running ? data.request : null;
    if (runningRequest) lastRunScenario = runningRequest.scenario;
    if (!t) return;

    // Tempo de teste: começa em 0 quando o aquecimento termina e o controlador assume.
    const testTime = (t.sim_time || 0) - warmupS;
    const warming = testTime <= 0;
    document.getElementById('sim-clock').textContent = warming ? 'Aguarde…' : formatClock(testTime);
    renderAmbulances(t.emergencies, t.sim_time || 0, runningRequest && runningRequest.preemption !== 'none');
    updateAmbulanceCounts(t.emergencies);
    updateCameras(t, running && !warming);
    const gt = t.ground_truth;
    document.getElementById('val-halting').textContent = gt.halting_vehicles;
    document.getElementById('val-wait').textContent = gt.mean_wait_per_stopped_s.toFixed(1) + ' s';
    document.getElementById('phase-name').textContent = running && !warming ? PHASE_LABELS[t.phase] || t.phase : '—';
    const priority = PRIORITY_APPROACHES[t.preempt_target];
    document.getElementById('preempt-name').textContent = priority && running && !warming
        ? '🚑 verde para ' + priority.map(a => APPROACH_LABELS[a]).join(' e ') : '—';

    // As imagens só aparecem quando o tempo de teste começa (depois do aquecimento).
    document.querySelectorAll('.camera-overlay').forEach(el => el.classList.toggle('hidden', running && !warming));

    // Um ponto por instante novo da simulação (a telemetria pode repetir o mesmo).
    if (t.sim_time === lastSimTime) return;
    lastSimTime = t.sim_time;
    // Espera por veículo desde o aquecimento: a mesma métrica da avaliação oficial.
    const trip = t.trip || {};
    const meanWait = trip.mean_waiting_time_s;
    // O aquecimento não entra nos gráficos nem na divisão por fase: só o tempo de teste.
    if (!warming) {
        chartData.timestamps.push(testTime);
        chartData.haltingVehicles.push(gt.halting_vehicles);
        if (meanWait != null) {
            chartData.waitingTimes.push(meanWait);
            chartData.waitingTimesAt.push(testTime);
        }
        chartData.phaseCounters[t.phase] = (chartData.phaseCounters[t.phase] || 0) + 1;
    }
    // Cada série anda junto com o próprio eixo do tempo.
    for (const series of [chartData.timestamps, chartData.haltingVehicles, chartData.waitingTimes, chartData.waitingTimesAt]) {
        if (series.length > MAX_CHART_POINTS) series.shift();
    }

    updateReferenceLabels();
    // O mesmo tempo de teste do Ao vivo e do eixo dos gráficos.
    const sampled = trip.sampled_s || 0;
    document.getElementById('kpi-total-steps').textContent = warming ? '0:00' : minutesClock(testTime);
    document.getElementById('kpi-time-note').textContent = warming ? 'preparando o cruzamento…' : 'desde o início do teste';
    document.getElementById('kpi-avg-wait').textContent = meanWait == null ? '—' : meanWait.toFixed(1) + ' s';
    // Quem ainda espera para entrar na rede não está na média (só veículos que concluíram o trajeto).
    const pending = trip.pending_vehicles || 0;
    const pendingNote = document.getElementById('kpi-pending');
    pendingNote.textContent = pending ? `fila de entrada: ${pending} veículos (ainda fora da média)` : 'fila de entrada: 0';
    pendingNote.classList.toggle('text-amber', pending > 0);
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
const tglAutoEmergencies = document.getElementById('tgl-auto-emergencies');
const selApproach = document.getElementById('sel-approach');
const selExit = document.getElementById('sel-exit');

// Só as saídas que existem para a rua escolhida (rotas do sp.yaml).
function syncExitOptions() {
    const exits = emergencyRoutes[selApproach.value] || [];
    selExit.innerHTML = '<option value="">Aleatório</option>' +
        exits.map(name => `<option value="${name}">${EXIT_LABELS[name] || name}</option>`).join('');
}
selApproach.addEventListener('change', syncExitOptions);

// Mensagens de confirmação somem sozinhas (transient_ms); erros e avisos ficam até
// a próxima mensagem. "Iniciando…" some quando chegam as primeiras imagens.
let messageTimer = null;
let waitingFirstImages = false;
function showMessage(text, transientMs = 0) {
    clearTimeout(messageTimer);
    document.getElementById('control-message').textContent = text;
    if (transientMs > 0) messageTimer = setTimeout(() => showMessage(''), transientMs);
}

const ICON_PLAY = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
const ICON_PAUSE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';

// Parado: Iniciar (verde). Rodando: Pausar (amarelo). Pausado: Retomar (azul).
function updateButtons() {
    const [icon, label] = !isRunning ? [ICON_PLAY, 'Iniciar'] : isPaused ? [ICON_PLAY, 'Retomar'] : [ICON_PAUSE, 'Pausar'];
    btnStart.innerHTML = `${icon} ${label}`;
    btnStart.classList.toggle('btn-pause', isRunning && !isPaused);
    btnStart.classList.toggle('btn-resume', isRunning && isPaused);
    btnStop.disabled = !isRunning;
    btnEmergency.disabled = !isRunning;
    [selScenario, selVersion, selPreemption, tglAutoEmergencies].forEach(el => { el.disabled = isRunning; });
}

async function loadOptions() {
    try {
        const options = await (await fetch('/api/options')).json();
        selVersion.innerHTML = options.versions.map(v => `<option value="${v.id}">${v.label}</option>`).join('');
        emergencyRoutes = options.emergency_routes || {};
        fixedTimeReferenceS = options.fixed_time_reference_s || {};
        minSampleS = options.min_sample_s ?? minSampleS;
        warmupS = options.warmup_s ?? warmupS;
        referenceWarmupS = options.reference_warmup_s ?? referenceWarmupS;
        if (options.generic_detector) {
            // Sem a classe de viatura, a câmera não pede prioridade: só o V2I.
            for (const option of selPreemption.options) {
                if (option.value === 'vision' || option.value === 'both') option.disabled = true;
            }
            // Só troca se a escolha atual ficou indisponível; "Desativada" é mantida.
            if (selPreemption.selectedOptions[0]?.disabled) selPreemption.value = 'v2i';
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
    chartData = { timestamps: [], waitingTimes: [], waitingTimesAt: [], haltingVehicles: [], phaseCounters: {} };
    lastSimTime = null;
    renderCharts();
    updatePhaseDistribution();
}

selScenario.addEventListener('change', () => { updateReferenceLabels(); renderCharts(); });
tglAutoEmergencies.addEventListener('change', () => {
    document.getElementById('auto-emergencies-state').textContent = tglAutoEmergencies.checked ? 'a cada ~5 min' : 'desligadas';
});

// Zera os cartões de Resultados ao iniciar outra rodada, para nunca misturar amostras.
function resetKpis() {
    for (const [id, text] of [['kpi-total-steps', '0:00'], ['kpi-time-note', 'aguardando o início'], ['kpi-avg-wait', '—'], ['kpi-reduction-val', '—'],
                              ['kpi-pending', 'fila de entrada: —'], ['kpi-reduction-note', 'aguardando amostra']]) {
        document.getElementById(id).textContent = text;
    }
    updateAmbulanceCounts(null);
    renderAmbulances(null, 0, false);
}

btnStart.addEventListener('click', async () => {
    try {
        if (isRunning) {
            // Pausa ou retoma: o SUMO só avança quando o Python pede o próximo passo.
            await post(isPaused ? '/api/resume' : '/api/pause');
            isPaused = !isPaused;
            if (isPaused) showMessage('Simulação pausada. Os dados ficam na tela para análise.');
            else showMessage('Simulação retomada.', 4000);
            updateButtons();
            return;
        }
        await post('/api/start', { scenario: selScenario.value, version: selVersion.value, preemption: selPreemption.value,
                                   auto_emergencies: tglAutoEmergencies.checked });
        lastRunScenario = selScenario.value;
        resetCharts();
        resetKpis();
        showMessage('Iniciando a simulação. As imagens serão exibidas em alguns segundos.');
        waitingFirstImages = true;
        isRunning = true;
        isPaused = false;
        updateButtons();
    } catch (e) {
        showMessage(e.message);
    }
});

btnStop.addEventListener('click', async () => {
    await post('/api/stop').catch(e => showMessage(e.message));
    waitingFirstImages = false;
    showMessage('Demonstração encerrada.', 4000);
    document.querySelectorAll('.camera-overlay').forEach(el => el.classList.remove('hidden'));
});

btnEmergency.addEventListener('click', async () => {
    try {
        const exit = selExit.value || null;
        await post('/api/emergency', { approach: selApproach.value, exit });
        showMessage('🚑 Ambulância acionada: aviso de aproximação enviado ao semáforo.', 4000);
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
// Posição do mouse (px, relativa ao canvas) sobre cada gráfico, ou ausente fora dele.
// Guardamos a posição, não o índice: com o gráfico andando, o ponto sob o mouse muda.
const chartHoverX = {};

function drawLineChart(canvasId, data, color, label, yLabel, baselineVal = null, times = chartData.timestamps) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // Alta densidade de pixels. A largura é a do próprio canvas na tela (o .chart-body
    // tem padding): desenho e coordenadas do mouse ficam na mesma escala.
    const width = canvas.clientWidth || canvas.parentElement.clientWidth;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = 260 * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = '260px';
    ctx.scale(dpr, dpr);

    const W = width;
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
        const t = times[idx] || 0;
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

    // Hover: linha vertical, ponto e o valor daquele instante.
    const hoverX = chartHoverX[canvasId];
    if (hoverX == null || hoverX < pad.left || hoverX > pad.left + plotW) return;
    const idx = Math.round((hoverX - pad.left) / plotW * (data.length - 1));
    const x = pad.left + (plotW * idx / (data.length - 1));
    const y = pad.top + plotH - ((data[idx] - minY) / (maxY - minY)) * plotH;
    ctx.save();
    ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + plotH);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#0d1117';
    ctx.lineWidth = 2;
    ctx.stroke();

    const value = yLabel ? `${data[idx].toFixed(1)} ${yLabel}` : `${Math.round(data[idx])}`;
    const lines = [`${label}: ${value}`, `tempo de teste ${minutesClock(times[idx] || 0)}`];
    ctx.font = '600 12px Inter, sans-serif';
    const boxW = Math.max(...lines.map(line => ctx.measureText(line).width)) + 20;
    const boxH = 44;
    let boxX = x + 12;
    if (boxX + boxW > W - pad.right) boxX = x - 12 - boxW;
    const boxY = Math.min(Math.max(pad.top, y - boxH - 10), pad.top + plotH - boxH);
    ctx.fillStyle = 'rgba(13, 17, 23, 0.94)';
    ctx.strokeStyle = color + '80';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(boxX, boxY, boxW, boxH, 6);
    ctx.fill();
    ctx.stroke();
    ctx.textAlign = 'left';
    ctx.fillStyle = '#eaf0f6';
    ctx.fillText(lines[0], boxX + 10, boxY + 18);
    ctx.font = '11px Inter, sans-serif';
    ctx.fillStyle = '#8b95a8';
    ctx.fillText(lines[1], boxX + 10, boxY + 34);
    ctx.restore();
}

for (const canvasId of ['chart-waiting', 'chart-halting']) {
    const canvas = document.getElementById(canvasId);
    canvas.addEventListener('mousemove', (e) => {
        const rect = canvas.getBoundingClientRect();
        chartHoverX[canvasId] = e.clientX - rect.left;
        renderCharts();
    });
    canvas.addEventListener('mouseleave', () => {
        delete chartHoverX[canvasId];
        renderCharts();
    });
}

/** Redução da espera contra o tempo fixo do cenário: só com amostra suficiente e
 *  nunca para o próprio tempo fixo (seria comparar a referência com ela mesma). */
function updateReduction(meanWait, sampled) {
    const value = document.getElementById('kpi-reduction-val');
    const note = document.getElementById('kpi-reduction-note');
    const reference = fixedTimeReference();
    value.className = 'kpi-value text-green';
    value.textContent = '—';
    note.className = 'kpi-subtext text-green font-semibold';
    note.textContent = '';
    if (runningRequest && runningRequest.version === 'baseline') {
        note.textContent = 'o tempo fixo é a própria referência';
        return;
    }
    if (reference == null || meanWait == null) {
        note.textContent = 'aguardando os primeiros veículos';
        return;
    }
    const pct = (reference - meanWait) / reference * 100;
    value.textContent = (pct >= 0 ? '−' : '+') + Math.abs(pct).toFixed(0) + '%';
    if (warmupS !== referenceWarmupS) {
        // Outro aquecimento: a média ao vivo não é comparável com a referência.
        value.className = 'kpi-value text-muted';
        note.className = 'kpi-subtext text-amber';
        note.textContent = `aquecimento diferente da avaliação (${warmupS} s × ${referenceWarmupS} s)`;
    } else if (sampled < minSampleS) {
        // Com pouca amostra a média ainda oscila: o número aparece, mas em cinza.
        value.className = 'kpi-value text-muted';
        note.className = 'kpi-subtext text-muted';
        note.textContent = `preliminar até ${minutesClock(minSampleS)} de teste`;
    } else if (pct < 0) {
        value.className = 'kpi-value text-amber';
    }
}

function renderCharts() {
    drawLineChart('chart-waiting', chartData.waitingTimes, '#2dd4a0', 'Espera média', 's', fixedTimeReference(), chartData.waitingTimesAt);
    drawLineChart('chart-halting', chartData.haltingVehicles, '#4f8ff7', 'Veículos retidos', '');
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
