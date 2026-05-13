"""Teste minimo de integracao com SUMO via TraCI, sem Unity e sem controle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sumo import GroundTruthCollector, SumoClient, SumoStateExtractor


def load_config(config_path: Path) -> dict[str, Any]:
    """Carrega a configuracao YAML do projeto."""
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def main() -> None:
    """Inicia o SUMO, avanca alguns steps e imprime estado basico."""
    base_dir = Path(__file__).resolve().parents[1]
    config = load_config(base_dir / "config.yaml")

    sumo_client = SumoClient.from_config(config=config, base_dir=base_dir)
    state_extractor = SumoStateExtractor()
    tls_id = str(config["traffic_light"]["id"])
    ground_truth = GroundTruthCollector(tls_id=tls_id)

    try:
        sumo_client.start()

        tls_ids = sumo_client.get_traffic_light_ids()
        if tls_id not in tls_ids:
            raise RuntimeError(
                f"Semaforo configurado '{tls_id}' nao encontrado no cenario. "
                f"Semaforos disponiveis: {tls_ids}"
            )

        print(f"SUMO iniciado com sucesso. TLS monitorado: {tls_id}")

        max_steps = 5
        for step in range(max_steps):
            sim_time = sumo_client.step()
            vehicles = sumo_client.get_vehicle_state()
            traffic_light_state = sumo_client.get_traffic_light_state(tls_id)
            extracted_state = state_extractor.build_from_client(
                step=step,
                sim_time=sim_time,
                vehicles=vehicles,
                traffic_light_state=traffic_light_state,
            )
            metrics = ground_truth.collect_step_metrics(
                sim_time=sim_time,
                vehicles=vehicles,
                traffic_light_state=traffic_light_state,
            )

            print(
                f"step={extracted_state['step']} "
                f"sim_time={sim_time:.2f} "
                f"active_vehicles={len(vehicles)} "
                f"tls_phase={traffic_light_state['phase']} "
                f"tls_state={traffic_light_state['state']}"
            )
            print(f"ground_truth={metrics}")

        if tls_ids:
            current_phase = traffic_light_state["phase"]
            sumo_client.set_traffic_light_phase(tls_id, current_phase)
            print(f"Teste de alteracao manual de fase executado para {tls_id} na fase {current_phase}.")

    except FileNotFoundError as exc:
        raise SystemExit(
            "Nao foi possivel iniciar o teste SUMO porque o arquivo .sumocfg "
            f"nao foi encontrado: {exc}"
        ) from exc
    finally:
        sumo_client.close()


if __name__ == "__main__":
    main()
