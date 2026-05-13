"""Cliente de alto nivel para controlar o SUMO via TraCI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import traci
from sumolib import checkBinary


class SumoClient:
    """Encapsula o ciclo de vida do SUMO e operacoes basicas de simulacao."""

    def __init__(
        self,
        sumo_binary: str | None,
        config_path: str,
        gui: bool = True,
        seed: int | None = None,
        step_length: float | None = None,
    ) -> None:
        self.sumo_binary = sumo_binary
        self.config_path = str(Path(config_path))
        self.gui = gui
        self.seed = seed
        self.step_length = step_length
        self._started = False

    @classmethod
    def from_config(cls, config: dict[str, Any], base_dir: str | Path) -> "SumoClient":
        """Constroi o cliente a partir da configuracao YAML do projeto."""
        base_path = Path(base_dir)
        sumo_config = config.get("sumo", {})
        experiment_config = config.get("experiment", {})

        config_path = (base_path / sumo_config["config_path"]).resolve()
        gui = bool(sumo_config.get("gui", True))
        binary_name = "sumo-gui" if gui else "sumo"
        return cls(
            sumo_binary=binary_name,
            config_path=str(config_path),
            gui=gui,
            seed=experiment_config.get("seed"),
            step_length=sumo_config.get("step_length"),
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

        traci.start(sumo_cmd)
        self._started = True

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
