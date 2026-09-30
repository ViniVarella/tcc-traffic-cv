"""Domain gap visão × oráculo TraCI a partir do log por step de ``run_visual_policy``."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from statistics import fmean, median
from typing import Any

import numpy as np

from .lane_features import LaneFeatures


FEATURES = ("vehicle_count", "stopped_count", "occupancy", "mean_speed_mps", "waiting_time_s")


def feature_gap(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, dict[str, float | int | None]]]:
    """Por faixa e feature: amostras, MAE, viés (visão − oráculo), RMSE e correlação."""
    pairs: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        visual, oracle = record.get("visual"), record.get("oracle")
        if visual is None or oracle is None:
            continue
        for lane, visual_features in visual.items():
            oracle_features = oracle.get(lane)
            if oracle_features is None:
                continue
            for name in FEATURES:
                estimated, truth = visual_features.get(name), oracle_features.get(name)
                if estimated is not None and truth is not None:
                    pairs[lane][name].append((float(estimated), float(truth)))
    return {lane: {name: _error_summary(values) for name, values in by_feature.items()} for lane, by_feature in sorted(pairs.items())}


def _error_summary(values: list[tuple[float, float]]) -> dict[str, float | int | None]:
    estimated = np.asarray([item[0] for item in values])
    truth = np.asarray([item[1] for item in values])
    error = estimated - truth
    correlation = None
    if len(values) > 1 and estimated.std() > 0 and truth.std() > 0:
        correlation = float(np.corrcoef(estimated, truth)[0, 1])
    return {
        "samples": len(values),
        "mae": float(np.abs(error).mean()),
        "bias": float(error.mean()),
        "rmse": float(np.sqrt((error ** 2).mean())),
        "pearson_r": correlation,
        "exact_match_rate": float((error == 0).mean()),
    }


def ground_offset_estimate(records: Iterable[Mapping[str, Any]], max_gap_m: float = 5.0) -> dict[str, dict[str, float | int | None]]:
    """Estima, por câmera, quanto somar à distância visual para coincidir com o oráculo.

    Em cada step e faixa, pareia gulosamente cada observação visual com a do
    oráculo mais próxima (até ``max_gap_m``). O resultado sugere
    ``lane_state.visual_ground_offset_m``.
    """
    gaps: dict[str, list[float]] = defaultdict(list)
    for record in records:
        visual, oracle = record.get("visual_observations") or {}, record.get("oracle_observations") or {}
        for camera, visual_items in visual.items():
            for lane in {item[0] for item in visual_items}:
                estimated = sorted(item[1] for item in visual_items if item[0] == lane)
                truth = sorted(item[1] for item in oracle.get(camera, []) if item[0] == lane)
                gaps[camera].extend(_greedy_gaps(estimated, truth, max_gap_m))
    return {
        camera: {"matches": len(values), "mean_offset_m": fmean(values) if values else None, "median_offset_m": median(values) if values else None}
        for camera, values in sorted(gaps.items())
    }


def _greedy_gaps(estimated: list[float], truth: list[float], max_gap_m: float) -> list[float]:
    candidates = sorted((abs(t - e), i, j) for i, e in enumerate(estimated) for j, t in enumerate(truth) if abs(t - e) <= max_gap_m)
    used_estimated: set[int] = set()
    used_truth: set[int] = set()
    gaps = []
    for _, i, j in candidates:
        if i in used_estimated or j in used_truth:
            continue
        used_estimated.add(i)
        used_truth.add(j)
        gaps.append(truth[j] - estimated[i])
    return gaps


def action_agreement(records: Iterable[Mapping[str, Any]], q_values: Callable[[np.ndarray], np.ndarray], encoder: Any) -> dict[str, float | int | None]:
    """Nos pontos de decisão, compara a ação gulosa com features visuais e do oráculo."""
    agreements: list[bool] = []
    gaps: list[float] = []
    for record in records:
        if record.get("requested_action") is None or record.get("visual") is None or record.get("oracle") is None:
            continue
        states = [
            encoder.encode(_features(record[source]), int(record["phase_index"]), float(record["phase_elapsed"]))
            for source in ("visual", "oracle")
        ]
        visual_q, oracle_q = (np.asarray(q_values(state)) for state in states)
        agreements.append(int(visual_q.argmax()) == int(oracle_q.argmax()))
        gaps.append(float(np.abs(visual_q - oracle_q).max()))
    return {
        "decisions": len(agreements),
        "agreement_rate": None if not agreements else float(np.mean(agreements)),
        "mean_max_abs_q_gap": None if not gaps else float(np.mean(gaps)),
    }


def _features(raw: Mapping[str, Mapping[str, Any]]) -> dict[tuple[str, str], LaneFeatures]:
    return {tuple(lane.split("/", 1)): LaneFeatures(**values) for lane, values in raw.items()}  # type: ignore[misc]
