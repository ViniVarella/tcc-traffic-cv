"""Politicas de decisao para o controlador semaforico."""

from __future__ import annotations

from typing import Any


class QueueBasedPolicy:
    """Avalia contagens visuais e sugere a direcao com maior prioridade."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def decide(self, visual_counts: dict[str, int]) -> dict[str, Any]:
        """Produz uma decisao abstrata baseada no estado das filas observadas."""
        return {"action": "hold", "visual_counts": visual_counts}
