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

    def test_progress_tracks_the_summary_waiting_time(self) -> None:
        collector = ExperimentMetricsCollector(warmup_until_s=10.0)
        empty = collector.progress(5.0)
        self.assertEqual((empty["completed_vehicles"], empty["mean_waiting_time_s"], empty["sampled_s"]), (0, None, 0.0))
        collector.observe(11, {"departed": ["a", "b"], "arrived": []},
                          {"a": {"speed": 0.0, "accumulated_waiting_time": 4.0}, "b": {"speed": 0.0, "accumulated_waiting_time": 8.0}},
                          pending_vehicles=3)
        collector.observe(12, {"departed": [], "arrived": ["a"]}, {"b": {"speed": 0.0, "accumulated_waiting_time": 9.0}}, pending_vehicles=2)
        progress = collector.progress(12.0)
        self.assertEqual((progress["completed_vehicles"], progress["mean_waiting_time_s"], progress["sampled_s"]), (1, 4.0, 2.0))
        # A fila de inserção e os veículos ainda na rede vão à parte, não na média.
        self.assertEqual((progress["pending_vehicles"], progress["active_vehicles"]), (2, 1))
        collector.observe(13, {"departed": [], "arrived": ["b"]}, {}, pending_vehicles=0)
        self.assertEqual(collector.progress(13.0)["mean_waiting_time_s"], collector.summary()["mean_waiting_time_seconds"])

    def test_stopped_wait_leaves_out_vehicles_that_never_stopped(self) -> None:
        collector = ExperimentMetricsCollector()
        self.assertEqual(collector.progress(0.0)["mean_waiting_time_stopped_s"], None)
        collector.observe(1, {"departed": ["a", "b", "c", "emergency_0"], "arrived": []}, {
            "a": {"speed": 0.0, "accumulated_waiting_time": 6.0}, "b": {"speed": 0.0, "accumulated_waiting_time": 10.0},
            "c": {"speed": 9.0, "accumulated_waiting_time": 0.0}, "emergency_0": {"speed": 0.0, "accumulated_waiting_time": 20.0}})
        collector.observe(2, {"departed": [], "arrived": ["a", "b", "c", "emergency_0"]}, {})
        summary = collector.summary()
        self.assertEqual((summary["mean_waiting_time_seconds"], summary["mean_waiting_time_stopped_seconds"]), (9.0, 12.0))
        self.assertEqual(summary["stopped_vehicle_share"], 0.75)
        progress = collector.progress(2.0)
        self.assertEqual((progress["mean_waiting_time_stopped_s"], progress["stopped_share"], progress["stopped_vehicles"]), (12.0, 0.75, 3))
        # Sem viaturas: a, b e c; quem passou no verde (c) só entra na média geral.
        progress = collector.progress(2.0, exclude_emergencies=True)
        self.assertEqual((progress["mean_waiting_time_s"], progress["mean_waiting_time_stopped_s"]), (16.0 / 3, 8.0))
        self.assertAlmostEqual(progress["stopped_share"], 2 / 3)

    def test_progress_can_leave_emergency_vehicles_out(self) -> None:
        collector = ExperimentMetricsCollector()
        collector.observe(1, {"departed": ["car", "emergency_0", "emergency_manual_0"], "arrived": []}, {
            "car": {"speed": 0.0, "accumulated_waiting_time": 6.0},
            "emergency_0": {"speed": 0.0, "accumulated_waiting_time": 0.0},
            "emergency_manual_0": {"speed": 0.0, "accumulated_waiting_time": 0.0}})
        collector.observe(2, {"departed": [], "arrived": ["car", "emergency_0", "emergency_manual_0"]}, {})
        self.assertEqual(collector.progress(2.0, exclude_emergencies=True)["mean_waiting_time_s"], 6.0)
        self.assertEqual(collector.progress(2.0)["mean_waiting_time_s"], collector.summary()["mean_waiting_time_seconds"])

    def test_pending_metrics_are_omitted_when_not_observed(self) -> None:
        collector = ExperimentMetricsCollector()
        collector.observe(1, {"departed": [], "arrived": []}, {})
        self.assertNotIn("mean_pending_vehicles", collector.summary())


if __name__ == "__main__":
    unittest.main()
