from __future__ import annotations

import unittest

from vision.detection_evaluation import OUTSIDE_ROI, UNCALIBRATED, Box, DetectionTally, distance_band, match_boxes


class DetectionEvaluationTest(unittest.TestCase):
    def test_match_is_class_agnostic_and_one_to_one(self) -> None:
        truths = [Box((0, 0, 10, 10), 0), Box((20, 0, 30, 10), 1)]
        predictions = [Box((21, 0, 31, 10), 0), Box((0, 0, 10, 10), 0), Box((0, 1, 10, 11), 0)]
        self.assertEqual(match_boxes(truths, predictions), [1, 0])

    def test_distance_bands(self) -> None:
        self.assertEqual(distance_band(5.0, True), "0-20m")
        self.assertEqual(distance_band(60.0, True), "40-60m")
        self.assertEqual(distance_band(None, True), OUTSIDE_ROI)
        self.assertEqual(distance_band(10.0, False), UNCALIBRATED)

    def test_tally_separates_confusion_from_miss_and_counts_false_positives(self) -> None:
        tally = DetectionTally(("vehicle", "emergency"))
        truths = [Box((0, 0, 10, 10), 0), Box((20, 0, 30, 10), 0), Box((40, 0, 50, 10), 1)]
        predictions = [Box((0, 0, 10, 10), 0), Box((20, 0, 30, 10), 1), Box((80, 0, 90, 10), 1)]
        tally.add_image(truths, ["0-20m", "40-60m", "40-60m"], predictions)
        summary = tally.summary()
        vehicle = summary["classes"]["vehicle"]
        self.assertEqual(vehicle["all"]["labels"], 2)
        self.assertEqual(vehicle["all"]["recall"], 0.5)
        self.assertEqual(vehicle["all"]["confused_class"], 1)
        self.assertEqual(vehicle["by_band"]["40-60m"]["detected_any_class"], 1.0)
        self.assertEqual(summary["classes"]["emergency"]["all"]["recall"], 0.0)
        self.assertEqual(summary["false_positives"], {"emergency": 1})


if __name__ == "__main__":
    unittest.main()
