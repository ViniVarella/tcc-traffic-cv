"""Pedido de preempção a partir da detecção visual de viaturas (classe ``emergency``).

A captura é de 1 frame por segundo simulado e uma viatura a ~14 m/s percorre
os 60 m da ROI em ~4 frames, então o ``track_id`` do ByteTrack não é confiável
para ela. O detector trabalha por aproximação: uma viatura está presente quando
há objeto ``emergency`` dentro de uma ROI de faixa em ``confirm_frames``
frames seguidos. Sem ver mais a viatura (saiu da ROI rumo à linha de retenção,
ficou oculta ou faltou frame), o pedido continua pelo tempo estimado até a
linha, mais uma folga, e então se encerra (para a preempção, "cruzou").

Limitações: uma viatura por aproximação de cada vez, e a visão só enxerga a
viatura dentro dos 60 m da ROI (o aviso V2I chega bem antes).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from controller.preemption import EmergencyRequest

from .lane_features import LaneGeometry
from .visual_lane_features import VisualLaneFeatureSource


EMERGENCY_CLASS_ID = 1


@dataclass(frozen=True, slots=True)
class VisualEmergencySettings:
    confirm_frames: int = 2
    # Velocidade mínima usada na estimativa do tempo até a linha (mesma regra do
    # aviso V2I: metade da velocidade livre), para que uma viatura parada na
    # fila também peça passagem.
    min_speed_mps: float = 13.89 / 2
    max_speed_mps: float = 25.0
    hold_margin_s: float = 3.0

    def __post_init__(self) -> None:
        if self.confirm_frames < 1 or self.min_speed_mps <= 0 or self.max_speed_mps < self.min_speed_mps or self.hold_margin_s < 0:
            raise ValueError("Parâmetros inválidos para a detecção visual de emergência.")

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "VisualEmergencySettings":
        emergency = config.get("emergency", {})
        raw = dict(emergency.get("visual_detection", {}))
        if "min_speed_mps" not in raw and "free_speed_mps" in emergency:
            raw["min_speed_mps"] = float(emergency["free_speed_mps"]) / 2
        return cls(**raw)


@dataclass(slots=True)
class _Approach:
    streak: int = 0
    event: int = 0
    active: bool = False
    distance_m: float = 0.0
    seen_s: float = 0.0
    speed_mps: float | None = None


class VisualEmergencyDetector:
    """Converte distâncias de viaturas vistas por câmera em ``EmergencyRequest``."""

    def __init__(self, approaches: Sequence[str], settings: VisualEmergencySettings = VisualEmergencySettings()) -> None:
        self.settings = settings
        self.approaches = tuple(approaches)
        self.reset()

    def reset(self) -> None:
        self._state = {approach: _Approach() for approach in self.approaches}
        self.events_started = 0

    def update(self, sightings: Mapping[str, Sequence[float]] | None, sim_time: float) -> list[EmergencyRequest]:
        """``sightings``: distâncias até a linha de retenção (m) das viaturas vistas
        por aproximação neste frame; ``None`` quando faltou o frame (sem informação)."""
        requests: list[EmergencyRequest] = []
        for approach, state in self._state.items():
            distances = None if sightings is None else sightings.get(approach, ())
            if distances:
                self._see(state, min(distances), sim_time)
            elif distances is not None:
                state.streak = 0
            request = self._request(approach, state, sim_time)
            if request is not None:
                requests.append(request)
        return requests

    def _see(self, state: _Approach, distance: float, sim_time: float) -> None:
        if state.active or state.streak > 0:
            elapsed = sim_time - state.seen_s
            if elapsed > 0:
                speed = (state.distance_m - distance) / elapsed
                state.speed_mps = min(self.settings.max_speed_mps, max(0.0, speed))
        else:
            state.speed_mps = None
        state.streak += 1
        state.distance_m, state.seen_s = distance, sim_time
        if not state.active and state.streak >= self.settings.confirm_frames:
            state.active = True
            state.event = self.events_started
            self.events_started += 1

    def _request(self, approach: str, state: _Approach, sim_time: float) -> EmergencyRequest | None:
        if not state.active:
            return None
        speed = max(self.settings.min_speed_mps, state.speed_mps or 0.0)
        eta_at_sighting = state.distance_m / speed
        elapsed = sim_time - state.seen_s
        if elapsed > eta_at_sighting + self.settings.hold_margin_s:
            state.active = False
            state.streak = 0
            return None
        return EmergencyRequest(f"vision_{approach}_{state.event}", approach, max(0.0, eta_at_sighting - elapsed))


def emergency_sightings(
    camera_results: Mapping[str, Any],
    source: VisualLaneFeatureSource,
    geometries: Mapping[tuple[str, str], LaneGeometry],
    class_id: int = EMERGENCY_CLASS_ID,
) -> dict[str, list[float]]:
    """Distâncias até a linha de retenção dos objetos ``emergency`` dentro das ROIs.

    A posição na ROI vem da mesma homografia das features por faixa; somar o
    início da ROI (``roi_start_m``) leva à distância até a linha de retenção.
    """
    sightings: dict[str, list[float]] = {}
    for camera_id, result in camera_results.items():
        objects = [obj for obj in result.objects if int(obj.get("class_id", -1)) == class_id]
        if not objects:
            continue
        height, width = result.frame.shape[:2]
        for observation in source.observations(camera_id, objects, width, height):
            geometry = geometries[(camera_id, observation.lane_id)]
            sightings.setdefault(camera_id, []).append(geometry.roi_start_m + observation.distance_m)
    return sightings
