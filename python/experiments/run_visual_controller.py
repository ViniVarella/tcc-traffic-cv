"""Executa o controle adaptativo: SUMO → Unity → visão → TraCI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import sleep
from typing import Any

import cv2
import numpy as np
import yaml

from bridge import FrameBundleCollector, UnityBridge
from controller.traffic_controller import TrafficController
from sumo import SumoClient, SumoStateExtractor
from vision import ByteTrackVehicleTracker, QueueEstimator, ROICounter, VisualDebugger, YoloVehicleDetector, load_camera_calibration
from vision.roi_counter import filter_detections_to_roi, select_counting_objects


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa o controlador semafórico adaptativo baseado em visão.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument("--steps", type=int, default=100)
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
    return parser.parse_args()


def _class_ids(raw: str) -> list[int]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    try:
        class_ids = [int(value) for value in values]
    except ValueError as error:
        raise ValueError(f"IDs de classe inválidos: {raw!r}") from error
    if not class_ids or any(value < 0 for value in class_ids):
        raise ValueError("--classes precisa conter IDs não negativos.")
    return class_ids


def _decode_jpeg(jpeg: bytes, camera_id: str, step_id: int) -> Any:
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"JPEG inválido: camera={camera_id} step={step_id}.")
    return frame


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    if args.steps <= 0 or args.send_interval < 0 or args.frame_rate <= 0 or args.image_size <= 0:
        raise ValueError("--steps, --frame-rate e --image-size devem ser positivos; --send-interval não pode ser negativo.")
    camera_ids = tuple(value.strip() for value in args.camera_ids.split(",") if value.strip())
    if not camera_ids:
        raise ValueError("Informe ao menos uma câmera em --camera-ids.")

    config = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    calibrations = {
        camera_id: load_camera_calibration(
            base_dir.parent / "unity" / "TrafficVisionUnity" / "Assets" / "Calibration" / f"{camera_id}-calibration.json",
            expected_camera_id=camera_id,
        )
        for camera_id in camera_ids
    }
    detector = YoloVehicleDetector(
        model_path=args.model,
        confidence_threshold=args.confidence,
        classes=_class_ids(args.classes),
        inference_size=args.image_size,
    )
    trackers = {
        camera_id: ByteTrackVehicleTracker(
            frame_rate=args.frame_rate,
            confidence_threshold=args.confidence,
            matching_threshold=args.track_match_threshold,
        )
        for camera_id in camera_ids
    }
    estimators = {camera_id: QueueEstimator() for camera_id in camera_ids}
    debuggers = {camera_id: VisualDebugger(str(args.debug_output_dir / camera_id)) for camera_id in camera_ids}
    controller = TrafficController(str(config["traffic_light"]["id"]), config)
    sumo_client = SumoClient.from_config(config, base_dir)
    unity_bridge = UnityBridge.from_config(config)
    frame_collector = FrameBundleCollector(set(camera_ids))
    state_extractor = SumoStateExtractor()
    decisions: list[dict[str, Any]] = []

    try:
        unity_bridge.start_frame_server()
        sumo_client.start()
        tls_id = str(config["traffic_light"]["id"])
        if tls_id not in sumo_client.get_traffic_light_ids():
            raise RuntimeError(f"Semáforo configurado não encontrado: {tls_id}")

        for step_id in range(args.steps):
            sim_time = sumo_client.step()
            state = state_extractor.build_simulation_state(
                step=step_id,
                sim_time=sim_time,
                vehicles=sumo_client.get_vehicle_state(),
                traffic_light_state=sumo_client.get_traffic_light_state(tls_id),
            )
            unity_bridge.send_state(state)
            try:
                bundle = frame_collector.collect_for_step(step_id, unity_bridge.receive_frame)
            except ConnectionError as error:
                # O Unity abre uma conexão TCP por frame. Um frame interrompido não
                # deve encerrar o controle: o próximo estado abre novas conexões.
                print(f"vision_connection_interrupted step_id={step_id} error={error}")
                sleep(args.send_interval)
                continue
            if not bundle.is_complete:
                print(f"vision_missing step_id={step_id} cameras={','.join(bundle.missing_camera_ids)}")
                sleep(args.send_interval)
                continue

            visual_counts: dict[str, dict[str, int]] = {}
            for camera_id, captured in bundle.frames.items():
                frame = _decode_jpeg(captured.jpeg, camera_id, step_id)
                calibration = calibrations[camera_id]
                approach_rois = calibration.pixel_rois(frame.shape[1], frame.shape[0])
                lane_rois = calibration.lane_pixel_rois(frame.shape[1], frame.shape[0])
                detections = filter_detections_to_roi(detector.detect(frame), approach_rois["approach"])
                tracks = trackers[camera_id].update(detections)
                objects, source = select_counting_objects(detections, tracks)
                raw_counts = ROICounter(lane_rois).count(objects)
                queue_counts = estimators[camera_id].update(raw_counts)
                visual_counts[camera_id] = queue_counts
                annotated = debuggers[camera_id].annotate(
                    frame=frame,
                    detections=detections,
                    tracks=tracks,
                    roi_counts=raw_counts,
                    rois=approach_rois,
                    queue_counts=queue_counts,
                    metadata={"camera": camera_id, "step": step_id, "tracker": "ByteTrack", "count_source": source},
                )
                debuggers[camera_id].save_frame(annotated, f"step_{step_id:06d}.jpg")

            decision = controller.update(sim_time, visual_counts)
            controller.apply(sumo_client, decision)
            decisions.append({**decision, "step_id": step_id, "visual_counts": visual_counts})
            print(
                f"control_step step_id={step_id} phase={decision['phase_index']} action={decision['action']} "
                f"reason={decision['reason']} demand={decision['demand']}"
            )
            sleep(args.send_interval)
    finally:
        args.decision_output.parent.mkdir(parents=True, exist_ok=True)
        args.decision_output.write_text("".join(json.dumps(item) + "\n" for item in decisions), encoding="utf-8")
        sumo_client.close()
        unity_bridge.close()

    print(f"control_complete decisions={len(decisions)} output={args.decision_output}")


if __name__ == "__main__":
    main()
