"""Stubs para a camada de deteccao de veiculos baseada em YOLO."""

from __future__ import annotations

from typing import Any


class YoloVehicleDetector:
    """Carrega o modelo YOLO e padroniza a inferencia sobre frames da Unity."""

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

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        """Retorna deteccoes padronizadas de veiculos para um frame."""
        _ = frame
        return []
