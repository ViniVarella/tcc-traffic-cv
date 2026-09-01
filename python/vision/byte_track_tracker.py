"""Adaptador ByteTrack compatível com o formato de detecção do projeto.

O SimJamCV usa ``supervision.ByteTrack`` depois de filtrar detecções pela
ROI principal. Esta classe preserva aquele fluxo sem vazar tipos da biblioteca
para o restante da integração Unity/DQN.
"""

from __future__ import annotations

import inspect
from typing import Any

import numpy as np


class ByteTrackVehicleTracker:
    """Mantém IDs de veículos entre frames usando ByteTrack do Supervision."""

    def __init__(
        self,
        frame_rate: float = 1.0,
        confidence_threshold: float = 0.15,
        matching_threshold: float = 0.6,
    ) -> None:
        try:
            import supervision as sv
        except ImportError as exception:  # pragma: no cover - depende do ambiente
            raise RuntimeError(
                "ByteTrack requer o pacote 'supervision'. "
                "Instale as dependências com pip install -r python/requirements.txt."
            ) from exception

        self._sv = sv
        if not 0.0 < matching_threshold <= 1.0:
            raise ValueError("matching_threshold precisa estar no intervalo (0, 1].")
        self._tracker = self._create_tracker(frame_rate, confidence_threshold, matching_threshold)

    def update(self, detections: list[dict[str, Any]]) -> list[dict[str, float | int | list[float]]]:
        """Atualiza ByteTrack e retorna tracks no formato padronizado."""
        if detections:
            xyxy = np.asarray([detection["bbox"] for detection in detections], dtype=np.float32)
            confidence = np.asarray([detection["confidence"] for detection in detections], dtype=np.float32)
            class_id = np.asarray([detection["class_id"] for detection in detections], dtype=int)
        else:
            xyxy = np.empty((0, 4), dtype=np.float32)
            confidence = np.empty((0,), dtype=np.float32)
            class_id = np.empty((0,), dtype=int)

        supervision_detections = self._sv.Detections(
            xyxy=xyxy,
            confidence=confidence,
            class_id=class_id,
        )
        tracked = self._tracker.update_with_detections(supervision_detections)
        if len(tracked) == 0 or tracked.tracker_id is None:
            return []

        tracks: list[dict[str, float | int | list[float]]] = []
        for bbox, track_id, track_confidence, track_class_id in zip(
            tracked.xyxy,
            tracked.tracker_id,
            tracked.confidence,
            tracked.class_id,
        ):
            tracks.append(
                {
                    "track_id": int(track_id),
                    "bbox": [float(value) for value in bbox.tolist()],
                    "confidence": float(track_confidence),
                    "class_id": int(track_class_id),
                }
            )
        return tracks

    def _create_tracker(self, frame_rate: float, confidence_threshold: float, matching_threshold: float) -> Any:
        """Mantém compatibilidade entre versões recentes do Supervision."""
        effective_frame_rate = max(1, round(frame_rate))
        # O Supervision converte este valor usando frame_rate / 30. Com a
        # amostragem SP de 1 FPS, 240 preserva um track perdido por ~8 s.
        lost_track_buffer = 240
        parameters = set(inspect.signature(self._sv.ByteTrack.__init__).parameters)
        if {"track_thresh", "match_thresh", "track_buffer"} <= parameters:
            return self._sv.ByteTrack(
                frame_rate=effective_frame_rate,
                track_thresh=confidence_threshold,
                match_thresh=matching_threshold,
                track_buffer=lost_track_buffer,
            )
        if "track_activation_threshold" in parameters:
            arguments: dict[str, Any] = {
                "frame_rate": effective_frame_rate,
                "track_activation_threshold": confidence_threshold,
            }
            if "minimum_matching_threshold" in parameters:
                arguments["minimum_matching_threshold"] = matching_threshold
            if "lost_track_buffer" in parameters:
                arguments["lost_track_buffer"] = lost_track_buffer
            if "minimum_consecutive_frames" in parameters:
                arguments["minimum_consecutive_frames"] = 1
            return self._sv.ByteTrack(**arguments)
        return self._sv.ByteTrack(frame_rate=effective_frame_rate)
