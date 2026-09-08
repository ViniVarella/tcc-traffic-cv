"""Testes unitarios do agrupamento de frames Unity por step."""

from __future__ import annotations

import unittest

from bridge import FrameBundleCollector, FramePacket


def make_packet(step_id: int, camera_id: str) -> FramePacket:
    return FramePacket(
        step_id=step_id,
        sim_time=float(step_id),
        camera_id=camera_id,
        image_format="jpeg",
        payload_size=3,
    )


class FrameBundleCollectorTests(unittest.TestCase):
    def test_collects_all_expected_cameras_for_one_step(self) -> None:
        collector = FrameBundleCollector({"south", "east", "west"})
        incoming = iter(
            [
                (b"e", make_packet(12, "east")),
                (b"s", make_packet(12, "south")),
                (b"w", make_packet(12, "west")),
            ]
        )

        bundle = collector.collect_for_step(12, lambda: next(incoming, None))

        self.assertTrue(bundle.is_complete)
        self.assertEqual(set(bundle.frames), {"south", "east", "west"})
        self.assertEqual(bundle.frames["east"].jpeg, b"e")

    def test_buffers_future_step_until_it_is_requested(self) -> None:
        collector = FrameBundleCollector({"south", "east"})
        incoming = iter(
            [
                (b"future-s", make_packet(6, "south")),
                (b"current-s", make_packet(5, "south")),
                (b"current-e", make_packet(5, "east")),
                (b"future-e", make_packet(6, "east")),
            ]
        )

        current = collector.collect_for_step(5, lambda: next(incoming, None))
        future = collector.collect_for_step(6, lambda: next(incoming, None))

        self.assertTrue(current.is_complete)
        self.assertTrue(future.is_complete)
        self.assertEqual(future.frames["south"].jpeg, b"future-s")

    def test_reports_missing_camera_after_timeout(self) -> None:
        collector = FrameBundleCollector({"south", "west"})
        incoming = iter([(b"s", make_packet(4, "south"))])

        bundle = collector.collect_for_step(4, lambda: next(incoming, None))

        self.assertFalse(bundle.is_complete)
        self.assertEqual(bundle.missing_camera_ids, ("west",))

    def test_discards_unexpected_duplicate_and_stale_frames(self) -> None:
        collector = FrameBundleCollector({"south"})
        self.assertFalse(collector.add_frame(b"n", make_packet(9, "north")))
        self.assertFalse(collector.add_frame(b"old", make_packet(8, "south"), minimum_step_id=9))
        self.assertTrue(collector.add_frame(b"first", make_packet(9, "south")))
        self.assertFalse(collector.add_frame(b"duplicate", make_packet(9, "south")))


if __name__ == "__main__":
    unittest.main()
