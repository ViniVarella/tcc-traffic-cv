"""Testes da preempção para veículos de emergência."""

from __future__ import annotations

import unittest

from controller import DqnTrafficController
from controller.phase_manager import PhaseManager
from controller.preemption import EmergencyPreemption, EmergencyRequest, PreemptionSettings


CONFIG = {"traffic_light": {"phases": {"primary_green": 0, "primary_yellow": 1, "all_red": 2, "secondary_green": 3, "secondary_yellow": 4}},
          "traffic_control": {"min_green_seconds": 10, "max_green_seconds": 40, "yellow_seconds": 3, "all_red_seconds": 1}}
SOUTH, EAST_WEST = PhaseManager.SOUTH_GREEN, PhaseManager.EAST_WEST_GREEN


def _run(controller: DqnTrafficController, times: range, target: str) -> list[tuple[float, str, str]]:
    return [(float(time), (decision := controller.update_preemption(float(time), target))["phase_name"], decision["reason"]) for time in times]


class ControllerPreemptionTests(unittest.TestCase):
    def test_other_green_switches_immediately_without_waiting_min_green(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        steps = _run(controller, range(2, 9), SOUTH)
        # t=2: verde E/W há só 2 s (< 10 s mínimos) e já vai para o amarelo.
        self.assertEqual(steps[0], (2.0, PhaseManager.EAST_WEST_YELLOW, "preemption_switch"))
        self.assertEqual([name for _, name, _ in steps], [PhaseManager.EAST_WEST_YELLOW] * 3 + [PhaseManager.ALL_RED] + [SOUTH] * 3)

    def test_target_green_is_held_beyond_max_green(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        steps = _run(controller, range(1, 61), EAST_WEST)
        self.assertTrue(all(name == EAST_WEST for _, name, _ in steps))
        self.assertEqual(steps[-1][2], "preemption_hold")

    def test_yellow_and_all_red_are_never_skipped(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        controller.update(10.0, controller.SWITCH)  # E/W -> amarelo por decisão normal
        self.assertEqual(controller.update_preemption(11.0, SOUTH)["reason"], "east_west_yellow_in_progress")
        self.assertEqual(controller.update_preemption(13.0, SOUTH)["phase_name"], PhaseManager.ALL_RED)
        self.assertEqual(controller.update_preemption(14.0, SOUTH)["phase_name"], SOUTH)

    def test_all_red_goes_straight_back_to_the_target_green(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        controller.update(10.0, controller.SWITCH)  # rumo ao verde South...
        controller.update(13.0, controller.KEEP)    # all-red
        # ...mas a emergência vem pelo Leste: sai do all-red direto para E/W, sem verde South.
        self.assertEqual(controller.update_preemption(14.0, EAST_WEST)["phase_name"], EAST_WEST)

    def test_invalid_target_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DqnTrafficController("tls", CONFIG).update_preemption(1.0, PhaseManager.ALL_RED)


class EmergencyPreemptionTests(unittest.TestCase):
    def test_activates_only_within_eta_and_locks_until_the_vehicle_passes(self) -> None:
        preemption = EmergencyPreemption(PreemptionSettings(activation_eta_s=20.0))
        self.assertIsNone(preemption.target_green([EmergencyRequest("amb1", "east", 35.0)]))
        self.assertEqual(preemption.target_green([EmergencyRequest("amb1", "east", 18.0)]), EAST_WEST)
        # Outra ambulância mais próxima pelo Sul não rouba o semáforo já travado.
        both = [EmergencyRequest("amb1", "east", 9.0), EmergencyRequest("amb2", "south", 3.0)]
        self.assertEqual(preemption.target_green(both), EAST_WEST)
        # amb1 cruzou a linha: libera e passa a atender amb2.
        self.assertEqual(preemption.target_green([EmergencyRequest("amb2", "south", 2.0)]), SOUTH)
        self.assertEqual(preemption.served, ["amb1"])
        self.assertIsNone(preemption.target_green([]))
        self.assertEqual(preemption.served, ["amb1", "amb2"])

    def test_earliest_arrival_is_served_first(self) -> None:
        preemption = EmergencyPreemption()
        requests = [EmergencyRequest("a", "west", 12.0), EmergencyRequest("b", "south", 6.0)]
        self.assertEqual(preemption.target_green(requests), SOUTH)

    def test_settings_come_from_profile(self) -> None:
        self.assertEqual(PreemptionSettings.from_config({"emergency": {"preemption": {"activation_eta_s": 25}}}).activation_eta_s, 25)
        with self.assertRaises(ValueError):
            PreemptionSettings(activation_eta_s=0)


if __name__ == "__main__":
    unittest.main()
