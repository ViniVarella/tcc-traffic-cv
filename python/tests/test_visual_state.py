"""Testes do contrato visual que alimenta o DQN."""

from __future__ import annotations

import unittest

import numpy as np

from vision.visual_state import VisualStateEncoder


class VisualStateEncoderTests(unittest.TestCase):
    def test_encodes_seven_lanes_phase_and_elapsed_time(self) -> None:
        encoder = VisualStateEncoder(max_lane_count=10, phase_count=5, max_green_seconds=40)
        state = encoder.encode({"south": {"lane_0": 5}, "east": {"lane_1": 2}, "west": {"lane_0": 11}}, 3, 20)
        self.assertEqual(encoder.state_size, 13)
        np.testing.assert_allclose(
            state,
            [0.5, 0.0, 0.0, 0.0, 0.0, 0.2, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.5],
        )
