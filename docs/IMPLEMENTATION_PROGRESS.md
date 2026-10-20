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
- Controlador visual heurístico (v1) e DQN visual v1 (v1.1, 13 contagens):
  concluídos em 2026-09. A v1.1 colapsou em "sempre trocar"; o diagnóstico, a
  comparação no mesmo ambiente e o registro histórico estão na seção seguinte.
- DQN v2 (features por faixa, pré-treino só SUMO e avaliação visual):
  concluído em 2026-09-29 — seção **DQN v2** abaixo.
- Câmeras reposicionadas, ROIs de 60 m e preempção para veículos de
  emergência por aviso V2I (*vehicle-to-infrastructure*): concluídos em 2026-09-30 — seção **Ambiente com
  ROIs de 60 m e preempção** abaixo.
- YOLO de duas classes, detecção visual das viaturas, correção do filtro da
  ROI e avaliações visuais do ambiente de 60 m: concluídos em 2026-10-04.
- Pedestres no SUMO (rede, fase exclusiva de pedestres, estado v3,
  métricas): desde 2026-10-05 — seção **Pedestres** abaixo. Pedestres,
  faixas e sinais na Unity em 2026-10-08; avaliação visual com pedestres em
  2026-10-09.
- Demanda calibrada sem motos: 2026-10-07 — seção **Demanda calibrada sem
  motos** abaixo. v2 e v3 foram retreinados (checkpoints
  `*-sem-motos-best.pt`); os resultados obtidos com a demanda anterior foram
  retirados deste registro.
  Avaliações visuais (Unity) refeitas em 2026-10-08 (cenário `original` em
  2026-10-12).
- Fase de pedestres curta a cada ciclo (7 s + 11 s): 2026-10-13 — seção
  **Fase de pedestres curta** abaixo. Experimento DQN estado v3 retreinado
  (`dqn-v3-fase-curta-best.pt`); versões com pedestres refeitas com
  percepção *ground truth* e visual; preempção refeita com as duas
  percepções.
- Versões do produto TraffIQ (v1 a v4) e painel web para o Eureka:
  2026-10-14 — seção **Versões do produto** abaixo.

## Projeto Unity renomeado (2026-10-20)

A pasta do projeto Unity passou de `unity/TrafficVisionUnity` para
`unity/TraffIQ-TCC` (é o nome que o Unity Hub mostra), e o nome do produto
(Player Settings) para "TraffIQ - TCC". Os caminhos citados neste documento
já usam a pasta nova. No Hub, remova a entrada antiga e adicione a pasta nova
(*Add → Add project from disk*).

No mesmo dia, o checkpoint do TraffIQ (DQN estado v2) passou de
`dqn-v2-sem-motos-best.pt` para **`dqn-v2-traffiq-best.pt`** (mesmo arquivo; o
cenário com motos não é mais usado), e os checkpoints sem uso foram para
`results/models/arquivo/`. Os nomes citados nas seções anteriores já usam o
nome novo.

Também passaram a ser versionados os artefatos necessários para rodar o
projeto em outra máquina: `dqn-v2-traffiq-best.pt`, `visual-dqn-sp-best.pt`,
`dqn-v3-fase-curta-best.pt`, o detector
`yolov8n-unity-cam60-2cls-960/weights/best.pt`, as referências
`versoes-{calibrated,calibrated_ped,original,original_ped}-oracle.json` e o
modelo da ambulância (RigModels.com, licença de uso pessoal/estudante, com o
`License.txt` junto).

## Amostra mínima da redução no painel: 5 min (2026-10-20)

A "Redução na espera" do painel aparece em cinza (prévia) até a amostra
mínima (`MIN_SAMPLE_S` em `python/dashboard/app.py`), que passou de 10 para
**5 min** de teste. Para escolher, a média acumulada da espera do tempo fixo
(só veículos que entraram depois do aquecimento e concluíram o trajeto, como
no painel) foi comparada com a média de 30 min, nas seeds 201–203:

| Tempo de teste | Veículos | `calibrated_ped` | `calibrated` |
|---|---|---|---|
| 1 min | ~12 | −56% a −92% | −92% a −97% |
| 3 min | ~75 | −14% a −25% | −8% a −19% |
| 5 min | ~140 | −6% a −12% | −3% a −7% |
| 10 min | ~290 | +4% a −11% | 0% a −9% |
| 20 min | ~600 | 0% a −3% | 0% a +1% |

No começo a média fica baixa demais: os primeiros a concluir o trajeto são os
que pegaram verde. De 5 para 10 min a margem quase não muda (~10%). Os
primeiros veículos concluem o trajeto ~40 s depois do aquecimento (percurso
mediano de ~180 m; mediana de 39 s de viagem com pedestres). As médias de
30 min (≈ 21 s e ≈ 13 s) batem com as referências do painel (20,8 s e
13,0 s). É uma rodada do SUMO sem TraCI, com o programa estático; o número
do painel continua sendo uma estimativa de uma seed.

## Versões do produto TraffIQ (2026-10-14)

Desde 2026-10-14 as versões são do **produto** (decisão do usuário): cada uma
acrescenta uma capacidade, e o modelo que decide pode se repetir. Treinar um
modelo não cria uma versão.

| Versão | Período | O que acrescenta | Quem decide |
|---|---|---|---|
| v1 | 2026-09-02 | Controle em malha fechada pela câmera | Regra de fila |
| v1.1 | 2026-09-04 | Primeira política aprendida (colapsou em "trocar sempre") | DQN estado v1 |
| v2 | 2026-09-29 | Features cinemáticas por faixa, pré-treino só no SUMO | DQN estado v2 |
| v3 | 2026-09-30 a 10-04 | Prioridade para viaturas (V2I + câmera) | DQN estado v2 |
| **v4** (atual) | 2026-10-05 a 10-13 | Fase exclusiva de pedestres (7 s + 11 s a cada ciclo) | DQN estado v2 |

O **DQN estado v3** (44 entradas) é um experimento: empatou com o DQN estado
v2 e não entrou no produto. **Numeração nas seções abaixo:** até esta data,
"v1", "v1.1", "v2" e "v3" nomeavam controladores, como `--versions` no código
(v2 = DQN estado v2; v3 = DQN estado v3). Os registros antigos ficam com essa
numeração. As seções da v4 e o README usam a numeração do produto.

## Fase de pedestres curta a cada ciclo (2026-10-13; produto v4)

Status: branch `feat/fase-pedestres-curta` (`210686d`, `5b4dcd3`).

A fase antiga (verde de 41 s, o tempo para fazer o maior "L" a pé, + 3 s, a
cada dois ciclos) parava todos os veículos por 44 s e deixava a espera deles
em 21–25 s, o dobro do cenário sem pedestres. Agora cada pedestre atravessa
uma rua por fase, e quem precisa de duas espera a fase seguinte na esquina:

- **verde de 7 s**, o mínimo para começar a travessia;
- **11 s de liberação** em vermelho total: 13,0 m (travessia mais larga, a
  Leste) a 1,2 m/s. Quem entra no último segundo do verde termina antes de
  os veículos voltarem;
- **a cada ciclo** (L/O → Sul → pedestres). A cada dois ciclos, quem
  atravessa duas ruas esperaria dois intervalos longos.

`sp.yaml` (`pedestrians:`): `every_cycles: 1`, `green_seconds: 7`,
`clearance_seconds: 11`, `widest_crossing_m: 13.0` (sai `longest_l_m`). A rede
`.ped.net.xml` foi regenerada (`crossing_lengths` no gerador).

**Escolha da variante** (percepção *ground truth*, seeds 201–203, DQN estado v2 com
`dqn-v2-traffiq-best.pt` e o DQN estado v3 antigo; espera média de veículos /
pedestres). Referência: níveis de serviço do HCM 2000 para a espera de
pedestre em semáforo (A < 10 s, B 10–20, C 20–30, D 30–40, E 40–60, F > 60 s).

| Variante | Ciclo fixo | DQN estado v2 |
|---|---|---|
| A: 11 + 3 s, a cada 2 ciclos | 16,2 / 107 s | 7,9 / 38 s |
| B: 7 + 11 s, a cada 2 ciclos | 17,1 / 112 s | 10,3 / 45 s |
| C: 11 + 3 s, a cada ciclo | 18,8 / 53 s | 12,1 / 19 s |
| **D: 7 + 11 s, a cada ciclo** (escolhida) | 20,8 / 57 s | 14,2 / 23 s |
| fase antiga: 41 + 3 s, a cada 2 ciclos | 24,5 / 64 s | 21,3 / 26 s |

