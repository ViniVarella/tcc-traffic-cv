"""Estados e transições seguras do semáforo do cenário SP."""

from __future__ import annotations

from dataclasses import dataclass


# Duração aplicada via TraCI após cada ``setPhase``. O controlador Python decide
# todas as transições; sem isso o programa estático da rede avançaria sozinho
# (por exemplo, do amarelo South direto para o verde E/W, sem all-red).
SUMO_PHASE_HOLD_SECONDS = 100_000.0


@dataclass(frozen=True, slots=True)
class PhaseState:
    """Fase SUMO e o instante simulado em que ela começou."""

    name: str
    phase_index: int
    started_at: float


class PhaseManager:
    """Controla a sequência EW verde → amarelo → all-red → South verde.

    Na rede com pedestres há também o verde exclusivo de pedestres e o vermelho
    total de liberação que o segue (``DqnTrafficController`` decide quando).
    """

    EAST_WEST_GREEN = "EAST_WEST_GREEN"
    EAST_WEST_YELLOW = "EAST_WEST_YELLOW"
    ALL_RED = "ALL_RED"
    SOUTH_GREEN = "SOUTH_GREEN"
    SOUTH_YELLOW = "SOUTH_YELLOW"
    PEDESTRIAN_GREEN = "PEDESTRIAN_GREEN"
    PEDESTRIAN_CLEARANCE = "PEDESTRIAN_CLEARANCE"

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

    def has_phase(self, name: str) -> bool:
        """Indica se o perfil mapeia a fase (as de pedestres só existem na rede com pedestres)."""
        try:
            self._phase_index(name)
        except ValueError:
            return False
        return True

    def _phase_index(self, name: str) -> int:
        mapping = {
            self.EAST_WEST_GREEN: "primary_green",
            self.EAST_WEST_YELLOW: "primary_yellow",
            self.ALL_RED: "all_red",
            self.SOUTH_GREEN: "secondary_green",
            self.SOUTH_YELLOW: "secondary_yellow",
            self.PEDESTRIAN_GREEN: "pedestrian_green",
            self.PEDESTRIAN_CLEARANCE: "pedestrian_clearance",
        }
        try:
            return int(self._phases[mapping[name]])
        except KeyError as error:
            raise ValueError(f"Mapeamento de fase ausente para {name!r}.") from error
