"""Testes de configuração do cliente TraCI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from sumo import SumoClient
from sumo import traci_client


class SumoClientTests(unittest.TestCase):
    def test_seed_override_has_priority_over_profile_seed(self) -> None:
        config = {"sumo": {"config_path": "scenario.sumocfg", "gui": False}, "experiment": {"seed": 42}}
        client = SumoClient.from_config(config, Path("/tmp"), seed_override=7)
        self.assertEqual(client.seed, 7)



def fake_traci(lanes: dict[str, list[list[str]]], links: list[list[tuple[str, str, str]]] | None = None) -> SimpleNamespace:
    """TraCI mínimo: ``lanes`` mapeia edge → classes permitidas por faixa."""
    return SimpleNamespace(
        edge=SimpleNamespace(getLaneNumber=lambda edge: len(lanes[edge])),
        lane=SimpleNamespace(getAllowed=lambda lane: lanes[lane.rpartition("_")[0]][int(lane.rpartition("_")[2])]),
        trafficlight=SimpleNamespace(getControlledLinks=lambda tls: links or []),
    )


class VehicleLaneTests(unittest.TestCase):
    def client(self) -> SumoClient:
        client = SumoClient("sumo", "x.sumocfg", gui=False)
        client._started = True
        return client

    def test_network_without_sidewalks_keeps_lane_ids(self) -> None:
        with mock.patch.object(traci_client, "traci", fake_traci({"E3": [[], [], [], []]})):
            self.assertEqual(self.client().vehicle_lane_id("E3_2"), "E3_2")

    def test_sidewalk_at_index_zero_shifts_vehicle_lanes(self) -> None:
        with mock.patch.object(traci_client, "traci", fake_traci({"E3": [["pedestrian"], [], [], [], []]})):
            client = self.client()
            self.assertEqual(client.vehicle_lane_id("E3_0"), "E3_1")
            self.assertEqual(client.vehicle_lane_id("E3_3"), "E3_4")
            with self.assertRaises(ValueError):
                client.vehicle_lane_id("E3_4")

    def test_pedestrian_links_are_those_starting_at_internal_lanes(self) -> None:
        links = [[("E2_1", "E0_1", ":c_0_0")], [("E3_1", "E1_1", ":c_3_0")], [(":c_w0_0", ":c_c0_0", "")], []]
        with mock.patch.object(traci_client, "traci", fake_traci({}, links)):
            self.assertEqual(self.client().pedestrian_link_count("tls"), 1)


if __name__ == "__main__":
    unittest.main()
