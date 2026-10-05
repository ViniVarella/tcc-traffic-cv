"""Métricas de pedestres nos cenários com faixas de pedestre."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from statistics import fmean


# Mesmo limiar de parada da espera dos veículos no SUMO.
PEDESTRIAN_WAITING_SPEED_MPS = 0.1


@dataclass
class PedestrianMetricsCollector:
    """Acumula a espera de cada pedestre (steps parado) até ele sair da simulação.

    Como os veículos, só contam os pedestres que partiram depois de
    ``warmup_until_s``. Recebe só velocidades; não fornece nada ao controlador.
    """

    warmup_until_s: float = 0.0
    step_length_s: float = 1.0
    first_seen: dict[str, float] = field(default_factory=dict)
    waiting: dict[str, float] = field(default_factory=dict)
    completed_waiting: list[float] = field(default_factory=list)
    completed_trip: list[float] = field(default_factory=list)
    last_time: float | None = None

    def observe(self, sim_time: float, speeds: Mapping[str, float]) -> None:
        for person_id, speed in speeds.items():
            self.first_seen.setdefault(person_id, float(sim_time))
            if float(speed) < PEDESTRIAN_WAITING_SPEED_MPS:
                self.waiting[person_id] = self.waiting.get(person_id, 0.0) + self.step_length_s
        for person_id in [person for person in self.first_seen if person not in speeds]:
            started = self.first_seen.pop(person_id)
            waited = self.waiting.pop(person_id, 0.0)
            if started > self.warmup_until_s:
                self.completed_waiting.append(waited)
                self.completed_trip.append(float(sim_time) - started)
        self.last_time = float(sim_time)

    def summary(self) -> dict[str, float | int | None]:
        waiting = sorted(self.completed_waiting)
        return {
            "pedestrians_arrived": len(waiting),
            "pedestrian_mean_waiting_s": None if not waiting else float(fmean(waiting)),
            "pedestrian_p95_waiting_s": None if not waiting else float(waiting[min(len(waiting) - 1, int(0.95 * len(waiting)))]),
            "pedestrian_max_waiting_s": None if not waiting else float(waiting[-1]),
            "pedestrian_mean_trip_s": None if not self.completed_trip else float(fmean(self.completed_trip)),
            "pedestrians_active_at_end": len(self.first_seen),
        }
