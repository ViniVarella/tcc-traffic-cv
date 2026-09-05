"""Treina e valida um DQN cujo estado é formado exclusivamente por contagens visuais."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from time import sleep
from typing import Any

import cv2
import numpy as np
import yaml

from bridge import FrameBundleCollector, UnityBridge
from controller import DqnAgent, DqnConfig, DqnTrafficController
from sumo import SumoClient, SumoStateExtractor
from vision import ByteTrackVehicleTracker, QueueEstimator, ROICounter, VisualStateEncoder, YoloVehicleDetector, load_camera_calibration
from vision.roi_counter import filter_detections_to_roi, select_counting_objects


@dataclass(frozen=True)
class EpisodeResult:
    split: str
    episode: int
    seed: int
    epsilon: float
    total_reward: float
    mean_reward: float
    mean_loss: float | None
    transitions: int
    missing_frames: int
    replay_size: int


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Treina DQN de controle semafórico a partir de visão Unity.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument("--episodes", type=int, default=50)
    parser.add_argument("--steps-per-episode", type=int, default=100)
    parser.add_argument("--seed-start", type=int, default=1, help="Primeira seed exclusiva de treino.")
    parser.add_argument("--validation-episodes", type=int, default=3, help="Número de seeds exclusivas de validação por rodada.")
    parser.add_argument("--validation-seed-start", type=int, default=1001, help="Primeira seed exclusiva de validação.")
    parser.add_argument("--validation-interval", type=int, default=5, help="Valida a cada N episódios de treino e no último.")
    parser.add_argument("--send-interval", type=float, default=0.1)
    parser.add_argument("--camera-ids", default="south,east,west")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--classes", default="0")
    parser.add_argument("--confidence", type=float, default=0.15)
    parser.add_argument("--image-size", type=int, default=1280)
    parser.add_argument("--frame-rate", type=float, default=1.0)
    parser.add_argument("--track-match-threshold", type=float, default=0.6)
    parser.add_argument("--device", default=None, help="Dispositivo PyTorch; padrão: MPS se disponível, senão CPU.")
    parser.add_argument("--checkpoint-output", type=Path, default=base_dir.parent / "results" / "models" / "visual-dqn-sp-last.pt")
    parser.add_argument("--best-checkpoint-output", type=Path, default=base_dir.parent / "results" / "models" / "visual-dqn-sp-best.pt")
    parser.add_argument("--training-log-output", type=Path, default=base_dir.parent / "results" / "logs" / "visual-dqn-training.jsonl")
    return parser.parse_args()


def _class_ids(raw: str) -> list[int]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    result = [int(value) for value in values]
    if not result or any(value < 0 for value in result):
        raise ValueError("--classes deve conter IDs não negativos.")
    return result


def _decode_jpeg(jpeg: bytes, camera_id: str, step_id: int) -> Any:
    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"JPEG inválido: camera={camera_id} step={step_id}.")
    return frame


def _visual_counts(bundle: Any, calibrations: dict[str, Any], detector: YoloVehicleDetector,
                   trackers: dict[str, ByteTrackVehicleTracker], estimators: dict[str, QueueEstimator],
                   step_id: int) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for camera_id, captured in bundle.frames.items():
        frame = _decode_jpeg(captured.jpeg, camera_id, step_id)
        calibration = calibrations[camera_id]
        approach = calibration.pixel_rois(frame.shape[1], frame.shape[0])["approach"]
        lanes = calibration.lane_pixel_rois(frame.shape[1], frame.shape[0])
        detections = filter_detections_to_roi(detector.detect(frame), approach)
        tracks = trackers[camera_id].update(detections)
        objects, _ = select_counting_objects(detections, tracks)
        result[camera_id] = estimators[camera_id].update(ROICounter(lanes).count(objects))
    return result


def _total_waiting(active_vehicles: dict[str, dict[str, float]]) -> float:
    return sum(float(metrics["accumulated_waiting_time"]) for metrics in active_vehicles.values())


def _run_episode(*, split: str, episode: int, seed: int, epsilon: float, train: bool,
                 args: argparse.Namespace, config: dict[str, Any], base_dir: Path,
                 camera_ids: tuple[str, ...], calibrations: dict[str, Any], detector: YoloVehicleDetector,
                 encoder: VisualStateEncoder, agent: DqnAgent, unity_bridge: UnityBridge,
                 global_step: int) -> tuple[EpisodeResult, int]:
    sumo_client = SumoClient.from_config(config, base_dir, seed_override=seed)
    controller = DqnTrafficController(str(config["traffic_light"]["id"]), config)
    collector = FrameBundleCollector(set(camera_ids))
    trackers = {camera_id: ByteTrackVehicleTracker(args.frame_rate, args.confidence, args.track_match_threshold) for camera_id in camera_ids}
    estimators = {camera_id: QueueEstimator() for camera_id in camera_ids}
    state_extractor = SumoStateExtractor()
    previous_state: np.ndarray | None = None
    previous_action = DqnTrafficController.KEEP
    previous_waiting = 0.0
    rewards: list[float] = []
    losses: list[float] = []
    missing_frames = 0
    try:
        sumo_client.start()
        tls_id = str(config["traffic_light"]["id"])
        for _ in range(args.steps_per_episode):
            sim_time = sumo_client.step()
            active = sumo_client.get_active_vehicle_metrics()
            state_message = state_extractor.build_simulation_state(
                step=global_step, sim_time=sim_time, vehicles=sumo_client.get_vehicle_state(),
                traffic_light_state=sumo_client.get_traffic_light_state(tls_id),
            )
            unity_bridge.send_state(state_message)
            try:
                bundle = collector.collect_for_step(global_step, unity_bridge.receive_frame)
            except ConnectionError:
                missing_frames += 1
                global_step += 1
                sleep(args.send_interval)
                continue
            if not bundle.is_complete:
                missing_frames += 1
                global_step += 1
                sleep(args.send_interval)
                continue
            counts = _visual_counts(bundle, calibrations, detector, trackers, estimators, global_step)
            phase = controller.phase_manager.get_current_phase()
            state = encoder.encode(counts, phase.phase_index, controller.phase_manager.elapsed(sim_time))
            current_waiting = _total_waiting(active)
            if previous_state is not None:
                reward = previous_waiting - current_waiting - 0.05 * sum(sum(lanes.values()) for lanes in counts.values())
                rewards.append(reward)
                if train:
                    agent.remember(previous_state, previous_action, reward, state, False)
                    loss = agent.train_step()
                    if loss is not None:
                        losses.append(loss)
            action = agent.select_action(state, epsilon=epsilon, explore=train)
            decision = controller.update(sim_time, action)
            controller.apply(sumo_client, decision)
            previous_state, previous_action, previous_waiting = state, action, current_waiting
            global_step += 1
            sleep(args.send_interval)
    finally:
        sumo_client.close()
    total_reward = float(sum(rewards))
    return EpisodeResult(split, episode, seed, epsilon, total_reward,
                         0.0 if not rewards else float(np.mean(rewards)),
                         None if not losses else float(np.mean(losses)), len(rewards), missing_frames,
                         len(agent.replay)), global_step


def _validation_score(results: list[EpisodeResult], steps_per_episode: int) -> float | None:
    """Recompensa média por step; não seleciona modelo se a visão falhou na rodada."""
    minimum_transitions = max(1, steps_per_episode // 2)
    valid = [result for result in results if result.transitions >= minimum_transitions]
    if not valid:
        return None
    return float(np.mean([result.total_reward / steps_per_episode for result in valid]))


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    if min(args.episodes, args.steps_per_episode, args.validation_episodes, args.validation_interval) <= 0:
        raise ValueError("--episodes, --steps-per-episode, --validation-episodes e --validation-interval devem ser positivos.")
    if args.seed_start < 0 or args.validation_seed_start < 0:
        raise ValueError("As seeds devem ser não negativas.")
    training_seeds = set(range(args.seed_start, args.seed_start + args.episodes))
    validation_seeds = set(range(args.validation_seed_start, args.validation_seed_start + args.validation_episodes))
    if training_seeds & validation_seeds:
        raise ValueError("As seeds de treino e validação devem ser disjuntas.")
    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    camera_ids = tuple(item.strip() for item in args.camera_ids.split(",") if item.strip())
    if not camera_ids:
        raise ValueError("Informe ao menos uma câmera em --camera-ids.")
    dqn_config = config["dqn"]
    encoder = VisualStateEncoder(float(dqn_config["max_lane_count"]), int(config["traffic_light"]["phase_count"]),
                                 float(config["traffic_control"]["max_green_seconds"]))
    if encoder.state_size != int(dqn_config["state_size"]):
        raise ValueError("dqn.state_size diverge do contrato de estado visual.")
    agent = DqnAgent(DqnConfig(
        state_size=encoder.state_size, hidden_size=int(dqn_config["hidden_size"]), gamma=float(dqn_config["gamma"]),
        learning_rate=float(dqn_config["learning_rate"]), batch_size=int(dqn_config["batch_size"]),
        replay_capacity=int(dqn_config["replay_capacity"]), min_replay_size=int(dqn_config["min_replay_size"]),
        target_update_interval=int(dqn_config["target_update_interval"]),
    ), device=args.device, seed=args.seed_start)
    calibrations = {camera_id: load_camera_calibration(
        base_dir.parent / "unity" / "TrafficVisionUnity" / "Assets" / "Calibration" / f"{camera_id}-calibration.json",
        expected_camera_id=camera_id) for camera_id in camera_ids}
    detector = YoloVehicleDetector(args.model, args.confidence, _class_ids(args.classes), args.image_size)
    unity_bridge = UnityBridge.from_config(config)
    logs: list[dict[str, Any]] = []
    best_validation_score: float | None = None
    best_training_episode: int | None = None
    global_step = 0
    try:
        unity_bridge.start_frame_server()
        for episode in range(args.episodes):
            epsilon = max(float(dqn_config["epsilon_min"]), float(dqn_config["epsilon_start"]) * float(dqn_config["epsilon_decay"]) ** episode)
            result, global_step = _run_episode(
                split="train", episode=episode, seed=args.seed_start + episode, epsilon=epsilon, train=True,
                args=args, config=config, base_dir=base_dir, camera_ids=camera_ids, calibrations=calibrations,
                detector=detector, encoder=encoder, agent=agent, unity_bridge=unity_bridge, global_step=global_step)
            logs.append(asdict(result))
            agent.save(args.checkpoint_output, {"kind": "latest", "training_episode": episode, "training_seed": result.seed})
            print(f"dqn_episode_complete split=train episode={episode} seed={result.seed} reward={result.mean_reward:.3f} transitions={result.transitions} missing_frames={result.missing_frames}")
            should_validate = (episode + 1) % args.validation_interval == 0 or episode + 1 == args.episodes
            if not should_validate:
                continue
            validation_results: list[EpisodeResult] = []
            for validation_episode in range(args.validation_episodes):
                validation_result, global_step = _run_episode(
                    split="validation", episode=episode, seed=args.validation_seed_start + validation_episode,
                    epsilon=0.0, train=False, args=args, config=config, base_dir=base_dir, camera_ids=camera_ids,
                    calibrations=calibrations, detector=detector, encoder=encoder, agent=agent,
                    unity_bridge=unity_bridge, global_step=global_step)
                validation_results.append(validation_result)
                logs.append(asdict(validation_result))
            validation_score = _validation_score(validation_results, args.steps_per_episode)
            score_text = "unavailable" if validation_score is None else f"{validation_score:.4f}"
            print(f"dqn_validation_complete after_episode={episode} score={score_text} seeds={args.validation_seed_start}-{args.validation_seed_start + args.validation_episodes - 1}")
            if validation_score is not None and (best_validation_score is None or validation_score > best_validation_score):
                best_validation_score = validation_score
                best_training_episode = episode
                agent.save(args.best_checkpoint_output, {
                    "kind": "best_validation", "validation_score": validation_score, "training_episode": episode,
                    "training_seed": result.seed, "validation_seeds": sorted(validation_seeds),
                })
                print(f"dqn_best_checkpoint_updated episode={episode} validation_score={validation_score:.4f} checkpoint={args.best_checkpoint_output}")
    finally:
        args.training_log_output.parent.mkdir(parents=True, exist_ok=True)
        args.training_log_output.write_text("".join(json.dumps(item) + "\n" for item in logs), encoding="utf-8")
        unity_bridge.close()
    best_path = args.best_checkpoint_output if best_validation_score is not None else "unavailable"
    print(f"dqn_training_complete episodes={args.episodes} latest_checkpoint={args.checkpoint_output} best_checkpoint={best_path} best_training_episode={best_training_episode} best_validation_score={best_validation_score} log={args.training_log_output}")


if __name__ == "__main__":
    main()
