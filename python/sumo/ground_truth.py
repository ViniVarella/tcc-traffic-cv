"""Coleta de metricas de verdade de terreno extraidas do SUMO."""

from __future__ import annotations

from typing import Any


class GroundTruthCollector:
    """Centraliza metricas do SUMO usadas apenas para avaliacao experimental."""

    def __init__(self, tls_id: str) -> None:
        self.tls_id = tls_id

    def collect_step_metrics(self) -> dict[str, Any]:
        """Retorna as metricas de ground truth disponiveis para o passo atual."""
        return {"tls_id": self.tls_id}
