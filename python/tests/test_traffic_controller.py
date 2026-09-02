"""Testes do controlador visual e das transições de fase seguras."""

from __future__ import annotations

import unittest

from controller.traffic_controller import TrafficController


CONFIG = {
    "traffic_light": {"phases": {"primary_green": 0, "primary_yellow": 1, "all_red": 2, "secondary_green": 3, "secondary_yellow": 4}},
    "traffic_control": {"min_green_seconds": 10, "max_green_seconds": 40, "yellow_seconds": 3, "all_red_seconds": 1, "switch_margin": 1},
}


class TrafficControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = TrafficController("tls", CONFIG)

    def test_holds_green_until_minimum_duration(self) -> None:
        decision = self.controller.update(9, {"south": {"lane_0": 8}, "east": {"lane_0": 1}, "west": {"lane_0": 0}})
        self.assertEqual((decision["action"], decision["phase_index"], decision["reason"]), ("hold", 0, "min_green_not_reached"))

    def test_switches_safely_from_east_west_to_south(self) -> None:
        counts = {"south": {"lane_0": 8}, "east": {"lane_0": 1}, "west": {"lane_0": 0}}
        yellow = self.controller.update(10, counts)
        yellow_hold = self.controller.update(11, counts)
        all_red = self.controller.update(13, counts)
        all_red_hold = self.controller.update(13.5, counts)
        south_green = self.controller.update(14, counts)
        self.assertEqual((yellow["action"], yellow["phase_index"]), ("set_phase", 1))
        self.assertEqual((yellow_hold["action"], yellow_hold["phase_index"], yellow_hold["reason"]), ("hold", 1, "east_west_yellow_in_progress"))
        self.assertEqual((all_red["action"], all_red["phase_index"]), ("set_phase", 2))
        self.assertEqual((all_red_hold["action"], all_red_hold["phase_index"], all_red_hold["reason"]), ("hold", 2, "all_red_in_progress"))
        self.assertEqual((south_green["action"], south_green["phase_index"]), ("set_phase", 3))

    def test_max_green_forces_change_even_without_opposing_demand(self) -> None:
        decision = self.controller.update(40, {"south": 0, "east": 0, "west": 0})
        self.assertEqual((decision["action"], decision["phase_index"], decision["reason"]), ("set_phase", 1, "max_green_reached"))

    def test_apply_only_sends_real_phase_changes(self) -> None:
        class Client:
            def __init__(self) -> None:
                self.calls: list[tuple[str, int]] = []

            def set_traffic_light_phase(self, tls_id: str, phase: int) -> None:
                self.calls.append((tls_id, phase))

        client = Client()
        self.controller.apply(client, self.controller.update(0, {"south": 1, "east": 1, "west": 0}))
        self.controller.apply(client, self.controller.update(10, {"south": 4, "east": 0, "west": 0}))
        self.assertEqual(client.calls, [("tls", 1)])
