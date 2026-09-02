"""Camada de deteccao de veiculos baseada em Ultralytics YOLO."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from ultralytics import YOLO


class YoloVehicleDetector:
    """Carrega um modelo YOLO e retorna deteccoes no formato padronizado do projeto."""

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.15,
        classes: list[int] | None = None,
        inference_size: int = 1280,
        nms_iou_threshold: float = 0.5,
    ) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.classes = classes or [2, 3, 5, 7]
        self.inference_size = inference_size
        self.nms_iou_threshold = nms_iou_threshold
        self.model = YOLO(model=Path(model_path))

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        """Executa inferencia e retorna deteccoes de veiculos padronizadas."""
        if frame is None:
            return []

        results = self.model.predict(source=frame, imgsz=self.inference_size, verbose=False)
        if not results:
            return []

        detections: list[dict[str, Any]] = []
        boxes = results[0].boxes
        if boxes is None:
            return detections

        xyxy = boxes.xyxy.cpu().numpy() if boxes.xyxy is not None else np.empty((0, 4))
        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else np.empty((0,))
        classes = boxes.cls.cpu().numpy() if boxes.cls is not None else np.empty((0,))

        candidates: list[dict[str, Any]] = []
        for bbox, confidence, class_id in zip(xyxy, confs, classes):
            if confidence <= self.confidence_threshold or int(class_id) not in self.classes:
                continue
            x1, y1, x2, y2 = [float(value) for value in bbox.tolist()]
            candidates.append(
                {
                    "bbox": [x1, y1, x2, y2],
                    "confidence": float(confidence),
                    "class_id": int(class_id),
                }
            )
        return _class_agnostic_nms(candidates, self.nms_iou_threshold)

    def track_with_botsort(self, frame: Any, tracker_config: str | Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Executa detecção e BoT-SORT persistente no mesmo passe do YOLO.

        O backend Ultralytics mantém o estado do tracker entre chamadas quando
        ``persist=True``. Ao contrário do ByteTrack do Supervision, BoT-SORT
        pode usar características de aparência (ReID) configuradas no YAML.
        """
        if frame is None:
            return [], []

        results = self.model.track(
            source=frame,
            persist=True,
            tracker=str(tracker_config),
            conf=self.confidence_threshold,
            classes=self.classes,
            imgsz=self.inference_size,
            verbose=False,
        )
        if not results or results[0].boxes is None:
            return [], []

        boxes = results[0].boxes
        xyxy = boxes.xyxy.cpu().numpy() if boxes.xyxy is not None else np.empty((0, 4))
        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else np.empty((0,))
        class_ids = boxes.cls.cpu().numpy() if boxes.cls is not None else np.empty((0,))
        track_ids = boxes.id.cpu().numpy() if boxes.id is not None else np.empty((0,))

        detections: list[dict[str, Any]] = []
        tracks: list[dict[str, Any]] = []
        for index, (bbox, confidence, class_id) in enumerate(zip(xyxy, confs, class_ids)):
            if confidence <= self.confidence_threshold or int(class_id) not in self.classes:
                continue
            record = {
                "bbox": [float(value) for value in bbox.tolist()],
                "confidence": float(confidence),
                "class_id": int(class_id),
            }
            detections.append(record)
            if index < len(track_ids):
                tracks.append({**record, "track_id": int(track_ids[index])})
        return detections, tracks


def _class_agnostic_nms(detections: list[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    """Replica o NMS agnóstico de classe aplicado pelo SimJamCV."""
    kept: list[dict[str, Any]] = []
    for detection in sorted(detections, key=lambda value: float(value["confidence"]), reverse=True):
        if all(_iou(detection["bbox"], other["bbox"]) < threshold for other in kept):
            kept.append(detection)
    return kept


def _iou(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection == 0.0:
        return 0.0
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    return intersection / max(first_area + second_area - intersection, 1e-6)
