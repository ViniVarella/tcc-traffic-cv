"""Ajuste fino visual do DQN v2 pré-treinado no SUMO (Unity em Play Mode).

Parte do checkpoint do pré-treino, valida primeiro a política sem ajuste
(zero-shot) com percepção visual e só substitui o melhor checkpoint quando o
ajuste fino empata ou melhora esse valor. Treino nas seeds 41–50 por padrão,
disjuntas do pré-treino (1–40), da validação (1001+) e do teste (201–203).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml

from bridge import UnityBridge
from controller import DqnAgent
from experiments.checkpoint_selection import CheckpointSelector, SelectionCriteria, ValidationRecord
from experiments.episode_runner import DqnPolicy, EpisodeSettings, EpsilonSchedule
from experiments.scenario_config import add_scenario_argument
from experiments.sumo_environment import Environment
from experiments.visual_observer import StepLogger, add_vision_arguments, build_unity_observer


def parse_args(base_dir: Path) -> argparse.Namespace:
    models = base_dir.parent / "results" / "models"
    parser = argparse.ArgumentParser(description="Ajuste fino visual do DQN v2 pré-treinado.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    add_scenario_argument(parser)
    parser.add_argument("--init-checkpoint", type=Path, default=models / "dqn-v2-pretrain-best.pt")
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--seed-start", type=int, default=41)
    parser.add_argument("--validation-seeds", default="1001,1002")
    parser.add_argument("--validation-interval", type=int, default=5)
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=900.0)
    parser.add_argument("--decision-interval", type=float, default=5.0)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--epsilon-start", type=float, default=0.1)
    parser.add_argument("--epsilon-end", type=float, default=0.02)
    parser.add_argument("--min-replay-size", type=int, default=64)
    add_vision_arguments(parser)
    parser.add_argument("--checkpoint-output", type=Path, default=models / "dqn-v2-visual-last.pt")
    parser.add_argument("--best-checkpoint-output", type=Path, default=models / "dqn-v2-visual-best.pt")
    parser.add_argument("--log-output", type=Path, default=base_dir.parent / "results" / "logs" / "dqn-v2-visual-finetune.jsonl")
    parser.add_argument("--step-log-output", type=Path, default=base_dir.parent / "results" / "logs" / "dqn-v2-visual-finetune-steps.jsonl")
    return parser.parse_args()


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    if args.episodes <= 0 or args.validation_interval <= 0:
        raise ValueError("--episodes e --validation-interval devem ser positivos.")
    training_seeds = list(range(args.seed_start, args.seed_start + args.episodes))
    validation_seeds = [int(value) for value in args.validation_seeds.split(",") if value.strip()]
    if set(training_seeds) & set(validation_seeds) or set(training_seeds) & set(range(1, 41)) or set(training_seeds) & {201, 202, 203}:
        raise ValueError("Seeds de ajuste fino devem ser disjuntas do pré-treino (1–40), da validação e do teste (201–203).")

    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    environment = Environment(config, base_dir, args.scenario, EpisodeSettings(args.warmup_seconds, args.control_seconds, args.decision_interval))
    agent = DqnAgent.load(args.init_checkpoint, device="cpu")
    if agent.config.state_version != 2:
        raise ValueError(f"{args.init_checkpoint} não é um checkpoint de estado v2.")
    agent.config = replace(agent.config, learning_rate=args.learning_rate, min_replay_size=args.min_replay_size)
    for group in agent.optimizer.param_groups:
        group["lr"] = args.learning_rate
    agent.online.train()
    estimated_decisions = int(args.episodes * args.control_seconds / (2 * args.decision_interval))
    policy = DqnPolicy(agent, EpsilonSchedule(args.epsilon_start, args.epsilon_end, estimated_decisions))
    selector = CheckpointSelector(SelectionCriteria(min_gradient_steps=0, max_epsilon=1.0))
    metadata = {**agent.metadata, "feature_source": "visual", "init_checkpoint": str(args.init_checkpoint),
                "finetune": {"learning_rate": args.learning_rate, "episodes": args.episodes, "seeds": training_seeds,
                             "control_s": args.control_seconds, "validation_seeds": validation_seeds}}
    logs: list[dict[str, Any]] = []
    bridge = UnityBridge.from_config(config)
    args.step_log_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        bridge.start_frame_server()
        observer = build_unity_observer(config, base_dir, args, environment, bridge)
        with args.step_log_output.open("w", encoding="utf-8") as handle:

            def validate(label: str, episode: int) -> float:
                outcomes = [environment.run(seed, DqnPolicy(agent), observer=observer,
                                            on_step=StepLogger(handle, observer, f"validation:{label}"))[0] for seed in validation_seeds]
                score = sum(outcome.mean_reward for outcome in outcomes) / len(outcomes)
                rates = [outcome.switch_rate for outcome in outcomes if outcome.switch_rate is not None]
                switch_rate = None if not rates else sum(rates) / len(rates)
                record = ValidationRecord(episode, score, agent.training_steps, policy.current_epsilon(), switch_rate)
                selected = selector.consider(record)
                for seed, outcome in zip(validation_seeds, outcomes):
                    logs.append({"split": "validation", "label": label, "seed": seed, **outcome.summary()})
                logs.append({"split": "selection", "label": label, **asdict(record), "selected": selected,
                             "degeneracy": selector.degeneracy(switch_rate)})
                if selected:
                    agent.save(args.best_checkpoint_output, {**metadata, "kind": "best_visual_validation", "label": label,
                                                             "finetune_episode": episode, "validation_score": score})
                print(f"dqn_v2_visual_validation label={label} score={score:.4f} switch_rate={switch_rate} selected={selected} "
                      f"missing_frames={observer.missing_frames}")
                return score

            validate("zero_shot", -1)
            for episode, seed in enumerate(training_seeds):
                started = perf_counter()
                outcome, scenario = environment.run(seed, policy, learner=agent, observer=observer,
                                                    on_step=StepLogger(handle, observer, "finetune"))
                logs.append({"split": "train", "episode": episode, "seed": seed, "epsilon": policy.current_epsilon(),
                             "gradient_steps": agent.training_steps, **outcome.summary()})
                agent.save(args.checkpoint_output, {**metadata, "kind": "latest", "scenario": scenario, "finetune_episode": episode})
                print(f"dqn_v2_visual_episode episode={episode} seed={seed} reward={outcome.mean_reward:.4f} "
                      f"switch_rate={outcome.switch_rate} gradient_steps={agent.training_steps} "
                      f"missing={outcome.missing_observations} minutes={(perf_counter() - started) / 60:.1f}")
                if (episode + 1) % args.validation_interval == 0 or episode + 1 == args.episodes:
                    validate(f"after_episode_{episode}", episode)
    finally:
        bridge.close()
        args.log_output.parent.mkdir(parents=True, exist_ok=True)
        args.log_output.write_text("".join(json.dumps(item, default=str) + "\n" for item in logs), encoding="utf-8")
    best = selector.best
    print(f"dqn_v2_visual_finetune_complete best_label={'zero_shot' if best and best.episode < 0 else best and best.episode} "
          f"best_score={None if best is None else round(best.score, 4)} best_checkpoint={args.best_checkpoint_output} log={args.log_output}")


if __name__ == "__main__":
    main()
