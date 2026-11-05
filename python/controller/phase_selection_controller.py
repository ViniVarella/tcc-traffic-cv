"""Camada de segurança para a seleção livre de fase (qualquer verde → qualquer verde).

A política escolhe qual fase verde vem a seguir; escolher a fase atual é manter.
Este controlador aplica as mesmas regras do ``DqnTrafficController``: verde
mínimo e máximo, amarelo e all-red nunca pulados. O amarelo é calculado pelos
links: fica amarelo o que está verde agora e não está na fase escolhida; links
verdes nas duas fases seguem verdes durante a transição. Os estados vão ao SUMO
por ``setRedYellowGreenState`` (o programa estático não avança sozinho).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


GREEN, YELLOW, ALL_RED = "green", "yellow", "all_red"


def yellow_state(current: str, target: str) -> str:
    """Amarelo entre dois verdes: ``y`` onde o verde acaba, o resto segue igual ou vermelho."""
    _check_lengths(current, target)
    return "".join(
        c if c in "Gg" and t in "Gg" else "y" if c in "Gg" else "r"
        for c, t in zip(current, target)
    )


def all_red_state(current: str, target: str) -> str:
    """Vermelho total, exceto os links verdes nas duas fases."""
    _check_lengths(current, target)
    return "".join(c if c in "Gg" and t in "Gg" else "r" for c, t in zip(current, target))


def _check_lengths(current: str, target: str) -> None:
    if len(current) != len(target):
        raise ValueError("Os estados das fases têm tamanhos diferentes.")


class PhaseSelectionController:
    """Executa a fase verde escolhida pela política, sem manobras inseguras."""

    def __init__(
        self,
        tls_id: str,
        green_states: Sequence[str],
        min_green_s: float = 10.0,
        max_green_s: float = 40.0,
        yellow_s: float = 3.0,
        all_red_s: float = 1.0,
        initial_time: float = 0.0,
    ) -> None:
        if len(green_states) < 2:
            raise ValueError("São necessárias pelo menos duas fases verdes.")
        if not 0 <= min_green_s < max_green_s or yellow_s <= 0 or all_red_s < 0:
            raise ValueError("Tempos de segurança inválidos.")
        self.tls_id = tls_id
        self.green_states = tuple(green_states)
        self.min_green_s = float(min_green_s)
        self.max_green_s = float(max_green_s)
        self.yellow_s = float(yellow_s)
        self.all_red_s = float(all_red_s)
        self.mode = GREEN
        self.current = 0
        self.target: int | None = None
        self.started_at = float(initial_time)
        # Instante em que cada fase deixou o verde (a atual não está no vermelho).
        self.red_since = [float(initial_time)] * len(self.green_states)
        self.state = self.green_states[0]
        self.pending_apply = True

    @property
    def phase_count(self) -> int:
        return len(self.green_states)

    @property
    def is_green(self) -> bool:
        return self.mode == GREEN

    @property
    def phase_name(self) -> str:
        return f"green_{self.current}" if self.mode == GREEN else self.mode

    def elapsed(self, sim_time: float) -> float:
        return max(0.0, float(sim_time) - self.started_at)

    def red_time(self, phase: int, sim_time: float) -> float:
        """Há quanto tempo a fase está fora do verde (0 para a fase verde atual)."""
        if self.mode == GREEN and phase == self.current:
            return 0.0
        return max(0.0, float(sim_time) - self.red_since[phase])

    def next_cyclic(self, phase: int | None = None) -> int:
        return ((self.current if phase is None else phase) + 1) % self.phase_count

    def update(self, sim_time: float, choice: int | None) -> dict[str, Any]:
        """Avança o semáforo; ``choice`` é a fase verde pedida (``None`` = sem decisão)."""
        if choice is not None and not 0 <= choice < self.phase_count:
            raise ValueError(f"Fase inválida: {choice}.")
        elapsed = self.elapsed(sim_time)
        if self.mode == YELLOW:
            if elapsed < self.yellow_s:
                return self._decision("hold", sim_time, choice, "yellow_in_progress")
            if self.all_red_s > 0:
                return self._set(ALL_RED, all_red_state(self.green_states[self.current], self.green_states[self.target]),
                                 sim_time, choice, "yellow_complete")
            return self._enter_green(sim_time, choice, "yellow_complete")
        if self.mode == ALL_RED:
            if elapsed < self.all_red_s:
                return self._decision("hold", sim_time, choice, "all_red_in_progress")
            return self._enter_green(sim_time, choice, "all_red_complete")
        if elapsed >= self.max_green_s:
            target = self.next_cyclic() if choice is None or choice == self.current else choice
            return self._leave_green(target, sim_time, choice, "max_green_reached")
        if elapsed < self.min_green_s:
            return self._decision("hold", sim_time, choice, "min_green_not_reached")
        if choice is None:
            return self._decision("hold", sim_time, choice, "no_decision")
        if choice == self.current:
            return self._decision("hold", sim_time, choice, "policy_keep")
        return self._leave_green(choice, sim_time, choice, "policy_select")

    def apply(self, sumo_client: Any, decision: dict[str, Any]) -> None:
        if decision["action"] == "set_state" or self.pending_apply:
            sumo_client.set_traffic_light_state(self.tls_id, self.state)
            self.pending_apply = False

    def _leave_green(self, target: int, sim_time: float, choice: int | None, reason: str) -> dict[str, Any]:
        self.target = target
        self.red_since[self.current] = float(sim_time)
        yellow = yellow_state(self.green_states[self.current], self.green_states[target])
        if "y" not in yellow:
            # A fase escolhida só acrescenta verdes: não há o que encerrar.
            return self._enter_green(sim_time, choice, reason)
        return self._set(YELLOW, yellow, sim_time, choice, reason)

    def _enter_green(self, sim_time: float, choice: int | None, reason: str) -> dict[str, Any]:
        self.current, self.target = self.target, None
        return self._set(GREEN, self.green_states[self.current], sim_time, choice, reason)

    def _set(self, mode: str, state: str, sim_time: float, choice: int | None, reason: str) -> dict[str, Any]:
        self.mode, self.state, self.started_at = mode, state, float(sim_time)
        return self._decision("set_state", sim_time, choice, reason)

    def _decision(self, action: str, sim_time: float, choice: int | None, reason: str) -> dict[str, Any]:
        return {"tls_id": self.tls_id, "sim_time": float(sim_time), "action": action, "phase_name": self.phase_name,
                "state": self.state, "requested_phase": choice, "reason": reason}
