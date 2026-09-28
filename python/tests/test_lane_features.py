"""Testes do contrato de features por faixa e do rastreador cinemático."""

from __future__ import annotations

import unittest

from vision.lane_features import (
    ApproachKinematicsTracker,
    KinematicsParameters,
    LaneGeometry,
    LaneObservation,
    load_lane_geometries,
    occupancy_fraction,
)


def _tracker(**parameters) -> ApproachKinematicsTracker:
    return ApproachKinematicsTracker({"lane_0": 25.0, "lane_1": 25.0}, KinematicsParameters(**parameters))


def _run(tracker: ApproachKinematicsTracker, frames: list[list[LaneObservation]], start: float = 1.0) -> list[dict]:
    return [tracker.update(frame, start + index) for index, frame in enumerate(frames)]


class StoppedAndWaitingTests(unittest.TestCase):
    def test_stationary_vehicle_becomes_stopped_after_stop_time_and_accrues_waiting(self) -> None:
        frames = [[LaneObservation("lane_0", 10.0, "a")] for _ in range(5)]
        lanes = [result["lane_0"] for result in _run(_tracker(), frames)]
        # t=1: sem velocidade; t=2: v=0 (abaixo do limiar desde 2); t=3: parado há 1 s.
        self.assertEqual([lane.stopped_count for lane in lanes], [0, 0, 1, 1, 1])
        self.assertEqual([lane.waiting_time_s for lane in lanes], [0.0, 0.0, 1.0, 2.0, 3.0])
        self.assertEqual((lanes[0].unknown_speed_count, lanes[0].mean_speed_mps), (1, None))
        self.assertEqual(lanes[-1].mean_speed_mps, 0.0)

    def test_speed_is_estimated_towards_the_stop_line(self) -> None:
        frames = [[LaneObservation("lane_0", 24.0 - 10.0 * step, "a")] for step in range(3)]
        lane = _run(_tracker(), frames)[-1]["lane_0"]
        self.assertAlmostEqual(lane.mean_speed_mps, 10.0)
        self.assertEqual((lane.stopped_count, lane.waiting_time_s), (0, 0.0))

    def test_hysteresis_keeps_creeping_vehicle_stopped_and_moving_resets_waiting(self) -> None:
        distances = [20.0, 20.0, 20.0, 18.5, 17.0, 12.0]  # parado, avança 1,5 m/s (< 2), depois arranca
        frames = [[LaneObservation("lane_0", distance, "a")] for distance in distances]
        lanes = [result["lane_0"] for result in _run(_tracker(history_size=2), frames)]
        self.assertEqual([lane.stopped_count for lane in lanes], [0, 0, 1, 1, 1, 0])
        self.assertEqual(lanes[-1].waiting_time_s, 0.0)

    def test_missing_frame_uses_simulated_time_gap(self) -> None:
        tracker = _tracker()
        tracker.update([LaneObservation("lane_0", 20.0, "a")], 1.0)
        lane = tracker.update([LaneObservation("lane_0", 10.0, "a")], 3.0)["lane_0"]
        self.assertAlmostEqual(lane.mean_speed_mps, 5.0)


class OccupancyTests(unittest.TestCase):
    def test_union_of_vehicle_footprints_with_overlap_and_clipping(self) -> None:
        self.assertAlmostEqual(occupancy_fraction([0.0, 3.0], 5.0, 25.0), 8.0 / 25.0)
        self.assertAlmostEqual(occupancy_fraction([22.0], 5.0, 25.0), 3.0 / 25.0)
        # Frente 2 m além da linha de retenção: só [0, 3] m do corpo ficam na ROI.
        self.assertAlmostEqual(occupancy_fraction([-2.0], 5.0, 25.0), 3.0 / 25.0)
        self.assertEqual(occupancy_fraction([], 5.0, 25.0), 0.0)
        self.assertEqual(occupancy_fraction([0, 5, 10, 15, 20, 24], 5.0, 25.0), 1.0)

    def test_tracker_reports_occupancy_and_count_per_lane(self) -> None:
        result = _tracker().update([LaneObservation("lane_0", 0.0, "a"), LaneObservation("lane_1", 10.0, "b"), LaneObservation("lane_1", 20.0, "c")], 1.0)
        self.assertEqual((result["lane_0"].vehicle_count, result["lane_1"].vehicle_count), (1, 2))
        self.assertAlmostEqual(result["lane_1"].occupancy, 10.0 / 25.0)

    def test_empty_lane_has_no_speed(self) -> None:
        lane = _tracker().update([], 1.0)["lane_0"]
        self.assertEqual((lane.vehicle_count, lane.mean_speed_mps, lane.occupancy), (0, None, 0.0))


