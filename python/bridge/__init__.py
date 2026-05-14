"""Interfaces de comunicacao entre Python e Unity."""

from .protocol import FramePacket, SimulationState, TrafficLightState, VehicleState
from .serialization import deserialize_frame_header, serialize_state
from .unity_comm import UnityBridge

__all__ = [
    "FramePacket",
    "SimulationState",
    "TrafficLightState",
    "UnityBridge",
    "VehicleState",
    "deserialize_frame_header",
    "serialize_state",
]
