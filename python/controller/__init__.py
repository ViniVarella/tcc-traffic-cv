"""Controle semafórico.

- ``keep_switch``: linha manter/trocar sobre o programa do cruzamento de SP
  (regra de fila, tempo fixo, max-pressure e DQN estado v1–v3; produto
  v2.0–v5.0), com a camada de segurança ``DqnTrafficController`` e a prioridade
  para viaturas.
- ``phase_selection``: linha de escolha livre de estágio em qualquer cruzamento
  (modelo global, produto v6.0).
- ``rewards`` e ``smdp``: recompensa e transições SMDP, comuns às duas linhas.
"""

from .keep_switch.agent import DqnAgent, DqnConfig
from .keep_switch.phase_manager import PhaseManager
from .keep_switch.policies import QueueBasedPolicy
from .keep_switch.traffic_controller import DqnTrafficController

__all__ = ["DqnAgent", "DqnConfig", "DqnTrafficController", "PhaseManager", "QueueBasedPolicy"]
