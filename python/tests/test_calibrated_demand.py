"""Testes do gerador da demanda calibrada sem motos."""

from __future__ import annotations

from pathlib import Path
import unittest

from experiments.build_calibrated_demand import (
    APPROACHES, Flow, approach_demand, kept_share, read_summary, read_labels, scale_flows,
)


SP_DATA = Path(__file__).resolve().parents[2] / "simjamcv" / "DigitalTwinsforSmartCities" / "SP"


class KeptShareTests(unittest.TestCase):
    def test_motorcycles_tricycles_and_pedestrians_are_removed(self) -> None:
        labels = ["car"] * 4 + ["van", "bus", "truck"] + ["motor"] * 3 + ["tricycle", "pedestrian", "people"]
        self.assertAlmostEqual(kept_share(labels), 7 / 13)
        self.assertAlmostEqual(approach_demand(1300.0, labels), 700.0)
        with self.assertRaises(ValueError):
            kept_share([])

    def test_unknown_labels_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            kept_share(["car", "bicycle"])


class ScaleFlowsTests(unittest.TestCase):
    def test_turn_proportions_are_kept_and_totals_replaced(self) -> None:
        flows = [Flow("f_1", "E2", "E0", 0.1), Flow("f_2", "E2", "E5", 0.3), Flow("f_0", "E6", "E1", 0.05)]
        scaled = {flow.flow_id: flow for flow in scale_flows(flows, {"E2": 720.0, "E6": 36.0})}
        self.assertAlmostEqual(scaled["f_1"].rate_per_s, 0.05)
        self.assertAlmostEqual(scaled["f_2"].rate_per_s, 0.15)
        self.assertAlmostEqual(scaled["f_0"].rate_per_s, 0.01)
        with self.assertRaises(ValueError):
            scale_flows(flows, {"E2": 720.0})


@unittest.skipUnless(SP_DATA.exists(), "dados do drone ausentes")
class DroneDataTests(unittest.TestCase):
    def test_drone_demand_without_motorcycles(self) -> None:
        expected = {"E2": 975.6, "E3": 726.6, "E6": 139.0}
        for folder, edge in APPROACHES.items():
            demand = approach_demand(read_summary(SP_DATA / folder)["throughput_per_hour"], read_labels(SP_DATA / folder))
            self.assertAlmostEqual(demand, expected[edge], delta=0.1)


if __name__ == "__main__":
    unittest.main()
