"""Avalia a preempção para veículos de emergência no mesmo ambiente.

Cada política roda com a mesma agenda de viaturas (reproduzível pela seed),
sem preempção e com preempção por cada fonte de detecção, no mesmo cenário,
seeds, aquecimento e duração. Mede o atraso das viaturas até a linha de
retenção e o impacto no restante do tráfego.

- ``--perception oracle`` (só SUMO): features do oráculo TraCI; só V2I.
- ``--perception visual`` (Unity em Play Mode): features e viaturas pela câmera;
  ``--detections`` aceita ``v2i``, ``vision`` (classe ``emergency`` nas ROIs) e
  ``both``. A agenda, a política e a percepção das features são as mesmas; muda
  só a fonte do pedido de prioridade.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml

from bridge import UnityBridge
from controller.preemption import PreemptionSettings
from experiments.episode_runner import EpisodeSettings
from experiments.scenario_config import add_scenario_argument
from experiments.sumo_environment import EMERGENCY_DETECTIONS, Environment
from experiments.version_policies import build_version_policies
from experiments.visual_observer import StepLogger, add_vision_arguments, build_unity_observer
from sumo.emergency import EmergencySettings


def parse_args(base_dir: Path) -> argparse.Namespace:
    models = base_dir.parent / "results" / "models"
    parser = argparse.ArgumentParser(description="Avalia a preempção para veículos de emergência.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    add_scenario_argument(parser)
    parser.add_argument("--perception", choices=("oracle", "visual"), default="oracle")
    parser.add_argument("--detections", default=None,
                        help=f"Fontes do pedido de preempção, entre {','.join(EMERGENCY_DETECTIONS)}. "
                             "Padrão: v2i (oracle) ou v2i,vision,both (visual).")
    parser.add_argument("--versions", default="baseline,v2,max_pressure")
    parser.add_argument("--seeds", default="201,202,203")
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=1800.0)
    parser.add_argument("--v1-dqn-model", type=Path, default=models / "visual-dqn-sp-best.pt")
    parser.add_argument("--v2-dqn-model", type=Path, default=models / "dqn-v2-roi60-mix-pretrain-best.pt")
    parser.add_argument("--v3-dqn-model", type=Path, default=models / "dqn-v3-ped-w03-e100-best.pt",
                        help="Checkpoint do estado v3 (só cenários *_ped; inclua v3 em --versions).")
    add_vision_arguments(parser)
    parser.add_argument("--step-log-dir", type=Path, default=base_dir.parent / "results" / "logs",
                        help="Com --perception visual, grava um JSONL por versão e modo neste diretório.")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def _mean(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else float(fmean(present))


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    detections = [item.strip() for item in (args.detections or ("v2i" if args.perception == "oracle" else "v2i,vision,both")).split(",")
                  if item.strip()]
    if any(item not in EMERGENCY_DETECTIONS for item in detections):
        raise ValueError(f"--detections aceita {EMERGENCY_DETECTIONS}.")
    if args.perception == "oracle" and detections != ["v2i"]:
        raise ValueError("A detecção visual das viaturas exige --perception visual (Unity em Play Mode).")
    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    scenario = args.scenario or config["sumo"].get("default_scenario")
    output = args.output or base_dir.parent / "results" / "evaluation" / f"preempcao-{scenario}-{args.perception}.json"
    emergency = EmergencySettings.from_config(config)
    preemption = PreemptionSettings.from_config(config)
    versions = build_version_policies(config, [item.strip() for item in args.versions.split(",") if item.strip()],
                                      args.v1_dqn_model, args.v2_dqn_model, args.v3_dqn_model)
    modes = [("sem_preempcao", None, "v2i")] + [(f"com_preempcao_{item}", preemption, item) for item in detections]
    report: dict[str, Any] = {"perception": args.perception, "detections": detections, "scenario": scenario, "seeds": seeds,
                              "warmup_s": args.warmup_seconds, "control_s": args.control_seconds, "results": {}}
    bridge = UnityBridge.from_config(config) if args.perception == "visual" else None
    observer = None
    try:
        if bridge is not None:
            bridge.start_frame_server()
            reference = Environment(config, base_dir, args.scenario, EpisodeSettings(args.warmup_seconds, args.control_seconds))
            observer = build_unity_observer(config, base_dir, args, reference, bridge)
            args.step_log_dir.mkdir(parents=True, exist_ok=True)
        for version in versions:
            environment = Environment(config, base_dir, args.scenario,
                                      EpisodeSettings(args.warmup_seconds, args.control_seconds, version.decision_interval_s),
                                      state_version=version.state_version)
            for label, settings, detection in modes:
                handle = None if observer is None else (
                    args.step_log_dir / f"preempcao-{scenario}-visual-{version.name}-{label}.jsonl").open("w", encoding="utf-8")
                try:
                    runs = []
                    for seed in seeds:
                        outcome, _ = environment.run(
                            seed, version.policy, observer=observer, emergency=emergency, preemption=settings,
                            emergency_detection=detection,
                            on_step=None if handle is None else StepLogger(handle, observer, f"{version.name}/{label}"))
                        metrics, vehicles = outcome.metrics, outcome.metrics["emergency"]
                        runs.append({"seed": seed, "preemption_steps": outcome.preemption_steps,
                                     "missing_observations": outcome.missing_observations, **{key: metrics.get(key) for key in (
                                         "mean_waiting_time_seconds", "mean_travel_time_seconds", "arrived_vehicles",
                                         "final_pending_vehicles", "pedestrian_mean_waiting_s", "pedestrian_median_waiting_s",
                                         "pedestrian_p90_waiting_s", "pedestrian_max_waiting_s")},
                                     "emergency": vehicles})
                finally:
                    if handle is not None:
                        handle.close()
                visual = [run["emergency"]["visual_detection"] for run in runs]
                summary = {
                    "emergency_mean_time_loss_s": _mean([run["emergency"]["mean_time_loss_at_crossing_s"] for run in runs]),
                    "emergency_max_time_loss_s": max((run["emergency"]["max_time_loss_at_crossing_s"] or 0.0) for run in runs),
                    "emergency_mean_insertion_delay_s": _mean([run["emergency"]["mean_insertion_delay_s"] for run in runs]),
                    "emergency_mean_total_loss_s": _mean([run["emergency"]["mean_total_loss_at_crossing_s"] for run in runs]),
                    "emergency_max_total_loss_s": max((run["emergency"]["max_total_loss_at_crossing_s"] or 0.0) for run in runs),
                    "emergency_share_without_stops": _mean([run["emergency"]["share_without_stops"] for run in runs]),
                    "emergency_crossed": sum(run["emergency"]["crossed_stop_line"] for run in runs),
                    "emergency_scheduled": sum(run["emergency"]["scheduled"] for run in runs),
                    "v2i_mean_lead_s": _mean([run["emergency"]["mean_v2i_lead_s"] for run in runs]),
                    "visual_detected": sum(item["detected"] for item in visual),
                    "visual_mean_lead_s": _mean([item["mean_lead_s"] for item in visual]),
                    "visual_events": sum(item["events"] for item in visual),
                    "visual_false_events": sum(item["false_events"] for item in visual),
                    **{key: _mean([run[key] for run in runs]) for key in (
                        "mean_waiting_time_seconds", "mean_travel_time_seconds", "arrived_vehicles", "final_pending_vehicles",
                        "pedestrian_mean_waiting_s", "pedestrian_median_waiting_s", "pedestrian_p90_waiting_s",
                        "pedestrian_max_waiting_s")},
                }
                report["results"][f"{version.name}/{label}"] = {"summary": summary, "runs": runs}
                lead = summary["visual_mean_lead_s"]
                print(f"preemption_evaluated version={version.name} mode={label} perception={args.perception} "
                      f"viatura_perda_media={summary['emergency_mean_time_loss_s']:.1f}s viatura_perda_max={summary['emergency_max_time_loss_s']:.1f}s "
                      f"viatura_espera_entrada={summary['emergency_mean_insertion_delay_s']:.1f}s "
                      f"viatura_perda_total_media={summary['emergency_mean_total_loss_s']:.1f}s "
                      f"viatura_perda_total_max={summary['emergency_max_total_loss_s']:.1f}s "
                      f"viaturas_sem_parar={summary['emergency_share_without_stops']:.0%} "
                      f"cruzaram={summary['emergency_crossed']}/{summary['emergency_scheduled']} "
                      f"visao_detectou={summary['visual_detected']} visao_antecedencia={'n/a' if lead is None else f'{lead:.1f}s'} "
                      f"visao_alarmes_falsos={summary['visual_false_events']}/{summary['visual_events']} "
                      f"trafego_espera={summary['mean_waiting_time_seconds']:.1f}s chegadas={summary['arrived_vehicles']:.0f} "
                      f"fila_insercao={summary['final_pending_vehicles']:.1f}"
                      + ("" if summary["pedestrian_mean_waiting_s"] is None else
                         f" pedestres_espera={summary['pedestrian_mean_waiting_s']:.1f}s pedestres_mediana={summary['pedestrian_median_waiting_s']:.0f}s"
                         f" pedestres_p90={summary['pedestrian_p90_waiting_s']:.0f}s pedestres_max={summary['pedestrian_max_waiting_s']:.0f}s"),
                      flush=True)
    finally:
        if bridge is not None:
            bridge.close()
    if observer is not None:
        report["missing_frames"] = observer.missing_frames
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"preemption_complete output={output}")


if __name__ == "__main__":
    main()
