"""Ponto de entrada inicial do projeto Python."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load the project configuration from a YAML file encoded as JSON."""
    path = Path(config_path)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    """Load the initial configuration and confirm the scaffold is ready."""
    base_dir = Path(__file__).resolve().parent
    config = load_config(base_dir / "config.yaml")

    print(
        "Estrutura inicial pronta: "
        f"SUMO gui={config['sumo']['gui']}, "
        f"TLS={config['sumo']['tls_id']}, "
        f"porta Unity estado={config['unity']['state_port']}."
    )


if __name__ == "__main__":
    main()
