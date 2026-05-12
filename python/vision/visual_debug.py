"""Ferramentas auxiliares para anotacao visual e salvamento de frames."""

from __future__ import annotations

from typing import Any


class VisualDebugger:
    """Desenha elementos de depuracao visual e gerencia artefatos de analise."""

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir

    def annotate(
        self,
        frame: Any,
        detections: list[dict],
        tracks: list[dict],
        roi_counts: dict[str, int],
    ) -> Any:
        """Retorna um frame anotado com deteccoes, tracks e informacoes de ROI."""
        _ = (detections, tracks, roi_counts)
        return frame
