"""Cliente de alto nivel para controlar o SUMO via TraCI."""

from __future__ import annotations

from typing import Any


class SumoClient:
    """Encapsula o ciclo de vida do SUMO e operacoes basicas de simulacao."""

    def __init__(self, sumo_binary: str, config_path: str, gui: bool = True) -> None:
        self.sumo_binary = sumo_binary
        self.config_path = config_path
        self.gui = gui

    def start(self) -> None:
        """Inicia o processo do SUMO e estabelece a conexao TraCI."""

    def step(self) -> float:
        """Avanca um passo da simulacao e retorna o tempo simulado."""
        return 0.0

    def close(self) -> None:
        """Encerra a conexao TraCI e libera os recursos do simulador."""

    def get_vehicle_state(self) -> list[dict[str, Any]]:
        """Retorna um snapshot serializavel dos veiculos ativos."""
        return []

    def get_traffic_light_state(self, tls_id: str) -> dict[str, Any]:
        """Retorna o estado do semaforo indicado por identificador."""
        return {"id": tls_id, "phase": 0, "state": ""}

    def set_traffic_light_phase(self, tls_id: str, phase: int) -> None:
        """Define a fase corrente de um semaforo no SUMO."""
        _ = (tls_id, phase)

    def set_traffic_light_phase_duration(self, tls_id: str, duration: float) -> None:
        """Ajusta a duracao restante da fase ativa de um semaforo."""
        _ = (tls_id, duration)
