"""Controlador adaptativo visual com transições seguras para o cenário SP."""

from __future__ import annotations

from typing import Any

from .phase_manager import PhaseManager
from .policies import QueueBasedPolicy


class TrafficController:
    """Alterna South e East+West usando somente estimativas de visão."""

    def __init__(self, tls_id: str, config: dict[str, Any]) -> None:
        self.tls_id = tls_id
        phase_config = config.get("traffic_light", {}).get("phases", {})
        control_config = config.get("traffic_control", {})
        self.phase_manager = PhaseManager(phase_config)
        self.policy = QueueBasedPolicy(switch_margin=int(control_config.get("switch_margin", 1)))
        self.min_green_seconds = float(control_config.get("min_green_seconds", 10.0))
        self.max_green_seconds = float(control_config.get("max_green_seconds", 40.0))
        self.yellow_seconds = float(control_config.get("yellow_seconds", 3.0))
        self.all_red_seconds = float(control_config.get("all_red_seconds", 1.0))
        if not 0 < self.min_green_seconds <= self.max_green_seconds:
            raise ValueError("As durações de verde devem satisfazer 0 < mínimo <= máximo.")
        if self.yellow_seconds <= 0 or self.all_red_seconds <= 0:
            raise ValueError("As durações de amarelo e all-red devem ser positivas.")

    def update(self, sim_time: float, visual_counts: dict[str, Any]) -> dict[str, Any]:
        """Calcula a próxima ação sem consultar E2 ou outro estado perfeito do SUMO."""
        demand = self.policy.aggregate(visual_counts)
        phase = self.phase_manager.get_current_phase()
        elapsed = self.phase_manager.elapsed(sim_time)
        next_phase, reason = self._next_phase(phase.name, elapsed, demand)
        if next_phase is None:
            return self._decision("hold", phase, sim_time, demand, reason)

        applied_phase = self.phase_manager.set_phase(next_phase, sim_time)
        return self._decision("set_phase", applied_phase, sim_time, demand, reason)

    def apply(self, sumo_client: Any, decision: dict[str, Any]) -> None:
        """Aplica uma troca de fase já decidida usando TraCI."""
        if decision["action"] == "set_phase":
            sumo_client.set_traffic_light_phase(self.tls_id, int(decision["phase_index"]))

    def _next_phase(self, name: str, elapsed: float, demand: dict[str, int]) -> tuple[str | None, str]:
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
        if name == PhaseManager.EAST_WEST_GREEN:
            return self._green_transition(elapsed, demand["east_west"], demand["south"], PhaseManager.EAST_WEST_YELLOW)
        if name == PhaseManager.SOUTH_GREEN:
            return self._green_transition(elapsed, demand["south"], demand["east_west"], PhaseManager.SOUTH_YELLOW)
        raise RuntimeError(f"Fase lógica desconhecida: {name!r}")

    def _green_transition(self, elapsed: float, current_demand: int, opposing_demand: int, yellow: str) -> tuple[str | None, str]:
        if elapsed >= self.max_green_seconds:
            return yellow, "max_green_reached"
        if elapsed < self.min_green_seconds:
            return None, "min_green_not_reached"
        should_switch, reason = self.policy.should_switch(current_demand, opposing_demand)
        return (yellow, reason) if should_switch else (None, reason)

    def _decision(self, action: str, phase: Any, sim_time: float, demand: dict[str, int], reason: str) -> dict[str, Any]:
        return {
            "tls_id": self.tls_id,
            "sim_time": float(sim_time),
            "action": action,
            "phase_name": phase.name,
            "phase_index": phase.phase_index,
            "demand": demand,
            "reason": reason,
        }
