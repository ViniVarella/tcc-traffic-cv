"""Seleção do melhor checkpoint por validação, com salvaguardas contra o colapso do v1.

O DQN v1 guardou como "melhor" o checkpoint do episódio 4 (240 passos de
gradiente, ε≈0,98) porque a validação empatava e o primeiro valor vencia.
Aqui só se compara depois de treino mínimo, empates favorecem o checkpoint
mais treinado e políticas degeneradas (sempre/nunca trocar) são sinalizadas.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SelectionCriteria:
    min_gradient_steps: int = 5_000
    max_epsilon: float = 0.2
    tie_tolerance: float = 0.01
    degenerate_low: float = 0.05
    degenerate_high: float = 0.95


@dataclass(frozen=True, slots=True)
class ValidationRecord:
    episode: int
    score: float | None
    gradient_steps: int
    epsilon: float
    switch_rate: float | None


class CheckpointSelector:
    """Decide se um checkpoint validado substitui o melhor atual."""

    def __init__(self, criteria: SelectionCriteria = SelectionCriteria()) -> None:
        self.criteria = criteria
        self.best: ValidationRecord | None = None

    def eligible(self, record: ValidationRecord) -> bool:
        return (
            record.score is not None
            and record.gradient_steps >= self.criteria.min_gradient_steps
            and record.epsilon <= self.criteria.max_epsilon
        )

    def consider(self, record: ValidationRecord) -> bool:
        """Retorna ``True`` quando ``record`` passa a ser o melhor checkpoint."""
        if not self.eligible(record):
            return False
        if self.best is None:
            self.best = record
            return True
        tolerance = self.criteria.tie_tolerance * max(abs(self.best.score), 1e-9)
        # Empate dentro da tolerância: fica o mais treinado.
        if record.score >= self.best.score - tolerance:
            self.best = record
            return True
        return False

    def degeneracy(self, switch_rate: float | None) -> str | None:
        """Rótulo de alerta para políticas que sempre (ou nunca) pedem troca."""
        if switch_rate is None:
            return None
        if switch_rate >= self.criteria.degenerate_high:
            return "always_switch"
        if switch_rate <= self.criteria.degenerate_low:
            return "never_switch"
        return None
