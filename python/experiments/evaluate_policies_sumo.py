"""Avalia políticas v2 só no SUMO (percepção oráculo TraCI) nas mesmas seeds.

Compara ciclo fixo, max-pressure e checkpoints DQN v2 com o mesmo executor de
episódios, aquecimento e features. Os resultados usam percepção oráculo e devem
ser rotulados assim; a avaliação visual exige a Unity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any

import yaml

from controller import DqnAgent
from controller.policies import FixedCyclePolicy, MaxPressurePolicy
from experiments.episode_runner import DqnPolicy, EpisodeSettings, Policy
from experiments.sumo_environment import Environment
from experiments.scenario_config import add_scenario_argument


SUMMARY_KEYS = (
    "mean_waiting_time_seconds", "mean_travel_time_seconds", "arrived_vehicles", "throughput_vehicles_per_hour",
    "mean_queue_length", "mean_pending_vehicles", "final_pending_vehicles", "teleported_vehicles",
)


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Avalia políticas v2 no SUMO com percepção oráculo.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    add_scenario_argument(parser)
    parser.add_argument("--seeds", default="201,202,203")
    parser.add_argument("--dqn-model", type=Path, action="append", default=[], help="Checkpoint DQN v2 (repetível).")
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=1800.0)
    parser.add_argument("--decision-interval", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=base_dir.parent / "results" / "evaluation" / "policies-sumo-oracle.json")
    return parser.parse_args()


def evaluate(environment: Environment, policy: Policy, seeds: list[int], **run_options: Any) -> dict[str, Any]:
    """Roda a política em cada seed; ``run_options`` vai para ``Environment.run`` (ex.: observer)."""
    runs = []
    for seed in seeds:
        outcome, scenario = environment.run(seed, policy, **run_options)
        green = {name: outcome.phase_seconds.get(name, 0) for name in ("EAST_WEST_GREEN", "SOUTH_GREEN")}
        runs.append({"seed": seed, "scenario": scenario, "mean_reward": outcome.mean_reward, "switches": outcome.switches,
                     "switch_rate": outcome.switch_rate, "missing_observations": outcome.missing_observations,
                     "east_west_green_share": green["EAST_WEST_GREEN"] / max(1, sum(green.values())),
                     **{key: outcome.metrics.get(key) for key in SUMMARY_KEYS}})
    numeric = ("mean_reward", "switches", "east_west_green_share", *SUMMARY_KEYS)
    return {"runs": runs, "mean": {key: fmean(float(run[key]) for run in runs) for key in numeric if all(run[key] is not None for run in runs)}}


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    config = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    environment = Environment(config, base_dir, args.scenario, EpisodeSettings(args.warmup_seconds, args.control_seconds, args.decision_interval))
    policies: dict[str, Policy] = {"fixed_cycle": FixedCyclePolicy(), "max_pressure": MaxPressurePolicy()}
    for path in args.dqn_model:
        agent = DqnAgent.load(path, device="cpu")
        if agent.config.state_version != 2:
            raise ValueError(f"{path} não é um checkpoint de estado v2.")
        policies[f"dqn:{path.stem}"] = DqnPolicy(agent)
    report: dict[str, Any] = {"perception": "traci_oracle", "scenario": args.scenario or config["sumo"].get("default_scenario"),
                              "seeds": seeds, "warmup_s": args.warmup_seconds, "control_s": args.control_seconds, "policies": {}}
    for name, policy in policies.items():
        result = evaluate(environment, policy, seeds)
        report["policies"][name] = result
        mean = result["mean"]
        print(f"policy_evaluated policy={name} wait={mean['mean_waiting_time_seconds']:.1f}s travel={mean['mean_travel_time_seconds']:.1f}s "
              f"arrived={mean['arrived_vehicles']:.0f} pending_end={mean['final_pending_vehicles']:.1f} "
              f"ew_green_share={mean['east_west_green_share']:.2f} reward={mean['mean_reward']:.3f}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"evaluation_complete output={args.output}")


if __name__ == "__main__":
    main()
