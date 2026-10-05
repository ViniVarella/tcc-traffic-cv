"""Pré-treino rápido do DQN v2 só com SUMO, usando o oráculo TraCI das ROIs.

As features vêm de ``TraciLaneFeatureSource`` (mesmo contrato e mesmo
intervalo físico das ROIs das câmeras); a política implantada depois usa a
visão. Nenhum frame Unity é necessário, então episódios longos e muitas seeds
são viáveis.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import yaml

from controller import DqnAgent, DqnConfig
from controller.policies import FixedCyclePolicy, MaxPressurePolicy
from experiments.checkpoint_selection import CheckpointSelector, SelectionCriteria, ValidationRecord
from experiments.episode_runner import DqnPolicy, EpisodeSettings, EpsilonSchedule, Policy
from experiments.scenario_config import add_scenario_argument
from experiments.sumo_environment import Environment
from vision import SP_LANE_ORDER


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pré-treina o DQN v2 no SUMO com features por faixa do oráculo TraCI.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    add_scenario_argument(parser)
    parser.add_argument("--scenarios", default=None,
                        help="Lista (ex.: calibrated,original): os episódios de treino alternam entre eles e a validação usa todos.")
    parser.add_argument("--episodes", type=int, default=40)
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--validation-episodes", type=int, default=3)
    parser.add_argument("--validation-seed-start", type=int, default=1001)
    parser.add_argument("--validation-interval", type=int, default=5)
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=1800.0)
    parser.add_argument("--decision-interval", type=float, default=5.0)
    parser.add_argument("--gamma", type=float, default=0.99, help="Desconto por segundo simulado (transições SMDP).")
    parser.add_argument("--epsilon-start", type=float, default=1.0)
    parser.add_argument("--epsilon-end", type=float, default=0.05)
    parser.add_argument("--epsilon-decay-fraction", type=float, default=0.5,
                        help="Fração das decisões estimadas do treino em que ε decai linearmente.")
    parser.add_argument("--double-dqn", action="store_true")
    parser.add_argument("--pedestrian-reward-weight", type=float, default=None,
                        help="Substitui pedestrians.reward_weight do perfil (cenários com pedestres).")
    parser.add_argument("--state-version", type=int, choices=(2, 3), default=2,
                        help="3 = estado com a fase de pedestres; exige cenários *_ped (ex.: calibrated_ped,original_ped).")
    parser.add_argument("--min-gradient-steps", type=int, default=5_000)
    parser.add_argument("--device", default="cpu", help="A MLP é pequena; CPU costuma ser mais rápida que MPS.")
    parser.add_argument("--checkpoint-output", type=Path, default=base_dir.parent / "results" / "models" / "dqn-v2-pretrain-last.pt")
    parser.add_argument("--best-checkpoint-output", type=Path, default=base_dir.parent / "results" / "models" / "dqn-v2-pretrain-best.pt")
    parser.add_argument("--log-output", type=Path, default=base_dir.parent / "results" / "logs" / "dqn-v2-pretrain.jsonl")
    return parser.parse_args()


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    if min(args.episodes, args.validation_episodes, args.validation_interval) <= 0:
        raise ValueError("--episodes, --validation-episodes e --validation-interval devem ser positivos.")
    training_seeds = list(range(args.seed_start, args.seed_start + args.episodes))
    validation_seeds = list(range(args.validation_seed_start, args.validation_seed_start + args.validation_episodes))
    if set(training_seeds) & set(validation_seeds):
        raise ValueError("As seeds de treino e validação devem ser disjuntas.")

    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    if args.pedestrian_reward_weight is not None:
        config.setdefault("pedestrians", {})["reward_weight"] = float(args.pedestrian_reward_weight)
    settings = EpisodeSettings(args.warmup_seconds, args.control_seconds, args.decision_interval, args.gamma)
    scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()] if args.scenarios else [args.scenario]
    environments = [Environment(config, base_dir, scenario, settings, state_version=args.state_version) for scenario in scenarios]
    environment = environments[0]
    dqn = config["dqn"]
    agent = DqnAgent(DqnConfig(
        state_size=environment.encoder.state_size, hidden_size=int(dqn["hidden_size"]), gamma=args.gamma,
        learning_rate=float(dqn["learning_rate"]), batch_size=int(dqn["batch_size"]), replay_capacity=int(dqn["replay_capacity"]),
        min_replay_size=int(dqn["min_replay_size"]), target_update_interval=int(dqn["target_update_interval"]),
        state_version=args.state_version, double_dqn=args.double_dqn,
    ), device=args.device, seed=args.seed_start)
    # ~1 decisão a cada intervalo de verde disponível; a estimativa só dimensiona o decaimento de ε.
    estimated_decisions = int(args.episodes * args.control_seconds / (2 * args.decision_interval))
    policy = DqnPolicy(agent, EpsilonSchedule(args.epsilon_start, args.epsilon_end, int(args.epsilon_decay_fraction * estimated_decisions)))
    selector = CheckpointSelector(SelectionCriteria(min_gradient_steps=args.min_gradient_steps))
    metadata_base = {
        "state_version": args.state_version, "feature_names": list(environment.encoder.feature_names), "lane_order": [list(key) for key in SP_LANE_ORDER],
        "feature_source": "traci_oracle", "oracle_noise": asdict(environment.noise), "decision_interval_s": args.decision_interval,
        "gamma_per_second": args.gamma, "warmup_s": args.warmup_seconds, "control_s": args.control_seconds,
        "validation_seeds": validation_seeds, "double_dqn": args.double_dqn,
        "pedestrian_reward_weight": config.get("pedestrians", {}).get("reward_weight"),
        "training_scenarios": [scenario or config["sumo"].get("default_scenario") for scenario in scenarios],
    }
    logs: list[dict[str, Any]] = []

    def validate(label: str, validation_policy: Policy) -> tuple[float, float | None]:
        """Média do escore em todas as seeds de validação de todos os cenários de treino."""
        outcomes, per_scenario = [], {}
        for env in environments:
            runs = [env.run(seed, validation_policy) for seed in validation_seeds]
            for seed, (outcome, scenario) in zip(validation_seeds, runs):
                logs.append({"split": "validation", "policy": label, "scenario": scenario, "seed": seed, **outcome.summary()})
            per_scenario[runs[0][1]] = sum(outcome.mean_reward for outcome, _ in runs) / len(runs)
            outcomes += [outcome for outcome, _ in runs]
        score = sum(outcome.mean_reward for outcome in outcomes) / len(outcomes)
        rates = [outcome.switch_rate for outcome in outcomes if outcome.switch_rate is not None]
        switch_rate = None if not rates else sum(rates) / len(rates)
        if len(per_scenario) > 1:
            print("dqn_v2_validation_by_scenario policy=" + label + " " + " ".join(f"{name}={value:.4f}" for name, value in per_scenario.items()))
        return score, switch_rate

    try:
        for label, reference in (("fixed_cycle", FixedCyclePolicy()), ("max_pressure", MaxPressurePolicy())):
            score, switch_rate = validate(label, reference)
            print(f"dqn_v2_reference policy={label} validation_score={score:.4f} switch_rate={switch_rate}")
        for episode, seed in enumerate(training_seeds):
            started = perf_counter()
            outcome, scenario = environments[episode % len(environments)].run(seed, policy, learner=agent)
            epsilon = policy.current_epsilon()
            logs.append({"split": "train", "episode": episode, "seed": seed, "epsilon": epsilon,
                         "gradient_steps": agent.training_steps, "replay_size": len(agent.replay), **outcome.summary()})
            agent.save(args.checkpoint_output, {**metadata_base, "kind": "latest", "scenario": scenario, "training_episode": episode})
            print(f"dqn_v2_episode episode={episode} seed={seed} scenario={scenario} reward={outcome.mean_reward:.4f} switch_rate={outcome.switch_rate} "
                  f"epsilon={epsilon:.3f} gradient_steps={agent.training_steps} seconds={perf_counter() - started:.1f}")
            if (episode + 1) % args.validation_interval and episode + 1 != args.episodes:
                continue
            score, switch_rate = validate("dqn", DqnPolicy(agent))
            record = ValidationRecord(episode, score, agent.training_steps, epsilon, switch_rate)
            warning = selector.degeneracy(switch_rate)
            selected = selector.consider(record)
            logs.append({"split": "selection", **asdict(record), "selected": selected, "degeneracy": warning})
            print(f"dqn_v2_validation after_episode={episode} score={score:.4f} switch_rate={switch_rate} "
                  f"selected={selected} eligible={selector.eligible(record)} degeneracy={warning}")
            if selected:
                agent.save(args.best_checkpoint_output, {**metadata_base, "kind": "best_validation", "scenario": scenario,
                                                         "training_episode": episode, "validation_score": score,
                                                         "validation_switch_rate": switch_rate})
    finally:
        args.log_output.parent.mkdir(parents=True, exist_ok=True)
        args.log_output.write_text("".join(json.dumps(item, default=str) + "\n" for item in logs), encoding="utf-8")
    best = selector.best
    print(f"dqn_v2_pretrain_complete episodes={args.episodes} best_episode={None if best is None else best.episode} "
          f"best_score={None if best is None else round(best.score, 4)} best_checkpoint={args.best_checkpoint_output if best else 'unavailable'} "
          f"log={args.log_output}")


if __name__ == "__main__":
    main()
