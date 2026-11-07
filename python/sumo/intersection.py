"""Descrição genérica de um cruzamento semaforizado, lida do ``.net.xml``.

Base do experimento de seleção livre de fase: em vez de faixas e fases fixas do
cenário SP, cada cruzamento é descrito pelas suas fases verdes (estados do
programa estático sem amarelo) e pelas faixas de entrada que cada uma atende.
As ROIs são os últimos ``roi_length_m`` metros de cada faixa de entrada até a
linha de retenção, no mesmo contrato ``LaneGeometry`` das câmeras.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vision.lane_features import LaneGeometry


LaneKey = tuple[str, str]
GREEN_CHARS = frozenset("Gg")


@dataclass(frozen=True, slots=True)
class GreenPhase:
    """Uma fase verde: estado de sinais, duração no programa e faixas atendidas."""

    state: str
    duration_s: float
    lanes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntersectionLayout:
    tls_id: str
    greens: tuple[GreenPhase, ...]
    geometries: Mapping[LaneKey, LaneGeometry]

    @property
    def incoming_lanes(self) -> tuple[str, ...]:
        return tuple(sorted({geometry.sumo_lane for geometry in self.geometries.values()}))

    def lane_keys(self, phase: int) -> tuple[LaneKey, ...]:
        """Chaves ``(edge, faixa)`` das ROIs das faixas atendidas pela fase."""
        lanes = set(self.greens[phase].lanes)
        return tuple(key for key, geometry in self.geometries.items() if geometry.sumo_lane in lanes)


def green_phases(states: Sequence[tuple[str, float]], link_lanes: Mapping[int, str]) -> tuple[GreenPhase, ...]:
    """Extrai as fases verdes de um programa: estados com verde e sem amarelo, sem repetir.

    ``link_lanes`` liga cada ``linkIndex`` à faixa de entrada. Uma faixa entra no
    grupo da fase se algum link dela estiver verde (faixa compartilhada conta
    em todas as fases que a atendem).
    """
    greens: list[GreenPhase] = []
    seen: set[str] = set()
    for state, duration in states:
        if "y" in state.lower() or not GREEN_CHARS & set(state) or state in seen:
            continue
        seen.add(state)
        lanes = tuple(sorted({link_lanes[index] for index, char in enumerate(state) if char in GREEN_CHARS and index in link_lanes}))
        greens.append(GreenPhase(state, float(duration), lanes))
    if len(greens) < 2:
        raise ValueError("O programa precisa de pelo menos duas fases verdes.")
    return tuple(greens)


def roi_geometry(sumo_lane: str, lane_length_m: float, roi_length_m: float) -> LaneGeometry:
    """ROI dos últimos ``roi_length_m`` metros da faixa (até a linha de retenção)."""
    edge, _, index = sumo_lane.rpartition("_")
    start = max(0.0, lane_length_m - roi_length_m)
    return LaneGeometry(edge, f"lane_{index}", sumo_lane, start, lane_length_m, 3.2)


def _read_traffic_light(net_path: str | Path, tls_id: str | None) -> tuple[Any, list[tuple[str, float]], dict[int, str], dict[str, float]]:
    """Semáforo, estados do programa estático, ``linkIndex`` → faixa de entrada e comprimentos."""
    import sumolib

    net = sumolib.net.readNet(str(net_path), withPrograms=True)
    lights = net.getTrafficLights()
    if tls_id is None:
        if len(lights) != 1:
            raise ValueError("Informe tls_id: a rede tem mais de um semáforo.")
        tls = lights[0]
    else:
        tls = net.getTLS(tls_id)
    link_lanes: dict[int, str] = {}
    lengths: dict[str, float] = {}
    for in_lane, _, link_index in tls.getConnections():
        link_lanes[int(link_index)] = in_lane.getID()
        lengths[in_lane.getID()] = float(in_lane.getLength())
    program = next(iter(tls.getPrograms().values()))
    return tls, [(phase.state, phase.duration) for phase in program.getPhases()], link_lanes, lengths


def program_green_indices(net_path: str | Path, tls_id: str | None = None) -> dict[int, int]:
    """Índice da fase no programa estático → índice da fase verde no layout (só fases verdes)."""
    _, states, link_lanes, _ = _read_traffic_light(net_path, tls_id)
    order = [green.state for green in green_phases(states, link_lanes)]
    return {index: order.index(state) for index, (state, _) in enumerate(states) if state in order}


def load_intersection(net_path: str | Path, tls_id: str | None = None, roi_length_m: float = 60.0) -> IntersectionLayout:
    """Lê o semáforo (o único da rede, se ``tls_id`` for omitido) e monta o layout."""
    tls, states, link_lanes, lengths = _read_traffic_light(net_path, tls_id)
    greens = green_phases(states, link_lanes)
    geometries = {}
    for lane, length in sorted(lengths.items()):
        geometry = roi_geometry(lane, length, roi_length_m)
        geometries[(geometry.camera_id, geometry.lane_id)] = geometry
    return IntersectionLayout(tls.getID(), greens, geometries)
