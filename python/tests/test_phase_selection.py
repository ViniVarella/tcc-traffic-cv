"""Testes da seleção livre de fase: layout, segurança, máscara, estado, políticas e agente."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from controller.phase_selection_agent import PhaseAgentConfig, PhaseSelectionAgent
from controller.phase_selection_controller import PhaseSelectionController, all_red_state, yellow_state
from controller.phase_selection_policies import FixedTimePhasePolicy, MaxPressurePhasePolicy
from controller.phase_selection_state import ROW_FEATURE_NAMES, PhaseObservation, PhaseStateEncoder, split_state
from experiments.phase_selection_environment import decision_mask, max_red_seconds
from sumo.intersection import green_phases, roi_geometry
from vision.lane_features import LaneFeatures


GREENS = ("GGrrrr", "rrGGrr", "rrrrGG")


def features(stopped: int = 0, count: int | None = None) -> LaneFeatures:
    return LaneFeatures(stopped if count is None else count, stopped, 0.1 * stopped, 0.0 if stopped else None, 5.0 * stopped)


class IntersectionTests(unittest.TestCase):
    def test_green_phases_skip_yellow_and_repeated_states(self) -> None:
        states = [("GGgrr", 30), ("yygrr", 3), ("rrGrr", 10), ("rrrrr", 1), ("rrrGG", 30), ("GGgrr", 30)]
        lanes = {0: "a_0", 1: "a_1", 2: "a_1", 3: "b_0", 4: "b_0"}
        greens = green_phases(states, lanes)
        self.assertEqual([green.state for green in greens], ["GGgrr", "rrGrr", "rrrGG"])
        self.assertEqual(greens[0].lanes, ("a_0", "a_1"))
        self.assertEqual(greens[1].lanes, ("a_1",))  # faixa compartilhada conta nas duas fases

    def test_program_needs_two_green_phases(self) -> None:
        with self.assertRaises(ValueError):
            green_phases([("GG", 30), ("yy", 3)], {0: "a_0", 1: "a_0"})

    def test_roi_is_the_last_meters_before_the_stop_line(self) -> None:
        geometry = roi_geometry("in_E_2", 190.0, 60.0)
        self.assertEqual((geometry.camera_id, geometry.lane_id, geometry.roi_start_m, geometry.roi_end_m), ("in_E", "lane_2", 130.0, 190.0))
        self.assertEqual(roi_geometry("x_0", 40.0, 60.0).roi_start_m, 0.0)


class TransitionStateTests(unittest.TestCase):
    def test_yellow_only_where_green_ends(self) -> None:
        self.assertEqual(yellow_state("GGgrr", "rrGGr"), "yygrr")
        self.assertEqual(all_red_state("GGgrr", "rrGGr"), "rrgrr")

    def test_lengths_must_match(self) -> None:
        with self.assertRaises(ValueError):
            yellow_state("GG", "rrr")


class PhaseSelectionControllerTests(unittest.TestCase):
    def test_any_to_any_transition_never_skips_yellow_or_all_red(self) -> None:
        controller = PhaseSelectionController("tls", GREENS)
        self.assertEqual(controller.update(9, 2)["reason"], "min_green_not_reached")
        decision = controller.update(10, 2)
        self.assertEqual((decision["phase_name"], decision["state"]), ("yellow", "yyrrrr"))
        self.assertEqual(controller.update(12, 1)["reason"], "yellow_in_progress")
        self.assertEqual(controller.update(13, None)["state"], "rrrrrr")
        decision = controller.update(14, None)
        self.assertEqual((decision["phase_name"], decision["state"]), ("green_2", "rrrrGG"))

    def test_choosing_the_current_phase_keeps_it(self) -> None:
        controller = PhaseSelectionController("tls", GREENS)
        self.assertEqual(controller.update(20, 0)["reason"], "policy_keep")
        self.assertTrue(controller.is_green)

    def test_max_green_forces_a_change(self) -> None:
        controller = PhaseSelectionController("tls", GREENS)
        decision = controller.update(40, 0)
        self.assertEqual((decision["reason"], controller.target), ("max_green_reached", 1))

    def test_superset_phase_skips_the_yellow(self) -> None:
        controller = PhaseSelectionController("tls", ("GGrr", "GGGG"))
        decision = controller.update(10, 1)
        self.assertEqual((decision["phase_name"], decision["state"]), ("green_1", "GGGG"))

    def test_red_time_starts_when_the_green_ends(self) -> None:
        controller = PhaseSelectionController("tls", GREENS)
        self.assertEqual(controller.red_time(0, 5), 0.0)
        self.assertEqual(controller.red_time(2, 5), 5.0)
        controller.update(10, 1)
        self.assertEqual(controller.red_time(0, 30), 20.0)

    def test_first_apply_imposes_the_state(self) -> None:
        controller = PhaseSelectionController("tls", GREENS)
        client = RecordingClient()
        controller.apply(client, controller.update(1, None))
        controller.apply(client, controller.update(2, None))
        self.assertEqual(client.calls, [("tls", "GGrrrr")])


class DecisionMaskTests(unittest.TestCase):
    GROUPS = ((("a", "lane_0"),), (("b", "lane_0"),), (("c", "lane_0"),))

    def test_max_green_removes_the_current_phase(self) -> None:
        controller = PhaseSelectionController("tls", GREENS)
        lanes = {key: features() for group in self.GROUPS for key in group}
        self.assertEqual(decision_mask(controller, 20, lanes, self.GROUPS, 200), (True, True, True))
        self.assertEqual(decision_mask(controller, 40, lanes, self.GROUPS, 200), (False, True, True))

    def test_starving_phase_with_stopped_vehicles_is_the_only_option(self) -> None:
        controller = PhaseSelectionController("tls", GREENS)
        lanes = {("a", "lane_0"): features(3), ("b", "lane_0"): features(0), ("c", "lane_0"): features(2)}
        self.assertEqual(decision_mask(controller, 30, lanes, self.GROUPS, 25), (False, False, True))

    def test_fixed_time_never_reaches_the_fairness_limit(self) -> None:
        self.assertEqual(max_red_seconds(4, 40, 3, 1), 132)
        self.assertEqual(max_red_seconds(2, 40, 3, 1), 44)


class PhaseStateEncoderTests(unittest.TestCase):
    def test_state_has_fixed_size_padding_and_mask(self) -> None:
        encoder = PhaseStateEncoder(max_phases=4, max_red_s=100)
        groups = ((("a", "lane_0"),), (("b", "lane_0"), ("b", "lane_1")), (("c", "lane_0"),))
        lanes = {("a", "lane_0"): features(4), ("b", "lane_0"): features(8), ("c", "lane_0"): features(0)}
        capacities = {key: 8.0 for group in groups for key in group}
        observation = encoder.encode(lanes, groups, capacities, 0, 20, [0, 50, 200], (True, True, False))
        self.assertEqual(observation.state.shape, (4 * (len(ROW_FEATURE_NAMES) + 1),))
        rows, mask = split_state(observation.state, 4, len(ROW_FEATURE_NAMES))
        np.testing.assert_allclose(rows[0, 1, :2], [0.5, 0.5])  # 8 de 16 vagas no grupo b
        np.testing.assert_allclose(rows[0, 1, 5:7], [0.5, 0.5])  # contexto: fase atual (a)
        np.testing.assert_allclose(rows[0, :3, 10:13], [[1, 0.5, 0], [0, 0.5, 0.5], [0, 0.5, 1]])
        self.assertFalse(rows[0, 3].any())
        self.assertEqual(mask[0].tolist(), [True, True, False, False])
        self.assertEqual((observation.stopped, observation.lane_counts), ((4, 8, 0), (1, 2, 1)))

    def test_rejects_more_phases_than_supported(self) -> None:
        encoder = PhaseStateEncoder(max_phases=2)
        with self.assertRaises(ValueError):
            encoder.encode({}, ((), (), ()), {}, 0, 0, [0, 0, 0], (True, True, True))


def observation(current: int, stopped: tuple[int, ...], mask: tuple[bool, ...], elapsed: float = 20.0) -> PhaseObservation:
    return PhaseObservation(np.zeros(1), current, mask, stopped, tuple(1 for _ in stopped), elapsed)


class PolicyTests(unittest.TestCase):
    def test_fixed_time_follows_program_order_with_clamped_durations(self) -> None:
        policy = FixedTimePhasePolicy([30, 5, 42])
        self.assertEqual(policy.durations_s, (30, 10, 40))
        self.assertEqual(policy(observation(0, (0, 0, 0), (True, True, True), 25)), 0)
        self.assertEqual(policy(observation(0, (0, 0, 0), (True, True, True), 30)), 1)
        self.assertEqual(policy(observation(2, (0, 0, 0), (False, True, False), 40)), 1)  # pula a fase fora da máscara

    def test_max_pressure_jumps_to_the_most_loaded_phase(self) -> None:
        policy = MaxPressurePhasePolicy()
        self.assertEqual(policy(observation(0, (2, 3, 9), (True, True, True))), 2)
        self.assertEqual(policy(observation(0, (8, 3, 9), (True, True, True))), 0)  # 9 não supera 8 + 2
        self.assertEqual(policy(observation(0, (0, 0, 0), (True, True, True))), 0)
        self.assertEqual(policy(observation(0, (8, 3, 1), (False, True, True))), 1)


class PhaseSelectionAgentTests(unittest.TestCase):
    CONFIG = PhaseAgentConfig(max_phases=3, min_replay_size=4, batch_size=4, target_update_interval=2)

    def state(self, mask: tuple[bool, ...]) -> np.ndarray:
        rows = np.random.default_rng(0).random(3 * self.CONFIG.row_size)
        return np.concatenate([rows, np.asarray(mask, dtype=np.float32)]).astype(np.float32)

    def test_actions_respect_the_mask(self) -> None:
        agent = PhaseSelectionAgent(self.CONFIG, seed=1)
        state = self.state((False, True, False))
        self.assertEqual({agent.select_action(state, epsilon=1.0) for _ in range(20)}, {1})
        self.assertEqual(agent.select_action(state, epsilon=0.0), 1)
        with self.assertRaises(ValueError):
            agent.remember(state, 0, -0.1, state, False)

    def test_train_step_save_and_load(self) -> None:
        agent = PhaseSelectionAgent(self.CONFIG, seed=1)
        for action in (0, 1, 2, 0):
            agent.remember(self.state((True, True, True)), action, -0.5, self.state((True, False, True)), False, discount=0.9)
        self.assertIsNotNone(agent.train_step())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.pt"
            agent.save(path, {"scenarios": ["x"]})
            loaded = PhaseSelectionAgent.load(path)
        state = self.state((True, True, True))
        np.testing.assert_allclose(loaded.q_values(state), agent.q_values(state), rtol=1e-6)
        self.assertEqual(loaded.metadata, {"scenarios": ["x"]})


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def set_traffic_light_state(self, tls_id: str, state: str) -> None:
        self.calls.append((tls_id, state))


if __name__ == "__main__":
    unittest.main()
