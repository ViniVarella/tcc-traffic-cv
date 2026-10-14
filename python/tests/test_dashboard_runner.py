"""Testes das validações do painel web (sem SUMO, Unity nem thread)."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
import unittest

from dashboard.app import EpisodeRunner, PanelSettings, StartRequest


BASE_DIR = Path(__file__).resolve().parents[1]


class EpisodeRunnerValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = EpisodeRunner(PanelSettings(BASE_DIR, argparse.Namespace()))
        # Checkpoints fictícios que "existem": a validação não depende dos artefatos locais.
        self.runner.checkpoints = {key: BASE_DIR / "configs" / "sp.yaml" for key in self.runner.checkpoints}
        # Simula a thread do episódio viva e a conexão com a Unity aberta.
        self.runner._thread = threading.current_thread()
        self.runner._bridge_ready.set()

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

    def test_v1_heuristic_needs_no_checkpoint(self) -> None:
        self.runner.v1_1_checkpoint = BASE_DIR / "nao-existe.pt"
        self.runner.start(StartRequest(version="v1"))
        self.assertTrue(self.runner.state["is_running"])

    def test_start_is_rejected_when_the_unity_connection_failed(self) -> None:
        self.runner._bridge_ready.clear()
        self.runner.state = {**self.runner.state, "error": "Falha ao abrir a conexão com a Unity: porta em uso"}
        with self.assertRaisesRegex(ValueError, "porta em uso"):
            self.runner.start(StartRequest())

    def test_pending_dispatches_do_not_leak_into_the_next_episode(self) -> None:
        self.runner.start(StartRequest())
        self.runner.dispatch_emergency("south")
        self.runner.state = {**self.runner.state, "is_running": False}  # episódio falhou antes do 1º step
        self.runner._pending.get_nowait()
        self.runner.start(StartRequest())
        self.assertTrue(self.runner._dispatch.empty())

    def test_emergency_routes_follow_the_config(self) -> None:
        self.assertEqual(self.runner.emergency_routes(),
                         {"south": ["east", "north", "west"], "east": ["north", "west"], "west": ["east"]})


if __name__ == "__main__":
    unittest.main()
