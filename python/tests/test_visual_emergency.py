"""Testes da detecção visual de viaturas e da sua contabilidade no ambiente."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np
import yaml

from sumo.emergency import EmergencySettings, EmergencyTraffic
from vision.lane_features import LaneGeometry
from vision.visual_emergency import VisualEmergencyDetector, VisualEmergencySettings, emergency_sightings


CONFIG = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs" / "sp.yaml").read_text(encoding="utf-8"))


class DetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = VisualEmergencyDetector(["east", "south"], VisualEmergencySettings(confirm_frames=2, min_speed_mps=5.0, hold_margin_s=2.0))

    def test_request_only_after_consecutive_frames(self) -> None:
        self.assertEqual(self.detector.update({"east": [60.0]}, 1.0), [])
        self.assertEqual(self.detector.update({}, 2.0), [])
        self.assertEqual(self.detector.update({"east": [50.0]}, 3.0), [])
        requests = self.detector.update({"east": [40.0]}, 4.0)
        self.assertEqual([(r.vehicle_id, r.approach) for r in requests], [("vision_east_0", "east")])
        # 10 m/s medidos: 40 m → 4 s.
        self.assertAlmostEqual(requests[0].eta_s, 4.0)

    def test_request_coasts_until_eta_plus_margin_then_releases(self) -> None:
        self.detector.update({"east": [30.0]}, 1.0)
        self.detector.update({"east": [20.0]}, 2.0)  # 10 m/s, 2 s até a linha
        self.assertAlmostEqual(self.detector.update({}, 3.0)[0].eta_s, 1.0)
        self.assertEqual(self.detector.update({}, 4.0)[0].eta_s, 0.0)
        self.assertEqual(len(self.detector.update({}, 6.0)), 1)
        self.assertEqual(self.detector.update({}, 6.5), [])
        self.detector.update({"east": [70.0]}, 100.0)
        self.assertEqual(self.detector.update({"east": [60.0]}, 101.0)[0].vehicle_id, "vision_east_1")

    def test_stopped_vehicle_uses_minimum_speed_and_missing_frame_keeps_state(self) -> None:
        self.detector.update({"south": [25.0]}, 1.0)
        self.assertIsNone(self.detector.update(None, 2.0) or None)
        requests = self.detector.update({"south": [25.0]}, 3.0)
        self.assertAlmostEqual(requests[0].eta_s, 5.0)
        self.assertEqual(len(self.detector.update({"south": [25.0]}, 20.0)), 1)


class SightingTests(unittest.TestCase):
    def test_sightings_keep_only_emergency_class_and_add_roi_start(self) -> None:
        class Source:
            def observations(self, camera_id, objects, width, height):
                self.seen = (camera_id, [obj["bbox"] for obj in objects], width, height)
                return [SimpleNamespace(lane_id="lane_0", distance_m=12.0)]

        source = Source()
        result = SimpleNamespace(frame=np.zeros((480, 640, 3)), objects=[
            {"bbox": [0, 0, 1, 1], "class_id": 0}, {"bbox": [5, 5, 9, 9], "class_id": 1}])
        geometries = {("east", "lane_0"): LaneGeometry("east", "lane_0", "E2_0", 8.4, 68.4, 4.0)}
        self.assertEqual(emergency_sightings({"east": result}, source, geometries), {"east": [20.4]})
        self.assertEqual(source.seen, ("east", [[5, 5, 9, 9]], 640, 480))


class FakeClient:
    def __init__(self) -> None:
        self.added: list[str] = []

    def ensure_vehicle_type(self, *args) -> None:
        pass

    def add_vehicle(self, vehicle_id, from_edge, to_edge, type_id) -> None:
        self.added.append(vehicle_id)

    def get_vehicle_road_state(self, vehicle_id):
        return {"road_id": "E2", "lane_length": 70.0, "lane_position": 10.0, "speed": 10.0, "time_loss": 0.0, "waiting_time": 0.0}


class TrafficBookkeepingTests(unittest.TestCase):
    def test_visual_events_are_checked_against_vehicles_on_the_approach(self) -> None:
        settings = EmergencySettings(interval_s=500, jitter_s=0, first_after_s=0, routes={"east": (("E2", "E0"),)})
        traffic = EmergencyTraffic(settings, {"east": "E2"}, seed=1, start_s=0, end_s=100)
        client = FakeClient()
        from controller.preemption import EmergencyRequest

        traffic.step(client, 0.0)
        traffic.note_visual([EmergencyRequest("vision_east_0", "east", 3.0)], 0.0)
        self.assertFalse(traffic.present_on("east"))  # inserida neste step, ainda sem estado
        traffic.step(client, 1.0)
        self.assertTrue(traffic.present_on("east"))
        traffic.note_visual([EmergencyRequest("vision_east_1", "east", 3.0)], 1.0)
        summary = traffic.summary()["visual_detection"]
        self.assertEqual((summary["events"], summary["false_events"]), (2, 1))
        self.assertEqual(traffic.summary()["vehicles"][0]["first_visual_s"], 1.0)

    def test_config_with_visual_block_still_loads(self) -> None:
        EmergencySettings.from_config(CONFIG)
        self.assertEqual(VisualEmergencySettings.from_config(CONFIG).confirm_frames, 2)


if __name__ == "__main__":
    unittest.main()
