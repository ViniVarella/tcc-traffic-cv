"""Tipos de dados compartilhados no protocolo Python e Unity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SimulationState:
    """Representa o estado serializavel de um passo da simulacao."""

    step: int
    sim_time: float
    vehicles: list[dict[str, Any]] = field(default_factory=list)
    traffic_lights: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FramePacket:
    """Representa um frame renderizado pela Unity com metadados do passo."""

    step_id: int
    sim_time: float
    payload_size: int
    latency_ms: float | None = None
