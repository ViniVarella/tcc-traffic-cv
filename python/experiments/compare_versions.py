"""Compara as versões do controlador no mesmo ambiente de avaliação.

Todas as versões rodam no mesmo cenário, seeds, aquecimento, duração, camada de
segurança e métricas, e com a mesma percepção:

- ``--perception oracle``: features do oráculo TraCI, só SUMO (minutos);
- ``--perception visual``: features estimadas pela câmera, Unity em Play Mode
  (~45 min por seed e versão com 1800 s controlados).

A regra de cada versão está em ``experiments/version_policies.py``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from bridge import UnityBridge
from experiments.episode_runner import EpisodeSettings
from experiments.evaluate_policies_sumo import evaluate
from experiments.scenario_config import add_scenario_argument
from experiments.sumo_environment import Environment
from experiments.version_policies import VERSION_ORDER, build_version_policies
from experiments.visual_observer import StepLogger, add_vision_arguments, build_unity_observer


def parse_args(base_dir: Path) -> argparse.Namespace:
    models = base_dir.parent / "results" / "models"
    parser = argparse.ArgumentParser(description="Compara as versões do controlador no mesmo ambiente.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    add_scenario_argument(parser)
    parser.add_argument("--perception", choices=("oracle", "visual"), default="oracle")
    parser.add_argument("--versions", default=",".join(VERSION_ORDER), help=f"Subconjunto de {','.join(VERSION_ORDER)}.")
    parser.add_argument("--seeds", default="201,202,203")
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=1800.0)
    parser.add_argument("--v1-dqn-model", type=Path, default=models / "visual-dqn-sp-best.pt")
    parser.add_argument("--v2-dqn-model", type=Path, default=models / "dqn-v2-roi60-mix-pretrain-best.pt")
    parser.add_argument("--v3-dqn-model", type=Path, default=models / "dqn-v3-ped-w03-e100-best.pt",
                        help="Checkpoint do estado v3 (só cenários *_ped; inclua v3 em --versions).")
    add_vision_arguments(parser)
    parser.add_argument("--step-log-dir", type=Path, default=base_dir.parent / "results" / "logs",
                        help="Com --perception visual, grava um JSONL por versão neste diretório.")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    names = [value.strip() for value in args.versions.split(",") if value.strip()]
    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    scenario = args.scenario or config["sumo"].get("default_scenario")
    output = args.output or base_dir.parent / "results" / "evaluation" / f"versoes-{scenario}-{args.perception}.json"
    versions = build_version_policies(config, names, args.v1_dqn_model, args.v2_dqn_model, args.v3_dqn_model)
    report: dict[str, Any] = {"perception": args.perception, "scenario": scenario, "seeds": seeds,
                              "warmup_s": args.warmup_seconds, "control_s": args.control_seconds, "versions": {}}
    bridge = UnityBridge.from_config(config) if args.perception == "visual" else None
    try:
        observer = None
        if bridge is not None:
            bridge.start_frame_server()
            reference = Environment(config, base_dir, args.scenario, EpisodeSettings(args.warmup_seconds, args.control_seconds))
            observer = build_unity_observer(config, base_dir, args, reference, bridge)
            args.step_log_dir.mkdir(parents=True, exist_ok=True)
        for version in versions:
            environment = Environment(config, base_dir, args.scenario,
                                      EpisodeSettings(args.warmup_seconds, args.control_seconds, version.decision_interval_s),
                                      state_version=version.state_version)
            if observer is None:
                result = evaluate(environment, version.policy, seeds)
            else:
                log_path = args.step_log_dir / f"versoes-{scenario}-visual-{version.name}.jsonl"
                with log_path.open("w", encoding="utf-8") as handle:
                    result = evaluate(environment, version.policy, seeds, observer=observer,
                                      on_step=StepLogger(handle, observer, version.name))
            report["versions"][version.name] = {"description": version.description,
                                                "decision_interval_s": version.decision_interval_s, **result}
            mean = result["mean"]
            print(f"version_evaluated version={version.name} perception={args.perception} scenario={scenario} "
                  f"wait={mean['mean_waiting_time_seconds']:.1f}s travel={mean['mean_travel_time_seconds']:.1f}s "
                  f"arrived={mean['arrived_vehicles']:.0f} pending_end={mean['final_pending_vehicles']:.1f} "
                  f"ew_green_share={mean['east_west_green_share']:.2f} switches={mean['switches']:.0f}"
                  + (f" ped_wait={mean['pedestrian_mean_waiting_s']:.1f}s ped_median={mean['pedestrian_median_waiting_s']:.0f}s"
                     f" ped_p90={mean['pedestrian_p90_waiting_s']:.0f}s ped_max={mean['pedestrian_max_waiting_s']:.0f}s"
                     if "pedestrian_mean_waiting_s" in mean else ""))
    finally:
        if bridge is not None:
            bridge.close()
    if observer is not None:
        report["missing_frames"] = observer.missing_frames
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"comparison_complete output={output}")


if __name__ == "__main__":
    main()
