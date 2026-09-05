"""Testes das restrições de segurança entre DQN e semáforo."""

from __future__ import annotations

import unittest

from controller import DqnTrafficController


CONFIG = {"traffic_light": {"phases": {"primary_green": 0, "primary_yellow": 1, "all_red": 2, "secondary_green": 3, "secondary_yellow": 4}}, "traffic_control": {"min_green_seconds": 10, "max_green_seconds": 40, "yellow_seconds": 3, "all_red_seconds": 1}}


class DqnTrafficControllerTests(unittest.TestCase):
    def test_switch_is_blocked_until_minimum_green_then_is_safe(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        self.assertEqual(controller.update(9, controller.SWITCH)["reason"], "min_green_not_reached")
        self.assertEqual((controller.update(10, controller.SWITCH)["phase_index"], controller.update(11, controller.KEEP)["reason"]), (1, "east_west_yellow_in_progress"))
        self.assertEqual(controller.update(13, controller.KEEP)["phase_index"], 2)
        self.assertEqual(controller.update(14, controller.KEEP)["phase_index"], 3)
