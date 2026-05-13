"""Coleta de metricas de verdade de terreno extraidas do SUMO."""

from __future__ import annotations

from typing import Any


class GroundTruthCollector:
    """Centraliza metricas perfeitas do SUMO usadas apenas para avaliacao.

    Essas metricas existem para comparar contagem visual, filas reais, tempos
    de espera e demais indicadores de desempenho. Elas nao devem alimentar a
    decisao online do controlador baseado em visao.
    """

    def __init__(self, tls_id: str) -> None:
        self.tls_id = tls_id

    def collect_step_metrics(
        self,
        sim_time: float,
        vehicles: list[dict[str, Any]],
        traffic_light_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Retorna um snapshot simples de avaliacao para o passo atual."""
        return {
            "sim_time": float(sim_time),
            "tls_id": self.tls_id,
            "tls_phase": traffic_light_state.get("phase"),
            "tls_state": traffic_light_state.get("state"),
            "active_vehicle_count": len(vehicles),
        }

    def collect_vehicle_snapshot(self, vehicles: list[dict[str, Any]]) -> dict[str, Any]:
        """Resume o estado dos veiculos ativos para logs e avaliacao futura."""
        return {
            "vehicle_ids": [vehicle["id"] for vehicle in vehicles],
            "active_vehicle_count": len(vehicles),
        }
