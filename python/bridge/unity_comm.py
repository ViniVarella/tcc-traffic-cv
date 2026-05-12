"""Abstracoes para envio de estado ao Unity e recepcao de frames."""

from __future__ import annotations

from typing import Any

from .protocol import FramePacket


class UnityBridge:
    """Gerencia a troca de mensagens entre o orquestrador Python e a Unity."""

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
        """Envia o estado do SUMO para a Unity."""
        _ = state

    def receive_frame(self) -> tuple[Any, int, float, float] | None:
        """Recebe um frame renderizado pela Unity ou retorna None em timeout."""
        return None

    def close(self) -> None:
        """Fecha recursos de rede associados a ponte com a Unity."""

    def build_frame_packet(self, step_id: int, sim_time: float, payload_size: int) -> FramePacket:
        """Cria um pacote de metadados para um frame associado a um passo."""
        return FramePacket(step_id=step_id, sim_time=sim_time, payload_size=payload_size)