A e B dão a menor espera dos veículos, mas pedestres de ~40 s (nível D–E).
C e D deixam os pedestres no nível C. Entre as duas, D é a única em que quem
entra no fim do verde termina a travessia antes de os veículos voltarem
(decisão do usuário).

**Experimento DQN estado v3 retreinado** com a fase nova: `dqn-v3-fase-curta-best.pt`, mesma
receita (`calibrated_ped,original_ped`, w = 0,3, 100 episódios, seeds 51–150,
~30 min), melhor no episódio 99 (score −0,146). A referência de 1200 s do
termo dos pedestres na recompensa não foi recalculada. O DQN estado v2 não
precisou de retreino: ele vê a fase de pedestres como all-red. Os resultados da fase
antiga ganharam o sufixo `-fase-41s`.

**Controladores no `calibrated_ped`** (seeds 201–203, 300 s + 1800 s; visão: Unity,
**0 frames perdidos**; arquivos `versoes-calibrated_ped-{oracle,visual}.json`,
log `results/logs/versoes-calibrated_ped-visual.log`). Espera dos veículos,
por seed entre parênteses; pedestres: média (mediana / p90):

| Controlador | Veículos, *ground truth* | Veículos, visão | Fila média de inserção (GT / visão) | Pedestres, *ground truth* | Pedestres, visão | Trocas (GT / visão) |
|---|---:|---:|---:|---|---|---:|
| ciclo fixo | 20,8 s | 20,8 s (21,4 / 20,4 / 20,6) | 0,9 / 0,9 | 56,6 s (47 / 140) | 56,6 s (47 / 140) | 0 / 0 |
| Regra de fila (v1) | 25,3 s | 24,6 s (22,5 / 25,8 / 25,7) | 10,3 / 9,3 | 22,6 s (20 / 53) | 22,3 s (21 / 53) | 71 / 71 |
| **DQN estado v2 (v4, atual)** | **14,2 s** | **14,1 s** (13,9 / 14,3 / 14,2) | 0,1 / 0,1 | 23,4 s (21 / 57) | 25,0 s (22 / 58) | 68 / 66 |
| DQN estado v3 (experimento) | **14,2 s** | 14,7 s (14,2 / 14,6 / 15,2) | 0,1 / 0,1 | 26,6 s (26 / 60) | 27,4 s (25 / 60) | 62 / 62 |
| max-pressure | 26,5 s | 21,0 s (19,7 / 22,9 / 20,4) | 12,2 / 1,9 | 22,3 s (20 / 51) | 24,2 s (23 / 57) | 73 / 68 |

Chegadas de veículos (visão): 911–922 em todos os controladores; pedestres
159–161; 0 teleportes.

- **O DQN estado v2 com a câmera reduz a espera dos veículos em 32%** em relação ao ciclo
  fixo (20,8 → 14,1 s; com a fase antiga eram 13–17%) e a dos pedestres em
  56% (56,6 → 25,0 s; p90 140 → 58 s).
- **A visão reproduz a percepção *ground truth*** no DQN estado v2 (−0,1 s)
  e no DQN estado v3 (+0,5 s). Nos pedestres, a diferença é de +0,8 a +1,6 s.
- **Os dois DQN empatam nos veículos**; o DQN estado v3 deixa os pedestres
  ~2–3 s a mais nas duas percepções. Com a fase a cada ciclo, saber quantos
  verdes faltam até ela já não ajuda: a resposta é sempre a mesma. Por isso o
  experimento não entrou no produto, e a v4 decide com o DQN estado v2.
- **A regra de fila e o max-pressure ficam piores que o ciclo fixo para os veículos.** Eles
  trocam no verde mínimo sempre que a fila oposta é maior. Agora cada ciclo
  inclui 18 s de fase de pedestres, então cada troca a mais custa caro. Com a
  câmera, o max-pressure troca menos (68 × 73), porque a contagem visual
  demora a refletir a fila oposta. Isso reduz a fila de inserção (12,2 → 1,9)
  e a espera (26,5 → 21,0 s). Ele não melhora por ver melhor: segura o verde
  por mais tempo.

**Preempção com percepção *ground truth*** (V2I, mesma agenda de 18 viaturas,
seeds 201–203; arquivo `results/evaluation/preempcao-calibrated_ped-oracle.json`,
log `results/logs/preempcao-oracle-calibrated_ped-fase-curta.log`). Perda
total sem → com preempção; espera do tráfego e dos pedestres (média, p90) com
preempção:

| Controlador | Perda total (máx. com preempção) | Sem parar | Espera do tráfego | Pedestres |
|---|---:|---:|---:|---|
| ciclo fixo | 35,3 → **1,7 s** (6,4 s) | 11% → 100% | 20,9 → 21,6 s | 56,2 s (138) |
| DQN estado v2 | 20,0 → 2,0 s (9,8 s) | 28% → 100% | 14,2 → 15,3 s | 25,6 s (59) |
| DQN estado v3 (experimento) | 13,0 → 2,0 s (9,8 s) | 44% → 100% | 14,8 → 14,5 s | 29,1 s (68) |
| max-pressure | 45,3 → 6,2 s (31,2 s) | 22% → 100% | 27,0 → 24,3 s | 24,0 s (56) |

- Com a preempção, todas as viaturas cruzam sem parar. A perda fica em
  1,7–2,0 s; a única exceção (~10 s) é a viatura que chega durante a fase de
  pedestres. Com a fase antiga, a perda era de 6–9 s, e a pior chegava a 39 s.
- O max-pressure é a exceção: a fila de inserção dele (24,7 veículos em média
  sem preempção) segura a viatura antes de entrar na rede (espera de entrada de
  5,1 s, máx. 31 s).
- Sem preempção, a perda do DQN estado v2 é maior com percepção *ground truth* do que
  com visão (20,0 × 13,0 s). A agenda é a mesma; o que muda é em que fase
  cada viatura chega. Com 18 viaturas, isso varia de uma rodada para outra.
- Pedestres: +0,6 a +2,0 s na média com a preempção; máxima até 101 s (DQN estado v3).

**Preempção com visão** (DQN estado v2, `calibrated_ped`, mesma agenda de 18 viaturas,
seeds 201–203; perda total = espera de entrada + perda na rede; arquivo
`results/evaluation/preempcao-calibrated_ped-visual.json`, log
`results/logs/preempcao-visual-calibrated_ped.log`, **0 frames perdidos**;
já com a correção do aviso V2I no step da inserção):

| Fonte do pedido | Perda total média | Máx. | Sem parar | Antecedência | Espera do tráfego | Pedestres (mediana / p90 / máx.) |
|---|---:|---:|---:|---:|---:|---|
| nenhuma | 13,0 s | 41,3 s | 50% | — | 14,3 s | 25,1 s (22 / 59 / 93) |
| V2I | **1,8 s** | 9,8 s | 100% | ~23 s (V2I) | 15,3 s | 26,6 s (22 / 63 / 92) |
| visão | 6,4 s | 21,3 s | 72% | ~8 s (câmera) | 14,8 s | 25,3 s (23 / 59 / 93) |
| V2I + visão | 2,4 s | 10,6 s | 100% | — | 15,3 s | 28,0 s (23 / 68 / 106) |

A visão detectou as 18 viaturas em todos os modos, sem alarme falso.

- **Com V2I, 17 das 18 viaturas perdem ≤ 2 s.** A exceção (~10 s) chegou
  durante a fase de pedestres, que a preempção não encerra. Com a fase antiga
  essa espera chegava a ~39 s e puxava a média para 5,5 s; agora a fase dura
  18 s.
- **A visão sozinha reduz a perda em 51%** (13,0 → 6,4 s). Ela vê a viatura
  só nos últimos 60 m (~8 s antes da linha), e 5 das 18 ainda param. V2I +
  visão empata com V2I, e a visão serve de redundância.
- **Custo:** +0,5 a +1,0 s na espera dos outros veículos. Os pedestres
  esperam em média +0,2 a +2,9 s, e a espera máxima chega a 106 s no modo
  V2I + visão.


## Demanda calibrada sem motos (2026-10-07)

