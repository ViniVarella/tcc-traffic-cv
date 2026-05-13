"""Abstracoes para envio de estado ao Unity e recepcao de frames."""

from __future__ import annotations

from typing import Any

from .protocol import FramePacket


class UnityBridge:
    """Gerencia o contrato de troca entre o orquestrador Python e a Unity.

    A implementacao real de rede ainda nao foi feita, mas a arquitetura alvo ja
    esta definida: Python -> Unity envia estado por step; Unity -> Python envia
    frames completos por TCP, um por camera, identificados por `step_id` e
    `camera_id`. Timeouts de frame nao devem travar a simulacao inteira.
    """

    def __init__(
        self,
        state_host: str,
        state_port: int,
        frame_host: str,
        frame_port: int,
        timeout: float = 2.0,
    ) -> None:
        self.state_host = state_host
        self.state_port = state_port
        self.frame_host = frame_host
        self.frame_port = frame_port
        self.timeout = timeout

    def send_state(self, state: dict[str, Any]) -> None:
        """Envia para a Unity o estado serializado do step atual do SUMO."""
        _ = state

    def receive_frame(self) -> tuple[Any, int, float, float] | None:
        """Recebe um frame renderizado pela Unity ou retorna None em timeout.

        Quando a comunicacao real existir, o timeout deve gerar um evento de
        `missing_frame` por camera e a simulacao deve continuar usando a ultima
        contagem valida daquela camera.
        """
        return None

    def close(self) -> None:
        """Fecha recursos de rede associados a ponte com a Unity."""

    def build_frame_packet(
        self,
        step_id: int,
        sim_time: float,
        camera_id: str,
        payload_size: int,
        image_format: str = "jpeg",
    ) -> FramePacket:
        """Cria um pacote de metadados para um frame associado a uma camera."""
        return FramePacket(
            step_id=step_id,
            sim_time=sim_time,
            camera_id=camera_id,
            image_format=image_format,
            payload_size=payload_size,
        )
