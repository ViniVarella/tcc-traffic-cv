"""Testes do pipeline visual compartilhado entre treino e controle."""

from __future__ import annotations

from pathlib import Path
import unittest

import cv2
import numpy as np

from bridge import FramePacket
from bridge.frame_bundle import CapturedFrame, FrameBundle
from vision.visual_pipeline import VisualPipeline, load_calibrations, parse_class_ids, queue_counts_by_camera


PYTHON_DIR = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 640, 360


def _lane_center(calibration, lane_id: str) -> tuple[float, float]:
    points = np.asarray(calibration.lane_pixel_rois(WIDTH, HEIGHT)[lane_id], dtype=float)
    return tuple(points.mean(axis=0))


def _box(center: tuple[float, float], half: float = 6.0) -> list[float]:
    x, y = center
    return [x - half, y - half, x + half, y + half]


class FakeDetector:
    def __init__(self, detections_by_call: list[list[dict]]) -> None:
        self._detections = list(detections_by_call)

    def detect(self, frame) -> list[dict]:
        return self._detections.pop(0) if self._detections else []


class EchoTracker:
    """Transforma cada detecção em um track com ID sequencial estável por posição."""

    def __init__(self) -> None:
        self.updates = 0

    def update(self, detections: list[dict]) -> list[dict]:
        self.updates += 1
        return [{**detection, "track_id": index + 1} for index, detection in enumerate(detections)]


def _bundle(step_id: int, camera_ids: tuple[str, ...]) -> FrameBundle:
    ok, jpeg = cv2.imencode(".jpg", np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8))
    assert ok
    frames = {
        camera_id: CapturedFrame(jpeg.tobytes(), FramePacket(step_id, float(step_id), camera_id, "jpg", len(jpeg)))
        for camera_id in camera_ids
    }
    return FrameBundle(step_id, frozenset(camera_ids), frames)


class VisualPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calibrations = load_calibrations(PYTHON_DIR, ("south", "east", "west"))

    def _detection(self, camera_id: str, lane_id: str) -> dict:
        return {"bbox": _box(_lane_center(self.calibrations[camera_id], lane_id)), "confidence": 0.9, "class_id": 0}

    def test_counts_one_vehicle_in_each_targeted_lane(self) -> None:
        detections = [self._detection("south", "lane_0"), self._detection("south", "lane_2")]
        pipeline = VisualPipeline({"south": self.calibrations["south"]}, FakeDetector([detections]), EchoTracker)
        results = pipeline.process_bundle(_bundle(0, ("south",)))
        self.assertEqual(results["south"].raw_counts, {"lane_0": 1, "lane_1": 0, "lane_2": 1, "lane_3": 0})
        self.assertEqual(results["south"].count_source, "tracks")
        self.assertEqual(queue_counts_by_camera(results), {"south": results["south"].queue_counts})

    def test_detections_outside_approach_roi_are_discarded(self) -> None:
        outside = {"bbox": [0.0, 0.0, 4.0, 4.0], "confidence": 0.9, "class_id": 0}
        pipeline = VisualPipeline({"west": self.calibrations["west"]}, FakeDetector([[outside]]), EchoTracker)
        result = pipeline.process_bundle(_bundle(0, ("west",)))["west"]
        self.assertEqual((result.detections, result.raw_counts), ([], {"lane_0": 0}))

    def test_queue_counts_are_smoothed_across_steps_and_reset_per_episode(self) -> None:
        detection = self._detection("east", "lane_1")
        detector = FakeDetector([[detection], [], [detection]])
        pipeline = VisualPipeline({"east": self.calibrations["east"]}, detector, EchoTracker)
        first = pipeline.process_bundle(_bundle(0, ("east",)))["east"].queue_counts["lane_1"]
        second = pipeline.process_bundle(_bundle(1, ("east",)))["east"].queue_counts["lane_1"]
        pipeline.reset()
        third = pipeline.process_bundle(_bundle(2, ("east",)))["east"].queue_counts["lane_1"]
        # Média móvel: [1] -> 1, [1, 0] -> round(0.5) = 0; após reset o histórico recomeça.
        self.assertEqual((first, second, third), (1, 0, 1))

    def test_all_three_cameras_are_processed_with_independent_trackers(self) -> None:
        trackers: list[EchoTracker] = []

        def factory() -> EchoTracker:
            trackers.append(EchoTracker())
            return trackers[-1]

        pipeline = VisualPipeline(self.calibrations, FakeDetector([]), factory)
        results = pipeline.process_bundle(_bundle(0, ("south", "east", "west")))
        self.assertEqual(set(results), {"south", "east", "west"})
        self.assertEqual([tracker.updates for tracker in trackers], [1, 1, 1])

    def test_parse_class_ids(self) -> None:
        self.assertEqual(parse_class_ids("2, 3,5"), [2, 3, 5])
        with self.assertRaises(ValueError):
            parse_class_ids("-1")
        with self.assertRaises(ValueError):
            parse_class_ids("car")
