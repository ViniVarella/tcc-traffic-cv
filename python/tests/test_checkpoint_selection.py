"""Testes da seleção de checkpoint por validação."""

from __future__ import annotations

import unittest

from experiments.checkpoint_selection import CheckpointSelector, SelectionCriteria, ValidationRecord


def _record(episode: int, score: float | None, steps: int = 10_000, epsilon: float = 0.1, switch_rate: float | None = 0.5) -> ValidationRecord:
    return ValidationRecord(episode, score, steps, epsilon, switch_rate)


class CheckpointSelectorTests(unittest.TestCase):
    def test_untrained_checkpoints_are_never_selected(self) -> None:
        selector = CheckpointSelector()
        self.assertFalse(selector.consider(_record(4, -0.1, steps=240, epsilon=0.98)))
        self.assertFalse(selector.consider(_record(5, -0.1, steps=10_000, epsilon=0.5)))
        self.assertFalse(selector.consider(_record(6, None)))
        self.assertIsNone(selector.best)

    def test_better_scores_replace_and_worse_scores_do_not(self) -> None:
        selector = CheckpointSelector()
        self.assertTrue(selector.consider(_record(10, -0.40)))
        self.assertTrue(selector.consider(_record(20, -0.30)))
        self.assertFalse(selector.consider(_record(30, -0.35)))
        self.assertEqual(selector.best.episode, 20)

    def test_ties_within_tolerance_keep_the_more_trained_checkpoint(self) -> None:
        selector = CheckpointSelector(SelectionCriteria(tie_tolerance=0.01))
        selector.consider(_record(10, -0.300))
        self.assertTrue(selector.consider(_record(20, -0.302)))  # 0,7% pior: empate
        self.assertFalse(selector.consider(_record(30, -0.310)))
        self.assertEqual(selector.best.episode, 20)

    def test_degenerate_policies_are_flagged(self) -> None:
        selector = CheckpointSelector()
        self.assertEqual([selector.degeneracy(rate) for rate in (1.0, 0.96, 0.5, 0.02, None)],
                         ["always_switch", "always_switch", None, "never_switch", None])


if __name__ == "__main__":
    unittest.main()
