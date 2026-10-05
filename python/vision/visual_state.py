"""Contrato de estado visual usado pelo DQN do cenário SP."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np


SP_LANE_ORDER = (
    ("south", "lane_0"),
    ("south", "lane_1"),
    ("south", "lane_2"),
    ("south", "lane_3"),
    ("east", "lane_0"),
    ("east", "lane_1"),
    ("west", "lane_0"),
)


class VisualStateEncoder:
    """Estado v1: contagens visuais por faixa e estado local do TLS, normalizados."""

    def __init__(self, max_lane_count: float = 10.0, phase_count: int = 5, max_green_seconds: float = 40.0) -> None:
        if max_lane_count <= 0 or phase_count <= 0 or max_green_seconds <= 0:
            raise ValueError("Parâmetros de normalização do estado visual devem ser positivos.")
        self.max_lane_count = float(max_lane_count)
        self.phase_count = int(phase_count)
        self.max_green_seconds = float(max_green_seconds)

    @property
    def state_size(self) -> int:
        return len(SP_LANE_ORDER) + self.phase_count + 1

    def encode(
        self,
        visual_counts: Mapping[str, Mapping[str, int]],
        phase_index: int,
        phase_elapsed_seconds: float,
    ) -> np.ndarray:
        """Retorna [contagens por faixa, fase one-hot, tempo da fase] em float32."""
        if not 0 <= phase_index < self.phase_count:
            raise ValueError(f"Índice de fase inválido: {phase_index}.")
        values = [
            min(1.0, max(0.0, float(visual_counts.get(camera_id, {}).get(lane_id, 0)) / self.max_lane_count))
            for camera_id, lane_id in SP_LANE_ORDER
        ]
        phase = [0.0] * self.phase_count
        phase[phase_index] = 1.0
        elapsed = min(1.0, max(0.0, float(phase_elapsed_seconds) / self.max_green_seconds))
        return np.asarray([*values, *phase, elapsed], dtype=np.float32)


LANE_FEATURE_NAMES = ("count", "stopped", "occupancy", "speed", "waiting")


class LaneFeatureStateEncoder:
    """Estado v2: 5 features por faixa (``LaneFeatures``) + fase one-hot + tempo da fase.

    Contagens e parados são divididos pela capacidade da ROI (comprimento / 7,5 m);
    a espera, pela capacidade × ``waiting_reference_seconds``. Faixa sem velocidade
    conhecida vale 1,0 (fluxo livre), como o E2 vazio do SUMO.

    Estado v3 (rede com pedestres): o one-hot cobre também o verde e a liberação
    de pedestres, e uma última feature informa quantos verdes de veículos faltam
    até a fase de pedestres (dividido por ``pedestrian_cycle_greens``).
    """

    def __init__(
        self,
        capacities: Mapping[tuple[str, str], float],
        phase_count: int = 5,
        max_green_seconds: float = 40.0,
        max_speed_mps: float = 13.89,
        waiting_reference_seconds: float = 60.0,
        pedestrian_cycle_greens: int | None = None,
    ) -> None:
        missing = [key for key in SP_LANE_ORDER if key not in capacities]
        if missing:
            raise ValueError(f"Capacidade ausente para as faixas {missing}.")
        if min(phase_count, max_green_seconds, max_speed_mps, waiting_reference_seconds) <= 0:
            raise ValueError("Parâmetros de normalização do estado v2 devem ser positivos.")
        self.capacities = {key: float(capacities[key]) for key in SP_LANE_ORDER}
        self.phase_count = int(phase_count)
        self.max_green_seconds = float(max_green_seconds)
        self.max_speed_mps = float(max_speed_mps)
        self.waiting_reference_seconds = float(waiting_reference_seconds)
        if pedestrian_cycle_greens is not None and pedestrian_cycle_greens <= 0:
            raise ValueError("pedestrian_cycle_greens deve ser positivo.")
        self.pedestrian_cycle_greens = pedestrian_cycle_greens

    @property
    def state_size(self) -> int:
        extra = 0 if self.pedestrian_cycle_greens is None else 1
        return len(SP_LANE_ORDER) * len(LANE_FEATURE_NAMES) + self.phase_count + 1 + extra

    @property
    def feature_names(self) -> tuple[str, ...]:
        lanes = [f"{camera}/{lane}/{name}" for camera, lane in SP_LANE_ORDER for name in LANE_FEATURE_NAMES]
        extra = () if self.pedestrian_cycle_greens is None else ("greens_until_pedestrian",)
        return (*lanes, *(f"phase_{index}" for index in range(self.phase_count)), "phase_elapsed", *extra)

    def encode(
        self,
        lane_features: Mapping[tuple[str, str], Any],
        phase_index: int,
        phase_elapsed_seconds: float,
        greens_until_pedestrian: int | None = None,
    ) -> np.ndarray:
        if not 0 <= phase_index < self.phase_count:
            raise ValueError(f"Índice de fase inválido: {phase_index}.")
        if (self.pedestrian_cycle_greens is None) != (greens_until_pedestrian is None):
            raise ValueError("greens_until_pedestrian é obrigatório no estado v3 e não existe no v2.")
        values: list[float] = []
        for key in SP_LANE_ORDER:
            capacity = self.capacities[key]
            features = lane_features.get(key)
            if features is None:
                values.extend([0.0, 0.0, 0.0, 1.0, 0.0])
                continue
            speed = 1.0 if features.mean_speed_mps is None else features.mean_speed_mps / self.max_speed_mps
            values.extend([
                features.vehicle_count / capacity,
                features.stopped_count / capacity,
                features.occupancy,
                speed,
                features.waiting_time_s / (capacity * self.waiting_reference_seconds),
            ])
        phase = [0.0] * self.phase_count
        phase[phase_index] = 1.0
        elapsed = float(phase_elapsed_seconds) / self.max_green_seconds
        extra = [] if greens_until_pedestrian is None else [greens_until_pedestrian / self.pedestrian_cycle_greens]
        return np.clip(np.asarray([*values, *phase, elapsed, *extra], dtype=np.float32), 0.0, 1.0)


def build_state_encoder(config: Mapping[str, Any], version: int) -> VisualStateEncoder | LaneFeatureStateEncoder:
    """Cria o encoder da versão de estado pedida.

    1: contagens; 2: features por faixa; 3: features por faixa na rede com
    pedestres (todas as fases do perfil + verdes até a fase de pedestres).
    """
    phase_count = int(config["traffic_light"]["phase_count"])
    max_green = float(config["traffic_control"]["max_green_seconds"])
    dqn = config.get("dqn", {})
    if version == 1:
        return VisualStateEncoder(float(dqn.get("max_lane_count", 10.0)), phase_count, max_green)
    if version in (2, 3):
        from .lane_features import load_lane_geometries

        capacities = {key: geometry.capacity for key, geometry in load_lane_geometries(config).items()}
        cycle_greens = None
        if version == 3:
            phase_count = len(config["traffic_light"]["phases"])
            cycle_greens = 2 * int(config["pedestrians"]["every_cycles"]) - 1
        return LaneFeatureStateEncoder(
            capacities, phase_count, max_green,
            max_speed_mps=float(dqn.get("max_speed_mps", 13.89)),
            waiting_reference_seconds=float(dqn.get("waiting_reference_seconds", 60.0)),
            pedestrian_cycle_greens=cycle_greens,
        )
    raise ValueError(f"Versão de estado desconhecida: {version!r}.")
