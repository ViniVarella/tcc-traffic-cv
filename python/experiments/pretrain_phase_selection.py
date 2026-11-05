"""Pré-treino do DQN de seleção livre de fase nos cruzamentos de treino (só SUMO).

Os episódios alternam entre todos os cenários ``split: train`` de
``configs/generic.yaml`` (cruzamento × demanda); a seed avança a cada volta
completa. A validação usa as seeds 1001+ nos mesmos cenários de treino; os
cruzamentos de teste (incluindo o SP) nunca são vistos aqui.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from controller.phase_selection_agent import PhaseAgentConfig, PhaseSelectionAgent
from controller.phase_selection_policies import FixedTimePhasePolicy, MaxPressurePhasePolicy, PhaseDqnPolicy
from controller.phase_selection_state import ROW_FEATURE_NAMES
from experiments.checkpoint_selection import CheckpointSelector, SelectionCriteria, ValidationRecord
from experiments.episode_runner import EpisodeSettings, EpsilonSchedule
from experiments.phase_selection_environment import PhaseSelectionEnvironment, PolicyFactory


def fixed_time(layout: Any) -> FixedTimePhasePolicy:
    return FixedTimePhasePolicy([green.duration_s for green in layout.greens])


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pré-treina o DQN de seleção livre de fase nos cruzamentos sintéticos.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "generic.yaml")
    parser.add_argument("--episodes", type=int, default=240)
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--validation-seeds", default="1001")
    parser.add_argument("--validation-interval", type=int, default=24)
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=1800.0)
    parser.add_argument("--decision-interval", type=float, default=5.0)
    parser.add_argument("--gamma", type=float, default=0.99, help="Desconto por segundo simulado (transições SMDP).")
    parser.add_argument("--epsilon-start", type=float, default=1.0)
    parser.add_argument("--epsilon-end", type=float, default=0.05)
    parser.add_argument("--epsilon-decay-fraction", type=float, default=0.5)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--min-gradient-steps", type=int, default=5_000)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--checkpoint-output", type=Path, default=base_dir.parent / "results" / "models" / "dqn-fase-livre-last.pt")
    parser.add_argument("--best-checkpoint-output", type=Path, default=base_dir.parent / "results" / "models" / "dqn-fase-livre-best.pt")
    parser.add_argument("--log-output", type=Path, default=base_dir.parent / "results" / "logs" / "dqn-fase-livre-pretrain.jsonl")
    return parser.parse_args()


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    settings = EpisodeSettings(args.warmup_seconds, args.control_seconds, args.decision_interval, args.gamma)
    environment = PhaseSelectionEnvironment.from_file(args.config.resolve(), settings)
    scenarios = environment.split("train")
    validation_seeds = [int(item) for item in args.validation_seeds.split(",") if item.strip()]
    last_seed = args.seed_start + (args.episodes - 1) // len(scenarios)
    if not scenarios or args.episodes <= 0 or set(range(args.seed_start, last_seed + 1)) & set(validation_seeds):
        raise ValueError("Requer cenários de treino, episódios positivos e seeds de treino e validação disjuntas.")
    agent = PhaseSelectionAgent(PhaseAgentConfig(max_phases=environment.max_phases, hidden_size=args.hidden_size,
                                                 gamma=args.gamma, learning_rate=args.learning_rate),
                                device=args.device, seed=args.seed_start)
    # ~1 decisão a cada 10 s de controle; a estimativa só dimensiona o decaimento de ε.
    estimated_decisions = int(args.episodes * args.control_seconds / 10.0)
    policy = PhaseDqnPolicy(agent, EpsilonSchedule(args.epsilon_start, args.epsilon_end, int(args.epsilon_decay_fraction * estimated_decisions)))
    selector = CheckpointSelector(SelectionCriteria(min_gradient_steps=args.min_gradient_steps))
    metadata_base = {
        "state_version": agent.config.state_version, "row_features": list(ROW_FEATURE_NAMES), "feature_source": "traci_oracle",
        "decision_interval_s": args.decision_interval, "gamma_per_second": args.gamma, "warmup_s": args.warmup_seconds,
        "control_s": args.control_seconds, "validation_seeds": validation_seeds,
        "training_scenarios": [scenario.name for scenario in scenarios],
    }
    logs: list[dict[str, Any]] = []

    def validate(label: str, make_policy: PolicyFactory) -> tuple[float, float | None]:
        """Média da recompensa em todos os cenários de treino nas seeds de validação."""
        outcomes = []
        for scenario in scenarios:
            for seed in validation_seeds:
                outcome = environment.run(scenario, seed, make_policy)
                outcomes.append(outcome)
                logs.append({"split": "validation", "policy": label, "scenario": scenario.name, "seed": seed, **outcome.summary()})
        score = sum(outcome.mean_reward for outcome in outcomes) / len(outcomes)
        rates = [outcome.switch_rate for outcome in outcomes if outcome.switch_rate is not None]
        return score, None if not rates else sum(rates) / len(rates)

    try:
        for label, reference in (("fixed_time", fixed_time), ("max_pressure", lambda layout: MaxPressurePhasePolicy())):
            score, switch_rate = validate(label, reference)
            print(f"phase_select_reference policy={label} validation_score={score:.4f} switch_rate={switch_rate}", flush=True)
        for episode in range(args.episodes):
            started = perf_counter()
            scenario = scenarios[episode % len(scenarios)]
            seed = args.seed_start + episode // len(scenarios)
            outcome = environment.run(scenario, seed, lambda layout: policy, learner=agent)
            epsilon = policy.current_epsilon()
            logs.append({"split": "train", "episode": episode, "scenario": scenario.name, "seed": seed, "epsilon": epsilon,
                         "gradient_steps": agent.training_steps, "replay_size": len(agent.replay), **outcome.summary()})
            agent.save(args.checkpoint_output, {**metadata_base, "kind": "latest", "training_episode": episode})
            print(f"phase_select_episode episode={episode} scenario={scenario.name} seed={seed} reward={outcome.mean_reward:.4f} "
                  f"switch_rate={outcome.switch_rate} wait={outcome.metrics['mean_waiting_time_seconds']:.1f} epsilon={epsilon:.3f} "
                  f"gradient_steps={agent.training_steps} seconds={perf_counter() - started:.1f}", flush=True)
            if (episode + 1) % args.validation_interval and episode + 1 != args.episodes:
                continue
            greedy = PhaseDqnPolicy(agent)
            score, switch_rate = validate("dqn", lambda layout: greedy)
            record = ValidationRecord(episode, score, agent.training_steps, epsilon, switch_rate)
            selected = selector.consider(record)
            logs.append({"split": "selection", **asdict(record), "selected": selected})
            print(f"phase_select_validation after_episode={episode} score={score:.4f} switch_rate={switch_rate} "
                  f"selected={selected} eligible={selector.eligible(record)}", flush=True)
            if selected:
                agent.save(args.best_checkpoint_output, {**metadata_base, "kind": "best_validation", "training_episode": episode,
                                                         "validation_score": score, "validation_switch_rate": switch_rate})
    finally:
        args.log_output.parent.mkdir(parents=True, exist_ok=True)
        args.log_output.write_text("".join(json.dumps(item, default=str) + "\n" for item in logs), encoding="utf-8")
    best = selector.best
    print(f"phase_select_pretrain_complete episodes={args.episodes} best_episode={None if best is None else best.episode} "
          f"best_score={None if best is None else round(best.score, 4)} best_checkpoint={args.best_checkpoint_output if best else 'unavailable'} "
          f"log={args.log_output}", flush=True)


if __name__ == "__main__":
    main()
