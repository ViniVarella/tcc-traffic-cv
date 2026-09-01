"""Compara as contagens visuais Unity contra E2 do SUMO por faixa."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml

from vision.e2_evaluation import lane_comparison_rows, metrics_by_lane


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Avalia YOLO/ByteTrack contra detectores E2 por faixa.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument(
        "--vision-summary",
        type=Path,
        default=base_dir.parent / "results" / "vision" / "unity-realistic-prefabs" / "summary.jsonl",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=base_dir.parent / "results" / "ground_truth" / "sp-e2.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=base_dir.parent / "results" / "evaluation" / "unity-realistic-prefabs",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo JSONL não encontrado: {path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exception:
            raise ValueError(f"JSON inválido em {path}:{line_number}: {exception.msg}") from exception
        if not isinstance(record, dict):
            raise ValueError(f"Registro inválido em {path}:{line_number}; esperado objeto JSON.")
        records.append(record)
    if not records:
        raise ValueError(f"Arquivo JSONL sem registros: {path}")
    return records


def load_lane_mapping(config_path: Path) -> dict[str, dict[str, str]]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    try:
        raw_mapping = config["vision_evaluation"]["lane_detector_mapping"]
    except (KeyError, TypeError) as exception:
        raise ValueError(f"Mapeamento vision_evaluation.lane_detector_mapping ausente em {config_path}.") from exception
    if not isinstance(raw_mapping, dict) or not raw_mapping:
        raise ValueError("O mapeamento de ROI para E2 precisa conter ao menos uma câmera.")
    mapping: dict[str, dict[str, str]] = {}
    for camera_id, lanes in raw_mapping.items():
        if not isinstance(camera_id, str) or not camera_id or not isinstance(lanes, dict) or not lanes:
            raise ValueError("Cada câmera do mapeamento de ROI para E2 precisa conter ao menos uma faixa.")
        mapping[camera_id] = {}
        for lane_id, detector_id in lanes.items():
            if not isinstance(lane_id, str) or not lane_id or not isinstance(detector_id, str) or not detector_id:
                raise ValueError("Cada faixa visual precisa mapear para um ID E2 não vazio.")
            mapping[camera_id][lane_id] = detector_id
    return mapping


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Sem dados para escrever em {path}.")
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    vision_records = load_jsonl(args.vision_summary)
    ground_truth_records = load_jsonl(args.ground_truth)
    mapping = load_lane_mapping(args.config)
    rows = lane_comparison_rows(vision_records, ground_truth_records, mapping)
    metrics = metrics_by_lane(rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / "per_lane.csv"
    metrics_path = args.output_dir / "metrics.csv"
    summary_path = args.output_dir / "summary.json"
    write_csv(rows_path, rows)
    write_csv(metrics_path, metrics)
    summary_path.write_text(
        json.dumps(
            {
                "vision_summary": str(args.vision_summary),
                "ground_truth": str(args.ground_truth),
                "compared_steps": len({row["step_id"] for row in rows}),
                "lane_metrics": metrics,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"evaluation_complete steps={len({row['step_id'] for row in rows})} rows={len(rows)} output={args.output_dir}")


if __name__ == "__main__":
    main()
