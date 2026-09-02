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
