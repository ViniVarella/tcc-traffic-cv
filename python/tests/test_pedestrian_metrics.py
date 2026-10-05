"""Testes das métricas de pedestres."""

from __future__ import annotations

import unittest

from experiments.episode_runner import RewardModel
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



class PedestrianRewardTests(unittest.TestCase):
    METRICS = {"halting_vehicles": 10, "waiting_time_s": 0.0, "pending_vehicles": 0}

    def test_without_pedestrian_weight_the_reward_ignores_pedestrians(self) -> None:
        model = RewardModel(("E3_0",), capacity=20.0)
        self.assertAlmostEqual(model(self.METRICS), -0.25)

    def test_pedestrian_term_mixes_and_saturates(self) -> None:
        model = RewardModel(("E3_0",), capacity=20.0, pedestrian_weight=0.3, pedestrian_reference_s=600.0)
        self.assertAlmostEqual(model({**self.METRICS, "pedestrian_waiting_s": 300.0}), 0.7 * -0.25 - 0.3 * 0.5)
        self.assertAlmostEqual(model({**self.METRICS, "pedestrian_waiting_s": 6000.0}), 0.7 * -0.25 - 0.3)
        with self.assertRaises(ValueError):
            RewardModel(("E3_0",), capacity=20.0, pedestrian_weight=1.5)


if __name__ == "__main__":
    unittest.main()
