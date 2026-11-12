"""Escolha do intervalo N da fase de pedestres obrigatória por tempo (ambiente genérico).

Roda só controladores sem treino (tempo fixo e max-pressure) nas variantes com
pedestres dos cruzamentos pedidos, para cada N, e mede a espera dos veículos e a
dos pedestres estimada pelo HCM a partir dos inícios reais da fase
(``pedestrian_hcm_delay``). Usa seeds de validação, não as de teste, para que a
escolha de N não olhe para o teste.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from controller.phase_selection.policies import FixedTimePhasePolicy, MaxPressurePhasePolicy
from paths import PYTHON_DIR
from simulation.episode import EpisodeSettings
from simulation.phase_selection_environment import PhaseSelectionEnvironment, pedestrian_hcm_delay
from simulation.scenario_config import parse_seeds

POLICIES = {"fixed_time": FixedTimePhasePolicy.from_layout, "max_pressure": lambda layout: MaxPressurePhasePolicy()}


def main() -> None:
    base_dir = PYTHON_DIR
    parser = argparse.ArgumentParser(description="Compara intervalos N da fase de pedestres por tempo.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "generic.yaml")
    parser.add_argument("--intervals", default="30,40,60")
    parser.add_argument("--intersections", default="cruz-assimetrico")
    parser.add_argument("--seeds", default="1001,1002,1003,1004,1005")
    parser.add_argument("--output", type=Path, default=base_dir.parent / "results" / "evaluation" / "intervalo-pedestres.json")
    args = parser.parse_args()
    seeds = parse_seeds(args.seeds)
    intervals = [float(item) for item in args.intervals.split(",") if item.strip()]
    intersections = {item.strip() for item in args.intersections.split(",") if item.strip()}
    environment = PhaseSelectionEnvironment.from_file(args.config.resolve(), EpisodeSettings())
    green_s = float(environment.config["pedestrian_phase"]["green_seconds"])
    scenarios = [s for s in environment.scenarios if s.intersection in intersections and s.pedestrian_s > 0]
    report: dict[str, Any] = {"seeds": seeds, "green_seconds": green_s, "results": {}}
    for interval in intervals:
        environment.pedestrian_interval_s = interval
        for scenario in scenarios:
            for name, factory in POLICIES.items():
                runs = []
                for seed in seeds:
                    outcome = environment.run(scenario, seed, factory)
                    hcm = pedestrian_hcm_delay(outcome.pedestrian_starts, green_s) or {}
                    runs.append({"seed": seed, "wait_s": outcome.metrics["mean_waiting_time_seconds"],
                                 "stopped_wait_s": outcome.metrics["mean_waiting_time_stopped_seconds"],
                                 "pending": outcome.metrics["mean_pending_vehicles"],
                                 "pedestrian_seconds": outcome.phase_seconds.get("pedestrian", 0),
                                 **{f"pedestrian_{key}": value for key, value in hcm.items()}})
                summary = {key: float(np.mean([run[key] for run in runs if key in run]))
                           for key in ("wait_s", "stopped_wait_s", "pending", "pedestrian_seconds", "pedestrian_mean_wait_s",
                                       "pedestrian_max_wait_s", "pedestrian_mean_interval_s")}
                report["results"].setdefault(str(int(interval)), {}).setdefault(scenario.name, {})[name] = {
                    "summary": summary,
                    "runs": runs,
                }
                print(
                    f"pedestrian_interval N={interval:.0f} scenario={scenario.name} policy={name} "
                    f"wait={summary['wait_s']:.1f}s ped_hcm={summary['pedestrian_mean_wait_s']:.1f}s "
                    f"ped_max={summary['pedestrian_max_wait_s']:.0f}s interval={summary['pedestrian_mean_interval_s']:.0f}s",
                    flush=True,
                )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"pedestrian_interval_complete output={args.output}", flush=True)


if __name__ == "__main__":
    main()
