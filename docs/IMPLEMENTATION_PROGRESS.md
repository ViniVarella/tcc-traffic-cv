# Progresso de Implementação

Este arquivo registra o andamento prático do plano descrito em `docs/IMPLEMENTATION_GUIDE.md`.

## Status Geral

- Marco 1: concluído
- Marco 2: concluído
- Marco 3: concluído
- Marco 4: concluído
- Marco 5: implementado
- Arquitetura revisada documentada: concluído
- Levantamento do SUMO2Unity adicionado: concluído
- Pré-Marco 6: concluído (cenário SP importado, materializado e sincronizado
  dinamicamente por Python/TraCI; os veículos usam prefabs locais)
- Marco 6: concluído (três câmeras — `south`, `east` e `west` — calibradas,
  com ROIs de aproximação e faixa exportadas em JSON)
- Marco 7: concluído (captura TCP Unity -> Python alinhada por `step_id` e
  `camera_id`, validada por 100 steps)
- Marco 8: concluído (YOLO + ByteTrack + ROIs executados sobre os 100 frames)
- Marco 9: concluído (comparação das contagens visuais contra E2 por faixa
  executada em 100 steps)
- Marco 10: concluído (captura sintética com máscaras de instância, conversão
  para YOLO e primeiro fine-tuning do detector)
- Marco 11 em diante: pendentes (validação com ROIs alinhadas aos E2,
  integração do estado visual ao controlador e DQN)

## Avaliação visão versus E2 — cenário SP

Status: implementada e executada em 100 steps com as câmeras e calibrações
atuais.

O E2 permanece exclusivamente como verdade de terreno de avaliação. A decisão
online futura continua recebendo somente a saída visual. A comparação atual é
diagnóstica, não uma medida direta de erro do detector: os E2 observam apenas
20 m antes do cruzamento, enquanto as ROIs operacionais podem ter extensão
maior. Para uma métrica estrita, será criada uma ROI de avaliação alinhada a
cada E2, preservando as ROIs operacionais.

## Dataset sintético para fine-tuning do YOLO

Status: concluído para o primeiro ciclo de treinamento. A captura `run-002`
gerou 4.500 imagens (500 steps x 9 câmeras), 31.155 caixas visíveis derivadas
das máscaras e splits de 3.610/451/439 imagens para treino/validação/teste.
Os splits desse primeiro ciclo distribuem frames vizinhos da mesma execução;
por isso, as métricas de validação medem aderência ao cenário sintético atual,
e não generalização independente.

`VehicleGroundTruth` é anexado a cada objeto de veículo criado por
`VehicleManager`. A cada captura, a Unity transmite a identidade SUMO e uma
cor de instância única, além do JPEG RGB e de uma máscara PNG onde somente os
pixels visíveis de cada veículo recebem essa cor. Esse metadado é destinado
apenas à geração offline do dataset; nunca é fornecido ao DQN. A caixa YOLO é
calculada a partir desses pixels visíveis, portanto não inclui partes ocluídas
nem a área vazia dos bounds 3D projetados.

Para capturar JPEGs e seus rótulos JSON lado a lado, com `SPImport` em Play
Mode, execute:

```bash
cd /Users/vmvarella/PycharmProjects/tcc-traffic-cv/python
../.venv/bin/python -m experiments.test_sumo_to_unity \
  --config configs/sp.yaml \
  --steps 100 \
  --send-interval 0.1 \
  --receive-frames \
  --expected-cameras south,west,east \
  --vehicle-labels-output-dir ../results/ground_truth/unity-vehicle-boxes \
  --instance-masks-output-dir ../results/masks/unity-vehicle-boxes
```

Os JPEGs ficam em `results/frames/unity/<camera>/`; os JSONs equivalentes em
`results/ground_truth/unity-vehicle-boxes/<camera>/` e as máscaras em
`results/masks/unity-vehicle-boxes/<camera>/`. Os três conjuntos são
reiniciados ao iniciar a execução. Em seguida, monte um diretório YOLO novo:

