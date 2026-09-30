"""Ambiente de episódio v2: perfil, geometria, encoder e recompensa fixos entre episódios."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from controller import DqnAgent, DqnTrafficController
from controller.preemption import EmergencyPreemption, PreemptionSettings
from controller.rewards import RewardWeights
from experiments.episode_runner import EpisodeSettings, Observer, Policy, RewardModel, incoming_lane_capacity, run_episode
from sumo import SumoClient
from sumo.emergency import EmergencySettings, EmergencyTraffic
from sumo.lane_feature_source import TraciLaneFeatureSource, noise_from_config
from vision import build_state_encoder
from vision.lane_features import KinematicsParameters, load_lane_geometries


class EpisodeObserver(Protocol):
    """Fonte de features de um episódio; o padrão é o oráculo TraCI."""

    def begin_episode(self, client: SumoClient, seed: int) -> Observer: ...


class Environment:
    def __init__(self, config: dict[str, Any], base_dir: Path, scenario: str | None, settings: EpisodeSettings) -> None:
        self.config = config
        self.base_dir = base_dir
        self.scenario = scenario
        self.settings = settings
        self.geometries = load_lane_geometries(config)
        self.parameters = KinematicsParameters.from_config(config)
        self.noise = noise_from_config(config)
        self.encoder = build_state_encoder(config, version=2)
        self.reward_lanes = tuple(sorted({geometry.sumo_lane for geometry in self.geometries.values()}))
        self.reward_weights = RewardWeights.from_config(config)
        self.tls_id = str(config["traffic_light"]["id"])
        # Aproximação (câmera) -> edge SUMO de entrada, a partir das lanes das ROIs.
        self.approach_edges = {camera: geometry.sumo_lane.rsplit("_", 1)[0] for (camera, _), geometry in self.geometries.items()}

    def oracle_source(self, seed: int) -> TraciLaneFeatureSource:
        return TraciLaneFeatureSource(self.geometries, self.parameters, self.noise, seed=seed)

    def run(
        self,
        seed: int,
        policy: Policy,
        learner: DqnAgent | None = None,
        observer: EpisodeObserver | None = None,
        on_step: Callable[[dict[str, Any]], None] | None = None,
        emergency: EmergencySettings | None = None,
        preemption: PreemptionSettings | None = None,
    ) -> tuple[Any, str | None]:
        """Executa um episódio completo na seed; sem ``observer`` usa o oráculo TraCI.

        Com ``emergency``, viaturas agendadas pela seed entram após o aquecimento;
        com ``preemption`` também, elas recebem prioridade via aviso V2I.
        """
        if preemption is not None and emergency is None:
            raise ValueError("Preempção exige a agenda de viaturas de emergência.")
        client = SumoClient.from_config(self.config, self.base_dir, seed_override=seed, scenario_override=self.scenario)
        client.start()
        try:
            reward = RewardModel(self.reward_lanes, incoming_lane_capacity([client.get_lane_length(lane) for lane in self.reward_lanes]),
                                 self.reward_weights)
            if observer is None:
                source = self.oracle_source(seed)
                observe: Observer = lambda sim_time: source.observe(client, sim_time)
            else:
                observe = observer.begin_episode(client, seed)
            traffic = None if emergency is None else EmergencyTraffic(
                emergency, self.approach_edges, seed, self.settings.warmup_s, self.settings.warmup_s + self.settings.control_s)
            preempt = None if preemption is None else EmergencyPreemption(preemption)

            def emergency_step(sim_time: float) -> str | None:
                requests = traffic.step(client, sim_time)
                return None if preempt is None else preempt.target_green(requests)

            outcome = run_episode(
                client=client, controller=DqnTrafficController(self.tls_id, self.config), observe=observe,
                encoder=self.encoder, policy=policy, reward=reward, settings=self.settings, learner=learner, on_step=on_step,
                emergency=None if traffic is None else emergency_step,
            )
            if traffic is not None:
                outcome.metrics["emergency"] = traffic.summary()
        finally:
            client.close()
        return outcome, client.scenario
