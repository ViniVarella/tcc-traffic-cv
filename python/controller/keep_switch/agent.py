"""DQN da linha manter/trocar: duas ações (manter ou trocar o verde) sobre um vetor de estado.

É o agente dos DQN estado v1, v2 e v3 do cruzamento de SP (o especialista do
produto v3.0–v5.0 é o estado v2). A montagem das redes, o replay, a otimização
e o checkpoint vêm de ``controller.dqn_base``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch
from torch import nn
from torch.nn import functional as functional

from controller.dqn_base import DqnAgentBase, Transition

__all__ = ["DqnAgent", "DqnConfig", "QNetwork", "Transition"]


@dataclass(frozen=True)
class DqnConfig:
    state_size: int
    action_size: int = 2
    hidden_size: int = 64
    gamma: float = 0.90
    learning_rate: float = 0.001
    batch_size: int = 32
    replay_capacity: int = 50_000
    min_replay_size: int = 256
    target_update_interval: int = 250
    # 1 = contagens (13 entradas); 2 = features por faixa. Checkpoints antigos
    # não gravavam o campo e por isso carregam como versão 1.
    state_version: int = 1
    # Double DQN: a rede online escolhe a ação do próximo estado e a rede-alvo a avalia.
    double_dqn: bool = False


class QNetwork(nn.Module):
    def __init__(self, state_size: int, action_size: int, hidden_size: int) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(state_size, hidden_size), nn.ReLU(),
            nn.Linear(hidden_size, hidden_size), nn.ReLU(),
            nn.Linear(hidden_size, action_size),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.layers(state)


class DqnAgent(DqnAgentBase):
    """Agente DQN com replay buffer, Huber loss e rede-alvo periódica."""

    CONFIG_CLASS = DqnConfig

    def __init__(self, config: DqnConfig, device: str | None = None, seed: int = 42) -> None:
        if config.state_size <= 0 or config.action_size <= 1:
            raise ValueError("DQN requer estado positivo e pelo menos duas ações.")
        default_device = "mps" if torch.backends.mps.is_available() else "cpu"
        super().__init__(config, torch.device(device or default_device), seed)

    def _build_network(self) -> nn.Module:
        return QNetwork(self.config.state_size, self.config.action_size, self.config.hidden_size)

    def q_values(self, state: np.ndarray) -> np.ndarray:
        """Valores Q da rede online para um estado (diagnóstico e política gulosa)."""
        with torch.no_grad():
            values = self.online(torch.as_tensor(self._validate_state(state), dtype=torch.float32, device=self.device).unsqueeze(0))
        return values.squeeze(0).cpu().numpy()

    def select_action(self, state: np.ndarray, epsilon: float, explore: bool = True) -> int:
        """Ação ε-gulosa: aleatória com probabilidade ``epsilon`` (se ``explore``), senão a de maior Q."""
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon deve estar entre 0 e 1.")
        state = self._validate_state(state)
        if explore and self._random.random() < epsilon:
            return self._random.randrange(self.config.action_size)
        with torch.no_grad():
            values = self.online(torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0))
        return int(values.argmax(dim=1).item())

    def remember(self, state: np.ndarray, action: int, reward: float, next_state: np.ndarray, done: bool,
                 discount: float | None = None) -> None:
        """Guarda uma transição no replay; ``discount`` é ``gamma ** k`` nas transições SMDP."""
        if not 0 <= action < self.config.action_size:
            raise ValueError(f"Ação inválida: {action}.")
        discount = self._discount(discount)
        self.replay.append(Transition(self._validate_state(state), action, float(reward), self._validate_state(next_state),
                                      bool(done), discount))

    def train_step(self) -> float | None:
        """Um passo de TD num lote do replay; ``None`` enquanto o replay não tem o mínimo."""
        if len(self.replay) < max(self.config.min_replay_size, self.config.batch_size):
            return None
        batch = self._random.sample(self.replay, self.config.batch_size)
        states = torch.as_tensor(np.stack([item.state for item in batch]), dtype=torch.float32, device=self.device)
        actions = torch.as_tensor([item.action for item in batch], dtype=torch.int64, device=self.device).unsqueeze(1)
        rewards = torch.as_tensor([item.reward for item in batch], dtype=torch.float32, device=self.device)
        next_states = torch.as_tensor(np.stack([item.next_state for item in batch]), dtype=torch.float32, device=self.device)
        dones = torch.as_tensor([item.done for item in batch], dtype=torch.float32, device=self.device)
        discounts = torch.as_tensor([item.discount for item in batch], dtype=torch.float32, device=self.device)
        q_values = self.online(states).gather(1, actions).squeeze(1)
        with torch.no_grad():
            if self.config.double_dqn:
                next_actions = self.online(next_states).argmax(dim=1, keepdim=True)
                next_values = self.target(next_states).gather(1, next_actions).squeeze(1)
            else:
                next_values = self.target(next_states).max(dim=1).values
            targets = rewards + discounts * (1.0 - dones) * next_values
        return self._optimize(functional.smooth_l1_loss(q_values, targets))