Status: implementada na branch `feat/demanda-sem-motos`
(`experiments.build_calibrated_demand`, `tests/test_calibrated_demand.py`).

**Por que mudou.** A calibração anterior multiplicava o `throughput_per_hour`
do SimJamCV pela fração de veículos do `vehicles.csv`, tirando só os rótulos de
pedestre. As motos ficavam e viravam carros de 5 m no SUMO. Nos vídeos, motos
e "triciclos" (motos mal classificadas) são ~42% do Leste e ~43% do Sul. Com
isso o Leste do modelo ficou saturado (v/c 1,00), mas o próprio drone mediu
atraso de **6,6 s no Leste (nível A)**, 12,9 s no Sul e 17 s no Oeste. Decisão
do usuário: motos andam no corredor e não formam fila, então saem da demanda;
carros, vans, caminhões e ônibus entram (pesados como carros). Os rótulos de
pedestre do SimJamCV não são confiáveis.

| Aproximação | Antes (motos como carros) | Sem motos | v/c antes | v/c sem motos |
|---|---:|---:|---:|---:|
| Leste (E2) | 1.675 veíc/h | 976 | 1,00 | 0,58 |
| Sul (E3) | 1.279 | 727 | 0,39 | 0,22 |
| Oeste (E6) | 169 | 139 | 0,20 | 0,17 |

As conversões de cada aproximação mantêm as proporções anteriores. A rota
antiga continua como cenário `calibrated_motos` (`Cruzamento.calibrated-motos.*`):
o gerador lê dela as proporções de conversão.

### Retreino e avaliação com a demanda sem motos (percepção *ground truth*, seeds 201–203, 300 s + 1800 s)

Checkpoints novos, padrão dos scripts: v2 = `dqn-v2-traffiq-best.pt`
(`--scenarios calibrated,original`, 40 episódios, melhor no 39; ~5 min, pois
cada episódio leva ~5 s sem saturação) e v3 = `dqn-v3-sem-motos-best.pt`
(`calibrated_ped,original_ped`, w = 0,3, 100 episódios, seeds 51–150, melhor
no 89). v1/v1.1 continuam com o checkpoint legado. Arquivos:
`results/evaluation/versoes-*-oracle.json` e `preempcao-*-oracle.json`; os da
demanda antiga ganharam o sufixo `-motos`. Log: `results/logs/avaliacao-sem-motos.log`.

**Versões**

| Cenário | Ciclo fixo | v1 | v1.1 | v2 | v3 | max-pressure |
|---|---:|---:|---:|---:|---:|---:|
| calibrado | 13,0 s | 4,4 s | 5,7 s | **4,1 s** | — | 4,7 s |
| original | 14,9 s (fila 37) | 4,7 s | 4,6 s | **4,5 s** | — | 4,6 s |
| calibrado + pedestres | 24,5 s | 30,2 s (fila 15) | — | **21,3 s** | **21,3 s** | 34,2 s (fila 77) |
| original + pedestres | 32,3 s (fila 224) | 49,3 s (fila 417) | — | 30,9 s (fila 183) | **27,1 s** (fila 192) | 44,1 s (fila 357) |

Pedestres (mediana / p90): calibrado — ciclo fixo 48 / 163 s, v2 10 / 70 s,
v3 12 / 74 s, max-pressure 7 / 53 s; original — ciclo fixo 49 / 163 s, v2
14 / 74 s, v3 14 / 86 s.

- No calibrado, as políticas adaptativas reduzem a espera de 13,0 s para
  4,1–5,7 s (v2: −68%) e ficam próximas entre si: com v/c 0,58 no Leste, há
  menos a ganhar entre elas do que com o Leste saturado.
- Com pedestres, v2 e v3 empatam nos veículos no calibrado (21,3 s); a v2
  fica um pouco melhor para os pedestres. A v1 (decide a cada passo, sem a
  fase de pedestres no estado) e o max-pressure pioram os veículos.
- O cenário `original_ped` (demanda sintética do netedit, Sul com 1.630
  veíc/h) ainda satura com a fase exclusiva; ele não vem do drone.

As linhas com pedestres desta subseção (versões e preempção) usam a fase
antiga (41 s + 3 s a cada dois ciclos) e o v3 `dqn-v3-sem-motos-best.pt`.
Para as versões com a fase atual, ver a seção **Fase de pedestres curta**.

**Preempção (V2I, viaturas a cada ~5 min, 18 viaturas)**, perda total
(espera de entrada + perda na rede), sem → com preempção:

| Cenário | Ciclo fixo | v2 | v3 | max-pressure |
|---|---:|---:|---:|---:|
| calibrado | 16,6 → **1,3 s** | 8,0 → **1,3 s** | — | 7,9 → 1,4 s |
| original | 31,3 → 13,6 s | 12,2 → 2,9 s | — | 13,0 → **2,8 s** |
| calibrado + pedestres | 32,9 → 7,9 s | 26,7 → 8,6 s | 23,2 → **6,2 s** | 90,1 → 15,9 s |
| original + pedestres | 118,5 → 69,9 s | 96,8 → 72,8 s | 97,6 → 81,5 s | 106,4 → 99,9 s |

Valores com preempção refeitos em 2026-10-12, depois da correção do aviso V2I
no step da inserção (subseção seguinte). Os anteriores ficaram em
`preempcao-*-oracle-lacuna-insercao.json`.

- Calibrado sem pedestres: 100% das viaturas cruzam sem parar, espera de
  entrada ~1 s.
- **Calibrado com pedestres: o problema da investigação anterior sumiu.** A
  espera de entrada fica em 3–4 s, a perda total cai para 6–9 s (máx. 39 s,
  quem chega durante a fase de pedestres) e os pedestres praticamente não
  pioram com a preempção (v2: mediana 15 → 12 s, p90 72 → 74 s; v3: 12 → 14 s,
  74 → 74 s).
- No `original_ped`, ainda saturado, a viatura continua presa na fila de
  inserção (~60–75 s) e os pedestres pioram com a preempção, como antes.
  Sem preempção, nem todas as viaturas cruzam até o fim da rodada (17/18 na
  v2 e na v3, 16/18 no max-pressure); a média é só das que cruzaram.

### Correção: aviso V2I no step da inserção da viatura (2026-10-12)

No step em que a viatura era inserida, `EmergencyTraffic.step` chamava
`add_vehicle` e não emitia pedido: ela só aparece no TraCI no step seguinte.
Nesse step a preempção soltava o semáforo e a política voltava a ser
consultada; se pedisse troca, começava um amarelo com a viatura chegando. Em
todos os modos com V2I, as 18 viaturas passaram por essa lacuna. Apareceu na
avaliação visual do `original`: na seed 203 o DQN trocou o verde Sul no step
da inserção e a viatura parou (15,9 s de perda, contra 3,9 s com percepção
*ground truth*). A correção (commit `b8cf953`, com teste) mantém o pedido no
step da inserção com o tempo de uma aproximação inteira. "Sem preempção" e
"só visão" não dependem do aviso V2I e não mudam.

Percepção *ground truth* refeita nos quatro cenários (tabela acima):

- sem pedestres, a perda com V2I cai um pouco (calibrado 1,4–1,5 → 1,3–1,4 s;
  original v2 3,1 → 2,9 s, max-pressure 3,3 → 2,8 s) e o custo para o tráfego
  diminui (v2 calibrado +0,8 → +0,6 s; original +1,1 → +0,7 s);
- no `calibrated_ped`, a v2 ficou pior (5,2 → 8,6 s, 94% → 72% sem parar) e a
  v3 melhor (7,7 → 6,2 s). As viaturas que pioraram foram anunciadas com a
  fase de pedestres já em andamento (conferido nas fases de cada step), que a
  preempção espera terminar. A correção mudou o instante de algumas trocas, a
  fase de pedestres caiu em outro ponto do ciclo e outras viaturas passaram a
  coincidir com ela. Com 18 viaturas, cada uma que espera a fase de pedestres
  soma ~1–2 s à média: a diferença entre v2 e v3 está dentro dessa variação.

As linhas "V2I" e "V2I + visão" das tabelas visuais abaixo ainda são de antes
da correção; os comandos para refazê-las estão em
`TEMP_PREEMPCAO_CORRECAO.txt` (`--detections v2i,both --skip-no-preemption`).

### Avaliação visual com a demanda sem motos (Unity, 2026-10-08)

