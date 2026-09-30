"""Testes das restrições de segurança entre DQN e semáforo."""

from __future__ import annotations

import unittest

from controller import DqnTrafficController
from controller.phase_manager import SUMO_PHASE_HOLD_SECONDS


CONFIG = {"traffic_light": {"phases": {"primary_green": 0, "primary_yellow": 1, "all_red": 2, "secondary_green": 3, "secondary_yellow": 4}}, "traffic_control": {"min_green_seconds": 10, "max_green_seconds": 40, "yellow_seconds": 3, "all_red_seconds": 1}}


class DqnTrafficControllerTests(unittest.TestCase):
    def test_switch_is_blocked_until_minimum_green_then_is_safe(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        self.assertEqual(controller.update(9, controller.SWITCH)["reason"], "min_green_not_reached")
        self.assertEqual((controller.update(10, controller.SWITCH)["phase_index"], controller.update(11, controller.KEEP)["reason"]), (1, "east_west_yellow_in_progress"))
        self.assertEqual(controller.update(13, controller.KEEP)["phase_index"], 2)
        self.assertEqual(controller.update(14, controller.KEEP)["phase_index"], 3)

    def test_apply_holds_every_phase_set_in_sumo(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        client = RecordingClient()
        controller.apply(client, controller.update(5, controller.SWITCH))
        controller.apply(client, controller.update(10, controller.SWITCH))
        self.assertEqual(client.calls, [("phase", "tls", 1), ("duration", "tls", SUMO_PHASE_HOLD_SECONDS)])

    def test_without_vision_never_switches_voluntarily(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        decision = controller.update_without_vision(20)
        self.assertEqual((decision["action"], decision["reason"], decision["requested_action"]), ("hold", "vision_unavailable", None))

    def test_without_vision_still_enforces_max_green_yellow_and_all_red(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        self.assertEqual(controller.update_without_vision(40)["reason"], "max_green_reached")
        self.assertEqual(controller.update_without_vision(42)["reason"], "east_west_yellow_in_progress")
        self.assertEqual(controller.update_without_vision(43)["phase_index"], 2)
        self.assertEqual(controller.update_without_vision(44)["phase_index"], 3)


class RecordingClient:
    """Registra as chamadas TraCI feitas por ``apply``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def set_traffic_light_phase(self, tls_id: str, phase: int) -> None:
        self.calls.append(("phase", tls_id, phase))

    def set_traffic_light_phase_duration(self, tls_id: str, duration: float) -> None:
        self.calls.append(("duration", tls_id, duration))
