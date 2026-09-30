"""Métricas de desempenho agregadas para experimentos de controle semafórico."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import fmean
from typing import Any


@dataclass
class ExperimentMetricsCollector:
    """Mede resultados do tráfego sem fornecer dados ao controlador.

    Com ``warmup_until_s``, amostras, chegadas e duração só contam nos steps
    com tempo maior que ele, e tempos de viagem/espera só de veículos que
    partiram depois dele. A fila de inserção (veículos gerados que ainda não entraram na rede)
    é registrada quando informada, pois sua espera não aparece nas outras métricas.
    """

    warmup_until_s: float = 0.0
    departure_times: dict[str, float] = field(default_factory=dict)
    last_waiting_times: dict[str, float] = field(default_factory=dict)
    completed_travel_times: list[float] = field(default_factory=list)
    completed_waiting_times: list[float] = field(default_factory=list)
    queue_samples: list[int] = field(default_factory=list)
    active_vehicle_samples: list[int] = field(default_factory=list)
    pending_samples: list[int] = field(default_factory=list)
    teleported_vehicles: int = 0
    arrivals_after_warmup: int = 0
    started_at: float | None = None
    ended_at: float | None = None

    def observe(
        self,
        sim_time: float,
        events: dict[str, list[str]],
        active_vehicles: dict[str, dict[str, float]],
        pending_vehicles: int | None = None,
        teleports: int = 0,
    ) -> None:
        """Registra um passo já executado do SUMO para avaliação posterior."""
        current_time = float(sim_time)
        measuring = current_time > self.warmup_until_s
        for vehicle_id in events.get("departed", []):
            self.departure_times.setdefault(str(vehicle_id), current_time)
        for vehicle_id, metrics in active_vehicles.items():
            self.last_waiting_times[str(vehicle_id)] = float(metrics["accumulated_waiting_time"])
        if not measuring:
            for vehicle_id in events.get("arrived", []):
                self.last_waiting_times.pop(str(vehicle_id), None)
            return

        if self.started_at is None:
            self.started_at = current_time
        self.ended_at = current_time
        self.active_vehicle_samples.append(len(active_vehicles))
        self.queue_samples.append(sum(float(metrics["speed"]) <= 0.1 for metrics in active_vehicles.values()))
        if pending_vehicles is not None:
            self.pending_samples.append(int(pending_vehicles))
        self.teleported_vehicles += int(teleports)

        for vehicle_id in events.get("arrived", []):
            vehicle_id = str(vehicle_id)
            self.arrivals_after_warmup += 1
            departed_at = self.departure_times.get(vehicle_id)
            if departed_at is None or departed_at <= self.warmup_until_s:
                continue
            self.completed_travel_times.append(max(0.0, current_time - departed_at))
            self.completed_waiting_times.append(self.last_waiting_times.pop(vehicle_id, 0.0))

    def summary(self) -> dict[str, float | int]:
        """Resume o experimento com métricas comparáveis entre políticas."""
        duration = 0.0 if self.started_at is None or self.ended_at is None else max(0.0, self.ended_at - self.started_at)
        departed = sum(time > self.warmup_until_s for time in self.departure_times.values())
        completed = len(self.completed_waiting_times)
        arrived = self.arrivals_after_warmup
        summary: dict[str, float | int] = {
            "simulation_seconds": duration,
            "departed_vehicles": departed,
            "arrived_vehicles": arrived,
            "unfinished_vehicles": max(0, departed - completed),
            "mean_travel_time_seconds": _mean(self.completed_travel_times),
            "mean_waiting_time_seconds": _mean(self.completed_waiting_times),
            "mean_queue_length": _mean(self.queue_samples),
            "max_queue_length": max(self.queue_samples, default=0),
            "mean_active_vehicles": _mean(self.active_vehicle_samples),
            "throughput_vehicles_per_hour": 0.0 if duration == 0 else arrived * 3600.0 / duration,
        }
        if self.warmup_until_s > 0:
            summary["warmup_seconds"] = self.warmup_until_s
        if self.pending_samples:
            summary["mean_pending_vehicles"] = _mean(self.pending_samples)
            summary["max_pending_vehicles"] = max(self.pending_samples)
            summary["final_pending_vehicles"] = self.pending_samples[-1]
            summary["teleported_vehicles"] = self.teleported_vehicles
        return summary


def _mean(values: list[float] | list[int]) -> float:
    return 0.0 if not values else float(fmean(values))