Mesmo protocolo (seeds 201–203, 300 s + 1800 s), cenário `calibrated`, YOLO
de duas classes, **0 frames perdidos** e 0 observações perdidas em todas as
execuções. Arquivos: `results/evaluation/versoes-calibrated-visual.json` e
`preempcao-calibrated-visual.json` (os da demanda antiga ganharam o sufixo
`-motos`); logs em `results/logs/versoes-calibrated-visual.log` e
`preempcao-visual-calibrated.log`. Teste rápido antes (v2, seed 201, 300 s):
`versoes-calibrated-visual-teste.json`, espera 4,5 s.

**Versões** (espera média; por seed entre parênteses):

| Versão | *Ground truth* | Visão | Visão − *ground truth* | Trocas (visão) |
|---|---:|---:|---:|---:|
| ciclo fixo | 13,0 s | 13,0 s | 0 | 0 |
| v1 | 4,41 s | **4,27 s** (4,41 / 4,41 / 3,99) | −0,14 | 121 |
| v1.1 | 5,70 s | 5,70 s | 0 | 129 |
| v2 | **4,15 s** | 4,31 s (4,47 / 4,03 / 4,44) | +0,16 | 110 |
| max-pressure | 4,72 s | 4,77 s | +0,05 | 116 |

Chegadas 915–918 e fila de inserção 0 em todas.

- A visão custa no máximo 0,16 s.
- Com visão, v1 e v2 empatam (diferença de 0,04 s, menor que a variação
  entre seeds). Sem saturação, alternar perto do mínimo já é quase ótimo,
  como no cenário `original`; a vantagem da v2 aparecia com o Leste
  saturado.
- A v1.1 é idêntica nas duas percepções, seed por seed: troca sempre no
  verde mínimo (10 + 3 + 1 s ≈ 14 s por fase → 129 trocas em 1800 s), ou
  seja, é uma política degenerada que não depende do estado.

**Preempção com visão** (v2, 18 viaturas; perda total = espera de entrada +
perda na rede; arquivo `results/evaluation/preempcao-calibrated-visual.json`,
0 frames perdidos). V2I e V2I + visão refeitos em 2026-10-13, depois da
correção do aviso na inserção (`preempcao-calibrated-visual-correcao.json`,
log `results/logs/preempcao-visual-calibrated-correcao.log`, juntados ao
arquivo principal); os anteriores ficaram em
`preempcao-calibrated-visual-lacuna-insercao.json`.

| Fonte do pedido | Perda total média | Máx. | Sem parar | Antecedência | Espera do tráfego |
|---|---:|---:|---:|---:|---:|
| nenhuma | 7,6 s | 19,7 s | 50% | — | 4,3 s |
| V2I | **1,4 s** | 2,0 s | 100% | ~23 s | 4,6 s |
| visão | 2,7 s | 9,0 s | 89% | 4,9 s | 4,6 s |
| V2I + visão | **1,4 s** | 2,0 s | 100% | — | 4,9 s |

Antes da correção: V2I 1,5 s (máx. 3,2 s), V2I + visão 1,4 s (máx. 3,3 s).

- A visão detectou as 18 viaturas, sem alarme falso. Sozinha, reduz a perda
  em 65% (7,6 → 2,7 s).
- V2I com percepção visual dá o mesmo resultado que com a percepção
  *ground truth* (1,4 s × 1,3 s); a perda na rede não passa de 1,0 s. A espera de entrada fica em 1,0 s em todos os modos (a
  latência de 1 step), sem fila de inserção.
- Custo para o tráfego: +0,3 s (visão e V2I) a +0,6 s (V2I + visão).

### Avaliação visual do cenário original (Unity, 2026-10-12)

Mesmo protocolo (seeds 201–203, 300 s + 1800 s), cenário `original`, v2 =
`dqn-v2-traffiq-best.pt`, **0 frames perdidos** e 0 observações perdidas.
A demanda do `original` não mudou; mudou só o checkpoint da v2. Arquivo:
`results/evaluation/versoes-original-visual.json` (a rodada com o checkpoint
anterior ficou em `versoes-original-visual-motos.json`); log em
`results/logs/versoes-original-visual.log`.

| Versão | *Ground truth* | Visão | Visão − *ground truth* | Trocas (GT → visão) |
|---|---:|---:|---:|---:|
| ciclo fixo | 14,95 s | 14,95 s | 0 | 0 |
| v1 | 4,72 s | **4,59 s** (4,55 / 4,65 / 4,57) | −0,13 | 129 → 129 |
| v1.1 | 4,65 s | 4,65 s | 0 | 127 → 127 |
| v2 | **4,47 s** | 5,18 s (5,20 / 5,13 / 5,22) | +0,71 | 128 → 110 |
| max-pressure | 4,57 s | 6,08 s (6,19 / 5,77 / 6,27) | +1,51 | 129 → 97 |

Chegadas 1471–1474 e fila de inserção final 0–1 nas adaptativas (ciclo fixo:
1431 e 37).

- Com a câmera, a v2 e o max-pressure trocam menos de fase e seguram o verde
  um pouco mais; a v1, que só olha a contagem, não muda. O max-pressure
  decide por veículos parados, e o "parado" visual vem da velocidade estimada
  a 1 fps, subestimada em 0,1–0,9 m/s (subseção **Pedestres na Unity**).
- No cenário calibrado a visão custava no máximo 0,16 s; aqui custa até
  1,5 s porque, com demanda equilibrada, alternar no mínimo já é quase ótimo e
  qualquer verde a mais aparece na média. Mesmo assim, todas as adaptativas
  ficam 59–69% abaixo do ciclo fixo.
- O checkpoint anterior da v2 dava 4,88 s com visão no mesmo cenário (5,06 s
  com *ground truth*): o atual é melhor com *ground truth* e pior com visão,
  diferenças da ordem de 0,3–0,6 s.
- A v1.1 de novo é idêntica nas duas percepções (troca sempre no mínimo).

**Preempção com visão** (v2, 18 viaturas; perda total = espera de entrada +
perda na rede; arquivo `results/evaluation/preempcao-original-visual.json`,
0 frames perdidos). "Nenhuma" e "visão" são de 2026-10-12. V2I e V2I + visão
foram refeitos em 2026-10-13, depois da correção do aviso na inserção
(`preempcao-original-visual-correcao.json`, log
`results/logs/preempcao-visual-original-correcao.log`, juntados ao arquivo
principal); os anteriores ficaram em
`preempcao-original-visual-lacuna-insercao.json`.

| Fonte do pedido | Perda total média | Máx. | Sem parar | Antecedência | Espera do tráfego |
|---|---:|---:|---:|---:|---:|
| nenhuma | 11,2 s | 21,8 s | 39% | — | 5,2 s |
| V2I | 2,9 s | 6,6 s | 100% | ~24 s | 6,0 s |
| visão | 4,5 s | 13,9 s | 94% | ~6 s | 5,5 s |
| V2I + visão | **2,8 s** | 6,6 s | 100% | — | 6,1 s |

Antes da correção: V2I e V2I + visão davam 3,7 s (máx. 15,9 s, 94% sem
parar). A viatura que parava era a da seed 203: o DQN trocou o verde Sul no
step da inserção.

- A visão detectou as 18 viaturas em todos os modos, sem alarme falso.
- V2I com a câmera dá o mesmo que com a percepção *ground truth* (2,9 s ×
  2,9 s). A perda é maior que no calibrado (1,4 s) porque há mais fila de
  inserção no `original` (espera de entrada de 1,8 s, contra 1,0 s).
- A visão sozinha reduz a perda em 60% (11,2 → 4,5 s); no calibrado eram 65%.
- Custo para o tráfego: +0,3 s (visão) a +0,9 s (V2I + visão).

### Avaliação visual com pedestres (Unity, 2026-10-09; fase antiga)

Fase de pedestres antiga (41 s + 3 s a cada dois ciclos); com a fase
atual, ver a seção **Fase de pedestres curta**. Os arquivos desta subseção
ganharam o sufixo `-fase-41s`.

Cenário `calibrated_ped`, mesmo protocolo (seeds 201–203, 300 s + 1800 s),
pedestres renderizados na Unity (subseção **Pedestres na Unity**), v3 =
`dqn-v3-sem-motos-best.pt`, **0 frames perdidos** e 0 observações perdidas.
Arquivo: `results/evaluation/versoes-calibrated_ped-visual.json`; log em
`results/logs/versoes-calibrated_ped-visual.log`. Teste rápido antes (v3,
seed 201, 300 s): `versoes-calibrated_ped-visual-teste.json`, espera 17,4 s.

