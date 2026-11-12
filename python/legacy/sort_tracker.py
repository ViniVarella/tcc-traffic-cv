"""Rastreamento temporal de deteccoes usando SORT."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from filterpy.kalman import KalmanFilter
from scipy.optimize import linear_sum_assignment


def _iou(bbox_a: np.ndarray, bbox_b: np.ndarray) -> float:
    """Calcula intersecao sobre uniao para duas caixas no formato xyxy."""
    xx1 = max(bbox_a[0], bbox_b[0])
    yy1 = max(bbox_a[1], bbox_b[1])
    xx2 = min(bbox_a[2], bbox_b[2])
    yy2 = min(bbox_a[3], bbox_b[3])

    width = max(0.0, xx2 - xx1)
    height = max(0.0, yy2 - yy1)
    intersection = width * height

    area_a = max(0.0, bbox_a[2] - bbox_a[0]) * max(0.0, bbox_a[3] - bbox_a[1])
    area_b = max(0.0, bbox_b[2] - bbox_b[0]) * max(0.0, bbox_b[3] - bbox_b[1])
    union = area_a + area_b - intersection

    if union <= 0.0:
        return 0.0
    return intersection / union


def _bbox_to_z(bbox: np.ndarray) -> np.ndarray:
    """Converte bbox xyxy em vetor de estado SORT."""
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    center_x = bbox[0] + width / 2.0
    center_y = bbox[1] + height / 2.0
    scale = width * height
    ratio = width / max(height, 1e-6)
    return np.array([center_x, center_y, scale, ratio], dtype=float).reshape((4, 1))


def _x_to_bbox(state: np.ndarray) -> np.ndarray:
    """Converte vetor de estado SORT em bbox xyxy."""
    center_x, center_y, scale, ratio = state[:4].reshape((4,))
    width = np.sqrt(max(scale * ratio, 0.0))
    height = scale / max(width, 1e-6)
    return np.array(
        [
            center_x - width / 2.0,
            center_y - height / 2.0,
            center_x + width / 2.0,
            center_y + height / 2.0,
        ],
        dtype=float,
    )


@dataclass(slots=True)
class _TrackPayload:
    """Mantem metadados associados ao ultimo update de um track."""

    confidence: float
    class_id: int


class _KalmanBoxTracker:
    """Representa um track SORT individual com filtro de Kalman para bbox."""

    count = 0

    def __init__(self, bbox: np.ndarray, confidence: float, class_id: int) -> None:
        self.kf = KalmanFilter(dim_x=7, dim_z=4)
        self.kf.F = np.array(
            [
                [1, 0, 0, 0, 1, 0, 0],
                [0, 1, 0, 0, 0, 1, 0],
                [0, 0, 1, 0, 0, 0, 1],
                [0, 0, 0, 1, 0, 0, 0],
                [0, 0, 0, 0, 1, 0, 0],
                [0, 0, 0, 0, 0, 1, 0],
                [0, 0, 0, 0, 0, 0, 1],
            ],
            dtype=float,
        )
        self.kf.H = np.array(
            [
                [1, 0, 0, 0, 0, 0, 0],
                [0, 1, 0, 0, 0, 0, 0],
                [0, 0, 1, 0, 0, 0, 0],
                [0, 0, 0, 1, 0, 0, 0],
            ],
            dtype=float,
        )
        self.kf.R[2:, 2:] *= 10.0
        self.kf.P[4:, 4:] *= 1000.0
        self.kf.P *= 10.0
        self.kf.Q[-1, -1] *= 0.01
        self.kf.Q[4:, 4:] *= 0.01

        self.kf.x[:4] = _bbox_to_z(bbox)
        self.time_since_update = 0
        self.id = _KalmanBoxTracker.count
        _KalmanBoxTracker.count += 1
        self.hits = 1
        self.hit_streak = 1
        self.age = 0
        self.payload = _TrackPayload(confidence=confidence, class_id=class_id)

    def update(self, bbox: np.ndarray, confidence: float, class_id: int) -> None:
        """Atualiza o track com uma nova medicao."""
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1
        self.payload = _TrackPayload(confidence=confidence, class_id=class_id)
        self.kf.update(_bbox_to_z(bbox))

    def predict(self) -> np.ndarray:
        """Avanca o estado previsto do filtro para o proximo frame."""
        if (self.kf.x[6] + self.kf.x[2]) <= 0:
            self.kf.x[6] = 0.0
        self.kf.predict()
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        return _x_to_bbox(self.kf.x)

    def get_state(self) -> np.ndarray:
        """Retorna a bbox corrente estimada pelo filtro."""
        return _x_to_bbox(self.kf.x)


def _associate_detections_to_trackers(
    detections: np.ndarray,
    predictions: np.ndarray,
    iou_threshold: float,
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Associa deteccoes a tracks previstos usando custo baseado em IoU."""
    if len(predictions) == 0:
        return [], list(range(len(detections))), []

    iou_matrix = np.zeros((len(detections), len(predictions)), dtype=float)
    for det_index, detection in enumerate(detections):
        for trk_index, tracker_bbox in enumerate(predictions):
            iou_matrix[det_index, trk_index] = _iou(detection[:4], tracker_bbox)

    det_indices, trk_indices = linear_sum_assignment(-iou_matrix)
    unmatched_detections = set(range(len(detections)))
    unmatched_trackers = set(range(len(predictions)))
    matches: list[tuple[int, int]] = []

    for det_index, trk_index in zip(det_indices.tolist(), trk_indices.tolist()):
        if iou_matrix[det_index, trk_index] < iou_threshold:
            continue
        matches.append((det_index, trk_index))
        unmatched_detections.discard(det_index)
        unmatched_trackers.discard(trk_index)

    return matches, sorted(unmatched_detections), sorted(unmatched_trackers)


