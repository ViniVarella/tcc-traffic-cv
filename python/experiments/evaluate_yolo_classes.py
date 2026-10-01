"""Avalia o YOLO de duas classes no split de teste, por classe e por distância.

A distância de cada rótulo vem do centro da base da caixa projetado pela
homografia da ROI de faixa (mesma regra da visão em operação), por isso só as
câmeras operacionais (south/east/west) têm faixas de distância; as câmeras de
dataset entram como ``sem_calibracao``. Casamento por IoU sem olhar a classe.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image
import yaml

from vision.dataset_classes import DATASET_CLASSES
from vision.detection_evaluation import Box, DetectionTally, distance_band
from vision.lane_features import load_lane_geometries
from vision.visual_lane_features import VisualLaneFeatureSource
from vision.visual_pipeline import load_calibrations

OPERATIONAL_CAMERAS = ("south", "east", "west")


def parse_args(base_dir: Path) -> argparse.Namespace:
    root = base_dir.parent
    parser = argparse.ArgumentParser(description="Avalia o YOLO por classe e por faixa de distância.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument("--model", type=Path, default=root / "runs/results/models/yolov8n-unity-cam60-2cls-960/weights/best.pt")
    parser.add_argument("--dataset", type=Path, default=root / "results/datasets/unity-cam60-2cls-s3")
    parser.add_argument("--split", default="test")
    parser.add_argument("--confidence", type=float, default=0.15, help="Mesmo limiar da visão em operação.")
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--image-size", type=int, default=960)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def camera_of(stem: str) -> str:
    """``run-304_east_ds_far_step_000003`` → ``east_ds_far``."""
    return stem.split("_", 1)[1].rsplit("_step_", 1)[0]


def read_labels(path: Path, width: int, height: int) -> list[Box]:
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        class_id, cx, cy, w, h = line.split()
        cx, cy, w, h = float(cx) * width, float(cy) * height, float(w) * width, float(h) * height
        boxes.append(Box((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), int(class_id)))
    return boxes


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    from ultralytics import YOLO

    config: dict[str, Any] = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
    calibrations = load_calibrations(base_dir, OPERATIONAL_CAMERAS)
    source = VisualLaneFeatureSource(calibrations, load_lane_geometries(config))
    images = sorted((args.dataset / "images" / args.split).glob("*.jpg"))
    if not images:
        raise FileNotFoundError(f"Nenhuma imagem em {args.dataset / 'images' / args.split}")

    model = YOLO(str(args.model))
    overall = DetectionTally(DATASET_CLASSES)
    per_camera: dict[str, DetectionTally] = {}
    for path in images:
        result = model.predict(source=str(path), imgsz=args.image_size, conf=args.confidence,
                               device=args.device, verbose=False)[0]
        camera_id = camera_of(path.stem)
        with Image.open(path) as image:
            width, height = image.size
        truths = read_labels(args.dataset / "labels" / args.split / f"{path.stem}.txt", width, height)
        calibrated = camera_id in calibrations
        bands = []
        for truth in truths:
            distance = None
            if calibrated:
                observed = source.observations(camera_id, [{"bbox": truth.xyxy}], width, height)
                distance = observed[0].distance_m if observed else None
            bands.append(distance_band(distance, calibrated))
        boxes = result.boxes
        predictions = [Box(tuple(float(v) for v in xyxy), int(cls), float(conf))
                       for xyxy, cls, conf in zip(boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist())]
        for tally in (overall, per_camera.setdefault(camera_id, DetectionTally(DATASET_CLASSES))):
            tally.add_image(truths, bands, predictions, args.iou)

    report = {"model": str(args.model), "dataset": str(args.dataset), "split": args.split, "confidence": args.confidence,
              "iou": args.iou, "image_size": args.image_size, "overall": overall.summary(),
              "per_camera": {camera: tally.summary() for camera, tally in sorted(per_camera.items())}}
    output = args.output or base_dir.parent / "results" / "evaluation" / f"yolo-2cls-{args.split}-por-distancia.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def fmt(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.3f}"

    for name, data in report["overall"]["classes"].items():
        for band, stats in {"todas": data["all"], **data["by_band"]}.items():
            print(f"yolo_eval classe={name} faixa={band} rotulos={stats['labels']} recall={fmt(stats['recall'])} "
                  f"detectado_qualquer_classe={fmt(stats['detected_any_class'])} confusao={fmt(stats['confusion_rate'])}")
    print(f"yolo_eval_complete imagens={overall.images} falsos_positivos={report['overall']['false_positives']} output={output}")


if __name__ == "__main__":
    main()
