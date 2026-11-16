"""Metadados descritivos de uma execucao experimental."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RunMetadata:
    """Agrupa informacoes que identificam e contextualizam uma execucao."""

    scenario_name: str
    controller_name: str
    notes: dict[str, Any] = field(default_factory=dict)
