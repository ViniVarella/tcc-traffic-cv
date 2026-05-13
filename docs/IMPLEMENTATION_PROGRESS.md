# Progresso de Implementação

Este arquivo registra o andamento prático do plano descrito em `docs/IMPLEMENTATION_GUIDE_TCC_TRAFFIC_CV.md`.

## Status Geral

- Marco 1: concluído
- Marco 2: concluído
- Marco 3: concluído
- Arquitetura revisada documentada: concluído
- Marco 4 em diante: pendentes

## Marco 1 — Estrutura inicial do repositório

Status: concluído

Entregas realizadas:

- criação do `README.md` inicial;
- criação de `python/config.yaml`;
- criação dos pacotes Python com `__init__.py`;
- criação dos stubs principais em:
  - `python/sumo`
  - `python/bridge`
  - `python/vision`
  - `python/controller`
  - `python/logging_utils`
  - `python/experiments`
- criação de `python/main.py` com carga de configuração e mensagem de scaffold pronto;
- criação de `docs/IMPLEMENTATION_GUIDE.md` como arquivo de referência local para o guia principal.

Validação realizada:

- `python python/main.py`
- `python -m compileall python`

## Marco 2 — Pipeline de visão computacional

Status: concluído

Objetivo atendido:

- adaptar a base conceitual do `car-counter` para uma pipeline modular de visão;
- manter YOLO com `ultralytics`;
- manter SORT como tracker;
- usar contagem principal por ROI, sem lógica principal baseada em linha;
- permitir teste local com imagem ou vídeo, sem depender de SUMO ou Unity.

Entregas realizadas:

- implementação de `python/vision/yolo_detector.py`;
- implementação de `python/vision/sort_tracker.py`;
- implementação de `python/vision/roi_counter.py`;
- implementação de `python/vision/queue_estimator.py`;
- implementação de `python/vision/visual_debug.py`;
- criação de `python/experiments/test_vision.py`;
- atualização do `README.md` com instruções mínimas de execução do teste de visão.

Comportamento disponível hoje:

- entrada por imagem ou vídeo local;
- detecção de veículos com YOLO;
- rastreamento com IDs persistentes via SORT;
- contagem por ROIs usando centro da bounding box dentro de polígono;
- suavização simples das contagens;
- geração de frames de debug em `results/frames` com:
  - bounding boxes;
  - `track_id`;
  - ROIs;
  - contagens brutas e suavizadas.

Validação realizada:

- `python -m compileall python`
- execução com a `.venv` do projeto:
  - `cd python`
  - `..\\.venv\\Scripts\\python.exe -m experiments.test_vision --input ../samples/traffic_top_view.mp4 --max-frames 1 --frame-step 30`

Observações:

- o teste depende do ambiente virtual com dependências instaladas;
- na primeira execução, o `ultralytics` pode baixar `yolov8n.pt`;
- modelos `.pt`, vídeos, imagens e frames gerados permanecem fora de versionamento pelo `.gitignore`.
- esse teste continua sendo apenas preliminar, com vídeo ou imagem local;
- a arquitetura final documentada passa a usar quatro câmeras Unity com ROIs por câmera;
- a visão final deve rodar a cada `N` steps simulados, com `update_every_steps` configurável;
- o protocolo final de frames deve identificar `step_id` e `camera_id`;
- ground truth do SUMO continua reservado para avaliação, nunca para decisão online.

## Marco 3 — Cliente SUMO e integração inicial via TraCI

Status: concluído

Objetivo atendido:

- criar uma integração mínima e testável com SUMO via TraCI;
- manter Python como único cliente TraCI;
- permitir avanço step-based da simulação;
- preparar extração de estado e ground truth sem implementar Unity nem controle adaptativo.

Entregas realizadas:

- implementação de `python/sumo/traci_client.py`;
- implementação inicial de `python/sumo/state_extractor.py`;
- implementação inicial de `python/sumo/ground_truth.py`;
- criação de `python/experiments/test_sumo_traci.py`;
- atualização do `README.md` com instruções mínimas para o teste SUMO.

Capacidades disponíveis neste marco:

- iniciar `sumo` ou `sumo-gui` a partir do `config.yaml`;
- usar `experiment.seed` com `--seed`;
- avançar a simulação com `simulationStep()`;
- obter `sim_time` por `traci.simulation.getTime()`;
- extrair veículos ativos com:
  - `id`
  - `x`
  - `y`
  - `angle`
  - `speed`
  - `type`
- extrair estado do semáforo com:
  - `id`
  - `phase`
  - `state`
- alterar fase do semáforo manualmente;
- fechar TraCI com segurança em `finally`.

Validação realizada:

- `python -m compileall python`
- execução com a `.venv` do projeto:
  - `cd python`
  - `..\\.venv\\Scripts\\python.exe -m experiments.test_sumo_traci`

Resultado da validação atual:

- o script está funcional e falha de forma controlada quando o arquivo configurado em `sumo.config_path` não existe;
- a mensagem de erro informa claramente que o `.sumocfg` esperado não foi encontrado.

Observações:

- neste momento, o repositório ainda não possui o cenário `sumo/configs/intersection.sumocfg`;
- por isso, o caminho feliz do teste ainda depende da criação do cenário SUMO;
- `ground_truth.py` continua reservado para avaliação futura, sem alimentar qualquer controlador.

## Próximos Marcos

### Marco 4 — Comunicação Python -> Unity

Pendente.

Escopo previsto:

- comunicação Python -> Unity;
- implementação inicial de `python/bridge/unity_comm.py`;
- recepção de estado na Unity;
- atualização visual básica da cena a partir de JSON fake.

### Marco 5 em diante

Pendentes conforme o guia:

- integração SUMO -> Python -> Unity;
- captura Unity -> Python;
- YOLO em frames da Unity;
- ROI por câmera no loop integrado;
- controlador semafórico;
- experimentos comparativos.
