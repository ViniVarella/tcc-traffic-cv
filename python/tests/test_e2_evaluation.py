"""Testes da comparação offline entre visão e detectores E2."""

from __future__ import annotations

import unittest

from sumo import GroundTruthCollector
from vision.e2_evaluation import lane_comparison_rows, metrics_by_lane


class E2EvaluationTests(unittest.TestCase):
    def test_collector_serializes_e2_metrics_for_a_step(self) -> None:
        snapshot = GroundTruthCollector("tls").collect_detector_snapshot(
            step_id=7,
            sim_time=8.0,
            detector_metrics={"e2_4": {"vehicle_count": 3, "halting_count": 2, "occupancy": 57.5}},
        )

        self.assertEqual(snapshot["step_id"], 7)
        self.assertEqual(snapshot["detectors"]["e2_4"]["vehicle_count"], 3)
        self.assertEqual(snapshot["detectors"]["e2_4"]["halting_count"], 2)

    def test_compares_raw_lane_counts_to_e2_vehicle_count(self) -> None:
        vision_records = [
            {"step_id": 4, "cameras": {"south": {"lane_counts": {"lane_0": 2}}}},
            {"step_id": 5, "cameras": {"south": {"lane_counts": {"lane_0": 1}}}},
        ]
        ground_truth_records = [
            {
                "step_id": 4,
                "sim_time": 5.0,
                "detectors": {"e2_4": {"vehicle_count": 3, "halting_count": 2, "occupancy": 50.0}},
            },
            {
                "step_id": 5,
                "sim_time": 6.0,
                "detectors": {"e2_4": {"vehicle_count": 1, "halting_count": 1, "occupancy": 20.0}},
            },
        ]

        rows = lane_comparison_rows(vision_records, ground_truth_records, {"south": {"lane_0": "e2_4"}})
        metrics = metrics_by_lane(rows)

        self.assertEqual([row["signed_error"] for row in rows], [-1, 0])
        self.assertEqual(rows[0]["e2_halting_count"], 2)
        self.assertEqual(metrics[0]["samples"], 2)
        self.assertEqual(metrics[0]["mae"], 0.5)
        self.assertEqual(metrics[0]["rmse"], round(2 ** -0.5, 4))
        self.assertEqual(metrics[0]["exact_match_rate"], 0.5)

    def test_rejects_records_without_a_common_step(self) -> None:
        with self.assertRaisesRegex(ValueError, "em comum"):
            lane_comparison_rows(
                [{"step_id": 1, "cameras": {}}],
                [{"step_id": 2, "detectors": {}}],
                {"south": {"lane_0": "e2_4"}},
            )


if __name__ == "__main__":
    unittest.main()
