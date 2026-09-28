"""Laço de episódio único do DQN v2: pré-treino (TraCI), ajuste fino e avaliação (visão).

A diferença entre os modos é só a função ``observe``, que devolve as features
por faixa do step (ou ``None`` quando não há visão). A segurança do semáforo
roda em todo step; a política só é consultada em pontos de decisão, e o
aprendizado usa transições SMDP entre eles.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from controller import DqnAgent, DqnTrafficController
from controller.decision_scheduler import DecisionScheduler, SmdpAccumulator
from controller.rewards import RewardWeights, TrafficSnapshot, level_reward
from sumo import ExperimentMetricsCollector


LaneKey = tuple[str, str]
Observer = Callable[[float], Mapping[LaneKey, Any] | None]


class Policy(Protocol):
    def __call__(self, state: np.ndarray, lane_features: Mapping[LaneKey, Any], phase: Any) -> int: ...


@dataclass(frozen=True, slots=True)
class EpisodeSettings:
    warmup_s: float = 300.0
    control_s: float = 1800.0
    decision_interval_s: float = 5.0
    gamma: float = 0.99
    # Regra fixa, idêntica para todas as políticas, que conduz o aquecimento.
    warmup_switch_after_s: float = 30.0

    def __post_init__(self) -> None:
        if self.warmup_s < 0 or self.control_s <= 0 or self.warmup_switch_after_s <= 0:
            raise ValueError("Durações do episódio inválidas.")


@dataclass(frozen=True, slots=True)
class EpsilonSchedule:
    """ε linear por decisão, de ``start`` a ``end`` em ``decay_decisions``."""

    start: float = 1.0
    end: float = 0.05
    decay_decisions: int = 10_000

    def value(self, decision_index: int) -> float:
        if self.decay_decisions <= 0:
            return self.end
        fraction = min(1.0, max(0, decision_index) / self.decay_decisions)
        return self.start + (self.end - self.start) * fraction


class DqnPolicy:
    """Política ε-gulosa sobre um ``DqnAgent``; conta decisões entre episódios."""

    name = "dqn"

    def __init__(self, agent: DqnAgent, epsilon: EpsilonSchedule | None = None) -> None:
        self.agent = agent
        self.epsilon = epsilon
        self.decisions = 0

    def current_epsilon(self) -> float:
        return 0.0 if self.epsilon is None else self.epsilon.value(self.decisions)

    def __call__(self, state: np.ndarray, lane_features: Mapping[LaneKey, Any], phase: Any) -> int:
        epsilon = self.current_epsilon()
        self.decisions += 1
        return self.agent.select_action(state, epsilon=epsilon, explore=epsilon > 0)


@dataclass(frozen=True, slots=True)
class RewardModel:
    """Recompensa de nível sobre as lanes de entrada inteiras (verdade de terreno)."""

    lanes: tuple[str, ...]
    capacity: float
    weights: RewardWeights = RewardWeights()

    def __call__(self, lane_metrics: Mapping[str, float | int]) -> float:
        snapshot = TrafficSnapshot(int(lane_metrics["halting_vehicles"]), float(lane_metrics["waiting_time_s"]), int(lane_metrics["pending_vehicles"]))
        return level_reward(snapshot, self.capacity, self.weights)


@dataclass(slots=True)
class EpisodeOutcome:
    total_reward: float = 0.0
    controlled_steps: int = 0
    decisions: int = 0
    switches: int = 0
    transitions: int = 0
    missing_observations: int = 0
    losses: list[float] = field(default_factory=list)
    phase_seconds: Counter = field(default_factory=Counter)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def mean_reward(self) -> float:
        return 0.0 if self.controlled_steps == 0 else self.total_reward / self.controlled_steps

    @property
    def switch_rate(self) -> float | None:
        return None if self.decisions == 0 else self.switches / self.decisions

    def summary(self) -> dict[str, Any]:
        return {
            "total_reward": self.total_reward,
            "mean_reward": self.mean_reward,
            "controlled_steps": self.controlled_steps,
            "decisions": self.decisions,
            "switches": self.switches,
            "switch_rate": self.switch_rate,
            "transitions": self.transitions,
            "missing_observations": self.missing_observations,
            "mean_loss": None if not self.losses else float(np.mean(self.losses)),
            "phase_seconds": dict(self.phase_seconds),
            "metrics": self.metrics,
        }


def run_episode(
    *,
    client: Any,
    controller: DqnTrafficController,
    observe: Observer,
    encoder: Any,
    policy: Policy,
    reward: RewardModel,
    settings: EpisodeSettings,
    learner: DqnAgent | None = None,
    metrics: ExperimentMetricsCollector | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> EpisodeOutcome:
    """Executa um episódio já iniciado em ``client``; ``learner`` ativa o aprendizado."""
    scheduler = DecisionScheduler(controller.min_green_seconds, controller.max_green_seconds, settings.decision_interval_s)
    accumulator = SmdpAccumulator(settings.gamma)
    metrics = metrics or ExperimentMetricsCollector(warmup_until_s=settings.warmup_s)
    outcome = EpisodeOutcome()
    last_state: np.ndarray | None = None
    total_steps = int(round(settings.warmup_s + settings.control_s))
    for _ in range(total_steps):
        sim_time = client.step()
        lane_metrics = client.get_incoming_lane_metrics(reward.lanes)
        metrics.observe(sim_time, client.get_simulation_events(), client.get_active_vehicle_metrics(),
                        pending_vehicles=int(lane_metrics["pending_vehicles"]), teleports=client.get_teleport_count())
        step_reward = reward(lane_metrics)
        lane_features = observe(sim_time)
        phase = controller.phase_manager.get_current_phase()
        elapsed = controller.phase_manager.elapsed(sim_time)
        requested: int | None = None
        if sim_time <= settings.warmup_s:
            decision = controller.update(sim_time, controller.SWITCH if elapsed >= settings.warmup_switch_after_s else controller.KEEP)
        else:
            outcome.controlled_steps += 1
            outcome.total_reward += step_reward
            outcome.phase_seconds[phase.name] += 1
            accumulator.add(step_reward)
            if lane_features is None:
                outcome.missing_observations += 1
                decision = controller.update_without_vision(sim_time)
            else:
                last_state = encoder.encode(lane_features, phase.phase_index, elapsed)
                if scheduler.is_decision_point(phase, sim_time):
                    _learn(learner, accumulator.close(last_state), outcome)
                    requested = int(policy(last_state, lane_features, phase))
                    accumulator.open(last_state, requested)
                    scheduler.mark_decision(sim_time)
                    outcome.decisions += 1
                    outcome.switches += requested == controller.SWITCH
                    decision = controller.update(sim_time, requested)
                else:
                    decision = controller.update(sim_time, controller.KEEP)
        controller.apply(client, decision)
        if on_step is not None:
            on_step({"sim_time": sim_time, "reward": step_reward, "phase": phase.name, "decision": decision,
                     "requested_action": requested, "lane_features": lane_features, "lane_metrics": lane_metrics})
    # Episódio truncado pelo tempo: a última transição faz bootstrap (done=False).
    if last_state is not None:
        _learn(learner, accumulator.close(last_state), outcome)
    outcome.metrics = metrics.summary()
    return outcome


def _learn(learner: DqnAgent | None, transition: Any, outcome: EpisodeOutcome) -> None:
    if learner is None or transition is None:
        return
    learner.remember(transition.state, transition.action, transition.reward, transition.next_state, False, discount=transition.discount)
    outcome.transitions += 1
    loss = learner.train_step()
    if loss is not None:
        outcome.losses.append(loss)


def incoming_lane_capacity(lane_lengths_m: Sequence[float], footprint_m: float = 7.5) -> float:
    """Capacidade das lanes de entrada inteiras (veículos parados que cabem)."""
    return float(sum(max(1.0, length / footprint_m) for length in lane_lengths_m))
