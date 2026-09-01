"""Testes da filtragem de ROI usada antes do ByteTrack."""

from __future__ import annotations

import unittest

from vision.roi_counter import ROICounter, filter_detections_to_roi, select_counting_objects


class RoiFilterTests(unittest.TestCase):
    def test_keeps_only_detection_with_center_inside_approach_roi(self) -> None:
        roi = [[10, 10], [90, 10], [90, 90], [10, 90]]
        detections = [
            {"bbox": [20.0, 20.0, 40.0, 40.0], "confidence": 0.9, "class_id": 2},
            {"bbox": [91.0, 20.0, 111.0, 40.0], "confidence": 0.9, "class_id": 2},
        ]

        filtered = filter_detections_to_roi(detections, roi)

        self.assertEqual(filtered, [detections[0]])

    def test_uses_detections_when_no_track_is_confirmed(self) -> None:
        detections = [{"bbox": [20.0, 20.0, 40.0, 40.0], "confidence": 0.3, "class_id": 2}]

        objects, source = select_counting_objects(detections, tracks=[])

        self.assertEqual(source, "detections_fallback")
        self.assertEqual(ROICounter({"lane_0": [[10, 10], [90, 10], [90, 90], [10, 90]]}).count(objects), {"lane_0": 1})

    def test_prefers_confirmed_tracks_over_detections(self) -> None:
        detections = [{"bbox": [20.0, 20.0, 40.0, 40.0], "confidence": 0.3, "class_id": 2}]
        tracks = [{"track_id": 7, "bbox": [30.0, 30.0, 50.0, 50.0], "confidence": 0.9, "class_id": 2}]

        objects, source = select_counting_objects(detections, tracks)

        self.assertEqual(source, "tracks")
        self.assertEqual(objects, tracks)


if __name__ == "__main__":
    unittest.main()
