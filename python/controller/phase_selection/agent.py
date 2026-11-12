"""DQN com pesos compartilhados entre fases: uma nota por fase candidata.

A mesma MLP embute cada linha do estado por fase (``phase_selection_state``);
a média e o máximo das linhas das fases existentes resumem o cruzamento. Rede
*dueling*: ``Q(s, fase) = V(resumo) + A(linha, resumo) − média das vantagens
válidas``, então o modelo serve para qualquer número de fases (até
``max_phases``) e cada nota sabe o que acontece no resto do cruzamento. Double
DQN com máscara: fases inexistentes ou proibidas pela camada de segurança
nunca são escolhidas nem entram no alvo.

Demonstrações (DQfD, Hester et al. 2018): transições de outra política (o
max-pressure) ficam num replay próprio, permanente; a cada passo uma fração do
lote vem delas e, nelas, uma perda de margem empurra a ação demonstrada acima
das outras em ``demo_margin``. O agente começa imitando a demonstração e o
TD aprende a superá-la.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
import random
from typing import Any, Deque, Mapping

import numpy as np
import torch
from torch import nn
from torch.nn import functional as functional

from controller.keep_switch.agent import Transition
from .state import LANE_COUNT_INDEX, ROW_FEATURE_NAMES, ROW_FEATURES_BY_VERSION, STATE_VERSION


MASKED_Q = -1e9


@dataclass(frozen=True)
class PhaseAgentConfig:
    max_phases: int = 8
    row_size: int = len(ROW_FEATURE_NAMES)
    hidden_size: int = 64
    gamma: float = 0.99
    learning_rate: float = 0.001
    batch_size: int = 32
    replay_capacity: int = 50_000
    min_replay_size: int = 256
    target_update_interval: int = 250
    double_dqn: bool = True
    demo_batch_fraction: float = 0.25
    demo_margin: float = 0.5
    demo_loss_weight: float = 1.0
    state_version: str = STATE_VERSION

    @property
    def state_size(self) -> int:
        return self.max_phases * (self.row_size + 1)


class PhaseScoringNetwork(nn.Module):
    """Linhas ``(B, P, d)`` → notas ``(B, P)``, invariante à ordem e ao número de fases."""

    def __init__(self, row_size: int, hidden_size: int) -> None:
        super().__init__()
        self.embed = nn.Sequential(
            nn.Linear(row_size, hidden_size), nn.ReLU(),
            nn.Linear(hidden_size, hidden_size), nn.ReLU(),
        )
        self.value = nn.Sequential(nn.Linear(2 * hidden_size, hidden_size), nn.ReLU(), nn.Linear(hidden_size, 1))
        self.advantage = nn.Sequential(nn.Linear(3 * hidden_size, hidden_size), nn.ReLU(), nn.Linear(hidden_size, 1))

    def forward(self, rows: torch.Tensor, exists: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        embedded = self.embed(rows)
        present = exists.unsqueeze(-1).to(embedded.dtype)
        # Saídas da ReLU são ≥ 0: zerar as fases inexistentes não muda o máximo.
        summary = torch.cat([(embedded * present).sum(1) / present.sum(1).clamp(min=1.0),
                             (embedded * present).max(1).values], dim=-1)
        context = summary.unsqueeze(1).expand(-1, rows.shape[1], -1)
        advantage = self.advantage(torch.cat([embedded, context], dim=-1)).squeeze(-1)
        valid = mask.to(advantage.dtype)
        mean_advantage = (advantage * valid).sum(1, keepdim=True) / valid.sum(1, keepdim=True).clamp(min=1.0)
        return self.value(summary) + advantage - mean_advantage


class PhaseSelectionAgent:
    """Agente de seleção de fase com replay, Huber loss e rede-alvo periódica."""

    def __init__(self, config: PhaseAgentConfig = PhaseAgentConfig(), device: str | None = None, seed: int = 42) -> None:
        if config.max_phases < 2 or config.row_size <= 0:
            raise ValueError("Configuração do agente de seleção de fase inválida.")
        self.config = config
        self.device = torch.device(device or "cpu")
        self._random = random.Random(seed)
        torch.manual_seed(seed)
        self.online = PhaseScoringNetwork(config.row_size, config.hidden_size).to(self.device)
        self.target = PhaseScoringNetwork(config.row_size, config.hidden_size).to(self.device)
        self.target.load_state_dict(self.online.state_dict())
        self.target.eval()
        self.optimizer = torch.optim.Adam(self.online.parameters(), lr=config.learning_rate)
        self.replay: Deque[Transition] = deque(maxlen=config.replay_capacity)
        self.demo_replay: Deque[Transition] = deque(maxlen=config.replay_capacity)
        self.training_steps = 0
        self.metadata: dict[str, Any] = {}

    def q_values(self, state: np.ndarray) -> np.ndarray:
        """Notas das fases válidas (as demais ficam em ``MASKED_Q``)."""
        rows, exists, mask = self._split(torch.as_tensor(self._validate_state(state), device=self.device).unsqueeze(0))
        with torch.no_grad():
            values = self.online(rows, exists, mask).masked_fill(~mask, MASKED_Q)
        return values.squeeze(0).cpu().numpy()

    def select_action(self, state: np.ndarray, epsilon: float, explore: bool = True) -> int:
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon deve estar entre 0 e 1.")
        state = self._validate_state(state)
        if explore and self._random.random() < epsilon:
            return self._random.choice(self._valid_actions(state))
        return int(np.argmax(self.q_values(state)))

    def remember(self, state: np.ndarray, action: int, reward: float, next_state: np.ndarray, done: bool,
                 discount: float | None = None, demo: bool = False) -> None:
        """Guarda uma transição; ``demo=True`` a põe no replay permanente de demonstrações."""
        state = self._validate_state(state)
        if action not in self._valid_actions(state):
            raise ValueError(f"Ação {action} fora da máscara do estado.")
        discount = self.config.gamma if discount is None else float(discount)
        if not 0.0 <= discount <= 1.0:
            raise ValueError("discount deve estar entre 0 e 1.")
        buffer = self.demo_replay if demo else self.replay
        buffer.append(Transition(state, int(action), float(reward), self._validate_state(next_state), bool(done), discount))

    def train_step(self) -> float | None:
        size = self.config.batch_size
        if len(self.replay) + len(self.demo_replay) < max(self.config.min_replay_size, size):
            return None
        demo_count = 0
        if self.demo_replay:
            wanted = size if not self.replay else max(1, round(size * self.config.demo_batch_fraction))
            demo_count = min(len(self.demo_replay), max(wanted, size - len(self.replay)))
        batch = self._random.sample(self.demo_replay, demo_count) + self._random.sample(self.replay, size - demo_count)
        states = torch.as_tensor(np.stack([item.state for item in batch]), device=self.device)
        next_states = torch.as_tensor(np.stack([item.next_state for item in batch]), device=self.device)
        actions = torch.as_tensor([item.action for item in batch], dtype=torch.int64, device=self.device).unsqueeze(1)
        rewards = torch.as_tensor([item.reward for item in batch], dtype=torch.float32, device=self.device)
        dones = torch.as_tensor([item.done for item in batch], dtype=torch.float32, device=self.device)
        discounts = torch.as_tensor([item.discount for item in batch], dtype=torch.float32, device=self.device)
        rows, exists, mask = self._split(states)
        all_q = self.online(rows, exists, mask)
        q_values = all_q.gather(1, actions).squeeze(1)
        with torch.no_grad():
            next_rows, next_exists, next_mask = self._split(next_states)
            target_values = self.target(next_rows, next_exists, next_mask).masked_fill(~next_mask, MASKED_Q)
            if self.config.double_dqn:
                next_actions = (self.online(next_rows, next_exists, next_mask).masked_fill(~next_mask, MASKED_Q)
                                .argmax(dim=1, keepdim=True))
                next_values = target_values.gather(1, next_actions).squeeze(1)
            else:
                next_values = target_values.max(dim=1).values
            targets = rewards + discounts * (1.0 - dones) * next_values
        loss = functional.smooth_l1_loss(q_values, targets)
        if demo_count:
            # Margem do DQfD: max_a [Q(s, a) + m·(a ≠ a_demo)] − Q(s, a_demo) nas transições demonstradas.
            demo_q = all_q[:demo_count]
            margins = torch.full_like(demo_q, self.config.demo_margin).scatter(1, actions[:demo_count], 0.0)
            best = (demo_q + margins).masked_fill(~mask[:demo_count], MASKED_Q).max(dim=1).values
            loss = loss + self.config.demo_loss_weight * (best - q_values[:demo_count]).mean()
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.online.parameters(), max_norm=1.0)
        self.optimizer.step()
        self.training_steps += 1
        if self.training_steps % self.config.target_update_interval == 0:
            self.target.load_state_dict(self.online.state_dict())
        return float(loss.item())

    def save(self, path: str | Path, metadata: Mapping[str, Any] | None = None) -> None:
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
    def load(cls, path: str | Path, device: str | None = None) -> "PhaseSelectionAgent":
        checkpoint = torch.load(Path(path), map_location=device or "cpu", weights_only=True)
        config = PhaseAgentConfig(**checkpoint["config"])
        expected = ROW_FEATURES_BY_VERSION.get(config.state_version)
        if expected is None or len(expected) != config.row_size:
            raise ValueError(f"Checkpoint de versão de estado desconhecida: {config.state_version!r}.")
        agent = cls(config, device=device)
        agent.online.load_state_dict(checkpoint["model_state"])
        agent.target.load_state_dict(checkpoint.get("target_model_state", checkpoint["model_state"]))
        if "optimizer_state" in checkpoint:
            agent.optimizer.load_state_dict(checkpoint["optimizer_state"])
        agent.training_steps = int(checkpoint.get("training_steps", 0))
        agent.metadata = dict(checkpoint.get("metadata", {}))
        agent.online.eval()
        return agent

    def _split(self, states: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Linhas ``(B, P, d)``, fases existentes (têm faixas) e máscara de fases escolhíveis."""
        phases, size = self.config.max_phases, self.config.row_size
        rows = states[:, : phases * size].reshape(-1, phases, size)
        return rows, rows[..., LANE_COUNT_INDEX] > 0.0, states[:, phases * size:] > 0.5

    def _valid_actions(self, state: np.ndarray) -> list[int]:
        mask = state[self.config.max_phases * self.config.row_size:]
        valid = [index for index, value in enumerate(mask) if value > 0.5]
        if not valid:
            raise ValueError("Estado sem nenhuma fase válida.")
        return valid

    def _validate_state(self, state: np.ndarray) -> np.ndarray:
        result = np.asarray(state, dtype=np.float32).reshape(-1)
        if result.shape != (self.config.state_size,):
            raise ValueError(f"Estado deve ter {self.config.state_size} entradas; recebeu {result.shape}.")
        return result.copy()
