"""Políticas de cada versão do projeto sobre o mesmo ambiente de avaliação.

Aqui "versão" nomeia **controladores** (quem decide), não versões do produto
TraffIQ: ``v1`` é a regra de fila (produto v2), ``v1.1`` o DQN estado v1
(produto v2.1), ``v2`` o DQN estado v2, que decide da v3 à v5 do produto, e
``v3`` o experimento DQN estado v3. A v1 do produto (prova de conceito com os
detectores do SUMO, em ``optimization/SP``) não roda aqui. Nos textos, use a
numeração do produto.

Para que as versões sejam comparáveis, todas recebem a mesma percepção (as
``LaneFeatures`` do oráculo TraCI ou da visão), a mesma camada de segurança e o
mesmo executor de episódios; muda só a lógica de decisão:

- ``baseline``: ciclo fixo 40/40 (nunca pede troca; o verde máximo alterna);
- ``v1``: regra de fila (``QueueBasedPolicy``) sobre as contagens por faixa;
- ``v1.1``: DQN do estado v1 (13 entradas: contagens, fase e tempo);
- ``v2``: DQN do estado v2 (41 entradas);
- ``max_pressure``: referência adaptativa sobre veículos parados;
- ``global``: o modelo global, experimento DQN de seleção livre de fase para
  qualquer cruzamento (``dqn-fase-livre-ped40-best.pt``, treinado só em
  cruzamentos sintéticos). No SP, com duas fases verdes, escolher a outra fase
  é "trocar".

Diferença deliberada em relação às execuções originais de ``v1``/``v1.1``: elas usavam
a contagem pelo centro da bbox com média móvel (``ROICounter`` +
``QueueEstimator``); aqui a contagem é ``LaneFeatures.vehicle_count`` da mesma
percepção usada pelo ``v2``. As versões antigas decidiam a cada step após o verde
mínimo, por isso usam intervalo de decisão de 1 s.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from controller import DqnAgent
from controller.policies import FixedCyclePolicy, MaxPressurePolicy, QueueBasedPolicy
from controller.phase_selection_agent import PhaseSelectionAgent
from experiments.episode_runner import DqnPolicy, EpisodeSettings, Policy
from vision import build_state_encoder


VERSION_ORDER = ("baseline", "v1", "v1.1", "v2", "max_pressure")
# Experimentos que só entram quando pedidos (fora da lista padrão).
EXPERIMENT_VERSIONS = ("v3", "global")


def lane_counts(lane_features: Mapping[tuple[str, str], Any]) -> dict[str, dict[str, int]]:
    """Converte ``LaneFeatures`` no formato de contagens por câmera/faixa da regra de fila."""
    counts: dict[str, dict[str, int]] = {}
    for (camera_id, lane_id), features in lane_features.items():
        counts.setdefault(camera_id, {})[lane_id] = int(features.vehicle_count)
    return counts


class HeuristicV1Policy:
    """Regra de fila (``v1``): troca se o grupo oposto tem fila e supera o atual pela margem."""

    def __init__(self, switch_margin: int = 1) -> None:
        self.rule = QueueBasedPolicy(switch_margin=switch_margin)

    def __call__(self, state: np.ndarray, lane_features: Mapping[tuple[str, str], Any], phase: Any) -> int:
        demand = self.rule.aggregate(lane_counts(lane_features))
        current, opposing = ("east_west", "south") if phase.name == "EAST_WEST_GREEN" else ("south", "east_west")
        return int(self.rule.should_switch(demand[current], demand[opposing])[0])


class DqnV1Policy:
    """Checkpoint do estado v1 avaliado sobre as mesmas features.

    O último elemento do estado v2 é ``min(1, tempo da fase / verde máximo)``, a
    mesma normalização do v1, então é reaproveitado sem recalcular o tempo.
    """

    def __init__(self, agent: DqnAgent, config: Mapping[str, Any]) -> None:
        if agent.config.state_version != 1:
            raise ValueError("DqnV1Policy exige um checkpoint de estado v1.")
        self.agent = agent
        self.encoder = build_state_encoder(config, version=1)

    def __call__(self, state: np.ndarray, lane_features: Mapping[tuple[str, str], Any], phase: Any) -> int:
        elapsed_seconds = float(state[-1]) * self.encoder.max_green_seconds
        v1_state = self.encoder.encode(lane_counts(lane_features), phase.phase_index, elapsed_seconds)
        return self.agent.select_action(v1_state, epsilon=0.0, explore=False)


class GlobalPhasePolicy:
    """Modelo global (DQN de seleção livre de fase) no laço manter/trocar do SP.

    Monta o estado ``phase_select_*`` com o layout do SP lido de
    ``generic.yaml`` (mesmas ROIs das câmeras) e as ``LaneFeatures`` da
    percepção, reindexadas de ``(câmera, faixa)`` para ``(edge, lane_k)``. O
    laço só consulta a política entre o verde mínimo e o máximo, então as duas
    fases são válidas. Com duas fases, a outra está no vermelho desde o fim do
    seu verde: tempo do verde atual + o tempo perdido ao sair dela (amarelo +
    all-red e, nos cenários com pedestres, a fase exclusiva que vem depois do
    verde Sul). O tempo do verde vem do último elemento do estado v2
    (``min(1, tempo / verde máximo)``), como no v1.1.
    """

    def __init__(self, agent: PhaseSelectionAgent, generic_config: Path, sp_config: Mapping[str, Any],
                 pedestrian_phase: bool = False, net_scenario: str = "sp/calibrated") -> None:
        from experiments.phase_selection_environment import PhaseSelectionEnvironment
        from sumo.intersection import program_green_indices

        environment = PhaseSelectionEnvironment.from_file(generic_config, EpisodeSettings())
        scenario = environment.scenario(net_scenario)
        self.agent = agent
        self.layout = environment.layout(scenario)
        self.green_index = program_green_indices(scenario.net, self.layout.tls_id)
        pedestrians = sp_config.get("pedestrians", {})
        self.pedestrian_s = (float(pedestrians.get("green_seconds", 0)) + float(pedestrians.get("clearance_seconds", 0))
                             if pedestrian_phase else 0.0)
        if self.pedestrian_s and int(pedestrians.get("every_cycles", 1)) != 1:
            raise ValueError("O modelo global só representa a fase de pedestres a cada ciclo (every_cycles = 1).")
        # A fase de pedestres vem depois do verde Sul (secondary_green do programa).
        south_program = int(sp_config["traffic_light"]["phases"]["secondary_green"])
        self.pedestrian_after = self.green_index[south_program] if self.pedestrian_s else None
        self.encoder = environment.encoder(self.layout, self.pedestrian_s, agent.config.state_version)
        if self.encoder.max_phases != agent.config.max_phases:
            raise ValueError("max_phases do generic.yaml difere do checkpoint.")
        self.key_map = environment.camera_key_map(scenario)
        self.groups = [self.layout.lane_keys(phase) for phase in range(len(self.layout.greens))]
        self.capacities = {key: geometry.capacity for key, geometry in self.layout.geometries.items()}
        self.max_green_s = environment.max_green_s
        self.transition_s = environment.yellow_s + environment.all_red_s

    def leave_seconds(self, phase: int) -> float:
        return self.transition_s + (self.pedestrian_s if phase == self.pedestrian_after else 0.0)

    def observation(self, state: np.ndarray, lane_features: Mapping[tuple[str, str], Any], phase: Any) -> Any:
        from experiments.phase_selection_environment import remap_features

        current = self.green_index[int(phase.phase_index)]
        elapsed = float(state[-1]) * self.max_green_s
        phases = range(len(self.groups))
        red_times = [0.0 if index == current else elapsed + self.leave_seconds(index) for index in phases]
        switch_in = [0.0 if index == current else self.leave_seconds(current) for index in phases]
        return self.encoder.encode(remap_features(lane_features, self.key_map), self.groups, self.capacities, current,
                                   elapsed, red_times, tuple(True for _ in self.groups),
                                   switch_in, [self.leave_seconds(index) for index in phases])

    def __call__(self, state: np.ndarray, lane_features: Mapping[tuple[str, str], Any], phase: Any) -> int:
        observation = self.observation(state, lane_features, phase)
        choice = self.agent.select_action(observation.state, epsilon=0.0, explore=False)
        return int(choice != observation.current)


@dataclass(frozen=True, slots=True)
class VersionPolicy:
    name: str
    description: str
    policy: Policy
    decision_interval_s: float
    # Versão do estado que o ambiente codifica para a política (3 só com pedestres).
    state_version: int = 2


def build_version_policies(config: Mapping[str, Any], names: Sequence[str], v1_checkpoint: Path, v2_checkpoint: Path,
                           v3_checkpoint: Path | None = None, global_checkpoint: Path | None = None,
                           generic_config: Path | None = None, scenario: str | None = None) -> list[VersionPolicy]:
    """Políticas pedidas; ``scenario`` só importa ao modelo global (``*_ped`` liga a fase de pedestres)."""
    unknown = [name for name in names if name not in (*VERSION_ORDER, *EXPERIMENT_VERSIONS)]
    if unknown:
        raise ValueError(f"Versões desconhecidas: {unknown}. Disponíveis: {', '.join(VERSION_ORDER)}.")
    margin = int(config.get("traffic_control", {}).get("switch_margin", 1))
    result: list[VersionPolicy] = []
    for name in names:
        if name == "baseline":
            result.append(VersionPolicy(name, "ciclo fixo 40/40", FixedCyclePolicy(), 5.0))
        elif name == "v1":
            result.append(VersionPolicy(name, "heurística por fila visual", HeuristicV1Policy(margin), 1.0))
        elif name == "v1.1":
            result.append(VersionPolicy(name, "DQN estado v1 (13 entradas)", DqnV1Policy(DqnAgent.load(v1_checkpoint, device="cpu"), config), 1.0))
        elif name == "v2":
            agent = DqnAgent.load(v2_checkpoint, device="cpu")
            if agent.config.state_version != 2:
                raise ValueError(f"{v2_checkpoint} não é um checkpoint de estado v2.")
            result.append(VersionPolicy(name, "DQN estado v2 (41 entradas)", DqnPolicy(agent), 5.0))
        elif name == "v3":
            if v3_checkpoint is None:
                raise ValueError("A versão v3 exige um checkpoint (--v3-dqn-model).")
            agent = DqnAgent.load(v3_checkpoint, device="cpu")
            if agent.config.state_version != 3:
                raise ValueError(f"{v3_checkpoint} não é um checkpoint de estado v3.")
            result.append(VersionPolicy(name, "DQN estado v3 (44 entradas, com pedestres)", DqnPolicy(agent), 5.0, state_version=3))
        elif name == "global":
            if global_checkpoint is None or generic_config is None:
                raise ValueError("A versão global exige o checkpoint e o generic.yaml.")
            agent = PhaseSelectionAgent.load(global_checkpoint)
            result.append(VersionPolicy(name, "modelo global: DQN de seleção livre de fase (experimento)",
                                        GlobalPhasePolicy(agent, generic_config, config,
                                                          pedestrian_phase=str(scenario or "").endswith("_ped")), 5.0))
        else:
            result.append(VersionPolicy(name, "max-pressure (referência)", MaxPressurePolicy(), 5.0))
    return result
