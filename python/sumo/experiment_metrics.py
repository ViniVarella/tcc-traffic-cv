"""Métricas de desempenho agregadas para experimentos de controle semafórico."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean
from typing import Any


@dataclass
class ExperimentMetricsCollector:
    """Mede resultados do tráfego sem fornecer dados ao controlador."""

    departure_times: dict[str, float] = field(default_factory=dict)
    last_waiting_times: dict[str, float] = field(default_factory=dict)
    completed_travel_times: list[float] = field(default_factory=list)
    completed_waiting_times: list[float] = field(default_factory=list)
    queue_samples: list[int] = field(default_factory=list)
    active_vehicle_samples: list[int] = field(default_factory=list)
    started_at: float | None = None
    ended_at: float | None = None

    def observe(
        self,
        sim_time: float,
        events: dict[str, list[str]],
        active_vehicles: dict[str, dict[str, float]],
    ) -> None:
        """Registra um passo já executado do SUMO para avaliação posterior."""
        current_time = float(sim_time)
        if self.started_at is None:
            self.started_at = current_time
        self.ended_at = current_time

        for vehicle_id in events.get("departed", []):
            self.departure_times.setdefault(str(vehicle_id), current_time)

        for vehicle_id, metrics in active_vehicles.items():
            self.last_waiting_times[str(vehicle_id)] = float(metrics["accumulated_waiting_time"])

        self.active_vehicle_samples.append(len(active_vehicles))
        self.queue_samples.append(sum(float(metrics["speed"]) <= 0.1 for metrics in active_vehicles.values()))

        for vehicle_id in events.get("arrived", []):
            vehicle_id = str(vehicle_id)
            departed_at = self.departure_times.get(vehicle_id)
            if departed_at is not None:
                self.completed_travel_times.append(max(0.0, current_time - departed_at))
            self.completed_waiting_times.append(self.last_waiting_times.get(vehicle_id, 0.0))

    def summary(self) -> dict[str, float | int]:
        """Resume o experimento com métricas comparáveis entre políticas."""
        duration = 0.0 if self.started_at is None or self.ended_at is None else max(0.0, self.ended_at - self.started_at)
        departed = len(self.departure_times)
        arrived = len(self.completed_waiting_times)
        return {
            "simulation_seconds": duration,
            "departed_vehicles": departed,
            "arrived_vehicles": arrived,
            "unfinished_vehicles": max(0, departed - arrived),
            "mean_travel_time_seconds": _mean(self.completed_travel_times),
            "mean_waiting_time_seconds": _mean(self.completed_waiting_times),
            "mean_queue_length": _mean(self.queue_samples),
            "max_queue_length": max(self.queue_samples, default=0),
            "mean_active_vehicles": _mean(self.active_vehicle_samples),
            "throughput_vehicles_per_hour": 0.0 if duration == 0 else arrived * 3600.0 / duration,
        }


def _mean(values: list[float] | list[int]) -> float:
    return 0.0 if not values else float(fmean(values))
