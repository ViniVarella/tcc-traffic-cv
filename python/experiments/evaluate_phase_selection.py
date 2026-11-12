"""Avalia tempo fixo, max-pressure acíclico e o DQN de seleção livre de fase (só SUMO).

Mesmas seeds de teste (201–203), aquecimento e duração para todas as políticas
em cada cenário; muda só a decisão. Para cada política: os valores por seed, a
média e o IC de 95% (t de Student, a seed é a unidade amostral) e a redução
pareada (seed a seed) contra o tempo fixo. Nos cenários do SP, o especialista
(DQN estado v2) entra a partir de ``versoes-<cenário>-oracle.json``, avaliado
no mesmo protocolo.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from paths import PYTHON_DIR
from controller.phase_selection.agent import PhaseSelectionAgent
from controller.phase_selection.policies import FixedTimePhasePolicy, MaxPressurePhasePolicy, PhaseDqnPolicy
from simulation.episode import EpisodeSettings
from simulation.phase_selection_environment import PhaseSelectionEnvironment
from simulation.statistics import METRICS, summarize


def specialist_runs(path: Path, seeds: list[int]) -> list[dict[str, Any]] | None:
    """Execuções do DQN estado v2 (TraffIQ) da avaliação de versões, nas mesmas seeds."""
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = {int(run["seed"]): run for run in data["versions"]["v2"]["runs"]}
    if not set(seeds) <= set(runs) or data.get("warmup_s") != 300.0 or data.get("control_s") != 1800.0:
        return None
    return [{"seed": seed, **{metric: runs[seed].get(metric) for metric in METRICS}} for seed in seeds]


def main() -> None:
    base_dir = PYTHON_DIR
    parser = argparse.ArgumentParser(description="Avalia a seleção livre de fase nos cruzamentos de teste.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "generic.yaml")
    parser.add_argument("--dqn-model", type=Path, default=base_dir.parent / "results" / "models" / "dqn-fase-livre-ped40-best.pt")
    parser.add_argument("--split", default="test", help="test, train ou all.")
    parser.add_argument("--seeds", default="201,202,203")
    parser.add_argument("--output", type=Path, default=base_dir.parent / "results" / "evaluation" / "fase-livre-test.json")
    args = parser.parse_args()
    seeds = [int(item) for item in args.seeds.split(",") if item.strip()]
    settings = EpisodeSettings()
    environment = PhaseSelectionEnvironment.from_file(args.config.resolve(), settings)
    scenarios = environment.scenarios if args.split == "all" else environment.split(args.split)
    agent = PhaseSelectionAgent.load(args.dqn_model)
    greedy = PhaseDqnPolicy(agent)
    policies = {"fixed_time": FixedTimePhasePolicy.from_layout, "max_pressure": lambda layout: MaxPressurePhasePolicy(), "dqn_fase_livre": lambda layout: greedy}
    results: dict[str, Any] = {"seeds": seeds, "warmup_s": settings.warmup_s, "control_s": settings.control_s,
                               "perception": "ground_truth", "dqn_model": str(args.dqn_model),
                               "dqn_metadata": agent.metadata, "scenarios": {}}
    for scenario in scenarios:
        layout = environment.layout(scenario)
        runs: dict[str, list[dict[str, Any]]] = {}
        for name, make_policy in policies.items():
            runs[name] = []
            for seed in seeds:
                outcome = environment.run(scenario, seed, make_policy, state_version=agent.config.state_version)
                runs[name].append({"seed": seed, "switches": outcome.switches, "decisions": outcome.decisions,
                                   "phase_seconds": dict(outcome.phase_seconds),
                                   **{metric: outcome.metrics.get(metric) for metric in METRICS}})
        if scenario.intersection == "sp":
            specialist = specialist_runs(base_dir.parent / "results" / "evaluation" / f"versoes-{scenario.demand}-oracle.json", seeds)
            if specialist is not None:
                runs["especialista_dqn_estado_v2"] = specialist
        entry = {"intersection": scenario.intersection, "demand": scenario.demand, "split": scenario.split,
                 "green_phases": len(layout.greens), "incoming_lanes": len(layout.incoming_lanes),
                 "policies": {name: summarize(items, None if name == "fixed_time" else runs["fixed_time"]) for name, items in runs.items()}}
        results["scenarios"][scenario.name] = entry
        line = " ".join(
            f"{name}={summary['mean_waiting_time_seconds']['mean']:.1f}s" for name, summary in entry["policies"].items()
        )
        print(f"phase_select_eval scenario={scenario.name} phases={entry['green_phases']} {line}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"phase_select_eval_complete output={args.output}", flush=True)


if __name__ == "__main__":
    main()
