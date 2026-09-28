"""Testes da ordenação das ROIs de faixa e da homografia métrica."""

from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np
import yaml

from experiments.check_lane_geometry import image_point_to_ground, measure_lane_rois
from vision.camera_calibration import load_camera_calibration
from vision.lane_geometry import LaneHomography, bbox_ground_point, order_lane_quad


REPO_DIR = Path(__file__).resolve().parents[2]
CALIBRATION_DIR = REPO_DIR / "unity" / "TrafficVisionUnity" / "Assets" / "Calibration"
# Trapézio em perspectiva: borda próxima larga embaixo, borda distante estreita em cima.
TRAPEZOID = [(0.2, 0.9), (0.6, 0.9), (0.45, 0.2), (0.35, 0.2)]


def _real_lane_quads() -> dict[str, tuple]:
    quads = {}
    for camera_id in ("south", "east", "west"):
        calibration = load_camera_calibration(CALIBRATION_DIR / f"{camera_id}-calibration.json", camera_id)
        for lane_id, points in calibration.lane_rois.items():
            quads[f"{camera_id}/{lane_id}"] = points
    return quads


class OrderLaneQuadTests(unittest.TestCase):
    def test_orders_near_edge_first_and_left_to_right(self) -> None:
        self.assertEqual(order_lane_quad(TRAPEZOID), ((0.2, 0.9), (0.6, 0.9), (0.45, 0.2), (0.35, 0.2)))

    def test_result_does_not_depend_on_rotation_or_direction_of_points(self) -> None:
        expected = order_lane_quad(TRAPEZOID)
        for shift in range(4):
            rotated = TRAPEZOID[shift:] + TRAPEZOID[:shift]
            self.assertEqual(order_lane_quad(rotated), expected)
            self.assertEqual(order_lane_quad(list(reversed(rotated))), expected)

    def test_all_seven_calibrated_lanes_have_near_edge_below_far_edge(self) -> None:
        quads = _real_lane_quads()
        self.assertEqual(len(quads), 7)
        for name, points in quads.items():
            near_left, near_right, far_right, far_left = order_lane_quad(points)
            with self.subTest(lane=name):
                self.assertGreater((near_left[1] + near_right[1]) / 2, (far_left[1] + far_right[1]) / 2)
                self.assertLess(near_left[0], near_right[0])
                self.assertEqual({near_left, near_right, far_right, far_left}, set(points))

    def test_degenerate_quad_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            order_lane_quad([(0.1, 0.1), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4)])
        with self.assertRaises(ValueError):
            order_lane_quad([(0.1, 0.1), (0.2, 0.2), (0.3, 0.3)])


class LaneHomographyTests(unittest.TestCase):
    def test_corners_map_to_the_lane_rectangle(self) -> None:
        homography = LaneHomography.from_quad(TRAPEZOID, length_m=45.8, width_m=4.0)
        corners = [homography.project(*point) for point in order_lane_quad(TRAPEZOID)]
        np.testing.assert_allclose(corners, [(0, 0), (4.0, 0), (4.0, 45.8), (0, 45.8)], atol=1e-4)

    def test_interior_point_is_inside_and_distance_grows_upstream(self) -> None:
        homography = LaneHomography.from_quad(TRAPEZOID, length_m=40.0, width_m=3.2)
        near = homography.project(0.4, 0.8)
        far = homography.project(0.4, 0.3)
        self.assertTrue(homography.contains(*near))
        self.assertTrue(homography.contains(*far))
        self.assertLess(near[1], far[1])
        self.assertFalse(homography.contains(*homography.project(0.95, 0.5)))

    def test_every_calibrated_lane_projects_its_centroid_inside(self) -> None:
        for name, points in _real_lane_quads().items():
            homography = LaneHomography.from_quad(points, length_m=44.0, width_m=3.2)
            centroid = np.asarray(points).mean(axis=0)
            with self.subTest(lane=name):
                self.assertTrue(homography.contains(*homography.project(*centroid)))

    def test_invalid_dimensions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LaneHomography.from_quad(TRAPEZOID, length_m=0.0, width_m=3.2)

    def test_bbox_ground_point_is_bottom_center(self) -> None:
        self.assertEqual(bbox_ground_point([10, 20, 30, 60]), (20.0, 60.0))


class CalibratedLaneExtentTests(unittest.TestCase):
    def test_camera_looking_straight_down_projects_image_center_below_it(self) -> None:
        pose = {"fieldOfView": 60.0, "position": {"x": 3.0, "y": 10.0, "z": -4.0}, "rotationEulerDegrees": {"x": 90.0, "y": 0.0, "z": 0.0}}
        np.testing.assert_allclose(image_point_to_ground(pose, 16 / 9, 0.5, 0.5), (3.0, -4.0), atol=1e-9)
        # Topo da imagem aponta para +z da Unity (= +y do SUMO) quando a câmera olha para baixo.
        self.assertGreater(image_point_to_ground(pose, 16 / 9, 0.5, 0.0)[1], -4.0)

    def test_sp_yaml_lane_geometry_matches_unity_calibration(self) -> None:
        config = yaml.safe_load((REPO_DIR / "python" / "configs" / "sp.yaml").read_text(encoding="utf-8"))
        measured = measure_lane_rois(
            config, REPO_DIR / "sumo" / "sp" / "Cruzamento.net.xml", REPO_DIR / "sumo" / "sp" / "Cruzamento.add.xml", CALIBRATION_DIR,
        )
        for name, row in measured.items():
            camera_id, lane_id = name.split("/")
            declared = config["lane_geometry"][camera_id][lane_id]
            with self.subTest(lane=name):
                self.assertEqual(declared["sumo_lane"], row["lane"])
                self.assertAlmostEqual(declared["roi_start_m"], row["roi_start_m"], delta=0.5)
                self.assertAlmostEqual(declared["roi_end_m"], row["roi_end_m"], delta=0.5)
                self.assertAlmostEqual(declared["width_m"], row["lane_width_m"])
                # Largura projetada ≈ largura da lane confirma pose/FOV coerentes.
                self.assertAlmostEqual(row["roi_width_near_m"], row["lane_width_m"], delta=0.7)


if __name__ == "__main__":
    unittest.main()