```bash
cd /Users/vmvarella/PycharmProjects/tcc-traffic-cv/python
../.venv/bin/python -m experiments.build_unity_yolo_dataset \
  --frames-root ../results/frames/unity \
  --labels-root ../results/ground_truth/unity-vehicle-boxes \
  --masks-root ../results/masks/unity-vehicle-boxes \
  --output-dir ../results/datasets/unity-vehicles-v1
```

O conversor cria `images/{train,val,test}`, `labels/{train,val,test}` e
`data.yaml`, com a única classe `vehicle`. Ele se recusa a sobrescrever um
dataset existente. Sem `--masks-root`, ele mantém o modo legado por projeção
de bounds 3D; para o fine-tuning, use sempre as máscaras de instância.

Validação em 2026-08-30: 100 JPEGs e 100 JSONs correspondentes foram recebidos
para cada uma das câmeras `south`, `east` e `west`, sem caixas fora do intervalo
normalizado. O dataset de fumaça `unity-vehicles-v1` foi convertido com 300
imagens, 1.963 caixas e divisão determinística de 236 treino / 31 validação /
33 teste. Esse volume ainda não é suficiente para o fine-tuning final.

Para ampliar a diversidade sem modificar as três câmeras operacionais, a Unity
possui o perfil **Traffic Vision > Dataset**. A ação **Create SP Dataset
Cameras** cria seis variações fisicamente plausíveis, duas para cada sentido,
sob `SP Dataset Cameras`. Elas começam com `Capture Enabled` desligado e por
isso não interferem com `south`, `east` e `west`. Antes de uma coleta sintética,
use **Enable SP Dataset Capture** e execute a captura incluindo todas as nove
câmeras:

```bash
cd /Users/vmvarella/PycharmProjects/tcc-traffic-cv/python
../.venv/bin/python -m experiments.test_sumo_to_unity \
  --config configs/sp.yaml \
  --steps 500 \
  --send-interval 0.1 \
  --receive-frames \
  --expected-cameras south,east,west,south_ds_left,south_ds_right,east_ds_near,east_ds_far,west_ds_near,west_ds_far \
  --frame-output-dir ../results/frames/unity-dataset-run-002 \
  --vehicle-labels-output-dir ../results/ground_truth/unity-dataset-run-002 \
  --instance-masks-output-dir ../results/masks/unity-dataset-run-002
```

Depois da coleta, use **Disable SP Dataset Capture** antes de voltar ao teste
operacional. Cada execução deve usar uma seed/demanda SUMO distinta; os splits
finais de treino, validação e teste deverão separar execuções inteiras, e não
frames vizinhos da mesma execução.

O perfil `python/configs/sp.yaml` registra o mapeamento verificado pela
geometria da rede e pelas ROIs salvas:

- `south/lane_0..lane_3` -> `E3_0..E3_3` (`e2_4`, `e2_3`, `e2_1`, `e2_2`);
- `east/lane_0..lane_1` -> `E2_0..E2_1` (`e2_6`, `e2_5`);
- `west/lane_0` -> `E6_0` (`e2_0`).

Para produzir uma nova execução de 100 steps com frames e referência E2, deixe
a cena `SPImport` em Play Mode e rode:

```bash
cd /Users/vmvarella/PycharmProjects/tcc-traffic-cv/python
../.venv/bin/python -m experiments.test_sumo_to_unity \
  --config configs/sp.yaml \
  --steps 100 \
  --send-interval 0.1 \
  --receive-frames \
  --expected-cameras south,west,east \
  --ground-truth-output ../results/ground_truth/sp-e2.jsonl
```

O comando limpa as pastas de frames `east`, `south` e `west`; o arquivo E2 é
reiniciado no começo da execução. Em seguida, rode a visão e a comparação:

```bash
../.venv/bin/python -m experiments.test_unity_vision \
  --frames-root ../results/frames/unity \
  --calibration-dir ../unity/TrafficVisionUnity/Assets/Calibration \
  --output-dir ../results/vision/unity-realistic-prefabs \
  --camera-ids south,east,west \
  --max-steps 100 \
  --frame-rate 1

../.venv/bin/python -m experiments.evaluate_unity_vision \
  --config configs/sp.yaml \
  --vision-summary ../results/vision/unity-realistic-prefabs/summary.jsonl \
  --ground-truth ../results/ground_truth/sp-e2.jsonl \
  --output-dir ../results/evaluation/unity-realistic-prefabs
```

A avaliação gera `per_lane.csv` (comparação por step/faixa), `metrics.csv` e
`summary.json`. As métricas usam a contagem visual bruta da ROI contra
`E2.vehicle_count`; `halting_count` e `occupancy` são preservados no CSV, mas
não são tratados como equivalentes a uma contagem de objetos.

ByteTrack é a fonte preferencial quando confirma IDs temporais. Em fluxo livre
ou em uma câmera distante, ele pode não confirmar nenhum ID apesar de haver
detecções válidas; nesse caso, o pipeline usa as detecções brutas já filtradas
pela ROI principal como fallback daquele step, em vez de registrar zero
artificialmente. A captura SP fornece um JPEG por segundo simulado, portanto o
`frame-rate` correto é `1`.

### Primeiro fine-tuning concluído

O modelo `yolov8n.pt` foi ajustado por 50 épocas com o dataset
`unity-vehicles-run-002-mask`, em MPS/Apple Silicon. O checkpoint selecionado
é `runs/results/models/yolov8n-unity-run-002-mask/weights/best.pt`; no
dataset de validação desse mesmo ciclo, alcançou `mAP50 = 0,98478` e
`mAP50-95 = 0,95267`. Esses valores devem ser lidos com a limitação do split
por frames vizinhos descrita acima.

O modelo ajustado tem somente a classe `0` (`vehicle`). Portanto, toda
inferência com ele deve incluir `--classes 0`; os IDs COCO usados pelo modelo
pré-treinado não são aplicáveis. A avaliação offline atual não exige Unity em
Play Mode, pois trabalha sobre os JPEGs já capturados:

```bash
cd /Users/vmvarella/PycharmProjects/tcc-traffic-cv/python
../.venv/bin/python -m experiments.test_unity_vision \
  --frames-root ../results/frames/unity \
  --calibration-dir ../unity/TrafficVisionUnity/Assets/Calibration \
  --output-dir ../results/vision/unity-finetuned-run-002-class0-new-south-camera \
  --model ../runs/results/models/yolov8n-unity-run-002-mask/weights/best.pt \
  --classes 0 \
  --camera-ids south,east,west \
  --max-steps 100 \
  --frame-rate 1 \
  --track-match-threshold 0.6

../.venv/bin/python -m experiments.evaluate_unity_vision \
  --config configs/sp.yaml \
  --vision-summary ../results/vision/unity-finetuned-run-002-class0-new-south-camera/summary.jsonl \
  --ground-truth ../results/ground_truth/sp-e2.jsonl \
  --output-dir ../results/evaluation/unity-finetuned-run-002-class0-new-south-camera
```

Na execução atual de 100 steps, a comparação diagnóstica com E2 produziu MAE
médio de `0,6400` e acerto exato médio de `62,57%`. O valor padrão
`--track-match-threshold 0.6` foi mantido: o teste com `0.8` tornou a associação
mais permissiva, mas piorou essas métricas (`MAE 0,7071`; acerto `61,14%`).
Nas imagens anotadas, uma caixa vermelha `d:<confiança>` é uma detecção YOLO
ainda sem track; uma caixa verde `id:<n>` é uma associação confirmada pelo
ByteTrack. Elas não são as ROIs verdes.

