"""Caminhos do repositório, independentes da pasta de onde o comando é rodado.

Scripts e testes devem montar caminhos a partir destas constantes, nunca de
``Path(__file__).parents[n]``: assim um módulo pode mudar de pasta sem quebrar.
"""

from __future__ import annotations

from pathlib import Path

PYTHON_DIR = Path(__file__).resolve().parent
REPO_DIR = PYTHON_DIR.parent

CONFIGS_DIR = PYTHON_DIR / "configs"
SP_CONFIG = CONFIGS_DIR / "sp.yaml"
GENERIC_CONFIG = CONFIGS_DIR / "generic.yaml"

SUMO_DIR = REPO_DIR / "sumo"
SP_NETWORK_DIR = SUMO_DIR / "sp"
GENERIC_NETWORK_DIR = SUMO_DIR / "generic"

RESULTS_DIR = REPO_DIR / "results"
MODELS_DIR = RESULTS_DIR / "models"
EVALUATION_DIR = RESULTS_DIR / "evaluation"
LOGS_DIR = RESULTS_DIR / "logs"

CALIBRATION_DIR = REPO_DIR / "unity" / "TraffIQ-TCC" / "Assets" / "Calibration"
YOLO_RUNS_DIR = REPO_DIR / "runs" / "results" / "models"
DEFAULT_YOLO_MODEL = YOLO_RUNS_DIR / "yolov8n-unity-cam60-2cls-960" / "weights" / "best.pt"
