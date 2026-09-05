"""Componentes de visão computacional e estimativa de filas."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .camera_calibration import CameraCalibration, load_camera_calibration
from .visual_state import SP_LANE_ORDER, VisualStateEncoder

__all__ = [
    "CameraCalibration",
    "SP_LANE_ORDER",
    "VisualStateEncoder",
    "ByteTrackVehicleTracker",
    "QueueEstimator",
    "ROICounter",
    "VehicleTracker",
    "VisualDebugger",
    "YoloVehicleDetector",
    "load_camera_calibration",
]

_LAZY_IMPORTS = {
    "QueueEstimator": (".queue_estimator", "QueueEstimator"),
    "ByteTrackVehicleTracker": (".byte_track_tracker", "ByteTrackVehicleTracker"),
    "ROICounter": (".roi_counter", "ROICounter"),
    "VehicleTracker": (".sort_tracker", "VehicleTracker"),
    "VisualDebugger": (".visual_debug", "VisualDebugger"),
    "YoloVehicleDetector": (".yolo_detector", "YoloVehicleDetector"),
}


def __getattr__(name: str) -> Any:
    """Importa dependências pesadas de visão apenas quando forem usadas."""
    module_and_attribute = _LAZY_IMPORTS.get(name)
    if module_and_attribute is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = module_and_attribute
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
