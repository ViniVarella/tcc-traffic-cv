"""Testes da telemetria do painel web (câmera × ground truth)."""

from __future__ import annotations

import json
import unittest

from dashboard.telemetry import approach_features, build_telemetry, ground_truth_metrics, signal_by_approach
from vision.lane_features import LaneFeatures


FEATURES = {
    ("south", "E3_0"): LaneFeatures(3, 2, 0.2, 1.0, 10.0),
    ("south", "E3_1"): LaneFeatures(1, 0, 0.1, 8.0, 0.0),
    ("east", "E2_0"): LaneFeatures(4, 4, 0.5, 0.0, 30.0),
    ("west", "E6_0"): LaneFeatures(0, 0, 0.0, None, 0.0),
}


class TelemetryTests(unittest.TestCase):
    def test_vision_is_summed_per_approach(self) -> None:
        totals = approach_features(FEATURES)
        self.assertEqual(totals["south"], {"vehicles": 4, "stopped": 2, "waiting_s": 10.0})
        self.assertEqual(totals["east"], {"vehicles": 4, "stopped": 4, "waiting_s": 30.0})
        self.assertEqual(totals["west"], {"vehicles": 0, "stopped": 0, "waiting_s": 0.0})
        self.assertIsNone(approach_features(None))  # step sem frames

    def test_ground_truth_mean_wait_is_per_stopped_vehicle(self) -> None:
        metrics = ground_truth_metrics({"halting_vehicles": 4, "waiting_time_s": 20.0, "pending_vehicles": 1})
        self.assertEqual(metrics["mean_wait_per_stopped_s"], 5.0)
        self.assertIsNone(metrics["pedestrian_waiting_s"])
        empty = ground_truth_metrics({"halting_vehicles": 0, "waiting_time_s": 0.0, "pending_vehicles": 0})
        self.assertEqual(empty["mean_wait_per_stopped_s"], 0.0)

    def test_signal_colors_follow_the_phase(self) -> None:
        self.assertEqual(signal_by_approach("EAST_WEST_GREEN"), {"south": "red", "east": "green", "west": "green"})
        self.assertEqual(signal_by_approach("SOUTH_YELLOW"), {"south": "yellow", "east": "red", "west": "red"})
        for phase in ("ALL_RED", "PEDESTRIAN_GREEN", "PEDESTRIAN_CLEARANCE"):
            self.assertEqual(set(signal_by_approach(phase).values()), {"red"})

    def test_telemetry_is_json_serializable(self) -> None:
        info = {"sim_time": 310.0, "phase": "SOUTH_GREEN", "phase_elapsed": 12.0, "reward": -0.2, "preempt_target": "SOUTH_GREEN",
                "lane_features": FEATURES, "decision": object(),
                "lane_metrics": {"halting_vehicles": 6, "waiting_time_s": 40.0, "pending_vehicles": 0, "pedestrian_waiting_s": 12.0}}
        telemetry = json.loads(json.dumps(build_telemetry(info)))
        self.assertEqual(telemetry["preempt_target"], "SOUTH_GREEN")
        self.assertEqual(telemetry["signals"]["south"], "green")
        self.assertEqual(telemetry["vision"]["east"]["stopped"], 4)
        self.assertEqual(telemetry["ground_truth"]["pedestrian_waiting_s"], 12.0)


if __name__ == "__main__":
    unittest.main()
