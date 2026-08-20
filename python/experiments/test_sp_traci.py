"""Valida o cenário SP via TraCI, sem Unity e sem inferência do DQN."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from sumo import SumoClient


def load_config(config_path: Path) -> dict[str, Any]:
    """Carrega um perfil de cenário YAML."""
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def parse_args(base_dir: Path) -> argparse.Namespace:
    """Recebe um perfil alternativo sem alterar a configuração padrão."""
    parser = argparse.ArgumentParser(description="Valida o cenário SUMO SP via TraCI.")
    parser.add_argument(
        "--config",
        type=Path,
        default=base_dir / "configs" / "sp.yaml",
        help="Perfil YAML do cenário SP.",
    )
    return parser.parse_args()


def main() -> None:
    """Inicia SP, valida TLS/E2 e testa uma mudança controlada de fase."""
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    config_path = args.config.resolve()
    config = load_config(config_path)

    sumo_client = SumoClient.from_config(config=config, base_dir=base_dir)
    tls_config = config["traffic_light"]
    tls_id = str(tls_config["id"])
    expected_phase_count = int(tls_config["phase_count"])
    target_phase = int(tls_config["phases"]["secondary_green"])
    detector_ids = [str(detector_id) for detector_id in config["detectors"]["ids"]]

    try:
        sumo_client.start()

        available_tls_ids = sumo_client.get_traffic_light_ids()
        if tls_id not in available_tls_ids:
            raise RuntimeError(
                f"Semáforo configurado '{tls_id}' não encontrado. "
                f"Disponíveis: {available_tls_ids}"
            )

        available_detector_ids = set(sumo_client.get_lane_area_detector_ids())
        missing_detector_ids = [
            detector_id for detector_id in detector_ids if detector_id not in available_detector_ids
        ]
        if missing_detector_ids:
            raise RuntimeError(
                "Detectores E2 configurados não encontrados: "
                f"{missing_detector_ids}. Disponíveis: {sorted(available_detector_ids)}"
            )

        sim_time = sumo_client.step()
        traffic_light_state = sumo_client.get_traffic_light_state(tls_id)
        current_phase = int(traffic_light_state["phase"])
        if not 0 <= current_phase < expected_phase_count:
            raise RuntimeError(
                f"Fase inicial inválida: {current_phase}; esperado entre 0 e "
                f"{expected_phase_count - 1}."
            )

        detector_metrics = {
            detector_id: sumo_client.get_lane_area_detector_metrics(detector_id)
            for detector_id in detector_ids
        }
        for detector_id, metrics in detector_metrics.items():
            if metrics["vehicle_count"] < 0 or metrics["halting_count"] < 0:
                raise RuntimeError(f"Métricas negativas no detector '{detector_id}': {metrics}")
            if not 0.0 <= metrics["occupancy"] <= 100.0:
                raise RuntimeError(f"Ocupação inválida no detector '{detector_id}': {metrics}")

        sumo_client.set_traffic_light_phase(tls_id, target_phase)
        sumo_client.step()
        switched_state = sumo_client.get_traffic_light_state(tls_id)
        if int(switched_state["phase"]) != target_phase:
            raise RuntimeError(
                f"A troca de fase falhou: esperado {target_phase}, "
                f"recebido {switched_state['phase']}."
            )

        print(
            "SP TraCI validation passed: "
            f"sim_time={sim_time:.2f}, tls={tls_id}, "
            f"initial_phase={current_phase}, switched_phase={target_phase}, "
            f"detectors={len(detector_metrics)}."
        )
    finally:
        sumo_client.close()


if __name__ == "__main__":
    main()
