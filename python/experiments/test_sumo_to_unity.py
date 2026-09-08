"""Teste de integracao SUMO -> Python -> Unity com estado real via UDP."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from time import sleep
from typing import Any

import yaml

from bridge import FrameBundleCollector, UnityBridge
from sumo import GroundTruthCollector, SumoClient, SumoStateExtractor


def load_config(config_path: Path) -> dict[str, Any]:
    """Carrega a configuracao YAML do projeto."""
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def camera_output_path(output_dir: Path, camera_id: str) -> Path:
    """Returns a safe, direct subdirectory for a camera's captured frames."""
    if not camera_id or Path(camera_id).name != camera_id or camera_id in {".", ".."}:
        raise ValueError(f"ID de câmera inválido para saída de frames: {camera_id!r}")
    return output_dir / camera_id


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
        help="Diretório raiz para JPEGs recebidos; cada câmera é salva em sua própria subpasta.",
    )
    parser.add_argument(
        "--expected-cameras",
        default="south",
        help="IDs de câmera separados por vírgula esperados por step com --receive-frames.",
    )
    parser.add_argument(
        "--ground-truth-output",
        type=Path,
        help=(
            "JSONL para snapshots E2 por step. Use apenas para avaliação offline; "
            "os dados não são enviados ao Unity nem ao controlador."
        ),
    )
    parser.add_argument(
        "--vehicle-labels-output-dir",
        type=Path,
        help=(
            "Diretório para os rótulos 2D por veículo enviados pela Unity. "
            "Use com --receive-frames para preparar o dataset sintético; não afeta a inferência."
        ),
    )
    parser.add_argument(
        "--instance-masks-output-dir",
        type=Path,
        help=(
            "Diretório para PNGs de máscara por instância enviados pela Unity. "
            "Requer --receive-frames e é usado para gerar rótulos YOLO precisos."
        ),
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
    expected_cameras = {camera_id.strip() for camera_id in args.expected_cameras.split(",") if camera_id.strip()}
    if args.receive_frames and not expected_cameras:
        raise ValueError("--expected-cameras precisa conter ao menos uma câmera quando --receive-frames está ativo.")
    if args.vehicle_labels_output_dir is not None and not args.receive_frames:
        raise ValueError("--vehicle-labels-output-dir requer --receive-frames.")
    if args.instance_masks_output_dir is not None and not args.receive_frames:
        raise ValueError("--instance-masks-output-dir requer --receive-frames.")
    camera_output_dirs = {
        camera_id: camera_output_path(args.frame_output_dir, camera_id)
        for camera_id in expected_cameras
    }

    config = load_config(args.config.resolve())

    sumo_client = SumoClient.from_config(config=config, base_dir=base_dir)
    unity_bridge = UnityBridge.from_config(config)
    state_extractor = SumoStateExtractor()
    tls_id = str(config["traffic_light"]["id"])
    detector_ids = [str(detector_id) for detector_id in config.get("detectors", {}).get("ids", [])]
    ground_truth_collector = GroundTruthCollector(tls_id)
    frame_collector = FrameBundleCollector(expected_cameras) if args.receive_frames else None

    try:
        if args.receive_frames:
            args.frame_output_dir.mkdir(parents=True, exist_ok=True)
            for camera_id, output_dir in camera_output_dirs.items():
                if output_dir.is_symlink() or output_dir.is_file():
                    output_dir.unlink()
                elif output_dir.exists():
                    shutil.rmtree(output_dir)
                output_dir.mkdir()
                print(f"frame_output_reset camera={camera_id} output={output_dir}")
            if args.vehicle_labels_output_dir is not None:
                if args.vehicle_labels_output_dir.is_symlink() or args.vehicle_labels_output_dir.is_file():
                    args.vehicle_labels_output_dir.unlink()
                elif args.vehicle_labels_output_dir.exists():
                    shutil.rmtree(args.vehicle_labels_output_dir)
                args.vehicle_labels_output_dir.mkdir(parents=True)
                for camera_id in expected_cameras:
                    (args.vehicle_labels_output_dir / camera_id).mkdir()
                print(f"vehicle_labels_output_reset output={args.vehicle_labels_output_dir}")
            if args.instance_masks_output_dir is not None:
                if args.instance_masks_output_dir.is_symlink() or args.instance_masks_output_dir.is_file():
                    args.instance_masks_output_dir.unlink()
                elif args.instance_masks_output_dir.exists():
                    shutil.rmtree(args.instance_masks_output_dir)
                args.instance_masks_output_dir.mkdir(parents=True)
                for camera_id in expected_cameras:
                    (args.instance_masks_output_dir / camera_id).mkdir()
                print(f"instance_masks_output_reset output={args.instance_masks_output_dir}")
            unity_bridge.start_frame_server()
            print(
                f"frame_listener host={unity_bridge.frame_host} port={unity_bridge.frame_port} "
                f"output={args.frame_output_dir}"
            )

        if args.ground_truth_output is not None:
            args.ground_truth_output.parent.mkdir(parents=True, exist_ok=True)
            args.ground_truth_output.write_text("", encoding="utf-8")
            print(f"ground_truth_output_reset output={args.ground_truth_output}")

        sumo_client.start()
        tls_ids = sumo_client.get_traffic_light_ids()
        if tls_id not in tls_ids:
            raise RuntimeError(
                f"Semaforo configurado '{tls_id}' nao encontrado no cenario. "
                f"Semaforos disponiveis: {tls_ids}"
            )
        available_detector_ids = set(sumo_client.get_lane_area_detector_ids())
        missing_detector_ids = sorted(set(detector_ids) - available_detector_ids)
        if missing_detector_ids:
            raise RuntimeError(
                "Detectores E2 configurados não encontrados no cenário: "
                f"{missing_detector_ids}. Disponíveis: {sorted(available_detector_ids)}"
            )

        for step in range(args.steps):
            sim_time = sumo_client.step()
            vehicles = sumo_client.get_vehicle_state()
            traffic_light_state = sumo_client.get_traffic_light_state(tls_id)
            if args.ground_truth_output is not None:
                detector_metrics = {
                    detector_id: sumo_client.get_lane_area_detector_metrics(detector_id)
                    for detector_id in detector_ids
                }
                detector_snapshot = ground_truth_collector.collect_detector_snapshot(
                    step_id=step,
                    sim_time=sim_time,
                    detector_metrics=detector_metrics,
                )
                with args.ground_truth_output.open("a", encoding="utf-8") as ground_truth_file:
                    ground_truth_file.write(json.dumps(detector_snapshot) + "\n")
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
                assert frame_collector is not None
                frame_bundle = frame_collector.collect_for_step(
                    step_id=state.step,
                    receive_frame=unity_bridge.receive_frame,
                )
                for camera_id, captured_frame in sorted(frame_bundle.frames.items()):
                    packet = captured_frame.packet
                    camera_output_dir = camera_output_dirs[camera_id]
                    output_path = camera_output_dir / f"step_{packet.step_id:06d}.jpg"
                    output_path.write_bytes(captured_frame.jpeg)
                    if args.vehicle_labels_output_dir is not None:
                        labels_path = args.vehicle_labels_output_dir / camera_id / f"step_{packet.step_id:06d}.json"
                        labels_path.write_text(
                            json.dumps(
                                {
                                    "step_id": packet.step_id,
                                    "sim_time": packet.sim_time,
                                    "camera_id": packet.camera_id,
                                    "vehicles": packet.ground_truth_vehicles,
                                },
                                indent=2,
                            ) + "\n",
                            encoding="utf-8",
                        )
                    if args.instance_masks_output_dir is not None:
                        if captured_frame.packet.mask_png is None:
                            raise RuntimeError(
                                f"Unity did not return an instance mask for camera={camera_id} step={packet.step_id}."
                            )
                        mask_path = args.instance_masks_output_dir / camera_id / f"step_{packet.step_id:06d}.png"
                        mask_path.write_bytes(captured_frame.packet.mask_png)
                    print(
                        f"frame_received step_id={packet.step_id} expected_step_id={state.step} "
                        f"match=True bytes={packet.payload_size} output={output_path}"
                    )

                if frame_bundle.missing_camera_ids:
                    print(
                        f"frame_missing expected_step_id={state.step} "
                        f"cameras={','.join(frame_bundle.missing_camera_ids)}"
                    )
                else:
                    print(f"frames_complete step_id={state.step} cameras={','.join(sorted(frame_bundle.frames))}")
            sleep(args.send_interval)
    finally:
        sumo_client.close()
        unity_bridge.close()


if __name__ == "__main__":
    main()
