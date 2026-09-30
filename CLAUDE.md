# CLAUDE.md — TCC Traffic CV

Controle semafórico adaptativo baseado em visão computacional para um cruzamento
de São Paulo (cenário `sp`), integrando SUMO, Unity, YOLOv8, ByteTrack e DQN.

- Responda ao usuário em **português**. Código, docstrings e mensagens de log do
  projeto também são em português.
- Progresso, resultados e documentação do projeto ficam em `docs/`
  (`IMPLEMENTATION_PROGRESS.md`, `IMPLEMENTATION_GUIDE.md`,
  `SUMO2UNITY_INTEGRATION.md`). `CODEX_HANDOFF.md` é só o retrato da migração
  do Codex: não o edite.

## Arquitetura

```text
SUMO ──TraCI──> Python ──UDP/JSON (estado)──> Unity (veículos, semáforos, câmeras)
                  ^                                  │
                  │                 TCP/JPEG por step_id (câmeras south/east/west)
                  │                                  v
           DqnTrafficController <── DQN <── VisualStateEncoder <── YOLO + ByteTrack + ROIs
```

- **O Python é o único cliente TraCI e o único que avança o SUMO**
  (`simulationStep()` síncrono; métricas usam tempo simulado, não relógio).
- A Unity só renderiza o estado recebido e devolve frames. Ela **não** se conecta
  ao SUMO nem ao `Sumo2UnityTool.exe`/ZeroMQ do projeto de referência
  (`sumo2unity/` é um clone local ignorado, apenas referência).
- Frames são agrupados por `step_id` (`bridge/frame_bundle.py`); uma decisão
  nunca pode misturar imagens de passos diferentes.
- Três câmeras operacionais: `south`, `east`, `west`. A aproximação norte é só
  de saída e não é observada.

### Duas linhas de DQN — não confundir

| Linha | Local | Estado | Framework |
|---|---|---|---|
| **Principal (visual)** | `python/` | contagens visuais por faixa (YOLO/ROI) + fase | PyTorch |
| Paralela (E2/TraCI) | `optimization/SP/` (`sp_env.py`, `traci8.DQN.py`, `traci9_comp.py`) | detectores E2 + lanes via TraCI | Keras |

`optimization/SP` é um experimento separado e não é substituto de
`python/experiments/train_visual_dqn.py`. Não reutilize seus comandos no
pipeline `python/` sem revisão. `optimization/Teste` e `optimization/EUA` são
protótipos antigos.

### Separação estado × recompensa

- A **política** observa apenas dados visuais. E2 e demais dados perfeitos do
  SUMO **não** entram na decisão.
- A **recompensa de treino** usa verdade de terreno do TraCI (espera dos
  veículos). Relatórios devem declarar isso; não chame o loop de "visão pura".
- E2 serve apenas para avaliação offline visão × verdade de terreno
  (`vision_evaluation.lane_detector_mapping` em `sp.yaml`,
  `vision/e2_evaluation.py`).

## Estrutura

```text
python/                 código Python (rodar comandos a partir daqui)
  configs/sp.yaml       fonte de verdade do cenário SP
  sumo/                 traci_client.py, scenarios.py, lane_feature_source.py (oráculo TraCI),
                        state_extractor.py, experiment_metrics.py, ground_truth.py
  bridge/               unity_comm.py (UDP/TCP), frame_bundle.py, protocol.py, serialization.py
  vision/               yolo_detector, byte_track_tracker, roi_counter, queue_estimator,
                        camera_calibration, visual_pipeline (laço por câmera compartilhado),
                        lane_geometry (homografia das ROIs), lane_features (contrato v2),
                        visual_lane_features, visual_state (encoders v1/v2), e2_evaluation
  controller/           dqn_agent.py, dqn_traffic_controller.py, phase_manager.py,
                        traffic_controller.py (heurístico), policies.py, rewards.py,
                        decision_scheduler.py
  experiments/          entry points (python -m experiments.<nome>)
  tests/                unittest (test_*.py)
sumo/sp/                rede, rotas e detectores do cenário SP (Cruzamento.*)
unity/TrafficVisionUnity/   projeto Unity 6000.0.53f1 (Unity 6, URP, macOS/Metal)
optimization/SP/        linha paralela E2/Keras (ver acima)
simjamcv/               dados de drone/SimJamComputerVision (referência de calibração)
results/, runs/         saídas locais de experimentos e modelos — ignoradas pelo Git
docs/                   guias de implementação e integração Sumo2Unity
```

