"""Testes da recompensa de nível, dos pontos de decisão e das transições SMDP."""

from __future__ import annotations

import unittest

import numpy as np
import torch

from controller import DqnAgent, DqnConfig, DqnTrafficController
from controller.decision_scheduler import DecisionScheduler, SmdpAccumulator
from controller.rewards import RewardWeights, TrafficSnapshot, level_reward


CONFIG = {"traffic_light": {"phases": {"primary_green": 0, "primary_yellow": 1, "all_red": 2, "secondary_green": 3, "secondary_yellow": 4}},
          "traffic_control": {"min_green_seconds": 10, "max_green_seconds": 40, "yellow_seconds": 3, "all_red_seconds": 1}}


class LevelRewardTests(unittest.TestCase):
    def test_reward_is_bounded_between_minus_one_and_zero(self) -> None:
        self.assertEqual(level_reward(TrafficSnapshot(0, 0.0, 0), 60.0), 0.0)
        self.assertEqual(level_reward(TrafficSnapshot(10_000, 1e9, 10_000), 60.0), -1.0)
        self.assertAlmostEqual(level_reward(TrafficSnapshot(30, 0.0, 30), 60.0), -(0.5 * 0.5 + 0.3 * 0.5))

    def test_vehicles_leaving_the_network_never_produce_positive_reward(self) -> None:
        # Antes: espera acumulada caía quando um veículo com muita espera saía.
        before = level_reward(TrafficSnapshot(12, 900.0, 0), 60.0)
        after = level_reward(TrafficSnapshot(11, 300.0, 0), 60.0)
        self.assertLessEqual(after, 0.0)
        self.assertGreater(after, before)

    def test_insertion_backlog_is_penalized(self) -> None:
        self.assertLess(level_reward(TrafficSnapshot(5, 50.0, 40), 60.0), level_reward(TrafficSnapshot(5, 50.0, 0), 60.0))

    def test_weights_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            RewardWeights(halting=0.9, pending=0.3, waiting=0.2)
        with self.assertRaises(ValueError):
            level_reward(TrafficSnapshot(0, 0.0, 0), 0.0)
        self.assertEqual(RewardWeights.from_config({"dqn": {"reward": {"halting": 1.0, "pending": 0.0, "waiting": 0.0}}}).halting, 1.0)


class DecisionSchedulerTests(unittest.TestCase):
    def test_decisions_only_in_green_after_min_green_and_at_interval(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        scheduler = DecisionScheduler(min_green_seconds=10, max_green_seconds=40, interval_s=5)
        decisions = []
        for time in range(0, 41):
            phase = controller.phase_manager.get_current_phase()
            if scheduler.is_decision_point(phase, float(time)):
                scheduler.mark_decision(float(time))
                decisions.append(time)
            controller.update(float(time), controller.KEEP)
        # Verde E/W começa em 0; em 40 o verde máximo força a troca, então não há decisão.
        self.assertEqual(decisions, [10, 15, 20, 25, 30, 35])

    def test_new_green_phase_restarts_the_schedule(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        scheduler = DecisionScheduler(10, 40, 5)
        decisions = []
        for time in range(0, 30):
            phase = controller.phase_manager.get_current_phase()
            action = controller.KEEP
            if scheduler.is_decision_point(phase, float(time)):
                scheduler.mark_decision(float(time))
                decisions.append((time, phase.name))
                action = controller.SWITCH
            controller.update(float(time), action)
        # Troca em 10 → amarelo 10-13, all-red 13-14, verde South em 14 → decisão em 24.
        self.assertEqual(decisions, [(10, "EAST_WEST_GREEN"), (24, "SOUTH_GREEN")])

    def test_missed_decision_happens_at_the_next_available_step(self) -> None:
        controller = DqnTrafficController("tls", CONFIG)
        scheduler = DecisionScheduler(10, 40, 5)
        phase = controller.phase_manager.get_current_phase()
        self.assertTrue(scheduler.is_decision_point(phase, 10.0))  # sem frames: não marca
        self.assertTrue(scheduler.is_decision_point(phase, 11.0))
        scheduler.mark_decision(11.0)
        self.assertFalse(scheduler.is_decision_point(phase, 15.0))
        self.assertTrue(scheduler.is_decision_point(phase, 16.0))


class SmdpAccumulatorTests(unittest.TestCase):
    def test_discounted_sum_and_discount_of_k_steps(self) -> None:
        accumulator = SmdpAccumulator(gamma=0.5)
        accumulator.add(-9.0)  # sem decisão aberta: ignorado
        accumulator.open(np.zeros(2), action=1)
        for reward in (-1.0, -1.0, -1.0):
            accumulator.add(reward)
        transition = accumulator.close(np.ones(2))
        self.assertAlmostEqual(transition.reward, -1.0 - 0.5 - 0.25)
        self.assertAlmostEqual(transition.discount, 0.125)
        self.assertEqual((transition.action, transition.steps), (1, 3))
        self.assertFalse(accumulator.is_open)

    def test_closing_without_steps_yields_nothing(self) -> None:
        accumulator = SmdpAccumulator(gamma=0.99)
        self.assertIsNone(accumulator.close(np.zeros(2)))
        accumulator.open(np.zeros(2), 0)
        self.assertIsNone(accumulator.close(np.zeros(2)))


class DqnDiscountTests(unittest.TestCase):
    def _agent(self, **config) -> DqnAgent:
        return DqnAgent(DqnConfig(state_size=1, hidden_size=4, batch_size=1, min_replay_size=1, target_update_interval=1000,
                                  learning_rate=0.0, **config), device="cpu")

    def test_per_transition_discount_scales_the_bootstrap(self) -> None:
        agent = self._agent(gamma=0.9)
        state = np.array([1.0], dtype=np.float32)
        agent.remember(state, 0, 0.0, state, False, discount=0.25)
        self.assertEqual(agent.replay[0].discount, 0.25)
        agent.remember(state, 0, 0.0, state, False)
        self.assertEqual(agent.replay[1].discount, 0.9)
        with self.assertRaises(ValueError):
            agent.remember(state, 0, 0.0, state, False, discount=1.5)

    def test_double_dqn_evaluates_online_argmax_with_target_network(self) -> None:
        agent = self._agent(double_dqn=True, gamma=1.0)
        with torch.no_grad():
            for network, (online_bias, target_bias) in ((agent.online, (5.0, 1.0)), (agent.target, (0.0, 3.0))):
                for layer in network.layers:
                    if isinstance(layer, torch.nn.Linear):
                        layer.weight.zero_()
                        layer.bias.zero_()
            agent.online.layers[-1].bias.copy_(torch.tensor([5.0, 1.0]))
            agent.target.layers[-1].bias.copy_(torch.tensor([0.0, 3.0]))
        state = np.array([1.0], dtype=np.float32)
        agent.remember(state, 0, 0.0, state, False, discount=1.0)
        loss = agent.train_step()
        # Double: online escolhe a ação 0 (5 > 1), alvo avalia Q_target(0)=0 → alvo 0, Q=5 → Huber(5) = 4,5.
        # DQN comum usaria max Q_target = 3 → Huber(2) = 1,5.
        self.assertAlmostEqual(loss, 4.5, places=5)


if __name__ == "__main__":
    unittest.main()
