"""Testes das validações do painel web (sem SUMO, Unity nem thread)."""

from __future__ import annotations

import argparse
from pathlib import Path
import unittest

from dashboard.app import EpisodeRunner, PanelSettings, StartRequest


BASE_DIR = Path(__file__).resolve().parents[1]


class EpisodeRunnerValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = EpisodeRunner(PanelSettings(BASE_DIR, argparse.Namespace()))
        # Checkpoints fictícios que "existem": a validação não depende dos artefatos locais.
        self.runner.checkpoints = {key: BASE_DIR / "configs" / "sp.yaml" for key in self.runner.checkpoints}

    def test_v3_requires_pedestrian_scenario(self) -> None:
        with self.assertRaises(ValueError):
            self.runner.start(StartRequest(scenario="calibrated", version="v3"))
        self.runner.start(StartRequest(scenario="calibrated_ped", version="v3"))
        self.assertTrue(self.runner.state["is_running"])

    def test_unknown_options_and_missing_checkpoint_are_rejected(self) -> None:
        for request in (StartRequest(scenario="calibrated_motos"), StartRequest(version="v1.1"), StartRequest(preemption="radio")):
            with self.assertRaises(ValueError):
                self.runner.start(request)
        self.runner.checkpoints["v2"] = BASE_DIR / "nao-existe.pt"
        with self.assertRaises(ValueError):
            self.runner.start(StartRequest(version="v2"))

    def test_second_start_and_idle_dispatch_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.runner.dispatch_emergency("south")
        self.runner.start(StartRequest())
        with self.assertRaises(ValueError):
            self.runner.start(StartRequest())
        self.runner.dispatch_emergency("east")
        self.runner.dispatch_emergency("south", "west")
        for approach, exit_name in (("north", None), ("west", "north"), ("east", "east")):
            with self.assertRaises(ValueError):
                self.runner.dispatch_emergency(approach, exit_name)

    def test_emergency_routes_follow_the_config(self) -> None:
        self.assertEqual(self.runner.emergency_routes(),
                         {"south": ["east", "north", "west"], "east": ["north", "west"], "west": ["east"]})


if __name__ == "__main__":
    unittest.main()
