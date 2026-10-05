"""Testes das métricas de pedestres."""

from __future__ import annotations

import unittest

from sumo.pedestrian_metrics import PedestrianMetricsCollector


class PedestrianMetricsTests(unittest.TestCase):
    def test_waiting_counts_stopped_steps_until_the_pedestrian_leaves(self) -> None:
        collector = PedestrianMetricsCollector(warmup_until_s=10.0)
        collector.observe(11, {"a": 1.2})
        collector.observe(12, {"a": 0.0})
        collector.observe(13, {"a": 0.05, "b": 1.0})
        collector.observe(14, {"b": 1.0})
        summary = collector.summary()
        self.assertEqual(summary["pedestrians_arrived"], 1)
        self.assertEqual(summary["pedestrian_mean_waiting_s"], 2.0)
        self.assertEqual(summary["pedestrian_mean_trip_s"], 3.0)
        self.assertEqual(summary["pedestrians_active_at_end"], 1)

    def test_pedestrians_from_the_warmup_are_not_counted(self) -> None:
        collector = PedestrianMetricsCollector(warmup_until_s=10.0)
        collector.observe(9, {"early": 0.0})
        collector.observe(12, {})
        self.assertEqual(collector.summary()["pedestrians_arrived"], 0)
        self.assertIsNone(collector.summary()["pedestrian_mean_waiting_s"])


if __name__ == "__main__":
    unittest.main()
