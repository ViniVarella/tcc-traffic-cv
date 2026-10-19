"""Testes das validações do painel web (sem SUMO, Unity nem thread)."""

from __future__ import annotations

import argparse
from pathlib import Path
import threading
import unittest

import json
import tempfile

from dashboard.app import FIXED_TIME_REFERENCE_S, SCENARIOS, EpisodeRunner, PanelSettings, StartRequest, load_fixed_time_reference
from experiments.api_server import GENERIC_CLASSES, choose_detector, parse_args


BASE_DIR = Path(__file__).resolve().parents[1]


class EpisodeRunnerValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = EpisodeRunner(PanelSettings(BASE_DIR, argparse.Namespace()))
        # Checkpoints fictícios que "existem": a validação não depende dos artefatos locais.
        self.runner.checkpoints = {key: BASE_DIR / "configs" / "sp.yaml" for key in self.runner.checkpoints}
        # Simula a thread do episódio viva e a conexão com a Unity aberta.
        self.runner._thread = threading.current_thread()
        self.runner._bridge_ready.set()

    def test_experiment_is_not_offered(self) -> None:
        # O DQN estado v3 é experimento: o painel só roda o produto (v2) e as referências.
        with self.assertRaises(ValueError):
            self.runner.start(StartRequest(scenario="calibrated_ped", version="v3"))
        self.runner.start(StartRequest(scenario="calibrated_ped", version="v2"))
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

    def test_generic_detector_refuses_visual_preemption(self) -> None:
        runner = EpisodeRunner(PanelSettings(BASE_DIR, argparse.Namespace(), generic_detector=True))
        runner.checkpoints, runner._thread = self.runner.checkpoints, threading.current_thread()
        runner._bridge_ready.set()
        for source in ("vision", "both"):
            with self.assertRaisesRegex(ValueError, "V2I"):
                runner.start(StartRequest(preemption=source))
        runner.start(StartRequest(preemption="v2i"))
        self.assertTrue(runner.state["is_running"])

    def test_every_scenario_has_a_fixed_time_reference(self) -> None:
        self.assertEqual(set(FIXED_TIME_REFERENCE_S), set(SCENARIOS))

    def test_reference_comes_from_the_official_evaluation_only(self) -> None:
        def report(warmup: float, wait: float) -> str:
            return json.dumps({"warmup_s": warmup, "control_s": 1800.0, "seeds": [201, 202, 203],
                               "versions": {"baseline": {"mean": {"mean_waiting_time_seconds": wait}}}})
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "versoes-calibrated-oracle.json").write_text(report(300.0, 12.34), encoding="utf-8")
            (folder / "versoes-original-oracle.json").write_text(report(30.0, 99.0), encoding="utf-8")  # outro protocolo
            values, sources = load_fixed_time_reference(folder)
        self.assertEqual((values["calibrated"], sources["calibrated"]), (12.3, "avaliação"))
        self.assertEqual((values["original"], sources["original"]), (FIXED_TIME_REFERENCE_S["original"], "valor embutido"))
        self.assertEqual(sources["calibrated_ped"], "valor embutido")  # arquivo ausente

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


class DetectorChoiceTests(unittest.TestCase):
    TUNED = str(BASE_DIR / "configs" / "sp.yaml")  # um arquivo que existe
    MISSING = str(BASE_DIR / "nao-existe.pt")
    GENERIC = BASE_DIR / "configs" / "sp.yaml"

    def args(self, model: str, classes: str = "0,1", allow: bool = True) -> argparse.Namespace:
        return argparse.Namespace(model=model, classes=classes, allow_generic_detector=allow)

    def test_tuned_detector_is_kept(self) -> None:
        args = self.args(self.TUNED)
        self.assertFalse(choose_detector(args, [], self.GENERIC))
        self.assertEqual((args.model, args.classes), (self.TUNED, "0,1"))

    def test_default_missing_falls_back_to_generic_without_motorcycles(self) -> None:
        args = self.args(self.MISSING)
        self.assertTrue(choose_detector(args, [], self.GENERIC))
        self.assertEqual((args.model, args.classes), (str(self.GENERIC), GENERIC_CLASSES))
        self.assertNotIn("3", GENERIC_CLASSES.split(","))

    def test_explicit_classes_are_never_replaced(self) -> None:
        args = self.args(self.MISSING, classes="2,7")
        self.assertTrue(choose_detector(args, ["--classes", "2,7"], self.GENERIC))
        self.assertEqual(args.classes, "2,7")

    def test_generic_detector_needs_the_explicit_option(self) -> None:
        # Sem --allow-generic-detector (ex.: servidor aberto fora de python/), falha como antes.
        with self.assertRaisesRegex(SystemExit, "allow-generic-detector"):
            choose_detector(self.args(self.MISSING, allow=False), [], self.GENERIC)

    def test_abbreviated_options_are_refused(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["--mod", self.MISSING])
        self.assertEqual(parse_args([]).warmup_seconds, 300.0)

    def test_explicit_missing_model_still_fails(self) -> None:
        with self.assertRaises(SystemExit):
            choose_detector(self.args(self.MISSING), ["--model", self.MISSING], self.GENERIC)
        with self.assertRaises(SystemExit):
            choose_detector(self.args(self.MISSING), [f"--model={self.MISSING}"], self.GENERIC)
        with self.assertRaises(SystemExit):
            choose_detector(self.args(self.MISSING), [], BASE_DIR / "tambem-nao-existe.pt")


if __name__ == "__main__":
    unittest.main()
