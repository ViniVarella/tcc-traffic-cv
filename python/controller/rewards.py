"""Recompensa de treino do DQN v2, calculada com verdade de terreno do TraCI.

A recompensa é um sinal de aprendizado, não entrada da política: usa as lanes de
entrada inteiras (não só as ROIs) e a fila de inserção do SUMO. É um *nível*
limitado a [-1, 0], não uma diferença, então veículos que saem da rede nunca
geram recompensa positiva espúria.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TrafficSnapshot:
    """Estado agregado das lanes de entrada em um step."""

    halting_vehicles: int
    waiting_time_s: float
    pending_vehicles: int


@dataclass(frozen=True, slots=True)
class RewardWeights:
    halting: float = 0.5
    pending: float = 0.3
    waiting: float = 0.2
    pending_reference: float = 60.0
    waiting_reference_s: float = 60.0

    def __post_init__(self) -> None:
        weights = (self.halting, self.pending, self.waiting)
        if min(weights) < 0 or abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("Os pesos da recompensa devem ser não negativos e somar 1.")
        if self.pending_reference <= 0 or self.waiting_reference_s <= 0:
            raise ValueError("As referências de normalização devem ser positivas.")

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "RewardWeights":
        return cls(**dict(config.get("dqn", {}).get("reward", {})))


def level_reward(snapshot: TrafficSnapshot, lane_capacity: float, weights: RewardWeights = RewardWeights()) -> float:
    """``-(w_h·parados/C + w_p·backlog/P + w_w·espera/(C·T))``, cada termo saturado em 1.

    ``lane_capacity`` é a soma das capacidades das lanes de entrada (comprimento / 7,5 m).
    """
    if lane_capacity <= 0:
        raise ValueError("A capacidade das lanes de entrada deve ser positiva.")
    halting = min(1.0, snapshot.halting_vehicles / lane_capacity)
    pending = min(1.0, snapshot.pending_vehicles / weights.pending_reference)
    waiting = min(1.0, snapshot.waiting_time_s / (lane_capacity * weights.waiting_reference_s))
    return -(weights.halting * halting + weights.pending * pending + weights.waiting * waiting)
