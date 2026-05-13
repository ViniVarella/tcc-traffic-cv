"""Teste local preliminar da pipeline de visao, sem SUMO e sem Unity.

Este script continua existindo como validacao tecnica isolada. Ele usa um
video ou imagem local, tipicamente top-down, apenas para confirmar a pipeline
YOLO + SORT + ROI antes da integracao com a arquitetura final de quatro
cameras da Unity.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2
import yaml

from vision import QueueEstimator, ROICounter, VehicleTracker, VisualDebugger, YoloVehicleDetector


VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def load_project_config(config_path: Path) -> dict[str, Any]:
    """Carrega o arquivo de configuracao YAML do projeto."""
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def build_default_rois(frame_width: int, frame_height: int) -> dict[str, list[list[int]]]:
    """Cria quatro ROIs simples para um video top-down de teste preliminar."""
    center_x = frame_width // 2
    center_y = frame_height // 2
    margin_x = max(frame_width // 12, 20)
    margin_y = max(frame_height // 12, 20)

    return {
        "north": [[margin_x, margin_y], [frame_width - margin_x, margin_y], [frame_width - margin_x, center_y], [margin_x, center_y]],
        "south": [[margin_x, center_y], [frame_width - margin_x, center_y], [frame_width - margin_x, frame_height - margin_y], [margin_x, frame_height - margin_y]],
        "east": [[center_x, margin_y], [frame_width - margin_x, margin_y], [frame_width - margin_x, frame_height - margin_y], [center_x, frame_height - margin_y]],
        "west": [[margin_x, margin_y], [center_x, margin_y], [center_x, frame_height - margin_y], [margin_x, frame_height - margin_y]],
    }


def resolve_rois(config: dict[str, Any], frame_width: int, frame_height: int) -> dict[str, list[list[int | float]]]:
    """Resolve ROIs a partir da configuracao final por camera ou de um fallback.

    A arquitetura alvo define as ROIs em `cameras.<camera_id>.roi`. Durante o
    teste preliminar com um unico video local, o script reutiliza essas ROIs
    como compatibilidade temporaria; se elas nao existirem, gera poligonos
    simples diretamente a partir do frame.
    """
    cameras = config.get("cameras", {})
    if isinstance(cameras, dict) and cameras:
        rois: dict[str, list[list[int | float]]] = {}
        for camera_id, camera_config in cameras.items():
            if not camera_config.get("enabled", False):
                continue
            roi = camera_config.get("roi")
            if roi:
                rois[camera_id] = roi
        if rois:
            return rois

    legacy_rois = config.get("rois")
    if isinstance(legacy_rois, dict) and legacy_rois:
        return legacy_rois
    return build_default_rois(frame_width=frame_width, frame_height=frame_height)


def parse_args() -> argparse.Namespace:
    """Define a interface de linha de comando do teste de visao."""
    parser = argparse.ArgumentParser(description="Valida a pipeline de visao do projeto com imagem ou video local.")
    parser.add_argument("--input", required=True, help="Caminho para imagem ou video local.")
    parser.add_argument("--model", default="yolov8n.pt", help="Caminho do modelo YOLO .pt.")
    parser.add_argument("--config", default="config.yaml", help="Arquivo de configuracao YAML do projeto.")
    parser.add_argument("--max-frames", type=int, default=30, help="Numero maximo de frames de video para processar.")
    parser.add_argument("--frame-step", type=int, default=5, help="Processa um frame a cada N frames no video.")
    parser.add_argument("--output-dir", default="../results/frames", help="Diretorio para salvar frames de debug.")
    return parser.parse_args()


def process_frame(
    frame: Any,
    frame_label: str,
    detector: YoloVehicleDetector,
    tracker: VehicleTracker,
    roi_counter: ROICounter,
    queue_estimator: QueueEstimator,
    debugger: VisualDebugger,
    rois: dict[str, list[list[int | float]]],
) -> Path:
    """Executa detector, tracker, contagem e escrita de frame de debug."""
    inference_start = perf_counter()
    detections = detector.detect(frame)
    inference_ms = round((perf_counter() - inference_start) * 1000.0, 2)

    tracks = tracker.update(detections)
    roi_counts = roi_counter.count(tracks)
    queue_counts = queue_estimator.update(roi_counts)

    annotated_frame = debugger.annotate(
        frame=frame,
        detections=detections,
        tracks=tracks,
        roi_counts=roi_counts,
        rois=rois,
        queue_counts=queue_counts,
        metadata={
            "frame": frame_label,
            "detections": len(detections),
            "tracks": len(tracks),
            "inference_ms": inference_ms,
        },
    )
    return debugger.save_frame(annotated_frame, f"{frame_label}.jpg")


def process_image(
    input_path: Path,
    detector: YoloVehicleDetector,
    tracker: VehicleTracker,
    queue_estimator: QueueEstimator,
    debugger: VisualDebugger,
    config: dict[str, Any],
) -> None:
    """Processa uma imagem unica."""
    frame = cv2.imread(str(input_path))
    if frame is None:
        raise ValueError(f"Nao foi possivel ler a imagem: {input_path}")

    rois = resolve_rois(config=config, frame_width=frame.shape[1], frame_height=frame.shape[0])
    roi_counter = ROICounter(rois)
    output_path = process_frame(
        frame=frame,
        frame_label=f"{input_path.stem}_debug",
        detector=detector,
        tracker=tracker,
        roi_counter=roi_counter,
        queue_estimator=queue_estimator,
        debugger=debugger,
        rois=rois,
    )
    print(f"Imagem processada. Debug salvo em: {output_path}")


def process_video(
    input_path: Path,
    detector: YoloVehicleDetector,
    tracker: VehicleTracker,
    queue_estimator: QueueEstimator,
    debugger: VisualDebugger,
    config: dict[str, Any],
    max_frames: int,
    frame_step: int,
) -> None:
    """Processa alguns frames de um video local e salva imagens de debug."""
    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise ValueError(f"Nao foi possivel abrir o video: {input_path}")

    try:
        frame_index = 0
        saved_frames = 0
        rois: dict[str, list[list[int | float]]] | None = None
        roi_counter: ROICounter | None = None

        while saved_frames < max_frames:
            success, frame = capture.read()
            if not success:
                break

            if frame_index % max(frame_step, 1) != 0:
                frame_index += 1
                continue

            if rois is None:
                rois = resolve_rois(config=config, frame_width=frame.shape[1], frame_height=frame.shape[0])
                roi_counter = ROICounter(rois)

            assert roi_counter is not None
            output_path = process_frame(
                frame=frame,
                frame_label=f"{input_path.stem}_frame_{frame_index:06d}",
                detector=detector,
                tracker=tracker,
                roi_counter=roi_counter,
                queue_estimator=queue_estimator,
                debugger=debugger,
                rois=rois,
            )
            saved_frames += 1
            frame_index += 1
            print(f"Frame salvo: {output_path}")
    finally:
        capture.release()

    print(f"Video processado. Frames salvos: {saved_frames}")


def main() -> None:
    """Executa o teste de visao local com imagem ou video.

    O objetivo aqui e validar a camada de visao em isolamento. Isso nao substitui
    a etapa futura de validar cedo o YOLO em frames reais renderizados pela
    Unity.
    """
    args = parse_args()
    input_path = Path(args.input).resolve()
    config_path = Path(args.config).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input nao encontrado: {input_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"Config nao encontrada: {config_path}")

    config = load_project_config(config_path)
    vision_config = config.get("vision", {})
    logging_config = config.get("logging", {})
    output_dir = Path(args.output_dir).resolve()
    if args.output_dir == "../results/frames" and logging_config.get("debug_frame_dir"):
        output_dir = (config_path.parent / logging_config["debug_frame_dir"]).resolve()

    detector = YoloVehicleDetector(
        model_path=args.model if args.model != "yolov8n.pt" else vision_config.get("model_path", "yolov8n.pt"),
        confidence_threshold=float(vision_config.get("confidence_threshold", 0.35)),
        classes=vision_config.get("classes"),
        inference_size=int(vision_config.get("inference_size", 640)),
    )
    tracker = VehicleTracker()
    queue_estimator = QueueEstimator(smoothing_window=int(vision_config.get("smoothing_window", 5)))
    debugger = VisualDebugger(output_dir=str(output_dir))

    suffix = input_path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        process_image(input_path, detector, tracker, queue_estimator, debugger, config)
        return
    if suffix in VIDEO_EXTENSIONS:
        process_video(input_path, detector, tracker, queue_estimator, debugger, config, args.max_frames, args.frame_step)
        return

    raise ValueError(f"Formato nao suportado para teste de visao: {input_path.suffix}")


if __name__ == "__main__":
    main()
