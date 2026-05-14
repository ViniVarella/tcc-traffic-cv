"""Teste de integracao SUMO -> Python -> Unity com estado real via UDP."""

from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Any

import yaml

from bridge import UnityBridge
from sumo import SumoClient, SumoStateExtractor


def load_config(config_path: Path) -> dict[str, Any]:
    """Carrega a configuracao YAML do projeto."""
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def main() -> None:
    """Extrai estado real do SUMO e envia para a Unity por alguns steps."""
    base_dir = Path(__file__).resolve().parents[1]
    config = load_config(base_dir / "config.yaml")

    sumo_client = SumoClient.from_config(config=config, base_dir=base_dir)
    unity_bridge = UnityBridge.from_config(config)
    state_extractor = SumoStateExtractor()
    tls_id = str(config["traffic_light"]["id"])

    try:
        sumo_client.start()
        tls_ids = sumo_client.get_traffic_light_ids()
        if tls_id not in tls_ids:
            raise RuntimeError(
                f"Semaforo configurado '{tls_id}' nao encontrado no cenario. "
                f"Semaforos disponiveis: {tls_ids}"
            )

        total_steps = 20
        for step in range(total_steps):
            sim_time = sumo_client.step()
            vehicles = sumo_client.get_vehicle_state()
            traffic_light_state = sumo_client.get_traffic_light_state(tls_id)
            state = state_extractor.build_simulation_state(
                step=step,
                sim_time=sim_time,
                vehicles=vehicles,
                traffic_light_state=traffic_light_state,
            )
            unity_bridge.send_state(state)
            print(
                f"state_sent step={state.step} "
                f"sim_time={state.sim_time:.2f} "
                f"vehicles={len(state.vehicles)} "
                f"traffic_lights={len(state.traffic_lights)}"
            )
            sleep(0.05)
    finally:
        sumo_client.close()
        unity_bridge.close()


if __name__ == "__main__":
    main()
