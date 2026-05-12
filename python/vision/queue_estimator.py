"""Estimativa suavizada de filas a partir das contagens por ROI."""

from __future__ import annotations

from collections import defaultdict, deque


class QueueEstimator:
    """Suaviza contagens visuais para produzir uma estimativa de fila mais estavel."""

    def __init__(self, smoothing_window: int = 5) -> None:
        self.smoothing_window = smoothing_window
        self._history: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=smoothing_window))

    def update(self, roi_counts: dict[str, int]) -> dict[str, int]:
        """Retorna contagens suavizadas para uso do controlador."""
        smoothed_counts: dict[str, int] = {}
        for roi_name, count in roi_counts.items():
            history = self._history[roi_name]
            history.append(int(count))
            smoothed_counts[roi_name] = int(round(sum(history) / len(history)))

        return smoothed_counts
