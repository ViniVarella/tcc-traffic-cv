"""Políticas de cada versão do projeto sobre o mesmo ambiente de avaliação.

Para que as versões sejam comparáveis, todas recebem a mesma percepção (as
``LaneFeatures`` do oráculo TraCI ou da visão), a mesma camada de segurança e o
mesmo executor de episódios; muda só a lógica de decisão:

- ``baseline``: ciclo fixo 40/40 (nunca pede troca; o verde máximo alterna);
- ``v1``: heurística da v1 (``QueueBasedPolicy``) sobre as contagens por faixa;
- ``v1.1``: DQN do estado v1 (13 entradas: contagens, fase e tempo);
- ``v2``: DQN do estado v2 (41 entradas);
- ``max_pressure``: referência adaptativa sobre veículos parados.

Diferença deliberada em relação às execuções originais da v1/v1.1: elas usavam
a contagem pelo centro da bbox com média móvel (``ROICounter`` +
``QueueEstimator``); aqui a contagem é ``LaneFeatures.vehicle_count`` da mesma
percepção usada pela v2. As versões antigas decidiam a cada step após o verde
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
from experiments.episode_runner import DqnPolicy, Policy
from vision import build_state_encoder


VERSION_ORDER = ("baseline", "v1", "v1.1", "v2", "max_pressure")


def lane_counts(lane_features: Mapping[tuple[str, str], Any]) -> dict[str, dict[str, int]]:
    """Converte ``LaneFeatures`` no formato de contagens por câmera/faixa da v1."""
    counts: dict[str, dict[str, int]] = {}
    for (camera_id, lane_id), features in lane_features.items():
        counts.setdefault(camera_id, {})[lane_id] = int(features.vehicle_count)
    return counts


class HeuristicV1Policy:
    """Regra da v1: troca se o grupo oposto tem fila e supera o atual pela margem."""

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


@dataclass(frozen=True, slots=True)
class VersionPolicy:
    name: str
    description: str
    policy: Policy
    decision_interval_s: float
    # Versão do estado que o ambiente codifica para a política (3 só com pedestres).
    state_version: int = 2


def build_version_policies(config: Mapping[str, Any], names: Sequence[str], v1_checkpoint: Path, v2_checkpoint: Path,
                           v3_checkpoint: Path | None = None) -> list[VersionPolicy]:
    unknown = [name for name in names if name not in (*VERSION_ORDER, "v3")]
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
        else:
            result.append(VersionPolicy(name, "max-pressure (referência)", MaxPressurePolicy(), 5.0))
    return result
