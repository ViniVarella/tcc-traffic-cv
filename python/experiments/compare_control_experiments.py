"""Compara as métricas do baseline fixo e do controlador visual."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


METRICS = (
    "arrived_vehicles",
    "mean_travel_time_seconds",
    "mean_waiting_time_seconds",
    "mean_queue_length",
    "max_queue_length",
    "throughput_vehicles_per_hour",
)


def compare_metrics(baseline: dict[str, Any], adaptive: dict[str, Any]) -> dict[str, Any]:
    """Calcula diferença absoluta e percentual; menor é melhor para tempo/fila."""
    comparison: dict[str, Any] = {"baseline": baseline, "visual_adaptive": adaptive, "comparison": {}}
    for name in METRICS:
        baseline_value = float(baseline.get(name, 0.0))
        adaptive_value = float(adaptive.get(name, 0.0))
        comparison["comparison"][name] = {
            "baseline": baseline_value,
            "visual_adaptive": adaptive_value,
            "absolute_delta": adaptive_value - baseline_value,
            "percent_delta": None if baseline_value == 0 else (adaptive_value - baseline_value) * 100.0 / baseline_value,
            "higher_is_better": name in {"arrived_vehicles", "throughput_vehicles_per_hour"},
        }
    return comparison


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compara baseline fixo e controle visual.")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--visual-adaptive", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=base_dir.parent / "results" / "evaluation" / "fixed-vs-visual-controller.json")
    return parser.parse_args()


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    adaptive = json.loads(args.visual_adaptive.read_text(encoding="utf-8"))
    output = compare_metrics(baseline, adaptive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"comparison_complete output={args.output}")


if __name__ == "__main__":
    main()
