"""Classes do dataset sintético e do YOLO ajustado, derivadas do tipo SUMO do veículo."""

from __future__ import annotations


# O índice é o class_id do YOLO. Ordem estável: não reordene sem retreinar.
DATASET_CLASSES = ("vehicle", "emergency")
EMERGENCY_VEHICLE_TYPE = "emergency"
EMERGENCY_CLASS_ID = DATASET_CLASSES.index("emergency")


def class_for_vehicle_type(vehicle_type: str | None) -> int:
    """``emergency`` para viaturas de emergência; ``vehicle`` para os demais tipos."""
    return EMERGENCY_CLASS_ID if (vehicle_type or "").lower() == EMERGENCY_VEHICLE_TYPE else 0


def yaml_names() -> str:
    return "names:\n" + "".join(f"  {index}: {name}\n" for index, name in enumerate(DATASET_CLASSES))