Importante: os E2 do cenário cobrem somente 20 m de cada faixa perto do
cruzamento. A ROI visual usada pelo DQN pode ser maior; nesse caso, a primeira
comparação também expõe a diferença de área observada. Para uma medida pura de
detecção, a próxima calibração deve criar uma ROI de avaliação limitada ao
mesmo trecho do E2, sem substituir a ROI operacional de fila.

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
- manter rastreamento temporal; a inferência Unity usa ByteTrack para
  equivalência com o SimJamCV;
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
- rastreamento com IDs persistentes; a inferência Unity usa ByteTrack;
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
- a arquitetura final documentada passa a usar três câmeras Unity de entrada (`south`,
  `east`, `west`) com ROIs por câmera;
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

- o script `python -m experiments.test_sumo_traci` roda com a configuração atual do projeto;
- o cenário SUMO configurado atualmente é `../sumo/fictional/RL.sumocfg`;
- o semáforo monitorado atualmente é `Node2`;
- a execução de validação avançou steps da simulação com sucesso e retornou:
  - `sim_time` crescente de `0.10` até `0.50`;
  - `active_vehicles=3` nos steps observados;
  - `tls_phase=0`;
  - `tls_state=GGGGgrrrrrGGGGgrrrrr`;
- o teste foi atualizado para validar explicitamente a troca manual de fase para `traffic_light.phases.ew_green`;
- após os steps iniciais em `tls_phase=0`, o script solicitou `ew_green=2`;
- após a troca, os steps seguintes retornaram:
  - `tls_phase=2`;
  - `tls_state=rrrrrGGGGgrrrrrGGGGg`;
- isso confirma que o Python consegue mudar manualmente o semáforo `Node2` de NS green para EW green via TraCI usando o mapeamento do `config.yaml`.

Observações:

- o nome do cenário SUMO atual do projeto é `RL`, não `intersection`;
- o caminho configurado em `python/config.yaml` é `../sumo/fictional/RL.sumocfg`;
- o teste TraCI já está funcional no caminho feliz com a configuração atual do repositório;
- `ground_truth.py` continua reservado para avaliação futura, sem alimentar qualquer controlador.

## Marco 4 — Comunicação Python -> Unity

Status: concluído

Objetivo atendido:

- implementar a primeira comunicação Python -> Unity com JSON simples;
- manter Python como orquestrador do estado enviado;
- validar manualmente a recepção de `step` e `step_id` no lado Unity.

Entregas realizadas:

- implementação inicial de `python/bridge/unity_comm.py` com envio UDP real;
- atualização de `python/bridge/protocol.py`;
- atualização de `python/bridge/serialization.py`;
- criação de `python/experiments/test_unity_comm.py`;
- criação de `unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs`;
- atualização do `README.md` com instruções mínimas do teste Python -> Unity.

Capacidades disponíveis neste marco:

- construir `UnityBridge` a partir do `config.yaml`;
- enviar estados fake por UDP usando `unity.state_host` e `unity.state_port`;
- serializar JSON com:
  - `step`
  - `step_id`
  - `sim_time`
  - `vehicles`
  - `traffic_lights`
- validar manualmente o recebimento do estado no Console da Unity.

Validação realizada:

- `python -m compileall python`
- execução com a `.venv` do projeto:
  - `cd python`
  - `..\\.venv\\Scripts\\python.exe -m experiments.test_unity_comm`
- execução com a `.venv` do projeto:
  - `cd python`
  - `..\\.venv\\Scripts\\python.exe -m experiments.test_sumo_traci`
- Unity 6.3 LTS instalada.
- projeto Unity criado em `unity/TrafficVisionUnity`.
- `PythonStateReceiver.cs` anexado a um `GameObject` na cena.
- teste executado:
  - `cd python`
  - `python -m experiments.test_unity_comm`

Resultado da validação atual:

- `python -m experiments.test_unity_comm` envia cinco estados fake via UDP;
- o terminal Python mostra `step=0` até `step=4`;
- cada mensagem inclui `step`, `step_id`, `sim_time`, `vehicles` e `traffic_lights`;
- Python enviou estados fake para `127.0.0.1:5004` via UDP;
- a Unity recebeu os estados e registrou no Console:
  - `step=0 step_id=0`
  - `step=1 step_id=1`
  - `step=2 step_id=2`
  - `step=3 step_id=3`
  - `step=4 step_id=4`
- `python -m experiments.test_sumo_traci` continua funcionando e nao foi quebrado.

Observações:

- a comunicação Python -> Unity com JSON fake está validada;
- este marco cobre apenas Python -> Unity;
- a recepção Unity -> Python com frames JPEG por TCP continua fora do escopo;
- ainda não há integração com estado real do SUMO neste marco;
- ainda não há captura de frames Unity -> Python;
- a Unity continua proibida de se conectar diretamente ao SUMO.

## Marco 5 — Integração SUMO -> Python -> Unity

Status: concluído

Objetivo atendido:

- substituir o estado fake por estado real extraído do SUMO;
- manter Python como único cliente TraCI;
- enviar estado real por UDP para a Unity;
- atualizar uma visualização básica da cena na main thread da Unity.

Entregas realizadas:

- atualização de `python/sumo/state_extractor.py` com conversão simples SUMO -> Unity;
- criação de `python/experiments/test_sumo_to_unity.py`;
- reutilização de `python/bridge/unity_comm.py` para envio do estado real;
- atualização de `unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs` para aplicar estado na main thread;
- criação de `unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/VehicleManager.cs`;
- criação de `unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/TrafficLightVisualController.cs`;
- atualização do `README.md` com instruções do teste SUMO -> Python -> Unity.

Capacidades disponíveis neste marco:

- iniciar SUMO e extrair estado real do cenário `RL`;
- serializar esse estado com `step`, `step_id`, `sim_time`, `vehicles` e `traffic_lights`;
- enviar o estado para a Unity via UDP;
- criar cubos para veículos ainda não vistos;
- atualizar posição e rotação de veículos existentes;
- ocultar veículos que não aparecem mais no estado corrente;
- registrar no Console da Unity o step recebido e a quantidade de veículos.

Validação realizada:

- `python -m compileall python`
- `python -m experiments.test_unity_comm`
- `python -m experiments.test_sumo_traci`
- `python -m experiments.test_sumo_to_unity`
- Unity aberta com a cena em Play;
- `PythonStateReceiver`, `VehicleManager` e `TrafficLightVisualController` criados fora do Play Mode;
- `VehicleManager` conectado ao campo correspondente do `PythonStateReceiver`;
- execução do comando:
  - `cd python`
  - `python -m experiments.test_sumo_to_unity`

Resultado da validação atual:

- os testes Python existentes continuam funcionando;
- Python enviou estados reais do SUMO para Unity via UDP;
- foram enviados steps de `0` a `19`;
- `sim_time` avançou de `0.10` até `2.00`;
- cada estado continha `vehicles=3` e `traffic_lights=1`;
- a Unity recebeu os estados e registrou no Console mensagens com `step`, `step_id`, `sim_time` e quantidade de veículos;
- a Unity criou e atualizou cubos cinzas representando veículos na cena.

Observações:

- este marco valida apenas SUMO -> Python -> Unity com estado real;
- a visualização ainda é básica, com cubos em vez de modelos realistas;
- ainda não há ruas ou cenário importado via SUMO2Unity;
- ainda não há captura de frames Unity -> Python;
- ainda não há YOLO sobre frames da Unity;
- ainda não há ROI por câmera nem controle adaptativo;
- a Unity continua proibida de se conectar diretamente ao SUMO.

## Próximos Marcos

### Pré-Marco 6 — Preparar o cenário Unity com base no SUMO2Unity

