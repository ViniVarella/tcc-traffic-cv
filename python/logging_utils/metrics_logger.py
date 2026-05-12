"""Registro estruturado de metricas e eventos por passo de simulacao."""

from __future__ import annotations

from typing import Any


class MetricsLogger:
    """Persiste metricas de visao, controle, latencia e ground truth por passo."""

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir

    def log_step(self, step: int, sim_time: float, **payload: Any) -> None:
        """Registra os dados consolidados de um passo da simulacao."""
        _ = (step, sim_time, payload)

    def close(self) -> None:
        """Finaliza a escrita de logs e libera recursos associados."""
