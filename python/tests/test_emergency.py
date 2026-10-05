"""Testes da agenda de viaturas, do aviso V2I e das métricas de emergência."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from sumo.emergency import EmergencySettings, EmergencyTraffic, build_schedule


CONFIG = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs" / "sp.yaml").read_text(encoding="utf-8"))
EDGES = {"south": "E3", "east": "E2", "west": "E6"}


class FakeClient:
    """Simula uma viatura que percorre 70 m da aproximação a 10 m/s e cruza a linha."""

    def __init__(self, insert_delay_steps: int = 0, stop_steps: int = 0) -> None:
        self.added: list[str] = []
        self.states: dict[str, list[dict | None]] = {}
        self.insert_delay_steps = insert_delay_steps
        self.stop_steps = stop_steps

    def ensure_vehicle_type(self, *args) -> None:
        self.type_args = args

    def add_vehicle(self, vehicle_id: str, from_edge: str, to_edge: str, type_id: str) -> None:
        self.added.append(vehicle_id)
        road = from_edge
        states: list[dict | None] = [None] * self.insert_delay_steps
        position = 0.0
        for _ in range(self.stop_steps):
            states.append({"road_id": road, "lane_length": 70.0, "lane_position": 60.0, "speed": 0.0, "time_loss": 5.0, "waiting_time": 3.0})
        while position < 70.0:
            states.append({"road_id": road, "lane_length": 70.0, "lane_position": position, "speed": 10.0, "time_loss": 5.0, "waiting_time": 3.0})
            position += 10.0
        states.append({"road_id": ":junction_0", "lane_length": 0.0, "lane_position": 0.0, "speed": 10.0, "time_loss": 6.0, "waiting_time": 3.0})
        states.append(None)
        self.states[vehicle_id] = states

    def get_vehicle_road_state(self, vehicle_id: str):
        states = self.states[vehicle_id]
        return states.pop(0) if len(states) > 1 else states[0]


class ScheduleTests(unittest.TestCase):
    def test_schedule_is_reproducible_and_covers_every_approach(self) -> None:
        settings = EmergencySettings.from_config(CONFIG)
        first = build_schedule(settings, seed=201, start_s=300, end_s=2100)
        self.assertEqual(first, build_schedule(settings, seed=201, start_s=300, end_s=2100))
        self.assertNotEqual(first, build_schedule(settings, seed=202, start_s=300, end_s=2100))
        self.assertEqual(len(first), 10)
        self.assertEqual({item.approach for item in first[:3]}, {"south", "east", "west"})
        self.assertTrue(all(300 <= item.depart_s < 2100 for item in first))

    def test_invalid_settings_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EmergencySettings(interval_s=60, jitter_s=60)


class EmergencyTrafficTests(unittest.TestCase):
    def _traffic(self) -> EmergencyTraffic:
        settings = EmergencySettings(interval_s=500, jitter_s=0, first_after_s=20, announce_before_s=5)
        return EmergencyTraffic(settings, EDGES, seed=1, start_s=0, end_s=100)

    def test_v2i_announces_before_insertion_then_reports_eta_until_the_stop_line(self) -> None:
        traffic, client = self._traffic(), FakeClient()
        requests = {time: traffic.step(client, float(time)) for time in range(10, 40)}
        self.assertEqual(requests[14], [])
        self.assertEqual(len(requests[15]), 1)  # anunciada 5 s antes de entrar
        self.assertAlmostEqual(requests[15][0].eta_s, 5 + 75 / 13.89)
        self.assertEqual(client.added, ["emergency_0"])
        self.assertAlmostEqual(requests[21][0].eta_s, 7.0)  # 70 m restantes a 10 m/s
        crossing = min(time for time, items in requests.items() if time > 21 and not items)
        self.assertEqual(crossing, 28)
        summary = traffic.summary()
        self.assertEqual((summary["crossed_stop_line"], summary["mean_stops"], summary["share_without_stops"]), (1, 0.0, 1.0))
        self.assertEqual(summary["mean_time_loss_at_crossing_s"], 6.0)

    def test_blocked_insertion_keeps_requesting_and_stops_are_counted(self) -> None:
        traffic, client = self._traffic(), FakeClient(insert_delay_steps=3, stop_steps=2)
        requests = {time: traffic.step(client, float(time)) for time in range(15, 45)}
        self.assertTrue(all(requests[time] for time in range(21, 24)))  # ainda fora da rede
        summary = traffic.summary()
        self.assertEqual((summary["crossed_stop_line"], summary["mean_stops"]), (1, 1.0))


if __name__ == "__main__":
    unittest.main()
