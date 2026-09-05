"""Aplicação segura das ações discretas escolhidas pelo DQN."""

from __future__ import annotations

from typing import Any

from .phase_manager import PhaseManager


class DqnTrafficController:
    """Traduz manter/trocar em fases SUMO, sem permitir manobras inseguras."""

    KEEP = 0
    SWITCH = 1

    def __init__(self, tls_id: str, config: dict[str, Any]) -> None:
        control = config.get("traffic_control", {})
        self.tls_id = tls_id
        self.phase_manager = PhaseManager(config.get("traffic_light", {}).get("phases", {}))
        self.min_green_seconds = float(control.get("min_green_seconds", 10.0))
        self.max_green_seconds = float(control.get("max_green_seconds", 40.0))
        self.yellow_seconds = float(control.get("yellow_seconds", 3.0))
        self.all_red_seconds = float(control.get("all_red_seconds", 1.0))

    def update(self, sim_time: float, action: int) -> dict[str, Any]:
        if action not in {self.KEEP, self.SWITCH}:
            raise ValueError(f"Ação DQN inválida: {action}.")
        phase = self.phase_manager.get_current_phase()
        elapsed = self.phase_manager.elapsed(sim_time)
        next_phase, reason = self._next_phase(phase.name, elapsed, action)
        if next_phase is None:
            return self._decision("hold", phase, sim_time, action, reason)
        applied = self.phase_manager.set_phase(next_phase, sim_time)
        return self._decision("set_phase", applied, sim_time, action, reason)

    def apply(self, sumo_client: Any, decision: dict[str, Any]) -> None:
        if decision["action"] == "set_phase":
            sumo_client.set_traffic_light_phase(self.tls_id, int(decision["phase_index"]))

    def _next_phase(self, name: str, elapsed: float, action: int) -> tuple[str | None, str]:
        if name == PhaseManager.EAST_WEST_YELLOW:
            if elapsed < self.yellow_seconds:
                return None, "east_west_yellow_in_progress"
            self.phase_manager.pending_green = PhaseManager.SOUTH_GREEN
            return PhaseManager.ALL_RED, "east_west_yellow_complete"
        if name == PhaseManager.SOUTH_YELLOW:
            if elapsed < self.yellow_seconds:
                return None, "south_yellow_in_progress"
            self.phase_manager.pending_green = PhaseManager.EAST_WEST_GREEN
            return PhaseManager.ALL_RED, "south_yellow_complete"
        if name == PhaseManager.ALL_RED:
            if elapsed < self.all_red_seconds:
                return None, "all_red_in_progress"
            next_green = self.phase_manager.pending_green
            if next_green is None:
                raise RuntimeError("All-red sem uma fase verde pendente.")
            self.phase_manager.pending_green = None
            return next_green, "all_red_complete"
        if name in {PhaseManager.EAST_WEST_GREEN, PhaseManager.SOUTH_GREEN}:
            yellow = PhaseManager.EAST_WEST_YELLOW if name == PhaseManager.EAST_WEST_GREEN else PhaseManager.SOUTH_YELLOW
            if elapsed >= self.max_green_seconds:
                return yellow, "max_green_reached"
            if elapsed < self.min_green_seconds:
                return None, "min_green_not_reached"
            return (yellow, "dqn_switch") if action == self.SWITCH else (None, "dqn_keep")
        raise RuntimeError(f"Fase lógica desconhecida: {name!r}")

    def _decision(self, action: str, phase: Any, sim_time: float, requested_action: int, reason: str) -> dict[str, Any]:
        return {"tls_id": self.tls_id, "sim_time": float(sim_time), "action": action, "phase_name": phase.name, "phase_index": phase.phase_index, "requested_action": requested_action, "reason": reason}
