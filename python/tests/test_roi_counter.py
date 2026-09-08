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

    def test_does_not_duplicate_detection_already_covered_by_track(self) -> None:
        detections = [{"bbox": [20.0, 20.0, 40.0, 40.0], "confidence": 0.3, "class_id": 2}]
        tracks = [{"track_id": 7, "bbox": [21.0, 21.0, 41.0, 41.0], "confidence": 0.9, "class_id": 2}]

        objects, source = select_counting_objects(detections, tracks)

        self.assertEqual(source, "tracks")
        self.assertEqual(objects, tracks)

    def test_adds_unmatched_detection_to_confirmed_tracks(self) -> None:
        detections = [
            {"bbox": [20.0, 20.0, 40.0, 40.0], "confidence": 0.3, "class_id": 2},
            {"bbox": [60.0, 20.0, 80.0, 40.0], "confidence": 0.3, "class_id": 2},
        ]
        tracks = [{"track_id": 7, "bbox": [21.0, 21.0, 41.0, 41.0], "confidence": 0.9, "class_id": 2}]

        objects, source = select_counting_objects(detections, tracks)

        self.assertEqual(source, "hybrid")
        self.assertEqual(len(objects), 2)
        self.assertEqual(objects[0], tracks[0])
        self.assertEqual(objects[1], detections[1])


if __name__ == "__main__":
    unittest.main()
