"""Agrupamento de frames Unity por step da simulacao."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .protocol import FramePacket


ReceivedFrame = tuple[bytes, FramePacket]


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """Payload JPEG e metadados de uma unica camera Unity."""

    jpeg: bytes
    packet: FramePacket


@dataclass(frozen=True, slots=True)
class FrameBundle:
    """Frames esperados para um unico ``step_id`` do SUMO."""

    step_id: int
    expected_camera_ids: frozenset[str]
    frames: dict[str, CapturedFrame]

    @property
    def missing_camera_ids(self) -> tuple[str, ...]:
        """IDs de camera ainda ausentes, em ordem estavel."""
        return tuple(sorted(self.expected_camera_ids.difference(self.frames)))

    @property
    def is_complete(self) -> bool:
        """Indica se todas as cameras esperadas chegaram para o step."""
        return not self.missing_camera_ids


class FrameBundleCollector:
    """Agrupa JPEGs TCP por step sem perder frames que chegam adiantados.

    O coletor aceita apenas IDs de camera declarados pelo experimento. Frames
    de steps futuros ficam em buffer para a proxima chamada; frames atrasados,
    duplicados ou de cameras inesperadas sao descartados de forma segura.
    """

    def __init__(self, expected_camera_ids: set[str] | frozenset[str]) -> None:
        expected = frozenset(camera_id.strip() for camera_id in expected_camera_ids if camera_id.strip())
        if not expected:
            raise ValueError("FrameBundleCollector requer ao menos uma camera esperada.")

        self._expected_camera_ids = expected
        self._frames_by_step: dict[int, dict[str, CapturedFrame]] = {}

    @property
    def expected_camera_ids(self) -> frozenset[str]:
        """IDs de camera aceitos pelo coletor."""
        return self._expected_camera_ids

    def add_frame(self, jpeg: bytes, packet: FramePacket, minimum_step_id: int | None = None) -> bool:
        """Adiciona um frame aceito e retorna se ele entrou no buffer."""
        if packet.camera_id not in self._expected_camera_ids:
            return False
        if minimum_step_id is not None and packet.step_id < minimum_step_id:
            return False

        frames = self._frames_by_step.setdefault(packet.step_id, {})
        if packet.camera_id in frames:
            return False

        frames[packet.camera_id] = CapturedFrame(jpeg=jpeg, packet=packet)
        return True

    def collect_for_step(
        self,
        step_id: int,
        receive_frame: Callable[[], ReceivedFrame | None],
    ) -> FrameBundle:
        """Recebe ate completar o step alvo ou o callback indicar timeout."""
        self._discard_steps_before(step_id)
        while not self._is_complete(step_id):
            received = receive_frame()
            if received is None:
                break

            jpeg, packet = received
            self.add_frame(jpeg=jpeg, packet=packet, minimum_step_id=step_id)

        frames = self._frames_by_step.pop(step_id, {})
        return FrameBundle(
            step_id=step_id,
            expected_camera_ids=self._expected_camera_ids,
            frames=frames,
        )

    def _is_complete(self, step_id: int) -> bool:
        frames = self._frames_by_step.get(step_id, {})
        return self._expected_camera_ids.issubset(frames)

    def _discard_steps_before(self, step_id: int) -> None:
        for buffered_step_id in tuple(self._frames_by_step):
            if buffered_step_id < step_id:
                del self._frames_by_step[buffered_step_id]
