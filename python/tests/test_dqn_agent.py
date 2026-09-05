"""Testes unitários do agente DQN vetorial."""

from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

import numpy as np
import torch

from controller import DqnAgent, DqnConfig


class DqnAgentTests(unittest.TestCase):
    def test_replay_batch_trains_and_selects_valid_action(self) -> None:
        agent = DqnAgent(
            DqnConfig(state_size=3, hidden_size=8, batch_size=2, min_replay_size=2, replay_capacity=4, target_update_interval=1),
            device="cpu",
        )
        state = np.array([0.0, 0.5, 1.0], dtype=np.float32)
        agent.remember(state, 0, 1.0, state, False)
        agent.remember(state, 1, -1.0, state, True)
        self.assertIsNotNone(agent.train_step())
        self.assertIn(agent.select_action(state, epsilon=0.0, explore=False), {0, 1})

    def test_checkpoint_restores_training_state(self) -> None:
        agent = DqnAgent(
            DqnConfig(state_size=2, hidden_size=4, batch_size=2, min_replay_size=2, target_update_interval=1),
            device="cpu",
        )
        state = np.array([0.0, 1.0], dtype=np.float32)
        agent.remember(state, 0, 1.0, state, False)
        agent.remember(state, 1, -1.0, state, True)
        agent.train_step()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "agent.pt"
            agent.save(path, {"kind": "best_validation", "validation_score": 0.5})
            restored = DqnAgent.load(path, device="cpu")
        self.assertEqual(restored.training_steps, agent.training_steps)
        self.assertTrue(np.allclose(
            restored.online(torch.from_numpy(state)).detach().numpy(),
            agent.online(torch.from_numpy(state)).detach().numpy(),
        ))


if __name__ == "__main__":
    unittest.main()
