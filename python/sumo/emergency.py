"""Veículos de emergência no SUMO: agenda, aviso V2I e métricas por viatura.

As viaturas são inseridas por TraCI numa agenda reproduzível pela seed, sem
mudar os arquivos de rota, e obedecem ao semáforo (sem o dispositivo
``bluelight`` do SUMO, que as deixaria furar o vermelho). O aviso V2I emula o
despacho por GPS: a viatura é anunciada ``announce_before_s`` antes de entrar
na rede e reporta posição até cruzar a linha de retenção.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import random
from statistics import fmean
from typing import Any, Protocol

from controller.preemption import EmergencyRequest


EMERGENCY_TYPE = "emergency"


class EmergencyClient(Protocol):
    def ensure_vehicle_type(self, type_id: str, vehicle_class: str, speed_factor: float, color: tuple[int, int, int]) -> None: ...
    def add_vehicle(self, vehicle_id: str, from_edge: str, to_edge: str, type_id: str) -> None: ...
    def get_vehicle_road_state(self, vehicle_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class EmergencySettings:
    interval_s: float = 300.0
    jitter_s: float = 60.0
    first_after_s: float = 30.0
    announce_before_s: float = 15.0
    speed_factor: float = 1.0
    free_speed_mps: float = 13.89
    routes: Mapping[str, tuple[tuple[str, str], ...]] = field(default_factory=lambda: {
        "south": (("E3", "E1"), ("E3", "E0"), ("E3", "E5")),
        "east": (("E2", "E0"), ("E2", "E5")),
        "west": (("E6", "E1"),),
    })

    def __post_init__(self) -> None:
        if self.interval_s <= 0 or not 0 <= self.jitter_s < self.interval_s or self.announce_before_s < 0:
            raise ValueError("Agenda de emergência inválida (intervalo > jitter ≥ 0 e aviso ≥ 0).")

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "EmergencySettings":
        raw = {key: value for key, value in dict(config.get("emergency", {})).items() if key not in ("preemption", "visual_detection")}
        if "routes" in raw:
            raw["routes"] = {approach: tuple(tuple(pair) for pair in pairs) for approach, pairs in raw["routes"].items()}
        return cls(**raw)


@dataclass(frozen=True, slots=True)
class ScheduledEmergency:
    vehicle_id: str
    depart_s: float
    approach: str
    from_edge: str
    to_edge: str


def build_schedule(settings: EmergencySettings, seed: int, start_s: float, end_s: float) -> list[ScheduledEmergency]:
    """Uma viatura a cada ~``interval_s``, alternando aproximações de forma embaralhada."""
    rng = random.Random(f"emergency-{seed}")
    approaches = sorted(settings.routes)
    schedule: list[ScheduledEmergency] = []
    time = start_s + settings.first_after_s
    order: list[str] = []
    while time < end_s:
        if not order:
            order = approaches[:]
            rng.shuffle(order)
        approach = order.pop()
        from_edge, to_edge = rng.choice(settings.routes[approach])
        depart = time + rng.uniform(-settings.jitter_s / 2, settings.jitter_s / 2)
        schedule.append(ScheduledEmergency(f"emergency_{len(schedule)}", max(start_s, depart), approach, from_edge, to_edge))
        time += settings.interval_s
    return schedule


@dataclass(slots=True)
class _Tracked:
    plan: ScheduledEmergency
    inserted: bool = False
    inserted_s: float | None = None
    entered_s: float | None = None
    seen: bool = False
    arrived_s: float | None = None
    passed_stop_line_s: float | None = None
    stops: int = 0
    stopped: bool = False
    time_loss: float = 0.0
    waiting: float = 0.0
    approach_time_loss: float = 0.0
    approach_stops: int = 0
    on_approach: bool = False
    first_visual_s: float | None = None


class EmergencyTraffic:
    """Insere as viaturas agendadas e produz os avisos V2I de cada step."""

    def __init__(self, settings: EmergencySettings, approach_edges: Mapping[str, str], seed: int, start_s: float, end_s: float) -> None:
        self.settings = settings
        self.approach_edges = dict(approach_edges)
        self._vehicles = [_Tracked(plan) for plan in build_schedule(settings, seed, start_s, end_s)]
        self._type_ready = False
        self._visual_events: dict[str, bool] = {}

    def step(self, client: EmergencyClient, sim_time: float) -> list[EmergencyRequest]:
        if not self._type_ready:
            client.ensure_vehicle_type(EMERGENCY_TYPE, "emergency", self.settings.speed_factor, (220, 20, 20))
            self._type_ready = True
        requests: list[EmergencyRequest] = []
        for vehicle in self._vehicles:
            plan = vehicle.plan
            if vehicle.arrived_s is not None:
                continue
            if not vehicle.inserted:
                if sim_time >= plan.depart_s:
                    client.add_vehicle(plan.vehicle_id, plan.from_edge, plan.to_edge, EMERGENCY_TYPE)
                    vehicle.inserted = True
                    vehicle.inserted_s = sim_time
                elif sim_time >= plan.depart_s - self.settings.announce_before_s:
                    # Anunciada pelo despacho, ainda antes de entrar na rede.
                    requests.append(EmergencyRequest(plan.vehicle_id, plan.approach, plan.depart_s - sim_time + self._full_approach_s()))
                continue
            state = client.get_vehicle_road_state(plan.vehicle_id)
            if state is None:
                vehicle.on_approach = False
                if vehicle.seen:
                    vehicle.arrived_s = sim_time
                else:
                    # Inserção adiada (entrada bloqueada pela fila): continua pedindo passagem.
                    requests.append(EmergencyRequest(plan.vehicle_id, plan.approach, self._full_approach_s()))
                continue
            if not vehicle.seen:
                vehicle.entered_s = sim_time
            vehicle.seen = True
            self._observe(vehicle, state, sim_time)
            vehicle.on_approach = state["road_id"] == self.approach_edges[plan.approach]
            if vehicle.on_approach:
                remaining = max(0.0, float(state["lane_length"]) - float(state["lane_position"]))
                speed = max(float(state["speed"]), self.settings.free_speed_mps / 2)
                requests.append(EmergencyRequest(plan.vehicle_id, plan.approach, remaining / speed))
            elif vehicle.passed_stop_line_s is None:
                vehicle.passed_stop_line_s = sim_time
                vehicle.approach_time_loss = vehicle.time_loss
                vehicle.approach_stops = vehicle.stops
        return requests

    def present_on(self, approach: str) -> bool:
        """Há viatura na edge de entrada desta aproximação, antes da linha de retenção?"""
        return any(vehicle.on_approach and vehicle.plan.approach == approach for vehicle in self._vehicles)

    def note_visual(self, requests: list[EmergencyRequest], sim_time: float) -> None:
        """Registra os pedidos visuais do step para medir antecedência e alarmes falsos.

        Chame depois de ``step`` no mesmo step. Um evento visual é verdadeiro se,
        quando aparece, há viatura na aproximação; a primeira detecção de cada
        viatura é o primeiro step com pedido visual na aproximação dela.
        """
        for request in requests:
            if request.vehicle_id not in self._visual_events:
                self._visual_events[request.vehicle_id] = self.present_on(request.approach)
            for vehicle in self._vehicles:
                if vehicle.on_approach and vehicle.plan.approach == request.approach and vehicle.first_visual_s is None:
                    vehicle.first_visual_s = sim_time

    @staticmethod
    def _insertion_delay(vehicle: _Tracked) -> float:
        if vehicle.entered_s is None or vehicle.inserted_s is None:
            return 0.0
        return vehicle.entered_s - vehicle.inserted_s

    def _full_approach_s(self) -> float:
        return 75.0 / self.settings.free_speed_mps

    @staticmethod
    def _observe(vehicle: _Tracked, state: Mapping[str, Any], sim_time: float) -> None:
        stopped = float(state["speed"]) < 0.1
        if stopped and not vehicle.stopped:
            vehicle.stops += 1
        vehicle.stopped = stopped
        vehicle.time_loss = float(state["time_loss"])
        vehicle.waiting = float(state["waiting_time"])

    def summary(self) -> dict[str, Any]:
        done = [vehicle for vehicle in self._vehicles if vehicle.passed_stop_line_s is not None]
        mean = lambda values: None if not values else float(fmean(values))
        total = [self._insertion_delay(vehicle) + vehicle.approach_time_loss for vehicle in done]
        return {
            "scheduled": len(self._vehicles),
            "crossed_stop_line": len(done),
            # Perda de tempo até cruzar a linha de retenção: o atraso causado pelo semáforo.
            "mean_time_loss_at_crossing_s": mean([vehicle.approach_time_loss for vehicle in done]),
            "max_time_loss_at_crossing_s": max((vehicle.approach_time_loss for vehicle in done), default=None),
            # Espera fora da rede: com a entrada bloqueada pela fila, o SUMO adia a
            # inserção e a perda acima não a vê. Inclui a latência de 1 step da inserção.
            "mean_insertion_delay_s": mean([self._insertion_delay(vehicle) for vehicle in done]),
            "mean_total_loss_at_crossing_s": mean(total),
            "max_total_loss_at_crossing_s": max(total, default=None),
            "mean_stops": mean([vehicle.approach_stops for vehicle in done]),
            "share_without_stops": mean([float(vehicle.approach_stops == 0) for vehicle in done]),
            "mean_waiting_s": mean([vehicle.waiting for vehicle in done]),
            # Antecedência do aviso até a viatura cruzar a linha: V2I (anúncio do
            # despacho) e visão (primeira detecção confirmada na ROI).
            "mean_v2i_lead_s": mean([vehicle.passed_stop_line_s - (vehicle.plan.depart_s - self.settings.announce_before_s)
                                     for vehicle in done]),
            "visual_detection": {
                "detected": sum(vehicle.first_visual_s is not None for vehicle in done),
                "share_detected": mean([float(vehicle.first_visual_s is not None) for vehicle in done]),
                "mean_lead_s": mean([vehicle.passed_stop_line_s - vehicle.first_visual_s
                                     for vehicle in done if vehicle.first_visual_s is not None]),
                "events": len(self._visual_events),
                "false_events": sum(not real for real in self._visual_events.values()),
            },
            "vehicles": [
                {"id": vehicle.plan.vehicle_id, "approach": vehicle.plan.approach, "depart_s": vehicle.plan.depart_s,
                 "crossed_s": vehicle.passed_stop_line_s, "time_loss_at_crossing_s": vehicle.approach_time_loss,
                 "insertion_delay_s": None if vehicle.entered_s is None else self._insertion_delay(vehicle),
                 "stops_before_crossing": vehicle.approach_stops, "waiting_s": vehicle.waiting,
                 "first_visual_s": vehicle.first_visual_s}
                for vehicle in self._vehicles
            ],
        }
