"""Funcoes utilitarias para serializacao do protocolo de integracao."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Any

from .protocol import FramePacket, SimulationState


def _normalize_message(value: Any) -> Any:
    """Converte dataclasses do protocolo em estruturas JSON serializaveis."""
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_normalize_message(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_message(item) for key, item in value.items()}
    return value


def serialize_state(state: SimulationState | dict[str, Any]) -> bytes:
    """Converte um estado de simulacao em payload JSON codificado em UTF-8."""
    if isinstance(state, SimulationState):
        payload = {
            "step": state.step,
            "step_id": state.step,
            "sim_time": state.sim_time,
            "vehicles": _normalize_message(state.vehicles),
            "traffic_lights": _normalize_message(state.traffic_lights),
        }
    else:
        payload = _normalize_message(state)
        if "step" in payload and "step_id" not in payload:
            payload["step_id"] = payload["step"]

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
