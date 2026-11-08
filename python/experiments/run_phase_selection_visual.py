"""Seleção livre de fase no SP com percepção visual (Unity em Play Mode).

Mesmo protocolo de ``compare_versions --perception visual`` (seeds 201–203,
300 s de aquecimento, 1800 s de controle, YOLO + ByteTrack + ROIs das câmeras
``south``, ``east`` e ``west``): só muda a decisão, que passa a ser do DQN
genérico (treinado só em cruzamentos sintéticos e com percepção *ground
truth*). O relatório traz as mesmas métricas de ``evaluate_phase_selection``
e, para comparar no mesmo ambiente, as versões de
``versoes-<cenário>-visual.json`` (tempo fixo, max-pressure e DQN estado v2).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from bridge import UnityBridge
from controller.phase_selection_agent import PhaseSelectionAgent
from controller.phase_selection_policies import MaxPressurePhasePolicy, PhaseDqnPolicy
from experiments.episode_runner import EpisodeSettings
from experiments.evaluate_phase_selection import METRICS, summarize
from experiments.phase_selection_environment import PhaseSelectionEnvironment
from experiments.pretrain_phase_selection import fixed_time
from experiments.sumo_environment import Environment
from experiments.visual_observer import add_vision_arguments, build_unity_observer

# Rótulos das versões do relatório visual (ids do código → rótulo do modelo).
REFERENCE_VERSIONS = {"baseline": "tempo_fixo_programa", "max_pressure": "max_pressure_ciclico", "v2": "especialista_dqn_estado_v2"}


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DQN genérico de seleção livre de fase no SP com visão (Unity).")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml", help="Perfil do SP (Unity, câmeras, ROIs).")
    parser.add_argument("--generic-config", type=Path, default=base_dir / "configs" / "generic.yaml")
    parser.add_argument("--scenario", default="calibrated", help="Cenário do SP em generic.yaml (calibrated ou original).")
    parser.add_argument("--policies", default="dqn_fase_livre",
                        help="Lista separada por vírgula: dqn_fase_livre, max_pressure, fixed_time.")
    parser.add_argument("--dqn-model", type=Path, default=base_dir.parent / "results" / "models" / "dqn-fase-livre-v3-best.pt")
    parser.add_argument("--seeds", default="201,202,203")
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=1800.0)
    parser.add_argument("--decision-interval", type=float, default=5.0)
    add_vision_arguments(parser)
    parser.add_argument("--output", type=Path, default=None,
                        help="Padrão: results/evaluation/fase-livre-sp-<cenário>-visual.json")
    return parser.parse_args()


def reference_runs(path: Path, seeds: list[int], settings: EpisodeSettings) -> dict[str, list[dict[str, Any]]]:
    """Execuções visuais das versões do TraffIQ nas mesmas seeds e no mesmo protocolo."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("warmup_s") != settings.warmup_s or data.get("control_s") != settings.control_s:
        return {}
    references = {}
    for version, label in REFERENCE_VERSIONS.items():
        runs = {int(run["seed"]): run for run in data.get("versions", {}).get(version, {}).get("runs", [])}
        if set(seeds) <= set(runs):
            references[label] = [{"seed": seed, **{metric: runs[seed].get(metric) for metric in METRICS}} for seed in seeds]
    return references


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    settings = EpisodeSettings(args.warmup_seconds, args.control_seconds, args.decision_interval)
    sp_config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    generic = PhaseSelectionEnvironment.from_file(args.generic_config.resolve(), settings)
    scenario = generic.scenario(f"sp/{args.scenario}")
    # O Environment do SP só monta a percepção visual (câmeras, ROIs, sombra ground truth).
    sp_environment = Environment(sp_config, base_dir, args.scenario, settings)
    agent = PhaseSelectionAgent.load(args.dqn_model)
    greedy = PhaseDqnPolicy(agent)
    factories = {"dqn_fase_livre": lambda layout: greedy, "max_pressure": lambda layout: MaxPressurePhasePolicy(),
                 "fixed_time": fixed_time}
    names = [name.strip() for name in args.policies.split(",") if name.strip()]
    unknown = set(names) - set(factories)
    if unknown:
        raise ValueError(f"Políticas desconhecidas: {sorted(unknown)}.")
    output = args.output or base_dir.parent / "results" / "evaluation" / f"fase-livre-sp-{args.scenario}-visual.json"
    bridge = UnityBridge.from_config(sp_config)
    runs: dict[str, list[dict[str, Any]]] = {}
    missing: dict[str, int] = {}
    try:
        bridge.start_frame_server()
        observer = build_unity_observer(sp_config, base_dir, args, sp_environment, bridge)
        for name in names:
            runs[name] = []
            before = observer.missing_frames
            for seed in seeds:
                outcome = generic.run(scenario, seed, factories[name], observer=observer,
                                      state_version=agent.config.state_version)
                runs[name].append({"seed": seed, "switches": outcome.switches, "decisions": outcome.decisions,
                                   "missing_observations": outcome.missing_observations,
                                   "phase_seconds": dict(outcome.phase_seconds),
                                   **{metric: outcome.metrics.get(metric) for metric in METRICS}})
                print(f"phase_select_visual_run policy={name} seed={seed} "
                      f"wait={outcome.metrics['mean_waiting_time_seconds']:.2f}s switches={outcome.switches} "
                      f"missing_observations={outcome.missing_observations}", flush=True)
            missing[name] = observer.missing_frames - before
    finally:
        bridge.close()
    references = reference_runs(base_dir.parent / "results" / "evaluation" / f"versoes-{args.scenario}-visual.json", seeds, settings)
    baseline = references.get("tempo_fixo_programa")
    policies = {name: summarize(items, baseline) for name, items in {**runs, **references}.items()}
    report = {"perception": "visual", "scenario": args.scenario, "seeds": seeds, "warmup_s": settings.warmup_s,
              "control_s": settings.control_s, "dqn_model": str(args.dqn_model), "dqn_metadata": agent.metadata,
              "missing_frames": missing, "reduction_reference": "tempo_fixo_programa (versoes-*-visual.json)" if baseline else None,
              "policies": policies}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    line = " ".join(f"{name}={summary['mean_waiting_time_seconds']['mean']:.2f}s" for name, summary in policies.items())
    print(f"phase_select_visual_complete scenario={args.scenario} {line} missing_frames={missing} output={output}", flush=True)


if __name__ == "__main__":
    main()
