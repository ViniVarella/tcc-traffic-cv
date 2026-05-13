"""Funcoes utilitarias para serializacao do protocolo de integracao."""

from __future__ import annotations

import json
from typing import Any

from .protocol import FramePacket, SimulationState


def serialize_state(state: SimulationState | dict[str, Any]) -> bytes:
    """Converte um estado de simulacao em payload JSON codificado em UTF-8."""
    if isinstance(state, SimulationState):
        payload = {
            "step": state.step,
            "sim_time": state.sim_time,
            "vehicles": state.vehicles,
            "traffic_lights": state.traffic_lights,
        }
    else:
        payload = state

    return json.dumps(payload).encode("utf-8")


def deserialize_frame_header(header: dict[str, Any]) -> FramePacket:
    """Converte um cabecalho bruto recebido da Unity em um FramePacket."""
    return FramePacket(
        step_id=int(header.get("step_id", -1)),
        sim_time=float(header.get("sim_time", 0.0)),
        camera_id=str(header.get("camera_id", "unknown")),
        image_format=str(header.get("image_format", "jpeg")),
        payload_size=int(header.get("payload_size", 0)),
        latency_ms=float(header["latency_ms"]) if "latency_ms" in header else None,
    )