`optimization/SP/Cruzamento.{net,rou,add}.xml` são cópias de `sumo/sp/`; se
alterar um, verifique o outro. Exceção deliberada: `sumo/sp/Cruzamento.calibrated.rou.xml`
usa chegadas Poisson (`period="exp(...)"`) e inserção realista
(`departLane="best" departSpeed="max"`), ao contrário da cópia em `optimization/SP`.

## Cenário SP (`python/configs/sp.yaml`)

- SUMO: step 1 s, porta TraCI 8873. Cenários em `sumo.scenarios` (escolha com
  `--scenario`; padrão `sumo.default_scenario`):
  - `calibrated` (padrão): demanda medida nos vídeos de drone — Leste
    saturado (v/c≈1,0), Sul 0,39, Oeste 0,20. É o cenário principal.
  - `original`: demanda equilibrada do netedit (v/c≈0,5); o tempo de verde
    quase não muda o resultado. Mantido para comparar com resultados antigos.
- Unity: estado UDP `127.0.0.1:5004`, frames TCP `127.0.0.1:5005`.
- TLS `clusterJ0_J14_J2_J7`, 5 fases: 0 verde E/W, 1 amarelo E/W, 2 all-red,
  3 verde South, 4 amarelo South. String de estado com 10 links.
- Segurança: verde mín. 10 s, máx. 40 s, amarelo 3 s, all-red 1 s. O programa
  estático do `.net.xml` (42/3/1/41/3, sem all-red após o amarelo South) é só
  o baseline `run_fixed_time_baseline`. Quando o Python controla, `apply()`
  faz `setPhase` + `setPhaseDuration(SUMO_PHASE_HOLD_SECONDS)` para o SUMO nunca
  avançar sozinho, e steps sem frames chamam `update_without_vision()` (nunca
  pule o controlador — isso dessincronizava as fases).
- Faixas monitoradas (7): south 4 (edge E3), east 2 (E2), west 1 (E6).
  Ordem estável das features em `vision/visual_state.py::SP_LANE_ORDER`.
- Detectores E2 `e2_0..e2_6` em `sumo/sp/Cruzamento.add.xml` (IDs são contrato
  com `sp.yaml` e scripts; não renomeie). Eles cobrem 42,6–45,8 m, mas as ROIs
  das câmeras Unity cobrem só ~23–26 m por faixa (`lane_geometry` em
  `sp.yaml`, medido por `experiments.check_lane_geometry` e protegido por
  teste). Compare visão com TraCI no intervalo da ROI, não no do E2.
- Métricas de avaliação devem incluir a fila de inserção (`*_pending_vehicles`):
  veículos que ainda não entraram na rede não aparecem na espera média.
- Alterar `sp.yaml` pode invalidar calibrações de câmera, o state encoder e
  checkpoints.

## Contrato do DQN

Há duas versões de estado (`DqnConfig.state_version`; checkpoints sem o campo
carregam como v1):

- **v1 (legado, 13 entradas):** contagens suavizadas por faixa + fase + tempo
  (`VisualStateEncoder`). Treino `train_visual_dqn.py`; execução
  `run_visual_controller.py` (decide a cada step). Os scripts v2 são
  `pretrain_dqn_sumo`, `evaluate_policies_sumo`, `run_visual_policy` e
  `finetune_dqn_visual`, todos sobre `sumo_environment.Environment`.
