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

    def collect_detector_snapshot(
        self,
        step_id: int,
        sim_time: float,
        detector_metrics: dict[str, dict[str, float | int]],
    ) -> dict[str, Any]:
        """Cria um snapshot E2 alinhado a um step para avaliação offline.

        O chamador fornece as métricas já consultadas via TraCI para manter esta
        classe independente do cliente TraCI e facilmente testável. Este payload
        é apenas referência de avaliação: nunca deve ser enviado ao controlador
        baseado em visão durante a execução online.
        """
        if step_id < 0:
            raise ValueError("step_id não pode ser negativo.")

        detectors: dict[str, dict[str, float | int]] = {}
        for detector_id, metrics in detector_metrics.items():
            if not detector_id:
                raise ValueError("ID de detector E2 não pode ser vazio.")
            detectors[detector_id] = {
                "vehicle_count": int(metrics["vehicle_count"]),
                "halting_count": int(metrics["halting_count"]),
                "occupancy": float(metrics["occupancy"]),
            }

        return {
            "step_id": int(step_id),
            "sim_time": float(sim_time),
            "detectors": detectors,
        }