class TrackContinuityTests(unittest.TestCase):
    def test_lane_change_keeps_history(self) -> None:
        tracker = _tracker()
        tracker.update([LaneObservation("lane_0", 20.0, "a")], 1.0)
        result = tracker.update([LaneObservation("lane_1", 12.0, "a")], 2.0)
        self.assertEqual((result["lane_0"].vehicle_count, result["lane_1"].vehicle_count), (0, 1))
        self.assertAlmostEqual(result["lane_1"].mean_speed_mps, 8.0)

    def test_implausible_jump_resets_history(self) -> None:
        tracker = _tracker()
        tracker.update([LaneObservation("lane_0", 5.0, "a")], 1.0)
        lane = tracker.update([LaneObservation("lane_0", 20.0, "a")], 2.0)["lane_0"]  # 15 m para trás
        self.assertEqual((lane.mean_speed_mps, lane.unknown_speed_count), (None, 1))

    def test_occluded_stopped_vehicle_is_kept_as_ghost_until_ttl(self) -> None:
        tracker = _tracker(ghost_ttl_s=3.0)
        for time in (1.0, 2.0, 3.0):
            tracker.update([LaneObservation("lane_0", 15.0, "a")], time)
        counts = [tracker.update([], time)["lane_0"] for time in (4.0, 5.0, 6.0, 7.0)]
        self.assertEqual([lane.vehicle_count for lane in counts], [1, 1, 1, 0])
        self.assertEqual(counts[2].waiting_time_s, 4.0)  # continua acumulando enquanto fantasma

    def test_ghost_ttl_zero_drops_unseen_vehicles_immediately(self) -> None:
        tracker = _tracker(ghost_ttl_s=0.0)
        for time in (1.0, 2.0, 3.0):
            tracker.update([LaneObservation("lane_0", 15.0, "a")], time)
        self.assertEqual(tracker.update([], 4.0)["lane_0"].vehicle_count, 0)

    def test_stopped_vehicle_that_vanishes_at_the_stop_line_departed(self) -> None:
        tracker = _tracker(ghost_ttl_s=3.0)
        for time in (1.0, 2.0, 3.0):
            tracker.update([LaneObservation("lane_0", 1.0, "head")], time)
        self.assertEqual(tracker.update([], 4.0)["lane_0"].vehicle_count, 0)

    def test_new_track_next_to_stopped_ghost_inherits_waiting(self) -> None:
        tracker = _tracker()
        for time in (1.0, 2.0, 3.0, 4.0):
            tracker.update([LaneObservation("lane_0", 15.0, "7")], time)
        lane = tracker.update([LaneObservation("lane_0", 15.5, "9")], 5.0)["lane_0"]
        self.assertEqual((lane.vehicle_count, lane.stopped_count, lane.waiting_time_s), (1, 1, 3.0))

    def test_ghost_is_not_stolen_when_its_own_id_is_present(self) -> None:
        tracker = _tracker()
        for time in (1.0, 2.0, 3.0):
            tracker.update([LaneObservation("lane_0", 15.0, "7")], time)
        lane = tracker.update([LaneObservation("lane_0", 15.5, "9"), LaneObservation("lane_0", 15.0, "7")], 4.0)["lane_0"]
        self.assertEqual((lane.vehicle_count, lane.stopped_count), (2, 1))

    def test_untracked_detection_continues_nearest_known_object(self) -> None:
        tracker = _tracker()
        for time in (1.0, 2.0, 3.0):
            tracker.update([LaneObservation("lane_0", 15.0, "7")], time)
        lane = tracker.update([LaneObservation("lane_0", 15.3, None)], 4.0)["lane_0"]
        self.assertEqual((lane.vehicle_count, lane.stopped_count, lane.waiting_time_s), (1, 1, 2.0))

    def test_unmatched_untracked_detection_counts_with_unknown_speed(self) -> None:
        lane = _tracker().update([LaneObservation("lane_0", 12.0, None)], 1.0)["lane_0"]
        self.assertEqual((lane.vehicle_count, lane.unknown_speed_count, lane.stopped_count), (1, 1, 0))

    def test_observations_of_unknown_lanes_are_ignored_and_time_must_advance(self) -> None:
        tracker = _tracker()
        self.assertEqual(tracker.update([LaneObservation("lane_9", 3.0, "x")], 1.0)["lane_0"].vehicle_count, 0)
        with self.assertRaises(ValueError):
            tracker.update([], 1.0)
        tracker.reset()
        tracker.update([], 1.0)


class GeometryTests(unittest.TestCase):
    def test_capacity_uses_sumo_vehicle_footprint(self) -> None:
        geometry = LaneGeometry("east", "lane_0", "E2_0", 43.0, 68.5, 4.0)
        self.assertAlmostEqual(geometry.length_m, 25.5)
        self.assertAlmostEqual(geometry.capacity, 3.4)

    def test_load_from_profile(self) -> None:
        config = {"lane_geometry": {"west": {"lane_0": {"sumo_lane": "E6_0", "roi_start_m": 50.8, "roi_end_m": 74.0, "width_m": 3.2}}}}
        geometry = load_lane_geometries(config)[("west", "lane_0")]
        self.assertEqual((geometry.sumo_lane, geometry.width_m), ("E6_0", 3.2))
        with self.assertRaises(ValueError):
            LaneGeometry("west", "lane_0", "E6_0", 10.0, 5.0, 3.2)

    def test_parameters_validate_hysteresis(self) -> None:
        with self.assertRaises(ValueError):
            KinematicsParameters(stop_speed_mps=3.0, move_speed_mps=2.0)
        self.assertEqual(KinematicsParameters.from_config({"lane_state": {"kinematics": {"ghost_ttl_s": 0.0}}}).ghost_ttl_s, 0.0)


if __name__ == "__main__":
    unittest.main()
