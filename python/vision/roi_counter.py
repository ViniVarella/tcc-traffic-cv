"""Contagem de tracks dentro de regioes de interesse por aproximacao."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def _bbox_center(bbox: list[float]) -> tuple[float, float]:
    """Retorna o centro geometrico de uma bbox no formato xyxy."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


class ROICounter:
    """Conta veiculos rastreados em poligonos associados a cada aproximacao."""

    def __init__(self, rois: dict[str, list[list[int | float]]]) -> None:
        self.rois = rois
        self._roi_arrays = {
            name: np.asarray(points, dtype=np.int32)
            for name, points in rois.items()
        }

    def count(self, tracks: list[dict[str, Any]]) -> dict[str, int]:
        """Conta tracks cujo centro da bbox cai dentro de cada poligono ROI."""
        counts = {name: 0 for name in self.rois}
        seen_track_ids: dict[str, set[int]] = {name: set() for name in self.rois}

        for track in tracks:
            center = _bbox_center(track["bbox"])
            for name, polygon in self._roi_arrays.items():
                if cv2.pointPolygonTest(polygon, center, measureDist=False) >= 0:
                    track_id = int(track["track_id"])
                    if track_id not in seen_track_ids[name]:
                        seen_track_ids[name].add(track_id)
                        counts[name] += 1

        return counts
