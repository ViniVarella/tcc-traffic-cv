"""Aplicação segura das ações discretas escolhidas pelo DQN."""

from __future__ import annotations

from typing import Any

from .phase_manager import SUMO_PHASE_HOLD_SECONDS, PhaseManager


class DqnTrafficController:
    """Traduz manter/trocar em fases SUMO, sem permitir manobras inseguras."""

    KEEP = 0
    SWITCH = 1

    def __init__(self, tls_id: str, config: dict[str, Any], pedestrian_phase: bool = False) -> None:
        """``pedestrian_phase`` liga a fase exclusiva de pedestres (rede com faixas de pedestre).

        Ela entra depois de cada ``pedestrians.every_cycles``-ésimo verde Sul:
        all-red → verde de pedestres → liberação (vermelho total) → verde L/O. É
        obrigatória como o amarelo: a política não a encerra nem a pula, e a
        preempção espera o fim dela.
        """
        control = config.get("traffic_control", {})
        self.tls_id = tls_id
        self.phase_manager = PhaseManager(config.get("traffic_light", {}).get("phases", {}))
        self.min_green_seconds = float(control.get("min_green_seconds", 10.0))
        self.max_green_seconds = float(control.get("max_green_seconds", 40.0))
        self.yellow_seconds = float(control.get("yellow_seconds", 3.0))
        self.all_red_seconds = float(control.get("all_red_seconds", 1.0))
        self.pedestrian_phase = bool(pedestrian_phase)
        pedestrians = config.get("pedestrians", {})
        self.pedestrian_every_cycles = int(pedestrians.get("every_cycles", 2))
        self.pedestrian_green_seconds = float(pedestrians.get("green_seconds", 0.0))
        self.pedestrian_clearance_seconds = float(pedestrians.get("clearance_seconds", 0.0))
        if self.pedestrian_phase and not (
            self.phase_manager.has_phase(PhaseManager.PEDESTRIAN_GREEN)
            and self.phase_manager.has_phase(PhaseManager.PEDESTRIAN_CLEARANCE)
            and self.pedestrian_every_cycles >= 1 and self.pedestrian_green_seconds > 0
        ):
            raise ValueError("A fase de pedestres exige traffic_light.phases.pedestrian_* e o bloco pedestrians do perfil.")
        # Verdes Sul concluídos desde a última fase de pedestres.
        self.south_greens_since_pedestrian = 0
        self.history: list[str] = []

    def greens_until_pedestrian(self) -> int | None:
        """Verdes de veículos que ainda vêm antes da fase de pedestres, sem contar o atual.

        Fora de um verde, vale para o próximo verde. ``None`` sem a fase de pedestres.
        """
        if not self.pedestrian_phase:
            return None
        every, done = self.pedestrian_every_cycles, self.south_greens_since_pedestrian
        name = self.phase_manager.get_current_phase().name
        upcoming = self.phase_manager.pending_green if name == PhaseManager.ALL_RED else None
        if name in {PhaseManager.SOUTH_GREEN, PhaseManager.EAST_WEST_YELLOW} or upcoming == PhaseManager.SOUTH_GREEN:
            return max(0, 2 * (every - done - 1))
        pedestrian_next = name == PhaseManager.SOUTH_YELLOW and done >= every
        if pedestrian_next or upcoming == PhaseManager.PEDESTRIAN_GREEN or name in {PhaseManager.PEDESTRIAN_GREEN, PhaseManager.PEDESTRIAN_CLEARANCE}:
            return 2 * every - 1
        return max(0, 2 * (every - done) - 1)

    def update(self, sim_time: float, action: int) -> dict[str, Any]:
        if action not in {self.KEEP, self.SWITCH}:
            raise ValueError(f"Ação DQN inválida: {action}.")
        return self._update(sim_time, action)

    def update_without_vision(self, sim_time: float) -> dict[str, Any]:
        """Avança só as transições obrigatórias quando não há frames para decidir."""
        return self._update(sim_time, None)

    def update_preemption(self, sim_time: float, target_green: str) -> dict[str, Any]:
        """Leva o semáforo ao verde de um veículo de emergência e o mantém lá.

        No verde-alvo, mantém mesmo além do verde máximo; no outro verde, inicia
        o amarelo sem esperar o verde mínimo. Amarelo e all-red nunca são
        pulados; ao fim do all-red segue direto para o verde-alvo.
        """
        if target_green not in {PhaseManager.EAST_WEST_GREEN, PhaseManager.SOUTH_GREEN}:
            raise ValueError(f"Verde de preempção inválido: {target_green!r}.")
        return self._update(sim_time, None, preempt_target=target_green)

    def _update(self, sim_time: float, action: int | None, preempt_target: str | None = None) -> dict[str, Any]:
        phase = self.phase_manager.get_current_phase()
        elapsed = self.phase_manager.elapsed(sim_time)
        next_phase, reason = self._next_phase(phase.name, elapsed, action, preempt_target)
        if next_phase is None:
            return self._decision("hold", phase, sim_time, action, reason)
        applied = self.phase_manager.set_phase(next_phase, sim_time)
        self.history.append(next_phase)
        return self._decision("set_phase", applied, sim_time, action, reason)

    def apply(self, sumo_client: Any, decision: dict[str, Any]) -> None:
        if decision["action"] == "set_phase":
            sumo_client.set_traffic_light_phase(self.tls_id, int(decision["phase_index"]))
            sumo_client.set_traffic_light_phase_duration(self.tls_id, SUMO_PHASE_HOLD_SECONDS)

    def _next_phase(self, name: str, elapsed: float, action: int | None, preempt_target: str | None = None) -> tuple[str | None, str]:
        if name == PhaseManager.EAST_WEST_YELLOW:
            if elapsed < self.yellow_seconds:
                return None, "east_west_yellow_in_progress"
            self.phase_manager.pending_green = PhaseManager.SOUTH_GREEN
            return PhaseManager.ALL_RED, "east_west_yellow_complete"
        if name == PhaseManager.SOUTH_YELLOW:
            if elapsed < self.yellow_seconds:
                return None, "south_yellow_in_progress"
            due = self.pedestrian_phase and self.south_greens_since_pedestrian >= self.pedestrian_every_cycles
            self.phase_manager.pending_green = PhaseManager.PEDESTRIAN_GREEN if due else PhaseManager.EAST_WEST_GREEN
            return PhaseManager.ALL_RED, "south_yellow_complete"
        if name == PhaseManager.PEDESTRIAN_GREEN:
            if elapsed < self.pedestrian_green_seconds:
                return None, "pedestrian_green_in_progress"
            self.south_greens_since_pedestrian = 0
            return PhaseManager.PEDESTRIAN_CLEARANCE, "pedestrian_green_complete"
        if name == PhaseManager.PEDESTRIAN_CLEARANCE:
            if elapsed < self.pedestrian_clearance_seconds:
                return None, "pedestrian_clearance_in_progress"
            return preempt_target or PhaseManager.EAST_WEST_GREEN, "pedestrian_clearance_complete"
        if name == PhaseManager.ALL_RED:
            if elapsed < self.all_red_seconds:
                return None, "all_red_in_progress"
            if preempt_target is not None:
                # A viatura passa à frente de uma fase de pedestres ainda não iniciada;
                # o contador não zera, então ela vem na próxima oportunidade.
                self.phase_manager.pending_green = preempt_target
            next_green = self.phase_manager.pending_green
            if next_green is None:
                raise RuntimeError("All-red sem uma fase verde pendente.")
            self.phase_manager.pending_green = None
            return next_green, "all_red_complete"
        if name in {PhaseManager.EAST_WEST_GREEN, PhaseManager.SOUTH_GREEN}:
            yellow = PhaseManager.EAST_WEST_YELLOW if name == PhaseManager.EAST_WEST_GREEN else PhaseManager.SOUTH_YELLOW
            if preempt_target is not None:
                return (None, "preemption_hold") if name == preempt_target else self._end_green(name, yellow, "preemption_switch")
            if elapsed >= self.max_green_seconds:
                return self._end_green(name, yellow, "max_green_reached")
            if elapsed < self.min_green_seconds:
                return None, "min_green_not_reached"
            if action is None:
                return None, "vision_unavailable"
            return self._end_green(name, yellow, "dqn_switch") if action == self.SWITCH else (None, "dqn_keep")
        raise RuntimeError(f"Fase lógica desconhecida: {name!r}")

    def _end_green(self, name: str, yellow: str, reason: str) -> tuple[str, str]:
        if name == PhaseManager.SOUTH_GREEN:
            self.south_greens_since_pedestrian += 1
        return yellow, reason

    def _decision(self, action: str, phase: Any, sim_time: float, requested_action: int | None, reason: str) -> dict[str, Any]:
        return {"tls_id": self.tls_id, "sim_time": float(sim_time), "action": action, "phase_name": phase.name, "phase_index": phase.phase_index, "requested_action": requested_action, "reason": reason}
