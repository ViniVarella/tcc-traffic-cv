"""Testes da leitura de calibração exportada pelo Unity."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vision.camera_calibration import load_camera_calibration


def calibration_payload(camera_id: str = "south") -> dict:
    return {
        "schemaVersion": 1,
        "cameraId": camera_id,
        "capture": {"width": 1280, "height": 720},
        "approachRoi": {"id": "approach", "points": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}]},
        "laneRois": [{"id": "lane_0", "points": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0}, {"x": 0.5, "y": 1.0}, {"x": 0.0, "y": 1.0}]}],
    }


class CameraCalibrationTests(unittest.TestCase):
    def write_calibration(self, payload: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "calibration.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_scales_normalized_rois_to_frame_pixels(self) -> None:
        calibration = load_camera_calibration(self.write_calibration(calibration_payload()))

        self.assertEqual(calibration.pixel_rois(1280, 720)["approach"], [[0, 0], [1279, 0], [1279, 719], [0, 719]])
        self.assertEqual(calibration.lane_pixel_rois(1280, 720)["lane_0"][1], [640, 0])

    def test_rejects_wrong_expected_camera(self) -> None:
        path = self.write_calibration(calibration_payload("east"))

        with self.assertRaisesRegex(ValueError, "esperada 'south'"):
            load_camera_calibration(path, expected_camera_id="south")

    def test_rejects_roi_with_out_of_range_coordinate(self) -> None:
        payload = calibration_payload()
        payload["laneRois"][0]["points"][0]["x"] = 1.1

        with self.assertRaisesRegex(ValueError, "fora do intervalo"):
            load_camera_calibration(self.write_calibration(payload))
