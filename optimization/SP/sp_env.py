"""
Ambiente compartilhado do cruzamento de SP (SUMO/TraCI).

Este modulo e a UNICA fonte de verdade para:
  - identificadores do semaforo, detectores e faixas de entrada;
  - transicoes de fase seguras (verde -> amarelo -> all-red -> verde);
  - representacao de estado;
  - funcao de recompensa;
  - coleta de metricas;
  - linha de comando do SUMO.

Treino (traci8.DQN.py) e avaliacao (traci9_comp.py) importam daqui, de modo que
e impossivel treinar com uma dinamica e avaliar com outra.

Separacao de sinais (alinhada ao README do projeto):
  ESTADO      -> somente detectores E2, que representam as ROIs das cameras.
                 E o unico sinal que o agente ve na inferencia.
  RECOMPENSA  -> ground truth das faixas de entrada. Usado SO no treino, como
                 sinal de aprendizado, nunca como entrada de decisao.
  METRICA     -> tripinfo do SUMO. Usado SO na avaliacao.

Geometria das fases, derivada das <connection> de Cruzamento.net.xml (10 links):
  Fase 0  "GGGrrrrrrG"  -> links 0,1,2 (E2/Leste) + 9 (E6/Oeste)
  Fase 1  "yyyrrrrrry"  -> amarelo de 0
  Fase 2  "rrrrrrrrrr"  -> all-red
  Fase 3  "rrrGgGGGGr"  -> links 3..8 (E3/Sul)
  Fase 4  "rrryyyyyyr"  -> amarelo de 3
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np

if "SUMO_HOME" not in os.environ:
    sys.exit("Defina a variavel de ambiente SUMO_HOME antes de rodar.")
sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))

import traci
import traci.constants as tc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(SCRIPT_DIR, "runs")

# Dois cenarios de demanda sobre a MESMA rede e os MESMOS detectores:
#
#   "original"   Cruzamento.rou.xml, 1936 veic/h. Ambas as fases em v/c ~ 0.5,
#                entao a temporizacao quase nao altera o resultado.
#   "calibrated" Cruzamento.calibrated.rou.xml, 3123 veic/h, derivado dos
#                videos de drone. E2/Leste fica em v/c = 1.00 e E3/Sul em 0.39,
#                enquanto o programa fixo reparte o verde quase meio a meio.
#
# O cenario calibrado e o unico dos dois em que existe um desequilibrio real
# para um controlador adaptativo descobrir.
SCENARIOS = {
    "original": os.path.join(SCRIPT_DIR, "Cruzamento.sumocfg"),
    "calibrated": os.path.join(SCRIPT_DIR, "Cruzamento.calibrated.sumocfg"),
}
SCENARIO = "calibrated"
SUMOCFG = SCENARIOS[SCENARIO]


def set_scenario(name):
    """Seleciona o cenario de demanda. Chamar antes de qualquer reset()."""
    global SCENARIO, SUMOCFG
    if name not in SCENARIOS:
        raise ValueError("cenario desconhecido: %s (use %s)"
                         % (name, "/".join(SCENARIOS)))
    SCENARIO = name
    SUMOCFG = SCENARIOS[name]
    return SUMOCFG

# =============================================================================
# Identificadores da rede
# =============================================================================

TLS_ID = "clusterJ0_J14_J2_J7"

GREEN_PHASES = (0, 3)
YELLOW_OF = {0: 1, 3: 4}
ALL_RED_PHASE = 2

# Tempo perdido por troca. Identico para o agente e para qualquer baseline
# adaptativo, e igual ao que o programa fixo pratica em cada transicao.
YELLOW_STEPS = 3
ALL_RED_STEPS = 1

# Detectores ordenados por grupo de fase. Manter esta ordem: ela define o
# layout do vetor de estado e, portanto, a compatibilidade do modelo salvo.
DETECTORS = (
    "e2_6",  # E2_0  Leste  (fase 0)
    "e2_5",  # E2_1  Leste  (fase 0)
    "e2_0",  # E6_0  Oeste  (fase 0)
    "e2_4",  # E3_0  Sul    (fase 3)
    "e2_3",  # E3_1  Sul    (fase 3)
    "e2_1",  # E3_2  Sul    (fase 3)
    "e2_2",  # E3_3  Sul    (fase 3)
)

DETECTOR_LANE = {
    "e2_0": "E6_0",
    "e2_1": "E3_2",
    "e2_2": "E3_3",
    "e2_3": "E3_1",
    "e2_4": "E3_0",
    "e2_5": "E2_1",
    "e2_6": "E2_0",
}

# Faixas de entrada, por grupo de fase.
PHASE_LANES = {
    0: ("E2_0", "E2_1", "E6_0"),
    3: ("E3_0", "E3_1", "E3_2", "E3_3"),
}
INCOMING_LANES = tuple(PHASE_LANES[0] + PHASE_LANES[3])

MAX_SPEED = 13.89          # m/s, velocidade das faixas no net.xml
VEH_FOOTPRINT = 7.5        # length 5.0 + minGap 2.5 (padrao SUMO)

# Features por detector: fila, parados, ocupacao, velocidade media, espera.
FEATURES_PER_DETECTOR = 5
# Globais: one-hot de fase (5) + verde decorrido + pode trocar + deve trocar.
GLOBAL_FEATURES = 5 + 3
STATE_SIZE = len(DETECTORS) * FEATURES_PER_DETECTOR + GLOBAL_FEATURES  # 43
ACTION_SIZE = 2            # 0 = manter verde | 1 = trocar de fase

# =============================================================================
# Linha de comando do SUMO
# =============================================================================


def sumo_cmd(seed, gui=False, tripinfo=None, scale=None, end=None, step_length=1.0):
    """
    Monta a linha de comando do SUMO.

    Todas as flags que afetam a dinamica sao definidas aqui e apenas aqui, para
    que o ambiente de treino e o de avaliacao sejam equivalentes. Diferem
    somente: seed, gui e tripinfo, que nao alteram a dinamica.

    time-to-teleport fica no padrao 300 s. O valor 60 s usado antes removia
    veiculos travados e apagava o tempo de espera deles das metricas.
    """
    cmd = [
        "sumo-gui" if gui else "sumo",
        "-c", SCENARIOS[SCENARIO],
        "--step-length", str(step_length),
        "--seed", str(int(seed)),
        "--random", "false",
        "--time-to-teleport", "300",
        "--waiting-time-memory", "10000",
        "--no-warnings", "true",
        "--no-step-log", "true",
        "--duration-log.disable", "true",
    ]
    if end is not None:
        cmd += ["--end", str(float(end))]
    if scale is not None and abs(scale - 1.0) > 1e-9:
        cmd += ["--scale", "%.4f" % scale]
    if tripinfo is not None:
        cmd += ["--tripinfo-output", tripinfo]
    if gui:
        cmd += ["--start", "true", "--quit-on-end", "true"]
    return cmd


# =============================================================================
# Semaforo com transicoes seguras
# =============================================================================


class SafeTrafficLight:
    """
    Assume autoridade total sobre o semaforo e garante que toda troca de verde
    passe por amarelo e all-red.

    O programa do net.xml e do tipo "static": um setPhase() cru reinicia a
    duracao e o ciclo volta a avancar sozinho. Aqui cada fase entra com
    duracao efetivamente infinita e a maquina de estados abaixo e a unica
    responsavel por avancar, o que da controle real ao agente.

    Uso, uma vez por step de simulacao:
        tl.tick()                 # aplica transicoes pendentes
        traci.simulationStep()
    """

    HOLD = 100000.0

    def __init__(self, min_green, max_green,
                 yellow_steps=YELLOW_STEPS, all_red_steps=ALL_RED_STEPS):
        self.min_green = int(min_green)
        self.max_green = int(max_green)
        self.yellow_steps = int(yellow_steps)
        self.all_red_steps = int(all_red_steps)
        self._phase = GREEN_PHASES[0]
        self._mode = "green"
        self._timer = 0
        self._pending = None
        self.switches = 0
        self.lost_steps = 0

    # -- estado interno ----------------------------------------------------

    @property
    def in_green(self):
        return self._mode == "green"

    @property
    def green_phase(self):
        return self._phase

    @property
    def green_elapsed(self):
        return self._timer if self._mode == "green" else 0

    @property
    def can_switch(self):
        return self._mode == "green" and self._timer >= self.min_green

    @property
    def must_switch(self):
        return self._mode == "green" and self._timer >= self.max_green

    # -- comandos ----------------------------------------------------------

    def reset(self):
        traci.trafficlight.setProgram(TLS_ID, "0")
        self._pending = None
        self.switches = 0
        self.lost_steps = 0
        self._enter(GREEN_PHASES[0], "green")

    def request_switch(self):
        """Inicia a transicao para o proximo verde, se o verde minimo passou."""
        if not self.can_switch:
            return False
        idx = GREEN_PHASES.index(self._phase)
        self._pending = GREEN_PHASES[(idx + 1) % len(GREEN_PHASES)]
        self._enter(YELLOW_OF[self._phase], "yellow")
        return True

    def tick(self):
        """Avanca a maquina de estados. Chamar ANTES de traci.simulationStep()."""
        if self._mode == "yellow" and self._timer >= self.yellow_steps:
            self._enter(ALL_RED_PHASE, "all_red")
        elif self._mode == "all_red" and self._timer >= self.all_red_steps:
            self._enter(self._pending, "green")
            self._pending = None
            self.switches += 1
        if self._mode != "green":
            self.lost_steps += 1
        self._timer += 1

    # -- interno -----------------------------------------------------------

    def _enter(self, phase, mode):
        traci.trafficlight.setPhase(TLS_ID, int(phase))
        traci.trafficlight.setPhaseDuration(TLS_ID, self.HOLD)
        if mode == "green":
            self._phase = int(phase)
        self._mode = mode
        self._timer = 0


# =============================================================================
# Metricas
# =============================================================================


@dataclass
class EpisodeMetrics:
    """Acumula metricas em janela, ignorando o aquecimento da rede."""

    warmup_steps: int = 0
    steps: int = 0
    counted: int = 0
    queue_sum: float = 0.0
    queue_max: float = 0.0
    wait_sum: float = 0.0
    speed_sum: float = 0.0
    speed_n: int = 0
    arrived: int = 0
    teleports: int = 0
    switches: int = 0
    lost_steps: int = 0

    def observe(self, step, queue, wait, speed, arrived, teleports):
        self.steps = step
        if step < self.warmup_steps:
            return
        self.counted += 1
        self.arrived += arrived
        self.teleports += teleports
        self.queue_sum += queue
        self.queue_max = max(self.queue_max, queue)
        self.wait_sum += wait
        if speed is not None:
            self.speed_sum += speed
            self.speed_n += 1

    def summary(self):
        n = max(self.counted, 1)
        hours = n / 3600.0
        return {
            "mean_queue": self.queue_sum / n,
            "max_queue": self.queue_max,
            "mean_lane_wait": self.wait_sum / n,
            "mean_speed": (self.speed_sum / self.speed_n) if self.speed_n else 0.0,
            "arrived": self.arrived,
            "throughput_per_hour": self.arrived / hours,
            "teleports": self.teleports,
            "switches": self.switches,
            "lost_time_s": self.lost_steps,
        }


def parse_tripinfo(path, min_depart=0.0):
    """
    Le o tripinfo do SUMO e agrega por veiculo concluido.

    E a metrica de referencia: mede o que aconteceu com cada veiculo do inicio
    ao fim da viagem, e nao um instantaneo de detector. Veiculos que partiram
    durante o aquecimento sao descartados.
    """
    empty = {"n_trips": 0, "mean_wait": 0.0, "mean_time_loss": 0.0,
             "mean_duration": 0.0, "p90_wait": 0.0, "total_wait": 0.0,
             "mean_depart_delay": 0.0, "mean_total_delay": 0.0}
    if not os.path.exists(path):
        return dict(empty)
    waits, losses, durations, dep_delays = [], [], [], []
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag != "tripinfo":
            continue
        if float(elem.get("depart", 0.0)) >= min_depart:
            waits.append(float(elem.get("waitingTime", 0.0)))
            losses.append(float(elem.get("timeLoss", 0.0)))
            durations.append(float(elem.get("duration", 0.0)))
            dep_delays.append(float(elem.get("departDelay", 0.0)))
        elem.clear()
    if not waits:
        return dict(empty)
    w = np.asarray(waits)
    dd = np.asarray(dep_delays)
    tl = np.asarray(losses)
    return {
        # departDelay e onde a demora se esconde quando o cruzamento satura:
        # o SUMO retem o veiculo na insercao e o tempo dentro da rede nao
        # registra nada. Sem esta parcela, um cenario saturado parece saudavel.
        "mean_depart_delay": float(dd.mean()),
        "mean_total_delay": float((tl + dd).mean()),
        "n_trips": len(waits),
        "mean_wait": float(w.mean()),
        "p90_wait": float(np.percentile(w, 90)),
        "total_wait": float(w.sum()),
        "mean_time_loss": float(np.mean(losses)),
        "mean_duration": float(np.mean(durations)),
    }


# =============================================================================
# Ambiente
# =============================================================================


@dataclass
class EnvConfig:
    horizon: int = 1800            # steps de simulacao por episodio
    decision_interval: int = 5     # steps entre decisoes do agente
    min_green: int = 10            # verde minimo, em steps
    max_green: int = 60            # verde maximo, evita starvation
    warmup_steps: int = 300        # excluido das metricas
    control: str = "agent"         # "agent" = autoridade total | "fixed" = programa estatico
    switch_penalty: float = 0.05
    # Pesos da recompensa.
    #
    # O termo de fila soma a fila das faixas COM a fila de insercao (veiculos
    # que o SUMO retem fora da rede por falta de espaco). Sem essa segunda
    # parcela existe uma brecha que o agente encontra: reduzir a fila das
    # faixas admitindo menos veiculos. Medido, o DQN chegava ao melhor time
    # loss (13,7 s) e a melhor fila (4,53) de todas as politicas, e ainda
    # assim ficava atras no atraso TOTAL, porque empurrava 131,7 s de atraso
    # para a insercao. Contando as duas filas, empurrar deixa de ser ganho.
    #
    # O termo de vazao complementa: em saturacao, minimizar atraso total
    # equivale a maximizar veiculos escoados.
    w_queue: float = 0.35
    w_pending: float = 0.30
    w_wait: float = 0.10
    w_throughput: float = 0.25
    wait_cap_per_lane: float = 60.0
    discharge_cap: float = 1.5      # veic/s de descarga de referencia
    pending_cap: float = 60.0       # veiculos retidos na insercao, referencia


class SpIntersection:
    """
    Ambiente estilo Gym para o cruzamento de SP.

    step(action) avanca a simulacao ate o proximo ponto de decisao, definido
    como: passaram-se pelo menos decision_interval steps E o semaforo esta em
    verde. Isso faz com que o agente nunca seja consultado durante amarelo ou
    all-red, e que o tempo perdido da transicao seja efetivamente pago.
    """

    def __init__(self, config):
        self.cfg = config
        self.tl = SafeTrafficLight(config.min_green, config.max_green)
        self.metrics = EpisodeMetrics(warmup_steps=config.warmup_steps)
        self.sim_step = 0
        self._capacity = {}
        self._total_capacity = 1.0
        self._det = {}
        self._lane = {}
        self._acc_queue = 0.0
        self._acc_wait = 0.0
        self._acc_n = 0
        self._acc_arrived = 0
        self._acc_pending = 0.0
        self._fixed_lost_steps = 0
        self._phase_now = GREEN_PHASES[0]
        self._running = False

    # -- ciclo de vida -----------------------------------------------------

    def reset(self, seed, gui=False, tripinfo=None, scale=None):
        self.close()
        traci.start(sumo_cmd(seed, gui=gui, tripinfo=tripinfo,
                             scale=scale, end=self.cfg.horizon + 1))
        self._running = True
        self.sim_step = 0
        self.metrics = EpisodeMetrics(warmup_steps=self.cfg.warmup_steps)
        self.tl = SafeTrafficLight(self.cfg.min_green, self.cfg.max_green)
        self._fixed_lost_steps = 0

        for det in DETECTORS:
            traci.lanearea.subscribe(det, [
                tc.LAST_STEP_VEHICLE_NUMBER,
                tc.LAST_STEP_VEHICLE_HALTING_NUMBER,
                tc.LAST_STEP_OCCUPANCY,
                tc.LAST_STEP_MEAN_SPEED,
            ])
            length = traci.lanearea.getLength(det)
            self._capacity[det] = max(length / VEH_FOOTPRINT, 1.0)
        self._total_capacity = sum(self._capacity.values())

        for lane in INCOMING_LANES:
            traci.lane.subscribe(lane, [
                tc.LAST_STEP_VEHICLE_HALTING_NUMBER,
                tc.VAR_WAITING_TIME,
                tc.LAST_STEP_MEAN_SPEED,
                tc.LAST_STEP_VEHICLE_NUMBER,
            ])

        # A fase corrente vem por assinatura para que o braco de tempo fixo
        # possa ler a fase e contabilizar seu proprio amarelo/all-red sem
        # gastar uma chamada TraCI extra por step.
        traci.trafficlight.subscribe(TLS_ID, [tc.TL_CURRENT_PHASE])
        self._phase_now = GREEN_PHASES[0]

        if self.cfg.control == "agent":
            self.tl.reset()

        # Um step para popular as assinaturas antes da primeira leitura.
        self._advance_one()
        self._reset_accumulators()
        return self.state()

    def close(self):
        if self._running:
            try:
                traci.close()
            except Exception:
                pass
            self._running = False

    # -- passo -------------------------------------------------------------

    def step(self, action):
        forced = False
        if self.cfg.control == "agent":
            if self.tl.must_switch:
                action, forced = 1, True
            elif not self.tl.can_switch:
                action, forced = 0, True
            if action == 1:
                self.tl.request_switch()

        self._reset_accumulators()
        n = 0
        while True:
            done = self._advance_one()
            n += 1
            if done:
                break
            if n >= self.cfg.decision_interval and (
                self.cfg.control != "agent" or self.tl.in_green
            ):
                break

        reward = self._reward(switched=(action == 1 and not forced))
        info = {"forced": forced, "action": action, "steps": n,
                "sim_step": self.sim_step}
        return self.state(), reward, done, info

    def _advance_one(self):
        if self.cfg.control == "agent":
            self.tl.tick()
        traci.simulationStep()
        self.sim_step += 1
        self._det = traci.lanearea.getAllSubscriptionResults()
        self._lane = traci.lane.getAllSubscriptionResults()
        self._phase_now = traci.trafficlight.getSubscriptionResults(TLS_ID).get(
            tc.TL_CURRENT_PHASE, self._phase_now)
        if self.cfg.control != "agent" and self._phase_now not in GREEN_PHASES:
            self._fixed_lost_steps += 1

        queue, wait, speed_sum, nveh = 0.0, 0.0, 0.0, 0
        for lane in INCOMING_LANES:
            row = self._lane.get(lane, {})
            queue += row.get(tc.LAST_STEP_VEHICLE_HALTING_NUMBER, 0)
            wait += row.get(tc.VAR_WAITING_TIME, 0.0)
            k = row.get(tc.LAST_STEP_VEHICLE_NUMBER, 0)
            if k:
                speed_sum += row.get(tc.LAST_STEP_MEAN_SPEED, 0.0) * k
                nveh += k

        arrived = traci.simulation.getArrivedNumber()
        # Fila de insercao: veiculos que o SUMO nao conseguiu inserir.
        # Ground truth, usado apenas na recompensa e nas metricas.
        self._acc_pending += len(traci.simulation.getPendingVehicles())
        self._acc_queue += queue
        self._acc_wait += wait
        self._acc_arrived += arrived
        self._acc_n += 1

        self.metrics.observe(
            self.sim_step, queue, wait,
            (speed_sum / nveh) if nveh else None,
            arrived,
            traci.simulation.getStartingTeleportNumber(),
        )
        if self.cfg.control == "agent":
            self.metrics.switches = self.tl.switches
            self.metrics.lost_steps = self.tl.lost_steps
        else:
            self.metrics.lost_steps = self._fixed_lost_steps

        if self.sim_step >= self.cfg.horizon:
            return True
        if self.sim_step > 100 and traci.simulation.getMinExpectedNumber() <= 0:
            return True
        return False

    def _reset_accumulators(self):
        self._acc_queue = 0.0
        self._acc_wait = 0.0
        self._acc_n = 0
        self._acc_arrived = 0
        self._acc_pending = 0.0

    # -- estado ------------------------------------------------------------

    def state(self):
        """
        Vetor de estado normalizado em [0, 1].

        Le APENAS os detectores E2, que representam as ROIs das cameras. A
        normalizacao usa a capacidade do detector em veiculos (comprimento /
        7.5 m), nao o comprimento em metros: antes, dividir por 20.0 mantinha
        as features esmagadas em [0; 0,15] enquanto o one-hot de fase valia 1.
        """
        out = np.empty(STATE_SIZE, dtype=np.float32)
        i = 0
        for det in DETECTORS:
            row = self._det.get(det, {})
            cap = self._capacity.get(det, 1.0)
            lane_row = self._lane.get(DETECTOR_LANE[det], {})
            mean_speed = row.get(tc.LAST_STEP_MEAN_SPEED, -1.0)
            out[i + 0] = min(row.get(tc.LAST_STEP_VEHICLE_NUMBER, 0) / cap, 1.0)
            out[i + 1] = min(row.get(tc.LAST_STEP_VEHICLE_HALTING_NUMBER, 0) / cap, 1.0)
            out[i + 2] = min(row.get(tc.LAST_STEP_OCCUPANCY, 0.0) / 100.0, 1.0)
            # -1 significa detector vazio: trata-se como fluxo livre.
            out[i + 3] = 1.0 if mean_speed < 0 else min(mean_speed / MAX_SPEED, 1.0)
            out[i + 4] = min(lane_row.get(tc.VAR_WAITING_TIME, 0.0)
                             / self.cfg.wait_cap_per_lane, 1.0)
            i += FEATURES_PER_DETECTOR

        if self.cfg.control == "agent":
            phase = self.tl.green_phase
        else:
            phase = self._phase_now
        onehot = [0.0] * 5
        if 0 <= phase < 5:
            onehot[phase] = 1.0
        out[i:i + 5] = onehot
        i += 5

        if self.cfg.control == "agent":
            out[i + 0] = min(self.tl.green_elapsed / max(self.cfg.max_green, 1), 1.0)
            out[i + 1] = 1.0 if self.tl.can_switch else 0.0
            out[i + 2] = 1.0 if self.tl.must_switch else 0.0
        else:
            out[i:i + 3] = 0.0
        return out

    # -- recompensa --------------------------------------------------------

    def _reward(self, switched):
        """
        Recompensa unica, usada no treino e reportada na avaliacao.

        Usa ground truth de faixa (nao os detectores), porque a recompensa e
        sinal de aprendizado e nao entrada de inferencia. Fica limitada a
        cerca de [-1,05; 0], o que casa com Huber + Adam sem escalonamento
        adicional.
        """
        n = max(self._acc_n, 1)
        q = (self._acc_queue / n) / self._total_capacity
        w = (self._acc_wait / n) / (len(INCOMING_LANES) * self.cfg.wait_cap_per_lane)
        thr = (self._acc_arrived / n) / self.cfg.discharge_cap
        pend = (self._acc_pending / n) / self.cfg.pending_cap
        r = (self.cfg.w_throughput * min(thr, 1.0)
             - self.cfg.w_queue * min(q, 1.0)
             - self.cfg.w_pending * min(pend, 1.0)
             - self.cfg.w_wait * min(w, 1.0))
        if switched:
            r -= self.cfg.switch_penalty
        return float(r)


# =============================================================================
# Politicas de referencia
# =============================================================================


def max_pressure_action(env, margin=None):
    """
    Max-pressure com custo de troca -- baseline adaptativa forte.

    A versao ingenua (margin=1.0) troca sempre que o outro grupo tem mais um
    veiculo que o atual. Isso ignora que cada troca custa yellow+all-red de
    verde: com min_green curto ela troca ~119 vezes por 1800 s, queima 26% do
    horizonte em transicao e perde para um rateio de duracao fixa.

    Aqui o limiar e o numero de veiculos que o grupo ATUAL conseguiria
    descarregar durante o tempo perdido da transicao (~1 veiculo a cada 2 s por
    faixa). So vale trocar se a fila do outro grupo superar esse custo.
    """
    cur = env.tl.green_phase
    idx = GREEN_PHASES.index(cur)
    other = GREEN_PHASES[(idx + 1) % len(GREEN_PHASES)]

    def group_queue(phase):
        total = 0.0
        for lane in PHASE_LANES[phase]:
            row = env._lane.get(lane, {})
            total += row.get(tc.LAST_STEP_VEHICLE_HALTING_NUMBER, 0)
        return total

    q_cur, q_other = group_queue(cur), group_queue(other)
    if margin is None:
        lost = env.tl.yellow_steps + env.tl.all_red_steps
        margin = len(PHASE_LANES[cur]) * lost / 2.0

    # Grupo atual vazio: nao ha nada a descarregar, o custo da troca e menor.
    if q_cur < 1.0:
        return 1 if q_other > 0 else 0
    return 1 if q_other > q_cur + margin else 0


def max_pressure_naive_action(env):
    """Versao ingenua, sem custo de troca. Mantida para comparacao."""
    return max_pressure_action(env, margin=1.0)


def ensure_runs_dir():
    os.makedirs(RUNS_DIR, exist_ok=True)
    return RUNS_DIR
