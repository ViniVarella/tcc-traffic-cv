"""Pontos de decisão do DQN v2 e transições SMDP entre eles.

A política só é consultada quando a escolha tem efeito: em verde, depois do
verde mínimo, antes do verde máximo (que força a troca) e a cada
``interval_s``. Entre decisões o controlador recebe ``KEEP`` e continua
aplicando amarelo, all-red e verde máximo. A recompensa de cada step entre
duas decisões é acumulada com desconto, e a transição guarda ``gamma ** k``
para o alvo do DQN.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .phase_manager import PhaseManager, PhaseState


GREEN_PHASES = frozenset({PhaseManager.EAST_WEST_GREEN, PhaseManager.SOUTH_GREEN})


class DecisionScheduler:
    """Indica em quais steps a política deve escolher manter ou trocar."""

    def __init__(self, min_green_seconds: float, max_green_seconds: float, interval_s: float) -> None:
        if not 0 <= min_green_seconds < max_green_seconds or interval_s <= 0:
            raise ValueError("Requer 0 <= verde mínimo < verde máximo e intervalo positivo.")
        self.min_green_seconds = float(min_green_seconds)
        self.max_green_seconds = float(max_green_seconds)
        self.interval_s = float(interval_s)
        self.reset()

    def reset(self) -> None:
        self._phase_started_at: float | None = None
        self._last_decision_at: float | None = None

    def is_decision_point(self, phase: PhaseState, sim_time: float) -> bool:
        if phase.name not in GREEN_PHASES:
            return False
        if phase.started_at != self._phase_started_at:
            self._phase_started_at, self._last_decision_at = phase.started_at, None
        elapsed = sim_time - phase.started_at
        if not self.min_green_seconds <= elapsed < self.max_green_seconds:
            return False
        # Tolerância para tempos de ponto flutuante do SUMO.
        return self._last_decision_at is None or sim_time - self._last_decision_at >= self.interval_s - 1e-6

    def mark_decision(self, sim_time: float) -> None:
        self._last_decision_at = float(sim_time)


@dataclass(frozen=True, slots=True)
class SmdpTransition:
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    discount: float
    steps: int


class SmdpAccumulator:
    """Acumula ``sum(gamma**i * r_i)`` desde a última decisão até a próxima."""

    def __init__(self, gamma: float) -> None:
        if not 0.0 < gamma <= 1.0:
            raise ValueError("gamma deve estar em (0, 1].")
        self.gamma = float(gamma)
        self.reset()

    def reset(self) -> None:
        self._state: np.ndarray | None = None
        self._action = 0
        self._reward = 0.0
        self._steps = 0

    @property
    def is_open(self) -> bool:
        return self._state is not None

    def open(self, state: np.ndarray, action: int) -> None:
        self._state, self._action, self._reward, self._steps = np.asarray(state, dtype=np.float32).copy(), int(action), 0.0, 0

    def add(self, reward: float) -> None:
        """Soma a recompensa de um step já simulado após a decisão aberta."""
        if self._state is None:
            return
        self._reward += (self.gamma ** self._steps) * float(reward)
        self._steps += 1

    def close(self, next_state: np.ndarray) -> SmdpTransition | None:
        """Fecha a transição aberta; ``None`` se não houve decisão ou step algum."""
        if self._state is None or self._steps == 0:
            self.reset()
            return None
        transition = SmdpTransition(self._state, self._action, self._reward, np.asarray(next_state, dtype=np.float32).copy(),
                                    self.gamma ** self._steps, self._steps)
        self.reset()
        return transition
