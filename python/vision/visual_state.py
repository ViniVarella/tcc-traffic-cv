"""Contrato de estado visual usado pelo DQN do cenário SP."""

from __future__ import annotations

from typing import Mapping

import numpy as np


SP_LANE_ORDER = (
    ("south", "lane_0"),
    ("south", "lane_1"),
    ("south", "lane_2"),
    ("south", "lane_3"),
    ("east", "lane_0"),
    ("east", "lane_1"),
    ("west", "lane_0"),
)


class VisualStateEncoder:
    """Converte contagens visuais e estado local do TLS em vetor normalizado."""

    def __init__(self, max_lane_count: float = 10.0, phase_count: int = 5, max_green_seconds: float = 40.0) -> None:
        if max_lane_count <= 0 or phase_count <= 0 or max_green_seconds <= 0:
            raise ValueError("Parâmetros de normalização do estado visual devem ser positivos.")
        self.max_lane_count = float(max_lane_count)
        self.phase_count = int(phase_count)
        self.max_green_seconds = float(max_green_seconds)

    @property
    def state_size(self) -> int:
        return len(SP_LANE_ORDER) + self.phase_count + 1

    def encode(
        self,
        visual_counts: Mapping[str, Mapping[str, int]],
        phase_index: int,
        phase_elapsed_seconds: float,
    ) -> np.ndarray:
        """Retorna [contagens por faixa, fase one-hot, tempo da fase] em float32."""
        if not 0 <= phase_index < self.phase_count:
            raise ValueError(f"Índice de fase inválido: {phase_index}.")
        values = [
            min(1.0, max(0.0, float(visual_counts.get(camera_id, {}).get(lane_id, 0)) / self.max_lane_count))
            for camera_id, lane_id in SP_LANE_ORDER
        ]
        phase = [0.0] * self.phase_count
        phase[phase_index] = 1.0
        elapsed = min(1.0, max(0.0, float(phase_elapsed_seconds) / self.max_green_seconds))
        return np.asarray([*values, *phase, elapsed], dtype=np.float32)
