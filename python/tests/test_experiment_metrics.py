"""Testes das métricas agregadas dos experimentos semafóricos."""

from __future__ import annotations

import unittest

from sumo import ExperimentMetricsCollector


class ExperimentMetricsCollectorTests(unittest.TestCase):
    def test_records_travel_waiting_and_queue_metrics(self) -> None:
        collector = ExperimentMetricsCollector()
        collector.observe(1, {"departed": ["car_1"], "arrived": []}, {"car_1": {"speed": 0.0, "accumulated_waiting_time": 1.0}})
        collector.observe(3, {"departed": [], "arrived": ["car_1"]}, {})
        summary = collector.summary()
        self.assertEqual(summary["departed_vehicles"], 1)
        self.assertEqual(summary["arrived_vehicles"], 1)
        self.assertEqual(summary["mean_travel_time_seconds"], 2.0)
        self.assertEqual(summary["mean_waiting_time_seconds"], 1.0)
        self.assertEqual(summary["max_queue_length"], 1)


if __name__ == "__main__":
    unittest.main()
