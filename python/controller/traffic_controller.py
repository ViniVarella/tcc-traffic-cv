"""Orquestracao de decisoes semaforicas baseadas em contagens visuais."""

from __future__ import annotations

from typing import Any


class TrafficController:
    """Decide acoes semaforicas a partir de contagens visuais agregadas.

    A primeira versao da politica considera dois grupos de fluxo: NS
    (`north + south`) e EW (`east + west`). O controlador definitivo ainda nao
    foi implementado, mas a documentacao alvo ja assume verde minimo, verde
    maximo, amarelo, all-red e transicoes seguras entre os dois grupos.
    """

    def __init__(self, tls_id: str, config: dict[str, Any]) -> None:
        self.tls_id = tls_id
        self.config = config

    def update(self, sim_time: float, visual_counts: dict[str, int]) -> dict[str, Any]:
        """Calcula uma decisao de controle semaforico para o passo atual.

        A logica planejada e:
        - manter a fase ate cumprir verde minimo;
        - trocar obrigatoriamente ao atingir verde maximo;
        - apos o verde minimo, trocar se a demanda atual estiver baixa e a
          demanda oposta existir;
        - trocar se a demanda oposta superar a atual pela margem configurada;
        - caso contrario, manter a fase atual.
        """
        return {
            "tls_id": self.tls_id,
            "sim_time": sim_time,
            "visual_counts": visual_counts,
            "action": "hold",
        }

    def apply(self, sumo_client: Any, decision: dict[str, Any]) -> None:
        """Aplica a decisao ao cliente SUMO quando a logica estiver implementada."""
        _ = (sumo_client, decision)
