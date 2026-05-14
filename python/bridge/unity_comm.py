"""Abstracoes para envio de estado ao Unity e recepcao de frames."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import yaml

from .protocol import FramePacket, SimulationState
from .serialization import serialize_state


class UnityBridge:
    """Gerencia o contrato de troca entre o orquestrador Python e a Unity.

    Nesta etapa, o lado Python envia estados fake ou reais por UDP para a
    Unity. O retorno de frames continua fora do escopo deste marco e sera
    implementado em etapa posterior.
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
        self._state_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._state_socket.settimeout(timeout)

    @classmethod
    def from_config_path(cls, config_path: str | Path) -> "UnityBridge":
        """Constroi a ponte usando os parametros de rede do config.yaml."""
        path = Path(config_path)
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.from_config(config)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "UnityBridge":
        """Constroi a ponte usando um dicionario de configuracao ja carregado."""
        unity_config = config.get("unity", {})
        return cls(
            state_host=str(unity_config["state_host"]),
            state_port=int(unity_config["state_port"]),
            frame_host=str(unity_config["frame_host"]),
            frame_port=int(unity_config["frame_port"]),
            timeout=float(unity_config.get("frame_timeout", 2.0)),
        )

    def send_state(self, state: SimulationState | dict[str, Any]) -> int:
        """Envia para a Unity o estado serializado do step atual do SUMO."""
        payload = serialize_state(state)
        return self._state_socket.sendto(payload, (self.state_host, self.state_port))

    def receive_frame(self) -> tuple[Any, int, float, str, float] | None:
        """Recebe um frame renderizado pela Unity ou retorna None em timeout.

        Quando a comunicacao real existir, o timeout deve gerar um evento de
        `missing_frame` por camera e a simulacao deve continuar usando a ultima
        contagem valida daquela camera.
        """
        return None

    def close(self) -> None:
        """Fecha recursos de rede associados a ponte com a Unity."""
        self._state_socket.close()

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
