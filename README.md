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
só no SUMO e executado com a câmera. No cenário com a demanda medida por drone,
reduz a espera média em 36% em relação ao ciclo fixo e escoa 6% mais veículos
(detalhes em [Evolução por versão](#evolução-por-versão)).

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

| Versão | Período | Política | Entrada da política | Protocolo de teste | Resultado principal |
|---|---|---|---|---|---|
| Linha de base | — | Tempo fixo (plano do SUMO) | — | — | Referência de cada versão |
| **v1** | 2026-09-02 | Heurística por fila visual | Contagem por faixa | Demanda original, seeds 42/7/99, 100 s | Espera −42% contra o tempo fixo |
| **v1.1** | 2026-09-04 | DQN visual (estado v1, 13 entradas) | Contagem por faixa + fase | Demanda original, seeds 201–203, 100 s | Supera o tempo fixo, mas empata com a v1 (colapsou em "sempre trocar") |
| **v2** | 2026-09-29 | DQN visual (estado v2, 41 entradas) | Contagem, parados, ocupação, velocidade e espera por faixa + fase | Demanda calibrada (drone), seeds 201–203, 1800 s | Espera −36% e +6% de chegadas contra o ciclo fixo; fila de inserção zerada |

Os números de versões diferentes **não são diretamente comparáveis**. A v2
mudou o cenário (demanda calibrada), a duração (1800 s em vez de 100 s) e as
métricas (fila de inserção). Também corrigiu uma dessincronização de fases que
afetava as execuções das versões v1 e v1.1, cujos valores foram mantidos como
registro histórico, sem reexecução. Cada tabela abaixo compara políticas dentro
do mesmo protocolo.

### Linha de base — tempo fixo

O programa estático do SUMO (`sumo/sp/Cruzamento.net.xml`: verdes de 42/41 s)
é executado por `experiments.run_fixed_time_baseline`, sem Unity. Na v2, a
referência passou a ser um **ciclo fixo 40/40** conduzido pela mesma camada de
segurança das demais políticas (`FixedCyclePolicy`), para que todas usem as
mesmas transições.

### v1 — Controle visual heurístico (2026-09-02)

**O que foi introduzido:** o primeiro controle em malha fechada pela câmera.
`TrafficController` soma as contagens visuais de `South` e de `East + West` e
troca o verde quando a fila oposta supera a atual por uma margem, respeitando
verde mínimo e máximo.

**Protocolo:** demanda original do netedit, seeds `42`, `7` e `99`, 100 s
simulados.

| Métrica (média de 3 seeds) | Tempo fixo | Controle visual | Variação |
| --- | ---: | ---: | ---: |
| Veículos concluídos | 50,67 | 60,67 | +19,7% |
| Vazão | 1842,4 veh/h | 2206,1 veh/h | +19,7% |
| Tempo médio de viagem | 27,35 s | 26,11 s | −4,6% |
| Tempo médio de espera | 6,77 s | 3,93 s | −42,0% |
| Fila média | 8,70 | 3,89 | −55,3% |
| Fila máxima | 19,67 | 9,33 | −52,5% |

**Limitação:** 100 s é pouco para avaliar a alocação de verde. Com a demanda
original equilibrada (v/c≈0,5 nas duas fases), o tempo de verde quase não muda
o resultado.

### v1.1 — DQN visual, estado v1 (2026-09-04)

**O que foi introduzido:** um DQN em PyTorch (`DqnAgent`, MLP 64×2) com 13
entradas: contagens normalizadas das 7 faixas, fase em *one-hot* e tempo da
fase. A recompensa de treino usava a espera acumulada do TraCI. O treino
rodou nas seeds 1–50 com a Unity no loop, e a validação usou as seeds
1001–1003.

**Protocolo:** demanda original, seeds inéditas `201`–`203`, 100 s simulados.

| Métrica (média de 3 seeds) | Tempo fixo | Heurístico visual | DQN visual v1 |
| --- | ---: | ---: | ---: |
| Veículos concluídos | 50,67 | 60,67 | 60,33 |
| Vazão (veíc./h) | 1842,42 | 2206,06 | 2193,94 |
| Tempo médio de espera | 6,85 s | 4,41 s | 4,44 s |
| Fila média | 8,73 | 4,15 | 4,21 |
| Fila máxima | 18,67 | 10,33 | 10,33 |

**Limitação e diagnóstico:** o DQN pediu troca assim que o verde mínimo
permitia, virando praticamente um ciclo fixo mínimo. A análise posterior
encontrou as causas:

- O checkpoint "melhor" era o do episódio 4, com 240 passos de gradiente e
  ε≈0,98: o ε decaía por episódio e ainda estava em ≈0,78 no fim do treino, e
  a validação empatava.
- A recompensa ficava positiva quando um veículo com espera saía da rede.
- As transições eram gravadas mesmo quando a ação era ignorada.

### v2 — DQN visual por faixa, estado v2 (2026-09-29)

**O que mudou:**

- **Estado v2 (41 entradas).** Para cada faixa: contagem, parados (< 1,39 m/s
  por ≥ 1 s), ocupação, velocidade média e espera, normalizados pela
  capacidade da ROI, mais fase e tempo. A base de cada bbox é projetada pela
  homografia da ROI de faixa, e um rastreador cinemático por câmera calcula
  velocidade e tempo parado.
- **Pré-treino só no SUMO.** Um oráculo TraCI produz as mesmas features a
  partir das posições reais no mesmo trecho das ROIs; um teste de paridade
  garante a equivalência. Cada episódio (300 s de aquecimento + 1800 s) leva
  ~6 s, contra ~1,5 s por step com a Unity. Com isso foram 40 episódios, com
  ε linear por decisão, Double DQN e seleção de checkpoint só após treino
  mínimo.
- **Decisões apenas quando têm efeito.** A política decide em verde, entre o
  verde mínimo e o máximo, a cada 5 s. As transições são SMDP, e a recompensa
  é um nível em [−1, 0] com parados, espera e fila de inserção.
- **Cenário calibrado.** A demanda foi medida nos vídeos de drone: o Leste fica
  saturado (v/c≈1,0), com chegadas Poisson e inserção realista. A demanda
  original continua disponível com `--scenario original`.
- **Correção de base.** O Python passa a manter o controle das fases no SUMO
  mesmo quando falta um frame. Antes, o programa estático podia pular o
  *all-red*.
- **Fila de inserção.** Os veículos que ainda não conseguiram entrar na rede
  passaram a ser medidos; eles não aparecem na espera média.

**Protocolo:** cenário calibrado, seeds inéditas `201`–`203`, 300 s de
aquecimento + 1800 s controlados. Nenhum frame foi perdido.

| Política (média de 3 seeds) | Percepção | Espera | Viagem | Chegadas | Fila de inserção final | Verde Leste/Oeste |
|---|---|---:|---:|---:|---:|---:|
| Ciclo fixo 40/40 | — | 16,1 s | 36,2 s | 1503 | 97 | 50% |
| Max-pressure | visual | 11,1 s | 33,9 s | 1498 | 104 | 56% |
| **DQN v2** | **visual** | **10,3 s** | **32,1 s** | **1599** | **1** | **67%** |
| DQN v2 | oráculo TraCI | 9,1 s | 30,9 s | 1598 | 6 | 66% |

- O DQN aprendeu a dar mais verde ao Leste saturado. Pela câmera, fica a
  1,2 s de espera do limite com percepção perfeita. Na seed 1001, a ação
  coincidiu com a do oráculo em 82,7% das decisões.
- O max-pressure visual tem espera média parecida, mas deixa 104 veículos
  esperando para entrar na rede.
- Com a demanda original, que ele não viu no treino, o DQN v2 com oráculo
  empata com o max-pressure (5,1 s × 4,6 s de espera), e ambos ficam bem à
  frente do ciclo fixo (14,9 s).
- Um ajuste fino com a Unity no loop (10 episódios) piorou a validação visual.
  A política final é a pré-treinada no SUMO, usada direto com a câmera
  (zero-shot).

**Limitações:**

- As ROIs das câmeras cobrem só 23–26 m por faixa, e filas longas do Leste
  saturam o estado.
- A velocidade visual é subestimada.
- Há oclusão na faixa sul mais distante.
- A recompensa de treino vem do TraCI; só a política é exclusivamente visual.
- A avaliação usou três seeds de teste.

Detalhes, medições da diferença visão × oráculo e todos os comandos estão em
[`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md), seção
**DQN v2**.

## Como reproduzir a v2

Todos os comandos rodam a partir de `python/`, com o ambiente virtual da raiz.
Modelos e resultados ficam em `results/` e `runs/`, que são locais (não
versionados).

```bash
cd python
../.venv/bin/python -m pip install -r requirements.txt
../.venv/bin/python -m unittest discover -s tests -p 'test_*.py'

# Pré-treino e avaliação só no SUMO (percepção oráculo; sem Unity)
../.venv/bin/python -m experiments.pretrain_dqn_sumo --double-dqn
../.venv/bin/python -m experiments.evaluate_policies_sumo --scenario calibrated \
  --dqn-model ../results/models/dqn-v2-pretrain-best.pt \
  --output ../results/evaluation/teste-sumo-oraculo.json
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

### Controlador visual e DQN das versões v1 e v1.1

Os scripts das versões anteriores continuam disponíveis, com a Unity em Play
Mode:

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
