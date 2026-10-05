"""Testes do gerador da variante com pedestres do cenário SP."""

from __future__ import annotations

import math
from pathlib import Path
import unittest

import yaml

from experiments.build_pedestrian_network import flows_xml, pedestrian_flows, pedestrian_program, shift_lane_ids


CONFIG = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs" / "sp.yaml").read_text(encoding="utf-8"))
VEHICLE_STATES = ["GGGrrrrrrG", "yyyrrrrrry", "rrrrrrrrrr", "rrrGgGGGGr", "rrryyyyyyr"]


class BuilderTests(unittest.TestCase):
    def test_detector_lanes_shift_by_one_for_the_sidewalk(self) -> None:
        text = '<laneAreaDetector id="e2_4" lane="E3_0" pos="33.67"/><laneAreaDetector id="e2_5" lane="E2_1"/>'
        self.assertEqual(shift_lane_ids(text),
                         '<laneAreaDetector id="e2_4" lane="E3_1" pos="33.67"/><laneAreaDetector id="e2_5" lane="E2_2"/>')

    def test_program_keeps_vehicle_links_and_adds_pedestrian_phases(self) -> None:
        program = pedestrian_program(VEHICLE_STATES, crossing_count=4)
        self.assertEqual([state[:10] for _, state in program[:5]], VEHICLE_STATES)
        self.assertTrue(all(state[10:] == "rrrr" for _, state in program[:5]))
        self.assertEqual(program[5], ("pedestrian_green", "r" * 10 + "GGGG"))
        self.assertEqual(program[6], ("pedestrian_clearance", "r" * 14))
        with self.assertRaises(ValueError):
            pedestrian_program(VEHICLE_STATES[:4], 4)

    def test_flows_cover_every_ordered_pair_and_sum_to_the_demand(self) -> None:
        flows = pedestrian_flows(("E0", "E1", "E2"), total_per_hour=360.0, end_s=3600.0)
        self.assertEqual(len(flows), 6)
        self.assertAlmostEqual(sum(rate for *_, rate in flows) * 3600.0, 360.0)
        self.assertIn('<walk from="E0" to="E1" arrivalPos="random"/>', flows_xml(flows, 3600.0))
        with self.assertRaises(ValueError):
            pedestrian_flows(("E0", "E1"), 0.0, 3600.0)

    def test_profile_green_covers_the_longest_l_at_design_speed(self) -> None:
        pedestrians = CONFIG["pedestrians"]
        self.assertEqual(pedestrians["green_seconds"], math.ceil(pedestrians["longest_l_m"] / pedestrians["walking_speed_mps"]))
        self.assertEqual(CONFIG["traffic_light"]["phases"]["pedestrian_green"], 5)
        self.assertIn("calibrated_ped", CONFIG["sumo"]["scenarios"])


if __name__ == "__main__":
    unittest.main()
