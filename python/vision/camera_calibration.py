"""Leitura das calibrações de câmera exportadas pelo Editor Unity."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class CameraCalibration:
    """ROIs normalizadas e metadados de uma câmera de tráfego."""

    camera_id: str
    capture_width: int
    capture_height: int
    approach_roi: tuple[Point, ...]
    lane_rois: dict[str, tuple[Point, ...]]

    def pixel_rois(self, frame_width: int, frame_height: int) -> dict[str, list[list[int]]]:
        """Escala ROIs normalizadas para as dimensões do frame recebido."""
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("As dimensões do frame devem ser positivas.")

        rois = {"approach": self.approach_roi, **self.lane_rois}
        return {
            roi_id: [
                [round(x * (frame_width - 1)), round(y * (frame_height - 1))]
                for x, y in points
            ]
            for roi_id, points in rois.items()
        }

    def lane_pixel_rois(self, frame_width: int, frame_height: int) -> dict[str, list[list[int]]]:
        """Retorna apenas as ROIs de faixas, próprias para o contador."""
        all_rois = self.pixel_rois(frame_width=frame_width, frame_height=frame_height)
        return {lane_id: all_rois[lane_id] for lane_id in self.lane_rois}


def load_camera_calibration(path: str | Path, expected_camera_id: str | None = None) -> CameraCalibration:
    """Carrega e valida um JSON de calibração exportado pelo Unity."""
    calibration_path = Path(path)
    raw = json.loads(calibration_path.read_text(encoding="utf-8"))
    if raw.get("schemaVersion") != 1:
        raise ValueError(f"Versão de calibração não suportada em {calibration_path}: {raw.get('schemaVersion')!r}.")

    camera_id = _read_nonempty_string(raw, "cameraId", calibration_path)
    if expected_camera_id is not None and camera_id != expected_camera_id:
        raise ValueError(
            f"Calibração {calibration_path} pertence à câmera {camera_id!r}, "
            f"mas era esperada {expected_camera_id!r}."
        )

    capture = _read_mapping(raw, "capture", calibration_path)
    capture_width = _read_positive_int(capture, "width", calibration_path)
    capture_height = _read_positive_int(capture, "height", calibration_path)
    approach = _read_roi(_read_mapping(raw, "approachRoi", calibration_path), calibration_path)

    lane_rois_raw = raw.get("laneRois")
    if not isinstance(lane_rois_raw, list) or not lane_rois_raw:
        raise ValueError(f"Calibração {calibration_path} precisa conter ao menos uma ROI de faixa.")

    lane_rois: dict[str, tuple[Point, ...]] = {}
    for lane_raw in lane_rois_raw:
        if not isinstance(lane_raw, dict):
            raise ValueError(f"ROI de faixa inválida em {calibration_path}.")
        lane_id = _read_nonempty_string(lane_raw, "id", calibration_path)
        if lane_id in lane_rois:
            raise ValueError(f"ID de faixa duplicado {lane_id!r} em {calibration_path}.")
        lane_rois[lane_id] = _read_roi(lane_raw, calibration_path)

    return CameraCalibration(
        camera_id=camera_id,
        capture_width=capture_width,
        capture_height=capture_height,
        approach_roi=approach,
        lane_rois=lane_rois,
    )


def _read_mapping(raw: dict[str, Any], key: str, path: Path) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Campo {key!r} inválido em {path}.")
    return value


def _read_nonempty_string(raw: dict[str, Any], key: str, path: Path) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo {key!r} inválido em {path}.")
    return value.strip()


def _read_positive_int(raw: dict[str, Any], key: str, path: Path) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Campo {key!r} deve ser inteiro positivo em {path}.")
    return value


def _read_roi(raw: dict[str, Any], path: Path) -> tuple[Point, ...]:
    points_raw = raw.get("points")
    if not isinstance(points_raw, list) or len(points_raw) != 4:
        raise ValueError(f"ROI em {path} deve conter exatamente quatro pontos.")

    points: list[Point] = []
    for point_raw in points_raw:
        if not isinstance(point_raw, dict):
            raise ValueError(f"Ponto de ROI inválido em {path}.")
        x = point_raw.get("x")
        y = point_raw.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise ValueError(f"Coordenada de ROI inválida em {path}.")
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            raise ValueError(f"Coordenada de ROI fora do intervalo normalizado em {path}.")
        points.append((float(x), float(y)))
    return tuple(points)
