"""DQN vetorial em PyTorch para decisão semafórica baseada em visão."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
import random
from typing import Any, Deque, Mapping, NamedTuple

import numpy as np
import torch
from torch import nn
from torch.nn import functional as functional


class Transition(NamedTuple):
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool


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


class DqnAgent:
    """Agente DQN com replay buffer, Huber loss e rede-alvo periódica."""

    def __init__(self, config: DqnConfig, device: str | None = None, seed: int = 42) -> None:
        if config.state_size <= 0 or config.action_size <= 1:
            raise ValueError("DQN requer estado positivo e pelo menos duas ações.")
        self.config = config
        self.device = torch.device(device or ("mps" if torch.backends.mps.is_available() else "cpu"))
        self._random = random.Random(seed)
        torch.manual_seed(seed)
        self.online = QNetwork(config.state_size, config.action_size, config.hidden_size).to(self.device)
        self.target = QNetwork(config.state_size, config.action_size, config.hidden_size).to(self.device)
        self.target.load_state_dict(self.online.state_dict())
        self.target.eval()
        self.optimizer = torch.optim.Adam(self.online.parameters(), lr=config.learning_rate)
        self.replay: Deque[Transition] = deque(maxlen=config.replay_capacity)
        self.training_steps = 0

    def select_action(self, state: np.ndarray, epsilon: float, explore: bool = True) -> int:
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon deve estar entre 0 e 1.")
        state = self._validate_state(state)
        if explore and self._random.random() < epsilon:
            return self._random.randrange(self.config.action_size)
        with torch.no_grad():
            values = self.online(torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0))
        return int(values.argmax(dim=1).item())

    def remember(self, state: np.ndarray, action: int, reward: float, next_state: np.ndarray, done: bool) -> None:
        if not 0 <= action < self.config.action_size:
            raise ValueError(f"Ação inválida: {action}.")
        self.replay.append(Transition(self._validate_state(state), action, float(reward), self._validate_state(next_state), bool(done)))

    def train_step(self) -> float | None:
        if len(self.replay) < self.config.min_replay_size:
            return None
        batch = self._random.sample(self.replay, self.config.batch_size)
        states = torch.as_tensor(np.stack([item.state for item in batch]), dtype=torch.float32, device=self.device)
        actions = torch.as_tensor([item.action for item in batch], dtype=torch.int64, device=self.device).unsqueeze(1)
        rewards = torch.as_tensor([item.reward for item in batch], dtype=torch.float32, device=self.device)
        next_states = torch.as_tensor(np.stack([item.next_state for item in batch]), dtype=torch.float32, device=self.device)
        dones = torch.as_tensor([item.done for item in batch], dtype=torch.float32, device=self.device)
        q_values = self.online(states).gather(1, actions).squeeze(1)
        with torch.no_grad():
            targets = rewards + self.config.gamma * (1.0 - dones) * self.target(next_states).max(dim=1).values
        loss = functional.smooth_l1_loss(q_values, targets)
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.online.parameters(), max_norm=1.0)
        self.optimizer.step()
        self.training_steps += 1
        if self.training_steps % self.config.target_update_interval == 0:
            self.target.load_state_dict(self.online.state_dict())
        return float(loss.item())

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
    def load(cls, path: str | Path, device: str | None = None) -> "DqnAgent":
        checkpoint = torch.load(Path(path), map_location=device or "cpu", weights_only=True)
        agent = cls(DqnConfig(**checkpoint["config"]), device=device)
        agent.online.load_state_dict(checkpoint["model_state"])
        agent.target.load_state_dict(checkpoint.get("target_model_state", checkpoint["model_state"]))
        if "optimizer_state" in checkpoint:
            agent.optimizer.load_state_dict(checkpoint["optimizer_state"])
        agent.training_steps = int(checkpoint.get("training_steps", 0))
        agent.online.eval()
        return agent

    def _validate_state(self, state: np.ndarray) -> np.ndarray:
        result = np.asarray(state, dtype=np.float32).reshape(-1)
        if result.shape != (self.config.state_size,):
            raise ValueError(f"Estado deve ter {self.config.state_size} entradas; recebeu {result.shape}.")
        return result.copy()
