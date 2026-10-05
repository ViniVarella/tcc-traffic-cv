"""Testes da fase exclusiva de pedestres na camada de segurança."""

from __future__ import annotations

import unittest

from controller import DqnTrafficController
from controller.phase_manager import PhaseManager


PHASES = {"primary_green": 0, "primary_yellow": 1, "all_red": 2, "secondary_green": 3, "secondary_yellow": 4,
          "pedestrian_green": 5, "pedestrian_clearance": 6}
CONFIG = {
    "traffic_light": {"phases": PHASES},
    "traffic_control": {"min_green_seconds": 10, "max_green_seconds": 40, "yellow_seconds": 3, "all_red_seconds": 1},
    "pedestrians": {"every_cycles": 2, "green_seconds": 41, "clearance_seconds": 3},
}


def run_until(controller: DqnTrafficController, start: int, phase: str, action: int = 1, limit: int = 400) -> int:
    """Avança de segundo em segundo (pedindo ``action``) até entrar em ``phase``; devolve o instante."""
    for time in range(start, start + limit):
        decision = controller.update(time, action)
        if decision["phase_name"] == phase and decision["action"] == "set_phase":
            return time
    raise AssertionError(f"{phase} não foi alcançada")


class PedestrianPhaseTests(unittest.TestCase):
    def test_pedestrian_phase_comes_after_every_second_south_green(self) -> None:
        controller = DqnTrafficController("tls", CONFIG, pedestrian_phase=True)
        sequence, time = [], 0
        for _ in range(6):
            time = run_until(controller, time + 1, PhaseManager.SOUTH_GREEN)
            sequence.append("S")
            time = run_until(controller, time + 1, PhaseManager.ALL_RED)
            following = run_until(controller, time + 1, PhaseManager.EAST_WEST_GREEN)
            if any(name == PhaseManager.PEDESTRIAN_GREEN for name in controller.history[-4:]):
                sequence.append("P")
            time = following
        self.assertEqual(sequence, ["S", "S", "P", "S", "S", "P", "S", "S", "P"])

    def test_pedestrian_green_and_clearance_last_their_configured_time(self) -> None:
        controller = DqnTrafficController("tls", CONFIG, pedestrian_phase=True)
        time = run_until(controller, 1, PhaseManager.SOUTH_GREEN)
        time = run_until(controller, time + 1, PhaseManager.SOUTH_GREEN)
        green = run_until(controller, time + 1, PhaseManager.PEDESTRIAN_GREEN)
        clearance = run_until(controller, green + 1, PhaseManager.PEDESTRIAN_CLEARANCE)
        back = run_until(controller, clearance + 1, PhaseManager.EAST_WEST_GREEN)
        self.assertEqual((clearance - green, back - clearance), (41, 3))
        self.assertEqual(controller.phase_manager.get_current_phase().phase_index, 0)

    def test_policy_cannot_end_the_pedestrian_phase(self) -> None:
        controller = DqnTrafficController("tls", CONFIG, pedestrian_phase=True)
        time = run_until(controller, 1, PhaseManager.SOUTH_GREEN)
        time = run_until(controller, time + 1, PhaseManager.SOUTH_GREEN)
        green = run_until(controller, time + 1, PhaseManager.PEDESTRIAN_GREEN)
        decision = controller.update(green + 5, controller.SWITCH)
        self.assertEqual((decision["action"], decision["reason"]), ("hold", "pedestrian_green_in_progress"))

    def test_preemption_never_interrupts_the_pedestrian_phase_and_follows_it(self) -> None:
        controller = DqnTrafficController("tls", CONFIG, pedestrian_phase=True)
        time = run_until(controller, 1, PhaseManager.SOUTH_GREEN)
        time = run_until(controller, time + 1, PhaseManager.SOUTH_GREEN)
        green = run_until(controller, time + 1, PhaseManager.PEDESTRIAN_GREEN)
        self.assertEqual(controller.update_preemption(green + 1, PhaseManager.SOUTH_GREEN)["reason"], "pedestrian_green_in_progress")
        clearance = run_until(controller, green + 1, PhaseManager.PEDESTRIAN_CLEARANCE)
        decision = controller.update_preemption(clearance + 3, PhaseManager.SOUTH_GREEN)
        self.assertEqual((decision["phase_name"], decision["reason"]), (PhaseManager.SOUTH_GREEN, "pedestrian_clearance_complete"))

    def test_preemption_defers_a_pending_pedestrian_phase_to_the_next_opportunity(self) -> None:
        controller = DqnTrafficController("tls", CONFIG, pedestrian_phase=True)
        time = run_until(controller, 1, PhaseManager.SOUTH_GREEN)
        time = run_until(controller, time + 1, PhaseManager.SOUTH_GREEN)
        yellow = run_until(controller, time + 1, PhaseManager.SOUTH_YELLOW)
        all_red = run_until(controller, yellow + 1, PhaseManager.ALL_RED)
        decision = controller.update_preemption(all_red + 1, PhaseManager.EAST_WEST_GREEN)
        self.assertEqual(decision["phase_name"], PhaseManager.EAST_WEST_GREEN)
        # Sem viatura, a fase de pedestres adiada vem logo depois do próximo verde Sul.
        time = run_until(controller, all_red + 2, PhaseManager.SOUTH_GREEN)
        self.assertEqual(run_until(controller, time + 1, PhaseManager.PEDESTRIAN_GREEN) > time, True)

    def test_without_pedestrian_phase_the_cycle_is_unchanged(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        time = 0
        for _ in range(4):
            time = run_until(controller, time + 1, PhaseManager.SOUTH_GREEN)
        self.assertNotIn(PhaseManager.PEDESTRIAN_GREEN, controller.history)

    def test_pedestrian_phase_requires_its_configuration(self) -> None:
        config = {**CONFIG, "traffic_light": {"phases": {key: value for key, value in PHASES.items() if not key.startswith("pedestrian")}}}
        with self.assertRaises(ValueError):
            DqnTrafficController("tls", config, pedestrian_phase=True)

    def test_greens_until_pedestrian_phase(self) -> None:
        controller = DqnTrafficController("tls", CONFIG, pedestrian_phase=True)
        self.assertEqual(controller.greens_until_pedestrian(), 3)  # L/O agora, depois S, L/O, S
        time = run_until(controller, 1, PhaseManager.SOUTH_GREEN)
        self.assertEqual(controller.greens_until_pedestrian(), 2)
        time = run_until(controller, time + 1, PhaseManager.EAST_WEST_GREEN)
        self.assertEqual(controller.greens_until_pedestrian(), 1)
        run_until(controller, time + 1, PhaseManager.SOUTH_GREEN)
        self.assertEqual(controller.greens_until_pedestrian(), 0)
        self.assertIsNone(DqnTrafficController("tls", CONFIG).greens_until_pedestrian())


if __name__ == "__main__":
    unittest.main()
