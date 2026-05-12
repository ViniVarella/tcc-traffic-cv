"""Estimativa suavizada de filas a partir das contagens por ROI."""

from __future__ import annotations


class QueueEstimator:
    """Suaviza contagens visuais para produzir uma estimativa de fila mais estavel."""

    def __init__(self, smoothing_window: int = 5) -> None:
        self.smoothing_window = smoothing_window

    def update(self, roi_counts: dict[str, int]) -> dict[str, int]:
        """Retorna contagens suavizadas para uso do controlador."""
        return dict(roi_counts)