Status: em andamento.

Entregas realizadas:

- criação de `SumoRoadNetworkImporter`, adaptado do importador estático do
  Sumo2Unity, para gerar faixas, cruzamentos e polígonos dentro de
  `unity/TrafficVisionUnity`;
- cópia da rede SP para
  `unity/TrafficVisionUnity/Assets/Sumo/SP/Cruzamento.net.xml`;
- criação da ação de Editor `Traffic Vision > SUMO > Create SP Import Scene`,
  que prepara uma cena com luz, câmera de visão geral e o
  `SumoRoadNetworkImporter` apontando para a rede SP;
- criação e salvamento da cena `Assets/Scenes/SPImport.unity`, contendo a rede
  SP importada e a câmera aérea de inspeção;
- criação do Inspector `SumoRoadNetworkImporterEditor`, com ações de importar,
  regerar e limpar a rede gerada;
- parsing numérico com `CultureInfo.InvariantCulture`, incluindo `netOffset`,
  coordenadas, largura de faixa e polígonos;
- alinhamento do projeto Unity ao baseline do Sumo2Unity (Unity `6000.0.53f1`
  e URP `17.0.4`), com `manifest.json` e `packages-lock.json` idênticos aos do
  projeto de referência;
- preservação de `PythonStateReceiver`, `VehicleManager` e
  `TrafficLightVisualController`; nenhum código ZeroMQ do Sumo2Unity foi
  integrado.
- adição do cenário SP em `sumo/sp/`, composto por `Cruzamento.sumocfg`,
  `Cruzamento.net.xml`, `Cruzamento.rou.xml` e `Cruzamento.add.xml`;
- adição do modelo treinado em `models/dqn_traffic_model.keras`; ele ainda usa
  os sete detectores E2 definidos no cenário como entrada de referência.
- criação do perfil isolado `python/configs/sp.yaml`, com o TLS, as cinco fases,
  a ordem dos sete detectores E2 e o contrato de 26 entradas do DQN;
- criação de `python -m experiments.test_sp_traci`, que valida o cenário SP via
  TraCI sem iniciar Unity ou inferência do DQN.
- configuração `unity` no perfil SP e extensão de
  `python -m experiments.test_sumo_to_unity` para selecionar esse perfil,
  duração e intervalo de envio;
- criação da ação `Traffic Vision > SUMO > Configure SP Dynamic Sync`, que
  configura o receptor UDP, raiz de veículos e marcador visual do TLS na cena;
- criação da ação `Traffic Vision > SUMO > Configure SP Visuals`, com materiais
  persistentes de asfalto, junção e marcação, além de linhas tracejadas geradas
  a partir das geometrias das faixas;
- atualização dos veículos temporários: cor por tipo, marcador de frente e
  orientação compatível com os ângulos navegacionais do SUMO.
- criação das câmeras de tráfego `south`, `east` e `west`, com poses,
  resolução e ROIs persistentes na cena `SPImport`; a calibração `south` foi
  exportada em `Assets/Calibration/south-calibration.json`;
- captura da câmera após cada estado aplicado, codificação JPEG e envio TCP
  length-prefixed com `step_id`, `sim_time`, `camera_id` e tamanho do payload;
- listener TCP no `UnityBridge` e opção `--receive-frames` no experimento SP,
  que salva os JPEGs recebidos em subpastas por câmera, como
  `results/frames/unity/south/`;
- criação de `FrameBundleCollector`, que agrupa os JPEGs de `south`, `east` e
  `west` por `step_id`, preserva frames futuros em buffer e informa câmeras
  ausentes sem travar o experimento;
- exportação e validação das calibrações finais `south`, `east` e `west` em
  `Assets/Calibration/`, com respectivamente 4, 2 e 1 ROIs de faixa;
- bloqueio explícito da edição de ROIs durante Play Mode, pois alterações da
  calibração só podem ser persistidas fora da simulação.

