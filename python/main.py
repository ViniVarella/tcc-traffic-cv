"""Ponto de entrada inicial do projeto Python."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Carrega a configuracao YAML legivel do projeto."""
    path = Path(config_path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> None:
    """Carrega a configuracao revisada e confirma o scaffold arquitetural."""
    base_dir = Path(__file__).resolve().parent
    config = load_config(base_dir / "config.yaml")
    enabled_cameras = [
        camera_id
        for camera_id, camera_config in config.get("cameras", {}).items()
        if camera_config.get("enabled", False)
    ]

    print(
        "Estrutura inicial pronta: "
        f"cenario={config['experiment']['scenario']}, "
        f"step_length={config['sumo']['step_length']}, "
        f"tls={config['traffic_light']['id']}, "
        f"cameras={len(enabled_cameras)}, "
        f"vision_every_steps={config['vision']['update_every_steps']}."
    )


if __name__ == "__main__":
    main()
