"""Scripts de linha de comando (``python -m experiments.<grupo>.<script>``, a partir de ``python/``).

- ``train``: pré-treino e ajuste fino dos agentes DQN.
- ``evaluate``: avaliações e comparações entre versões, políticas e percepções.
- ``data``: geração de redes, demandas e dataset; conferência e extensão das ROIs.
- ``checks``: verificações manuais de integração com o SUMO e a Unity.
- ``article``: figuras e estatísticas do artigo final.

A lógica reutilizável fica em ``simulation/``, ``controller/``, ``vision/`` e ``sumo/``.
"""
