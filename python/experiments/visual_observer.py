"""Observador do executor de episódios com frames da Unity (percepção visual).

Em cada step: envia o estado SUMO à Unity, reúne os frames das câmeras do mesmo
``step_id``, roda o pipeline visual e devolve as ``LaneFeatures`` estimadas.
Opcionalmente calcula o oráculo TraCI em paralelo, só para registro (domain
gap) — ele nunca decide. Antes de ``active_from_s`` a Unity não é usada, o que
permite aquecer o SUMO rápido e ligar a visão alguns segundos antes do controle
para inicializar os trackers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
import json
from time import sleep
from typing import Any

from bridge import FrameBundleCollector
from controller.preemption import EmergencyRequest
from sumo import SumoStateExtractor
from sumo.lane_feature_source import TraciLaneFeatureSource
from vision.lane_features import LaneFeatures, LaneObservation
from vision.visual_emergency import VisualEmergencyDetector, VisualEmergencySettings, emergency_sightings
from vision.visual_lane_features import VisualLaneFeatureSource
from vision.visual_pipeline import VisualPipeline


MISSING_STREAK_WARNING = 10


def features_record(features: dict[tuple[str, str], LaneFeatures] | None) -> dict[str, Any] | None:
    return None if features is None else {f"{camera}/{lane}": asdict(values) for (camera, lane), values in features.items()}


def observations_record(observations: dict[str, list[LaneObservation]]) -> dict[str, list[list[Any]]]:
    return {camera: [[item.lane_id, round(item.distance_m, 3), item.object_id] for item in items] for camera, items in observations.items()}


class UnityVisualObserver:
    def __init__(
        self,
        *,
        bridge: Any,
        pipeline: VisualPipeline,
        visual_source: VisualLaneFeatureSource,
        tls_id: str,
        send_interval_s: float,
        active_from_s: float = 0.0,
        shadow_factory: Callable[[int], TraciLaneFeatureSource] | None = None,
        emergency_detector: VisualEmergencyDetector | None = None,
    ) -> None:
        self.bridge = bridge
        self.pipeline = pipeline
        self.visual_source = visual_source
        self.tls_id = tls_id
        self.send_interval_s = float(send_interval_s)
        self.active_from_s = float(active_from_s)
        self.shadow_factory = shadow_factory
        self.emergency_detector = emergency_detector
        self._emergency: tuple[float, list[EmergencyRequest]] | None = None
        self.state_extractor = SumoStateExtractor()
        # step_id cresce entre episódios para que frames atrasados de um episódio
        # anterior nunca sejam associados a um step novo.
        self.next_step_id = 0
        self.last_record: dict[str, Any] | None = None
        self.missing_frames = 0
        self.missing_streak = 0

    def begin_episode(self, client: Any, seed: int) -> Callable[[float], dict[tuple[str, str], LaneFeatures] | None]:
        self.pipeline.reset()
        self.visual_source.reset()
        if self.emergency_detector is not None:
            self.emergency_detector.reset()
        self._emergency = None
        shadow = None if self.shadow_factory is None else self.shadow_factory(seed)
        collector = FrameBundleCollector(set(self.pipeline.camera_ids))
        self.last_record = None

        def observe(sim_time: float) -> dict[tuple[str, str], LaneFeatures] | None:
            if sim_time < self.active_from_s:
                return None
            step_id = self.next_step_id
            self.next_step_id += 1
            self.bridge.send_state(self.state_extractor.build_simulation_state(
                step=step_id, sim_time=sim_time, vehicles=client.get_vehicle_state(),
                traffic_light_state=client.get_traffic_light_state(self.tls_id),
                pedestrians=client.get_pedestrian_state(),
            ))
            try:
                bundle = collector.collect_for_step(step_id, self.bridge.receive_frame)
            except ConnectionError:
                bundle = None
            sleep(self.send_interval_s)
            oracle = None if shadow is None else shadow.observe(client, sim_time)
            if bundle is None or not bundle.is_complete:
                self.missing_frames += 1
                self.missing_streak += 1
                if self.missing_streak % MISSING_STREAK_WARNING == 0:
                    # A Unity sem foco deixa de renderizar se "Run In Background" estiver desligado.
                    print(f"vision_missing_streak steps={self.missing_streak} step_id={step_id} "
                          "aviso=sem frames da Unity; confira Play Mode e Run In Background (ou mantenha a Unity em foco)",
                          flush=True)
                features = None
                visual_observations: dict[str, list[LaneObservation]] = {}
                sightings = None
            else:
                self.missing_streak = 0
                results = self.pipeline.process_bundle(bundle)
                features = self.visual_source.observe(results, sim_time)
                visual_observations = self.visual_source.last_observations
                sightings = emergency_sightings(results, self.visual_source, self.visual_source.geometries)
            emergency: list[EmergencyRequest] = []
            if self.emergency_detector is not None:
                emergency = self.emergency_detector.update(sightings, sim_time)
                self._emergency = (sim_time, emergency)
            self.last_record = {
                "step_id": step_id, "sim_time": sim_time, "seed": seed,
                "visual": features_record(features), "oracle": features_record(oracle),
                "visual_observations": observations_record(visual_observations),
                "oracle_observations": None if shadow is None else observations_record(shadow.last_observations),
                "emergency_sightings": sightings, "emergency_requests": [asdict(request) for request in emergency],
            }
            return features

        return observe

    def emergency_requests(self, sim_time: float) -> list[EmergencyRequest]:
        """Pedidos visuais de preempção do step atual (vazio antes da visão ligar)."""
        if self._emergency is None or self._emergency[0] != sim_time:
            return []
        return self._emergency[1]


def add_vision_arguments(parser: Any) -> None:
    """Argumentos de câmera/YOLO/ByteTrack compartilhados pelos scripts visuais v2."""
    parser.add_argument("--camera-ids", default="south,east,west")
    parser.add_argument("--model", default="../runs/results/models/yolov8n-unity-cam60-2cls-960/weights/best.pt")
    parser.add_argument("--classes", default="0,1",
                        help="Detector ajustado: 0 vehicle, 1 emergency (as duas entram nas contagens). "
                             "Pesos de uma classe (run-002): 0; pesos COCO: 2,3,5,7.")
    parser.add_argument("--confidence", type=float, default=0.15)
    parser.add_argument("--image-size", type=int, default=960, help="Mesmo tamanho do treino do detector de duas classes.")
    parser.add_argument("--frame-rate", type=float, default=1.0)
    parser.add_argument("--track-match-threshold", type=float, default=0.6)
    parser.add_argument("--send-interval", type=float, default=0.1)
    parser.add_argument("--prime-seconds", type=float, default=10.0,
                        help="Liga a Unity este tanto antes do fim do aquecimento para inicializar os trackers.")
    parser.add_argument("--ground-offset", type=float, default=None,
                        help="Sobrescreve lane_state.visual_ground_offset_m (m somados à distância visual).")
    parser.add_argument("--no-oracle-shadow", action="store_true", help="Não registra o oráculo TraCI em paralelo.")


def build_unity_observer(config: dict[str, Any], base_dir: Any, args: Any, environment: Any, bridge: Any) -> UnityVisualObserver:
    """Monta YOLO + ByteTrack + pipeline + fonte visual a partir dos argumentos."""
    from vision import ByteTrackVehicleTracker, YoloVehicleDetector
    from vision.visual_pipeline import load_calibrations, parse_class_ids

    camera_ids = tuple(item.strip() for item in args.camera_ids.split(",") if item.strip())
    calibrations = load_calibrations(base_dir, camera_ids)
    detector = YoloVehicleDetector(args.model, args.confidence, parse_class_ids(args.classes), args.image_size)
    pipeline = VisualPipeline(calibrations, detector,
                              lambda: ByteTrackVehicleTracker(args.frame_rate, args.confidence, args.track_match_threshold))
    offset = args.ground_offset if args.ground_offset is not None else float(config.get("lane_state", {}).get("visual_ground_offset_m", 0.0))
    visual_source = VisualLaneFeatureSource(calibrations, environment.geometries, environment.parameters, ground_offset_m=offset)
    return UnityVisualObserver(
        bridge=bridge, pipeline=pipeline, visual_source=visual_source, tls_id=environment.tls_id,
        send_interval_s=args.send_interval, active_from_s=max(0.0, environment.settings.warmup_s - args.prime_seconds),
        shadow_factory=None if args.no_oracle_shadow else environment.oracle_source,
        emergency_detector=VisualEmergencyDetector(sorted(calibrations), VisualEmergencySettings.from_config(config)),
    )


class StepLogger:
    """Grava uma linha JSONL por step controlado: features visuais, oráculo e decisão."""

    def __init__(self, handle: Any, observer: UnityVisualObserver, policy: str) -> None:
        self.handle = handle
        self.observer = observer
        self.policy = policy

    def __call__(self, info: dict[str, Any]) -> None:
        record = self.observer.last_record
        if record is None or record["sim_time"] != info["sim_time"]:
            return
        decision = info["decision"]
        line = {
            **record, "policy": self.policy, "phase": info["phase"], "phase_index": info["phase_index"],
            "phase_elapsed": info["phase_elapsed"], "requested_action": info["requested_action"],
            "decision_action": decision["action"], "decision_reason": decision["reason"], "reward": info["reward"],
        }
        self.handle.write(json.dumps(line) + "\n")