A primeira tentativa caiu no v1 com `OSError: Message too long`: com
pedestres, a mensagem de estado passava do limite de 9216 bytes por
datagrama UDP do macOS (`net.inet.udp.maxdgram`). O JSON agora é compacto e
arredondado ao milímetro e, acima de 8192 bytes, vai em partes que a Unity
junta pelo `step_id` (`fix:` 34112bb).

**Versões** (espera dos veículos, por seed entre parênteses; pedestres:
média, mediana / p90):

| Versão | Veículos, *ground truth* | Veículos, visão | Fila final (visão) | Pedestres, *ground truth* | Pedestres, visão |
|---|---:|---:|---:|---|---|
| ciclo fixo | 24,5 s | 24,5 s | 0 | 64,1 s (48 / 163) | 64,1 s (48 / 163) |
| v1 | 30,2 s | 30,1 s (27,4 / 30,4 / 32,5) | 26 | 22,0 s (11 / 57) | 21,8 s (11 / 59) |
| v2 | 21,3 s | **20,4 s** (20,3 / 20,6 / 20,2) | 0 | 25,6 s (10 / 70) | 28,3 s (14 / 77) |
| v3 | 21,3 s | 21,5 s (20,6 / 21,6 / 22,2) | 0 | 27,9 s (12 / 74) | 26,6 s (9 / 74) |
| max-pressure | 34,2 s | 32,6 s | 39 | 19,1 s (7 / 53) | 21,4 s (11 / 57) |

Chegadas de veículos (visão): ciclo fixo 906, v1 875, v2 909, v3 909,
max-pressure 860; pedestres 153–161.

- Com pedestres na imagem, a visão continua equivalente à percepção *ground truth*: as
  diferenças vão de −1,6 a +0,2 s nos veículos e de −1,3 a +2,7 s na média dos
  pedestres, da ordem da variação entre seeds.
- v2 e v3 seguem empatadas nos veículos (20,4 × 21,5 s) e trocam de posição
  nos pedestres em relação à percepção *ground truth* (v2 28,3 × v3 26,6 s; na percepção *ground truth*, 25,6
  × 27,9 s). Com 3 seeds, nenhuma das duas é melhor que a outra.
- A v1 e o max-pressure decidem só pelas filas de veículos; deixam os
  pedestres esperando menos (~21 s), mas acumulam fila de inserção (26 e 39
  veículos no fim) e pioram a espera dos veículos para 30–33 s, acima do
  ciclo fixo.
- O ciclo fixo dá números idênticos nas duas percepções (não usa a visão).

**Preempção com visão e pedestres** (v2 e v3, mesma agenda de 18 viaturas;
perda total = espera de entrada + perda na rede; arquivo
`results/evaluation/preempcao-calibrated_ped-visual-fase-41s.json`, 0 frames
perdidos). V2I e V2I + visão são de antes da correção da lacuna na inserção.
Não foram refeitos porque a fase mudou; com a fase atual, ver a seção **Fase
de pedestres curta**.

| Versão | Fonte do pedido | Perda total média | Máx. | Sem parar | Antecedência | Espera do tráfego | Pedestres (mediana / p90 / máx.) |
|---|---|---:|---:|---:|---:|---:|---|
| v2 | nenhuma | 24,4 s | 83,2 s | 50% | — | 20,2 s | 28,8 s (17 / 74 / 94) |
| v2 | V2I | **5,5 s** | 38,9 s | 100% | ~27 s | 20,7 s | 31,3 s (16 / 84 / 111) |
| v2 | visão | 14,2 s | 38,9 s | 72% | ~11 s | 21,1 s | 28,8 s (19 / 75 / 98) |
| v2 | V2I + visão | 8,4 s | 38,9 s | 89% | — | 21,6 s | 30,2 s (15 / 82 / 110) |
| v3 | nenhuma | 15,7 s | 41,3 s | 61% | — | 21,4 s | 28,3 s (15 / 77 / 95) |
| v3 | V2I | 9,9 s | 38,9 s | 89% | ~31 s | 22,8 s | 30,5 s (18 / 80 / 111) |
| v3 | visão | 13,4 s | 40,5 s | 67% | ~13 s | 21,4 s | 28,2 s (12 / 75 / 94) |
| v3 | V2I + visão | **7,3 s** | 38,9 s | 83% | — | 23,4 s | 30,1 s (18 / 79 / 115) |

Percepção *ground truth*, mesma agenda (V2I), antes da correção: v2 26,7 → 5,2 s, v3 23,2 → 7,7 s (depois: 8,6 s e 6,2 s).

- **V2I com visão reproduz a percepção *ground truth*:** v2 5,5 s (*ground truth*: 5,2 s), v3 9,9 s
  (7,7 s). A visão detectou as 18 viaturas em todos os modos, sem alarme falso.
- **A máxima de ~39 s aparece em todos os modos:** é a viatura que chega
  durante a fase de pedestres, que nem a preempção encerra. Sem contar as
  perdas acima de 15 s (2–7 viaturas de 18), a média com preempção fica em
  2–5 s. Uma viatura tem 35 s de espera de entrada em todos os modos (a fila
  da fase de pedestres chega à borda da rede).
- **Visão sozinha** reduz a perda da v2 em 42% (24,4 → 14,2 s), menos que sem
  pedestres (65%): ela vê a viatura ~11–13 s antes, e qualquer espera pela
  fase de pedestres anula essa antecedência.
- **V2I + visão não supera V2I na v2** (8,4 × 5,5 s), e na v3 é o melhor
  modo. Com 18 viaturas por modo, duas ou três que caem na fase de pedestres
  mudam a média em 3–5 s; as diferenças entre V2I e V2I + visão e entre v2 e
  v3 estão dentro dessa variação.
- **Pedestres:** a preempção piora pouco a espera deles (média +1 a +3 s,
  máxima 94 → 111–115 s), sem os bloqueios de vários minutos da demanda
  antiga.
- **Tráfego:** +0,5 a +2 s de espera para os demais veículos.

## Pedestres (fase exclusiva)

Status: rede, fase de pedestres, estado v3 e métricas implementados em
2026-10-05 (branch `feat/pedestres`); só SUMO até 2026-10-08, quando a
Unity passou a renderizar pedestres, faixas e sinais (subseção **Pedestres na
Unity**). Decisões do usuário: fase
exclusiva (todos os veículos no vermelho, todas as faixas verdes) a cada dois
ciclos; verde que cubra a travessia em "L" a 1,2 m/s; nova versão de estado.
Desde 2026-10-13 a fase é curta e vem a cada ciclo (seção **Fase de
pedestres curta**); a tabela de "L" abaixo é da regra antiga.

### Rede

`experiments.build_pedestrian_network` gera, a partir da rede atual (que não
muda), `Cruzamento.ped.net.xml` (`netconvert --sidewalks.guess
--crossings.guess`), os detectores E2 nas faixas renumeradas, os fluxos de
pedestres e os `.sumocfg` dos cenários `calibrated_ped` e `original_ped`.

- A geometria das faixas de veículos e os links 0–9 do semáforo são os mesmos;
  as travessias são os links 10–13: Leste 13,0 m, Sul 12,8 m, Oeste 11,2 m,
  Norte 12,0 m.
- A calçada vira a faixa 0 de cada via (`E3_0` → `E3_1`).
  `SumoClient.vehicle_lane_id` traduz o ID lógico do perfil, então ROIs,
  recompensa e percepção *ground truth* funcionam nas duas redes.
- Demanda sintética (o drone não mediu pedestres): 300 pedestres/h, chegadas
  Poisson divididas igualmente entre os 30 pares de calçadas.
- **Deadlock corrigido:** as duas faixas de conversão Sul → Leste se fundem
  numa só depois da faixa de pedestre Leste. O netconvert criou um ponto de
  espera interno por faixa antes da travessia, e os dois cediam passagem um ao
  outro: 6–12 teleportes por episódio de 1800 s. Com `contPos="0"` nessas
  conexões a espera fica na linha de retenção, como na rede sem pedestres:
  0 teleportes. Geometria, links e travessias não mudam.

### Fase de pedestres

