"""Testes da seleção livre de fase: layout, segurança, máscara, estado, políticas e agente."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from paths import PYTHON_DIR
from controller.phase_selection.agent import PhaseAgentConfig, PhaseSelectionAgent
from controller.phase_selection.controller import PhaseSelectionController, all_red_state, yellow_state
from controller.phase_selection.policies import FixedTimePhasePolicy, MaxPressurePhasePolicy
from controller.phase_selection.state import ROW_FEATURE_NAMES, PhaseObservation, PhaseStateEncoder, split_state
from simulation.phase_selection_environment import decision_mask, max_red_seconds, pedestrian_hcm_delay
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

    def test_pedestrian_phase_follows_the_configured_green(self) -> None:
        controller = PhaseSelectionController("tls", GREENS, pedestrian_after=2, pedestrian_s=18)
        self.assertEqual((controller.switch_seconds(2, 0), controller.switch_seconds(0, 2), controller.leave_seconds(2)), (22, 4, 22))
        controller.update(10, 2)  # 0 → 2: sem pedestres
        controller.update(13, None)
        self.assertEqual(controller.update(14, None)["phase_name"], "green_2")
        controller.update(24, 0)  # sai do verde 2: amarelo, all-red e pedestres
        controller.update(27, None)
        decision = controller.update(28, None)
        self.assertEqual((decision["phase_name"], decision["state"]), ("pedestrian", "rrrrrr"))
        self.assertEqual(controller.update(45, None)["reason"], "pedestrian_in_progress")
        self.assertEqual(controller.update(46, None)["phase_name"], "green_0")
        self.assertEqual(controller.red_time(2, 46), 22.0)

    def test_pedestrian_phase_by_time_comes_from_any_green(self) -> None:
        controller = PhaseSelectionController("tls", GREENS, pedestrian_s=18, pedestrian_interval_s=30)
        self.assertFalse(controller.pedestrian_due(29))
        self.assertEqual(controller.leave_seconds(1, 29), 4)
        controller.update(10, 1)  # antes do prazo: troca normal, sem pedestres
        controller.update(13, None)
        self.assertEqual(controller.update(14, None)["phase_name"], "green_1")
        self.assertTrue(controller.pedestrian_due(30))
        self.assertEqual((controller.leave_seconds(1, 30), controller.switch_seconds(1, 2, 30)), (22, 22))
        decision = controller.update(30, 2)  # pendente: sai do verde 1 rumo aos pedestres
        self.assertEqual(decision["state"], "rryyrr")  # amarelo em todos os links verdes, não só nos que acabam
        self.assertEqual(controller.update(33, None)["state"], "rrrrrr")
        self.assertEqual(controller.update(34, None)["phase_name"], "pedestrian")
        self.assertEqual(controller.update(52, None)["phase_name"], "green_2")  # depois, o verde que a política pediu
        self.assertEqual(controller.pedestrian_starts, [34.0])
        self.assertFalse(controller.pedestrian_due(81))
        self.assertTrue(controller.pedestrian_due(82))

    def test_pedestrian_phase_by_time_cannot_be_avoided_by_holding_the_green(self) -> None:
        controller = PhaseSelectionController("tls", GREENS, pedestrian_s=18, pedestrian_interval_s=30)
        for second in range(1, 40):
            controller.update(second, 0)  # a política só pede para manter
        controller.update(40, 0)  # verde máximo: troca forçada, com os pedestres pendentes
        controller.update(43, None)
        self.assertEqual(controller.update(44, None)["phase_name"], "pedestrian")

    def test_pedestrian_rules_are_exclusive(self) -> None:
        with self.assertRaises(ValueError):
            PhaseSelectionController("tls", GREENS, pedestrian_after=1, pedestrian_s=18, pedestrian_interval_s=30)

    def test_hcm_pedestrian_delay_from_phase_starts(self) -> None:
        delay = pedestrian_hcm_delay([100.0, 160.0, 240.0], green_s=7)
        self.assertAlmostEqual(delay["mean_wait_s"], (53 ** 2 + 73 ** 2) / (2 * 140))
        self.assertEqual((delay["max_wait_s"], delay["mean_interval_s"], delay["phases"]), (73, 70, 3))
        self.assertIsNone(pedestrian_hcm_delay([100.0], green_s=7))

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
        observation = encoder.encode(lanes, groups, capacities, 0, 20, [0, 50, 200], (True, True, False), [0, 4, 4], [4, 4, 22])
        self.assertEqual(observation.state.shape, (4 * (len(ROW_FEATURE_NAMES) + 1),))
        rows, mask = split_state(observation.state, 4, len(ROW_FEATURE_NAMES))
        index = {name: position for position, name in enumerate(ROW_FEATURE_NAMES)}
        np.testing.assert_allclose(rows[0, 1, :2], [0.5, 0.5])  # 8 de 16 vagas no grupo b
        np.testing.assert_allclose(rows[0, 1, [index["current_count"], index["current_stopped"]]], [0.5, 0.5])  # fase atual (a)
        tail = [index["is_current"], index["green_elapsed"], index["red_time"]]
        np.testing.assert_allclose(rows[0, :3][:, tail], [[1, 0.5, 0], [0, 0.5, 0.5], [0, 0.5, 1]])
        self.assertFalse(rows[0, 3].any())
        self.assertEqual(mask[0].tolist(), [True, True, False, False])
        self.assertEqual((observation.stopped, observation.lane_counts), ((4, 8, 0), (1, 2, 1)))

    def test_absolute_counts_separate_one_lane_from_three(self) -> None:
        encoder = PhaseStateEncoder(max_phases=2)
        groups = ((("a", "lane_0"),), (("b", "lane_0"), ("b", "lane_1"), ("b", "lane_2")))
        lanes = {("a", "lane_0"): features(2), ("b", "lane_0"): features(2), ("b", "lane_1"): features(2), ("b", "lane_2"): features(2)}
        capacities = {key: 8.0 for group in groups for key in group}
        rows, _ = split_state(encoder.encode(lanes, groups, capacities, 0, 20, [0, 30], (True, True), [0, 4], [4, 4]).state,
                              2, len(ROW_FEATURE_NAMES))
        index = {name: position for position, name in enumerate(ROW_FEATURE_NAMES)}
        self.assertAlmostEqual(rows[0, 0, index["stopped"]], rows[0, 1, index["stopped"]])  # mesma densidade
        np.testing.assert_allclose(rows[0, :, index["stopped_vehicles"]], [2 / 16, 6 / 16])
        np.testing.assert_allclose(rows[0, :, index["lane_count"]], [1 / 4, 3 / 4])

    def test_switch_costs_enter_the_rows_and_are_required(self) -> None:
        encoder = PhaseStateEncoder(max_phases=2)
        groups = ((("a", "lane_0"),), (("b", "lane_0"),))
        lanes = {key: features(1) for group in groups for key in group}
        capacities = {key: 8.0 for group in groups for key in group}
        rows, _ = split_state(encoder.encode(lanes, groups, capacities, 1, 20, [24, 0], (True, True), [22, 0], [4, 22]).state,
                              2, len(ROW_FEATURE_NAMES))
        index = {name: position for position, name in enumerate(ROW_FEATURE_NAMES)}
        np.testing.assert_allclose(rows[0, :, index["switch_in"]], [22 / 30, 0.0])
        np.testing.assert_allclose(rows[0, :, index["switch_out"]], [4 / 30, 22 / 30])
        with self.assertRaises(ValueError):
            encoder.encode(lanes, groups, capacities, 1, 20, [24, 0], (True, True))

    def test_version_2_rows_keep_their_size(self) -> None:
        from controller.phase_selection.state import ROW_FEATURE_NAMES_V2

        encoder = PhaseStateEncoder(max_phases=2, state_version="phase_select_2")
        groups = ((("a", "lane_0"),), (("b", "lane_0"),))
        lanes = {key: features(1) for group in groups for key in group}
        observation = encoder.encode(lanes, groups, {key: 8.0 for key in lanes}, 0, 20, [0, 24], (True, True))
        self.assertEqual(observation.state.shape, (2 * (len(ROW_FEATURE_NAMES_V2) + 1),))

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
        rows = np.random.default_rng(0).random(3 * self.CONFIG.row_size) + 0.1  # toda fase existe (faixas > 0)
        return np.concatenate([rows, np.asarray(mask, dtype=np.float32)]).astype(np.float32)

    def test_actions_respect_the_mask(self) -> None:
        agent = PhaseSelectionAgent(self.CONFIG, seed=1)
        state = self.state((False, True, False))
        self.assertEqual({agent.select_action(state, epsilon=1.0) for _ in range(20)}, {1})
        self.assertEqual(agent.select_action(state, epsilon=0.0), 1)
        with self.assertRaises(ValueError):
            agent.remember(state, 0, -0.1, state, False)

    def test_scores_follow_the_phase_not_its_position(self) -> None:
        agent = PhaseSelectionAgent(self.CONFIG, seed=1)
        rows = np.random.default_rng(3).random((3, self.CONFIG.row_size)).astype(np.float32) + 0.1
        state = np.concatenate([rows.reshape(-1), np.ones(3, dtype=np.float32)])
        swapped = np.concatenate([rows[[2, 0, 1]].reshape(-1), np.ones(3, dtype=np.float32)])
        np.testing.assert_allclose(agent.q_values(swapped), agent.q_values(state)[[2, 0, 1]], rtol=1e-5)

    def test_padding_does_not_change_the_scores(self) -> None:
        small = PhaseSelectionAgent(PhaseAgentConfig(max_phases=2), seed=1)
        large = PhaseSelectionAgent(PhaseAgentConfig(max_phases=4), seed=1)
        large.online.load_state_dict(small.online.state_dict())
        rows = np.random.default_rng(4).random((2, small.config.row_size)).astype(np.float32) + 0.1
        padded = np.concatenate([rows, np.zeros((2, small.config.row_size), dtype=np.float32)])
        q_small = small.q_values(np.concatenate([rows.reshape(-1), np.ones(2, dtype=np.float32)]))
        q_large = large.q_values(np.concatenate([padded.reshape(-1), np.asarray([1, 1, 0, 0], dtype=np.float32)]))
        np.testing.assert_allclose(q_large[:2], q_small, rtol=1e-5)

    def test_demonstrations_teach_the_demonstrated_phase(self) -> None:
        config = PhaseAgentConfig(max_phases=3, min_replay_size=8, batch_size=8, learning_rate=0.01)
        agent = PhaseSelectionAgent(config, seed=1)
        state = self.state((True, True, True))
        for _ in range(16):
            agent.remember(state, 2, -0.1, state, False, discount=0.9, demo=True)
        self.assertEqual(len(agent.replay), 0)
        for _ in range(200):
            agent.train_step()
        self.assertEqual(agent.select_action(state, epsilon=0.0), 2)

    def test_version_2_checkpoints_still_load(self) -> None:
        from controller.phase_selection.state import ROW_FEATURE_NAMES_V2

        old = PhaseSelectionAgent(PhaseAgentConfig(max_phases=3, row_size=len(ROW_FEATURE_NAMES_V2), state_version="phase_select_2"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "v2.pt"
            old.save(path)
            self.assertEqual(PhaseSelectionAgent.load(path).config.state_version, "phase_select_2")

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


class EvaluationStatisticsTests(unittest.TestCase):
    def test_confidence_interval_uses_student_t(self) -> None:
        from simulation.statistics import confidence_interval

        interval = confidence_interval([13.0, 13.3, 12.6])
        self.assertAlmostEqual(interval["mean"], 12.9667, places=4)
        self.assertAlmostEqual(interval["ci95_high"] - interval["mean"], 4.303 * 0.351188 / 3 ** 0.5, places=3)
        self.assertIsNone(confidence_interval([1.0])["ci95_low"])

    def test_reduction_is_paired_by_seed(self) -> None:
        from simulation.statistics import paired_reduction

        reduction = paired_reduction([4.0, 5.0], [10.0, 10.0])
        self.assertAlmostEqual(reduction["mean"], 0.55)


class ScenarioTests(unittest.TestCase):
    def test_pedestrian_variants_double_the_scenarios(self) -> None:
        import yaml

        from simulation.phase_selection_environment import load_scenarios

        base = PYTHON_DIR
        scenarios = load_scenarios(yaml.safe_load((base / "configs" / "generic.yaml").read_text(encoding="utf-8")), base)
        names = {scenario.name: scenario for scenario in scenarios}
        self.assertEqual(names["t-3/media+ped"].pedestrian_s, 18.0)
        self.assertEqual(names["t-3/media"].pedestrian_s, 0.0)
        self.assertNotIn("sp/calibrated+ped", names)  # SP com pedestres só pelo laço oficial (compare_versions)


class VisualKeyTests(unittest.TestCase):
    def test_camera_keys_become_sumo_lane_keys(self) -> None:
        import yaml
        from simulation.phase_selection_environment import camera_key_map, profile_geometries, remap_features

        profile = yaml.safe_load((PYTHON_DIR / "configs" / "sp.yaml").read_text(encoding="utf-8"))
        key_map = camera_key_map(profile)
        self.assertEqual(key_map[("south", "lane_0")], ("E3", "lane_0"))
        self.assertEqual(set(key_map.values()), set(profile_geometries(profile)))  # mesmas chaves das ROIs do ambiente
        self.assertEqual(remap_features({("south", "lane_0"): 1}, key_map), {("E3", "lane_0"): 1})
        self.assertIsNone(remap_features(None, key_map))  # sem frames continua sem frames

    def test_summary_skips_reductions_without_the_metric(self) -> None:
        from simulation.statistics import summarize

        runs = [{"mean_waiting_time_seconds": 4.0, "mean_waiting_time_stopped_seconds": 8.0}]
        summary = summarize(runs, [{"mean_waiting_time_seconds": 10.0}])
        self.assertIn("reduction_mean_waiting_time_seconds", summary)
        self.assertNotIn("reduction_mean_waiting_time_stopped_seconds", summary)


class GlobalPhasePolicyTests(unittest.TestCase):
    def test_sp_phases_and_red_time_in_the_keep_switch_loop(self) -> None:
        from types import SimpleNamespace

        from simulation.version_policies import GlobalPhasePolicy

        config = PYTHON_DIR / "configs" / "generic.yaml"
        import yaml

        sp = yaml.safe_load((config.parent / "sp.yaml").read_text(encoding="utf-8"))
        policy = GlobalPhasePolicy(PhaseSelectionAgent(PhaseAgentConfig(max_phases=8), seed=1), config, sp)
        lanes = {key: features(2) for key in policy.key_map}  # chaves (câmera, faixa) da visão
        state_v2 = np.asarray([0.5], dtype=np.float32)  # último elemento: 20 s de 40
        south = policy.observation(state_v2, lanes, SimpleNamespace(phase_index=3))
        self.assertEqual(south.current, 1)  # programa: 0 = verde L/O, 3 = verde Sul
        rows, _ = split_state(south.state, 8, len(ROW_FEATURE_NAMES))
        red = ROW_FEATURE_NAMES.index("red_time")
        self.assertAlmostEqual(rows[0, 0, red], (20 + 4) / 44)  # verde atual + amarelo + all-red
        self.assertEqual(sum(south.lane_counts), 7)  # as 7 faixas monitoradas do SP
        self.assertIn(policy(state_v2, lanes, SimpleNamespace(phase_index=0)), (0, 1))

    def test_sp_pedestrian_phase_comes_after_the_south_green(self) -> None:
        from types import SimpleNamespace
        import yaml

        from simulation.version_policies import GlobalPhasePolicy

        config = PYTHON_DIR / "configs" / "generic.yaml"
        sp = yaml.safe_load((config.parent / "sp.yaml").read_text(encoding="utf-8"))
        policy = GlobalPhasePolicy(PhaseSelectionAgent(PhaseAgentConfig(max_phases=8), seed=1), config, sp, pedestrian_phase=True)
        lanes = {key: features(2) for key in policy.key_map}
        east_west = policy.observation(np.asarray([0.5], dtype=np.float32), lanes, SimpleNamespace(phase_index=0))
        rows, _ = split_state(east_west.state, 8, len(ROW_FEATURE_NAMES))
        index = {name: position for position, name in enumerate(ROW_FEATURE_NAMES)}
        # Sul ficou no vermelho: verde L/O (20 s) + amarelo/all-red (4 s) + pedestres (18 s).
        self.assertAlmostEqual(rows[0, 1, index["red_time"]], 42 / policy.encoder.max_red_s, places=5)
        np.testing.assert_allclose(rows[0, :2, index["switch_out"]], [4 / 30, 22 / 30])


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def set_traffic_light_state(self, tls_id: str, state: str) -> None:
        self.calls.append((tls_id, state))


if __name__ == "__main__":
    unittest.main()
