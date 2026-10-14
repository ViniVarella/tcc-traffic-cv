"""Testes da mensagem de estado Python -> Unity (veículos, semáforo e pedestres)."""

from __future__ import annotations

import json
import unittest

from bridge import PedestrianState, SimulationState, VehicleState, serialize_state, serialize_state_datagrams
from sumo import SumoStateExtractor


VEHICLE = {"id": "f_1.0", "x": 50.0, "y": -20.0, "angle": 250.0, "speed": 8.0, "type": "DEFAULT_VEHTYPE"}
PEDESTRIAN = {"id": "p_0.3", "x": 12.5, "y": -18.0, "angle": 90.0, "speed": 1.2}


class StateMessageTests(unittest.TestCase):
    def test_pedestrians_use_the_vehicle_coordinate_conversion(self) -> None:
        state = SumoStateExtractor().build_simulation_state(
            step=7, sim_time=307.0, vehicles=[VEHICLE], traffic_light_state={"id": "tls", "phase": 5, "state": "r" * 10 + "G" * 4},
            pedestrians=[PEDESTRIAN],
        )
        self.assertEqual(state.pedestrians, [PedestrianState(id="p_0.3", x=12.5, y=0.0, z=-18.0, angle=90.0, speed=1.2)])
        payload = json.loads(serialize_state(state))
        self.assertEqual(payload["pedestrians"], [{"id": "p_0.3", "x": 12.5, "y": 0.0, "z": -18.0, "angle": 90.0, "speed": 1.2}])
        self.assertEqual(payload["vehicles"][0]["z"], -20.0)
        self.assertEqual(payload["step_id"], 7)

    def test_networks_without_pedestrians_send_an_empty_list(self) -> None:
        state = SumoStateExtractor().build_simulation_state(
            step=0, sim_time=0.0, vehicles=[], traffic_light_state={"id": "tls", "phase": 0, "state": "G" * 10},
        )
        self.assertEqual(state.pedestrians, [])
        self.assertEqual(json.loads(serialize_state(state))["pedestrians"], [])
        self.assertEqual(json.loads(serialize_state(SimulationState(step=1, sim_time=1.0)))["pedestrians"], [])

    def test_floats_are_rounded_to_millimetres(self) -> None:
        state = SimulationState(step=1, sim_time=1.0, vehicles=[VehicleState("v", 1.23456789, 0.0, -2.0004999, 90.123456, 3.0, "car")])
        vehicle = json.loads(serialize_state(state))["vehicles"][0]
        self.assertEqual((vehicle["x"], vehicle["z"], vehicle["angle"]), (1.235, -2.0, 90.123))

    def test_small_state_goes_in_one_datagram_without_part_fields(self) -> None:
        datagrams = serialize_state_datagrams(SimulationState(step=3, sim_time=3.0))
        self.assertEqual(len(datagrams), 1)
        self.assertNotIn("parts", json.loads(datagrams[0]))

    def test_large_state_is_split_and_every_entity_sent_once(self) -> None:
        vehicles = [VehicleState(f"flow_east.{i}", 100.0 + i, 0.0, -50.5, 270.0, 8.25, "car") for i in range(120)]
        pedestrians = [PedestrianState(f"ped_E0_E1.{i}", 10.0 + i, 0.0, 5.5, 90.0, 1.2) for i in range(120)]
        state = SimulationState(step=9, sim_time=909.0, vehicles=vehicles,
                                traffic_lights=[{"id": "tls", "phase": 5, "state": "r" * 10 + "G" * 4}], pedestrians=pedestrians)
        datagrams = serialize_state_datagrams(state, max_bytes=2048)
        self.assertGreater(len(datagrams), 1)
        parts = [json.loads(datagram) for datagram in datagrams]
        self.assertTrue(all(len(datagram) <= 2048 for datagram in datagrams))
        self.assertEqual([part["part"] for part in parts], list(range(len(parts))))
        self.assertTrue(all(part["parts"] == len(parts) and part["step_id"] == 9 for part in parts))
        self.assertTrue(all(part["traffic_lights"][0]["state"] == "r" * 10 + "G" * 4 for part in parts))
        self.assertEqual([v["id"] for part in parts for v in part["vehicles"]], [v.id for v in vehicles])
        self.assertEqual([p["id"] for part in parts for p in part["pedestrians"]], [p.id for p in pedestrians])


if __name__ == "__main__":
    unittest.main()
