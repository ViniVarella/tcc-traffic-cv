"""Features por faixa a partir das posições reais do SUMO (oráculo do pré-treino).

Usa o mesmo intervalo físico das ROIs das câmeras (``lane_geometry`` do perfil)
e o mesmo ``ApproachKinematicsTracker`` da visão. Não consulta os detectores
E2, que cobrem outro trecho da via. Nunca deve decidir o controle implantado
sem ser rotulado como percepção oráculo.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import random
from typing import Any, Protocol

from vision.lane_features import ApproachKinematicsTracker, KinematicsParameters, LaneFeatures, LaneGeometry, LaneObservation


LaneKey = tuple[str, str]


class LanePositionClient(Protocol):
    def get_lane_vehicle_positions(self, lane_id: str) -> list[tuple[str, float]]: ...


@dataclass(frozen=True, slots=True)
class ObservationNoise:
    """Degrada o oráculo para aproximar a visão (calibrado pela medição do domain gap)."""

    position_std_m: float = 0.0
    drop_probability: float = 0.0
    untracked_probability: float = 0.0

    def __post_init__(self) -> None:
        if self.position_std_m < 0 or not 0 <= self.drop_probability < 1 or not 0 <= self.untracked_probability <= 1:
            raise ValueError("Parâmetros de ruído de observação inválidos.")

    @property
    def enabled(self) -> bool:
        return bool(self.position_std_m or self.drop_probability or self.untracked_probability)


class TraciLaneFeatureSource:
    """Converte posições de veículos nas lanes SUMO em ``LaneFeatures`` por ROI."""

    def __init__(
        self,
        geometries: Mapping[LaneKey, LaneGeometry],
        parameters: KinematicsParameters | None = None,
        noise: ObservationNoise | None = None,
        seed: int = 0,
    ) -> None:
        if not geometries:
            raise ValueError("Informe ao menos uma geometria de faixa.")
        self.geometries = dict(geometries)
        # Sem oclusão no simulador: um veículo não observado de fato saiu da ROI.
        self.parameters = replace(parameters or KinematicsParameters(), ghost_ttl_s=0.0)
        self.noise = noise or ObservationNoise()
        self._seed = seed
        self.reset()

    def reset(self, seed: int | None = None) -> None:
        cameras = sorted({camera_id for camera_id, _ in self.geometries})
        self._trackers = {
            camera_id: ApproachKinematicsTracker(
                {lane_id: geometry.length_m for (camera, lane_id), geometry in self.geometries.items() if camera == camera_id},
                self.parameters,
            )
            for camera_id in cameras
        }
        self._random = random.Random(self._seed if seed is None else seed)

    def observe(self, client: LanePositionClient, sim_time: float) -> dict[LaneKey, LaneFeatures]:
        observations: dict[str, list[LaneObservation]] = {camera_id: [] for camera_id in self._trackers}
        for (camera_id, lane_id), geometry in self.geometries.items():
            for vehicle_id, lane_position in client.get_lane_vehicle_positions(geometry.sumo_lane):
                observation = self._observation(lane_id, geometry, vehicle_id, lane_position)
                if observation is not None:
                    observations[camera_id].append(observation)
        features: dict[LaneKey, LaneFeatures] = {}
        for camera_id, tracker in self._trackers.items():
            for lane_id, lane_features in tracker.update(observations[camera_id], sim_time).items():
                features[(camera_id, lane_id)] = lane_features
        return features

    def _observation(self, lane_id: str, geometry: LaneGeometry, vehicle_id: str, lane_position: float) -> LaneObservation | None:
        distance = geometry.roi_end_m - lane_position
        if self.noise.enabled:
            if self._random.random() < self.noise.drop_probability:
                return None
            distance += self._random.gauss(0.0, self.noise.position_std_m)
        if not 0.0 <= distance <= geometry.length_m:
            return None
        untracked = self.noise.untracked_probability and self._random.random() < self.noise.untracked_probability
        return LaneObservation(lane_id, distance, None if untracked else vehicle_id)


def noise_from_config(config: Mapping[str, Any]) -> ObservationNoise:
    return ObservationNoise(**dict(config.get("lane_state", {}).get("oracle_noise", {})))
