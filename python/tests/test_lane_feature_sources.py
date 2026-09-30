"""Testes das fontes de features por faixa (TraCI e visão) e da paridade entre elas."""

from __future__ import annotations

from dataclasses import dataclass
import unittest

import numpy as np

from sumo.lane_feature_source import ObservationNoise, TraciLaneFeatureSource
from vision.camera_calibration import CameraCalibration
from vision.lane_features import KinematicsParameters, LaneGeometry
from vision.lane_geometry import LaneHomography
from vision.visual_lane_features import VisualLaneFeatureSource


WIDTH, HEIGHT = 1280, 720
GEOMETRIES = {
    ("cam", "lane_0"): LaneGeometry("cam", "lane_0", "E9_0", roi_start_m=50.0, roi_end_m=75.0, width_m=3.2),
    ("cam", "lane_1"): LaneGeometry("cam", "lane_1", "E9_1", roi_start_m=50.0, roi_end_m=75.0, width_m=3.2),
}
# Duas faixas lado a lado em perspectiva (pontos fora de ordem de propósito).
CALIBRATION = CameraCalibration(
    camera_id="cam",
    capture_width=WIDTH,
    capture_height=HEIGHT,
    approach_roi=((0.1, 0.95), (0.9, 0.95), (0.6, 0.2), (0.4, 0.2)),
    lane_rois={
        "lane_0": ((0.5, 0.2), (0.4, 0.2), (0.1, 0.95), (0.5, 0.95)),
        "lane_1": ((0.5, 0.95), (0.9, 0.95), (0.6, 0.2), (0.5, 0.2)),
    },
)


class FakeLaneClient:
    def __init__(self) -> None:
        self.positions: dict[str, list[tuple[str, float]]] = {}

    def get_lane_vehicle_positions(self, lane_id: str) -> list[tuple[str, float]]:
        return list(self.positions.get(lane_id, []))


@dataclass
class FakeCameraResult:
    objects: list[dict]
    frame: np.ndarray


def _bbox_for(lane_id: str, distance_m: float) -> list[float]:
    """Gera a bbox cuja base central cai na faixa, à distância pedida da linha de retenção."""
    geometry = GEOMETRIES[("cam", lane_id)]
    homography = LaneHomography.from_quad(CALIBRATION.lane_rois[lane_id], geometry.length_m, geometry.width_m)
    u, v, scale = np.linalg.inv(homography.matrix) @ np.asarray([geometry.width_m / 2.0, distance_m, 1.0])
    x, y = u / scale * (WIDTH - 1), v / scale * (HEIGHT - 1)
    return [x - 15.0, y - 30.0, x + 15.0, y]


# Trajetórias (faixa, distância à linha de retenção) por step: "a" chega e para
# na fila; "b" passa direto e sai; "c" entra parado atrás de "a".
TRAJECTORY = [
    {"a": ("lane_0", 24.0), "b": ("lane_1", 20.0)},
    {"a": ("lane_0", 14.0), "b": ("lane_1", 8.0)},
    {"a": ("lane_0", 6.0), "b": ("lane_1", 0.5)},
    {"a": ("lane_0", 5.0), "c": ("lane_0", 18.0)},
    {"a": ("lane_0", 5.0), "c": ("lane_0", 12.0)},
    {"a": ("lane_0", 5.0), "c": ("lane_0", 12.0)},
    {"a": ("lane_0", 5.0), "c": ("lane_0", 12.0)},
    # A regressão de 3 pontos só zera a velocidade de "c" dois steps após parar.
    {"a": ("lane_0", 5.0), "c": ("lane_0", 12.0)},
]


class TraciLaneFeatureSourceTests(unittest.TestCase):
    def test_only_vehicles_inside_the_roi_interval_are_observed(self) -> None:
        client = FakeLaneClient()
        # Frente em 74 m (1 m da linha), 60 m (15 m), 40 m (antes da ROI) e 75,5 m (já no cruzamento).
        client.positions["E9_0"] = [("near", 74.0), ("mid", 60.0), ("upstream", 40.0), ("inside_junction", 75.5)]
        features = TraciLaneFeatureSource(GEOMETRIES).observe(client, 1.0)
        self.assertEqual(features[("cam", "lane_0")].vehicle_count, 2)
        self.assertAlmostEqual(features[("cam", "lane_0")].occupancy, 10.0 / 25.0)
        self.assertEqual(features[("cam", "lane_1")].vehicle_count, 0)

    def test_oracle_has_no_ghosts(self) -> None:
        source = TraciLaneFeatureSource(GEOMETRIES, KinematicsParameters(ghost_ttl_s=3.0))
        client = FakeLaneClient()
        client.positions["E9_0"] = [("v", 60.0)]
        for time in (1.0, 2.0, 3.0):
            source.observe(client, time)
        client.positions["E9_0"] = []
        self.assertEqual(source.observe(client, 4.0)[("cam", "lane_0")].vehicle_count, 0)

    def test_noise_is_reproducible_by_seed(self) -> None:
        client = FakeLaneClient()
        client.positions["E9_0"] = [(f"v{index}", 51.0 + 2.0 * index) for index in range(10)]
        noise = ObservationNoise(position_std_m=1.0, drop_probability=0.3)
        first = TraciLaneFeatureSource(GEOMETRIES, noise=noise, seed=5).observe(client, 1.0)
        second = TraciLaneFeatureSource(GEOMETRIES, noise=noise, seed=5).observe(client, 1.0)
        clean = TraciLaneFeatureSource(GEOMETRIES).observe(client, 1.0)
        self.assertEqual(first, second)
        self.assertLess(first[("cam", "lane_0")].vehicle_count, clean[("cam", "lane_0")].vehicle_count)
        with self.assertRaises(ValueError):
            ObservationNoise(drop_probability=1.0)


