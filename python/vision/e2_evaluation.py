"""Avaliação offline das contagens visuais contra detectores E2 do SUMO."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


LaneMapping = dict[str, dict[str, str]]


def lane_comparison_rows(
    vision_records: list[dict[str, Any]],
    ground_truth_records: list[dict[str, Any]],
    lane_mapping: LaneMapping,
) -> list[dict[str, Any]]:
    """Alinha `summary.jsonl` da visão a snapshots E2 pelo mesmo `step_id`.

    A comparação utiliza `lane_counts` (contagem visual bruta) contra
    `vehicle_count` do E2. `halting_count` e `occupancy` são preservados na
    saída por serem métricas relevantes ao DQN, mas não são equivalentes a uma
    simples contagem de objetos visíveis.
    """
    ground_truth_by_step = _index_records_by_step(ground_truth_records, "ground truth")
    vision_by_step = _index_records_by_step(vision_records, "visão")
    common_steps = sorted(set(vision_by_step) & set(ground_truth_by_step))
    if not common_steps:
        raise ValueError("Não há step_id em comum entre os resultados de visão e o ground truth E2.")

    rows: list[dict[str, Any]] = []
    for step_id in common_steps:
        vision_cameras = _require_mapping(vision_by_step[step_id], "cameras", f"visão step={step_id}")
        ground_truth_detectors = _require_mapping(
            ground_truth_by_step[step_id], "detectors", f"ground truth step={step_id}"
        )
        sim_time = float(ground_truth_by_step[step_id].get("sim_time", 0.0))

        for camera_id, lanes in lane_mapping.items():
            camera = _require_mapping(vision_cameras, camera_id, f"visão step={step_id}")
            lane_counts = _require_mapping(camera, "lane_counts", f"visão camera={camera_id} step={step_id}")
            for lane_id, detector_id in lanes.items():
                detector = _require_mapping(
                    ground_truth_detectors, detector_id, f"ground truth step={step_id}"
                )
                visual_count = int(lane_counts.get(lane_id, 0))
                vehicle_count = int(detector["vehicle_count"])
                rows.append(
                    {
                        "step_id": step_id,
                        "sim_time": sim_time,
                        "camera_id": camera_id,
                        "lane_id": lane_id,
                        "detector_id": detector_id,
                        "visual_count": visual_count,
                        "e2_vehicle_count": vehicle_count,
                        "e2_halting_count": int(detector["halting_count"]),
                        "e2_occupancy": float(detector["occupancy"]),
                        "signed_error": visual_count - vehicle_count,
                        "absolute_error": abs(visual_count - vehicle_count),
                    }
                )
    return rows


def metrics_by_lane(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calcula MAE, RMSE, viés e taxa de acerto por câmera/faixa."""
    if not rows:
        raise ValueError("Não há linhas de comparação para calcular métricas.")

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["camera_id"]), str(row["lane_id"]), str(row["detector_id"]))].append(row)

    metrics: list[dict[str, Any]] = []
    for (camera_id, lane_id, detector_id), lane_rows in sorted(grouped.items()):
        sample_count = len(lane_rows)
        signed_errors = [float(row["signed_error"]) for row in lane_rows]
        absolute_errors = [float(row["absolute_error"]) for row in lane_rows]
        exact_matches = sum(error == 0.0 for error in signed_errors)
        metrics.append(
            {
                "camera_id": camera_id,
                "lane_id": lane_id,
                "detector_id": detector_id,
                "samples": sample_count,
                "mae": round(sum(absolute_errors) / sample_count, 4),
                "rmse": round(math.sqrt(sum(error * error for error in signed_errors) / sample_count), 4),
                "bias": round(sum(signed_errors) / sample_count, 4),
                "exact_match_rate": round(exact_matches / sample_count, 4),
                "visual_mean": round(sum(float(row["visual_count"]) for row in lane_rows) / sample_count, 4),
                "e2_vehicle_mean": round(sum(float(row["e2_vehicle_count"]) for row in lane_rows) / sample_count, 4),
                "e2_halting_mean": round(sum(float(row["e2_halting_count"]) for row in lane_rows) / sample_count, 4),
            }
        )
    return metrics


def _index_records_by_step(records: list[dict[str, Any]], source_name: str) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        if "step_id" not in record:
            raise ValueError(f"Registro de {source_name} sem step_id.")
        step_id = int(record["step_id"])
        if step_id in indexed:
            raise ValueError(f"step_id duplicado em {source_name}: {step_id}.")
        indexed[step_id] = record
    return indexed


def _require_mapping(mapping: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Campo {key!r} ausente ou inválido em {context}.")
    return value
