"""Funcoes utilitarias para serializacao do protocolo de integracao."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import json
from typing import Any

from .protocol import FramePacket, SimulationState


# O macOS limita um datagrama UDP a 9216 bytes (net.inet.udp.maxdgram). Com
# pedestres o estado passa disso; acima deste tamanho ele vai em partes, que a
# Unity junta pelo step_id.
MAX_STATE_DATAGRAM_BYTES = 8192
# Casas decimais dos floats do estado (milímetros em posição).
STATE_FLOAT_DECIMALS = 3
_SPLIT_LISTS = ("vehicles", "pedestrians")


def _normalize_message(value: Any) -> Any:
    """Converte dataclasses do protocolo em estruturas JSON serializaveis."""
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_normalize_message(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_message(item) for key, item in value.items()}
    return value


def _round_floats(value: Any) -> Any:
    """Arredonda floats aninhados para encurtar o JSON."""
    if isinstance(value, float):
        return round(value, STATE_FLOAT_DECIMALS)
    if isinstance(value, list):
        return [_round_floats(item) for item in value]
    if isinstance(value, dict):
        return {key: _round_floats(item) for key, item in value.items()}
    return value


def _dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _state_payload(state: SimulationState | dict[str, Any]) -> dict[str, Any]:
    """Monta o dicionário do estado, com floats arredondados."""
    if isinstance(state, SimulationState):
        payload = {
            "step": state.step,
            "step_id": state.step,
            "sim_time": state.sim_time,
            "vehicles": _normalize_message(state.vehicles),
            "traffic_lights": _normalize_message(state.traffic_lights),
            "pedestrians": _normalize_message(state.pedestrians),
        }
    else:
        payload = _normalize_message(state)
        if "step" in payload and "step_id" not in payload:
            payload["step_id"] = payload["step"]
    return _round_floats(payload)


def serialize_state(state: SimulationState | dict[str, Any]) -> bytes:
    """Converte um estado de simulacao em payload JSON codificado em UTF-8."""
    return _dumps(_state_payload(state))


def serialize_state_datagrams(
    state: SimulationState | dict[str, Any], max_bytes: int = MAX_STATE_DATAGRAM_BYTES,
) -> list[bytes]:
    """Serializa o estado em um ou mais datagramas de até ``max_bytes``.

    Cabendo, vai inteiro e sem campos extras. Senão, veículos e pedestres são
    repartidos entre partes com ``part``/``parts``; cada parte repete o resto
    (step, semáforos), e a Unity só aplica o estado quando tem todas.
    """
    payload = _state_payload(state)
    whole = _dumps(payload)
    if len(whole) <= max_bytes:
        return [whole]

    entities = [(key, item) for key in _SPLIT_LISTS for item in payload.get(key, [])]
    header = {key: value for key, value in payload.items() if key not in _SPLIT_LISTS}
    # Folga para "part"/"parts" e as chaves das listas vazias.
    base_size = len(_dumps({**header, **{key: [] for key in _SPLIT_LISTS}, "part": 9999, "parts": 9999}))
    budget = max_bytes - base_size
    chunks: list[list[tuple[str, Any]]] = [[]]
    used = 0
    for key, item in entities:
        size = len(_dumps(item)) + 1
        if size > budget:
            raise ValueError(f"entidade {item.get('id')!r} não cabe em um datagrama de {max_bytes} bytes")
        if used + size > budget:
            chunks.append([])
            used = 0
        chunks[-1].append((key, item))
        used += size

    datagrams = []
    for index, chunk in enumerate(chunks):
        part = {**header, **{key: [item for k, item in chunk if k == key] for key in _SPLIT_LISTS}}
        part.update(part=index, parts=len(chunks))
        datagrams.append(_dumps(part))
    return datagrams


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
