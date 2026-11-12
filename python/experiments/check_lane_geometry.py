"""Compara a extensão física de cada ROI de faixa com o detector E2 correspondente.

Projeta as bordas próxima e distante das ROIs no plano da via usando a pose e o
FOV exportados pela Unity e mede onde elas caem ao longo da lane SUMO. Não
inicia SUMO nem Unity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ElementTree

import numpy as np
import yaml
from sumolib.geomhelper import polygonOffsetWithMinimumDistanceToPoint

from paths import PYTHON_DIR
from sumo.intersection import lane_shapes
from vision.camera_projection import image_point_to_ground
from vision.lane_geometry import order_lane_quad


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Confere ROIs de faixa × detectores E2 do cenário SP.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument("--net", type=Path, default=base_dir.parent / "sumo" / "sp" / "Cruzamento.net.xml")
    parser.add_argument("--additional", type=Path, default=base_dir.parent / "sumo" / "sp" / "Cruzamento.add.xml")
    parser.add_argument("--output", type=Path, default=None, help="JSON opcional com o relatório por faixa.")
    return parser.parse_args()


def detector_extents(additional_path: Path) -> dict[str, dict[str, Any]]:
    return {
        detector.attrib["id"]: {
            "lane": detector.attrib["lane"],
            "start": float(detector.attrib["pos"]),
            "end": float(detector.attrib["pos"]) + float(detector.attrib["length"]),
        }
        for detector in ElementTree.parse(additional_path).getroot().iter("laneAreaDetector")
    }


def lane_report(calibration: dict[str, Any], lane_id: str, detector: dict[str, Any],
                shape: list[tuple[float, float]], lane_width: float) -> dict[str, Any]:
    width, height = calibration["capture"]["width"], calibration["capture"]["height"]
    raw = next(item for item in calibration["laneRois"] if item["id"] == lane_id)
    near_left, near_right, far_right, far_left = order_lane_quad([(point["x"], point["y"]) for point in raw["points"]])
    ground = {
        name: image_point_to_ground(calibration["pose"], width / height, *point)
        for name, point in {"near_left": near_left, "near_right": near_right, "far_right": far_right, "far_left": far_left}.items()
    }
    near_mid = tuple(np.mean([ground["near_left"], ground["near_right"]], axis=0))
    far_mid = tuple(np.mean([ground["far_left"], ground["far_right"]], axis=0))
    roi_end = float(polygonOffsetWithMinimumDistanceToPoint(near_mid, shape))
    roi_start = float(polygonOffsetWithMinimumDistanceToPoint(far_mid, shape))
    near_width = float(np.linalg.norm(np.subtract(ground["near_left"], ground["near_right"])))
    far_width = float(np.linalg.norm(np.subtract(ground["far_left"], ground["far_right"])))
    return {
        "lane": detector["lane"],
        "roi_start_m": round(roi_start, 2),
        "roi_end_m": round(roi_end, 2),
        "roi_length_m": round(roi_end - roi_start, 2),
        "e2_start_m": detector["start"],
        "e2_end_m": detector["end"],
        "e2_length_m": round(detector["end"] - detector["start"], 2),
        "start_delta_m": round(roi_start - detector["start"], 2),
        "end_delta_m": round(roi_end - detector["end"], 2),
        "roi_width_near_m": round(near_width, 2),
        "roi_width_far_m": round(far_width, 2),
        "lane_width_m": lane_width,
    }


def measure_lane_rois(config: dict[str, Any], net_path: Path, additional_path: Path,
                      calibration_dir: Path) -> dict[str, dict[str, Any]]:
    """Mede, para cada ROI mapeada em ``vision_evaluation``, sua extensão na lane SUMO."""
    shapes = lane_shapes(net_path)
    detectors = detector_extents(additional_path)
    report: dict[str, dict[str, Any]] = {}
    for camera_id, lanes in config["vision_evaluation"]["lane_detector_mapping"].items():
        calibration = json.loads((calibration_dir / f"{camera_id}-calibration.json").read_text(encoding="utf-8"))
        for lane_id, detector_id in lanes.items():
            detector = detectors[detector_id]
            shape, lane_width = shapes[detector["lane"]]
            report[f"{camera_id}/{lane_id}"] = {"detector": detector_id, **lane_report(calibration, lane_id, detector, shape, lane_width)}
    return report


def main() -> None:
    base_dir = PYTHON_DIR
    args = parse_args(base_dir)
    config = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    calibration_dir = base_dir.parent / "unity" / "TraffIQ-TCC" / "Assets" / "Calibration"
    report = measure_lane_rois(config, args.net, args.additional, calibration_dir)
    for name, row in report.items():
        print(
            f"lane_geometry {name} detector={row['detector']} lane={row['lane']} "
            f"roi=[{row['roi_start_m']}, {row['roi_end_m']}] e2=[{row['e2_start_m']}, {row['e2_end_m']:.2f}] "
            f"start_delta={row['start_delta_m']} end_delta={row['end_delta_m']} "
            f"width_near={row['roi_width_near_m']} width_far={row['roi_width_far_m']} lane_width={row['lane_width_m']}"
        )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
