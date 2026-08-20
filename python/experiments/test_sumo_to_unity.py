"""Teste de integracao SUMO -> Python -> Unity com estado real via UDP."""

from __future__ import annotations

import argparse
from pathlib import Path
from time import sleep
from typing import Any

import yaml

from bridge import UnityBridge
from sumo import SumoClient, SumoStateExtractor


def load_config(config_path: Path) -> dict[str, Any]:
    """Carrega a configuracao YAML do projeto."""
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def parse_args(base_dir: Path) -> argparse.Namespace:
    """Permite testar perfis de cenário sem alterar o config.yaml padrão."""
    parser = argparse.ArgumentParser(description="Envia estado SUMO para Unity via UDP.")
    parser.add_argument(
        "--config",
        type=Path,
        default=base_dir / "config.yaml",
        help="Perfil YAML a ser executado.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=20,
        help="Quantidade de steps SUMO a transmitir.",
    )
    parser.add_argument(
        "--send-interval",
        type=float,
        default=0.05,
        help="Pausa em segundos entre mensagens UDP, para inspeção visual.",
    )
    parser.add_argument(
        "--receive-frames",
        action="store_true",
        help="Abre o listener TCP, recebe um JPEG Unity por step e o salva para depuração.",
    )
    parser.add_argument(
        "--frame-output-dir",
        type=Path,
        default=base_dir.parent / "results" / "frames" / "unity",
        help="Diretório para JPEGs recebidos quando --receive-frames está ativo.",
    )
    return parser.parse_args()


def main() -> None:
    """Extrai estado real do SUMO e envia para a Unity por alguns steps."""
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    if args.steps <= 0:
        raise ValueError("--steps deve ser maior que zero.")
    if args.send_interval < 0:
        raise ValueError("--send-interval não pode ser negativo.")

    config = load_config(args.config.resolve())

    sumo_client = SumoClient.from_config(config=config, base_dir=base_dir)
    unity_bridge = UnityBridge.from_config(config)
    state_extractor = SumoStateExtractor()
    tls_id = str(config["traffic_light"]["id"])

    try:
        if args.receive_frames:
            args.frame_output_dir.mkdir(parents=True, exist_ok=True)
            unity_bridge.start_frame_server()
            print(
                f"frame_listener host={unity_bridge.frame_host} port={unity_bridge.frame_port} "
                f"output={args.frame_output_dir}"
            )

        sumo_client.start()
        tls_ids = sumo_client.get_traffic_light_ids()
        if tls_id not in tls_ids:
            raise RuntimeError(
                f"Semaforo configurado '{tls_id}' nao encontrado no cenario. "
                f"Semaforos disponiveis: {tls_ids}"
            )

        for step in range(args.steps):
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
            if args.receive_frames:
                received_frame = unity_bridge.receive_frame()
                if received_frame is None:
                    print(f"frame_missing expected_step_id={state.step}")
                else:
                    jpeg, packet = received_frame
                    output_path = args.frame_output_dir / f"{packet.camera_id}_step_{packet.step_id:06d}.jpg"
                    output_path.write_bytes(jpeg)
                    match = packet.step_id == state.step
                    print(
                        f"frame_received step_id={packet.step_id} expected_step_id={state.step} "
                        f"match={match} bytes={packet.payload_size} output={output_path}"
                    )
            sleep(args.send_interval)
    finally:
        sumo_client.close()
        unity_bridge.close()


if __name__ == "__main__":
    main()