- **v2 (atual, 41 entradas):** por faixa, `LaneFeatures` = contagem, parados,
  ocupação, velocidade média e espera, normalizados pela capacidade da ROI
  (comprimento / 7,5 m), + fase one-hot + tempo (`LaneFeatureStateEncoder`,
  `build_state_encoder(config, versão)`).
  - As features vêm de `ApproachKinematicsTracker` (`vision/lane_features.py`),
    alimentado por duas fontes com o mesmo contrato: `VisualLaneFeatureSource`
    (base das bboxes → homografia da ROI) e `TraciLaneFeatureSource`
    (posições reais no intervalo da ROI — oráculo do pré-treino). Um teste de
    paridade garante features idênticas para a mesma trajetória.
  - "Parado" = < 1,39 m/s por ≥ 1 s (padrão do E2). A Unity põe o pivô do
    modelo na posição da frente do veículo no SUMO; `lane_state.visual_ground_offset_m`
    corrige o ponto de solo da visão.
  - A política só decide em pontos de decisão (verde, entre verde mínimo e
    máximo, a cada 5 s; `controller/decision_scheduler.py`); entre eles o
    controlador recebe KEEP. Transições são SMDP (recompensa acumulada,
    desconto `gamma ** k`, γ por segundo).
  - Recompensa (`controller/rewards.py`): nível em [−1, 0] sobre as lanes de
    entrada inteiras (parados, espera nativa, fila de inserção), vinda do
    TraCI — não é entrada da política.
  - Laço único em `experiments/episode_runner.py` para pré-treino, ajuste
    fino e avaliação; muda só a função `observe`.
- Ações: `keep` (0) e `switch` (1). O DQN só escolhe manter/trocar;
  `DqnTrafficController` + `PhaseManager` aplicam verde mínimo/máximo, amarelo
  e all-red. **Nunca** permita que a política pule transições de segurança.
- Checkpoints (`DqnAgent.save`) guardam `config` e `metadata` (versão, nomes
  das features, fonte, cenário). Se a dimensão ou a semântica do estado mudar,
  pesos antigos não são reaproveitáveis: crie uma nova versão de estado.
- **Nunca** use o oráculo TraCI para controlar em uma avaliação "visual" sem
  rotulá-la como percepção oráculo.
- **Compare versões só no mesmo ambiente**: mesmo cenário, seeds, aquecimento,
  duração, camada de segurança, métricas e percepção; muda só a decisão. Use
  `experiments.compare_versions` (regras das versões em
  `experiments/version_policies.py`). Resultados de protocolos diferentes
  ficam só como registro histórico, nunca em tabela comparativa.
- A Unity só renderiza e envia frames com o editor em foco, a menos que
  *Run In Background* esteja ligado (Project Settings > Player > Resolution
  and Presentation; `runInBackground` em `ProjectSettings.asset`). Sem frames,
  o controle mantém o verde e a avaliação fica enviesada; o observador imprime
  `vision_missing_streak` a cada 10 steps seguidos sem frames. Confira
  `missing_frames` nas saídas antes de usar um resultado visual.
- Com a Unity no loop, `step_id` cresce entre episódios do mesmo processo
  (frames atrasados nunca casam com um step novo) e o usuário reinicia o Play
  Mode entre comandos. A visão só liga `--prime-seconds` antes do fim do
  aquecimento; o aquecimento do SUMO roda sem Unity.
- Seeds: treino 1–40 (pré-treino) e 41–50 (ajuste fino), validação 1001–1003,
  teste 201–203 — manter disjuntas (os scripts recusam sobreposição).
  Comparações entre políticas usam a mesma seed em cada par.

## Unity

- Cena canônica: `Assets/Scenes/SPImport.unity`. Raízes:
  `GeneratedSumoRoadNetwork`, `SP Environment`, `SP Dynamic Synchronization`,
  `SP Vehicles`, `SP Traffic Light Marker`.