Regra antiga (até 2026-10-13):

| Esquina | Travessia + esquina + travessia | Verde a 1,2 m/s |
|---|---|---:|
| Nordeste (Leste + Norte) | 13,0 + 20,3 + 12,0 = 45,3 m | 38 s |
| Sudeste (Leste + Sul) | 13,0 + 9,9 + 12,8 = 35,7 m | 30 s |
| **Sudoeste (Sul + Oeste)** | **12,8 + 24,0 + 11,2 = 48,05 m** | **41 s** |
| Noroeste (Oeste + Norte) | 11,2 + 12,0 + 12,0 = 35,2 m | 30 s |

- Sequência antiga: L/O → Sul → L/O → Sul → all-red (1 s) → verde de
  pedestres (41 s, o maior "L") → liberação em vermelho total (3 s) → L/O.
  Atual: L/O → Sul → all-red (1 s) → verde de pedestres (7 s) → liberação
  (11 s) → L/O.
- Obrigatória como o amarelo: a política não a encerra nem a pula. A
  preempção não a interrompe; uma viatura que chega quando ela ainda não
  começou passa à frente, e a fase vem na próxima oportunidade.
- Estado v3 (44 entradas): v2 + one-hot das 7 fases + verdes até a fase de
  pedestres. v1/v2 continuam rodando na rede com pedestres, vendo as fases de
  pedestre como all-red.
- Métricas novas: espera média, p95 e máxima dos pedestres (steps parados até
  sair da rede), pedestres atendidos e na rede ao fim.

### Decisões de projeto (tomadas antes da recalibração da demanda)

- **Estado v3:** a v2, treinada sem pedestres, ficou pior que o ciclo fixo
  na rede com a fase exclusiva, o que motivou um estado que vê as fases de
  pedestre e quantos verdes faltam até a próxima.
- **Pedestres na recompensa** (decisão do usuário, 2026-10-05): com a
  recompensa só dos veículos, o v3 aprendeu a segurar o verde para espaçar a
  fase de pedestres, e os pedestres esperavam mais. Nos cenários com
  pedestres a recompensa é `(1 − w)·veículos − w·min(1, Σ espera atual dos
  pedestres parados / ref.)`, com ref. = 1200 s (p90 dessa soma com o ciclo
  fixo; com 600 s o termo saturava em 32% do tempo). Bloco `pedestrians:` do
  `sp.yaml`; a política continua sem ver o TraCI.
- **Peso e duração do treino:** `w` = 0,2, 0,3 e 0,5 com 100 episódios
  (seeds 51–150). Com 0,5 os veículos pioravam até perto do ciclo fixo; 0,2 e
  0,3 ficaram praticamente iguais. Ficou `w` = 0,3, e 100 episódios foram
  melhores que 40 para veículos e pedestres.
- **Fase a cada dois ciclos, não três:** a cada três ciclos os veículos
  ganhavam, mas a mediana de espera dos pedestres dobrava.
- **Adiamento pela viatura** (`fix:` 7483050): a fase de pedestres ainda não
  iniciada que uma viatura adia vem no all-red seguinte, logo depois do verde
  dela, e o ciclo retoma pelo verde que viria. Antes ela esperava mais um
  verde Sul completo, e alguns pedestres ficavam mais de 7 min parados.
- **Métricas da viatura:** a perda só contava depois da entrada na rede, e uma
  viatura presa na fila de inserção parecia não ter atraso. O resumo passou a
  ter `mean_insertion_delay_s` e `mean_total_loss_at_crossing_s` (inserção +
  perda na rede), e os pedestres ganharam mediana e p90.
- **Viaturas a cada ~5 min** (`interval_s` 180 → 300).

### Pedestres na Unity (2026-10-08, branch `feat/pedestres-unity`)

- **Modelos:** Quaternius Animated Men/Women Pack, licença CC0, versão
  *Smooth* (~4 mil polígonos). A malha vem com ~4,8 m e o importador usa
  escala 0,36 (≈ 1,74 m / 1,67 m). Origem registrada em
  `Assets/Art/TrafficModels/Models/Pedestrians/README.md`.
- **Protocolo:** a mensagem de estado ganhou `pedestrians` (id, x, y, z,
  ângulo e velocidade do `traci.person`), com a mesma conversão de
  coordenadas dos veículos e vazia na rede sem pedestres
  (`tests/test_state_message.py`).
- **Render:** `PedestrianManager` toca a caminhada acima de 0,1 m/s, com a
  cadência pela velocidade, e reaproveita os objetos.
- **Cena:** o menu *Build SP Crosswalks and Corners* lê
  `Cruzamento.ped.net.xml` e cria:
  - faixas zebradas com listras de 0,4 m e 1 m livre antes da linha de
    parada;
  - cantos de espera, cada um a envoltória convexa da `walkingarea` com as
    pontas das calçadas geradas (que subiram para 1 cm acima do asfalto,
    como os cantos);
  - 8 sinais de pedestre, ligados aos links 10–13.

**Efeito dos pedestres na visão** (v2, seed 1001, 300 s de controle, 0
frames perdidos; `results/logs/visao-pedestres-*.jsonl`,
`experiments.evaluate_lane_features`):

| Cenário | Contagem: erro relativo | Parados: erro relativo | Espera: erro relativo | Visão vê veículo onde não há | Ações iguais às da percepção *ground truth* |
|---|---:|---:|---:|---:|---:|
| `calibrated` (sem pedestres) | 10% | 27% | 53% | 2,2% | 93% |
| `calibrated_ped` | 4% | 7% | 11% | 0,9% | 96% |

No `calibrated`, o viés por faixa fica em +0,01 a +0,18 veículo na contagem
(nenhuma faixa subconta), −0,1 a −0,9 m/s na velocidade e +0,2 a +4,2 s na
espera. O erro relativo cai com pedestres porque as filas ficam maiores com a fase
exclusiva (espera média *ground truth* por faixa: 3,0 s → 43,5 s). Os erros
absolutos da contagem ficam iguais (0,10 × 0,09 veículo por faixa). Nas
capturas da câmera sul durante a fase de pedestres, o YOLO de duas classes
não detecta as pessoas: as caixas são só os carros, com confiança de
0,94–0,99. Pedestres não poluem o estado visual, então a v3 pode ser
avaliada com percepção visual.

## Ambiente com ROIs de 60 m e preempção para emergências

Status: câmeras, ROIs e preempção V2I concluídos (branch `feat/cameras-60m`,
2026-09-30). Os resultados atuais estão na seção **Demanda calibrada sem
motos**.

### Câmeras e ROIs

- As câmeras antigas ficavam a ~5 m de altura, na mesma altura das caixas dos
  semáforos, que cobriam parte das faixas, e viam só ~25 m de cada uma.
- As poses novas (menus *Traffic Vision > Cameras > Create SP … Camera*)
  foram calculadas a partir da geometria das lanes e dos postes. Cada câmera
  fica 15–30 m depois da linha de retenção, a 6–9 m de altura, mirando no
  meio do trecho de 60 m. A oclusão pelos postes foi medida por área na
  imagem, com folga para a carroceria: 0%.
- As ROIs de faixa foram desenhadas na linha de retenção e estendidas por
  cálculo até **60,0 m** em todas as faixas (`experiments.extend_lane_rois`,
  importadas na cena pelo menu *Import SP Calibration JSON*). A borda
  distante fica a ~8% do topo da imagem; um carro a 60 m tem ~31–53 px de
  altura. A capacidade de cada ROI passou de ~3,4 para 8 veículos parados.
- O YOLO foi retreinado para as poses novas (seção **Segundo fine-tuning**).

### Detecção visual de viaturas (segunda fonte de preempção)

Status: implementada e avaliada em malha fechada em 2026-10-02.

- **Regra** (`vision/visual_emergency.py`): por aproximação, não por
  `track_id`. A 1 fps uma viatura a ~14 m/s cruza os 60 m da ROI em ~4 frames,
  e o ByteTrack não mantém a identidade dela com segurança. Há viatura quando
  algum objeto da classe `emergency` cai numa ROI de faixa em
  `confirm_frames = 2` frames seguidos. A distância até a linha é a posição
  na ROI (mesma homografia das features) + `roi_start_m`. O tempo até a linha
  usa a velocidade medida entre frames, com piso na metade da velocidade
  livre, a mesma regra do V2I. Sem ver a viatura (saiu da ROI rumo à linha,
  ficou oculta ou faltou frame), o pedido continua por esse tempo +
  `hold_margin_s = 3 s` e então se encerra. O pedido entra na mesma
  `EmergencyPreemption` do V2I.