Comando de captura multícâmera de referência (100 steps):

```bash
cd /Users/vmvarella/PycharmProjects/tcc-traffic-cv/python
../.venv/bin/python -m experiments.test_sumo_to_unity \
  --config configs/sp.yaml \
  --steps 100 \
  --send-interval 0.1 \
  --receive-frames \
  --expected-cameras south,west,east
```

Antes de abrir o listener TCP, o experimento limpa somente as subpastas das
câmeras esperadas (`results/frames/unity/south/`, `west/` e `east/`). Assim,
cada execução inicia com até 100 JPEGs novos por câmera, sem misturar frames de
execuções anteriores.

Inferência offline de referência, alinhada ao pipeline do SimJamCV:

```bash
cd /Users/vmvarella/PycharmProjects/tcc-traffic-cv/python
../.venv/bin/python -m experiments.test_unity_vision \
  --frames-root ../results/frames/unity \
  --calibration-dir ../unity/TrafficVisionUnity/Assets/Calibration \
  --output-dir ../results/vision/unity \
  --camera-ids south,east,west \
  --max-steps 100 \
  --frame-rate 1
```

Para cada câmera e step completo, o experimento executa YOLO, remove as
detecções fora da ROI externa, aplica NMS agnóstico de classe, atualiza um
ByteTrack independente e conta os tracks nas ROIs de faixa. Se nenhum track
for confirmado no step, usa as detecções filtradas como fallback. As imagens
anotadas e `summary.jsonl` ficam em `results/vision/unity/`.

Validação realizada:

- inicialização direta de `sumo/sp/Cruzamento.sumocfg` até o tempo simulado de
  2 segundos, concluída com `exit 0`;
- execução de `python -m experiments.test_sp_traci` em 2026-08-19: TLS
  `clusterJ0_J14_J2_J7` encontrado, sete E2 encontrados, fase inicial `0` e
  troca controlada confirmada para a fase `3`.
- validação manual no Unity em 2026-08-20: a cena `SPImport` carregou a rede
  com 22 faixas e 1 cruzamento; a câmera aérea renderizou a geometria; a ação
  `Clear generated road network` removeu toda a rede e uma nova importação a
  recriou uma única vez, sem duplicação no `Hierarchy`.
- validação manual da sincronização SUMO -> Python/TraCI -> UDP/JSON -> Unity
  em 2026-08-20: a Unity recebeu estados até o `step_id` 120, com 24--29
  veículos por estado, e os veículos permaneceram alinhados às vias SP.
- validação manual visual em 2026-08-20: as linhas tracejadas, os materiais de
  via e os veículos orientados foram renderizados durante a mesma simulação.
- validação manual em 2026-08-20 da câmera `south`: pose final
  `(2.984, 5.25, -16.34)`, FOV de `48°`, ROI externa e quatro ROIs de faixa
  foram exportadas; os frames JPEG associados aos steps chegaram ao Python via
  TCP e foram salvos para depuração.
- calibração manual posterior das três câmeras de entrada: `south` em
  `(4.8, 5.25, -13.2)` com rotação `(22.613, -160, 0)`, FOV `38.8°` e quatro
  ROIs de faixa; `east` em `(12.1, 5.07, -1.6)` com rotação
  `(18.343, 123.797, -2.175)`, FOV `28.7°` e duas ROIs; e `west` em
  `(-17.46, 5, -4.75)` com rotação `(14.902, -63.164, 0)`, FOV `25.7°` e uma
  ROI. Todas usam resolução `1280x720`; as ROIs foram recalibradas e os JSONs
  exportados após esse ajuste de enquadramento.

Escopo previsto:

- registrar snapshots E2 junto da próxima captura e executar a comparação
  visual por faixa; o ramo `north` é saída da mão única do `south` e não será
  observado por câmera.
