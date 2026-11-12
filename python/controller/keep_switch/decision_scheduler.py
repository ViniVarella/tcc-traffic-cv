"""Pontos de decisão da linha manter/trocar (DQN estado v2).

A política só é consultada quando a escolha tem efeito: em verde, depois do
verde mínimo, antes do verde máximo (que força a troca) e a cada
``interval_s``. Entre decisões o controlador recebe ``KEEP`` e continua
aplicando amarelo, all-red e verde máximo. As transições entre decisões ficam
em ``controller.smdp``.
"""

from __future__ import annotations

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
