"""Executa YOLO e contagem por faixa sobre frames já capturados da Unity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

import cv2

from vision import ByteTrackVehicleTracker, QueueEstimator, ROICounter, VisualDebugger, YoloVehicleDetector, load_camera_calibration
from vision.roi_counter import filter_detections_to_roi, select_counting_objects


def parse_args(base_dir: Path) -> argparse.Namespace:
    """Configura o processamento offline dos conjuntos de frames Unity."""
    parser = argparse.ArgumentParser(description="Executa YOLO + ROIs nos frames capturados da Unity.")
    parser.add_argument("--frames-root", type=Path, default=base_dir.parent / "results" / "frames" / "unity")
    parser.add_argument("--calibration-dir", type=Path, default=base_dir.parent / "unity" / "TrafficVisionUnity" / "Assets" / "Calibration")
    parser.add_argument("--output-dir", type=Path, default=base_dir.parent / "results" / "vision" / "unity")
    parser.add_argument("--model", default="yolov8n.pt", help="Modelo Ultralytics local ou identificador compatível.")
    parser.add_argument("--camera-ids", default="south,east,west", help="IDs de câmera separados por vírgula.")
    parser.add_argument("--max-steps", type=int, default=100, help="Máximo de steps completos a processar.")
    parser.add_argument("--frame-step", type=int, default=1, help="Processa um a cada N steps completos.")
    parser.add_argument(
        "--frame-rate",
        type=float,
        default=1.0,
        help="Taxa efetiva dos frames em tempo simulado; a captura SP atual gera um por segundo.",
    )
    parser.add_argument("--confidence", type=float, default=0.15, help="Confiança mínima YOLO, igual ao fluxo SimJamCV.")
    parser.add_argument("--nms-iou", type=float, default=0.5, help="IoU do NMS agnóstico de classe.")
    parser.add_argument("--image-size", type=int, default=1280, help="Tamanho de inferência YOLO.")
    parser.add_argument(
        "--track-match-threshold",
        type=float,
        default=0.6,
        help="Tolerância de associação do ByteTrack; maior aceita deslocamentos maiores entre frames.",
    )
    parser.add_argument(
        "--tracker",
        choices=("bytetrack", "botsort"),
        default="bytetrack",
        help="Backend de tracking. BoT-SORT é experimental e usa o YAML de ReID.",
    )
    parser.add_argument(
        "--botsort-config",
        type=Path,
        default=base_dir / "configs" / "botsort_sparse_unity.yaml",
        help="YAML do BoT-SORT usado quando --tracker botsort.",
    )
    parser.add_argument(
        "--classes",
        default="2,3,5,7",
        help="IDs de classe YOLO aceitos, separados por vírgula. Use 0 para o modelo sintético de classe única.",
    )
    return parser.parse_args()


def parse_class_ids(raw_class_ids: str) -> list[int]:
    """Converte a seleção de classes da CLI em IDs YOLO válidos."""
    try:
        class_ids = [int(value.strip()) for value in raw_class_ids.split(",") if value.strip()]
    except ValueError as error:
        raise ValueError(f"IDs de classe inválidos: {raw_class_ids!r}") from error
    if not class_ids or any(class_id < 0 for class_id in class_ids):
        raise ValueError(f"Informe ao menos um ID de classe não negativo: {raw_class_ids!r}")
    return class_ids


def step_ids_for_camera(frames_root: Path, camera_id: str) -> set[int]:
    """Lê os IDs de step válidos de uma pasta de câmera."""
    step_ids: set[int] = set()
    for image_path in (frames_root / camera_id).glob("step_*.jpg"):
        try:
            step_ids.add(int(image_path.stem.removeprefix("step_")))
        except ValueError:
            continue
    return step_ids


def main() -> None:
    """Processa apenas steps presentes em todas as câmeras esperadas."""
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    camera_ids = tuple(camera_id.strip() for camera_id in args.camera_ids.split(",") if camera_id.strip())
    if not camera_ids:
        raise ValueError("--camera-ids precisa conter ao menos uma câmera.")
    if args.max_steps <= 0 or args.frame_step <= 0 or args.frame_rate <= 0 or args.image_size <= 0:
        raise ValueError("--max-steps, --frame-step, --frame-rate e --image-size devem ser positivos.")
    if args.tracker == "botsort" and not args.botsort_config.is_file():
        raise ValueError(f"YAML BoT-SORT não encontrado: {args.botsort_config}")

    calibrations = {
        camera_id: load_camera_calibration(
            args.calibration_dir / f"{camera_id}-calibration.json",
            expected_camera_id=camera_id,
        )
        for camera_id in camera_ids
    }
    common_step_ids = set.intersection(*(step_ids_for_camera(args.frames_root, camera_id) for camera_id in camera_ids))
    selected_step_ids = sorted(common_step_ids)[: args.max_steps : args.frame_step]
    if not selected_step_ids:
        raise ValueError("Nenhum step completo foi encontrado para as câmeras selecionadas.")

    detector = YoloVehicleDetector(
        model_path=args.model,
        confidence_threshold=args.confidence,
        classes=parse_class_ids(args.classes),
        inference_size=args.image_size,
        nms_iou_threshold=args.nms_iou,
    )
    trackers = {
        camera_id: ByteTrackVehicleTracker(
            frame_rate=args.frame_rate,
            confidence_threshold=args.confidence,
            matching_threshold=args.track_match_threshold,
        )
        for camera_id in camera_ids
    } if args.tracker == "bytetrack" else {}
    estimators = {camera_id: QueueEstimator() for camera_id in camera_ids}
    debuggers = {camera_id: VisualDebugger(str(args.output_dir / camera_id)) for camera_id in camera_ids}
    summaries: list[dict[str, object]] = []

    for step_id in selected_step_ids:
        cameras_summary: dict[str, object] = {}
        for camera_id in camera_ids:
            image_path = args.frames_root / camera_id / f"step_{step_id:06d}.jpg"
            frame = cv2.imread(str(image_path))
            if frame is None:
                raise ValueError(f"Não foi possível ler {image_path}.")

            calibration = calibrations[camera_id]
            all_rois = calibration.pixel_rois(frame.shape[1], frame.shape[0])
            lane_rois = calibration.lane_pixel_rois(frame.shape[1], frame.shape[0])
            inference_started = perf_counter()
            if args.tracker == "botsort":
                detections, tracks = detector.track_with_botsort(frame, args.botsort_config)
            else:
                detections = detector.detect(frame)
                tracks = trackers[camera_id].update(detections)
            detections = filter_detections_to_roi(detections, all_rois["approach"])
            tracks = filter_detections_to_roi(tracks, all_rois["approach"])
            inference_ms = round((perf_counter() - inference_started) * 1000.0, 2)
            counting_objects, count_source = select_counting_objects(detections, tracks)
            raw_counts = ROICounter(lane_rois).count(counting_objects)
            queue_counts = estimators[camera_id].update(raw_counts)
            annotated = debuggers[camera_id].annotate(
                frame=frame,
                detections=detections,
                tracks=tracks,
                roi_counts=raw_counts,
                rois=all_rois,
                queue_counts=queue_counts,
                metadata={
                    "camera": camera_id,
                    "step": step_id,
                    "detections": len(detections),
                    "tracker": "ByteTrack" if args.tracker == "bytetrack" else "BoT-SORT/ReID",
                    "count_source": count_source,
                    "inference_ms": inference_ms,
                },
            )
            debug_path = debuggers[camera_id].save_frame(annotated, f"step_{step_id:06d}.jpg")
            cameras_summary[camera_id] = {
                "detections": len(detections),
                "tracks": len(tracks),
                "tracker": args.tracker,
                "count_source": count_source,
                "lane_counts": raw_counts,
                "queue_counts": queue_counts,
                "inference_ms": inference_ms,
                "debug_frame": str(debug_path),
            }
        summaries.append({"step_id": step_id, "cameras": cameras_summary})
        print(f"vision_step_complete step_id={step_id} cameras={','.join(camera_ids)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "summary.jsonl"
    summary_path.write_text("".join(json.dumps(summary) + "\n" for summary in summaries), encoding="utf-8")
    print(f"vision_complete steps={len(summaries)} output={args.output_dir} summary={summary_path}")


if __name__ == "__main__":
    main()
