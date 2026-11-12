"""Pré-treino do DQN de seleção livre de fase nos cruzamentos de treino (só SUMO).

Os episódios alternam entre todos os cenários ``split: train`` de
``configs/generic.yaml`` (cruzamento × demanda); a seed avança a cada volta
completa. A validação usa as seeds 1001+ nos mesmos cenários de treino; os
cruzamentos de teste (incluindo o SP) nunca são vistos aqui.

Antes do RL, ``--demo-episodes`` episódios do max-pressure acíclico (seeds
``--demo-seed-start``+) enchem o replay de demonstrações e
``--demo-pretrain-steps`` passos treinam só nelas (DQfD); a validação logo
depois (``after_episode=-1``) mostra o ponto de partida do RL.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from paths import PYTHON_DIR
from controller.phase_selection.agent import PhaseAgentConfig, PhaseSelectionAgent
from controller.phase_selection.policies import FixedTimePhasePolicy, MaxPressurePhasePolicy, PhaseDqnPolicy
from controller.phase_selection.state import ROW_FEATURES_BY_VERSION
from simulation.checkpoint_selection import CheckpointSelector, SelectionCriteria, ValidationRecord
from simulation.episode import EpisodeSettings, EpsilonSchedule
from simulation.phase_selection_environment import PhaseSelectionEnvironment, PolicyFactory


class DemonstrationLearner:
    """Repassa ao agente as transições de outra política como demonstrações."""

    def __init__(self, agent: PhaseSelectionAgent) -> None:
        self.agent = agent

    def remember(self, state: Any, action: int, reward: float, next_state: Any, done: bool, discount: float | None = None) -> None:
        self.agent.remember(state, action, reward, next_state, done, discount=discount, demo=True)

    def train_step(self) -> float | None:
        return self.agent.train_step()


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
    parser.add_argument("--init-checkpoint", type=Path, default=None,
                        help="Parte deste checkpoint (ex.: o da imitação) em vez de pesos aleatórios.")
    parser.add_argument("--demo-episodes", type=int, default=48, help="Episódios de demonstração do max-pressure (0 desliga).")
    parser.add_argument("--demo-batch-fraction", type=float, default=0.25, help="Fração do lote vinda das demonstrações.")
    parser.add_argument("--demo-loss-weight", type=float, default=1.0, help="Peso da perda de margem do DQfD (0 = só TD).")
    parser.add_argument("--rl-without-demonstrations", action="store_true",
                        help="Depois dos passos só com demonstrações, o RL segue sem elas (fração e margem zeradas): "
                             "a imitação vira só o ponto de partida.")
    parser.add_argument("--demo-seed-start", type=int, default=41)
    parser.add_argument("--demo-pretrain-steps", type=int, default=5_000)
    parser.add_argument("--epsilon-start", type=float, default=0.2, help="Baixo: o RL parte da imitação do max-pressure.")
    parser.add_argument("--epsilon-end", type=float, default=0.05)
    parser.add_argument("--epsilon-decay-fraction", type=float, default=0.5)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=None,
                        help="Padrão 0,001; com --init-checkpoint, sem o valor segue o do checkpoint.")
    parser.add_argument("--min-gradient-steps", type=int, default=5_000)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--checkpoint-output", type=Path, default=base_dir.parent / "results" / "models" / "dqn-fase-livre-last.pt")
    parser.add_argument("--best-checkpoint-output", type=Path, default=base_dir.parent / "results" / "models" / "dqn-fase-livre-best.pt")
    parser.add_argument("--log-output", type=Path, default=base_dir.parent / "results" / "logs" / "dqn-fase-livre-pretrain.jsonl")
    return parser.parse_args()


def main() -> None:
    base_dir = PYTHON_DIR
    args = parse_args(base_dir)
    settings = EpisodeSettings(args.warmup_seconds, args.control_seconds, args.decision_interval, args.gamma)
    environment = PhaseSelectionEnvironment.from_file(args.config.resolve(), settings)
    scenarios = environment.split("train")
    validation_seeds = [int(item) for item in args.validation_seeds.split(",") if item.strip()]
    last_seed = args.seed_start + (args.episodes - 1) // len(scenarios)
    train_seeds = set(range(args.seed_start, last_seed + 1))
    demo_seeds = set(range(args.demo_seed_start, args.demo_seed_start + (args.demo_episodes + len(scenarios) - 1) // max(1, len(scenarios))))
    if (not scenarios or args.episodes <= 0 or args.demo_episodes < 0 or train_seeds & set(validation_seeds)
            or demo_seeds & (train_seeds | set(validation_seeds))):
        raise ValueError("Requer cenários de treino, episódios positivos e seeds de treino, demonstração e validação disjuntas.")
    if args.init_checkpoint is None:
        agent = PhaseSelectionAgent(PhaseAgentConfig(max_phases=environment.max_phases, hidden_size=args.hidden_size,
                                                     gamma=args.gamma, learning_rate=args.learning_rate or 0.001,
                                                     demo_batch_fraction=args.demo_batch_fraction,
                                                     demo_loss_weight=args.demo_loss_weight),
                                    device=args.device, seed=args.seed_start)
    else:
        agent = PhaseSelectionAgent.load(args.init_checkpoint, device=args.device)
        agent.config = replace(agent.config, demo_batch_fraction=args.demo_batch_fraction, demo_loss_weight=args.demo_loss_weight)
        if args.learning_rate is not None:
            agent.config = replace(agent.config, learning_rate=args.learning_rate)
            for group in agent.optimizer.param_groups:
                group["lr"] = args.learning_rate
        agent.online.train()
    # ~1 decisão a cada 10 s de controle; a estimativa só dimensiona o decaimento de ε.
    estimated_decisions = int(args.episodes * args.control_seconds / 10.0)
    policy = PhaseDqnPolicy(agent, EpsilonSchedule(args.epsilon_start, args.epsilon_end, int(args.epsilon_decay_fraction * estimated_decisions)))
    selector = CheckpointSelector(SelectionCriteria(min_gradient_steps=args.min_gradient_steps))
    metadata_base = {
        "state_version": agent.config.state_version, "row_features": list(ROW_FEATURES_BY_VERSION[agent.config.state_version]), "feature_source": "traci_oracle",
        "decision_interval_s": args.decision_interval, "gamma_per_second": args.gamma, "warmup_s": args.warmup_seconds,
        "control_s": args.control_seconds, "validation_seeds": validation_seeds,
        "training_scenarios": [scenario.name for scenario in scenarios],
        "demonstrations": {"policy": "max_pressure", "episodes": args.demo_episodes, "seeds": sorted(demo_seeds),
                           "pretrain_steps": args.demo_pretrain_steps, "batch_fraction": args.demo_batch_fraction,
                           "loss_weight": args.demo_loss_weight, "rl_without": args.rl_without_demonstrations},
        "init_checkpoint": None if args.init_checkpoint is None else str(args.init_checkpoint),
    }
    logs: list[dict[str, Any]] = []

    def validate(label: str, make_policy: PolicyFactory) -> tuple[float, float | None]:
        """Média da recompensa em todos os cenários de treino nas seeds de validação."""
        outcomes = []
        for scenario in scenarios:
            for seed in validation_seeds:
                outcome = environment.run(scenario, seed, make_policy, state_version=agent.config.state_version)
                outcomes.append(outcome)
                logs.append({"split": "validation", "policy": label, "scenario": scenario.name, "seed": seed, **outcome.summary()})
        score = sum(outcome.mean_reward for outcome in outcomes) / len(outcomes)
        rates = [outcome.switch_rate for outcome in outcomes if outcome.switch_rate is not None]
        return score, None if not rates else sum(rates) / len(rates)

    try:
        for label, reference in (("fixed_time", FixedTimePhasePolicy.from_layout), ("max_pressure", lambda layout: MaxPressurePhasePolicy())):
            score, switch_rate = validate(label, reference)
            print(f"phase_select_reference policy={label} validation_score={score:.4f} switch_rate={switch_rate}", flush=True)
        demonstrator = DemonstrationLearner(agent)
        for index in range(args.demo_episodes):
            scenario = scenarios[index % len(scenarios)]
            seed = args.demo_seed_start + index // len(scenarios)
            outcome = environment.run(scenario, seed, lambda layout: MaxPressurePhasePolicy(), learner=demonstrator,
                                      state_version=agent.config.state_version)
            logs.append({"split": "demonstration", "episode": index, "scenario": scenario.name, "seed": seed,
                         "demo_replay_size": len(agent.demo_replay), **outcome.summary()})
            print(f"phase_select_demo episode={index} scenario={scenario.name} seed={seed} "
                  f"demo_replay={len(agent.demo_replay)} gradient_steps={agent.training_steps}", flush=True)
        if args.demo_episodes or args.init_checkpoint is not None:
            for _ in range(args.demo_pretrain_steps if args.demo_episodes else 0):
                agent.train_step()
            if args.rl_without_demonstrations:
                agent.config = replace(agent.config, demo_batch_fraction=0.0, demo_loss_weight=0.0)
            greedy = PhaseDqnPolicy(agent)
            score, switch_rate = validate("dqn", lambda layout: greedy)
            record = ValidationRecord(-1, score, agent.training_steps, args.epsilon_start, switch_rate)
            selected = selector.consider(record)
            logs.append({"split": "selection", **asdict(record), "selected": selected})
            print(f"phase_select_validation after_episode=-1 score={score:.4f} switch_rate={switch_rate} "
                  f"selected={selected} eligible={selector.eligible(record)}", flush=True)
            if selected:
                agent.save(args.best_checkpoint_output, {**metadata_base, "kind": "best_validation", "training_episode": -1,
                                                         "validation_score": score, "validation_switch_rate": switch_rate})
        for episode in range(args.episodes):
            started = perf_counter()
            scenario = scenarios[episode % len(scenarios)]
            seed = args.seed_start + episode // len(scenarios)
            outcome = environment.run(scenario, seed, lambda layout: policy, learner=agent, state_version=agent.config.state_version)
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
