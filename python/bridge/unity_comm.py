"""Abstracoes para envio de estado ao Unity e recepcao de frames."""

from __future__ import annotations

import socket
import json
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
        self._frame_server: socket.socket | None = None

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

    def start_frame_server(self) -> None:
        """Abre o listener TCP que recebe um frame por conexao da Unity."""
        if self._frame_server is not None:
            return

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.frame_host, self.frame_port))
        server.listen(4)
        server.settimeout(self.timeout)
        self._frame_server = server

    def receive_frame(self) -> tuple[bytes, FramePacket] | None:
        """Recebe e valida um JPEG Unity ou retorna ``None`` em timeout.

        O protocolo TCP contém, nesta ordem: tamanho do cabeçalho JSON em quatro
        bytes big-endian, cabeçalho JSON UTF-8 e payload JPEG. Cada conexão
        transporta exatamente um frame para simplificar a associação com step.
        """
        self.start_frame_server()
        assert self._frame_server is not None
        try:
            connection, _ = self._frame_server.accept()
        except socket.timeout:
            return None

        with connection:
            connection.settimeout(self.timeout)
            header_size = int.from_bytes(self._read_exact(connection, 4), byteorder="big", signed=False)
            if not 2 <= header_size <= 16_384:
                raise ValueError(f"Invalid Unity frame header size: {header_size}.")

            raw_header = json.loads(self._read_exact(connection, header_size).decode("utf-8"))
            packet = self.build_frame_packet(
                step_id=int(raw_header.get("step_id", -1)),
                sim_time=float(raw_header.get("sim_time", 0.0)),
                camera_id=str(raw_header.get("camera_id", "unknown")),
                image_format=str(raw_header.get("image_format", "jpeg")),
                payload_size=int(raw_header.get("payload_size", -1)),
            )
            if packet.image_format.lower() != "jpeg":
                raise ValueError(f"Unsupported Unity frame format: {packet.image_format}.")
            if not 1 <= packet.payload_size <= 20 * 1024 * 1024:
                raise ValueError(f"Invalid Unity frame payload size: {packet.payload_size}.")

            payload = self._read_exact(connection, packet.payload_size)
            return payload, packet

    def close(self) -> None:
        """Fecha recursos de rede associados a ponte com a Unity."""
        self._state_socket.close()
        if self._frame_server is not None:
            self._frame_server.close()
            self._frame_server = None

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

    @staticmethod
    def _read_exact(connection: socket.socket, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = connection.recv(remaining)
            if not chunk:
                raise ConnectionError("Unity closed the frame connection before the payload completed.")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
