"""Conversao do estado bruto do SUMO em mensagens para a Unity."""

from __future__ import annotations

from typing import Any


class SumoStateExtractor:
    """Transforma dados do SUMO em estruturas serializaveis para renderizacao."""

    def __init__(self, coordinate_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
        self.coordinate_offset = coordinate_offset

    def build_state(
        self,
        step: int,
        sim_time: float,
        vehicles: list[dict[str, Any]],
        traffic_lights: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Monta a mensagem de estado completa para um passo de simulacao."""
        return {
            "step": step,
            "sim_time": sim_time,
            "vehicles": vehicles,
            "traffic_lights": traffic_lights,
        }

    def convert_vehicle_coordinates(self, vehicle_state: dict[str, Any]) -> dict[str, Any]:
        """Converte coordenadas do SUMO para o sistema esperado pela Unity."""
        return vehicle_state
