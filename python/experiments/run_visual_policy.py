"""Executa uma política v2 com percepção visual (Unity em Play Mode) e registra o domain gap.

Cada step controlado gera uma linha JSONL com as features visuais, as do
oráculo TraCI calculadas em paralelo (só registro) e a decisão. Esse log
alimenta ``experiments.evaluate_lane_features``. As métricas de tráfego vão
para ``--output`` no mesmo formato de ``evaluate_policies_sumo``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from bridge import UnityBridge
from controller import DqnAgent
from controller.policies import FixedCyclePolicy, MaxPressurePolicy
from experiments.episode_runner import DqnPolicy, EpisodeSettings, Policy
from experiments.evaluate_policies_sumo import evaluate
from experiments.scenario_config import add_scenario_argument
from experiments.sumo_environment import Environment
from experiments.visual_observer import StepLogger, add_vision_arguments, build_unity_observer


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa uma política v2 com visão Unity e registra visão × oráculo.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    add_scenario_argument(parser)
    parser.add_argument("--policy", choices=("dqn", "fixed_cycle", "max_pressure"), default="dqn")
    parser.add_argument("--dqn-model", type=Path, default=base_dir.parent / "results" / "models" / "dqn-v2-roi60-mix-pretrain-best.pt")
    parser.add_argument("--seeds", default="1001")
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=900.0)
    parser.add_argument("--decision-interval", type=float, default=5.0)
    add_vision_arguments(parser)
    parser.add_argument("--step-log-output", type=Path, default=base_dir.parent / "results" / "logs" / "visual-v2-steps.jsonl")
    parser.add_argument("--output", type=Path, default=base_dir.parent / "results" / "evaluation" / "visual-v2-policy.json")
    return parser.parse_args()


def build_policy(args: argparse.Namespace) -> tuple[str, Policy]:
    if args.policy == "fixed_cycle":
        return "fixed_cycle", FixedCyclePolicy()
    if args.policy == "max_pressure":
        return "max_pressure", MaxPressurePolicy()
    agent = DqnAgent.load(args.dqn_model, device="cpu")
    if agent.config.state_version != 2:
        raise ValueError(f"{args.dqn_model} não é um checkpoint de estado v2.")
    return f"dqn:{args.dqn_model.stem}", DqnPolicy(agent)


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    environment = Environment(config, base_dir, args.scenario, EpisodeSettings(args.warmup_seconds, args.control_seconds, args.decision_interval))
    policy_name, policy = build_policy(args)
    bridge = UnityBridge.from_config(config)
    args.step_log_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        bridge.start_frame_server()
        observer = build_unity_observer(config, base_dir, args, environment, bridge)
        with args.step_log_output.open("w", encoding="utf-8") as handle:
            result = evaluate(environment, policy, seeds, observer=observer, on_step=StepLogger(handle, observer, policy_name))
    finally:
        bridge.close()
    report = {"perception": "visual", "policy": policy_name, "scenario": args.scenario or config["sumo"].get("default_scenario"),
              "seeds": seeds, "warmup_s": args.warmup_seconds, "control_s": args.control_seconds,
              "missing_frames": observer.missing_frames, "step_log": str(args.step_log_output), **result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    mean = result["mean"]
    print(f"visual_policy_complete policy={policy_name} seeds={args.seeds} wait={mean['mean_waiting_time_seconds']:.1f}s "
          f"arrived={mean['arrived_vehicles']:.0f} pending_end={mean['final_pending_vehicles']:.1f} "
          f"ew_green_share={mean['east_west_green_share']:.2f} missing_frames={observer.missing_frames} "
          f"output={args.output} step_log={args.step_log_output}")


if __name__ == "__main__":
    main()
