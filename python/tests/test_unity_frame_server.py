"""Teste do servidor TCP de frames com várias câmeras conectando ao mesmo tempo."""

from __future__ import annotations

import json
import socket
import threading
import unittest

from bridge import UnityBridge


def _send_frame(port: int, camera_id: str, barrier: threading.Barrier, errors: list[str]) -> None:
    jpeg = b"\xff\xd8fake-jpeg"
    header = json.dumps({"step_id": 7, "sim_time": 7.0, "camera_id": camera_id, "image_format": "jpeg",
                         "payload_size": len(jpeg), "mask_payload_size": 0}).encode()
    try:
        barrier.wait()
        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
            connection.sendall(len(header).to_bytes(4, "big") + header + jpeg)
    except OSError as error:  # ex.: Connection reset by peer com fila de conexões pequena
        errors.append(f"{camera_id}: {error}")


class FrameServerTests(unittest.TestCase):
    def test_nine_cameras_connecting_at_once_are_all_received(self) -> None:
        # Porta livre escolhida pelo sistema para não colidir com a Unity (5005).
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        bridge = UnityBridge(state_host="127.0.0.1", state_port=port + 1, frame_host="127.0.0.1", frame_port=port, timeout=5.0)
        bridge.start_frame_server()
        cameras = [f"camera_{index}" for index in range(9)]
        barrier = threading.Barrier(len(cameras))
        errors: list[str] = []
        threads = [threading.Thread(target=_send_frame, args=(port, camera, barrier, errors)) for camera in cameras]
        try:
            for thread in threads:
                thread.start()
            received = sorted(bridge.receive_frame()[1].camera_id for _ in cameras)
        finally:
            for thread in threads:
                thread.join(timeout=5)
            bridge.close()
        self.assertEqual(errors, [])
        self.assertEqual(received, cameras)


if __name__ == "__main__":
    unittest.main()
