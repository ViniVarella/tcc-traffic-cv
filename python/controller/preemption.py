"""Preempção semafórica para veículos de emergência.

A fonte de detecção (aviso V2I do veículo ou visão) entrega ``EmergencyRequest``
com a aproximação e o tempo estimado até a linha de retenção. A preempção
escolhe um veículo, trava nele até que ele cruze a linha (a fonte para de
reportá-lo) e informa o verde-alvo ao ``DqnTrafficController``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .phase_manager import PhaseManager


APPROACH_GREEN = {"south": PhaseManager.SOUTH_GREEN, "east": PhaseManager.EAST_WEST_GREEN, "west": PhaseManager.EAST_WEST_GREEN}


@dataclass(frozen=True, slots=True)
class EmergencyRequest:
    vehicle_id: str
    approach: str
    eta_s: float


@dataclass(frozen=True, slots=True)
class PreemptionSettings:
    # Só assume o semáforo quando o veículo está a até este tempo da linha:
    # tempo de amarelo + all-red + escoar a fila à frente dele, com folga.
    activation_eta_s: float = 20.0

    def __post_init__(self) -> None:
        if self.activation_eta_s <= 0:
            raise ValueError("activation_eta_s deve ser positivo.")

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "PreemptionSettings":
        return cls(**dict(config.get("emergency", {}).get("preemption", {})))


class EmergencyPreemption:
    """Atende um veículo por vez, na ordem de chegada estimada."""

    def __init__(self, settings: PreemptionSettings = PreemptionSettings()) -> None:
        self.settings = settings
        self.reset()

    def reset(self) -> None:
        self.active: EmergencyRequest | None = None
        self.served: list[str] = []

    def target_green(self, requests: Iterable[EmergencyRequest]) -> str | None:
        """Verde-alvo do passo atual, ou ``None`` sem preempção ativa."""
        requests = list(requests)
        if self.active is not None:
            current = next((request for request in requests if request.vehicle_id == self.active.vehicle_id), None)
            if current is not None:
                self.active = current
                return APPROACH_GREEN[current.approach]
            # O veículo atendido cruzou a linha de retenção: libera o semáforo.
            self.served.append(self.active.vehicle_id)
            self.active = None
        candidates = [request for request in requests if request.eta_s <= self.settings.activation_eta_s]
        if not candidates:
            return None
        self.active = min(candidates, key=lambda request: (request.eta_s, request.vehicle_id))
        return APPROACH_GREEN[self.active.approach]
