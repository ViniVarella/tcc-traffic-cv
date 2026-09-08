"""Estados e transições seguras do semáforo do cenário SP."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PhaseState:
    """Fase SUMO e o instante simulado em que ela começou."""

    name: str
    phase_index: int
    started_at: float


class PhaseManager:
    """Controla a sequência EW verde → amarelo → all-red → South verde."""

    EAST_WEST_GREEN = "EAST_WEST_GREEN"
    EAST_WEST_YELLOW = "EAST_WEST_YELLOW"
    ALL_RED = "ALL_RED"
    SOUTH_GREEN = "SOUTH_GREEN"
    SOUTH_YELLOW = "SOUTH_YELLOW"

    def __init__(self, phases: dict[str, int], initial_time: float = 0.0) -> None:
        self._phases = phases
        self.current_phase = PhaseState(
            name=self.EAST_WEST_GREEN,
            phase_index=self._phase_index(self.EAST_WEST_GREEN),
            started_at=float(initial_time),
        )
        self.pending_green: str | None = None

    def get_current_phase(self) -> PhaseState:
        """Retorna a fase lógica atualmente ativa."""
        return self.current_phase

    def set_phase(self, name: str, sim_time: float) -> PhaseState:
        """Avança para uma fase conhecida e reinicia sua duração lógica."""
        self.current_phase = PhaseState(name=name, phase_index=self._phase_index(name), started_at=float(sim_time))
        return self.current_phase

    def elapsed(self, sim_time: float) -> float:
        """Retorna há quanto tempo a fase atual está ativa, em tempo simulado."""
        return max(0.0, float(sim_time) - self.current_phase.started_at)

    def _phase_index(self, name: str) -> int:
        mapping = {
            self.EAST_WEST_GREEN: "primary_green",
            self.EAST_WEST_YELLOW: "primary_yellow",
            self.ALL_RED: "all_red",
            self.SOUTH_GREEN: "secondary_green",
            self.SOUTH_YELLOW: "secondary_yellow",
        }
        try:
            return int(self._phases[mapping[name]])
        except KeyError as error:
            raise ValueError(f"Mapeamento de fase ausente para {name!r}.") from error