- **Fontes comparadas:** `v2i`, `vision` e `both` (união). Na mesma agenda,
  política e percepção das features, muda só a fonte do pedido.
- **Métricas novas** por viatura e por episódio: antecedência do V2I e da
  visão até a linha, viaturas detectadas pela visão, eventos visuais e
  alarmes falsos (evento sem viatura na aproximação). Em
  `sem_preempcao` com a Unity, a visão também é medida, sem agir.
- **Teste offline** nos frames capturados do run-304 (sem preempção, YOLO +
  ByteTrack sobre os JPEGs): as 10 passagens de viatura pelas ROIs foram
  detectadas, sem evento falso. A distância visual fica ~1 m acima da real.
  A primeira detecção ocorre a ≤ 55 m, e o pedido confirmado sai a ~40 m da
  linha: ~3–4 s em velocidade livre, menos que amarelo + all-red (4 s). Por
  isso se espera que a visão sozinha reduza o atraso das viaturas, mas não o
  elimine como o V2I (que avisa ~15 s antes de a viatura entrar na rede).
  Viaturas paradas na fila dentro da ROI são vistas e pedem passagem.
- **Limitações:** uma viatura por aproximação de cada vez; a visão não vê
  viaturas antes da ROI.

```bash
# Unity em Play Mode (SPImport); ~45 min por seed, política e modo
../.venv/bin/python -m experiments.evaluate_preemption --scenario calibrated --perception visual \
  --versions v2 --seeds 201,202,203
```

### Correção: filtro da ROI de aproximação pela base da caixa (2026-10-03)

A análise da subcontagem do Leste no log da v2 visual mostrou:

- **Leste, 50–60 m: ~100% dos veículos perdidos nas duas faixas**, mesmo
  isolados (sem veículo à frente). Não era oclusão: o YOLO detecta esses
  veículos (98,6% no teste), mas `filter_detections_to_roi` descartava a
  detecção porque usava o **centro** da caixa. Num carro distante, visto de
  lado, o centro cai fora do polígono de aproximação, embora a base (o ponto de
  solo usado pela homografia das faixas) esteja dentro da faixa.
- O mesmo acontecia nas outras câmeras. No replay offline do run-304 (250
  frames por câmera), objetos projetados a 50–60 m, com centro → com base:
  Leste 2 → 195, Sul 46 → 192, Oeste 3 → 30. Abaixo de 50 m não muda.
- A geometria está correta: com o veículo detectado, a distância visual fica
  +0,8 m da posição *ground truth* em todas as faixas e distâncias.
- Com as filas longas da demanda anterior, a faixa 1 do Leste também perdia
  17–40% a 10–50 m, mais com fila parada (35%) que em movimento (26%). Aí as detecções brutas já faltavam: é oclusão pela
  faixa 0 no ângulo lateral da câmera Leste, e não se corrige no filtro. Com
  a demanda atual as filas são curtas e nenhuma faixa subconta.

Correção: `filter_detections_to_roi(..., anchor="bottom_center")` no
`VisualPipeline`, com o mesmo ponto de solo das features por faixa (o padrão
`center` continua para o legado `test_unity_vision`). Na detecção de viaturas,
o pedido passa a sair a ~55–60 m da linha, em vez de ~40 m.

### Preempção por aviso V2I

V2I (*vehicle-to-infrastructure*, "veículo para infraestrutura"):
comunicação direta entre o veículo e equipamentos da via, aqui o controlador
do semáforo. Na prática, a viatura informa a aproximação de onde vem e o tempo
estimado até a linha de retenção, a partir do GPS dela ou do despacho da
central. No SUMO o aviso é simulado por `sumo/emergency.py`
(`EmergencyRequest`).

- Viaturas de emergência entram a cada ~5 min, sorteadas entre Sul, Leste e
  Oeste, obedecendo ao semáforo.
- O aviso V2I chega 15 s antes de a viatura entrar na rede. A preempção
  assume quando ela está a ≤ 20 s da linha de retenção: mantém o verde dela
  (além do verde máximo, se preciso) ou encerra o outro verde sem esperar o
  mínimo. Amarelo e all-red nunca são pulados.
- Métrica da viatura: perda total até cruzar a linha de retenção (espera de
  entrada + `getTimeLoss`).

## DQN v2 — estado por faixa, pré-treino SUMO e avaliação visual

Status: concluído (branch `feat/estado-faixa-v2`, 2026-09-28/29). Esta seção
registra o desenho da v2; os resultados atuais estão na seção **Demanda
calibrada sem motos**.

### Por que o v1 foi substituído

- O checkpoint "melhor" do v1 era o do episódio 4 (240 passos de gradiente,
  ε≈0,98): o ε decaía por episódio (`0.995**episódio`, ainda ≈0,78 no fim do
  treino), a validação empatava e o primeiro valor vencia. A política
  colapsou em "trocar assim que o verde mínimo permite" e empatou com o
  heurístico.
- A recompensa somava a espera acumulada só dos veículos ativos: quando um
  veículo com muita espera saía da rede, a recompensa ficava positiva.
- A demanda original é equilibrada (v/c≈0,5 nas duas fases), então o tempo de
  verde quase não muda o resultado.

### Correções de base (valem para qualquer política)

- **Fases do TLS sob controle do Python.** `apply()` só chamava `setPhase` e
  os steps sem frames pulavam o controlador, então o programa estático do SUMO
  avançava sozinho. Com 20% de frames ausentes, o SUMO foi 4 vezes do amarelo
  direto ao verde sem all-red em 600 s. Agora `apply()` fixa a duração da fase
  e `update_without_vision()` mantém amarelo, all-red e verde máximo quando não
  há visão. **Resultados gravados antes dessa correção devem ser refeitos.**
- **Cenários.** `sp.yaml` declara `calibrated` (padrão; demanda medida nos
  vídeos de drone) e `original`; escolha com `--scenario`.
  Na cópia calibrada em `sumo/sp`, as chegadas são Poisson (a seed passa a
  mudar a demanda) e a inserção é realista (`departLane="best"`,
  `departSpeed="max"`): com o padrão do SUMO, 231 veículos ficavam pendentes em
  1200 s no plano estático por causa da própria inserção, contra 49 depois.
- **Fila de inserção nas métricas.** Veículos que ainda não entraram na rede
  não aparecem na espera média; as avaliações v2 registram
  `mean/final_pending_vehicles`.

### Geometria das ROIs

`experiments.check_lane_geometry` projeta as ROIs no solo pela pose e FOV das
câmeras Unity. As larguras projetadas coincidem com as das lanes (3,0–4,3 m
para 3,2/4,0 m), mas as ROIs cobrem só **23–26 m por faixa**, terminando na
linha de retenção, enquanto os E2 atuais cobrem 42,6–45,8 m. Os intervalos
medidos estão em `lane_geometry` no `sp.yaml`, protegidos por teste. Decisão:
**manter as ROIs como estão** e declarar a limitação. Depois elas foram
substituídas pelas de 60 m (seção **Ambiente com ROIs de 60 m**).

### Estado v2 e treino

- Por faixa (7): contagem, parados (< 1,39 m/s por ≥ 1 s, padrão do E2),
  ocupação espacial, velocidade média e espera, normalizados pela capacidade
  da ROI (comprimento / 7,5 m); mais a fase em one-hot e o tempo da fase — 41
  entradas.
- As features vêm de `ApproachKinematicsTracker`, alimentado por duas fontes
  com o mesmo contrato: visão (base das bboxes projetada pela homografia da
  ROI) e *ground truth* TraCI (posições reais no mesmo intervalo da ROI). Um teste de
  paridade garante features idênticas para a mesma trajetória.
- A política só decide em verde, entre o verde mínimo e o máximo, a cada 5 s;
  as transições são SMDP (recompensa acumulada com desconto γ^k, γ=0,99/s).
- Recompensa: nível em [−1, 0] sobre as lanes de entrada inteiras (parados,
  espera nativa e fila de inserção), vinda do TraCI; não é entrada da política.
