"""Políticas de decisão baseadas exclusivamente nas contagens visuais."""

from __future__ import annotations

from typing import Any


class QueueBasedPolicy:
    """Decide se o grupo oposto merece trocar o próximo verde."""

    def __init__(self, switch_margin: int = 1) -> None:
        if switch_margin < 0:
            raise ValueError("switch_margin não pode ser negativo.")
        self.switch_margin = int(switch_margin)

    def should_switch(self, current_demand: int, opposing_demand: int) -> tuple[bool, str]:
        """Indica troca por fila vazia ou por demanda oposta significativamente maior."""
        if opposing_demand <= 0:
            return False, "opposing_demand_empty"
        if current_demand <= 0:
            return True, "current_demand_empty"
        if opposing_demand >= current_demand + self.switch_margin:
            return True, "opposing_demand_higher"
        return False, "current_demand_kept"

    @staticmethod
    def aggregate(visual_counts: dict[str, Any]) -> dict[str, int]:
        """Agrupa South e East+West sem consultar sensores internos do SUMO."""
        return {
            "south": QueueBasedPolicy._direction_total(visual_counts, "south"),
            "east_west": (
                QueueBasedPolicy._direction_total(visual_counts, "east")
                + QueueBasedPolicy._direction_total(visual_counts, "west")
            ),
        }

    @staticmethod
    def _direction_total(visual_counts: dict[str, Any], direction: str) -> int:
        direct = visual_counts.get(direction)
        if isinstance(direct, int):
            return max(0, direct)
        if isinstance(direct, dict):
            return sum(max(0, int(value)) for value in direct.values())
        return sum(
            max(0, int(value))
            for key, value in visual_counts.items()
            if key.startswith(f"{direction}/") and isinstance(value, (int, float))
        )


# Aproximações servidas por cada verde lógico do cenário SP.
GREEN_GROUPS = {"EAST_WEST_GREEN": ("east", "west"), "SOUTH_GREEN": ("south",)}
KEEP, SWITCH = 0, 1


class FixedCyclePolicy:
    """Nunca pede troca: o verde dura até o verde máximo (ciclo fixo seguro)."""

    name = "fixed_cycle"

    def __call__(self, state: Any, lane_features: dict[tuple[str, str], Any], phase: Any) -> int:
        return KEEP


class MaxPressurePolicy:
    """Troca quando a fila parada do grupo oposto supera a do atual mais o custo da troca.

    Sem ``margin``, o custo é o que o grupo atual descarregaria durante amarelo +
    all-red (~1 veículo a cada 2 s por faixa), como em ``optimization/SP``.
    """

    name = "max_pressure"

    def __init__(self, lost_time_s: float = 4.0, margin: float | None = None) -> None:
        self.lost_time_s = float(lost_time_s)
        self.margin = margin

    def __call__(self, state: Any, lane_features: dict[tuple[str, str], Any], phase: Any) -> int:
        current = GREEN_GROUPS[phase.name]
        opposing = next(group for name, group in GREEN_GROUPS.items() if name != phase.name)
        current_queue = _group_queue(lane_features, current)
        opposing_queue = _group_queue(lane_features, opposing)
        if current_queue < 1:
            return SWITCH if opposing_queue > 0 else KEEP
        lanes = sum(camera in current for camera, _ in lane_features)
        margin = self.margin if self.margin is not None else lanes * self.lost_time_s / 2.0
        return SWITCH if opposing_queue > current_queue + margin else KEEP


def _group_queue(lane_features: dict[tuple[str, str], Any], cameras: tuple[str, ...]) -> int:
    return sum(features.stopped_count for (camera, _), features in lane_features.items() if camera in cameras)
