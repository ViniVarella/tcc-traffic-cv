"""Avaliação do detector por classe e por faixa de distância na ROI.

Casa predições e rótulos por IoU sem olhar a classe (guloso, maior IoU
primeiro): assim um carro detectado como ambulância conta como confusão de
classe, não como uma perda mais um falso positivo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np


DISTANCE_BANDS_M: tuple[tuple[float, float], ...] = ((0.0, 20.0), (20.0, 40.0), (40.0, 60.0))
OUTSIDE_ROI = "fora_roi"
UNCALIBRATED = "sem_calibracao"


@dataclass(frozen=True, slots=True)
class Box:
    """Caixa xyxy em pixels com classe (e confiança, nas predições)."""

    xyxy: tuple[float, float, float, float]
    class_id: int
    confidence: float = 1.0


def box_iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return 0.0 if union <= 0 else inter / union


def match_boxes(truths: Sequence[Box], predictions: Sequence[Box], iou_threshold: float = 0.5) -> list[int | None]:
    """Para cada rótulo, o índice da predição casada (ou None)."""
    pairs = sorted(
        ((box_iou(truth.xyxy, prediction.xyxy), t, p) for t, truth in enumerate(truths) for p, prediction in enumerate(predictions)),
        reverse=True,
    )
    matched: list[int | None] = [None] * len(truths)
    used: set[int] = set()
    for iou, t, p in pairs:
        if iou < iou_threshold:
            break
        if matched[t] is None and p not in used:
            matched[t] = p
            used.add(p)
    return matched


def distance_band(distance_m: float | None, calibrated: bool) -> str:
    if not calibrated:
        return UNCALIBRATED
    if distance_m is None:
        return OUTSIDE_ROI
    for start, end in DISTANCE_BANDS_M:
        if start <= distance_m < end or (end == DISTANCE_BANDS_M[-1][1] and distance_m == end):
            return f"{start:.0f}-{end:.0f}m"
    return OUTSIDE_ROI


@dataclass(slots=True)
class DetectionTally:
    """Contagens por (classe verdadeira, faixa de distância)."""

    class_names: tuple[str, ...]
    # (classe, banda) -> [rótulos, achados com a classe certa, achados com outra classe]
    cells: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    false_positives: dict[str, int] = field(default_factory=dict)
    images: int = 0

    def add_image(self, truths: Sequence[Box], bands: Sequence[str], predictions: Sequence[Box], iou_threshold: float = 0.5) -> None:
        if len(truths) != len(bands):
            raise ValueError("Cada rótulo precisa de uma faixa de distância.")
        self.images += 1
        matched = match_boxes(truths, predictions, iou_threshold)
        for truth, band, index in zip(truths, bands, matched):
            cell = self.cells.setdefault((self.class_names[truth.class_id], band), [0, 0, 0])
            cell[0] += 1
            if index is not None:
                cell[1 if predictions[index].class_id == truth.class_id else 2] += 1
        for index in set(range(len(predictions))) - {i for i in matched if i is not None}:
            name = self.class_names[predictions[index].class_id]
            self.false_positives[name] = self.false_positives.get(name, 0) + 1

    def summary(self) -> dict[str, object]:
        def stats(rows: list[list[int]]) -> dict[str, float | int | None]:
            total, right, wrong = (int(np.sum([row[i] for row in rows])) for i in range(3))
            return {"labels": total, "recall": None if not total else right / total,
                    "detected_any_class": None if not total else (right + wrong) / total,
                    "confused_class": wrong, "confusion_rate": None if not total else wrong / total}

        bands = sorted({band for _, band in self.cells})
        result: dict[str, object] = {"images": self.images, "false_positives": dict(self.false_positives), "classes": {}}
        for name in self.class_names:
            rows = {band: self.cells[(name, band)] for band in bands if (name, band) in self.cells}
            result["classes"][name] = {"all": stats(list(rows.values())), "by_band": {band: stats([row]) for band, row in rows.items()}}
        return result
