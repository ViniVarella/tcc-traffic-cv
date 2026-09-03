"""Executa o plano fixo nativo do SUMO e registra métricas comparáveis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import sleep
from typing import Any

import yaml

from sumo import ExperimentMetricsCollector, SumoClient


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa o baseline de tempos fixos do SUMO.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=None, help="Seed do SUMO; substitui experiment.seed do perfil.")
    parser.add_argument("--send-interval", type=float, default=0.0)
    parser.add_argument("--output", type=Path, default=base_dir.parent / "results" / "evaluation" / "fixed-time-baseline-metrics.json")
    return parser.parse_args()


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    if args.steps <= 0 or args.send_interval < 0:
        raise ValueError("--steps deve ser positivo e --send-interval não pode ser negativo.")
    if args.seed is not None and args.seed < 0:
        raise ValueError("--seed não pode ser negativa.")
    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    sumo_client = SumoClient.from_config(config, base_dir, seed_override=args.seed)
    metrics = ExperimentMetricsCollector()
    try:
        sumo_client.start()
        for _ in range(args.steps):
            sim_time = sumo_client.step()
            metrics.observe(sim_time, sumo_client.get_simulation_events(), sumo_client.get_active_vehicle_metrics())
            sleep(args.send_interval)
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(metrics.summary(), indent=2) + "\n", encoding="utf-8")
        sumo_client.close()
    print(f"baseline_complete steps={args.steps} output={args.output}")


if __name__ == "__main__":
    main()
