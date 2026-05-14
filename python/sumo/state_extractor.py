"""Conversao do estado bruto do SUMO em mensagens para a Unity."""

from __future__ import annotations

from typing import Any

from bridge import SimulationState, TrafficLightState, VehicleState


class SumoStateExtractor:
    """Transforma dados do SUMO em estruturas serializaveis para renderizacao.

    Neste marco, a classe e usada para padronizar o estado extraido via TraCI.
    A conversao para Unity continua isolada, mas ainda sem integracao real com
    o renderizador.
    """

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
        converted_vehicles = [self.convert_vehicle_coordinates(vehicle) for vehicle in vehicles]
        return {
            "step": step,
            "step_id": step,
            "sim_time": sim_time,
            "vehicles": converted_vehicles,
            "traffic_lights": [self.convert_traffic_light_state(light) for light in traffic_lights],
        }

    def convert_vehicle_coordinates(self, vehicle_state: dict[str, Any]) -> dict[str, Any]:
        """Converte coordenadas SUMO em uma forma simples para a Unity.

        Conversao inicial usada neste marco:
        - Unity x = SUMO x
        - Unity z = SUMO y
        - Unity y = 0.0
        """
        converted = dict(vehicle_state)
        x_offset, y_offset, z_offset = self.coordinate_offset
        converted["x"] = float(vehicle_state["x"]) + x_offset
        converted["y"] = float(y_offset)
        converted["z"] = float(vehicle_state["y"]) + z_offset
        return converted

    def convert_traffic_light_state(self, traffic_light_state: dict[str, Any]) -> dict[str, Any]:
        """Padroniza o estado do semaforo para o payload enviado a Unity."""
        return {
            "id": str(traffic_light_state["id"]),
            "phase": int(traffic_light_state["phase"]),
            "state": str(traffic_light_state["state"]),
        }

    def build_from_client(
        self,
        step: int,
        sim_time: float,
        vehicles: list[dict[str, Any]],
        traffic_light_state: dict[str, Any] | list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Monta um estado completo a partir dos dados coletados pelo cliente."""
        if isinstance(traffic_light_state, dict):
            traffic_lights = [traffic_light_state]
        else:
            traffic_lights = traffic_light_state
        return self.build_state(
            step=step,
            sim_time=sim_time,
            vehicles=vehicles,
            traffic_lights=traffic_lights,
        )

    def build_simulation_state(
        self,
        step: int,
        sim_time: float,
        vehicles: list[dict[str, Any]],
        traffic_light_state: dict[str, Any] | list[dict[str, Any]],
    ) -> SimulationState:
        """Monta um `SimulationState` pronto para serializacao e envio."""
        if isinstance(traffic_light_state, dict):
            traffic_lights = [traffic_light_state]
        else:
            traffic_lights = traffic_light_state

        return SimulationState(
            step=step,
            sim_time=sim_time,
            vehicles=[
                VehicleState(**self.convert_vehicle_coordinates(vehicle))
                for vehicle in vehicles
            ],
            traffic_lights=[
                TrafficLightState(**self.convert_traffic_light_state(light))
                for light in traffic_lights
            ],
        )
