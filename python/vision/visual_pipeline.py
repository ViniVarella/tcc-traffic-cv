"""Pipeline visual por step compartilhado entre treino e execução do controlador."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from .camera_calibration import CameraCalibration, load_camera_calibration
from .queue_estimator import QueueEstimator
from .roi_counter import ROICounter, filter_detections_to_roi, select_counting_objects


class Detector(Protocol):
    def detect(self, frame: Any) -> list[dict[str, Any]]: ...


class Tracker(Protocol):
    def update(self, detections: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class CameraStepResult:
    """Saídas intermediárias de uma câmera em um step, úteis para debug e features."""

    camera_id: str
    frame: Any
    rois: dict[str, list[list[int]]]
    detections: list[dict[str, Any]]
    tracks: list[dict[str, Any]]
    objects: list[dict[str, Any]]
    count_source: str
    raw_counts: dict[str, int]
    queue_counts: dict[str, int]


def decode_jpeg(jpeg: bytes, camera_id: str, step_id: int) -> Any:
    """Decodifica o JPEG de uma câmera Unity em BGR."""
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"JPEG inválido: camera={camera_id} step={step_id}.")
    return frame


def parse_class_ids(raw: str) -> list[int]:
    """Converte ``--classes`` (ex.: ``"0"`` ou ``"2,3,5,7"``) em IDs de classe."""
    values = [value.strip() for value in raw.split(",") if value.strip()]
    try:
        class_ids = [int(value) for value in values]
    except ValueError as error:
        raise ValueError(f"IDs de classe inválidos: {raw!r}") from error
    if not class_ids or any(value < 0 for value in class_ids):
        raise ValueError("--classes precisa conter IDs não negativos.")
    return class_ids


def load_calibrations(python_dir: str | Path, camera_ids: Iterable[str]) -> dict[str, CameraCalibration]:
    """Carrega as calibrações exportadas pela Unity para as câmeras informadas."""
    calibration_dir = Path(python_dir).parent / "unity" / "TrafficVisionUnity" / "Assets" / "Calibration"
    return {
        camera_id: load_camera_calibration(calibration_dir / f"{camera_id}-calibration.json", expected_camera_id=camera_id)
        for camera_id in camera_ids
    }


class VisualPipeline:
    """Detecta, rastreia e conta veículos por faixa para todas as câmeras de um step.

    Trackers e suavizadores guardam estado entre steps; chame ``reset`` no
    início de cada episódio.
    """

    def __init__(
        self,
        calibrations: dict[str, CameraCalibration],
        detector: Detector,
        tracker_factory: Callable[[], Tracker],
        estimator_factory: Callable[[], QueueEstimator] = QueueEstimator,
    ) -> None:
        if not calibrations:
            raise ValueError("VisualPipeline requer ao menos uma calibração de câmera.")
        self.calibrations = calibrations
        self.detector = detector
        self._tracker_factory = tracker_factory
        self._estimator_factory = estimator_factory
        self.reset()

    @property
    def camera_ids(self) -> tuple[str, ...]:
        return tuple(self.calibrations)

    def reset(self) -> None:
        """Recria trackers e suavizadores de todas as câmeras."""
        self._trackers = {camera_id: self._tracker_factory() for camera_id in self.calibrations}
        self._estimators = {camera_id: self._estimator_factory() for camera_id in self.calibrations}

    def process_bundle(self, bundle: Any) -> dict[str, CameraStepResult]:
        """Processa um ``FrameBundle`` completo e retorna os resultados por câmera."""
        return {
            camera_id: self.process_frame(camera_id, decode_jpeg(captured.jpeg, camera_id, bundle.step_id))
            for camera_id, captured in bundle.frames.items()
        }

    def process_frame(self, camera_id: str, frame: Any) -> CameraStepResult:
        """Executa detecção → ROI de aproximação → tracker → contagem por faixa."""
        calibration = self.calibrations[camera_id]
        height, width = frame.shape[:2]
        rois = calibration.pixel_rois(width, height)
        lane_rois = calibration.lane_pixel_rois(width, height)
        # Mesmo ponto de solo das features por faixa (ver filter_detections_to_roi).
        detections = filter_detections_to_roi(self.detector.detect(frame), rois["approach"], anchor="bottom_center")
        tracks = self._trackers[camera_id].update(detections)
        objects, count_source = select_counting_objects(detections, tracks)
        raw_counts = ROICounter(lane_rois).count(objects)
        queue_counts = self._estimators[camera_id].update(raw_counts)
        return CameraStepResult(camera_id, frame, rois, detections, tracks, objects, count_source, raw_counts, queue_counts)


def queue_counts_by_camera(results: dict[str, CameraStepResult]) -> dict[str, dict[str, int]]:
    """Extrai as contagens suavizadas no formato consumido pelos controladores."""
    return {camera_id: result.queue_counts for camera_id, result in results.items()}
