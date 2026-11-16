# Código Python legado

Este código vem das primeiras versões do TraffIQ (v2.0 regra de fila, v2.1 DQN
estado v1) e dos primeiros testes de integração. Não faz parte do pipeline
atual (`simulation/`, `controller/`, `experiments/`), mas continua executável
para reproduzir resultados antigos. Rode a partir de `python/`:

```bash
../.venv/bin/python -m legacy.<módulo> --help
```

| Módulo | O que é |
|---|---|
| `train_visual_dqn.py` | Treino do DQN estado v1 (13 entradas) com Unity e YOLO |
| `run_visual_controller.py` | Controle visual da v2.0 (regra de fila) e da v2.1 (DQN estado v1) |
| `run_fixed_time_baseline.py` | Tempo fixo nativo do SUMO, com o programa estático do `.net.xml` |
| `compare_control_experiments.py` | Compara dois JSONs de métricas (formato da época da v2.x) |
| `traffic_controller.py` | Controlador heurístico (regra de fila) usado por `run_visual_controller` |
| `sort_tracker.py` | Rastreador SORT, substituído pelo ByteTrack |
| `test_sumo_traci.py`, `test_unity_comm.py`, `test_vision.py` | Testes manuais com a rede fictícia (`legacy/sumo/fictional`) e `config.yaml` |
| `main.py`, `config.yaml` | Esqueleto inicial do projeto e seu perfil de configuração |
| `logging_utils/` | Esqueletos de log nunca usados |

Os testes unitários de `traffic_controller` e `compare_control_experiments`
continuam em `python/tests/`.
