"""Executa o controle adaptativo: SUMO → Unity → visão → TraCI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import sleep
from typing import Any

import yaml

from bridge import FrameBundleCollector, UnityBridge
from controller import DqnAgent, DqnTrafficController
from controller.traffic_controller import TrafficController
from experiments.scenario_config import add_scenario_argument
from sumo import ExperimentMetricsCollector, SumoClient, SumoStateExtractor
from vision import ByteTrackVehicleTracker, VisualDebugger, VisualStateEncoder, YoloVehicleDetector, build_state_encoder
from vision.visual_pipeline import VisualPipeline, load_calibrations, parse_class_ids, queue_counts_by_camera


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa o controlador semafórico adaptativo baseado em visão.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=None, help="Seed do SUMO; substitui experiment.seed do perfil.")
    add_scenario_argument(parser)
    parser.add_argument("--send-interval", type=float, default=0.1)
    parser.add_argument("--camera-ids", default="south,east,west")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--classes", default="2,3,5,7")
    parser.add_argument("--confidence", type=float, default=0.15)
    parser.add_argument("--image-size", type=int, default=1280)
    parser.add_argument("--frame-rate", type=float, default=1.0)
    parser.add_argument("--track-match-threshold", type=float, default=0.6)
    parser.add_argument("--debug-output-dir", type=Path, default=base_dir.parent / "results" / "vision" / "live-visual-controller")
    parser.add_argument("--decision-output", type=Path, default=base_dir.parent / "results" / "logs" / "visual-controller-decisions.jsonl")
    parser.add_argument("--metrics-output", type=Path, default=base_dir.parent / "results" / "evaluation" / "visual-controller-metrics.json")
    parser.add_argument("--dqn-model", type=Path, default=None, help="Checkpoint .pt; ativa a política DQN em vez da heurística.")
    parser.add_argument("--dqn-device", default=None, help="Dispositivo PyTorch do DQN; padrão MPS/CPU automático.")
    return parser.parse_args()


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    if args.steps <= 0 or args.send_interval < 0 or args.frame_rate <= 0 or args.image_size <= 0:
        raise ValueError("--steps, --frame-rate e --image-size devem ser positivos; --send-interval não pode ser negativo.")
    if args.seed is not None and args.seed < 0:
        raise ValueError("--seed não pode ser negativa.")
    camera_ids = tuple(value.strip() for value in args.camera_ids.split(",") if value.strip())
    if not camera_ids:
        raise ValueError("Informe ao menos uma câmera em --camera-ids.")

    config = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    detector = YoloVehicleDetector(
        model_path=args.model,
        confidence_threshold=args.confidence,
        classes=parse_class_ids(args.classes),
        inference_size=args.image_size,
    )
    pipeline = VisualPipeline(
        load_calibrations(base_dir, camera_ids),
        detector,
        lambda: ByteTrackVehicleTracker(
            frame_rate=args.frame_rate,
            confidence_threshold=args.confidence,
            matching_threshold=args.track_match_threshold,
        ),
    )
    debuggers = {camera_id: VisualDebugger(str(args.debug_output_dir / camera_id)) for camera_id in camera_ids}
    dqn_agent: DqnAgent | None = None
    state_encoder: VisualStateEncoder | None = None
    if args.dqn_model is None:
        controller: Any = TrafficController(str(config["traffic_light"]["id"]), config)
    else:
        dqn_agent = DqnAgent.load(args.dqn_model, device=args.dqn_device)
        if dqn_agent.config.state_version != 1:
            raise ValueError(
                f"Checkpoint com estado v{dqn_agent.config.state_version}: este script só executa o v1 "
                "(contagens por step); políticas v2 decidem em pontos de decisão e usam o executor de episódios."
            )
        state_encoder = build_state_encoder(config, version=1)
        if dqn_agent.config.state_size != state_encoder.state_size:
            raise ValueError("Checkpoint DQN incompatível com o contrato visual v1.")
        controller = DqnTrafficController(str(config["traffic_light"]["id"]), config)
    sumo_client = SumoClient.from_config(config, base_dir, seed_override=args.seed, scenario_override=args.scenario)
    unity_bridge = UnityBridge.from_config(config)
    frame_collector = FrameBundleCollector(set(camera_ids))
    state_extractor = SumoStateExtractor()
    decisions: list[dict[str, Any]] = []
    metrics = ExperimentMetricsCollector()

    try:
        unity_bridge.start_frame_server()
        sumo_client.start()
        tls_id = str(config["traffic_light"]["id"])
        if tls_id not in sumo_client.get_traffic_light_ids():
            raise RuntimeError(f"Semáforo configurado não encontrado: {tls_id}")

        for step_id in range(args.steps):
            sim_time = sumo_client.step()
            metrics.observe(
                sim_time,
                sumo_client.get_simulation_events(),
                sumo_client.get_active_vehicle_metrics(),
            )
            state = state_extractor.build_simulation_state(
                step=step_id,
                sim_time=sim_time,
                vehicles=sumo_client.get_vehicle_state(),
                traffic_light_state=sumo_client.get_traffic_light_state(tls_id),
            )
            unity_bridge.send_state(state)
            policy_name = "dqn" if dqn_agent else "heuristic"
            try:
                bundle = frame_collector.collect_for_step(step_id, unity_bridge.receive_frame)
            except ConnectionError as error:
                # O Unity abre uma conexão TCP por frame. Um frame interrompido não
                # deve encerrar o controle: o próximo estado abre novas conexões.
                print(f"vision_connection_interrupted step_id={step_id} error={error}")
                bundle = None
            if bundle is None or not bundle.is_complete:
                if bundle is not None:
                    print(f"vision_missing step_id={step_id} cameras={','.join(bundle.missing_camera_ids)}")
                # Sem frames não há decisão, mas amarelo, all-red e verde máximo continuam valendo.
                decision = controller.update_without_vision(sim_time)
                controller.apply(sumo_client, decision)
                decisions.append({**decision, "step_id": step_id, "visual_counts": None, "policy": policy_name})
                sleep(args.send_interval)
                continue

            camera_results = pipeline.process_bundle(bundle)
            visual_counts = queue_counts_by_camera(camera_results)
            for camera_id, result in camera_results.items():
                annotated = debuggers[camera_id].annotate(
                    frame=result.frame,
                    detections=result.detections,
                    tracks=result.tracks,
                    roi_counts=result.raw_counts,
                    rois=result.rois,
                    queue_counts=result.queue_counts,
                    metadata={"camera": camera_id, "step": step_id, "tracker": "ByteTrack", "count_source": result.count_source},
                )
                debuggers[camera_id].save_frame(annotated, f"step_{step_id:06d}.jpg")

            if dqn_agent is None or state_encoder is None:
                decision = controller.update(sim_time, visual_counts)
            else:
                phase = controller.phase_manager.get_current_phase()
                state = state_encoder.encode(visual_counts, phase.phase_index, controller.phase_manager.elapsed(sim_time))
                dqn_action = dqn_agent.select_action(state, epsilon=0.0, explore=False)
                decision = controller.update(sim_time, dqn_action)
            controller.apply(sumo_client, decision)
            decisions.append({**decision, "step_id": step_id, "visual_counts": visual_counts, "policy": policy_name})
            demand_or_dqn_action = (
                f"dqn_action={decision['requested_action']}"
                if dqn_agent is not None
                else f"demand={decision['demand']}"
            )
            print(
                f"control_step step_id={step_id} phase={decision['phase_index']} action={decision['action']} "
                f"reason={decision['reason']} {demand_or_dqn_action}"
            )
            sleep(args.send_interval)
    finally:
        args.decision_output.parent.mkdir(parents=True, exist_ok=True)
        args.decision_output.write_text("".join(json.dumps(item) + "\n" for item in decisions), encoding="utf-8")
        args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_output.write_text(json.dumps({**metrics.summary(), "scenario": sumo_client.scenario, "seed": sumo_client.seed}, indent=2) + "\n", encoding="utf-8")
        sumo_client.close()
        unity_bridge.close()

    print(f"control_complete decisions={len(decisions)} output={args.decision_output} metrics={args.metrics_output}")


if __name__ == "__main__":
    main()
