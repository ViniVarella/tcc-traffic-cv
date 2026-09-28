"""Contrato de features por faixa e rastreador cinemático compartilhado.

As duas fontes de observação — visão (tracks projetados pela homografia da
ROI) e TraCI (posições reais na lane, usadas no pré-treino) — entregam o mesmo
``LaneObservation`` a um ``ApproachKinematicsTracker``. Assim contagem, parados,
ocupação, velocidade e espera têm uma única definição, e a diferença entre as
fontes é só erro de medição.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import count
from typing import Any

import numpy as np


# Padrões dos detectores E2 do SUMO (haltingSpeedThreshold / timeThreshold). Acima
# do ruído de pixel a 1 fps, ao contrário dos 0,1 m/s usados na espera nativa.
DEFAULT_STOP_SPEED_MPS = 1.39
DEFAULT_STOP_TIME_S = 1.0
VEHICLE_FOOTPRINT_M = 7.5  # comprimento padrão (5 m) + minGap (2,5 m) do SUMO


@dataclass(frozen=True, slots=True)
class LaneGeometry:
    """Intervalo físico de uma ROI de faixa ao longo da lane SUMO."""

    camera_id: str
    lane_id: str
    sumo_lane: str
    roi_start_m: float
    roi_end_m: float
    width_m: float

    def __post_init__(self) -> None:
        if self.roi_end_m <= self.roi_start_m or self.width_m <= 0:
            raise ValueError(f"Geometria inválida para {self.camera_id}/{self.lane_id}.")

    @property
    def length_m(self) -> float:
        return self.roi_end_m - self.roi_start_m

    @property
    def capacity(self) -> float:
        """Veículos que cabem parados na ROI (comprimento / 7,5 m)."""
        return max(1.0, self.length_m / VEHICLE_FOOTPRINT_M)


def load_lane_geometries(config: Mapping[str, Any]) -> dict[tuple[str, str], LaneGeometry]:
    """Lê ``lane_geometry`` do perfil YAML, indexado por (câmera, faixa)."""
    geometries: dict[tuple[str, str], LaneGeometry] = {}
    for camera_id, lanes in config["lane_geometry"].items():
        for lane_id, raw in lanes.items():
            geometries[(camera_id, lane_id)] = LaneGeometry(
                camera_id, lane_id, str(raw["sumo_lane"]), float(raw["roi_start_m"]), float(raw["roi_end_m"]), float(raw["width_m"]),
            )
    return geometries


@dataclass(frozen=True, slots=True)
class LaneObservation:
    """Um veículo visto em uma faixa da aproximação em um step.

    ``distance_m`` é a posição da frente do veículo medida a partir da linha de
    retenção, crescendo a montante. ``object_id`` é o ``track_id`` (visão) ou o
    ID SUMO; ``None`` indica detecção sem track.
    """

    lane_id: str
    distance_m: float
    object_id: str | None = None


@dataclass(frozen=True, slots=True)
class LaneFeatures:
    vehicle_count: int
    stopped_count: int
    occupancy: float
    mean_speed_mps: float | None
    waiting_time_s: float
    unknown_speed_count: int = 0


EMPTY_LANE = LaneFeatures(0, 0, 0.0, None, 0.0, 0)


@dataclass(frozen=True, slots=True)
class KinematicsParameters:
    stop_speed_mps: float = DEFAULT_STOP_SPEED_MPS
    stop_time_s: float = DEFAULT_STOP_TIME_S
    move_speed_mps: float = 2.0
    vehicle_length_m: float = 5.0
    max_speed_mps: float = 20.0
    jump_tolerance_m: float = 2.0
    ghost_ttl_s: float = 3.0
    handover_radius_m: float = 1.5
    history_size: int = 3

    def __post_init__(self) -> None:
        if not 0 < self.stop_speed_mps <= self.move_speed_mps:
            raise ValueError("Requer 0 < stop_speed_mps <= move_speed_mps (histerese).")
        if self.history_size < 2 or self.vehicle_length_m <= 0 or self.ghost_ttl_s < 0:
            raise ValueError("Parâmetros cinemáticos inválidos.")

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "KinematicsParameters":
        return cls(**dict(config.get("lane_state", {})))


@dataclass(slots=True)
class _TrackedObject:
    key: str
    lane_id: str
    history: deque[tuple[float, float]]
    last_seen: float
    speed: float | None = None
    below_since: float | None = None
    stopped: bool = False

    @property
    def distance(self) -> float:
        return self.history[-1][1]


class ApproachKinematicsTracker:
    """Mantém a cinemática dos veículos de uma aproximação (uma câmera).

    Os objetos são indexados por aproximação, não por faixa, para que uma troca
    de faixa preserve o histórico. Veículos parados que somem (oclusão comum em
    filas) seguem contando por ``ghost_ttl_s``; use ``ghost_ttl_s=0`` quando a
    fonte não tem oclusão (TraCI).
    """

    def __init__(self, lane_lengths_m: Mapping[str, float], parameters: KinematicsParameters | None = None) -> None:
        if not lane_lengths_m or any(length <= 0 for length in lane_lengths_m.values()):
            raise ValueError("Informe comprimentos positivos para todas as faixas.")
        self.lane_lengths_m = dict(lane_lengths_m)
        self.parameters = parameters or KinematicsParameters()
        self.reset()

    def reset(self) -> None:
        self._objects: dict[str, _TrackedObject] = {}
        self._provisional_ids = count()
        self._last_time: float | None = None

    def update(self, observations: Iterable[LaneObservation], sim_time: float) -> dict[str, LaneFeatures]:
        """Incorpora as observações de um step e devolve as features por faixa."""
        sim_time = float(sim_time)
        if self._last_time is not None and sim_time <= self._last_time:
            raise ValueError("sim_time deve crescer entre atualizações.")
        dt = None if self._last_time is None else sim_time - self._last_time
        self._last_time = sim_time
        observations = [item for item in observations if item.lane_id in self.lane_lengths_m]

        tracked = [item for item in observations if item.object_id is not None]
        untracked = [item for item in observations if item.object_id is None]
        # IDs presentes no frame nunca são tratados como fantasmas disponíveis.
        seen: set[str] = {str(item.object_id) for item in tracked}
        updates: list[tuple[_TrackedObject, LaneObservation]] = []
        handled: set[str] = set()
        for observation in tracked:
            key = str(observation.object_id)
            if key in handled:
                continue
            handled.add(key)
            obj = self._objects.get(key) or self._hand_over(key, observation, seen)
            updates.append((obj, observation))
        for observation in untracked:
            obj = self._match_untracked(observation, seen, dt)
            if obj is None:
                key = f"untracked-{next(self._provisional_ids)}"
                obj = self._new_object(key, observation)
            updates.append((obj, observation))
            seen.add(obj.key)

        for obj, observation in updates:
            self._objects[obj.key] = obj
            self._observe(obj, observation, sim_time)
        self._expire(seen, sim_time)
        return self._features(sim_time)

    # -- associação -------------------------------------------------------

    def _hand_over(self, key: str, observation: LaneObservation, seen: set[str]) -> _TrackedObject:
        """Um track novo junto a um fantasma parado herda seu estado (troca de ID)."""
        radius = self.parameters.handover_radius_m
        candidates = [
            obj for obj in self._objects.values()
            if obj.key not in seen and obj.stopped and obj.lane_id == observation.lane_id
            and abs(obj.distance - observation.distance_m) <= radius
        ]
        if candidates:
            ghost = min(candidates, key=lambda obj: abs(obj.distance - observation.distance_m))
            del self._objects[ghost.key]
            ghost.key = key
            return ghost
        return self._new_object(key, observation)

    def _new_object(self, key: str, observation: LaneObservation) -> _TrackedObject:
        return _TrackedObject(key, observation.lane_id, deque(maxlen=self.parameters.history_size), last_seen=0.0)

    def _match_untracked(self, observation: LaneObservation, seen: set[str], dt: float | None) -> _TrackedObject | None:
        """Associa uma detecção sem track ao objeto conhecido mais próximo, se plausível."""
        best: tuple[float, _TrackedObject] | None = None
        for obj in self._objects.values():
            if obj.key in seen or obj.lane_id != observation.lane_id:
                continue
            elapsed = dt if dt is not None else 1.0
            predicted = obj.distance - (obj.speed or 0.0) * elapsed
            gate = self.parameters.handover_radius_m if obj.stopped else self.parameters.max_speed_mps * elapsed + self.parameters.jump_tolerance_m
            gap = abs(predicted - observation.distance_m)
            if gap <= gate and (best is None or gap < best[0]):
                best = (gap, obj)
        return None if best is None else best[1]

    # -- cinemática -------------------------------------------------------

    def _observe(self, obj: _TrackedObject, observation: LaneObservation, sim_time: float) -> None:
        parameters = self.parameters
        if obj.history:
            last_time, last_distance = obj.history[-1]
            elapsed = sim_time - last_time
            advance = last_distance - observation.distance_m
            if advance < -parameters.jump_tolerance_m or advance > parameters.max_speed_mps * elapsed + parameters.jump_tolerance_m:
                obj.history.clear()
                obj.speed, obj.below_since, obj.stopped = None, None, False
        obj.history.append((sim_time, float(observation.distance_m)))
        obj.lane_id = observation.lane_id
        obj.last_seen = sim_time
        obj.speed = _approach_speed(obj.history)
        if obj.speed is None:
            return
        if obj.stopped:
            if obj.speed > parameters.move_speed_mps:
                obj.stopped, obj.below_since = False, None
            return
        if obj.speed < parameters.stop_speed_mps:
            if obj.below_since is None:
                obj.below_since = sim_time
            obj.stopped = sim_time - obj.below_since >= parameters.stop_time_s
        else:
            obj.below_since = None

    def _expire(self, seen: set[str], sim_time: float) -> None:
        """Remove objetos não vistos; parados sobrevivem como fantasmas por ``ghost_ttl_s``.

        Quem some a menos de um comprimento de veículo da linha de retenção
        provavelmente cruzou o cruzamento (ex.: início do verde) e não vira fantasma.
        """
        for key in [key for key in self._objects if key not in seen]:
            obj = self._objects[key]
            departed = obj.distance < self.parameters.vehicle_length_m
            if departed or not obj.stopped or sim_time - obj.last_seen > self.parameters.ghost_ttl_s:
                del self._objects[key]

    def _features(self, sim_time: float) -> dict[str, LaneFeatures]:
        by_lane: dict[str, list[_TrackedObject]] = {lane_id: [] for lane_id in self.lane_lengths_m}
        for obj in self._objects.values():
            by_lane[obj.lane_id].append(obj)
        return {lane_id: self._lane_features(objects, self.lane_lengths_m[lane_id], sim_time) for lane_id, objects in by_lane.items()}

    def _lane_features(self, objects: list[_TrackedObject], lane_length_m: float, sim_time: float) -> LaneFeatures:
        if not objects:
            return EMPTY_LANE
        speeds = [obj.speed for obj in objects if obj.speed is not None]
        stopped = [obj for obj in objects if obj.stopped]
        return LaneFeatures(
            vehicle_count=len(objects),
            stopped_count=len(stopped),
            occupancy=occupancy_fraction([obj.distance for obj in objects], self.parameters.vehicle_length_m, lane_length_m),
            mean_speed_mps=float(np.mean(speeds)) if speeds else None,
            waiting_time_s=float(sum(sim_time - obj.below_since for obj in stopped if obj.below_since is not None)),
            unknown_speed_count=len(objects) - len(speeds),
        )


def _approach_speed(history: deque[tuple[float, float]]) -> float | None:
    """Velocidade em direção à linha de retenção (m/s) por mínimos quadrados."""
    if len(history) < 2:
        return None
    times = np.asarray([item[0] for item in history])
    distances = np.asarray([item[1] for item in history])
    slope = np.polyfit(times - times[0], distances, 1)[0]
    return max(0.0, float(-slope))


def occupancy_fraction(distances_m: Iterable[float], vehicle_length_m: float, lane_length_m: float) -> float:
    """Fração da ROI coberta pela união de [d, d + comprimento], como a ocupação do E2."""
    intervals = sorted(
        (max(0.0, float(distance)), min(lane_length_m, float(distance) + vehicle_length_m))
        for distance in distances_m
    )
    covered, current_start, current_end = 0.0, None, None
    for start, end in intervals:
        if end <= start:
            continue
        if current_end is None or start > current_end:
            if current_end is not None:
                covered += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        covered += current_end - current_start
    return min(1.0, covered / lane_length_m)
