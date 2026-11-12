"""Projeção entre a imagem de uma câmera da Unity e o plano da via (coordenadas SUMO).

Usa a pose e o campo de visão exportados na calibração da câmera. Serve para
medir e estender as ROIs de faixa (``experiments.data.check_lane_geometry`` e
``extend_lane_rois``).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def camera_rotation(euler_degrees: dict[str, float]) -> np.ndarray:
    """Matriz de rotação da Unity (Quaternion.Euler aplica Z, depois X, depois Y)."""
    x, y, z = (math.radians(float(euler_degrees[axis])) for axis in ("x", "y", "z"))
    rotation_x = np.array([[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]])
    rotation_y = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rotation_z = np.array([[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]])
    return rotation_y @ rotation_x @ rotation_z


def image_point_to_ground(pose: dict[str, Any], aspect: float, u: float, v: float) -> tuple[float, float]:
    """Projeta (u, v) normalizados, origem no topo, no plano y=0; retorna (x, y) SUMO."""
    tan_half = math.tan(math.radians(float(pose["fieldOfView"])) / 2.0)
    direction_camera = np.array([(2.0 * u - 1.0) * tan_half * aspect, (1.0 - 2.0 * v) * tan_half, 1.0])
    direction = camera_rotation(pose["rotationEulerDegrees"]) @ direction_camera
    origin = np.array([pose["position"][axis] for axis in ("x", "y", "z")], dtype=float)
    if direction[1] >= 0:
        raise ValueError(f"O ponto ({u:.3f}, {v:.3f}) não intercepta o solo.")
    ground = origin + direction * (-origin[1] / direction[1])
    # Unity x = SUMO x e Unity z = SUMO y (netOffset 0,0; ver state_extractor).
    return float(ground[0]), float(ground[2])


def ground_to_image_point(pose: dict[str, Any], aspect: float, x: float, y: float) -> tuple[float, float]:
    """Inverso de ``image_point_to_ground``: (x, y) SUMO no chão -> (u, v) normalizados."""
    origin = np.array([pose["position"][axis] for axis in ("x", "y", "z")], dtype=float)
    camera = camera_rotation(pose["rotationEulerDegrees"]).T @ (np.array([x, 0.0, y]) - origin)
    if camera[2] <= 0:
        raise ValueError(f"O ponto ({x:.2f}, {y:.2f}) está atrás da câmera.")
    tan_half = math.tan(math.radians(float(pose["fieldOfView"])) / 2.0)
    return (
        float((camera[0] / camera[2] / (tan_half * aspect) + 1.0) / 2.0),
        float((1.0 - camera[1] / camera[2] / tan_half) / 2.0),
    )