- Pré-treino só SUMO com a percepção *ground truth*: 40 episódios de 300 s de aquecimento +
  1800 s controlados (~6 s por episódio), seeds 1–40, Double DQN, ε linear por
  decisão. Treinada só no calibrado, a v2 especializava e piorava no
  original; por isso o pré-treino usa os dois cenários.

### Ajuste fino visual

10 episódios de 900 s com a Unity no loop (seeds 41–50, ~900 passos de
gradiente) pioraram a validação visual, e o critério manteve a política
pré-treinada (zero-shot). Causa provável, não verificada: o replay recomeça
vazio e só com as transições correlacionadas do ajuste fino.

### Registro histórico da v1 e da v1.1 (protocolos diferentes)

Estes são os resultados originais, preservados como registro. **Não são
comparáveis com a v2 nem entre si:**

- usaram a demanda original e só 100 s simulados;
- a referência era o plano estático do SUMO (verdes de 42/41 s);
- rodaram antes da correção de sincronização das fases.

Em 100 s de demanda equilibrada, qualquer política de ciclo curto supera um
plano de 42/41 s, o que explica boa parte do ganho aparente.

v1 (heurística visual), seeds 42, 7 e 99, 2026-09-02:

| Métrica (média) | Tempo fixo | Controle visual | Variação |
| --- | ---: | ---: | ---: |
| Veículos concluídos | 50,67 | 60,67 | +19,7% |
| Vazão | 1842,4 veh/h | 2206,1 veh/h | +19,7% |
| Tempo médio de viagem | 27,35 s | 26,11 s | −4,6% |
| Tempo médio de espera | 6,77 s | 3,93 s | −42,0% |
| Fila média | 8,70 | 3,89 | −55,3% |
| Fila máxima | 19,67 | 9,33 | −52,5% |

v1.1 (DQN visual, estado v1), seeds 201–203, 2026-09-04:

| Métrica (média) | Tempo fixo | Heurístico visual | DQN visual v1 |
| --- | ---: | ---: | ---: |
| Veículos concluídos | 50,67 | 60,67 | 60,33 |
| Vazão (veíc./h) | 1842,42 | 2206,06 | 2193,94 |
| Tempo médio de espera | 6,85 s | 4,41 s | 4,44 s |
| Fila média | 8,73 | 4,15 | 4,21 |
| Fila máxima | 18,67 | 10,33 | 10,33 |

## Avaliação visão versus E2 — cenário SP

Status: implementada e executada em 100 steps com as câmeras e calibrações
atuais.

O E2 permanece exclusivamente como verdade de terreno de avaliação. A decisão
online continua recebendo somente a saída visual. A comparação desta seção é
diagnóstica, não uma medida direta de erro do detector. Na época, os E2
cobriam 20 m; hoje cobrem 42,6–45,8 m, enquanto as ROIs das câmeras cobrem
23–26 m. A medida estrita passou a ser a do DQN v2 (seção anterior): visão ×
*ground truth* TraCI no mesmo intervalo físico de cada ROI.

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
  --calibration-dir ../unity/TraffIQ-TCC/Assets/Calibration \
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
  --calibration-dir ../unity/TraffIQ-TCC/Assets/Calibration \
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

Importante: quando esta comparação foi feita, os E2 cobriam 20 m de cada
faixa perto do cruzamento, e a diferença de área observada entra no erro. A
medida no mesmo trecho físico da ROI é a do domain gap do DQN v2
(`experiments.evaluate_lane_features`).

### Segundo fine-tuning: duas classes (veículo e emergência), câmeras de 60 m

Status: concluído em 2026-10-01. Substitui o detector `run-002` no pipeline v2.

**Captura.** 8 execuções (seeds 301–308, alternando os cenários calibrado e
original), 250 steps cada, com as 3 câmeras operacionais nas poses novas e 6
câmeras de dataset em poses variantes (`south_ds_left/right`,
`east_ds_near/far`, `west_ds_near/far`). Viaturas entram a cada
`--emergency-interval` para haver exemplos da classe `emergency`. As caixas vêm
das máscaras de instância; a classe vem do tipo SUMO do veículo
(`vision/dataset_classes.py`: `0 vehicle`, `1 emergency`).

**Dataset.** A partição é por execução inteira (`runs.json`): treino 301–303 e
306–308, validação 305 (calibrado), teste 304 (original), para que frames
vizinhos não vazem entre partições. A versão completa
(`unity-cam60-2cls`) tem 18.000 imagens e 148.907 caixas (6.297 de emergência).
O treino usou `--frame-stride 3` (`unity-cam60-2cls-s3`): 4.536 imagens de
treino, 756 de validação e 756 de teste, com 49.869 caixas (2.104 de emergência).

**Treino.** A partir do `run-002`, 15 épocas, `imgsz=960`, `batch=4`, MPS
(Apple M5), 13,2 h. Checkpoint:
`runs/results/models/yolov8n-unity-cam60-2cls-960/weights/best.pt`. Na
validação: `mAP50 = 0,995`, `mAP50-95 = 0,983` (veículo 0,981; emergência 0,985).

**Teste por classe e distância** (`experiments.evaluate_yolo_classes`, run-304,
confiança 0,15 como em operação, IoU 0,5, casamento sem olhar a classe). A
distância de cada rótulo é o centro da base da caixa projetado pela homografia
da ROI de faixa, a mesma regra da visão em operação; por isso só as câmeras
operacionais têm faixas de distância.

| Classe | Faixa da ROI | Rótulos | Recall | Confundido com a outra classe |
|---|---|---|---|---|
| veículo | 0–20 m | 756 | 100% | 0 |
| veículo | 20–40 m | 382 | 99,5% | 0 |
| veículo | 40–60 m | 287 | 97,2% | 0 |
| veículo | todas as 9 câmeras | 5.924 | 99,3% | 0,1% |
| emergência | 0–20 m | 44 | 100% | 0 |
| emergência | 20–40 m | 36 | 100% | 0 |
| emergência | 40–60 m | 7 | 100% | 0 |
| emergência | todas as 9 câmeras | 317 | 99,7% | 1 caso (fora da ROI) |

Há 90 falsos positivos (todos `vehicle`) em 756 imagens, espalhados entre as
câmeras. Limitações: treino e teste vêm da mesma Unity, e a faixa de 40–60 m
tem só 7 viaturas no teste, o que é pouca base estatística. O teste que importa
é a malha fechada (YOLO + ByteTrack a 1 fps), feito nas avaliações visuais.

**Uso.** Os scripts v2 (`add_vision_arguments` em
`experiments/visual_observer.py`) passam a usar este modelo com
`--classes 0,1` e `--image-size 960` por padrão. As duas classes entram nas
contagens por faixa (uma viatura também ocupa a via); `--classes 0` com este
modelo apagaria as viaturas do estado. Os scripts legados da v1
(`run_visual_controller`, `train_visual_dqn`) mantêm seus padrões.

```bash
../.venv/bin/python -m experiments.evaluate_yolo_classes   # sem SUMO/Unity, ~10 min
```

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
- criação de `unity/TraffIQ-TCC/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs`;
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
- projeto Unity criado em `unity/TraffIQ-TCC`.
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
- atualização de `unity/TraffIQ-TCC/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs` para aplicar estado na main thread;
- criação de `unity/TraffIQ-TCC/Assets/Scripts/TccTrafficVision/VehicleManager.cs`;
- criação de `unity/TraffIQ-TCC/Assets/Scripts/TccTrafficVision/TrafficLightVisualController.cs`;
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
  `unity/TraffIQ-TCC`;
- cópia da rede SP para
  `unity/TraffIQ-TCC/Assets/Sumo/SP/Cruzamento.net.xml`;
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
  --calibration-dir ../unity/TraffIQ-TCC/Assets/Calibration \
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

Concluído: estado v1 (contagens) e, depois, estado v2 por faixa — ver a seção
**DQN v2** no início deste arquivo.

Escopo previsto:

- executar YOLO, filtro pela ROI externa, ByteTrack e ROIs de faixa nos frames
  Unity;
- converter as contagens por faixa em um vetor de estado visual;
- manter E2 apenas como ground truth de avaliação;
- treinar novamente o DQN para o novo vetor visual.

### Marco 9 em diante

Controlador semafórico e experimentos comparativos concluídos com o DQN v2
(seção **DQN v2**). Teste visual no cenário `original` com o checkpoint atual
em 2026-10-12 (seção **Avaliação visual do cenário original**).
