"""Estende as ROIs de faixa das câmeras Unity até um comprimento físico fixo.

Mantém a borda próxima (linha de retenção) desenhada na janela de calibração e
recalcula a borda distante: cada canto distante fica no mesmo afastamento
lateral do canto próximo correspondente, ``--length`` metros a montante ao
longo da lane SUMO, projetado na imagem pela pose exportada. Cantos
compartilhados por faixas vizinhas continuam idênticos, e a ROI de aproximação
é estendida um pouco além das faixas para contê-las. Depois, importe os JSONs
na cena com Traffic Vision > Cameras > Import SP Calibration JSON.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from sumolib.geomhelper import polygonOffsetWithMinimumDistanceToPoint, positionAtShapeOffset

from experiments.check_lane_geometry import ground_to_image_point, image_point_to_ground, lane_shapes
from vision.lane_geometry import order_lane_quad


# Folga da ROI de aproximação além das faixas, em coordenadas normalizadas.
APPROACH_MARGIN = 0.004


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estende as ROIs de faixa até um comprimento físico fixo.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument("--net", type=Path, default=base_dir.parent / "sumo" / "sp" / "Cruzamento.net.xml")
    parser.add_argument("--calibration-dir", type=Path,
                        default=base_dir.parent / "unity" / "TrafficVisionUnity" / "Assets" / "Calibration")
    parser.add_argument("--length", type=float, default=60.0, help="Comprimento desejado de cada ROI de faixa (m).")
    parser.add_argument("--cameras", default="south,east,west")
    parser.add_argument("--dry-run", action="store_true", help="Só imprime os novos pontos, sem gravar os JSONs.")
    return parser.parse_args()


def _tangent(shape: list[tuple[float, float]], offset: float) -> np.ndarray:
    total = sum(math.dist(a, b) for a, b in zip(shape, shape[1:]))
    before = np.array(positionAtShapeOffset(shape, max(0.0, offset - 0.5)))
    after = np.array(positionAtShapeOffset(shape, min(total, offset + 0.5)))
    direction = after - before
    return direction / np.linalg.norm(direction)


def _lane_coordinates(shape: list[tuple[float, float]], point: tuple[float, float]) -> tuple[float, float]:
    """(posição ao longo da lane, afastamento lateral assinado) de um ponto no chão."""
    offset = float(polygonOffsetWithMinimumDistanceToPoint(point, shape))
    tangent = _tangent(shape, offset)
    delta = np.array(point) - np.array(positionAtShapeOffset(shape, offset))
    return offset, float(tangent[0] * delta[1] - tangent[1] * delta[0])


def _ground_point(shape: list[tuple[float, float]], offset: float, lateral: float) -> tuple[float, float]:
    tangent = _tangent(shape, offset)
    normal = np.array([-tangent[1], tangent[0]])
    return tuple(np.array(positionAtShapeOffset(shape, offset)) + normal * lateral)  # type: ignore[return-value]


def _key(point: tuple[float, float]) -> tuple[float, float]:
    return (round(point[0], 5), round(point[1], 5))


def extend_calibration(calibration: dict[str, Any], lanes: dict[str, str], shapes: dict[str, Any], length_m: float) -> dict[str, Any]:
    """Retorna uma cópia da calibração com as bordas distantes a ``length_m`` metros."""
    pose = calibration["pose"]
    aspect = calibration["capture"]["width"] / calibration["capture"]["height"]
    far_by_near: dict[tuple[float, float], list[tuple[float, float]]] = {}
    plans: list[tuple[dict[str, Any], list[tuple[int, tuple[float, float]]]]] = []
    lane_far_distance: dict[str, tuple[Any, float]] = {}

    for lane in calibration["laneRois"]:
        shape = shapes[lanes[lane["id"]]][0]
        points = [(point["x"], point["y"]) for point in lane["points"]]
        near_left, near_right, far_right, far_left = order_lane_quad(points)
        near = [image_point_to_ground(pose, aspect, *corner) for corner in (near_left, near_right)]
        coordinates = [_lane_coordinates(shape, corner) for corner in near]
        far_offset = float(np.mean([offset for offset, _ in coordinates])) - length_m
        if far_offset < 0:
            raise ValueError(f"A lane {lanes[lane['id']]} é curta demais para {length_m} m a partir da ROI {lane['id']}.")
        lane_far_distance[lane["id"]] = (shape, far_offset)
        replacements = []
        for near_corner, far_corner, (_, lateral) in zip((near_left, near_right), (far_left, far_right), coordinates):
            projected = ground_to_image_point(pose, aspect, *_ground_point(shape, far_offset, lateral))
            far_by_near.setdefault(_key(near_corner), []).append(projected)
            replacements.append((points.index(far_corner), near_corner))
        plans.append((lane, replacements))

    # Faixas vizinhas compartilham o canto próximo: usam o mesmo canto distante.
    shared_far = {key: tuple(np.mean(values, axis=0)) for key, values in far_by_near.items()}
    result = json.loads(json.dumps(calibration))
    for lane, replacements in plans:
        target = next(item for item in result["laneRois"] if item["id"] == lane["id"])
        for index, near_corner in replacements:
            u, v = shared_far[_key(near_corner)]
            target["points"][index] = {"x": float(u), "y": float(v)}

    approach = [(point["x"], point["y"]) for point in calibration["approachRoi"]["points"]]
    near_left, near_right, far_right, far_left = order_lane_quad(approach)
    lane_near = {key: shared_far[key] for key in shared_far}
    for near_corner, far_corner, outward in ((near_left, far_left, -1.0), (near_right, far_right, 1.0)):
        key = min(lane_near, key=lambda item: math.dist(item, near_corner))
        u, v = lane_near[key]
        index = approach.index(far_corner)
        result["approachRoi"]["points"][index] = {
            "x": float(min(1.0, max(0.0, u + outward * APPROACH_MARGIN))),
            "y": float(max(0.0, v - APPROACH_MARGIN)),
        }
    for roi in (result["approachRoi"], *result["laneRois"]):
        for point in roi["points"]:
            if not (0.0 <= point["x"] <= 1.0 and 0.0 <= point["y"] <= 1.0):
                raise ValueError(f"A ROI {roi['id']} sai da imagem com {length_m} m; reduza --length ou reposicione a câmera.")
    return result


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    config = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    shapes = lane_shapes(args.net)
    for camera_id in (item.strip() for item in args.cameras.split(",") if item.strip()):
        path = args.calibration_dir / f"{camera_id}-calibration.json"
        calibration = json.loads(path.read_text(encoding="utf-8"))
        lanes = {lane_id: str(raw["sumo_lane"]) for lane_id, raw in config["lane_geometry"][camera_id].items()}
        extended = extend_calibration(calibration, lanes, shapes, args.length)
        for roi in (extended["approachRoi"], *extended["laneRois"]):
            coordinates = " ".join(f"({point['x']:.4f},{point['y']:.4f})" for point in roi["points"])
            print(f"roi_extended camera={camera_id} roi={roi['id']} points={coordinates}")
        if not args.dry_run:
            path.write_text(json.dumps(extended, indent=4) + "\n", encoding="utf-8")
    print(f"extend_complete length_m={args.length} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