class VehicleTracker:
    """Mantem IDs consistentes entre frames a partir das deteccoes de veiculos."""

    def __init__(self, max_age: int = 20, min_hits: int = 3, iou_threshold: float = 0.3) -> None:
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.trackers: list[_KalmanBoxTracker] = []
        self.frame_count = 0

    def update(self, detections: list[dict]) -> list[dict[str, float | int | list[float]]]:
        """Atualiza o estado do tracker e retorna tracks no formato padronizado."""
        self.frame_count += 1

        detection_array = np.asarray(
            [
                [
                    *detection["bbox"],
                    float(detection["confidence"]),
                    int(detection["class_id"]),
                ]
                for detection in detections
            ],
            dtype=float,
        )
        if detection_array.size == 0:
            detection_array = np.empty((0, 6), dtype=float)

        predictions: list[np.ndarray] = []
        active_trackers: list[_KalmanBoxTracker] = []
        for tracker in self.trackers:
            prediction = tracker.predict()
            if np.any(np.isnan(prediction)):
                continue
            predictions.append(prediction)
            active_trackers.append(tracker)
        self.trackers = active_trackers

        prediction_array = np.asarray(predictions, dtype=float) if predictions else np.empty((0, 4), dtype=float)
        matches, unmatched_detections, _ = _associate_detections_to_trackers(
            detection_array,
            prediction_array,
            self.iou_threshold,
        )

        for det_index, trk_index in matches:
            matched_detection = detection_array[det_index]
            self.trackers[trk_index].update(
                bbox=matched_detection[:4],
                confidence=float(matched_detection[4]),
                class_id=int(matched_detection[5]),
            )

        for det_index in unmatched_detections:
            detection = detection_array[det_index]
            self.trackers.append(
                _KalmanBoxTracker(
                    bbox=detection[:4],
                    confidence=float(detection[4]),
                    class_id=int(detection[5]),
                )
            )

        tracks: list[dict[str, float | int | list[float]]] = []
        survivors: list[_KalmanBoxTracker] = []
        for tracker in self.trackers:
            if tracker.time_since_update <= self.max_age:
                survivors.append(tracker)

            is_confirmed = tracker.time_since_update == 0 and (
                tracker.hit_streak >= self.min_hits or self.frame_count <= self.min_hits
            )
            if not is_confirmed:
                continue

            bbox = tracker.get_state().tolist()
            tracks.append(
                {
                    "track_id": int(tracker.id + 1),
                    "bbox": [float(value) for value in bbox],
                    "confidence": float(tracker.payload.confidence),
                    "class_id": int(tracker.payload.class_id),
                }
            )

        self.trackers = survivors
        return tracks
