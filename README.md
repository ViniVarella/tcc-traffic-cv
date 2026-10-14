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
só no SUMO e executado com a câmera. No cenário calibrado (demanda medida por
drone, sem motos), reduz a espera do ciclo fixo de 13,0 para 4,3 s pela
câmera, a 0,16 s do resultado com percepção *ground truth*; sem saturação, empata
com a heurística v1. Com a fase exclusiva de pedestres, a v2 reduz pela
câmera a espera dos veículos em 32% e a dos pedestres em 56% em relação ao
ciclo fixo; a **v3** (estado com as fases de pedestre) empata com ela, e são
as únicas versões que superam o ciclo fixo para os veículos (ver
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
| **v3** | 2026-10-05 | DQN (estado v3, 44 entradas) | Estado v2 + fases de pedestre + verdes até a fase de pedestres | Só nos cenários com pedestres; a recompensa inclui a espera dos pedestres |

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
- **Pré-treino só no SUMO.** Uma fonte *ground truth* (TraCI) produz as mesmas features a
  partir das posições reais no mesmo trecho das ROIs; um teste de paridade
  garante a equivalência. Cada episódio (300 s de aquecimento + 1800 s) leva
  ~6 s, contra ~1,5 s por step com a Unity. Foram 40 episódios, com ε linear
  por decisão, Double DQN e seleção de checkpoint só após treino mínimo.
- **Decisões apenas quando têm efeito.** A política decide em verde, entre o
  verde mínimo e o máximo, a cada 5 s. As transições são SMDP, e a recompensa
  é um nível em [−1, 0] com parados, espera e fila de inserção.
- **Cenário calibrado.** A demanda foi medida nos vídeos de drone, sem motos
  (andam no corredor e não formam fila): Leste com v/c≈0,58, chegadas
  Poisson e inserção realista. O checkpoint atual (`dqn-v2-sem-motos-best.pt`) foi
  pré-treinado nos cenários calibrado e original.
- **Correções que valem para todas as versões.** O Python passa a manter o
  controle das fases no SUMO mesmo quando falta um frame (antes o programa
  estático podia pular o *all-red*), e a fila de inserção passou a ser medida.
- Um ajuste fino com a Unity no loop (10 episódios) piorou a
  validação visual.
  A política final é a pré-treinada no SUMO, usada direto com a câmera
  (zero-shot).

## Comparação no mesmo ambiente

Todas as versões rodam no **mesmo ambiente**:

- mesmo cenário, seeds inéditas `201`–`203`, 300 s de aquecimento e 1800 s
  controlados;
- mesma camada de segurança, mesmas métricas e a **mesma percepção** — as
  features por faixa *ground truth* (TraCI) ou as da câmera.

Há duas percepções. Na **percepção visual**, as features por faixa vêm das
detecções do YOLO nas imagens da Unity. Na **percepção *ground truth***, vêm
das posições e velocidades reais dos veículos no SUMO, no mesmo trecho de
60 m coberto pelas câmeras. As duas passam pelo mesmo rastreador e produzem o
mesmo vetor de estado; a diferença entre elas é o custo da visão. A
recompensa de treino usa sempre o *ground truth*. No código, a percepção
*ground truth* se chama `oracle` (`--perception oracle`, arquivos `*-oracle.json`).

Só a lógica de decisão muda. As regras de cada versão estão em
`python/experiments/version_policies.py`, e o comparador é
`python -m experiments.compare_versions`.

**Diferença deliberada em relação às execuções originais:** a v1 e a v1.1
contavam os veículos pelo centro da bbox com média móvel. Aqui elas recebem a
mesma contagem por faixa usada pela v2. Também decidem a cada 1 s, como
faziam originalmente.

### Ambiente atual, cenário calibrado (demanda sem motos)

Demanda medida pelo drone sem motos (andam no corredor e não formam fila):
Leste 976 veíc/h (v/c 0,58), Sul 727, Oeste 139. Checkpoint da v2:
`dqn-v2-sem-motos-best.pt`. Seeds 201–203, 300 s de aquecimento + 1800 s,
0 frames perdidos na percepção visual.

| Versão | Espera (visual) | Espera (*ground truth*) | Chegadas (visual) | Fila de inserção |
|---|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 13,0 s | 13,0 s | 918 | 0 |
| v1 (heurística) | **4,3 s** | 4,4 s | 915 | 0 |
| v1.1 (DQN estado v1) | 5,7 s | 5,7 s | 916 | 0 |
| v2 (DQN estado v2) | **4,3 s** | **4,1 s** | 916 | 0 |
| max-pressure (referência) | 4,8 s | 4,7 s | 916 | 0 |

Pela câmera, as versões adaptativas reduzem a espera do ciclo fixo em 56–67%,
e a visão custa no máximo 0,16 s em relação à percepção *ground truth*. Sem o Leste
saturado, v1 e v2 empatam com visão (4,27 × 4,31 s, dentro da variação entre
seeds); com a percepção *ground truth*, a v2 é a melhor. A v1.1 dá o mesmo número nas duas
percepções porque troca sempre no verde mínimo (129 trocas em 30 min) e não
depende do que vê.

### Ambiente atual com pedestres (cenário `calibrated_ped`)

Mesma demanda e protocolo, com a fase exclusiva de pedestres a cada ciclo
(L/O → Sul → pedestres): todos os veículos no vermelho, 7 s de verde para
começar a travessia + 11 s de liberação, o tempo de cruzar a rua mais larga
(13,0 m) a 1,2 m/s. Quem atravessa duas ruas espera a fase seguinte na
esquina. Pedestres renderizados na Unity. Checkpoint da v3:
`dqn-v3-fase-curta-best.pt`, treinado com esta fase. 0 frames perdidos na
percepção visual.

| Versão | Espera veículos (visual) | Espera veículos (*ground truth*) | Espera pedestres (visual, mediana / p90) | Fila média de inserção (visual) |
|---|---:|---:|---|---:|
| Linha de base (ciclo fixo) | 20,8 s | 20,8 s | 56,6 s (47 / 140 s) | 0,9 |
| v1 (heurística) | 24,6 s | 25,3 s | 22,3 s (21 / 53 s) | 9,3 |
| v2 (DQN estado v2) | **14,1 s** | **14,2 s** | 25,0 s (22 / 58 s) | 0,1 |
| v3 (DQN estado v3, com pedestres) | 14,7 s | **14,2 s** | 27,4 s (25 / 60 s) | 0,1 |
| max-pressure (referência) | 21,0 s | 26,5 s | 24,2 s (23 / 57 s) | 1,9 |

Os pedestres na imagem não atrapalham a visão: o YOLO não os detecta, e a v2
e a v3 ficam a até 0,5 s da percepção *ground truth*. A v2 reduz a espera dos
veículos de 20,8 para 14,1 s (−32%) e a dos pedestres de 56,6 para 25,0 s
(p90 140 → 58 s). A v3 empata com ela nos veículos e deixa os pedestres 2–3 s
a mais: com a fase a cada ciclo, saber quantos verdes faltam até ela não
acrescenta nada. A v1 e o max-pressure trocam no verde mínimo sempre que a
fila oposta é maior, e cada ciclo a mais traz outra fase de pedestres de 18 s,
com todos os veículos parados. Por isso ficam iguais ao ciclo fixo ou piores
para os veículos. Com a câmera, o max-pressure troca menos, porque a contagem
visual demora a mostrar a fila oposta, e chega a empatar com o ciclo fixo.

### Ambiente atual, cenário original (demanda equilibrada do netedit)

Mesmo protocolo e mesmos checkpoints. A demanda não tem motos e não mudou;
mudou o checkpoint da v2. Percepção visual com 0 frames perdidos.

| Versão | Espera (*ground truth*) | Espera (visão) | Chegadas (visão) | Fila de inserção final (visão) |
|---|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 14,9 s | 14,9 s | 1431 | 37 |
| v1 (heurística) | 4,7 s | **4,6 s** | 1472 | 0 |
| v1.1 (DQN estado v1) | 4,6 s | **4,6 s** | 1474 | 0 |
| v2 (DQN estado v2) | **4,5 s** | 5,2 s | 1474 | 0 |
| max-pressure (referência) | 4,6 s | 6,1 s | 1471 | 0 |

Com demanda equilibrada, alternar rápido já é quase ótimo: com a percepção
*ground truth*, as versões adaptativas reduzem a espera do ciclo fixo em ~70%
e ficam a 0,2 s umas das outras. Com a câmera, a v2 e o max-pressure trocam
menos de fase (110 e 97 trocas, contra 128 e 129) e perdem 0,7 s e 1,5 s;
ainda assim ficam 59–65% abaixo do ciclo fixo. Aqui a visão custa mais que no
cenário calibrado (≤ 0,16 s), porque o ganho de cada decisão é pequeno e
qualquer verde segurado a mais aparece na média. O cenário `original_ped` satura com a fase exclusiva de pedestres
(fila de inserção de 183–417 veículos) e não vem do drone; os números estão
em [`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md).

### Limitações

- As ROIs cobrem 60 m por faixa. Com a demanda atual as filas ficam dentro
  delas, e a contagem visual não fica abaixo da real em nenhuma faixa (viés
  de +0,01 a +0,18 veículo; seed 1001, 300 s). A câmera Leste vê as faixas de
  lado, e uma fila longa na faixa 0 esconderia parte da faixa 1.
- A velocidade visual é subestimada (−0,1 a −0,9 m/s por faixa) e a espera
  visual, superestimada (+0,2 a +4,2 s).
- A recompensa de treino vem do TraCI; só a política é exclusivamente visual.
- A avaliação usou três seeds de teste.

Os resultados originais da v1 e da v1.1, obtidos em protocolos diferentes
(100 s, antes da correção das fases), estão preservados como registro
histórico em
[`docs/IMPLEMENTATION_PROGRESS.md`](docs/IMPLEMENTATION_PROGRESS.md). Eles não
devem ser comparados com a v2.

## Prioridade para veículos de emergência

Viaturas de emergência avisam sua aproximação por V2I (*vehicle-to-infrastructure*,
comunicação entre o veículo e o controlador do semáforo; como no despacho por
GPS dos sistemas reais), e o semáforo abre para o sentido de onde elas vêm:

- se o verde já é delas, é mantido, até além do verde máximo;
- se não é, o outro verde termina na hora, sem esperar o mínimo;
- amarelo e all-red nunca são pulados.

Cenário calibrado sem motos, ROIs de 60 m, seeds 201–203, uma viatura a
cada ~5 min (18 por política). A perda total soma a espera para entrar na
rede e a perda até a linha de retenção. Com percepção *ground truth*, ela cai de
16,6 s (ciclo fixo), 8,0 s (v2) e 7,9 s (max-pressure) para 1,3–1,4 s, e todas
cruzam sem parar. O custo é de até +0,6 s na espera do restante do
tráfego. A câmera também detecta as viaturas (classe `emergency` do YOLO
dentro das ROIs) e serve como segunda fonte. Em malha fechada com percepção
visual (v2, 0 frames perdidos):

| Fonte do pedido | Perda total média (máx.) | Sem parar | Espera do tráfego |
|---|---|---|---|
| nenhuma | 7,6 s (19,7 s) | 50% | 4,3 s |
| V2I | **1,4 s** (2,0 s) | 100% | 4,6 s |
| visão | 2,7 s (9,0 s) | 89% | 4,6 s |
| V2I + visão | **1,4 s** (2,0 s) | 100% | 4,9 s |

A visão detectou as 18 viaturas, sem alarme falso, mas só as vê nos últimos
60 m (~5 s antes da linha, contra ~23 s do V2I). Sozinha, reduz a perda em
65%; junto do V2I, serve de redundância.

No cenário `original` (demanda equilibrada do netedit), também com
percepção visual, v2 e 0 frames perdidos, a perda total cai de 11,2 s (sem
preempção) para 2,9 s com V2I (*ground truth*: 2,9 s), 4,5 s só com visão e
2,8 s com V2I + visão, com 100% sem parar nos modos com V2I. O custo para o
tráfego é de +0,3 a +0,9 s.

Com pedestres (`calibrated_ped`, fase de pedestres de 7 s + 11 s a cada
ciclo), percepção visual, v2, 0 frames perdidos:

| Fonte do pedido | Perda total média (máx.) | Sem parar | Espera do tráfego | Espera dos pedestres |
|---|---|---|---|---|
| nenhuma | 13,0 s (41,3 s) | 50% | 14,3 s | 25,1 s |
| V2I | **1,8 s** (9,8 s) | 100% | 15,3 s | 26,6 s |
| visão | 6,4 s (21,3 s) | 72% | 14,8 s | 25,3 s |
| V2I + visão | 2,4 s (10,6 s) | 100% | 15,3 s | 28,0 s |

Com percepção *ground truth* e V2I, a perda fica em 1,7–2,0 s no ciclo
fixo, na v2 e na v3 (100% sem parar). No max-pressure ela é de 6,2 s, porque
a fila de inserção segura a viatura antes de ela entrar na rede. A fase de
pedestres é obrigatória: a viatura que chega durante ela espera até o fim, no
máximo ~10 s com V2I. A visão detectou as 18 viaturas sem alarme
falso. Sozinha, ela reduz a perda em 51%; junto do V2I, serve de redundância.
O custo é de +0,5 a +1,0 s para os outros veículos e de até +3 s para os
pedestres.

As tabelas desta seção usam o ambiente atual: câmeras de 60 m, YOLO de duas
classes, demanda sem motos, v2 `dqn-v2-sem-motos-best.pt` e, com pedestres,
v3 `dqn-v3-fase-curta-best.pt`.

## Como reproduzir

Todos os comandos rodam a partir de `python/`, com o ambiente virtual da raiz.
Modelos e resultados ficam em `results/` e `runs/`, que são locais (não
versionados).

```bash
cd python
../.venv/bin/python -m pip install -r requirements.txt
../.venv/bin/python -m unittest discover -s tests -p 'test_*.py'

# Pré-treino só no SUMO (percepção ground truth; sem Unity)
../.venv/bin/python -m experiments.pretrain_dqn_sumo --double-dqn

# Todas as versões no mesmo ambiente, percepção ground truth (sem Unity; alguns minutos)
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

# Diferença visão × ground truth a partir do log por step (sem Unity)
../.venv/bin/python -m experiments.evaluate_lane_features \
  --step-log ../results/logs/teste-visual-dqn.jsonl \
  --dqn-model ../results/models/dqn-v2-pretrain-best.pt
```

O detector ajustado (`runs/results/models/yolov8n-unity-cam60-2cls-960/weights/best.pt`)
tem duas classes, `0 vehicle` e `1 emergency`; os scripts v2 já usam esse modelo
com `--classes 0,1` e `--image-size 960` por padrão. O detector anterior
(`yolov8n-unity-run-002-mask`, uma classe, `--classes 0`) continua nos scripts
legados da v1. Recall no teste: veículos 100% / 99,5% / 97,2% em 0–20 / 20–40 /
40–60 m da ROI ([detalhes](docs/IMPLEMENTATION_PROGRESS.md)).

## Modelo da ambulância

O modelo 3D da ambulância usado na Unity vem do RigModels.com, com licença
apenas para uso pessoal/estudante, e por isso **não é versionado**. Para
reproduzir:

1. Baixe o modelo "Ambulance" em https://rigmodels.com e copie a pasta, com
   `ambulance.fbx` e as texturas, para
   `unity/TrafficVisionUnity/Assets/Art/TrafficModels/Models/Cars/Ambulance/`.
2. Na Unity, com `SPImport` aberta, rode *Traffic Vision > Vehicles > Create
   SP Emergency Prefab* e salve a cena.
3. Para conferir, entre em Play Mode e rode
   `python -m experiments.test_sumo_to_unity --config configs/sp.yaml --steps 120 --send-interval 0.1 --emergency-interval 20`.
   Se a ambulância andar de ré, rode *Flip SP Emergency Prefab*.

Sem o modelo, as viaturas de emergência aparecem como blocos vermelhos.

## Principais módulos

- `python/sumo`: cliente TraCI, seleção de cenário, *ground truth* TraCI das
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
