"""Argumentos de linha de comando compartilhados: cenário SUMO e listas separadas por vírgula."""

from __future__ import annotations

import argparse


def add_scenario_argument(parser: argparse.ArgumentParser) -> None:
    """Adiciona ``--scenario``; sem ele, vale ``sumo.default_scenario`` do perfil."""
    parser.add_argument(
        "--scenario",
        default=None,
        help="Cenário de sumo.scenarios (ex.: calibrated, original); padrão: sumo.default_scenario.",
    )


def parse_csv(text: str) -> list[str]:
    """Itens de uma lista separada por vírgula (``"a, b,"`` → ``["a", "b"]``)."""
    return [item.strip() for item in text.split(",") if item.strip()]


def parse_seeds(text: str) -> list[int]:
    """Seeds de ``--seeds``/``--validation-seeds`` (``"201,202,203"``)."""
    return [int(item) for item in parse_csv(text)]
