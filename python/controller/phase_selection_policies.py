"""Políticas da seleção livre de fase: todas recebem uma ``PhaseObservation``.

- ``FixedTimePhasePolicy``: tempo fixo na ordem do programa, cada verde com a
  duração do programa limitada aos verdes mínimo e máximo;
- ``MaxPressurePhasePolicy``: max-pressure acíclico sobre veículos parados;
- ``PhaseDqnPolicy``: ε-gulosa sobre o ``PhaseSelectionAgent``.
"""

from __future__ import annotations

from collections.abc import Sequence

from .phase_selection_agent import PhaseSelectionAgent
from .phase_selection_state import PhaseObservation


def cyclic_order(current: int, count: int) -> list[int]:
    """Fases a partir da seguinte à atual, na ordem do programa."""
    return [(current + offset) % count for offset in range(1, count + 1)]


def next_valid(observation: PhaseObservation) -> int:
    count = len(observation.mask)
    return next(phase for phase in cyclic_order(observation.current, count) if observation.mask[phase])


class FixedTimePhasePolicy:
    name = "fixed_time"

    def __init__(self, durations_s: Sequence[float], min_green_s: float = 10.0, max_green_s: float = 40.0) -> None:
        self.durations_s = tuple(min(max_green_s, max(min_green_s, float(value))) for value in durations_s)

    def __call__(self, observation: PhaseObservation) -> int:
        current = observation.current
        if observation.mask[current] and observation.green_elapsed_s < self.durations_s[current]:
            return current
        return next_valid(observation)


class MaxPressurePhasePolicy:
    """Dá o verde à fase com mais veículos parados, se ela superar a atual mais o custo da troca.

    Mesmo critério de ``MaxPressurePolicy`` (cenário SP), generalizado para N
    fases: o custo é o que a fase atual descarregaria durante amarelo + all-red
    (~1 veículo a cada 2 s por faixa). Empates seguem a ordem do programa.
    """

    name = "max_pressure"

    def __init__(self, lost_time_s: float = 4.0) -> None:
        self.lost_time_s = float(lost_time_s)

    def __call__(self, observation: PhaseObservation) -> int:
        current, stopped = observation.current, observation.stopped
        others = [phase for phase in cyclic_order(current, len(stopped)) if phase != current and observation.mask[phase]]
        if not observation.mask[current]:
            return max(others, key=lambda phase: stopped[phase]) if others else next_valid(observation)
        if not others:
            return current
        best = max(others, key=lambda phase: stopped[phase])
        if stopped[current] < 1:
            return best if stopped[best] > 0 else current
        margin = observation.lane_counts[current] * self.lost_time_s / 2.0
        return best if stopped[best] > stopped[current] + margin else current


class PhaseDqnPolicy:
    name = "dqn"

    def __init__(self, agent: PhaseSelectionAgent, epsilon=None) -> None:
        self.agent = agent
        self.epsilon = epsilon
        self.decisions = 0

    def current_epsilon(self) -> float:
        return 0.0 if self.epsilon is None else self.epsilon.value(self.decisions)

    def __call__(self, observation: PhaseObservation) -> int:
        epsilon = self.current_epsilon()
        self.decisions += 1
        return self.agent.select_action(observation.state, epsilon=epsilon, explore=epsilon > 0)
