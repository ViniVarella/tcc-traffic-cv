"""Episódios da seleção livre de fase em qualquer cruzamento (só SUMO, percepção ground truth).

Mesmo protocolo do ``episode_runner`` do DQN v2 (aquecimento com regra fixa,
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

from controller.phase_selection_controller import PhaseSelectionController
from controller.phase_selection_state import PhaseObservation, PhaseStateEncoder
from controller.decision_scheduler import SmdpAccumulator
from controller.rewards import RewardWeights
from experiments.episode_runner import EpisodeOutcome, EpisodeSettings, RewardModel, incoming_lane_capacity
from sumo import ExperimentMetricsCollector, SumoClient
from sumo.intersection import IntersectionLayout, load_intersection
from sumo.lane_feature_source import TraciLaneFeatureSource
from vision.lane_features import KinematicsParameters, LaneGeometry, load_lane_geometries


class PhasePolicy(Protocol):
    def __call__(self, observation: PhaseObservation) -> int: ...


PolicyFactory = Callable[[IntersectionLayout], PhasePolicy]


@dataclass(frozen=True, slots=True)
class GenericScenario:
    intersection: str
    demand: str
    split: str
    net: Path
    sumocfg: Path

    @property
    def name(self) -> str:
        return f"{self.intersection}/{self.demand}"


def load_scenarios(config: Mapping[str, Any], base_dir: Path) -> list[GenericScenario]:
    scenarios = []
    for name, raw in config["intersections"].items():
        for demand, sumocfg in raw["scenarios"].items():
            scenarios.append(GenericScenario(name, str(demand), str(raw["split"]), (base_dir / raw["net"]).resolve(),
                                             (base_dir / sumocfg).resolve()))
    return scenarios


def profile_geometries(profile: Mapping[str, Any]) -> dict[tuple[str, str], LaneGeometry]:
    """ROIs de um perfil de câmeras, reindexadas por ``(edge, lane_k)`` como as geradas."""
    geometries = {}
    for geometry in load_lane_geometries(profile).values():
        edge, _, index = geometry.sumo_lane.rpartition("_")
        geometries[(edge, f"lane_{index}")] = replace(geometry, camera_id=edge, lane_id=f"lane_{index}")
    return geometries


def max_red_seconds(phase_count: int, max_green_s: float, yellow_s: float, all_red_s: float) -> float:
    return (phase_count - 1) * (max_green_s + yellow_s + all_red_s)


class PhaseSelectionEnvironment:
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
        if scenario.net not in self._layouts:
            raw = self.config["intersections"][scenario.intersection]
            layout = load_intersection(scenario.net, raw.get("tls_id"), self.roi_length_m)
            if "roi_profile" in raw:
                # ROIs reais das câmeras (ex.: sp.yaml), para comparar no mesmo ambiente das avaliações.
                profile = yaml.safe_load((self.base_dir / raw["roi_profile"]).read_text(encoding="utf-8"))
                layout = replace(layout, geometries=profile_geometries(profile))
            self._layouts[scenario.net] = layout
        return self._layouts[scenario.net]

    def encoder(self, layout: IntersectionLayout) -> PhaseStateEncoder:
        dqn = self.config.get("dqn", {})
        return PhaseStateEncoder(
            self.max_phases, self.max_green_s,
            max_red_seconds(len(layout.greens), self.max_green_s, self.yellow_s, self.all_red_s),
            float(dqn.get("max_speed_mps", 13.89)), float(dqn.get("waiting_reference_seconds", 60.0)),
        )

    def run(self, scenario: GenericScenario, seed: int, make_policy: PolicyFactory, learner: Any | None = None,
            on_step: Callable[[dict[str, Any]], None] | None = None) -> EpisodeOutcome:
        layout = self.layout(scenario)
        sumo = self.config.get("sumo", {})
        client = SumoClient("sumo", str(scenario.sumocfg), gui=False, seed=seed, step_length=sumo.get("step_length", 1.0),
                            traci_port=sumo.get("traci_port", 8873))
        client.start()
        try:
            lanes = layout.incoming_lanes
            reward = RewardModel(lanes, incoming_lane_capacity([client.get_lane_length(lane) for lane in lanes]), self.reward_weights)
            controller = PhaseSelectionController(layout.tls_id, [green.state for green in layout.greens], self.min_green_s,
                                                  self.max_green_s, self.yellow_s, self.all_red_s)
            source = TraciLaneFeatureSource(layout.geometries, self.parameters, seed=seed)
            return run_phase_episode(client=client, layout=layout, controller=controller,
                                     observe=lambda sim_time: source.observe(client, sim_time), encoder=self.encoder(layout),
                                     policy=make_policy(layout), reward=reward, settings=self.settings, learner=learner,
                                     on_step=on_step)
        finally:
            client.close()


def run_phase_episode(
    *,
    client: Any,
    layout: IntersectionLayout,
    controller: PhaseSelectionController,
    observe: Callable[[float], Mapping[Any, Any]],
    encoder: PhaseStateEncoder,
    policy: PhasePolicy,
    reward: RewardModel,
    settings: EpisodeSettings,
    learner: Any | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> EpisodeOutcome:
    groups = [layout.lane_keys(phase) for phase in range(len(layout.greens))]
    capacities = {key: geometry.capacity for key, geometry in layout.geometries.items()}
    accumulator = SmdpAccumulator(settings.gamma)
    metrics = ExperimentMetricsCollector(warmup_until_s=settings.warmup_s)
    outcome = EpisodeOutcome()
    last_state = None
    last_decision: tuple[float, float] | None = None  # (início do verde, instante da decisão)
    for _ in range(int(round(settings.warmup_s + settings.control_s))):
        sim_time = client.step()
        lane_metrics = client.get_incoming_lane_metrics(reward.lanes)
        metrics.observe(sim_time, client.get_simulation_events(), client.get_active_vehicle_metrics(),
                        pending_vehicles=int(lane_metrics["pending_vehicles"]), teleports=client.get_teleport_count())
        step_reward = reward(lane_metrics)
        lane_features = observe(sim_time)
        elapsed = controller.elapsed(sim_time)
        phase_name = controller.phase_name
        choice: int | None = None
        if sim_time <= settings.warmup_s:
            if controller.is_green and elapsed >= settings.warmup_switch_after_s:
                choice = controller.next_cyclic()
            decision = controller.update(sim_time, choice)
        else:
            outcome.controlled_steps += 1
            outcome.total_reward += step_reward
            outcome.phase_seconds[phase_name] += 1
            accumulator.add(step_reward)
            if _is_decision_point(controller, sim_time, settings.decision_interval_s, last_decision):
                observation = encoder.encode(
                    lane_features, groups, capacities, controller.current, elapsed,
                    [controller.red_time(phase, sim_time) for phase in range(controller.phase_count)],
                    decision_mask(controller, sim_time, lane_features, groups, encoder.max_red_s),
                )
                last_state = observation.state
                _learn(learner, accumulator.close(last_state), outcome)
                choice = int(policy(observation))
                if not observation.mask[choice]:
                    raise ValueError(f"A política escolheu a fase {choice}, fora da máscara {observation.mask}.")
                accumulator.open(last_state, choice)
                last_decision = (controller.started_at, sim_time)
                outcome.decisions += 1
                outcome.switches += choice != controller.current
            decision = controller.update(sim_time, choice)
        controller.apply(client, decision)
        if on_step is not None:
            on_step({"sim_time": sim_time, "reward": step_reward, "phase": phase_name, "decision": decision,
                     "requested_phase": choice})
    if last_state is not None:
        _learn(learner, accumulator.close(last_state), outcome)
    outcome.metrics = metrics.summary()
    return outcome


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
    if not controller.is_green:
        return False
    elapsed = controller.elapsed(sim_time)
    if elapsed < controller.min_green_s:
        return False
    if elapsed >= controller.max_green_s or last_decision is None or last_decision[0] != controller.started_at:
        return True
    # Tolerância para tempos de ponto flutuante do SUMO.
    return sim_time - last_decision[1] >= interval_s - 1e-6


def _learn(learner: Any | None, transition: Any, outcome: EpisodeOutcome) -> None:
    if learner is None or transition is None:
        return
    learner.remember(transition.state, transition.action, transition.reward, transition.next_state, False,
                     discount=transition.discount)
    outcome.transitions += 1
    loss = learner.train_step()
    if loss is not None:
        outcome.losses.append(loss)