- Calibração das câmeras/ROIs: `Assets/Calibration/{south,east,west}-calibration.json`
  (lidas pelo Python via `vision.load_camera_calibration`).
- Menus `Traffic Vision > SUMO` (cada um recria **apenas** sua raiz):
  - `Build SP Presentation Environment` → `SP Environment` (salva a cena sozinho);
  - `Configure SP Visuals` → `GeneratedSumoRoadNetwork` (depois `Cmd+S`);
  - `Configure SP Dynamic Sync` → sincronização + 3 postes (depois `Cmd+S`).
- O botão `Clear generated road network` (Inspector do importador) não deve ser
  a ação final; rode `Configure SP Visuals` em seguida.
- **Transforms manuais são intencionais.** As 8 casas
  (`SpEnvironmentSetup.cs`) e os 3 postes `Signal Post East/South/West`
  (`SpDynamicSyncSetup.cs`) foram posicionados pelo usuário no Editor e copiados
  para o código. Não os reposicione nem "melhore" por regra automática sem
  confirmação.
- **Semáforo por aproximação** (`TrafficLightVisualController.cs`): East = links
  0–2, South = 3–8, West = 9, derivados dos `linkIndex` de `Cruzamento.net.xml`.
  Prioridade verde > amarelo > vermelho. Não simplificar para uma cor global.
- Calçadas vêm da geometria da rede (`SumoRoadNetworkImporter.cs`), não de cubos
  manuais — cubos atravessavam o cruzamento e foram descartados.
- Não altere `ProjectSettings/URPProjectSettings.asset` casualmente (o Editor às
  vezes o modifica sozinho; reverta essas mudanças).
- Não há compilador Unity no terminal: C# só pode ser revisado estaticamente.
  Peça ao usuário para validar Console/Play Mode. Testes EditMode ficam em
  `Assets/Tests/Editor/`.
- A estética importa (apresentação acadêmica): casas voltadas para as ruas,
  árvores ao fundo/esquinas, semáforos realistas. Como o entorno aparece nas
  imagens RGB, mudanças visuais exigem conferir capturas das três câmeras antes
  de gerar dataset ou avaliar visão.

## Ambiente e dependências

- Python 3.12 no venv da raiz: `../.venv/bin/python` (a partir de `python/`).
- Dependências pinadas em `python/requirements.txt` (`traci`/`sumolib` 1.26.0,
  `torch` 2.11.0, `ultralytics` 8.4.48, OpenCV, NumPy, PyYAML).
- SUMO precisa estar no `PATH` (`SUMO_HOME` definido). Os arquivos da rede foram
  gerados com SUMO 1.26; confira a versão local com `sumo --version`.
- Modelos e resultados são artefatos locais ignorados (`*.pt`, `runs/`,
  `results/*`). Verifique se existem antes de rodar experimentos:
  - detector YOLO ajustado: `runs/results/models/yolov8n-unity-run-002-mask/weights/best.pt`
    (classe única → sempre passe `--classes 0`; o padrão `2,3,5,7` é para COCO);
  - checkpoints DQN: `results/models/visual-dqn-sp*.pt`.
- `TEMP_*.txt` na raiz são arquivos locais (ignorados) com comandos longos para
  copiar/colar — o usuário prefere esse formato quando a CLI fica extensa.

## Comandos

Todos a partir de `python/`:

```bash
# Testes unitários (rápidos, sem SUMO/Unity)
../.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
../.venv/bin/python -m unittest discover -s tests -p 'test_visual_state.py'   # um módulo
# (tests/ não tem __init__.py: "unittest tests.test_x" não funciona)

# Sanidade SUMO (sem Unity)
../.venv/bin/python -m experiments.test_sp_traci --config configs/sp.yaml

# SUMO -> Unity (Unity em Play Mode na cena SPImport)
../.venv/bin/python -m experiments.test_sumo_to_unity --config configs/sp.yaml --steps 120 --send-interval 0.1

# Baseline de tempo fixo (sem Unity)
../.venv/bin/python -m experiments.run_fixed_time_baseline --config configs/sp.yaml --steps 100 --seed 201 \
  --output ../results/evaluation/fixed-time-baseline-test-seed-201.json

# Controlador visual (Unity em Play Mode). Sem --dqn-model = heurístico; com = DQN.
../.venv/bin/python -m experiments.run_visual_controller --config configs/sp.yaml --steps 100 --seed 201 \
  --send-interval 0.1 --camera-ids south,east,west \
  --model ../runs/results/models/yolov8n-unity-run-002-mask/weights/best.pt --classes 0 \
  --confidence 0.15 --frame-rate 1 --track-match-threshold 0.6 \
  --dqn-model ../results/models/visual-dqn-sp-best.pt \
  --debug-output-dir ../results/vision/visual-dqn-test-seed-201 \
  --decision-output ../results/logs/visual-dqn-decisions-test-seed-201.jsonl \
  --metrics-output ../results/evaluation/visual-dqn-metrics-test-seed-201.json

# Comparação de dois JSONs de métricas
../.venv/bin/python -m experiments.compare_control_experiments \
  --baseline <a.json> --visual-adaptive <b.json> --output <saida.json>

# Pré-treino do DQN v2 só com SUMO (~12 s por episódio de 2100 steps)
../.venv/bin/python -m experiments.pretrain_dqn_sumo --double-dqn

# Avaliar ciclo fixo, max-pressure e checkpoints v2 com percepção oráculo (só SUMO)
../.venv/bin/python -m experiments.evaluate_policies_sumo --scenario calibrated \
  --dqn-model ../results/models/dqn-v2-pretrain-best.pt --output ../results/evaluation/policies-sumo-oracle-calibrated.json

# Todas as versões (linha de base, v1, v1.1, v2, max-pressure) no mesmo ambiente
../.venv/bin/python -m experiments.compare_versions --scenario calibrated --perception oracle   # só SUMO
../.venv/bin/python -m experiments.compare_versions --scenario calibrated --perception visual   # Unity em Play Mode

# Política v2 com visão (Unity em Play Mode) + log visão × oráculo por step
../.venv/bin/python -m experiments.run_visual_policy --policy dqn --dqn-model <checkpoint-v2> --seeds 1001
../.venv/bin/python -m experiments.evaluate_lane_features --step-log <log.jsonl> --dqn-model <checkpoint-v2>

# Ajuste fino visual a partir do pré-treino (Unity em Play Mode; horas)
../.venv/bin/python -m experiments.finetune_dqn_visual --init-checkpoint ../results/models/dqn-v2-pretrain-best.pt

# Conferir ROIs de faixa × lanes SUMO (sem SUMO/Unity)
../.venv/bin/python -m experiments.check_lane_geometry

# Treino legado do DQN v1 (longo; exige Unity em Play Mode e YOLO). Confira --help antes.
../.venv/bin/python -m experiments.train_visual_dqn --help
```

Sem `--seed`, o SUMO usa `experiment.seed` do `sp.yaml`. No cenário `original`
os fluxos `perHour` são equiespaçados e a seed quase não muda a demanda; no
`calibrated` as chegadas são Poisson e cada seed gera uma demanda diferente.

## Convenções de código

- Python: `from __future__ import annotations`, type hints, `dataclass`
  (frequentemente `frozen`/`slots`), docstrings curtas em português, módulos
  pequenos. Entry points são módulos em `experiments/` com `argparse`, rodados
  via `python -m`, e imprimem linhas `chave=valor` (ex.: `control_complete ...`).
- Sempre feche TraCI em `finally` (`SumoClient.close()`).
- Testes com `unittest` + `numpy.testing`; todo contrato novo (features, métricas,
  protocolo) deve ganhar teste antes de ser consumido pelo DQN.
- Commits em português no estilo Conventional Commits (`feat:`, `docs:`, `fix:`).
  Não reescreva histórico já publicado; trabalhe em branch nova para mudanças
  de contrato.
