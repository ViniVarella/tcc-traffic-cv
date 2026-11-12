"""Partes comuns aos dois agentes DQN (manter/trocar e escolha de estágio).

Cada agente define a rede (``_build_network``) e o passo de treino; aqui ficam
a montagem das redes online e alvo, o replay, a otimização com rede-alvo
periódica, a validação do estado e o checkpoint. O checkpoint guarda só
dicionários e tensores (``weights_only=True``), então o nome dos módulos pode
mudar sem invalidar os arquivos salvos.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Deque, Mapping, NamedTuple

import numpy as np
import torch
from torch import nn


class Transition(NamedTuple):
    """Uma transição do replay (SMDP: ``discount`` = ``gamma ** k``)."""

    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    # Desconto aplicado ao valor do próximo estado: gamma para transições de um
    # step ou gamma ** k para transições SMDP que duram k steps.
    discount: float


class DqnAgentBase:
    """Redes online e alvo, replay, otimização e checkpoint de um agente DQN.

    Subclasses definem ``CONFIG_CLASS``, ``_build_network`` e ``train_step``; a
    configuração precisa de ``state_size``, ``gamma``, ``learning_rate``,
    ``replay_capacity`` e ``target_update_interval``.
    """

    CONFIG_CLASS: type

    def __init__(self, config: Any, device: torch.device, seed: int) -> None:
        self.config = config
        self.device = device
        self._random = random.Random(seed)
        torch.manual_seed(seed)
        self.online = self._build_network().to(self.device)
        self.target = self._build_network().to(self.device)
        self.target.load_state_dict(self.online.state_dict())
        self.target.eval()
        self.optimizer = torch.optim.Adam(self.online.parameters(), lr=config.learning_rate)
        self.replay: Deque[Transition] = deque(maxlen=config.replay_capacity)
        self.training_steps = 0
        self.metadata: dict[str, Any] = {}

    def _build_network(self) -> nn.Module:
        raise NotImplementedError

    def _discount(self, discount: float | None) -> float:
        """Desconto da transição: ``gamma`` por padrão, ``gamma ** k`` nas transições SMDP."""
        value = self.config.gamma if discount is None else float(discount)
        if not 0.0 <= value <= 1.0:
            raise ValueError("discount deve estar entre 0 e 1.")
        return value

    def _optimize(self, loss: torch.Tensor) -> float:
        """Um passo do Adam (gradiente limitado a 1) e a sincronização periódica da rede-alvo."""
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.online.parameters(), max_norm=1.0)
        self.optimizer.step()
        self.training_steps += 1
        if self.training_steps % self.config.target_update_interval == 0:
            self.target.load_state_dict(self.online.state_dict())
        return float(loss.item())

    def _batch_tensors(self, batch: list[Transition]) -> tuple[torch.Tensor, ...]:
        """Lote do replay em tensores: estados, ações (B, 1), recompensas, próximos estados, fins e descontos."""
        states = torch.as_tensor(np.stack([item.state for item in batch]), dtype=torch.float32, device=self.device)
        actions = torch.as_tensor([item.action for item in batch], dtype=torch.int64, device=self.device).unsqueeze(1)
        rewards = torch.as_tensor([item.reward for item in batch], dtype=torch.float32, device=self.device)
        next_states = torch.as_tensor(np.stack([item.next_state for item in batch]), dtype=torch.float32, device=self.device)
        dones = torch.as_tensor([item.done for item in batch], dtype=torch.float32, device=self.device)
        discounts = torch.as_tensor([item.discount for item in batch], dtype=torch.float32, device=self.device)
        return states, actions, rewards, next_states, dones, discounts

    def save(self, path: str | Path, metadata: Mapping[str, Any] | None = None) -> None:
        """Salva pesos e estado de treinamento; ``metadata`` documenta a seleção do modelo."""
        checkpoint = {
            "config": asdict(self.config),
            "model_state": self.online.state_dict(),
            "target_model_state": self.target.state_dict(),
            "optimizer_state": self.optimizer.state_dict(),
            "training_steps": self.training_steps,
            "metadata": dict(metadata or {}),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(checkpoint, Path(path))

    @classmethod
    def load(cls, path: str | Path, device: str | None = None) -> Any:
        """Carrega um checkpoint salvo por ``save``; a rede online fica em modo de avaliação."""
        checkpoint = torch.load(Path(path), map_location=device or "cpu", weights_only=True)
        config = cls.CONFIG_CLASS(**checkpoint["config"])
        cls._check_loaded_config(config)
        agent = cls(config, device=device)
        agent.online.load_state_dict(checkpoint["model_state"])
        agent.target.load_state_dict(checkpoint.get("target_model_state", checkpoint["model_state"]))
        if "optimizer_state" in checkpoint:
            agent.optimizer.load_state_dict(checkpoint["optimizer_state"])
        agent.training_steps = int(checkpoint.get("training_steps", 0))
        agent.metadata = dict(checkpoint.get("metadata", {}))
        agent.online.eval()
        return agent

    @classmethod
    def _check_loaded_config(cls, config: Any) -> None:
        """Recusa checkpoints incompatíveis; por padrão aceita qualquer configuração."""

    def _validate_state(self, state: np.ndarray) -> np.ndarray:
        result = np.asarray(state, dtype=np.float32).reshape(-1)
        if result.shape != (self.config.state_size,):
            raise ValueError(f"Estado deve ter {self.config.state_size} entradas; recebeu {result.shape}.")
        return result.copy()


@dataclass(frozen=True, slots=True)
class EpsilonSchedule:
    """ε linear por decisão, de ``start`` a ``end`` em ``decay_decisions``."""

    start: float = 1.0
    end: float = 0.05
    decay_decisions: int = 10_000

    def value(self, decision_index: int) -> float:
        if self.decay_decisions <= 0:
            return self.end
        fraction = min(1.0, max(0, decision_index) / self.decay_decisions)
        return self.start + (self.end - self.start) * fraction


class EpsilonGreedyPolicy:
    """Política ε-gulosa sobre um agente; conta as decisões para o decaimento de ε.

    ``epsilon`` é um ``EpsilonSchedule`` ou ``None`` (sempre guloso, como na avaliação).
    """

    name = "dqn"

    def __init__(self, agent: Any, epsilon: EpsilonSchedule | None = None) -> None:
        self.agent = agent
        self.epsilon = epsilon
        self.decisions = 0

    def current_epsilon(self) -> float:
        return 0.0 if self.epsilon is None else self.epsilon.value(self.decisions)

    def _choose(self, state: np.ndarray) -> int:
        epsilon = self.current_epsilon()
        self.decisions += 1
        return self.agent.select_action(state, epsilon=epsilon, explore=epsilon > 0)
