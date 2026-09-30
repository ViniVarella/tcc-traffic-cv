"""Testes da seleção de cenário SUMO (demanda calibrada × original)."""

from __future__ import annotations

import argparse
from pathlib import Path
import unittest

import yaml

from experiments.scenario_config import add_scenario_argument
from sumo import SumoClient
from sumo.scenarios import resolve_sumo_scenario


PYTHON_DIR = Path(__file__).resolve().parents[1]
CONFIG = {
    "sumo": {
        "scenarios": {"calibrated": "../sumo/sp/Cruzamento.calibrated.sumocfg", "original": "../sumo/sp/Cruzamento.sumocfg"},
        "default_scenario": "calibrated",
        "gui": False,
    },
    "experiment": {"seed": 42},
}


class ResolveScenarioTests(unittest.TestCase):
    def test_default_scenario_is_used_without_override(self) -> None:
        self.assertEqual(resolve_sumo_scenario(CONFIG), ("calibrated", "../sumo/sp/Cruzamento.calibrated.sumocfg"))

    def test_override_selects_another_scenario(self) -> None:
        self.assertEqual(resolve_sumo_scenario(CONFIG, "original"), ("original", "../sumo/sp/Cruzamento.sumocfg"))

    def test_unknown_scenario_lists_the_available_ones(self) -> None:
        with self.assertRaisesRegex(ValueError, "calibrated, original"):
            resolve_sumo_scenario(CONFIG, "rush_hour")

    def test_default_must_be_declared(self) -> None:
        config = {"sumo": {"scenarios": CONFIG["sumo"]["scenarios"], "default_scenario": "missing"}}
        with self.assertRaises(ValueError):
            resolve_sumo_scenario(config)

    def test_legacy_profile_with_config_path_has_no_named_scenario(self) -> None:
        config = {"sumo": {"config_path": "../sumo/fictional/RL.sumocfg"}}
        self.assertEqual(resolve_sumo_scenario(config), (None, "../sumo/fictional/RL.sumocfg"))
        with self.assertRaises(ValueError):
            resolve_sumo_scenario(config, "calibrated")

    def test_scenarios_and_config_path_are_mutually_exclusive(self) -> None:
        config = {"sumo": {**CONFIG["sumo"], "config_path": "x.sumocfg"}}
        with self.assertRaises(ValueError):
            resolve_sumo_scenario(config)


class SumoClientScenarioTests(unittest.TestCase):
    def test_from_config_resolves_scenario_path_and_records_name(self) -> None:
        client = SumoClient.from_config(CONFIG, PYTHON_DIR, scenario_override="original")
        self.assertEqual(client.scenario, "original")
        self.assertEqual(Path(client.config_path), (PYTHON_DIR.parent / "sumo" / "sp" / "Cruzamento.sumocfg").resolve())

    def test_sp_profile_scenarios_point_to_existing_files(self) -> None:
        config = yaml.safe_load((PYTHON_DIR / "configs" / "sp.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["sumo"]["default_scenario"], "calibrated")
        for name in config["sumo"]["scenarios"]:
            client = SumoClient.from_config(config, PYTHON_DIR, scenario_override=name)
            self.assertTrue(Path(client.config_path).is_file(), client.config_path)


class ScenarioArgumentTests(unittest.TestCase):
    def test_argument_defaults_to_profile_scenario(self) -> None:
        parser = argparse.ArgumentParser()
        add_scenario_argument(parser)
        self.assertIsNone(parser.parse_args([]).scenario)
        self.assertEqual(parser.parse_args(["--scenario", "original"]).scenario, "original")


if __name__ == "__main__":
    unittest.main()
