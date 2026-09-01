"""Contagem de tracks dentro de regioes de interesse por aproximacao."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def _bbox_center(bbox: list[float]) -> tuple[float, float]:
    """Retorna o centro geometrico de uma bbox no formato xyxy."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def filter_detections_to_roi(
    detections: list[dict[str, Any]],
    roi: list[list[int | float]],
) -> list[dict[str, Any]]:
    """Mantém somente detecções cujo centro está na ROI principal.

    Corresponde à etapa ``filter_detections_to_polygon(..., CENTER)`` do
    SimJamCV e deve ocorrer antes de entregar detecções ao ByteTrack.
    """
    polygon = np.asarray(roi, dtype=np.int32)
    return [
        detection
        for detection in detections
        if cv2.pointPolygonTest(polygon, _bbox_center(detection["bbox"]), measureDist=False) >= 0
    ]


def select_counting_objects(
    detections: list[dict[str, Any]],
    tracks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Prefere tracks, mas mantém a contagem em fluxo livre sem track.

    ByteTrack oferece IDs persistentes quando há associação temporal. Em uma
    câmera com veículos rápidos ou amostragem esparsa, ele pode não confirmar
    nenhum ID apesar de haver detecções válidas no frame. Nesse caso, as
    detecções já filtradas pela ROI principal são usadas somente naquele step.
    """
    if tracks:
        return tracks, "tracks"
    return detections, "detections_fallback"


class ROICounter:
    """Conta veiculos dentro de ROIs poligonais associadas a cada aproximacao.

    Na arquitetura final, cada camera Unity tera sua propria ROI calibrada
    manualmente. O contador usa o centro da bounding box para medir quantos
    veiculos estao aguardando dentro da regiao relevante da imagem. O uso do
    tracker e auxiliar; pequenas trocas de ID nao devem ser criticas para o
    controlador inicial.
    """

    def __init__(self, rois: dict[str, list[list[int | float]]]) -> None:
        self.rois = rois
        self._roi_arrays = {
            name: np.asarray(points, dtype=np.int32)
            for name, points in rois.items()
        }

    def count(self, tracks: list[dict[str, Any]]) -> dict[str, int]:
        """Conta tracks ou detecções cujo centro cai dentro de cada ROI."""
        counts = {name: 0 for name in self.rois}
        seen_track_ids: dict[str, set[int]] = {name: set() for name in self.rois}

        for track in tracks:
            center = _bbox_center(track["bbox"])
            for name, polygon in self._roi_arrays.items():
                if cv2.pointPolygonTest(polygon, center, measureDist=False) >= 0:
                    track_id = track.get("track_id")
                    if track_id is None:
                        counts[name] += 1
                    elif int(track_id) not in seen_track_ids[name]:
                        seen_track_ids[name].add(int(track_id))
                        counts[name] += 1

        return counts
