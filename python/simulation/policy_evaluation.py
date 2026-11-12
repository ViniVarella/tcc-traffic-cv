"""Avaliação de uma política da linha manter/trocar em várias seeds do cenário SP."""

from __future__ import annotations

from statistics import fmean
from typing import Any

from simulation.episode import Policy
from simulation.sp_environment import SpEnvironment


SUMMARY_KEYS = (
    "mean_waiting_time_seconds", "mean_waiting_time_stopped_seconds", "stopped_vehicle_share",
    "mean_travel_time_seconds", "arrived_vehicles", "throughput_vehicles_per_hour",
    "mean_queue_length", "mean_pending_vehicles", "final_pending_vehicles", "teleported_vehicles",
    # Só nos cenários com pedestres (None nos demais).
    "pedestrians_arrived", "pedestrian_mean_waiting_s", "pedestrian_median_waiting_s",
    "pedestrian_p90_waiting_s", "pedestrian_p95_waiting_s", "pedestrian_max_waiting_s",
)


def evaluate(environment: SpEnvironment, policy: Policy, seeds: list[int], **run_options: Any) -> dict[str, Any]:
    """Roda a política em cada seed; ``run_options`` vai para ``SpEnvironment.run`` (ex.: observer)."""
    runs = []
    for seed in seeds:
        outcome, scenario = environment.run(seed, policy, **run_options)
        green = {name: outcome.phase_seconds.get(name, 0) for name in ("EAST_WEST_GREEN", "SOUTH_GREEN")}
        runs.append({"seed": seed, "scenario": scenario, "mean_reward": outcome.mean_reward, "switches": outcome.switches,
                     "switch_rate": outcome.switch_rate, "missing_observations": outcome.missing_observations,
                     "east_west_green_share": green["EAST_WEST_GREEN"] / max(1, sum(green.values())),
                     **{key: outcome.metrics.get(key) for key in SUMMARY_KEYS}})
    numeric = ("mean_reward", "switches", "east_west_green_share", *SUMMARY_KEYS)
    return {"runs": runs, "mean": {key: fmean(float(run[key]) for run in runs) for key in numeric if all(run[key] is not None for run in runs)}}
