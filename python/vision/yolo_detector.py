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
        confidence_threshold: float = 0.35,
        classes: list[int] | None = None,
        inference_size: int = 640,
    ) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.classes = classes or [2, 3, 5, 7]
        self.inference_size = inference_size
        self.model = YOLO(model=Path(model_path))

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        """Executa inferencia e retorna deteccoes de veiculos padronizadas."""
        if frame is None:
            return []

        results = self.model.predict(
            source=frame,
            conf=self.confidence_threshold,
            classes=self.classes,
            imgsz=self.inference_size,
            verbose=False,
        )
        if not results:
            return []

        detections: list[dict[str, Any]] = []
        boxes = results[0].boxes
        if boxes is None:
            return detections

        xyxy = boxes.xyxy.cpu().numpy() if boxes.xyxy is not None else np.empty((0, 4))
        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else np.empty((0,))
        classes = boxes.cls.cpu().numpy() if boxes.cls is not None else np.empty((0,))

        for bbox, confidence, class_id in zip(xyxy, confs, classes):
            x1, y1, x2, y2 = [float(value) for value in bbox.tolist()]
            detections.append(
                {
                    "bbox": [x1, y1, x2, y2],
                    "confidence": float(confidence),
                    "class_id": int(class_id),
                }
            )

        return detections
