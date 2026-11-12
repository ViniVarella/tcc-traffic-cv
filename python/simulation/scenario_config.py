"""Argumentos de linha de comando compartilhados para escolher o cenário SUMO."""

from __future__ import annotations

import argparse


def add_scenario_argument(parser: argparse.ArgumentParser) -> None:
    """Adiciona ``--scenario``; sem ele, vale ``sumo.default_scenario`` do perfil."""
    parser.add_argument(
        "--scenario",
        default=None,
        help="Cenário de sumo.scenarios (ex.: calibrated, original); padrão: sumo.default_scenario.",
    )
