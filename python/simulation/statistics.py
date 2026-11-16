"""Estatísticas das avaliações: média, IC de 95% e redução pareada por seed.

A seed é a unidade amostral: cada política roda nas mesmas seeds, e a redução
contra a referência é calculada seed a seed.
"""

from __future__ import annotations

import math
from statistics import fmean, stdev
from typing import Any

METRICS = ("mean_waiting_time_seconds", "mean_waiting_time_stopped_seconds", "mean_pending_vehicles",
           "unfinished_vehicles", "teleported_vehicles")
# t de Student bicaudal 95% por graus de liberdade.
T_95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


def confidence_interval(values: list[float]) -> dict[str, float | None]:
    """Média e IC de 95% (t de Student) de valores independentes."""
    mean = fmean(values)
    if len(values) < 2:
        return {"mean": mean, "ci95_low": None, "ci95_high": None}
    half = T_95.get(len(values) - 1, 1.96) * stdev(values) / math.sqrt(len(values))
    return {"mean": mean, "ci95_low": mean - half, "ci95_high": mean + half}


def paired_reduction(policy: list[float], reference: list[float]) -> dict[str, float | None]:
    """Redução relativa (1 − política/referência), seed a seed, com IC de 95%."""
    return confidence_interval([1.0 - value / base for value, base in zip(policy, reference) if base > 0])


def summarize(runs: list[dict[str, Any]], reference: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Média e IC de 95% de cada métrica e, com referência, a redução pareada da espera."""

    summary: dict[str, Any] = {"runs": runs}
    for metric in METRICS:
        values = [float(run[metric]) for run in runs if run.get(metric) is not None]
        if values:
            summary[metric] = confidence_interval(values)
    if reference is not None:
        for metric in METRICS[:2]:
            pairs = [(run.get(metric), base.get(metric)) for run, base in zip(runs, reference)]
            if pairs and all(value is not None and base is not None for value, base in pairs):
                summary[f"reduction_{metric}"] = paired_reduction([float(value) for value, _ in pairs],
                                                                  [float(base) for _, base in pairs])
    return summary
