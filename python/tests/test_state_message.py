"""Testes da mensagem de estado Python -> Unity (veículos, semáforo e pedestres)."""

from __future__ import annotations

import json
import unittest

from bridge import PedestrianState, SimulationState, serialize_state
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


if __name__ == "__main__":
    unittest.main()
