"""Testes de configuração do cliente TraCI."""

from __future__ import annotations

from pathlib import Path
import unittest

from sumo import SumoClient


class SumoClientTests(unittest.TestCase):
    def test_seed_override_has_priority_over_profile_seed(self) -> None:
        config = {"sumo": {"config_path": "scenario.sumocfg", "gui": False}, "experiment": {"seed": 42}}
        client = SumoClient.from_config(config, Path("/tmp"), seed_override=7)
        self.assertEqual(client.seed, 7)


if __name__ == "__main__":
    unittest.main()
