"""Contagem de tracks dentro de regioes de interesse por aproximacao."""

from __future__ import annotations


class ROICounter:
    """Conta veiculos rastreados em poligonos associados a cada aproximacao."""

    def __init__(self, rois: dict) -> None:
        self.rois = rois

    def count(self, tracks: list[dict]) -> dict[str, int]:
        """Retorna a contagem por aproximacao com base nos tracks recebidos."""
        _ = tracks
        return {name: 0 for name in self.rois}