- manter os semáforos 3D como item visual opcional, sem bloquear a percepção
  das câmeras;
- não executar `Sumo2UnityTool.exe` nem os scripts ZeroMQ originais, pois o
  Python do TCC continua sendo o único cliente TraCI;
- validar o alinhamento visual para o mesmo `step_id` antes de capturar frames.

Referência: `docs/SUMO2UNITY_INTEGRATION.md`.

### Marco 6 — Calibração de câmeras e ROIs

Status: em andamento — pipeline offline YOLO + ROI externa + ByteTrack + ROIs
de faixa implementado e validado tecnicamente em 100 steps das três câmeras.
Os cubos temporários foram substituídos por prefabs realistas Alma/Elka/Elora,
o que permitiu ao `yolov8n.pt` detectar veículos. A validação quantitativa
contra TraCI/E2 continua obrigatória antes de usar essas contagens no DQN.

Validação posterior com os prefabs realistas:

- 100 JPEGs válidos por câmera, steps `0..99`;
- saída anotada e `summary.jsonl` em `results/vision/unity-realistic-prefabs/`;
- South: 393 detecções em 81/100 steps, máximo de 11 por frame;
- East: 274 detecções em 75/100 steps, máximo de 6 por frame;
- West: 16 detecções em 16/100 steps, máximo de 1 por frame.

Esses números comprovam a inferência ponta a ponta, não a precisão final. A
próxima entrega deve confrontar, por `step_id` e faixa, a contagem visual com a
extraída pelo SUMO/TraCI (E2 como ground truth).

Entregas realizadas:

- criação de `TrafficCameraCalibration`, componente persistente para uma
  câmera com ID, resolução, ROI externa e ROIs de faixa normalizadas;
- criação de `CameraRoiCalibrationWindow` em `Traffic Vision > Camera ROI
  Calibration`, com preview por `RenderTexture` e coleta de quatro cliques;
- validação de quadriláteros cruzados, contenção dentro da ROI externa e
  ausência de sobreposição entre faixas;
- criação de testes de Edit Mode para os casos válido, fora da ROI externa,
  sobreposição e quadrilátero cruzado.

Validação realizada:

- verificação estática de balanceamento de chaves nos novos scripts;
- execução manual do Test Runner de Edit Mode em 2026-08-19;
- relatório `unity/TestResults_20260819_133851.xml`: 13 testes executados,
  13 aprovados e nenhuma falha, incluindo os casos de lados cruzados,
  sobreposição e pontos fora da ROI principal.

Escopo previsto:

- criar três câmeras de entrada (`south`, `east`, `west`) e registrar sua pose,
  FOV e resolução; o ramo `north` é apenas saída e não terá câmera;
- criar ferramenta visual para clicar quatro cantos da ROI externa de cada
  aproximação e quatro cantos de cada ROI de faixa;
- salvar coordenadas normalizadas; rejeitar ROIs fora da região externa ou com
  sobreposição entre faixas.

### Marco 7 — Captura Unity -> Python

Concluído para a validação offline: a captura TCP agrupa frames de `south`,
`east` e `west` por `step_id`; o experimento de 100 steps foi validado
manualmente após a reconstrução do cache Unity.

Escopo previsto:

- capturar `RenderTexture` após aplicar cada `step_id`;
- enviar JPEGs por TCP com `step_id`, `sim_time` e `camera_id`;
- validar que o Python recebe apenas frames correspondentes ao estado enviado.

### Marco 8 — Percepção visual e estado do DQN

Em andamento.

Escopo previsto:

- executar YOLO, filtro pela ROI externa, ByteTrack e ROIs de faixa nos frames
  Unity;
- converter as contagens por faixa em um vetor de estado visual;
- manter E2 apenas como ground truth de avaliação;
- treinar novamente o DQN para o novo vetor visual.

### Marco 9 em diante

Pendentes conforme o guia:

- controlador semafórico;
- experimentos comparativos.
