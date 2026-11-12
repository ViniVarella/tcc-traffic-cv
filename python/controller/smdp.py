"""Transições SMDP entre pontos de decisão, usadas pelas duas linhas de DQN.

A recompensa de cada step entre duas decisões é acumulada com desconto, e a
transição guarda ``gamma ** k`` para o alvo do DQN.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SmdpTransition:
    """Transição entre duas decisões: recompensa descontada acumulada e ``discount = gamma ** steps``."""

    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    discount: float
    steps: int


class SmdpAccumulator:
    """Acumula ``sum(gamma**i * r_i)`` desde a última decisão até a próxima."""

    def __init__(self, gamma: float) -> None:
        if not 0.0 < gamma <= 1.0:
            raise ValueError("gamma deve estar em (0, 1].")
        self.gamma = float(gamma)
        self.reset()

    def reset(self) -> None:
        self._state: np.ndarray | None = None
        self._action = 0
        self._reward = 0.0
        self._steps = 0

    @property
    def is_open(self) -> bool:
        return self._state is not None

    def open(self, state: np.ndarray, action: int) -> None:
        self._state, self._action, self._reward, self._steps = np.asarray(state, dtype=np.float32).copy(), int(action), 0.0, 0

    def add(self, reward: float) -> None:
        """Soma a recompensa de um step já simulado após a decisão aberta."""
        if self._state is None:
            return
        self._reward += (self.gamma ** self._steps) * float(reward)
        self._steps += 1

    def close(self, next_state: np.ndarray) -> SmdpTransition | None:
        """Fecha a transição aberta; ``None`` se não houve decisão ou step algum."""
        if self._state is None or self._steps == 0:
            self.reset()
            return None
        transition = SmdpTransition(self._state, self._action, self._reward, np.asarray(next_state, dtype=np.float32).copy(),
                                    self.gamma ** self._steps, self._steps)
        self.reset()
        return transition
