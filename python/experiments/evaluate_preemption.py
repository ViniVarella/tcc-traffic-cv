"""Avalia a preempção para veículos de emergência no mesmo ambiente.

Cada política roda com a mesma agenda de viaturas (reproduzível pela seed),
com e sem preempção por aviso V2I, no mesmo cenário, seeds, aquecimento e
duração. Mede o atraso das viaturas até a linha de retenção e o impacto no
restante do tráfego. Percepção das features da política: oráculo TraCI (só
SUMO); a detecção visual das viaturas é uma etapa posterior.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml

from controller.preemption import PreemptionSettings
from experiments.episode_runner import EpisodeSettings
from experiments.scenario_config import add_scenario_argument
from experiments.sumo_environment import Environment
from experiments.version_policies import build_version_policies
from sumo.emergency import EmergencySettings


def parse_args(base_dir: Path) -> argparse.Namespace:
    models = base_dir.parent / "results" / "models"
    parser = argparse.ArgumentParser(description="Avalia a preempção para veículos de emergência.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    add_scenario_argument(parser)
    parser.add_argument("--versions", default="baseline,v2,max_pressure")
    parser.add_argument("--seeds", default="201,202,203")
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=1800.0)
    parser.add_argument("--v1-dqn-model", type=Path, default=models / "visual-dqn-sp-best.pt")
    parser.add_argument("--v2-dqn-model", type=Path, default=models / "dqn-v2-roi60-pretrain-best.pt")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def _mean(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else float(fmean(present))


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    scenario = args.scenario or config["sumo"].get("default_scenario")
    output = args.output or base_dir.parent / "results" / "evaluation" / f"preempcao-{scenario}-oracle.json"
    emergency = EmergencySettings.from_config(config)
    preemption = PreemptionSettings.from_config(config)
    versions = build_version_policies(config, [item.strip() for item in args.versions.split(",") if item.strip()],
                                      args.v1_dqn_model, args.v2_dqn_model)
    report: dict[str, Any] = {"perception": "oracle", "emergency_detection": "v2i", "scenario": scenario, "seeds": seeds,
                              "warmup_s": args.warmup_seconds, "control_s": args.control_seconds, "results": {}}
    for version in versions:
        environment = Environment(config, base_dir, args.scenario,
                                  EpisodeSettings(args.warmup_seconds, args.control_seconds, version.decision_interval_s))
        for label, settings in (("sem_preempcao", None), ("com_preempcao", preemption)):
            runs = []
            for seed in seeds:
                outcome, _ = environment.run(seed, version.policy, emergency=emergency, preemption=settings)
                metrics, vehicles = outcome.metrics, outcome.metrics["emergency"]
                runs.append({"seed": seed, "preemption_steps": outcome.preemption_steps, **{key: metrics.get(key) for key in (
                    "mean_waiting_time_seconds", "mean_travel_time_seconds", "arrived_vehicles", "final_pending_vehicles")},
                    "emergency": vehicles})
            summary = {
                "emergency_mean_time_loss_s": _mean([run["emergency"]["mean_time_loss_at_crossing_s"] for run in runs]),
                "emergency_max_time_loss_s": max((run["emergency"]["max_time_loss_at_crossing_s"] or 0.0) for run in runs),
                "emergency_share_without_stops": _mean([run["emergency"]["share_without_stops"] for run in runs]),
                "emergency_crossed": sum(run["emergency"]["crossed_stop_line"] for run in runs),
                "emergency_scheduled": sum(run["emergency"]["scheduled"] for run in runs),
                **{key: _mean([run[key] for run in runs]) for key in (
                    "mean_waiting_time_seconds", "mean_travel_time_seconds", "arrived_vehicles", "final_pending_vehicles")},
            }
            report["results"][f"{version.name}/{label}"] = {"summary": summary, "runs": runs}
            print(f"preemption_evaluated version={version.name} mode={label} "
                  f"viatura_perda_media={summary['emergency_mean_time_loss_s']:.1f}s viatura_perda_max={summary['emergency_max_time_loss_s']:.1f}s "
                  f"viaturas_sem_parar={summary['emergency_share_without_stops']:.0%} "
                  f"cruzaram={summary['emergency_crossed']}/{summary['emergency_scheduled']} "
                  f"trafego_espera={summary['mean_waiting_time_seconds']:.1f}s chegadas={summary['arrived_vehicles']:.0f} "
                  f"fila_insercao={summary['final_pending_vehicles']:.1f}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"preemption_complete output={output}")


if __name__ == "__main__":
    main()
