"""Testes do comparador de baseline fixo e controle visual."""

from __future__ import annotations

import unittest

from experiments.compare_control_experiments import compare_metrics


class CompareControlExperimentsTests(unittest.TestCase):
    def test_computes_absolute_and_percent_deltas(self) -> None:
        comparison = compare_metrics(
            {"arrived_vehicles": 10, "mean_waiting_time_seconds": 20},
            {"arrived_vehicles": 12, "mean_waiting_time_seconds": 15},
        )
        arrived = comparison["comparison"]["arrived_vehicles"]
        waiting = comparison["comparison"]["mean_waiting_time_seconds"]
        self.assertEqual((arrived["absolute_delta"], arrived["percent_delta"], arrived["higher_is_better"]), (2.0, 20.0, True))
        self.assertEqual((waiting["absolute_delta"], waiting["percent_delta"], waiting["higher_is_better"]), (-5.0, -25.0, False))


if __name__ == "__main__":
    unittest.main()
