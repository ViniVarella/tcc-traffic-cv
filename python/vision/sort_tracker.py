"""Stubs para rastreamento temporal de deteccoes com SORT."""

from __future__ import annotations


class VehicleTracker:
    """Mantem IDs consistentes entre frames a partir das deteccoes de veiculos."""

    def __init__(self, max_age: int = 20, min_hits: int = 3, iou_threshold: float = 0.3) -> None:
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold

    def update(self, detections: list[dict]) -> list[dict]:
        """Atualiza o estado do tracker e retorna tracks padronizados."""
        _ = detections
        return []
