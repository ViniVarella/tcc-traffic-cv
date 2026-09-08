"""Converte capturas Unity e seus metadados em um dataset YOLO de uma classe."""

from __future__ import annotations

import argparse
import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    train: float = 0.8
    val: float = 0.1
    test: float = 0.1

    def validate(self) -> None:
        if min(self.train, self.val, self.test) <= 0:
            raise ValueError("As frações train/val/test precisam ser positivas.")
        if abs((self.train + self.val + self.test) - 1.0) > 1e-6:
            raise ValueError("As frações train/val/test precisam somar 1.0.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monta um dataset YOLO a partir de capturas Unity rotuladas.")
    parser.add_argument("--frames-root", type=Path, required=True, help="Raiz com south/east/west e JPEGs capturados.")
    parser.add_argument("--labels-root", type=Path, required=True, help="Raiz com os JSONs por câmera gerados no capture.")
    parser.add_argument(
        "--masks-root",
        type=Path,
        help="Raiz opcional com as máscaras PNG por câmera. Quando informada, produz caixas a partir dos pixels visíveis.",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Diretório novo que receberá images/, labels/ e data.yaml.")
    parser.add_argument("--seed", type=int, default=42, help="Semente do particionamento reprodutível.")
    parser.add_argument("--train", type=float, default=0.8)
    parser.add_argument("--val", type=float, default=0.1)
    parser.add_argument("--test", type=float, default=0.1)
    return parser.parse_args()


def yolo_line(vehicle: dict[str, object]) -> str:
    class_id = int(vehicle["class_id"])
    values = [float(vehicle[key]) for key in ("center_x", "center_y", "width", "height")]
    if class_id != 0 or not all(0.0 <= value <= 1.0 for value in values):
        raise ValueError(f"Rótulo inválido para o dataset YOLO: {vehicle!r}")
    return f"{class_id} " + " ".join(f"{value:.6f}" for value in values)


def mask_yolo_lines(mask_path: Path, vehicles: list[dict[str, object]]) -> list[str]:
    """Converte cores de instância visíveis em caixas YOLO normalizadas.

    Veículos totalmente ocultos não têm pixels na máscara e, corretamente, não
    recebem rótulo de treino naquela imagem.
    """
    pixels = np.asarray(Image.open(mask_path).convert("RGB"))
    image_height, image_width = pixels.shape[:2]
    lines: list[str] = []

    for vehicle in vehicles:
        if int(vehicle["class_id"]) != 0:
            raise ValueError(f"Classe inválida para o dataset YOLO: {vehicle!r}")
        try:
            color = np.array(
                [int(vehicle["color_r"]), int(vehicle["color_g"]), int(vehicle["color_b"])], dtype=np.uint8
            )
        except KeyError as error:
            raise ValueError(f"Metadado sem cor de instância em {mask_path}: {vehicle!r}") from error

        rows, columns = np.where(np.all(pixels == color, axis=2))
        if rows.size == 0:
            continue

        left, right = int(columns.min()), int(columns.max())
        top, bottom = int(rows.min()), int(rows.max())
        width, height = right - left + 1, bottom - top + 1
        center_x = (left + right + 1) / (2.0 * image_width)
        center_y = (top + bottom + 1) / (2.0 * image_height)
        lines.append(f"0 {center_x:.6f} {center_y:.6f} {width / image_width:.6f} {height / image_height:.6f}")
    return lines


def choose_split(randomizer: random.Random, split: DatasetSplit) -> str:
    value = randomizer.random()
    if value < split.train:
        return "train"
    if value < split.train + split.val:
        return "val"
    return "test"


def build_dataset(
    frames_root: Path,
    labels_root: Path,
    output_dir: Path,
    split: DatasetSplit,
    seed: int,
    masks_root: Path | None = None,
) -> dict[str, int]:
    split.validate()
    if output_dir.exists():
        raise FileExistsError(f"A saída já existe; escolha um diretório novo: {output_dir}")

    pairs: list[tuple[str, Path, Path]] = []
    for camera_dir in sorted(path for path in frames_root.iterdir() if path.is_dir()):
        labels_dir = labels_root / camera_dir.name
        for frame_path in sorted(camera_dir.glob("*.jpg")):
            label_path = labels_dir / f"{frame_path.stem}.json"
            if not label_path.is_file():
                raise FileNotFoundError(f"Rótulo ausente para {frame_path}: {label_path}")
            pairs.append((camera_dir.name, frame_path, label_path))
    if not pairs:
        raise ValueError("Nenhum par JPEG/JSON foi encontrado.")

    output_dir.mkdir(parents=True)
    for split_name in ("train", "val", "test"):
        (output_dir / "images" / split_name).mkdir(parents=True)
        (output_dir / "labels" / split_name).mkdir(parents=True)

    randomizer = random.Random(seed)
    counts = {"train": 0, "val": 0, "test": 0, "vehicles": 0}
    for camera_id, frame_path, metadata_path in pairs:
        split_name = choose_split(randomizer, split)
        stem = f"{camera_id}_{frame_path.stem}"
        image_destination = output_dir / "images" / split_name / f"{stem}.jpg"
        label_destination = output_dir / "labels" / split_name / f"{stem}.txt"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        vehicles = metadata.get("vehicles", [])
        if not isinstance(vehicles, list):
            raise ValueError(f"Campo vehicles inválido em {metadata_path}")
        if masks_root is None:
            label_lines = [yolo_line(vehicle) for vehicle in vehicles]
        else:
            mask_path = masks_root / camera_id / f"{frame_path.stem}.png"
            if not mask_path.is_file():
                raise FileNotFoundError(f"Máscara ausente para {frame_path}: {mask_path}")
            label_lines = mask_yolo_lines(mask_path, vehicles)
        label_destination.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")
        shutil.copy2(frame_path, image_destination)
        counts[split_name] += 1
        counts["vehicles"] += len(label_lines)

    (output_dir / "data.yaml").write_text(
        f"path: {output_dir.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\n\nnames:\n  0: vehicle\n",
        encoding="utf-8",
    )
    return counts


def main() -> None:
    args = parse_args()
    counts = build_dataset(
        frames_root=args.frames_root.resolve(),
        labels_root=args.labels_root.resolve(),
        output_dir=args.output_dir.resolve(),
        split=DatasetSplit(train=args.train, val=args.val, test=args.test),
        seed=args.seed,
        masks_root=args.masks_root.resolve() if args.masks_root else None,
    )
    print("dataset_complete " + " ".join(f"{key}={value}" for key, value in counts.items()) + f" output={args.output_dir}")


if __name__ == "__main__":
    main()
