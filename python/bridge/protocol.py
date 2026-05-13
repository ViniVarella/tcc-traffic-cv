"""Tipos de dados compartilhados no protocolo Python e Unity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SimulationState:
    """Representa o estado serializavel de um passo discreto da simulacao.

    O Python permanece como unico cliente TraCI e envia para a Unity apenas o
    estado necessario para renderizacao sincronizada daquele step.
    """

    step: int
    sim_time: float
    vehicles: list[dict[str, Any]] = field(default_factory=list)
    traffic_lights: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FramePacket:
    """Representa um frame de uma camera Unity associado a um step especifico.

    A arquitetura final usa quatro cameras virtuais. Por isso, o protocolo do
    frame precisa identificar explicitamente `step_id` e `camera_id`, alem de
    metadados suficientes para reconstruir o payload JPEG transportado por TCP.
    """

    step_id: int
    sim_time: float
    camera_id: str
    image_format: str
    payload_size: int
    latency_ms: float | None = None
