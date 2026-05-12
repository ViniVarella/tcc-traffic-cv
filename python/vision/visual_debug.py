"""Ferramentas auxiliares para anotacao visual e salvamento de frames."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


ROI_COLORS = {
    "north": (255, 128, 0),
    "south": (0, 255, 255),
    "east": (0, 200, 0),
    "west": (255, 0, 255),
}


class VisualDebugger:
    """Desenha elementos de depuracao visual e gerencia artefatos de analise."""

    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def annotate(
        self,
        frame: Any,
        detections: list[dict],
        tracks: list[dict],
        roi_counts: dict[str, int],
        rois: dict[str, list[list[int | float]]] | None = None,
        queue_counts: dict[str, int] | None = None,
        metadata: dict[str, str | int | float] | None = None,
    ) -> Any:
        """Retorna um frame anotado com deteccoes, tracks e informacoes de ROI."""
        canvas = frame.copy()
        self._draw_rois(canvas, rois or {})
        self._draw_detections(canvas, detections)
        self._draw_tracks(canvas, tracks)
        self._draw_counts(canvas, roi_counts, queue_counts or roi_counts)
        self._draw_metadata(canvas, metadata or {})
        return canvas

    def save_frame(self, frame: Any, name: str) -> Path:
        """Salva um frame de debug no diretorio configurado."""
        output_path = self.output_dir / name
        cv2.imwrite(str(output_path), frame)
        return output_path

    def _draw_rois(self, frame: np.ndarray, rois: dict[str, list[list[int | float]]]) -> None:
        for roi_name, points in rois.items():
            polygon = np.asarray(points, dtype=np.int32)
            color = ROI_COLORS.get(roi_name, (0, 255, 0))
            cv2.polylines(frame, [polygon], isClosed=True, color=color, thickness=2)
            label_point = polygon[0].tolist()
            cv2.putText(
                frame,
                roi_name,
                (int(label_point[0]), int(label_point[1]) - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )

    def _draw_detections(self, frame: np.ndarray, detections: list[dict]) -> None:
        for detection in detections:
            x1, y1, x2, y2 = [int(value) for value in detection["bbox"]]
            label = f"d:{detection['class_id']} {detection['confidence']:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 80, 255), 2)
            cv2.putText(
                frame,
                label,
                (x1, max(y1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (80, 80, 255),
                2,
                cv2.LINE_AA,
            )

    def _draw_tracks(self, frame: np.ndarray, tracks: list[dict]) -> None:
        for track in tracks:
            x1, y1, x2, y2 = [int(value) for value in track["bbox"]]
            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            label = f"id:{track['track_id']}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(frame, (center_x, center_y), 4, (0, 255, 0), -1)
            cv2.putText(
                frame,
                label,
                (x1, min(y2 + 18, frame.shape[0] - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

    def _draw_counts(
        self,
        frame: np.ndarray,
        roi_counts: dict[str, int],
        queue_counts: dict[str, int],
    ) -> None:
        panel_height = 24 + 24 * max(len(roi_counts), 1)
        cv2.rectangle(frame, (10, 10), (260, 10 + panel_height), (30, 30, 30), -1)
        cv2.putText(
            frame,
            "ROI counts",
            (18, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        for index, roi_name in enumerate(roi_counts):
            y = 54 + index * 24
            text = f"{roi_name}: raw={roi_counts[roi_name]} smooth={queue_counts.get(roi_name, roi_counts[roi_name])}"
            color = ROI_COLORS.get(roi_name, (255, 255, 255))
            cv2.putText(frame, text, (18, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    def _draw_metadata(self, frame: np.ndarray, metadata: dict[str, str | int | float]) -> None:
        if not metadata:
            return
        y = frame.shape[0] - 18 * len(metadata) - 10
        for key, value in metadata.items():
            cv2.putText(
                frame,
                f"{key}: {value}",
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            y += 18
