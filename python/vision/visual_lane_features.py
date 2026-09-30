"""Features por faixa estimadas só por visão: tracks → homografia da ROI → cinemática."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .camera_calibration import CameraCalibration
from .lane_features import ApproachKinematicsTracker, KinematicsParameters, LaneFeatures, LaneGeometry, LaneObservation
from .lane_geometry import LaneHomography, bbox_ground_point


LaneKey = tuple[str, str]


class VisualLaneFeatureSource:
    """Converte objetos contados (tracks + detecções sem track) em ``LaneFeatures``.

    Cada objeto é projetado pelo centro da base da bbox em todas as faixas da
    câmera; ele pertence à faixa cujo retângulo métrico o contém, desempatando
    pela proximidade ao eixo da faixa.
    """

    def __init__(
        self,
        calibrations: Mapping[str, CameraCalibration],
        geometries: Mapping[LaneKey, LaneGeometry],
        parameters: KinematicsParameters | None = None,
        ground_offset_m: float = 0.0,
    ) -> None:
        self.parameters = parameters or KinematicsParameters()
        self.ground_offset_m = float(ground_offset_m)
        self.geometries = {key: geometry for key, geometry in geometries.items() if key[0] in calibrations}
        self._homographies: dict[str, dict[str, LaneHomography]] = {}
        for (camera_id, lane_id), geometry in self.geometries.items():
            quad = calibrations[camera_id].lane_rois.get(lane_id)
            if quad is None:
                raise ValueError(f"Calibração de {camera_id} não tem a ROI {lane_id}.")
            self._homographies.setdefault(camera_id, {})[lane_id] = LaneHomography.from_quad(quad, geometry.length_m, geometry.width_m)
        if not self._homographies:
            raise ValueError("Nenhuma faixa com calibração e geometria em comum.")
        self.reset()

    def reset(self) -> None:
        self._trackers = {
            camera_id: ApproachKinematicsTracker({lane_id: homography.length_m for lane_id, homography in lanes.items()}, self.parameters)
            for camera_id, lanes in self._homographies.items()
        }
        self.last_observations: dict[str, list[LaneObservation]] = {}

    def observations(self, camera_id: str, objects: Sequence[Mapping[str, Any]], frame_width: int, frame_height: int) -> list[LaneObservation]:
        """Projeta os objetos de uma câmera nas faixas calibradas."""
        if frame_width <= 1 or frame_height <= 1:
            raise ValueError("Dimensões de frame inválidas.")
        result: list[LaneObservation] = []
        for obj in objects:
            x, y = bbox_ground_point(obj["bbox"])
            # Mesma normalização de CameraCalibration.pixel_rois.
            u, v = x / (frame_width - 1), y / (frame_height - 1)
            best: tuple[float, str, float] | None = None
            for lane_id, homography in self._homographies[camera_id].items():
                lateral, distance = homography.project(u, v)
                if homography.contains(lateral, distance):
                    centering = abs(lateral - homography.width_m / 2.0) / homography.width_m
                    if best is None or centering < best[0]:
                        best = (centering, lane_id, distance)
            if best is None:
                continue
            _, lane_id, distance = best
            length = self._homographies[camera_id][lane_id].length_m
            distance = min(length, max(0.0, distance + self.ground_offset_m))
            track_id = obj.get("track_id")
            result.append(LaneObservation(lane_id, distance, None if track_id is None else str(track_id)))
        return result

    def observe(self, camera_results: Mapping[str, Any], sim_time: float) -> dict[LaneKey, LaneFeatures]:
        """Recebe ``CameraStepResult`` por câmera (``objects`` e ``frame``) de um step."""
        features: dict[LaneKey, LaneFeatures] = {}
        self.last_observations = {}
        for camera_id, tracker in self._trackers.items():
            result = camera_results.get(camera_id)
            observations = [] if result is None else self.observations(camera_id, result.objects, result.frame.shape[1], result.frame.shape[0])
            self.last_observations[camera_id] = observations
            for lane_id, lane_features in tracker.update(observations, sim_time).items():
                features[(camera_id, lane_id)] = lane_features
        return features
