"""Testes das políticas das versões avaliadas no mesmo ambiente."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np
import yaml

from experiments.version_policies import DqnV1Policy, HeuristicV1Policy, build_version_policies, lane_counts
from vision.lane_features import LaneFeatures


CONFIG = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs" / "sp.yaml").read_text(encoding="utf-8"))
EAST_WEST = SimpleNamespace(name="EAST_WEST_GREEN", phase_index=0)
SOUTH = SimpleNamespace(name="SOUTH_GREEN", phase_index=3)


def _features(south: int, east: int, west: int = 0) -> dict:
    make = lambda count: LaneFeatures(count, 0, 0.0, None, 0.0)
    return {("south", "lane_0"): make(south), ("east", "lane_0"): make(east), ("west", "lane_0"): make(west)}


class FakeAgent:
    def __init__(self, action: int = 1) -> None:
        self.config = SimpleNamespace(state_version=1)
        self.action = action
        self.states: list[np.ndarray] = []

    def select_action(self, state, epsilon, explore) -> int:
        self.states.append(state)
        return self.action


class VersionPolicyTests(unittest.TestCase):
    def test_lane_counts_groups_by_camera(self) -> None:
        self.assertEqual(lane_counts(_features(3, 1, 2)), {"south": {"lane_0": 3}, "east": {"lane_0": 1}, "west": {"lane_0": 2}})

    def test_heuristic_follows_the_v1_queue_rule(self) -> None:
        policy = HeuristicV1Policy(switch_margin=1)
        self.assertEqual(policy(None, _features(south=3, east=2), EAST_WEST), 1)  # oposta ≥ atual + 1
        self.assertEqual(policy(None, _features(south=2, east=2), EAST_WEST), 0)
        self.assertEqual(policy(None, _features(south=0, east=0), EAST_WEST), 0)  # oposta vazia
        self.assertEqual(policy(None, _features(south=0, east=1), SOUTH), 1)      # atual vazia

    def test_v1_dqn_receives_the_13_input_state(self) -> None:
        agent = FakeAgent()
        policy = DqnV1Policy(agent, CONFIG)
        v2_state = np.zeros(41, dtype=np.float32)
        v2_state[-1] = 0.5  # 20 s de 40 s de verde máximo
        self.assertEqual(policy(v2_state, _features(south=5, east=2), SOUTH), 1)
        state = agent.states[0]
        self.assertEqual(state.shape, (13,))
        np.testing.assert_allclose(state[[0, 4, 6]], [0.5, 0.2, 0.0])  # contagem / max_lane_count (10)
        np.testing.assert_allclose(state[7:], [0, 0, 0, 1, 0, 0.5])

    def test_v1_dqn_rejects_v2_checkpoints(self) -> None:
        agent = FakeAgent()
        agent.config.state_version = 2
        with self.assertRaises(ValueError):
            DqnV1Policy(agent, CONFIG)

    def test_unknown_version_is_rejected_and_intervals_follow_each_version(self) -> None:
        with self.assertRaises(ValueError):
            build_version_policies(CONFIG, ["v9"], Path("x"), Path("y"))
        versions = build_version_policies(CONFIG, ["baseline", "v1", "max_pressure"], Path("x"), Path("y"))
        self.assertEqual([(item.name, item.decision_interval_s) for item in versions], [("baseline", 5.0), ("v1", 1.0), ("max_pressure", 5.0)])


if __name__ == "__main__":
    unittest.main()
