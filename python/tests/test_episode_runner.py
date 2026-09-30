"""Testes do laço de episódio v2 e das políticas de referência, com SUMO falso."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

import numpy as np

from controller import DqnAgent, DqnConfig, DqnTrafficController
from controller.policies import FixedCyclePolicy, MaxPressurePolicy
from experiments.episode_runner import DqnPolicy, EpisodeSettings, EpsilonSchedule, RewardModel, incoming_lane_capacity, run_episode
from vision.lane_features import LaneFeatures


CONFIG = {"traffic_light": {"phases": {"primary_green": 0, "primary_yellow": 1, "all_red": 2, "secondary_green": 3, "secondary_yellow": 4}},
          "traffic_control": {"min_green_seconds": 10, "max_green_seconds": 40, "yellow_seconds": 3, "all_red_seconds": 1}}


class FakeSumo:
    def __init__(self, pending: int = 0) -> None:
        self.time = 0.0
        self.pending = pending
        self.phases: list[int] = []

    def step(self) -> float:
        self.time += 1.0
        return self.time

    def get_simulation_events(self) -> dict:
        return {"departed": [], "arrived": []}

    def get_active_vehicle_metrics(self) -> dict:
        return {}

    def get_teleport_count(self) -> int:
        return 0

    def get_incoming_lane_metrics(self, lanes) -> dict:
        return {"halting_vehicles": 6, "waiting_time_s": 0.0, "pending_vehicles": self.pending}

    def set_traffic_light_phase(self, tls_id: str, phase: int) -> None:
        self.phases.append(phase)

    def set_traffic_light_phase_duration(self, tls_id: str, duration: float) -> None:
        pass


class ConstantEncoder:
    state_size = 2

    def encode(self, lane_features, phase_index, elapsed) -> np.ndarray:
        return np.asarray([phase_index / 4.0, min(1.0, elapsed / 40.0)], dtype=np.float32)


class AlwaysSwitch:
    def __call__(self, state, lane_features, phase) -> int:
        return 1


REWARD = RewardModel(lanes=("L",), capacity=12.0)


def _features(south_stopped: int = 0, east_stopped: int = 0) -> dict:
    return {
        ("south", "lane_0"): LaneFeatures(south_stopped, south_stopped, 0.0, None, 0.0),
        ("east", "lane_0"): LaneFeatures(east_stopped, east_stopped, 0.0, None, 0.0),
        ("west", "lane_0"): LaneFeatures(0, 0, 0.0, None, 0.0),
    }


def _run(policy, observe=lambda time: _features(), learner=None, settings=EpisodeSettings(warmup_s=0.0, control_s=60.0), client=None):
    client = client or FakeSumo()
    outcome = run_episode(client=client, controller=DqnTrafficController("tls", CONFIG), observe=observe, encoder=ConstantEncoder(),
                          policy=policy, reward=REWARD, settings=settings, learner=learner)
    return outcome, client


class EpisodeRunnerTests(unittest.TestCase):
    def test_always_switch_policy_decides_only_at_min_green_of_each_phase(self) -> None:
        outcome, client = _run(AlwaysSwitch())
        # Ciclo de 14 s (10 verde + 3 amarelo + 1 all-red): decisões em 10, 24, 38 e 52.
        self.assertEqual((outcome.decisions, outcome.switches, outcome.switch_rate), (4, 4, 1.0))
        self.assertEqual(client.phases[:4], [1, 2, 3, 4])
        self.assertEqual(outcome.controlled_steps, 60)
        self.assertAlmostEqual(outcome.mean_reward, -0.25)  # 0,5 × min(1, 6/12)

    def test_fixed_cycle_never_switches_voluntarily_but_max_green_cycles(self) -> None:
        outcome, client = _run(FixedCyclePolicy(), settings=EpisodeSettings(warmup_s=0.0, control_s=80.0))
        self.assertEqual(outcome.switches, 0)
        self.assertEqual(client.phases, [1, 2, 3])  # forçado pelo verde máximo em 40 s
        self.assertEqual(outcome.phase_seconds["EAST_WEST_GREEN"], 40)

    def test_warmup_uses_fixed_rule_and_is_not_scored(self) -> None:
        outcome, client = _run(FixedCyclePolicy(), settings=EpisodeSettings(warmup_s=60.0, control_s=10.0, warmup_switch_after_s=30.0))
        self.assertEqual(outcome.controlled_steps, 10)
        self.assertEqual(client.phases[0], 1)  # troca aos 30 s no aquecimento
        self.assertEqual(outcome.metrics["warmup_seconds"], 60.0)

    def test_missing_observations_hold_the_green_but_keep_safety(self) -> None:
        outcome, client = _run(AlwaysSwitch(), observe=lambda time: None)
        self.assertEqual((outcome.decisions, outcome.missing_observations), (0, 60))
        self.assertEqual(client.phases[:1], [1])  # só o verde máximo (40 s) troca

    def test_learner_receives_smdp_transitions_including_truncated_last_one(self) -> None:
        agent = DqnAgent(DqnConfig(state_size=2, hidden_size=4, batch_size=2, min_replay_size=2, gamma=0.99), device="cpu")
        outcome, _ = _run(DqnPolicy(agent, EpsilonSchedule(1.0, 1.0, 1)), learner=agent)
        self.assertEqual(outcome.transitions, outcome.decisions)
        discounts = sorted({round(item.discount, 6) for item in agent.replay})
        # Manter: 5 s até a próxima decisão; trocar: 3 + 1 + 10 = 14 s até o próximo verde decidir.
        self.assertTrue(set(discounts) <= {round(0.99 ** k, 6) for k in range(1, 61)})
        self.assertTrue(all(not item.done for item in agent.replay))
        self.assertGreater(len(outcome.losses), 0)

    def test_pending_backlog_is_reported(self) -> None:
        outcome, _ = _run(FixedCyclePolicy(), client=FakeSumo(pending=7))
        self.assertEqual((outcome.metrics["mean_pending_vehicles"], outcome.metrics["final_pending_vehicles"]), (7.0, 7))


class PolicyTests(unittest.TestCase):
    PHASE_EW = SimpleNamespace(name="EAST_WEST_GREEN")

    def test_max_pressure_switches_only_when_opposing_queue_exceeds_switch_cost(self) -> None:
        policy = MaxPressurePolicy(lost_time_s=4.0)  # E/W atende 2 faixas → margem 4
        self.assertEqual(policy(None, _features(south_stopped=6, east_stopped=2), self.PHASE_EW), 0)
        self.assertEqual(policy(None, _features(south_stopped=7, east_stopped=2), self.PHASE_EW), 1)
        self.assertEqual(policy(None, _features(south_stopped=1, east_stopped=0), self.PHASE_EW), 1)
        self.assertEqual(policy(None, _features(), self.PHASE_EW), 0)

    def test_epsilon_schedule_is_linear_by_decision(self) -> None:
        schedule = EpsilonSchedule(1.0, 0.0, 10)
        self.assertEqual([schedule.value(index) for index in (0, 5, 10, 50)], [1.0, 0.5, 0.0, 0.0])

    def test_incoming_capacity(self) -> None:
        self.assertAlmostEqual(incoming_lane_capacity([75.0, 7.5]), 11.0)


if __name__ == "__main__":
    unittest.main()
