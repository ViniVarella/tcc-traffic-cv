"""Testes do contrato visual que alimenta o DQN."""

from __future__ import annotations

import unittest

import numpy as np

from pathlib import Path

import yaml

from vision.lane_features import LaneFeatures
from vision.visual_state import SP_LANE_ORDER, LaneFeatureStateEncoder, VisualStateEncoder, build_state_encoder


SP_CONFIG = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs" / "sp.yaml").read_text(encoding="utf-8"))


class VisualStateEncoderTests(unittest.TestCase):
    def test_encodes_seven_lanes_phase_and_elapsed_time(self) -> None:
        encoder = VisualStateEncoder(max_lane_count=10, phase_count=5, max_green_seconds=40)
        state = encoder.encode({"south": {"lane_0": 5}, "east": {"lane_1": 2}, "west": {"lane_0": 11}}, 3, 20)
        self.assertEqual(encoder.state_size, 13)
        np.testing.assert_allclose(
            state,
            [0.5, 0.0, 0.0, 0.0, 0.0, 0.2, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.5],
        )


class LaneFeatureStateEncoderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.encoder = LaneFeatureStateEncoder({key: 4.0 for key in SP_LANE_ORDER}, phase_count=5, max_green_seconds=40.0,
                                               max_speed_mps=10.0, waiting_reference_seconds=50.0)

    def test_state_has_five_features_per_lane_phase_and_elapsed(self) -> None:
        self.assertEqual(self.encoder.state_size, 41)
        self.assertEqual(len(self.encoder.feature_names), 41)
        self.assertEqual(self.encoder.feature_names[:5], tuple(f"south/lane_0/{name}" for name in ("count", "stopped", "occupancy", "speed", "waiting")))

    def test_features_are_normalized_by_roi_capacity(self) -> None:
        features = {("east", "lane_1"): LaneFeatures(vehicle_count=2, stopped_count=1, occupancy=0.3, mean_speed_mps=5.0, waiting_time_s=40.0)}
        state = self.encoder.encode(features, phase_index=3, phase_elapsed_seconds=10.0)
        east_1 = SP_LANE_ORDER.index(("east", "lane_1")) * 5
        np.testing.assert_allclose(state[east_1:east_1 + 5], [0.5, 0.25, 0.3, 0.5, 0.2])
        np.testing.assert_allclose(state[35:], [0, 0, 0, 1, 0, 0.25])

    def test_missing_or_empty_lane_reads_as_free_flow_and_values_are_clipped(self) -> None:
        saturated = {("west", "lane_0"): LaneFeatures(9, 9, 1.0, None, 9999.0)}
        state = self.encoder.encode(saturated, 0, 90.0)
        np.testing.assert_allclose(state[:5], [0, 0, 0, 1, 0])  # south/lane_0 ausente
        np.testing.assert_allclose(state[30:35], [1, 1, 1, 1, 1])
        self.assertEqual(state[-1], 1.0)
        self.assertTrue(((state >= 0) & (state <= 1)).all())

    def test_missing_capacity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LaneFeatureStateEncoder({("south", "lane_0"): 3.0})


class BuildStateEncoderTests(unittest.TestCase):
    def test_sp_profile_declares_v2_with_matching_size(self) -> None:
        encoder = build_state_encoder(SP_CONFIG, SP_CONFIG["dqn"]["state_version"])
        self.assertIsInstance(encoder, LaneFeatureStateEncoder)
        self.assertEqual(encoder.state_size, SP_CONFIG["dqn"]["state_size"])
        # Capacidades vêm das ROIs medidas (60 m / 7,5 m = 8 veículos parados).
        self.assertAlmostEqual(encoder.capacities[("east", "lane_0")], 60.0 / 7.5)

    def test_version_1_keeps_legacy_contract(self) -> None:
        self.assertEqual(build_state_encoder(SP_CONFIG, 1).state_size, 13)
        with self.assertRaises(ValueError):
            build_state_encoder(SP_CONFIG, 3)


if __name__ == "__main__":
    unittest.main()
