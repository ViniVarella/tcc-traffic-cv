"""Episódios da escolha livre de estágio em qualquer cruzamento (modelo global, produto v6.0).

Sem ``observer`` a percepção é *ground truth* (TraCI); com ele, vem da Unity.
Mesmo protocolo do laço manter/trocar (``simulation.episode``: aquecimento com regra fixa,
decisões a cada ``decision_interval_s`` entre o verde mínimo e o máximo,
transições SMDP, recompensa de nível nas faixas de entrada), com três
diferenças: a ação é a fase verde escolhida; no verde máximo a política escolhe
entre as outras fases; e uma fase com veículos parados há mais de ``max_red_s``
no vermelho passa a ser a única opção (justiça). ``max_red_s`` é o vermelho de
um ciclo de tempo fixo com todos os verdes no máximo: nenhuma fase espera mais
do que esperaria no tempo fixo.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol

import yaml

from controller.phase_selection.controller import PhaseSelectionController
from controller.phase_selection.state import STATE_VERSION, PhaseObservation, PhaseStateEncoder
from controller.smdp import SmdpAccumulator
from controller.rewards import RewardWeights
from simulation.episode import (EpisodeOutcome, EpisodeSettings, RewardModel, incoming_lane_capacity, learn_transition,
                                observe_traffic)
from sumo import ExperimentMetricsCollector, SumoClient
from sumo.intersection import IntersectionLayout, load_intersection
from sumo.lane_feature_source import TraciLaneFeatureSource
from vision.lane_features import KinematicsParameters, LaneGeometry, load_lane_geometries


class PhasePolicy(Protocol):
    """Escolhe o estágio verde a partir da observação (um índice dentro da máscara)."""

    def __call__(self, observation: PhaseObservation) -> int: ...


PolicyFactory = Callable[[IntersectionLayout], PhasePolicy]


@dataclass(frozen=True, slots=True)
class GenericScenario:
    """Um cruzamento de ``configs/generic.yaml`` com uma das suas demandas."""

    intersection: str
    demand: str
    split: str
    net: Path
    sumocfg: Path
    # Fase exclusiva de pedestres depois do último verde do programa (0 = sem).
    pedestrian_s: float = 0.0

    @property
    def name(self) -> str:
        return f"{self.intersection}/{self.demand}"


def pedestrian_seconds(block: Mapping[str, Any] | None) -> float:
    """Duração da fase exclusiva de pedestres (verde + liberação) de um bloco de configuração.

    O bloco é ``pedestrian_phase`` em ``generic.yaml`` ou ``pedestrians`` em ``sp.yaml``.
    """
    block = block or {}
    return float(block.get("green_seconds", 0.0)) + float(block.get("clearance_seconds", 0.0))


def pedestrian_hcm_delay(starts: Sequence[float], green_s: float) -> dict[str, float] | None:
    """Espera dos pedestres estimada pelo HCM a partir dos inícios reais da fase de pedestres.

    Com chegadas uniformes, num intervalo C entre dois inícios de verde a espera
    média é (C − g)² / (2C); a média do episódio pondera cada intervalo pela sua
    duração: Σ(C − g)² / (2 ΣC). A espera máxima é a de quem chega logo depois
    do fim do verde: max(C) − g. Sem dois inícios, não há intervalo para medir.
    """
    cycles = [later - earlier for earlier, later in zip(starts, starts[1:])]
    if not cycles:
        return None
    lost = [max(0.0, cycle - green_s) for cycle in cycles]
    return {"mean_wait_s": sum(value * value for value in lost) / (2 * sum(cycles)),
            "max_wait_s": max(lost), "mean_interval_s": sum(cycles) / len(cycles), "phases": len(starts)}


def load_scenarios(config: Mapping[str, Any], base_dir: Path) -> list[GenericScenario]:
    """Cruzamento × demanda; com ``pedestrian_variants``, cada demanda ganha a variante ``<demanda>+ped``."""
    scenarios = []
    pedestrians = pedestrian_seconds(config.get("pedestrian_phase"))
    for name, raw in config["intersections"].items():
        variants = [0.0, pedestrians] if raw.get("pedestrian_variants") and pedestrians > 0 else [0.0]
        for demand, sumocfg in raw["scenarios"].items():
            for seconds in variants:
                scenarios.append(GenericScenario(name, f"{demand}+ped" if seconds else str(demand), str(raw["split"]),
                                                 (base_dir / raw["net"]).resolve(), (base_dir / sumocfg).resolve(), seconds))
    return scenarios


def lane_key(sumo_lane: str) -> tuple[str, str]:
    """Chave ``(edge, lane_k)`` de uma faixa do SUMO, a mesma das ROIs geradas."""
    edge, _, index = sumo_lane.rpartition("_")
    return edge, f"lane_{index}"


def profile_geometries(profile: Mapping[str, Any]) -> dict[tuple[str, str], LaneGeometry]:
    """ROIs de um perfil de câmeras, reindexadas por ``(edge, lane_k)`` como as geradas."""
    geometries = {}
    for geometry in load_lane_geometries(profile).values():
        edge, lane = lane_key(geometry.sumo_lane)
        geometries[(edge, lane)] = replace(geometry, camera_id=edge, lane_id=lane)
    return geometries


def camera_key_map(profile: Mapping[str, Any]) -> dict[tuple[str, str], tuple[str, str]]:
    """``(câmera, faixa)`` da percepção visual → ``(edge, lane_k)`` do ambiente genérico."""
    return {key: lane_key(geometry.sumo_lane) for key, geometry in load_lane_geometries(profile).items()}


def remap_features(features: Mapping[Any, Any] | None, key_map: Mapping[Any, Any]) -> dict[Any, Any] | None:
    """Reindexa as features de uma fonte visual; ``None`` (sem frames) continua ``None``."""
    return None if features is None else {key_map.get(key, key): value for key, value in features.items()}


def max_red_seconds(phase_count: int, max_green_s: float, yellow_s: float, all_red_s: float) -> float:
    """Pior vermelho no tempo fixo com todos os verdes no máximo: o limite da regra de justiça."""
    return (phase_count - 1) * (max_green_s + yellow_s + all_red_s)


class PhaseSelectionEnvironment:
    """Cruzamentos de ``configs/generic.yaml`` (sintéticos e o SP) para a escolha livre de estágio.

    Guarda a configuração comum (verdes, amarelo, ROIs, recompensa) e roda
    episódios em qualquer cenário com uma política escolhida por fábrica.
    """

    def __init__(self, config: dict[str, Any], base_dir: Path, settings: EpisodeSettings) -> None:
        self.config = config
        self.base_dir = base_dir
        self.settings = settings
        control = config["traffic_control"]
        self.min_green_s = float(control["min_green_seconds"])
        self.max_green_s = float(control["max_green_seconds"])
        self.yellow_s = float(control["yellow_seconds"])
        self.all_red_s = float(control["all_red_seconds"])
        self.roi_length_m = float(config.get("roi_length_m", 60.0))
        self.max_phases = int(config.get("max_phases", 8))
        self.parameters = KinematicsParameters.from_config(config)
        self.reward_weights = RewardWeights.from_config(config)
        self.scenarios = load_scenarios(config, base_dir)
        # Fase de pedestres obrigatória por tempo (N s); sem o campo, a regra antiga (depois do último verde).
        interval = (config.get("pedestrian_phase") or {}).get("interval_seconds")
        self.pedestrian_interval_s = None if interval is None else float(interval)
        self._layouts: dict[Path, IntersectionLayout] = {}

    @classmethod
    def from_file(cls, path: Path, settings: EpisodeSettings) -> "PhaseSelectionEnvironment":
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")), path.parent.parent, settings)

    def scenario(self, name: str) -> GenericScenario:
        for scenario in self.scenarios:
            if scenario.name == name:
                return scenario
        raise ValueError(f"Cenário desconhecido: {name!r}.")

    def split(self, split: str) -> list[GenericScenario]:
        return [scenario for scenario in self.scenarios if scenario.split == split]

    def layout(self, scenario: GenericScenario) -> IntersectionLayout:
        """Estágios, faixas e ROIs do cruzamento (lidos uma vez por rede)."""
        if scenario.net not in self._layouts:
            raw = self.config["intersections"][scenario.intersection]
            layout = load_intersection(scenario.net, raw.get("tls_id"), self.roi_length_m)
            if "roi_profile" in raw:
                # ROIs reais das câmeras (ex.: sp.yaml), para comparar no mesmo ambiente das avaliações.
                profile = yaml.safe_load((self.base_dir / raw["roi_profile"]).read_text(encoding="utf-8"))
                layout = replace(layout, geometries=profile_geometries(profile))
            self._layouts[scenario.net] = layout
        return self._layouts[scenario.net]

    def encoder(self, layout: IntersectionLayout, pedestrian_s: float = 0.0,
                state_version: str = STATE_VERSION) -> PhaseStateEncoder:
        """Encoder do cruzamento; a justiça (``max_red_s``) inclui a fase de pedestres de um ciclo."""
        dqn = self.config.get("dqn", {})
        return PhaseStateEncoder(
            self.max_phases, self.max_green_s,
            max_red_seconds(len(layout.greens), self.max_green_s, self.yellow_s, self.all_red_s) + pedestrian_s,
            float(dqn.get("max_speed_mps", 13.89)), float(dqn.get("waiting_reference_seconds", 60.0)),
            state_version,
        )

    def camera_key_map(self, scenario: GenericScenario) -> dict[tuple[str, str], tuple[str, str]]:
        """Tradução das chaves da visão; só cruzamentos com ``roi_profile`` (câmeras reais) têm visão."""
        raw = self.config["intersections"][scenario.intersection]
        if "roi_profile" not in raw:
            raise ValueError(f"{scenario.intersection} não tem câmeras (roi_profile): a percepção visual não se aplica.")
        return camera_key_map(yaml.safe_load((self.base_dir / raw["roi_profile"]).read_text(encoding="utf-8")))

    def run(self, scenario: GenericScenario, seed: int, make_policy: PolicyFactory, learner: Any | None = None,
            on_step: Callable[[dict[str, Any]], None] | None = None, observer: Any | None = None,
            state_version: str = STATE_VERSION) -> EpisodeOutcome:
        """Um episódio; sem ``observer`` a percepção é *ground truth* (TraCI).

        Com ``observer`` (ex.: ``UnityVisualObserver``), as features vêm da visão,
        reindexadas para ``(edge, lane_k)``; steps sem frames não decidem.
        """
        layout = self.layout(scenario)
        key_map = None if observer is None else self.camera_key_map(scenario)
        sumo = self.config.get("sumo", {})
        client = SumoClient("sumo", str(scenario.sumocfg), gui=False, seed=seed, step_length=sumo.get("step_length", 1.0),
                            traci_port=sumo.get("traci_port", 8873))
        client.start()
        try:
            lanes = layout.incoming_lanes
            reward = RewardModel(lanes, incoming_lane_capacity([client.get_lane_length(lane) for lane in lanes]), self.reward_weights)
            controller = self._controller(layout, scenario)
            if observer is None:
                source = TraciLaneFeatureSource(layout.geometries, self.parameters, seed=seed)
                observe: Callable[[float], Mapping[Any, Any] | None] = lambda sim_time: source.observe(client, sim_time)
            else:
                visual = observer.begin_episode(client, seed)
                observe = lambda sim_time: remap_features(visual(sim_time), key_map)
            outcome = run_phase_episode(client=client, layout=layout, controller=controller,
                                        observe=observe, encoder=self.encoder(layout, scenario.pedestrian_s, state_version),
                                        policy=make_policy(layout), reward=reward, settings=self.settings, learner=learner,
                                        on_step=on_step)
            outcome.pedestrian_starts = [start for start in controller.pedestrian_starts if start > self.settings.warmup_s]
            return outcome
        finally:
            client.close()

    def _controller(self, layout: IntersectionLayout, scenario: GenericScenario) -> PhaseSelectionController:
        """Camada de segurança do cruzamento; com pedestres, a fase deles vem por tempo ou depois do último verde."""
        has_pedestrians = scenario.pedestrian_s > 0
        by_time = has_pedestrians and self.pedestrian_interval_s is not None
        return PhaseSelectionController(
            layout.tls_id, [green.state for green in layout.greens], self.min_green_s, self.max_green_s,
            self.yellow_s, self.all_red_s,
            pedestrian_after=len(layout.greens) - 1 if has_pedestrians and not by_time else None,
            pedestrian_s=scenario.pedestrian_s,
            pedestrian_interval_s=self.pedestrian_interval_s if has_pedestrians else None,
        )


def run_phase_episode(
    *,
    client: Any,
    layout: IntersectionLayout,
    controller: PhaseSelectionController,
    observe: Callable[[float], Mapping[Any, Any] | None],
    encoder: PhaseStateEncoder,
    policy: PhasePolicy,
    reward: RewardModel,
    settings: EpisodeSettings,
    learner: Any | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> EpisodeOutcome:
    """Executa um episódio já iniciado em ``client``; ``learner`` ativa o aprendizado.

    No aquecimento o ciclo segue a ordem do programa (troca após
    ``warmup_switch_after_s``); no controle, a política escolhe o estágio em
    cada ponto de decisão, dentro da máscara da camada de segurança.
    """
    groups = [layout.lane_keys(phase) for phase in range(len(layout.greens))]
    capacities = {key: geometry.capacity for key, geometry in layout.geometries.items()}
    accumulator = SmdpAccumulator(settings.gamma)
    metrics = ExperimentMetricsCollector(warmup_until_s=settings.warmup_s)
    outcome = EpisodeOutcome()
    last_state = None
    last_decision: tuple[float, float] | None = None  # (início do verde, instante da decisão)
    for _ in range(settings.total_steps):
        sim_time = client.step()
        _, step_reward = observe_traffic(client, sim_time, reward, metrics)
        lane_features = observe(sim_time)
        elapsed = controller.elapsed(sim_time)
        phase_name = controller.phase_name
        choice: int | None = None
        if sim_time <= settings.warmup_s:
            if controller.is_green and elapsed >= settings.warmup_switch_after_s:
                choice = controller.next_cyclic()
            decision = controller.update(sim_time, choice)
        else:
            outcome.record_controlled_step(phase_name, step_reward)
            accumulator.add(step_reward)
            if lane_features is None:
                # Sem frames: nenhuma decisão (mantém o verde até o máximo, como o TraffIQ).
                outcome.missing_observations += 1
            elif _is_decision_point(controller, sim_time, settings.decision_interval_s, last_decision):
                observation = encode_observation(encoder, controller, sim_time, lane_features, groups, capacities)
                last_state = observation.state
                learn_transition(learner, accumulator.close(last_state), outcome)
                choice = int(policy(observation))
                if not observation.mask[choice]:
                    raise ValueError(f"A política escolheu a fase {choice}, fora da máscara {observation.mask}.")
                accumulator.open(last_state, choice)
                last_decision = (controller.started_at, sim_time)
                outcome.record_decision(choice != controller.current)
            decision = controller.update(sim_time, choice)
        controller.apply(client, decision)
        if on_step is not None:
            on_step({"sim_time": sim_time, "reward": step_reward, "phase": phase_name, "decision": decision,
                     "requested_phase": choice})
    if last_state is not None:
        learn_transition(learner, accumulator.close(last_state), outcome)
    outcome.metrics = metrics.summary()
    return outcome


def encode_observation(encoder: PhaseStateEncoder, controller: PhaseSelectionController, sim_time: float,
                       lane_features: Mapping[Any, Any], groups: Sequence[Sequence[Any]],
                       capacities: Mapping[Any, float]) -> PhaseObservation:
    """Estado por estágio do step: demanda das faixas, tempos do semáforo e máscara de escolhas."""
    phases = range(controller.phase_count)
    return encoder.encode(
        lane_features, groups, capacities, controller.current, controller.elapsed(sim_time),
        [controller.red_time(phase, sim_time) for phase in phases],
        decision_mask(controller, sim_time, lane_features, groups, encoder.max_red_s),
        [controller.switch_seconds(controller.current, phase, sim_time) for phase in phases],
        [controller.leave_seconds(phase, sim_time) for phase in phases],
    )


def decision_mask(controller: PhaseSelectionController, sim_time: float, lane_features: Mapping[Any, Any],
                  groups: Sequence[Sequence[Any]], max_red_s: float) -> tuple[bool, ...]:
    """Fases que a política pode escolher agora.

    Fases com veículos parados há mais de ``max_red_s`` no vermelho são as únicas
    opções; no verde máximo a fase atual sai da máscara.
    """
    count = controller.phase_count
    starving = [
        phase for phase in range(count)
        if phase != controller.current and controller.red_time(phase, sim_time) > max_red_s
        and any(lane_features[key].stopped_count > 0 for key in groups[phase] if key in lane_features)
    ]
    if starving:
        return tuple(phase in starving for phase in range(count))
    at_max = controller.elapsed(sim_time) >= controller.max_green_s
    return tuple(not (at_max and phase == controller.current) for phase in range(count))


def _is_decision_point(controller: PhaseSelectionController, sim_time: float, interval_s: float,
                       last_decision: tuple[float, float] | None) -> bool:
    """Em verde, depois do verde mínimo: a cada ``interval_s`` e sempre no verde máximo.

    Mesma regra do ``DecisionScheduler`` da linha manter/trocar, exceto no verde
    máximo: lá a troca é forçada; aqui a política escolhe para qual estágio.
    """
    if not controller.is_green:
        return False
    elapsed = controller.elapsed(sim_time)
    if elapsed < controller.min_green_s:
        return False
    if elapsed >= controller.max_green_s or last_decision is None or last_decision[0] != controller.started_at:
        return True
    # Tolerância para tempos de ponto flutuante do SUMO.
    return sim_time - last_decision[1] >= interval_s - 1e-6
