"""Cliente de alto nivel para controlar o SUMO via TraCI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import traci
from sumolib import checkBinary

from .scenarios import resolve_sumo_scenario


class SumoClient:
    """Encapsula o ciclo de vida do SUMO e operacoes basicas de simulacao."""

    def __init__(
        self,
        sumo_binary: str | None,
        config_path: str,
        gui: bool = True,
        seed: int | None = None,
        step_length: float | None = None,
        traci_port: int | None = None,
        scenario: str | None = None,
    ) -> None:
        self.sumo_binary = sumo_binary
        self.config_path = str(Path(config_path))
        self.gui = gui
        self.seed = seed
        self.step_length = step_length
        self.traci_port = traci_port
        self.scenario = scenario
        self._started = False
        self._vehicle_lanes: dict[str, str] = {}

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        base_dir: str | Path,
        seed_override: int | None = None,
        scenario_override: str | None = None,
    ) -> "SumoClient":
        """Constrói o cliente; ``seed_override``/``scenario_override`` substituem o perfil."""
        base_path = Path(base_dir)
        sumo_config = config.get("sumo", {})
        experiment_config = config.get("experiment", {})

        scenario, relative_config_path = resolve_sumo_scenario(config, scenario_override)
        config_path = (base_path / relative_config_path).resolve()
        gui = bool(sumo_config.get("gui", True))
        binary_name = "sumo-gui" if gui else "sumo"
        return cls(
            sumo_binary=binary_name,
            config_path=str(config_path),
            gui=gui,
            seed=experiment_config.get("seed") if seed_override is None else int(seed_override),
            step_length=sumo_config.get("step_length"),
            traci_port=sumo_config.get("traci_port"),
            scenario=scenario,
        )

    def start(self) -> None:
        """Inicia o processo do SUMO e estabelece a conexao TraCI."""
        config_path = Path(self.config_path)
        if not config_path.exists():
            raise FileNotFoundError(
                "Arquivo .sumocfg nao encontrado. "
                f"Esperado em: {config_path}"
            )

        binary_name = self.sumo_binary or ("sumo-gui" if self.gui else "sumo")
        sumo_binary = checkBinary(binary_name)
        sumo_cmd = [sumo_binary, "-c", str(config_path)]

        if self.seed is not None:
            sumo_cmd.extend(["--seed", str(int(self.seed))])
        if self.step_length is not None:
            sumo_cmd.extend(["--step-length", str(float(self.step_length))])

        traci.start(sumo_cmd, port=self.traci_port)
        self._started = True
        self._vehicle_lanes = {}

    def step(self) -> float:
        """Avanca um passo da simulacao e retorna o tempo simulado."""
        self._ensure_started()
        traci.simulationStep()
        return float(traci.simulation.getTime())

    def close(self) -> None:
        """Encerra a conexao TraCI e libera os recursos do simulador."""
        if not self._started:
            return
        try:
            traci.close()
        finally:
            self._started = False

    def get_vehicle_state(self) -> list[dict[str, Any]]:
        """Retorna um snapshot serializavel dos veiculos ativos."""
        self._ensure_started()
        vehicles: list[dict[str, Any]] = []
        for vehicle_id in traci.vehicle.getIDList():
            x_pos, y_pos = traci.vehicle.getPosition(vehicle_id)
            vehicles.append(
                {
                    "id": vehicle_id,
                    "x": float(x_pos),
                    "y": float(y_pos),
                    "angle": float(traci.vehicle.getAngle(vehicle_id)),
                    "speed": float(traci.vehicle.getSpeed(vehicle_id)),
                    "type": str(traci.vehicle.getTypeID(vehicle_id)),
                }
            )
        return vehicles

    def get_simulation_events(self) -> dict[str, list[str]]:
        """Retorna partidas e chegadas do último passo para avaliação offline."""
        self._ensure_started()
        return {
            "departed": [str(vehicle_id) for vehicle_id in traci.simulation.getDepartedIDList()],
            "arrived": [str(vehicle_id) for vehicle_id in traci.simulation.getArrivedIDList()],
        }

    def get_active_vehicle_metrics(self) -> dict[str, dict[str, float]]:
        """Retorna métricas globais dos veículos ativos, sem consultar detectores E2."""
        self._ensure_started()
        return {
            str(vehicle_id): {
                "speed": float(traci.vehicle.getSpeed(vehicle_id)),
                "accumulated_waiting_time": float(traci.vehicle.getAccumulatedWaitingTime(vehicle_id)),
            }
            for vehicle_id in traci.vehicle.getIDList()
        }

    def get_traffic_light_state(self, tls_id: str) -> dict[str, Any]:
        """Retorna o estado do semaforo indicado por identificador."""
        self._ensure_started()
        return {
            "id": tls_id,
            "phase": int(traci.trafficlight.getPhase(tls_id)),
            "state": str(traci.trafficlight.getRedYellowGreenState(tls_id)),
        }

    def get_traffic_light_ids(self) -> list[str]:
        """Retorna os identificadores de semaforos disponiveis na simulacao."""
        self._ensure_started()
        return list(traci.trafficlight.getIDList())

    def get_lane_area_detector_ids(self) -> list[str]:
        """Retorna os identificadores dos detectores E2 disponiveis."""
        self._ensure_started()
        return list(traci.lanearea.getIDList())

    def get_lane_area_detector_metrics(self, detector_id: str) -> dict[str, float | int]:
        """Retorna as metricas usadas pelo estado DQN de um detector E2."""
        self._ensure_started()
        return {
            "vehicle_count": int(traci.lanearea.getLastStepVehicleNumber(detector_id)),
            "halting_count": int(traci.lanearea.getLastStepHaltingNumber(detector_id)),
            "occupancy": float(traci.lanearea.getLastStepOccupancy(detector_id)),
        }

    def vehicle_lane_id(self, lane_id: str) -> str:
        """Traduz a faixa lógica ``<edge>_<k>`` (k-ésima faixa de veículos) no ID real.

        O perfil e as ROIs numeram só as faixas de veículos. Na rede com
        pedestres a calçada ocupa a faixa 0 e as de veículos ganham +1
        (``E3_0`` → ``E3_1``); na rede sem calçadas a tradução é a identidade.
        """
        cached = self._vehicle_lanes.get(lane_id)
        if cached is not None:
            return cached
        self._ensure_started()
        edge_id, _, index = lane_id.rpartition("_")
        if not edge_id or not index.isdigit():
            raise ValueError(f"ID de faixa inválido: {lane_id!r}")
        lanes = [f"{edge_id}_{position}" for position in range(int(traci.edge.getLaneNumber(edge_id)))]
        vehicle_lanes = [lane for lane in lanes if list(traci.lane.getAllowed(lane)) != ["pedestrian"]]
        if int(index) >= len(vehicle_lanes):
            raise ValueError(f"A edge {edge_id!r} não tem a faixa de veículos {index}.")
        self._vehicle_lanes[lane_id] = vehicle_lanes[int(index)]
        return self._vehicle_lanes[lane_id]

    def pedestrian_link_count(self, tls_id: str) -> int:
        """Links do semáforo que controlam faixas de pedestre (0 na rede sem pedestres)."""
        self._ensure_started()
        return sum(1 for links in traci.trafficlight.getControlledLinks(tls_id)
                   if links and str(links[0][0]).startswith(":"))

    def get_lane_vehicle_positions(self, lane_id: str) -> list[tuple[str, float]]:
        """Retorna ``(id, posição da frente na lane em m)`` dos veículos da faixa lógica."""
        self._ensure_started()
        return [
            (str(vehicle_id), float(traci.vehicle.getLanePosition(vehicle_id)))
            for vehicle_id in traci.lane.getLastStepVehicleIDs(self.vehicle_lane_id(lane_id))
        ]

    def get_incoming_lane_metrics(self, lane_ids: list[str] | tuple[str, ...]) -> dict[str, float | int]:
        """Soma parados e espera nativa nas faixas lógicas informadas e mede a fila de inserção."""
        self._ensure_started()
        lanes = [self.vehicle_lane_id(lane_id) for lane_id in lane_ids]
        return {
            "halting_vehicles": sum(int(traci.lane.getLastStepHaltingNumber(lane_id)) for lane_id in lanes),
            "waiting_time_s": sum(float(traci.lane.getWaitingTime(lane_id)) for lane_id in lanes),
            "pending_vehicles": len(traci.simulation.getPendingVehicles()),
        }

    def get_lane_length(self, lane_id: str) -> float:
        self._ensure_started()
        return float(traci.lane.getLength(self.vehicle_lane_id(lane_id)))

    def get_teleport_count(self) -> int:
        """Veículos que iniciaram teleporte no último step (bloqueio > time-to-teleport)."""
        self._ensure_started()
        return int(traci.simulation.getStartingTeleportNumber())

    def ensure_vehicle_type(self, type_id: str, vehicle_class: str, speed_factor: float, color: tuple[int, int, int]) -> None:
        """Cria (uma vez) um tipo derivado do padrão do SUMO, sem editar os arquivos de rota."""
        self._ensure_started()
        if type_id in traci.vehicletype.getIDList():
            return
        traci.vehicletype.copy("DEFAULT_VEHTYPE", type_id)
        traci.vehicletype.setVehicleClass(type_id, vehicle_class)
        traci.vehicletype.setShapeClass(type_id, vehicle_class)
        traci.vehicletype.setSpeedFactor(type_id, float(speed_factor))
        traci.vehicletype.setColor(type_id, (*color, 255))

    def add_vehicle(self, vehicle_id: str, from_edge: str, to_edge: str, type_id: str) -> None:
        """Insere um veículo agora, de uma aproximação direto a uma saída do cruzamento.

        A rota é só ``[entrada, saída]``: no cenário SP elas se ligam pelo próprio
        cruzamento. (``simulation.findRoute`` do traci 1.26 é incompatível com o
        SUMO 1.22 e por isso não é usado.)
        """
        self._ensure_started()
        route_id = f"route_{vehicle_id}"
        traci.route.add(route_id, [from_edge, to_edge])
        traci.vehicle.add(vehicle_id, route_id, typeID=type_id, depart="now", departLane="best", departSpeed="max")

    def get_vehicle_road_state(self, vehicle_id: str) -> dict[str, float | str] | None:
        """Posição de um veículo na rede, ou ``None`` se ele não está (mais) nela."""
        self._ensure_started()
        if vehicle_id not in traci.vehicle.getIDList():
            return None
        lane_id = str(traci.vehicle.getLaneID(vehicle_id))
        return {
            "road_id": str(traci.vehicle.getRoadID(vehicle_id)),
            "lane_id": lane_id,
            "lane_position": float(traci.vehicle.getLanePosition(vehicle_id)),
            "lane_length": float(traci.lane.getLength(lane_id)) if lane_id and not lane_id.startswith(":") else 0.0,
            "speed": float(traci.vehicle.getSpeed(vehicle_id)),
            "time_loss": float(traci.vehicle.getTimeLoss(vehicle_id)),
            "waiting_time": float(traci.vehicle.getAccumulatedWaitingTime(vehicle_id)),
        }

    def set_traffic_light_phase(self, tls_id: str, phase: int) -> None:
        """Define a fase corrente de um semaforo no SUMO."""
        self._ensure_started()
        traci.trafficlight.setPhase(tls_id, int(phase))

    def set_traffic_light_phase_duration(self, tls_id: str, duration: float) -> None:
        """Ajusta a duracao restante da fase ativa de um semaforo."""
        self._ensure_started()
        traci.trafficlight.setPhaseDuration(tls_id, float(duration))

    def get_pending_vehicle_count(self) -> int:
        """Retorna o numero de veiculos ainda esperados na simulacao."""
        self._ensure_started()
        return int(traci.simulation.getMinExpectedNumber())

    def _ensure_started(self) -> None:
        if not self._started:
            raise RuntimeError("SumoClient ainda nao foi iniciado.")
