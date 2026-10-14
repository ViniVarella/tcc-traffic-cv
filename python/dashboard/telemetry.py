"""Telemetria do painel a partir do ``on_step`` do executor de episódios.

Separa o que a política vê (``LaneFeatures`` da câmera, por aproximação) do que
só o SUMO sabe (métricas *ground truth* do TraCI nas faixas de entrada). O
painel mostra os dois lado a lado e precisa rotulá-los assim.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


APPROACHES = ("south", "east", "west")


def approach_features(lane_features: Mapping[tuple[str, str], Any] | None,
                      approaches: Sequence[str] = APPROACHES) -> dict[str, dict[str, float]] | None:
    """Soma veículos, parados e espera das faixas de cada aproximação (câmera)."""
    if lane_features is None:
        return None
    totals = {approach: {"vehicles": 0, "stopped": 0, "waiting_s": 0.0} for approach in approaches}
    for (camera_id, _lane_id), features in lane_features.items():
        if camera_id not in totals:
            continue
        totals[camera_id]["vehicles"] += int(features.vehicle_count)
        totals[camera_id]["stopped"] += int(features.stopped_count)
        totals[camera_id]["waiting_s"] += float(features.waiting_time_s)
    return totals


def ground_truth_metrics(lane_metrics: Mapping[str, float | int]) -> dict[str, float | int | None]:
    """Métricas do TraCI: parados, espera média por veículo parado e fila de inserção."""
    halting = int(lane_metrics.get("halting_vehicles", 0))
    waiting = float(lane_metrics.get("waiting_time_s", 0.0))
    pedestrians = lane_metrics.get("pedestrian_waiting_s")
    return {
        "halting_vehicles": halting,
        "waiting_time_s": waiting,
        # A soma da espera nas faixas cresce com a fila; por veículo parado é comparável.
        "mean_wait_per_stopped_s": waiting / halting if halting else 0.0,
        "pending_vehicles": int(lane_metrics.get("pending_vehicles", 0)),
        "pedestrian_waiting_s": None if pedestrians is None else float(pedestrians),
    }


# Cor do semáforo de cada aproximação por fase do PhaseManager. Leste e Oeste
# andam juntos; all-red e as fases de pedestre deixam todos os veículos no vermelho.
_SIGNALS = {
    "EAST_WEST_GREEN": {"south": "red", "east": "green", "west": "green"},
    "EAST_WEST_YELLOW": {"south": "red", "east": "yellow", "west": "yellow"},
    "SOUTH_GREEN": {"south": "green", "east": "red", "west": "red"},
    "SOUTH_YELLOW": {"south": "yellow", "east": "red", "west": "red"},
}


def signal_by_approach(phase: str) -> dict[str, str]:
    """Cor do semáforo (green/yellow/red) de cada aproximação na fase dada."""
    return dict(_SIGNALS.get(phase, {approach: "red" for approach in APPROACHES}))


def build_telemetry(info: Mapping[str, Any]) -> dict[str, Any]:
    """Converte o dicionário do ``on_step`` em JSON para o painel."""
    return {
        "sim_time": float(info["sim_time"]),
        "phase": str(info["phase"]),
        "signals": signal_by_approach(str(info["phase"])),
        "phase_elapsed": float(info.get("phase_elapsed", 0.0)),
        "reward": float(info["reward"]),
        # Verde que a preempção segura para a viatura (nome da fase), ou None.
        "preempt_target": info.get("preempt_target"),
        "vision": approach_features(info.get("lane_features")),
        "ground_truth": ground_truth_metrics(info["lane_metrics"]),
    }
