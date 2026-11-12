"""Estado por fase da seleção livre de fase, com tamanho independente do cruzamento.

Cada fase verde candidata vira uma linha de ``ROW_FEATURE_NAMES``: as
``LaneFeatures`` somadas no grupo de faixas da fase (normalizadas pela
capacidade do grupo), as contagens absolutas (parados e veículos ÷
``VEHICLE_REFERENCE``, faixas ÷ ``LANE_REFERENCE``: só a densidade confundia
uma conversão de 1 faixa com uma via de 3), as mesmas features da fase atual
como contexto, se a fase é a atual, o tempo de verde e há quanto tempo a fase
está no vermelho. No estado ``phase_select_3`` entram também o tempo perdido
para chegar à fase (amarelo + all-red e, se a fase atual dispara a fase
exclusiva de pedestres, o tempo dela) e o tempo perdido ao sair dela. As
linhas são completadas até ``max_phases`` e seguidas da máscara das fases que
a política pode escolher, num vetor plano (o replay e as transições SMDP
continuam guardando um ``np.ndarray`` por estado).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

GROUP_FEATURE_NAMES = ("count", "stopped", "occupancy", "speed", "waiting",
                       "stopped_vehicles", "vehicles", "lane_count")
ROW_FEATURE_NAMES_V2 = (
    *GROUP_FEATURE_NAMES,
    *(f"current_{name}" for name in GROUP_FEATURE_NAMES),
    "is_current",
    "green_elapsed",
    "red_time",
)
# phase_select_3: as features da v2 + custo das transições (pedestres incluídos).
ROW_FEATURE_NAMES = (*ROW_FEATURE_NAMES_V2, "switch_in", "switch_out")
STATE_VERSION = "phase_select_3"
ROW_FEATURES_BY_VERSION = {"phase_select_2": ROW_FEATURE_NAMES_V2, STATE_VERSION: ROW_FEATURE_NAMES}
# Tempo perdido de referência: transição (4 s) + fase de pedestres do SP (18 s), com folga.
TRANSITION_REFERENCE_S = 30.0
# Escalas das contagens absolutas: duas ROIs de 60 m cheias e 4 faixas.
VEHICLE_REFERENCE = 16.0
LANE_REFERENCE = 4.0
# Teto das features (densidades ficam em [0, 1]; contagens absolutas podem passar de 1).
FEATURE_CEILING = 3.0
LANE_COUNT_INDEX = ROW_FEATURE_NAMES.index("lane_count")  # o mesmo nas duas versões


@dataclass(frozen=True, slots=True)
class PhaseObservation:
    """O que as políticas de seleção de fase recebem em um ponto de decisão."""

    state: np.ndarray
    current: int
    mask: tuple[bool, ...]
    stopped: tuple[int, ...]
    lane_counts: tuple[int, ...]
    green_elapsed_s: float


def group_features(lane_features: Mapping[Any, Any], keys: Sequence[Any], capacities: Mapping[Any, float],
                   max_speed_mps: float, waiting_reference_s: float) -> list[float]:
    """Features de um grupo de faixas: as 5 densidades (pela capacidade somada) e as contagens absolutas."""
    capacity = sum(capacities[key] for key in keys) or 1.0
    features = [lane_features.get(key) for key in keys]
    present = [item for item in features if item is not None]
    speeds = [item.mean_speed_mps for item in present if item.mean_speed_mps is not None]
    occupancy = sum(item.occupancy for item in present) / len(keys) if keys else 0.0
    return [
        sum(item.vehicle_count for item in present) / capacity,
        sum(item.stopped_count for item in present) / capacity,
        occupancy,
        1.0 if not speeds else float(np.mean(speeds)) / max_speed_mps,
        sum(item.waiting_time_s for item in present) / (capacity * waiting_reference_s),
        sum(item.stopped_count for item in present) / VEHICLE_REFERENCE,
        sum(item.vehicle_count for item in present) / VEHICLE_REFERENCE,
        len(keys) / LANE_REFERENCE,
    ]


class PhaseStateEncoder:
    """Monta o vetor ``max_phases × len(ROW_FEATURE_NAMES) + max_phases`` (linhas + máscara)."""

    def __init__(self, max_phases: int = 8, max_green_s: float = 40.0, max_red_s: float = 132.0,
                 max_speed_mps: float = 13.89, waiting_reference_s: float = 60.0,
                 state_version: str = STATE_VERSION) -> None:
        if max_phases < 2 or min(max_green_s, max_red_s, max_speed_mps, waiting_reference_s) <= 0:
            raise ValueError("Parâmetros do estado por fase inválidos.")
        if state_version not in ROW_FEATURES_BY_VERSION:
            raise ValueError(f"Versão de estado desconhecida: {state_version!r}.")
        self.state_version = state_version
        self.max_phases = int(max_phases)
        self.max_green_s = float(max_green_s)
        self.max_red_s = float(max_red_s)
        self.max_speed_mps = float(max_speed_mps)
        self.waiting_reference_s = float(waiting_reference_s)

    @property
    def row_size(self) -> int:
        return len(ROW_FEATURES_BY_VERSION[self.state_version])

    @property
    def state_size(self) -> int:
        return self.max_phases * (self.row_size + 1)

    def encode(
        self,
        lane_features: Mapping[Any, Any],
        groups: Sequence[Sequence[Any]],
        capacities: Mapping[Any, float],
        current: int,
        green_elapsed_s: float,
        red_times_s: Sequence[float],
        mask: Sequence[bool],
        switch_in_s: Sequence[float] | None = None,
        switch_out_s: Sequence[float] | None = None,
    ) -> PhaseObservation:
        """``switch_in_s``/``switch_out_s``: tempo perdido para entrar/sair de cada fase (obrigatórios no v3)."""
        count = len(groups)
        if not 2 <= count <= self.max_phases or len(red_times_s) != count or len(mask) != count:
            raise ValueError(f"O cruzamento deve ter de 2 a {self.max_phases} fases, com tempos e máscara por fase.")
        if not 0 <= current < count or not any(mask):
            raise ValueError("Fase atual inválida ou máscara vazia.")
        with_switch = self.row_size > len(ROW_FEATURE_NAMES_V2)
        if with_switch and (switch_in_s is None or switch_out_s is None
                            or len(switch_in_s) != count or len(switch_out_s) != count):
            raise ValueError("O estado phase_select_3 exige o tempo perdido de entrada e de saída de cada fase.")
        per_group = [group_features(lane_features, keys, capacities, self.max_speed_mps, self.waiting_reference_s)
                     for keys in groups]
        rows = np.zeros((self.max_phases, self.row_size), dtype=np.float32)
        elapsed = float(green_elapsed_s) / self.max_green_s
        for phase in range(count):
            # Acima de max_red_s a justiça já força a fase: o tempo no vermelho satura em 1.
            red = 0.0 if phase == current else min(1.0, float(red_times_s[phase]) / self.max_red_s)
            row = [*per_group[phase], *per_group[current], float(phase == current), elapsed, red]
            if with_switch:
                row += [float(switch_in_s[phase]) / TRANSITION_REFERENCE_S, float(switch_out_s[phase]) / TRANSITION_REFERENCE_S]
            rows[phase] = row
        padded_mask = np.zeros(self.max_phases, dtype=np.float32)
        padded_mask[:count] = np.asarray(mask, dtype=np.float32)
        state = np.concatenate([np.clip(rows, 0.0, FEATURE_CEILING).reshape(-1), padded_mask])
        stopped = tuple(sum(lane_features[key].stopped_count for key in keys if key in lane_features) for keys in groups)
        return PhaseObservation(state, int(current), tuple(bool(item) for item in mask), stopped,
                                tuple(len(keys) for keys in groups), float(green_elapsed_s))


def split_state(states: np.ndarray, max_phases: int, row_size: int) -> tuple[np.ndarray, np.ndarray]:
    """Separa um lote de vetores planos em linhas ``(B, P, d)`` e máscara ``(B, P)``."""
    states = np.asarray(states, dtype=np.float32).reshape(-1, max_phases * (row_size + 1))
    rows = states[:, : max_phases * row_size].reshape(-1, max_phases, row_size)
    return rows, states[:, max_phases * row_size:] > 0.5
