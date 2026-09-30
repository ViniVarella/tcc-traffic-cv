"""Geometria métrica por faixa: homografia da ROI da imagem para o plano da via."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np


Point = tuple[float, float]


def order_lane_quad(points: Sequence[Sequence[float]]) -> tuple[Point, Point, Point, Point]:
    """Ordena a ROI como (perto-esq., perto-dir., longe-dir., longe-esq.).

    Os JSONs de calibração não mantêm uma ordem fixa dos pontos. As arestas
    transversais à faixa são o par de arestas opostas cujos pontos médios mais
    se afastam na vertical; a mais baixa na imagem (maior y, origem no topo) é a
    da linha de retenção, pois as três câmeras olham para o tráfego que chega.
    """
    quad = np.asarray(points, dtype=float)
    if quad.shape != (4, 2):
        raise ValueError("A ROI da faixa precisa de exatamente quatro pontos (x, y).")
    if abs(_signed_area(quad)) < 1e-9:
        raise ValueError("ROI da faixa degenerada (área nula).")

    def mean_y(start: int) -> float:
        return float((quad[start, 1] + quad[(start + 1) % 4, 1]) / 2.0)

    # Arestas opostas: (0-1, 2-3) ou (1-2, 3-0). Escolhe o par transversal.
    first_pair_gap = abs(mean_y(0) - mean_y(2))
    second_pair_gap = abs(mean_y(1) - mean_y(3))
    starts = (0, 2) if first_pair_gap >= second_pair_gap else (1, 3)
    near = max(starts, key=mean_y)
    a, b = near, (near + 1) % 4
    # Cada ponto da borda próxima liga-se, pela lateral, ao vizinho fora dela.
    far_of_a, far_of_b = (near - 1) % 4, (near + 2) % 4
    if quad[a, 0] > quad[b, 0]:
        a, b, far_of_a, far_of_b = b, a, far_of_b, far_of_a
    return tuple(tuple(float(value) for value in quad[index]) for index in (a, b, far_of_b, far_of_a))  # type: ignore[return-value]


def bbox_ground_point(bbox: Sequence[float]) -> Point:
    """Centro da base da bbox xyxy: aproxima o contato do veículo com a via."""
    x1, _, x2, y2 = (float(value) for value in bbox)
    return ((x1 + x2) / 2.0, y2)


@dataclass(frozen=True, slots=True, eq=False)
class LaneHomography:
    """Mapeia pontos da imagem para (lateral_m, distância_m) na faixa.

    A distância é medida a partir da borda da linha de retenção e cresce a
    montante; a lateral vai de 0 (lado esquerdo na imagem) até a largura.
    """

    matrix: np.ndarray
    length_m: float
    width_m: float

    @classmethod
    def from_quad(cls, points: Sequence[Sequence[float]], length_m: float, width_m: float) -> "LaneHomography":
        if length_m <= 0 or width_m <= 0:
            raise ValueError("Comprimento e largura da faixa devem ser positivos.")
        source = np.asarray(order_lane_quad(points), dtype=np.float32)
        target = np.asarray([[0.0, 0.0], [width_m, 0.0], [width_m, length_m], [0.0, length_m]], dtype=np.float32)
        return cls(cv2.getPerspectiveTransform(source, target), float(length_m), float(width_m))

    def project(self, x: float, y: float) -> Point:
        """Projeta um ponto da imagem (mesmo sistema da ROI) no plano da faixa."""
        lateral, distance, scale = self.matrix @ np.asarray([x, y, 1.0])
        if abs(scale) < 1e-12:
            raise ValueError("Ponto no horizonte da homografia da faixa.")
        return (float(lateral / scale), float(distance / scale))

    def contains(self, lateral_m: float, distance_m: float) -> bool:
        """Indica se o ponto projetado está dentro do retângulo da faixa."""
        return 0.0 <= lateral_m <= self.width_m and 0.0 <= distance_m <= self.length_m


def _signed_area(quad: np.ndarray) -> float:
    x, y = quad[:, 0], quad[:, 1]
    return float(0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
