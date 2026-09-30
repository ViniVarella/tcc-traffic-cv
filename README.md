# TCC Traffic CV

Sistema experimental de controle semafórico adaptativo baseado em visão
computacional, avaliado em um cruzamento real de São Paulo (cenário `sp`).

O SUMO gera a dinâmica do tráfego, a Unity renderiza a cena 3D e três câmeras
virtuais, o YOLO detecta os veículos nos frames, o ByteTrack os associa entre
frames e um DQN decide, a partir dessas estimativas visuais, quando manter ou
trocar o verde. **A política de controle não usa sensores perfeitos do SUMO**:
os dados internos do SUMO servem para renderização, sincronização, recompensa
de treino e avaliação.

**Versão atual: v2** — DQN com cinco features visuais por faixa, pré-treinado
só no SUMO e executado com a câmera. No mesmo ambiente de avaliação (demanda
medida por drone, Leste saturado), é a única versão que dá mais verde ao
Leste. Com isso, reduz a espera e zera a fila de entrada, enquanto a v1 e a
v1.1 deixam centenas de veículos presos fora da rede (ver
[Comparação no mesmo ambiente](#comparação-no-mesmo-ambiente)).

## Arquitetura

```text
SUMO ──TraCI──> Python ──UDP/JSON (estado)──> Unity (veículos, semáforos, câmeras)
                  ^                                  │
                  │                 TCP/JPEG por step_id (câmeras south/east/west)
                  │                                  v
     DqnTrafficController <── DQN <── features por faixa <── YOLO + ByteTrack + ROIs
```

- Simulação `step-based`: o Python avança o SUMO com `simulationStep()` (step
  de 1 s no cenário SP). As métricas usam o tempo simulado, não o relógio.
- O Python é o único cliente TraCI; a Unity só renderiza o estado recebido e
  devolve um JPEG por câmera a cada step, identificado por `step_id` e
  `camera_id`.
- Três câmeras operacionais: `south`, `east` e `west`. A aproximação norte é
  só de saída e não é observada.
- Cada câmera tem uma ROI de aproximação e ROIs por faixa (7 faixas no total).
- Duas fases de verde: `South` e `East + West`. A camada de segurança impõe
  verde mínimo de 10 s, verde máximo de 40 s, amarelo de 3 s e *all-red* de
  1 s; a política só escolhe manter ou trocar.
- Ground truth do SUMO entra em logs, avaliação e recompensa de treino, nunca
  como entrada da política implantada.

## Evolução por versão

| Versão | Período | Política | Entrada da política | O que mudou |
|---|---|---|---|---|
| Linha de base | — | Ciclo fixo 40/40 | — | Referência: nunca pede troca; o verde máximo alterna as fases |
| **v1** | 2026-09-02 | Heurística por fila visual | Contagem por faixa | Primeiro controle em malha fechada pela câmera |
| **v1.1** | 2026-09-04 | DQN (estado v1, 13 entradas) | Contagem por faixa + fase | Troca a regra fixa por uma política aprendida |
| **v2** | 2026-09-29 | DQN (estado v2, 41 entradas) | Contagem, parados, ocupação, velocidade e espera por faixa + fase | Features cinemáticas, pré-treino só no SUMO, decisões só quando têm efeito, cenário calibrado |

### v1 — Controle visual heurístico

`TrafficController` soma as contagens visuais de `South` e de `East + West` e
troca o verde quando a fila oposta supera a atual por uma margem de 1 veículo,
ou quando a fila atual está vazia. Verde mínimo e máximo são respeitados.

### v1.1 — DQN visual, estado v1

DQN em PyTorch (`DqnAgent`, MLP 64×2) com 13 entradas: contagens normalizadas
das 7 faixas, fase em *one-hot* e tempo da fase. A recompensa era a variação
da espera acumulada do TraCI. O treino rodou nas seeds 1–50 com a Unity no
loop.

**Por que foi substituída:** a política colapsou em "trocar assim que o verde
mínimo permite". A análise posterior encontrou as causas:

- O checkpoint "melhor" era o do episódio 4, com 240 passos de gradiente e
  ε≈0,98: o ε decaía por episódio e ainda estava em ≈0,78 no fim do treino, e
  a validação empatava.
- A recompensa ficava positiva quando um veículo com espera saía da rede.
- As transições eram gravadas mesmo quando a ação era ignorada.

### v2 — DQN visual por faixa, estado v2

- **Estado v2 (41 entradas).** Para cada faixa: contagem, parados (< 1,39 m/s
  por ≥ 1 s), ocupação, velocidade média e espera, normalizados pela
  capacidade da ROI, mais fase e tempo. A base de cada bbox é projetada pela
  homografia da ROI de faixa, e um rastreador cinemático por câmera calcula
  velocidade e tempo parado.
- **Pré-treino só no SUMO.** Um oráculo TraCI produz as mesmas features a
  partir das posições reais no mesmo trecho das ROIs; um teste de paridade
  garante a equivalência. Cada episódio (300 s de aquecimento + 1800 s) leva
  ~6 s, contra ~1,5 s por step com a Unity. Foram 40 episódios, com ε linear
  por decisão, Double DQN e seleção de checkpoint só após treino mínimo.
- **Decisões apenas quando têm efeito.** A política decide em verde, entre o
  verde mínimo e o máximo, a cada 5 s. As transições são SMDP, e a recompensa
  é um nível em [−1, 0] com parados, espera e fila de inserção.
- **Cenário calibrado.** A demanda foi medida nos vídeos de drone: o Leste fica
  saturado (v/c≈1,0), com chegadas Poisson e inserção realista.
- **Correções que valem para todas as versões.** O Python passa a manter o
  controle das fases no SUMO mesmo quando falta um frame (antes o programa
  estático podia pular o *all-red*), e a fila de inserção passou a ser medida.
- Um ajuste fino com a Unity no loop (10 episódios) piorou a validação visual.
  A política final é a pré-treinada no SUMO, usada direto com a câmera
  (zero-shot).

## Comparação no mesmo ambiente

Todas as versões rodam no **mesmo ambiente**:

- mesmo cenário, seeds inéditas `201`–`203`, 300 s de aquecimento e 1800 s
  controlados;
- mesma camada de segurança, mesmas métricas e a **mesma percepção** — as
  features por faixa do oráculo TraCI ou as da câmera.

Só a lógica de decisão muda. As regras de cada versão estão em
`python/experiments/version_policies.py`, e o comparador é
`python -m experiments.compare_versions`.

**Diferença deliberada em relação às execuções originais:** a v1 e a v1.1
contavam os veículos pelo centro da bbox com média móvel. Aqui elas recebem a
mesma contagem por faixa usada pela v2. Também decidem a cada 1 s, como
faziam originalmente.

### Percepção oráculo (só SUMO)

**Cenário calibrado** (Leste saturado — onde a adaptação importa):

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde Leste/Oeste | Trocas |
|---|---:|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 16,1 s | 36,2 s | 1503 | 97 | 50% | 0 |
| v1 (heurística) | 12,2 s | 36,9 s | 1349 | 254 | 52% | 126 |
| v1.1 (DQN estado v1) | 12,9 s | 38,0 s | 1311 | 290 | 50% | 129 |
| **v2 (DQN estado v2)** | **9,1 s** | **30,9 s** | **1598** | **6** | **66%** | 93 |
| max-pressure (referência) | 12,8 s | 37,5 s | 1317 | 284 | 50% | 127 |

A v1 e a v1.1 alternam o verde no ciclo mínimo e dividem 50/50. Com o Leste
saturado, escoam **menos** veículos que o ciclo fixo e deixam 250–290 veículos
presos fora da rede. A espera média delas parece melhor que a do ciclo fixo só
porque os veículos presos não entram nessa conta. A v2 é a única que dá mais
verde ao Leste, e ganha em espera, viagem, chegadas e fila de inserção.

**Cenário original** (demanda equilibrada):

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde Leste/Oeste | Trocas |
|---|---:|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 14,9 s | 37,3 s | 1431 | 37 | 50% | 0 |
| v1 (heurística) | 4,7 s | 27,4 s | 1473 | 0 | 50% | 129 |
| v1.1 (DQN estado v1) | 4,6 s | 27,3 s | 1474 | 0 | 50% | 127 |
| v2 (DQN estado v2) | 5,1 s | 27,6 s | 1472 | 0 | 55% | 116 |
| max-pressure (referência) | 4,6 s | 27,2 s | 1474 | 0 | 50% | 129 |

Com demanda equilibrada, alternar rápido já é quase ótimo, e todas as versões
adaptativas empatam. A v2, que não treinou nesse cenário, fica 0,4–0,5 s
atrás.

### Percepção visual (Unity)

Cenário calibrado (Leste saturado), mesmo protocolo, 0 frames perdidos:

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde Leste/Oeste |
|---|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 16,1 s | 36,2 s | 1503 | 97 | 50% |
| v1 (heurística) | 12,1 s | 36,7 s | 1351 | 253 | 52% |
| v1.1 (DQN estado v1) | 12,9 s | 38,0 s | 1312 | 289 | 50% |
| **v2 (DQN estado v2)** | **10,3 s** | **32,1 s** | **1599** | **1** | **67%** |
| max-pressure (referência) | 11,1 s | 33,9 s | 1498 | 104 | 56% |

O ciclo fixo não usa percepção, então o resultado é o mesmo das duas tabelas.
Pela câmera, o quadro se repete: a v1 e a v1.1 escoam menos veículos que o
ciclo fixo e deixam 250–290 veículos fora da rede, enquanto a v2 é a única que
dá mais verde ao Leste. A v2 fica a 1,2 s de espera do limite com percepção
perfeita; na seed 1001, a ação coincidiu com a do oráculo em 82,7% das
decisões.

Cenário original (demanda equilibrada), mesmo protocolo, 0 frames perdidos:

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde Leste/Oeste |
|---|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 14,9 s | 37,3 s | 1431 | 37 | 50% |
| v1 (heurística) | 4,6 s | 27,2 s | 1473 | 0 | 50% |
| v1.1 (DQN estado v1) | 4,6 s | 27,2 s | 1474 | 0 | 50% |
| v2 (DQN estado v2) | 5,4 s | 28,0 s | 1469 | 1 | 56% |
| max-pressure | 5,8 s | 28,3 s | 1472 | 0 | 49% |

Com a câmera, as versões adaptativas continuam empatadas e muito à frente do
ciclo fixo. A v2, que não treinou nesse cenário, fica 0,8 s atrás da v1 em
espera média, com as mesmas chegadas e sem fila de inserção.

### Limitações

- As ROIs das câmeras cobrem só 23–26 m por faixa, e filas longas do Leste
  saturam o estado.
- A velocidade visual é subestimada.
- Há oclusão na faixa sul mais distante.
- A recompensa de treino vem do TraCI; só a política é exclusivamente visual.
- A avaliação usou três seeds de teste.

Os resultados originais da v1 e da v1.1, obtidos em protocolos diferentes
(100 s, antes da correção das fases), estão preservados como registro
histórico em
[`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md). Eles não
devem ser comparados com a v2.

## Prioridade para veículos de emergência

Viaturas de emergência avisam sua aproximação por V2I (como no despacho por
GPS dos sistemas reais), e o semáforo abre para o sentido de onde elas vêm:

- se o verde já é delas, é mantido, até além do verde máximo;
- se não é, o outro verde termina na hora, sem esperar o mínimo;
- amarelo e all-red nunca são pulados.

No mesmo ambiente (ROIs de 60 m, percepção oráculo, seeds 201–203, 30
viaturas por política), a perda de tempo média das viaturas até a linha de
retenção cai de 14–20 s para ~1 s, e todas cruzam sem parar. O custo é de +1
a +4 s na espera média do restante do tráfego. A detecção visual das viaturas
(nova classe "ambulância" no YOLO) é a próxima etapa, para comparar as duas
fontes. Detalhes em [`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md).

**Mudança de ambiente em 2026-09-30:** as câmeras foram reposicionadas e as
ROIs passaram a cobrir 60 m por faixa. As tabelas de comparação acima são do
ambiente anterior (ROIs de ~25 m); as do ambiente novo estão no documento de
progresso, e as avaliações visuais serão refeitas depois do novo YOLO.

## Como reproduzir

Todos os comandos rodam a partir de `python/`, com o ambiente virtual da raiz.
Modelos e resultados ficam em `results/` e `runs/`, que são locais (não
versionados).

```bash
cd python
../.venv/bin/python -m pip install -r requirements.txt
../.venv/bin/python -m unittest discover -s tests -p 'test_*.py'

# Pré-treino só no SUMO (percepção oráculo; sem Unity)
../.venv/bin/python -m experiments.pretrain_dqn_sumo --double-dqn

# Todas as versões no mesmo ambiente, percepção oráculo (sem Unity; alguns minutos)
../.venv/bin/python -m experiments.compare_versions --scenario calibrated --perception oracle
../.venv/bin/python -m experiments.compare_versions --scenario original --perception oracle
```

Com a Unity aberta na cena `SPImport`, com o Dataset Capture desativado e em
Play Mode (reinicie o Play Mode antes de cada comando):

```bash
../.venv/bin/python -m experiments.run_visual_policy --scenario calibrated --policy dqn \
  --dqn-model ../results/models/dqn-v2-pretrain-best.pt --seeds 201,202,203 --control-seconds 1800 \
  --step-log-output ../results/logs/teste-visual-dqn.jsonl \
  --output ../results/evaluation/teste-visual-dqn.json

# Diferença visão × oráculo a partir do log por step (sem Unity)
../.venv/bin/python -m experiments.evaluate_lane_features \
  --step-log ../results/logs/teste-visual-dqn.jsonl \
  --dqn-model ../results/models/dqn-v2-pretrain-best.pt
```

O detector ajustado (`runs/results/models/yolov8n-unity-run-002-mask/weights/best.pt`)
tem uma única classe, e os scripts v2 já usam `--classes 0` por padrão.

## Principais módulos

- `python/sumo`: cliente TraCI, seleção de cenário, oráculo TraCI das
  features por faixa, estado enviado à Unity e métricas.
- `python/bridge`: comunicação Python ↔ Unity (UDP de estado, TCP de frames
  agrupados por `step_id`).
- `python/vision`: YOLO, ByteTrack, ROIs, pipeline visual por câmera,
  homografia das ROIs, features por faixa e encoders de estado v1/v2.
- `python/controller`: DQN, camada de segurança de fases, política
  heurística, ciclo fixo, max-pressure, recompensa e pontos de decisão.
- `python/experiments`: scripts de execução, treino e avaliação
  (`python -m experiments.<nome>`).
- `sumo/sp`: rede, demandas (original e calibrada) e detectores do cenário SP.
- `unity/TrafficVisionUnity`: projeto Unity 6000.0.53f1 com a cena `SPImport`.
- `optimization/SP`: linha paralela de DQN com detectores E2 (Keras),
  independente do pipeline visual.
- `docs/`: guia de implementação, progresso e integração com o Sumo2Unity.

## Dados de drone (SimJamCV)

As métricas de contagem e velocidade média extraídas de vídeos reais de drone
com o projeto open-source SimJamComputerVision estão em
`simjamcv/DigitalTwinsforSmartCities/` (pastas `SP` e `EUA`, arquivos
`lane_metrics_{sentido}`). Elas foram usadas para calibrar a demanda do
cenário `calibrated`. Os vídeos com as detecções estão no Google Drive:
https://drive.google.com/drive/folders/1bBa7s3MElVlagaMF5ZkscvY7kFj51qzr?usp=sharing

## Testes de integração

Os testes abaixo validam cada camada isoladamente e foram os marcos da
construção do pipeline.

### Visão local (sem SUMO e sem Unity)

Validação preliminar do YOLO + ByteTrack + ROI com uma imagem ou um vídeo
local, usando o perfil legado `python/config.yaml`:

```bash
cd python
../.venv/bin/python -m experiments.test_vision --input ../samples/traffic_top_view.mp4
../.venv/bin/python -m experiments.test_vision --input ../samples/minha_imagem.jpg
```

Os frames de debug são salvos em `results/frames` com bounding boxes,
`track_id`, ROIs e contagens suavizadas.

### SUMO via TraCI

`test_sumo_traci` roda o cenário legado do `config.yaml`. `test_sp_traci`
inicia o cenário SP, valida o semáforo `clusterJ0_J14_J2_J7`, os sete
detectores E2 e uma troca controlada para a fase verde secundária, sem Unity:

```bash
cd python
../.venv/bin/python -m experiments.test_sumo_traci
../.venv/bin/python -m experiments.test_sp_traci --scenario calibrated
```

O perfil SP usa a porta TraCI local `8873`. A conexão TraCI é sempre fechada
em `finally`.

### Importação do cenário SP na Unity

No Unity, execute `Traffic Vision > SUMO > Create SP Import Scene`. A ação cria
e seleciona `SP Road Network Importer`, já configurado com
`Cruzamento.net.xml`. No Inspector, clique em `Import / rebuild SUMO road
network`; a cena resultante é salva como `Assets/Scenes/SPImport.unity`.

O teste esperado confirma 22 faixas e um cruzamento. O botão `Clear generated
road network` deve remover a geometria e uma nova importação deve recriá-la sem
duplicar objetos.

#### Entorno de apresentação no Unity

Com `Assets/Scenes/SPImport.unity` aberto, execute `Traffic Vision > SUMO >
Build SP Presentation Environment`. A ação cria o nó `SP Environment`, com
grama, oito casas residenciais posicionadas manualmente junto às vias, árvores,
postes, iluminação e névoa leve, reutilizando somente assets já versionados no
projeto. As calçadas pertencem à malha viária gerada, não a esse nó.

O comando pode ser executado novamente: ele substitui apenas `SP Environment`.
Portanto, não modifica `GeneratedSumoRoadNetwork`, as câmeras/ROIs calibradas,
a sincronização com o SUMO nem a máscara de instâncias dos veículos. Como o
entorno passa a aparecer nas imagens RGB, depois de aplicá-lo é recomendável
verificar uma captura das três câmeras antes de gerar um novo conjunto de dados
ou rodar uma avaliação de visão. A cena e os materiais novos são salvos pelo
próprio comando.

Para reconstruir a apresentação da rede, execute `Traffic Vision > SUMO >
Configure SP Visuals`. O comando recria somente `GeneratedSumoRoadNetwork`:
asfalto, cruzamento, calçadas que acompanham as curvas, linhas tracejadas entre
faixas do mesmo sentido, dupla amarela entre sentidos opostos e linhas de
retenção nas aproximações controladas. Ele não altera as casas, câmeras ou
semáforos; pressione `Cmd+S` depois de executá-lo.

Para configurar a ponte visual, execute `Traffic Vision > SUMO > Configure SP
Dynamic Sync`. Ela mantém o nó `SP Dynamic Synchronization` e recria apenas os
três postes `Signal Post East`, `Signal Post South` e `Signal Post West` nas
posições ajustadas na cena. Cada poste exibe vermelho, amarelo ou verde segundo
os índices da fase do TLS SUMO correspondentes à sua aproximação. O comando não
modifica o ambiente ou a malha das vias; pressione `Cmd+S` depois de executá-lo.

### Python → Unity

`test_unity_comm` envia estados JSON fictícios por UDP (`unity.state_host` e
`unity.state_port`) para validar a recepção. Cada mensagem inclui `step`,
`step_id`, `sim_time`, `vehicles` e `traffic_lights`:

```bash
cd python
../.venv/bin/python -m experiments.test_unity_comm
```

Na Unity, anexe
[`PythonStateReceiver.cs`](unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs)
a um `GameObject` e rode a cena. O Console deve mostrar os `step`/`step_id`
recebidos.

### SUMO → Python → Unity

`test_sumo_to_unity` envia à Unity o estado real extraído do SUMO. Com
`--receive-frames`, também recebe e salva os JPEGs das câmeras:

```bash
cd python
../.venv/bin/python -m experiments.test_sumo_to_unity --config configs/sp.yaml --steps 120 --send-interval 0.1
```

Na cena `SPImport` a sincronização já está configurada
([`PythonStateReceiver.cs`](unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs),
[`VehicleManager.cs`](unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/VehicleManager.cs) e
[`TrafficLightVisualController.cs`](unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/TrafficLightVisualController.cs)).
Entre em Play Mode antes de executar o script. O terminal deve imprimir
`state_sent step=...`, e os veículos devem se mover na cena.

### Scripts originais da v1 e da v1.1

Os scripts originais das versões anteriores, com o pipeline de contagem da
época, continuam disponíveis com a Unity em Play Mode. Para comparar versões,
use `experiments.compare_versions`.

```bash
cd python
../.venv/bin/python -m experiments.run_fixed_time_baseline --scenario original --steps 100 --seed 201 \
  --output ../results/evaluation/fixed-time-baseline.json
../.venv/bin/python -m experiments.run_visual_controller --scenario original --steps 100 --seed 201 \
  --camera-ids south,east,west --model ../runs/results/models/yolov8n-unity-run-002-mask/weights/best.pt \
  --classes 0 --metrics-output ../results/evaluation/visual-controller-metrics.json
../.venv/bin/python -m experiments.compare_control_experiments \
  --baseline ../results/evaluation/fixed-time-baseline.json \
  --visual-adaptive ../results/evaluation/visual-controller-metrics.json \
  --output ../results/evaluation/fixed-vs-visual-controller.json
```

Sem `--dqn-model`, `run_visual_controller` usa o heurístico (v1); com um
checkpoint v1 (`--dqn-model ../results/models/visual-dqn-sp-best.pt`), usa o
DQN v1.1. Checkpoints v2 são recusados de propósito: use `run_visual_policy`.
