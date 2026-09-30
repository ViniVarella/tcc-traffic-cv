"""Testes do observador Unity e da análise de domain gap, com ponte Unity falsa."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import unittest

import cv2
import numpy as np
import yaml

from bridge import FramePacket
from experiments.visual_observer import StepLogger, UnityVisualObserver
from sumo.lane_feature_source import TraciLaneFeatureSource
from vision.lane_feature_evaluation import action_agreement, feature_gap, ground_offset_estimate
from vision.lane_features import LaneFeatures, load_lane_geometries
from vision.visual_lane_features import VisualLaneFeatureSource
from vision.visual_pipeline import VisualPipeline, load_calibrations


PYTHON_DIR = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((PYTHON_DIR / "configs" / "sp.yaml").read_text(encoding="utf-8"))
CAMERAS = ("south", "east", "west")
_, JPEG = cv2.imencode(".jpg", np.zeros((36, 64, 3), dtype=np.uint8))


class FakeBridge:
    """Responde a cada estado com um JPEG por câmera do mesmo step (ou nada, se ``drop``)."""

    def __init__(self) -> None:
        self.sent_steps: list[int] = []
        self.queue: list[tuple[bytes, FramePacket]] = []
        self.drop_steps: set[int] = set()

    def send_state(self, state) -> None:
        self.sent_steps.append(state.step)
        if state.step not in self.drop_steps:
            self.queue = [(JPEG.tobytes(), FramePacket(state.step, state.sim_time, camera, "jpeg", len(JPEG))) for camera in CAMERAS]

    def receive_frame(self):
        return self.queue.pop(0) if self.queue else None


class FakeClient:
    def get_vehicle_state(self) -> list:
        return []

    def get_traffic_light_state(self, tls_id: str) -> dict:
        return {"id": tls_id, "phase": 0, "state": "GGGrrrrrrG"}

    def get_lane_vehicle_positions(self, lane_id: str) -> list:
        return [("veh", 60.0)] if lane_id == "E2_0" else []  # dentro da ROI leste (43,0–68,5 m)


class NoDetections:
    def detect(self, frame) -> list:
        return []


class Echo:
    def update(self, detections) -> list:
        return []


def _observer(bridge: FakeBridge, active_from_s: float = 0.0, shadow: bool = True) -> UnityVisualObserver:
    calibrations = load_calibrations(PYTHON_DIR, CAMERAS)
    geometries = load_lane_geometries(CONFIG)
    return UnityVisualObserver(
        bridge=bridge, pipeline=VisualPipeline(calibrations, NoDetections(), Echo), tls_id="tls",
        visual_source=VisualLaneFeatureSource(calibrations, geometries), send_interval_s=0.0, active_from_s=active_from_s,
        shadow_factory=(lambda seed: TraciLaneFeatureSource(geometries)) if shadow else None,
    )


class UnityVisualObserverTests(unittest.TestCase):
    def test_unity_is_skipped_before_activation_and_step_ids_never_restart(self) -> None:
        bridge = FakeBridge()
        observer = _observer(bridge, active_from_s=3.0)
        observe = observer.begin_episode(FakeClient(), seed=1)
        self.assertIsNone(observe(1.0))
        self.assertEqual(bridge.sent_steps, [])
        features = observe(3.0)
        self.assertEqual(len(features), 7)
        observe = observer.begin_episode(FakeClient(), seed=2)
        observe(3.0)
        self.assertEqual(bridge.sent_steps, [0, 1])

    def test_missing_frames_return_none_but_keep_the_oracle_record(self) -> None:
        bridge = FakeBridge()
        bridge.drop_steps = {0}
        observer = _observer(bridge)
        self.assertIsNone(observer.begin_episode(FakeClient(), seed=1)(1.0))
        self.assertEqual(observer.missing_frames, 1)
        record = observer.last_record
        self.assertIsNone(record["visual"])
        self.assertEqual(record["oracle"]["east/lane_0"]["vehicle_count"], 1)

    def test_long_missing_streak_prints_a_focus_warning(self) -> None:
        bridge = FakeBridge()
        bridge.drop_steps = set(range(12))
        observer = _observer(bridge, shadow=False)
        observe = observer.begin_episode(FakeClient(), seed=1)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for time in range(1, 14):
                observe(float(time))
        self.assertEqual(output.getvalue().count("vision_missing_streak"), 1)
        self.assertIn("Run In Background", output.getvalue())
        self.assertEqual((observer.missing_frames, observer.missing_streak), (12, 0))

    def test_step_logger_writes_only_matching_steps(self) -> None:
        observer = _observer(FakeBridge())
        observer.begin_episode(FakeClient(), seed=1)(1.0)
        handle = io.StringIO()
        logger = StepLogger(handle, observer, "dqn")
        info = {"sim_time": 1.0, "phase": "EAST_WEST_GREEN", "phase_index": 0, "phase_elapsed": 1.0, "requested_action": None,
                "reward": -0.1, "decision": {"action": "hold", "reason": "min_green_not_reached"}}
        logger(info)
        logger({**info, "sim_time": 2.0})
        lines = [json.loads(line) for line in handle.getvalue().splitlines()]
        self.assertEqual(len(lines), 1)
        self.assertEqual((lines[0]["policy"], lines[0]["decision_reason"], lines[0]["oracle"]["east/lane_0"]["vehicle_count"]),
                         ("dqn", "min_green_not_reached", 1))


def _record(visual_count: int, oracle_count: int, requested=None) -> dict:
    features = lambda count: {"east/lane_0": {"vehicle_count": count, "stopped_count": 0, "occupancy": 0.1 * count,
                                              "mean_speed_mps": None, "waiting_time_s": 0.0, "unknown_speed_count": 0}}
    return {"visual": features(visual_count), "oracle": features(oracle_count), "requested_action": requested,
            "phase_index": 0, "phase_elapsed": 12.0,
            "visual_observations": {"east": [["lane_0", 10.0, "1"], ["lane_0", 20.0, "2"]]},
            "oracle_observations": {"east": [["lane_0", 12.5, "a"], ["lane_0", 22.4, "b"], ["lane_0", 40.0, "c"]]}}


class LaneFeatureEvaluationTests(unittest.TestCase):
    def test_feature_gap_reports_bias_and_error(self) -> None:
        gap = feature_gap([_record(2, 3), _record(3, 3), {"visual": None, "oracle": {}}])
        count = gap["east/lane_0"]["vehicle_count"]
        self.assertEqual((count["samples"], count["mae"], count["bias"], count["exact_match_rate"]), (2, 0.5, -0.5, 0.5))
        self.assertNotIn("mean_speed_mps", gap["east/lane_0"])  # sem velocidade conhecida em ambos

    def test_ground_offset_pairs_nearest_observations(self) -> None:
        offset = ground_offset_estimate([_record(2, 3)])["east"]
        self.assertEqual(offset["matches"], 2)
        self.assertAlmostEqual(offset["median_offset_m"], 2.45)

    def test_action_agreement_compares_greedy_actions_at_decisions(self) -> None:
        class Encoder:
            def encode(self, features, phase_index, elapsed):
                return np.asarray([features[("east", "lane_0")].vehicle_count], dtype=np.float32)

        q_values = lambda state: np.asarray([state[0], 2.5])  # troca quando a contagem < 2,5
        result = action_agreement([_record(2, 3, requested=1), _record(3, 3, requested=0), _record(1, 1)], q_values, Encoder())
        self.assertEqual((result["decisions"], result["agreement_rate"]), (2, 0.5))


if __name__ == "__main__":
    unittest.main()
