"""Interfaces de comunicacao entre Python e Unity."""

from .frame_bundle import CapturedFrame, FrameBundle, FrameBundleCollector
from .protocol import FramePacket, PedestrianState, SimulationState, TrafficLightState, VehicleState
from .serialization import deserialize_frame_header, serialize_state
from .unity_comm import UnityBridge

__all__ = [
    "CapturedFrame",
    "FrameBundle",
    "FrameBundleCollector",
    "FramePacket",
    "PedestrianState",
    "SimulationState",
    "TrafficLightState",
    "UnityBridge",
    "VehicleState",
    "deserialize_frame_header",
    "serialize_state",
]
