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

    def test_warmup_excludes_early_vehicles_and_samples(self) -> None:
        collector = ExperimentMetricsCollector(warmup_until_s=10.0)
        stopped = {"speed": 0.0, "accumulated_waiting_time": 5.0}
        collector.observe(5, {"departed": ["early"], "arrived": []}, {"early": stopped}, pending_vehicles=9)
        collector.observe(10, {"departed": ["boundary"], "arrived": []}, {"early": stopped}, pending_vehicles=99)
        collector.observe(11, {"departed": ["late"], "arrived": []}, {"early": stopped, "late": {"speed": 5.0, "accumulated_waiting_time": 0.0}}, pending_vehicles=4)
        collector.observe(15, {"departed": [], "arrived": ["early", "late"]}, {}, pending_vehicles=2, teleports=1)
        summary = collector.summary()
        self.assertEqual((summary["departed_vehicles"], summary["arrived_vehicles"]), (1, 2))
        self.assertEqual((summary["mean_travel_time_seconds"], summary["mean_waiting_time_seconds"]), (4.0, 0.0))
        self.assertEqual((summary["simulation_seconds"], summary["max_queue_length"]), (4.0, 1))
        self.assertEqual((summary["mean_pending_vehicles"], summary["max_pending_vehicles"], summary["final_pending_vehicles"]), (3.0, 4, 2))
        self.assertEqual((summary["teleported_vehicles"], summary["warmup_seconds"]), (1, 10.0))

    def test_pending_metrics_are_omitted_when_not_observed(self) -> None:
        collector = ExperimentMetricsCollector()
        collector.observe(1, {"departed": [], "arrived": []}, {})
        self.assertNotIn("mean_pending_vehicles", collector.summary())


if __name__ == "__main__":
    unittest.main()