class VisualLaneFeatureSourceTests(unittest.TestCase):
    def test_objects_are_assigned_to_the_lane_containing_their_ground_point(self) -> None:
        source = VisualLaneFeatureSource({"cam": CALIBRATION}, GEOMETRIES)
        objects = [{"bbox": _bbox_for("lane_1", 10.0), "track_id": 3}, {"bbox": _bbox_for("lane_0", 20.0)}]
        observations = sorted(source.observations("cam", objects, WIDTH, HEIGHT), key=lambda item: item.lane_id)
        self.assertEqual([(item.lane_id, item.object_id) for item in observations], [("lane_0", None), ("lane_1", "3")])
        np.testing.assert_allclose([item.distance_m for item in observations], [20.0, 10.0], atol=1e-3)

    def test_objects_outside_every_lane_are_ignored_and_offset_is_applied(self) -> None:
        source = VisualLaneFeatureSource({"cam": CALIBRATION}, GEOMETRIES, ground_offset_m=-2.5)
        observations = source.observations("cam", [{"bbox": [0, 0, 10, 10]}, {"bbox": _bbox_for("lane_0", 10.0)}], WIDTH, HEIGHT)
        self.assertEqual(len(observations), 1)
        self.assertAlmostEqual(observations[0].distance_m, 7.5, places=3)

    def test_missing_lane_roi_is_rejected(self) -> None:
        geometries = {("cam", "lane_7"): LaneGeometry("cam", "lane_7", "E9_7", 0.0, 10.0, 3.2)}
        with self.assertRaises(ValueError):
            VisualLaneFeatureSource({"cam": CALIBRATION}, geometries)


class ParityTests(unittest.TestCase):
    def test_same_trajectory_gives_identical_features_through_camera_and_traci(self) -> None:
        parameters = KinematicsParameters()
        visual = VisualLaneFeatureSource({"cam": CALIBRATION}, GEOMETRIES, parameters)
        oracle = TraciLaneFeatureSource(GEOMETRIES, parameters)
        client = FakeLaneClient()
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        track_ids = {"a": 1, "b": 2, "c": 3}
        for step, vehicles in enumerate(TRAJECTORY, start=1):
            client.positions = {}
            objects = []
            for vehicle_id, (lane_id, distance) in vehicles.items():
                geometry = GEOMETRIES[("cam", lane_id)]
                client.positions.setdefault(geometry.sumo_lane, []).append((vehicle_id, geometry.roi_end_m - distance))
                objects.append({"bbox": _bbox_for(lane_id, distance), "track_id": track_ids[vehicle_id]})
            from_camera = visual.observe({"cam": FakeCameraResult(objects, frame)}, float(step))
            from_traci = oracle.observe(client, float(step))
            for key in GEOMETRIES:
                with self.subTest(step=step, lane=key):
                    camera_lane, traci_lane = from_camera[key], from_traci[key]
                    self.assertEqual(
                        (camera_lane.vehicle_count, camera_lane.stopped_count, camera_lane.unknown_speed_count),
                        (traci_lane.vehicle_count, traci_lane.stopped_count, traci_lane.unknown_speed_count),
                    )
                    self.assertAlmostEqual(camera_lane.occupancy, traci_lane.occupancy, places=4)
                    self.assertAlmostEqual(camera_lane.waiting_time_s, traci_lane.waiting_time_s, places=6)
                    if traci_lane.mean_speed_mps is None:
                        self.assertIsNone(camera_lane.mean_speed_mps)
                    else:
                        self.assertAlmostEqual(camera_lane.mean_speed_mps, traci_lane.mean_speed_mps, places=3)
        final = from_traci[("cam", "lane_0")]
        self.assertEqual((final.vehicle_count, final.stopped_count), (2, 2))
        self.assertGreater(final.waiting_time_s, 0.0)


if __name__ == "__main__":
    unittest.main()
