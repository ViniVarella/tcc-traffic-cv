"""Gerenciamento das fases logicas e transicoes do semaforo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PhaseState:
    """Representa uma fase logica do controlador e sua duracao configurada."""

    name: str
    duration: float


class PhaseManager:
    """Define a sequencia segura entre verdes, amarelos e all-red."""

    def __init__(self) -> None:
        self.current_phase = PhaseState(name="NS_GREEN", duration=0.0)

    def get_current_phase(self) -> PhaseState:
        """Retorna a fase logica atualmente ativa no controlador."""
        return self.current_phase
