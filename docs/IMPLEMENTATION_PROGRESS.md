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
  emergência por aviso V2I: concluídos em 2026-09-30 — seção **Ambiente com
  ROIs de 60 m e preempção** abaixo.
- YOLO de duas classes, detecção visual das viaturas, correção do filtro da
  ROI e avaliações visuais do ambiente de 60 m: concluídos em 2026-10-04.
- Pedestres no SUMO (rede, fase exclusiva a cada dois ciclos, estado v3,
  métricas): em andamento desde 2026-10-05 — seção **Pedestres** abaixo.
  Unity e câmeras com pedestres ficam para a etapa seguinte.
- Demanda calibrada sem motos: 2026-10-07 — seção **Demanda calibrada sem
  motos** abaixo. Todos os resultados anteriores do cenário `calibrated`
  (inclusive os de pedestres) usam a demanda antiga e viram registro
  histórico; v2 e v3 foram retreinados (checkpoints `*-sem-motos-best.pt`).
  As avaliações visuais (Unity) ainda são da demanda antiga.

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
antiga ficou como cenário `calibrated_motos` (`Cruzamento.calibrated-motos.*`),
só como registro histórico.

Checagem (oráculo, seeds 201–203, 300 s + 1800 s; v2 = checkpoint antigo,
treinado com a demanda anterior, só indicativo). Arquivos:
`results/evaluation/versoes-{calibrated,calibrated_ped}-oracle-sem-motos-checagem.json`.

| Cenário | Versão | Espera veíc. | Chegadas | Fila de inserção | Ped. mediana | Ped. p90 |
|---|---|---:|---:|---:|---:|---:|
| calibrado | ciclo fixo | 13,0 s | 918 | 0 | — | — |
| calibrado | v2 (antigo) | 4,3 s | 918 | 0 | — | — |
| calibrado | max-pressure | 4,7 s | 917 | 0 | — | — |
| calibrado + pedestres | ciclo fixo | 24,5 s | 906 | 0 | 48 s | 163 s |
| calibrado + pedestres | v2 (antigo) | 21,1 s | 907 | 0 | 13 s | 69 s |
| calibrado + pedestres | max-pressure | 34,2 s | 828 | 77 | 7 s | 53 s |

Sem motos, nenhuma versão satura sem pedestres; o ciclo fixo fica na mesma
ordem dos atrasos medidos pelo drone. A fase exclusiva de pedestres ainda
custa ~10 s de espera aos veículos, mas não cria mais fila de inserção (exceto
no max-pressure).

### Retreino e avaliação com a demanda sem motos (oráculo, seeds 201–203, 300 s + 1800 s)

Checkpoints novos, padrão dos scripts: v2 = `dqn-v2-sem-motos-best.pt`
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

**Preempção (V2I, viaturas a cada ~5 min, 18 viaturas)**, perda total
(espera de entrada + perda na rede), sem → com preempção:

| Cenário | Ciclo fixo | v2 | v3 | max-pressure |
|---|---:|---:|---:|---:|
| calibrado | 16,6 → **1,4 s** | 8,0 → **1,5 s** | — | 7,9 → 1,5 s |
| original | 31,3 → 13,6 s | 12,2 → 3,1 s | — | 13,0 → 3,3 s |
| calibrado + pedestres | 32,9 → 5,8 s | 26,7 → **5,2 s** | 23,2 → 7,7 s | 90,1 → 19,9 s |
| original + pedestres | 118,5 → 69,9 s | 96,8 → 74,9 s | 97,6 → 81,4 s | 106,4 → 101,1 s |

- Calibrado sem pedestres: 100% das viaturas cruzam sem parar, espera de
  entrada ~1 s.
- **Calibrado com pedestres: o problema da investigação anterior sumiu.** A
  espera de entrada fica em 3–4 s, a perda total cai para 5–8 s (máx. 39 s,
  quem chega durante a fase de pedestres) e os pedestres praticamente não
  pioram com a preempção (v2: mediana 15 → 13 s, p90 72 → 74 s; v3: 12 → 16 s,
  74 → 76 s).
- No `original_ped`, ainda saturado, a viatura continua presa na fila de
  inserção (~60–75 s) e os pedestres pioram com a preempção, como antes.

## Pedestres (fase exclusiva a cada dois ciclos)

Status: rede, fase de pedestres, estado v3 e métricas implementados em
2026-10-05 (branch `feat/pedestres`); só SUMO. Decisões do usuário: fase
exclusiva (todos os veículos no vermelho, todas as faixas verdes) a cada dois
ciclos; verde que cubra a travessia em "L" a 1,2 m/s; nova versão de estado.

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
  recompensa e oráculo funcionam nas duas redes.
- Demanda sintética (o drone não mediu pedestres): 300 pedestres/h, chegadas
  Poisson divididas igualmente entre os 30 pares de calçadas.
- **Deadlock corrigido:** as duas faixas de conversão Sul → Leste se fundem
  numa só depois da faixa de pedestre Leste. O netconvert criou um ponto de
  espera interno por faixa antes da travessia, e os dois cediam passagem um ao
  outro: 6–12 teleportes por episódio de 1800 s. Com `contPos="0"` nessas
  conexões a espera fica na linha de retenção, como na rede sem pedestres:
  0 teleportes. Geometria, links e travessias não mudam.

### Fase de pedestres

| Esquina | Travessia + esquina + travessia | Verde a 1,2 m/s |
|---|---|---:|
| Nordeste (Leste + Norte) | 13,0 + 20,3 + 12,0 = 45,3 m | 38 s |
| Sudeste (Leste + Sul) | 13,0 + 9,9 + 12,8 = 35,7 m | 30 s |
| **Sudoeste (Sul + Oeste)** | **12,8 + 24,0 + 11,2 = 48,05 m** | **41 s** |
| Noroeste (Oeste + Norte) | 11,2 + 12,0 + 12,0 = 35,2 m | 30 s |

- Sequência: L/O → Sul → L/O → Sul → all-red (1 s) → verde de pedestres
  (41 s, o maior "L") → liberação em vermelho total (3 s) → L/O.
- Obrigatória como o amarelo: a política não a encerra nem a pula. A
  preempção não a interrompe; uma viatura que chega quando ela ainda não
  começou passa à frente, e a fase vem na próxima oportunidade.
- Estado v3 (44 entradas): v2 + one-hot das 7 fases + verdes até a fase de
  pedestres. v1/v2 continuam rodando na rede com pedestres, vendo as fases de
  pedestre como all-red.
- Métricas novas: espera média, p95 e máxima dos pedestres (steps parados até
  sair da rede), pedestres atendidos e na rede ao fim.

### Primeiras medições (ciclo fixo, só SUMO, seeds 201–203, 300 s + 1800 s)

| Cenário calibrado | Espera dos veículos | Chegadas | Fila de inserção final | Espera média dos pedestres | Espera máx. dos pedestres |
|---|---:|---:|---:|---:|---:|
| sem pedestres | 16,1 s | 1503 | 97 | — | — |
| com pedestres | 25,4–26,3 s | 1281–1364 | 265–309 | 61–66 s | ~180 s |

A fase de pedestres tira ~45 s de cada dois ciclos dos veículos; no cenário
calibrado, com o Leste saturado, a fila de inserção cresce. A espera máxima de
~180 s corresponde a quase dois ciclos inteiros: é o custo da regra "a cada
dois ciclos". A v2 (treinada sem pedestres) foi pior que o ciclo fixo num
teste de 900 s (31 × 25 s de espera), o que motiva o estado v3.

### Versões com pedestres (percepção oráculo, seeds 201–203, 300 s + 1800 s)

v3 = `dqn-v3-ped-pretrain-best.pt` (pré-treino com `calibrated_ped` e
`original_ped`, Double DQN, 40 episódios; melhor no episódio 39, escore
−0,451 contra −0,472 do ciclo fixo e −0,541 do max-pressure na validação, e
ainda subindo). v2 = `dqn-v2-roi60-mix-pretrain-best.pt`, treinada sem
pedestres. 0 teleportes em todas as rodadas. Arquivos:
`results/evaluation/versoes-{calibrated,original}_ped-oracle.json`.

**Calibrado com pedestres**

| Versão | Espera veículos | Chegadas | Fila de inserção | Trocas | Espera média ped. | p95 ped. | Máx. ped. |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ciclo fixo | 25,7 s | 1326 | 290 | 0 | 64,0 s | 170 s | 179 s |
| v1 | 55,6 s | 964 | 629 | 72 | 16,2 s | 57 s | 60 s |
| v2 | 26,0 s | 1233 | 367 | 48 | 32,8 s | 96 s | 110 s |
| v3 | 26,4 s | 1249 | 360 | 30 | 45,3 s | 134 s | 146 s |
| max-pressure | 55,2 s | 965 | 628 | 72 | 16,7 s | 57 s | 60 s |

**Original com pedestres**

| Versão | Espera veículos | Chegadas | Fila de inserção | Trocas | Espera média ped. | p95 ped. | Máx. ped. |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ciclo fixo | 32,3 s | 1260 | 224 | 0 | 64,4 s | 172 s | 180 s |
| v1 | 49,3 s | 1043 | 417 | 69 | 16,8 s | 56 s | 63 s |
| v2 | 28,6 s | 1301 | 188 | 56 | 27,1 s | 82 s | 93 s |
| v3 | 27,0 s | 1289 | 193 | 26 | 48,7 s | 133 s | 149 s |
| max-pressure | 44,1 s | 1123 | 357 | 68 | 19,4 s | 60 s | 66 s |

Leitura:

- **A regra acopla os pedestres à duração dos verdes.** Como a fase de
  pedestres vem a cada dois ciclos e dura 45 s, quem troca rápido (v1 e
  max-pressure, verdes no mínimo) chama a fase de pedestres muitas vezes:
  pedestres esperam ~16 s, mas os veículos perdem tanto tempo que a espera
  dobra (~55 s) e a fila de inserção passa de 600. Quem segura o verde (ciclo
  fixo 40/40, v2, v3) faz o contrário: veículos ~26 s e pedestres 33–64 s.
- **O v3 aprendeu a segurar o verde** (26–30 trocas, contra 48–56 da v2): com
  a recompensa só dos veículos, espaçar a fase de pedestres é vantajoso. Isso
  aumenta a espera dos pedestres (45–49 s, máximo ~150 s) sem ganho claro para
  os veículos no calibrado (26,4 × 25,7 s do ciclo fixo); no original o v3 é o
  melhor para os veículos (27,0 × 32,3 s).
- **A v2, mesmo sem conhecer os pedestres, fica perto do v3 para os veículos e
  bem melhor para os pedestres**, porque troca mais.
- **Todos ficam saturados:** a fila de inserção final de 188–629 mostra que,
  com 45 s de fase exclusiva a cada dois ciclos, a capacidade do cruzamento
  fica abaixo da demanda nos dois cenários.

### v3 com a espera dos pedestres na recompensa

Decisão do usuário (2026-10-05): manter a regra e incluir os pedestres na
recompensa de treino. Nos cenários com pedestres a recompensa passa a ser
`(1 − w)·veículos − w·min(1, Σ espera atual dos pedestres parados / ref.)`,
com `w = 0,3` e ref. = 1200 s (p90 dessa soma com o ciclo fixo; com 600 s o
termo saturava em 32% do tempo). Bloco `pedestrians:` do `sp.yaml`. A política
continua sem ver o TraCI.

Pré-treino igual ao anterior (`dqn-v3-pedrw-pretrain-best.pt`, 40 episódios,
melhor no 39: escore −0,342 contra −0,407 do ciclo fixo e −0,386 do
max-pressure com a recompensa nova). Avaliação no mesmo protocolo
(`versoes-*_ped-oracle-v3pedrw.json`):

| Cenário | Versão | Espera veículos | Chegadas | Fila de inserção | Trocas | Espera média ped. | Máx. ped. |
|---|---|---:|---:|---:|---:|---:|---:|
| calibrado | ciclo fixo | 25,7 s | 1326 | 290 | 0 | 64,0 s | 179 s |
| calibrado | v2 | 26,0 s | 1233 | 367 | 48 | 32,8 s | 110 s |
| calibrado | v3 (só veículos) | 26,4 s | 1249 | 360 | 30 | 45,3 s | 146 s |
| calibrado | **v3 (veículos + pedestres)** | 27,3 s | 1230 | 381 | 34 | 39,9 s | 129 s |
| original | ciclo fixo | 32,3 s | 1260 | 224 | 0 | 64,4 s | 180 s |
| original | v2 | 28,6 s | 1301 | 188 | 56 | 27,1 s | 93 s |
| original | v3 (só veículos) | 27,0 s | 1289 | 193 | 26 | 48,7 s | 149 s |
| original | **v3 (veículos + pedestres)** | **25,6 s** | **1315** | **159** | 34 | 38,0 s | 122 s |

- O termo de pedestres funcionou na direção esperada: o v3 troca mais (34 ×
  26–30) e reduz a espera dos pedestres em 5–11 s, com espera máxima ~20 s
  menor.
- No **original**, o v3 com pedestres é o melhor para os veículos de todas as
  versões (25,6 s, mais chegadas, menor fila) e domina o v3 anterior nos dois
  critérios. A v2 ainda deixa os pedestres esperando menos (27 × 38 s).
- No **calibrado**, a v2 é melhor que os dois v3 nos dois critérios (26,0 s e
  32,8 s). O v3 não supera o ciclo fixo para os veículos neste cenário.
- Nenhuma versão é a melhor nos dois critérios ao mesmo tempo: o custo de 45 s
  exclusivos a cada dois ciclos domina o resultado, e todas terminam com fila
  de inserção. O pré-treino ainda melhorava no fim (40 episódios).

### Peso dos pedestres e treino mais longo (100 episódios)

Pré-treinos do v3 com 100 episódios (seeds 51–150, disjuntas das de ajuste
fino, validação e teste) e peso dos pedestres na recompensa `w` = 0,2, 0,3 e
0,5 (`--pedestrian-reward-weight`). Mesmo protocolo de avaliação (oráculo,
seeds 201–203). Arquivos: `results/models/dqn-v3-ped-w0X-e100-best.pt`,
`results/evaluation/versoes-*_ped-oracle-v3-w0X-e100.json`.

| Versão | Calibrado: espera veículos | Chegadas | Fila | Espera ped. (p95) | Original: espera veículos | Chegadas | Fila | Espera ped. (p95) |
|---|---:|---:|---:|---|---:|---:|---:|---|
| Ciclo fixo | 25,7 s | 1326 | 290 | 64,0 s (170) | 32,3 s | 1260 | 224 | 64,4 s (172) |
| v2 (sem pedestres no treino) | 26,0 s | 1233 | 367 | 32,8 s (96) | 28,6 s | 1301 | 188 | 27,1 s (82) |
| v3 só veículos, 40 ep. | 26,4 s | 1249 | 360 | 45,3 s (134) | 27,0 s | 1289 | 193 | 48,7 s (133) |
| v3 w = 0,3, 40 ep. | 27,3 s | 1230 | 381 | 39,9 s (114) | 25,6 s | 1315 | 159 | 38,0 s (110) |
| v3 w = 0,2, 100 ep. | 27,2 s | 1177 | 429 | 30,5 s (87) | 26,8 s | 1286 | 191 | 31,8 s (88) |
| **v3 w = 0,3, 100 ep.** | **26,7 s** | 1175 | 429 | **30,2 s (88)** | **26,9 s** | 1290 | 185 | **29,8 s (85)** |
| v3 w = 0,5, 100 ep. | 33,4 s | 1006 | 608 | 23,5 s (68) | 31,8 s | 1202 | 284 | 25,3 s (72) |
| v1 / max-pressure | ~55 s | ~965 | ~628 | ~16 s (57) | 44–49 s | 1043–1123 | 357–417 | 17–19 s (56–60) |

Espera por seed (veículos / pedestres), v3 w = 0,3, 100 ep.: calibrado
26,1/29,1, 27,3/29,4, 26,7/32,2 s; original 26,9/27,2, 26,9/28,5, 27,0/33,5 s.

- **Treinar mais ajudou:** com w = 0,3, 100 episódios reduziram a espera dos
  pedestres de ~39 para ~30 s nos dois cenários, com espera máxima ~100 s
  (era ~125 s), e melhoraram os veículos no calibrado (27,3 → 26,7 s).
- **O peso controla o equilíbrio:** w = 0,5 leva os pedestres a ~24 s, mas os
  veículos pioram para 32–33 s, quase como o ciclo fixo e com fila de
  inserção bem maior; w = 0,2 e 0,3 ficam praticamente iguais.
- **v3 (w = 0,3, 100 ep.) × v2:** nenhum domina o outro. No calibrado, a v2
  escoa mais veículos (1233 × 1175; espera 26,0 × 26,7 s) e o v3 faz os
  pedestres esperarem menos (30,2 × 32,8 s). No original, o v3 é melhor para os
  veículos (26,9 × 28,6 s) e a v2 para os pedestres (27,1 × 29,8 s).
- **Referência do ambiente com pedestres:** v3 com w = 0,3 e 100 episódios
  (`dqn-v3-ped-w03-e100-best.pt`), padrão de `compare_versions --versions ...,v3`.
  É o único que, nos dois cenários, fica a ≤ 1 s do melhor para os veículos
  e a ≤ 3 s do melhor para os pedestres sem sacrificar o outro lado.
- O estado v3 sozinho não trouxe ganho claro sobre a v2; o que mais pesa é a
  recompensa (o termo de pedestres) e a regra da fase exclusiva, que mantém
  todos os controladores com fila de inserção.

### Preempção com pedestres (V2I, percepção oráculo)

`evaluate_preemption` nos cenários com pedestres, mesma agenda de 30 viaturas
(10 por seed, seeds 201–203), v3 = `dqn-v3-ped-w03-e100-best.pt`. Arquivos:
`results/evaluation/preempcao-{calibrated,original}_ped-oracle.json`.

| Cenário | Versão | Modo | Perda média viatura | Perda máx. | Sem parar | Espera veículos | Espera ped. | Máx. ped. |
|---|---|---|---:|---:|---:|---:|---:|---:|
| calibrado | ciclo fixo | sem | 37,6 s | 96 s | 46% | 25,7 s | 64,0 s | 179 s |
| calibrado | ciclo fixo | V2I | 5,0 s | 30 s | 80% | 23,2 s | 99,5 s | 339 s |
| calibrado | v2 | sem | 23,6 s | 106 s | 27% | 26,4 s | 33,8 s | 112 s |
| calibrado | v2 | V2I | 6,7 s | 49 s | 77% | 22,5 s | 82,0 s | 367 s |
| calibrado | v3 | sem | 28,9 s | 97 s | 35% | 26,5 s | 30,9 s | 100 s |
| calibrado | v3 | V2I | 5,2 s | 36 s | 80% | 21,5 s | 71,2 s | 320 s |
| calibrado | max-pressure | sem | 62,1 s | 149 s | 5% | 55,4 s | 16,9 s | 60 s |
| calibrado | max-pressure | V2I | 7,4 s | 94 s | 83% | 25,1 s | 71,8 s | 324 s |
| original | ciclo fixo | sem | 30,2 s | 89 s | 43% | 32,0 s | 64,0 s | 179 s |
| original | ciclo fixo | V2I | 13,4 s | 102 s | 70% | 30,4 s | 110,3 s | 432 s |
| original | v2 | sem | 34,7 s | 105 s | 11% | 29,6 s | 28,0 s | 96 s |
| original | v2 | V2I | 18,8 s | 182 s | 63% | 27,1 s | 93,3 s | 431 s |
| original | v3 | sem | 35,7 s | 87 s | 10% | 27,2 s | 29,3 s | 93 s |
| original | v3 | V2I | 11,4 s | 126 s | 67% | 26,7 s | 72,1 s | 357 s |
| original | max-pressure | sem | 42,6 s | 91 s | 14% | 44,8 s | 19,0 s | 70 s |
| original | max-pressure | V2I | 13,3 s | 152 s | 70% | 35,8 s | 73,7 s | 403 s |

- **Viaturas:** a preempção continua reduzindo bastante a perda (−65 a −88%),
  mas fica longe do ~1 s do ambiente sem pedestres: uma viatura que chega
  durante a fase de pedestres espera até o fim dela (45 s), e a perda máxima
  vai a 30–180 s. 20–37% das viaturas ainda param.
- **Problema encontrado — pedestres:** com preempção, a espera média dos
  pedestres sobe de 31–64 s para 71–110 s e a máxima para **320–432 s**. Pela
  regra atual, uma viatura adia a fase de pedestres que ainda não começou, e a
  fase só volta depois do próximo verde Sul completo. Com uma viatura a cada
  ~3 min, a fase de pedestres é adiada repetidamente e alguns pedestres
  esperam mais de 7 minutos. A regra precisa ser revista antes de valer como
  resultado.
- A espera dos veículos cai com a preempção no calibrado (21–25 s) justamente
  porque as fases de pedestres adiadas devolvem tempo aos veículos.

### Investigação da preempção com pedestres (demanda antiga, 2026-10-07)

Registro histórico: tudo nesta seção usa a demanda com motos
(`calibrated_motos`), que saturava o Leste.

- **Regra de adiamento corrigida** (`fix:` 7483050): a fase de pedestres
  adiada por uma viatura vem no all-red seguinte, logo depois do verde dela,
  e o ciclo retoma pelo verde que viria. Quase não mudou os números (v3
  calibrado: máx. de pedestres 320 → 312 s), então não era a causa principal.
- **Causa real:** com a fase exclusiva, o Leste (já com v/c 1,0) ficava com
  fila de inserção de 190–430 veículos. A viatura do Leste entrava no fim dessa
  fila, fora da rede, e o aviso V2I segurava o verde L/O por até ~220 s,
  travando o Sul e a fase de pedestres.
- **Métrica corrigida:** a perda da viatura só contava depois da entrada na
  rede (uma viatura com ~220 s de espera aparecia com 2,3 s). Agora o resumo
  traz `mean_insertion_delay_s` e `mean_total_loss_at_crossing_s` (inserção +
  perda na rede), e os pedestres ganharam mediana e p90.
- **Viaturas a cada 5 min** (`interval_s` 180 → 300; resultados de 3 min com
  sufixo `-viaturas-3min`). v3 calibrado com pedestres, V2I: perda na rede
  3,8 s, mas espera de entrada de 71,7 s e perda total de 75,5 s (sem
  preempção, 109,6 s). Pedestres: mediana 18 → 38 s, p90 83 → 216 s. Sem
  pedestres, a v2 fica com perda total de 4,5 s (calibrado) e 3,2 s (original).
- **Fase a cada 3 ciclos** (ciclo fixo, v2 e max-pressure; arquivos
  `versoes-*_ped-oracle-ped-cada{2,3}.json`): no calibrado, a v2 vai de
  26,0 para 21,4 s de espera e de 367 para 263 veículos na fila de inserção,
  mas a mediana dos pedestres sobe de 14 para 32 s. Não resolvia a saturação.
- Ao olhar a fila no `sumo-gui`, o usuário notou que o cruzamento real não
  tinha tanto carro, o que levou à recalibração sem motos (seção acima).

## Ambiente com ROIs de 60 m e preempção para emergências

Status: câmeras, ROIs e preempção V2I concluídos (branch `feat/cameras-60m`,
2026-09-30). **Muda o ambiente:** os resultados da seção DQN v2 abaixo foram
obtidos com as ROIs de ~25 m e não se comparam com os desta seção.

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
- O YOLO atual foi treinado com os ângulos antigos e precisa ser retreinado.

### Detecção visual de viaturas (segunda fonte de preempção)

Status: implementada e avaliada em malha fechada em 2026-10-02 (resultados no
fim desta seção).

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

#### Resultado em malha fechada (percepção visual)

Mesmo ambiente para os quatro modos: cenário calibrado, política v2
(`dqn-v2-roi60-mix-pretrain-best.pt`, pré-treinado nas ROIs de 60 m com os dois cenários),
percepção visual (YOLO de duas classes + ByteTrack,
1 fps), seeds 201–203, aquecimento 300 s + 1800 s, a mesma agenda de 30
viaturas. Muda só a fonte do pedido. `missing_frames = 0`. Arquivo:
`results/evaluation/preempcao-calibrated-visual.json`.

Rodado de novo em 2026-10-03, depois da correção do filtro da ROI de
aproximação (seção "Correção" abaixo).

| Modo | Perda média da viatura | Perda máx. | Sem parar | Espera do tráfego | Chegadas | Fila de inserção |
|---|---|---|---|---|---|---|
| sem preempção | 13,2 s | 26,2 s | 37% | 9,4 s | 1608 | 8 |
| V2I | 1,4 s | 5,6 s | 100% | 10,5 s | 1606 | 11 |
| visão | 4,2 s | 19,5 s | 80% | 9,9 s | 1605 | 11 |
| V2I + visão | 1,2 s | 4,0 s | 100% | 11,3 s | 1609 | 6 |

Perda média da viatura por seed (201/202/203): sem 12,0 / 13,0 / 14,6 s;
V2I 1,8 / 1,2 / 1,2 s; visão 6,2 / 2,5 / 3,7 s; ambos 1,3 / 1,0 / 1,3 s.

- **Detecção visual:** 30/30 viaturas detectadas e 0 alarmes falsos em 30
  eventos, em todos os modos.
- **Visão sozinha** reduz a perda média em 68% (13,2 → 4,2 s), e 80% das
  viaturas cruzam sem parar (37% sem preempção). Não zera o atraso: a
  antecedência média até a linha é de 6,7 s, contra ~30 s do V2I, e uma viatura
  que chega no vermelho ainda espera amarelo + all-red (4 s) e a fila à frente.
  Custa +0,5 s na espera média do tráfego.
- **V2I** é a melhor fonte isolada (1,4 s, 100% sem parar); custa +1,1 s.
- **V2I + visão** é o melhor modo (1,2 s, perda máxima 4,0 s, 100% sem parar),
  igual ao V2I dentro da variação entre seeds. A visão serve de redundância
  quando o aviso V2I falha.
- A antecedência da visão depende do modo: sem preempção (16,1 s) as viaturas
  ficam paradas na fila dentro da ROI e são vistas por mais tempo.

#### Antes da correção do filtro (2026-10-02, registro)

Arquivo: `results/evaluation/preempcao-calibrated-visual-filtro-centro.json`.

| Modo | Perda média da viatura | Perda máx. | Sem parar | Espera do tráfego | Chegadas |
|---|---|---|---|---|---|
| sem preempção | 15,8 s | 52,6 s | 37% | 10,3 s | 1580 |
| V2I | 1,2 s | 3,8 s | 97% | 11,7 s | 1592 |
| visão | 7,2 s | 25,8 s | 53% | 10,7 s | 1572 |
| V2I + visão | 1,4 s | 6,9 s | 100% | 11,7 s | 1592 |

- **Detecção visual:** 30/30 viaturas detectadas e 0 alarmes falsos em 30
  eventos, em todos os modos.
- **Visão sozinha** reduz a perda média em ~55% (15,8 → 7,2 s), mas não a zera:
  o pedido sai a ~40 m da linha, e a antecedência média até a linha foi 6,9 s,
  contra ~30 s do V2I. Quando a viatura chega no vermelho, amarelo + all-red
  (4 s) e a fila à frente ainda a atrasam. Custa pouco ao tráfego (+0,4 s na
  espera média).
- **V2I** continua sendo a melhor fonte (1,2 s); custa +1,4 s na espera média.
- **V2I + visão** fica igual ao V2I (diferenças dentro da variação entre
  seeds) e foi o único modo em que 100% das viaturas cruzaram sem parar. A
  visão serve de redundância quando o aviso V2I falha.
- A antecedência da visão depende do modo. Sem preempção (14,2 s)
  as viaturas ficam paradas na fila dentro da ROI e são vistas por mais tempo.
  A fila de inserção no fim do episódio varia muito entre seeds (0–87) e não
  serve para comparar os modos.

### Versões no ambiente novo (percepção oráculo, seeds 201–203, 1800 s)

A v2 foi pré-treinada de novo para as ROIs de 60 m
(`dqn-v2-roi60-pretrain-best.pt`: episódio 34, escore −0,058 contra −0,314 do
ciclo fixo e −0,300 do max-pressure).

| Versão | Calibrado: espera | Chegadas | Fila de inserção | Original: espera | Chegadas |
|---|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 16,1 s | 1503 | 97 | 14,9 s | 1431 |
| v1 (heurística) | 10,3 s | 1486 | 117 | 4,7 s | 1473 |
| v1.1 (DQN estado v1) | 12,9 s | 1312 | 289 | 4,6 s | 1474 |
| v2 (DQN estado v2) | 10,1 s | 1602 | 0 | 8,3 s | 1469 |
| max-pressure | 10,8 s | 1492 | 108 | 4,6 s | 1474 |

- Com ROIs maiores, a v1 e o max-pressure passam a enxergar filas longas e
  melhoram no calibrado; a v2 continua a única que zera a fila de inserção.
- **No cenário original, essa v2 piorou** (8,3 s, contra 4,6 s das demais):
  dava 64% do verde ao Leste mesmo com demanda equilibrada, porque treinou só
  no cenário calibrado.

**v2 pré-treinada com os dois cenários** (`--scenarios calibrated,original`,
episódios alternados, validação nos dois; `dqn-v2-roi60-mix-pretrain-best.pt`,
episódio 34). É a v2 de referência do ambiente novo:

| Versão | Calibrado: espera | Chegadas | Fila de inserção | Original: espera | Chegadas |
|---|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 16,1 s | 1503 | 97 | 14,9 s | 1431 |
| v1 (heurística) | 10,3 s | 1486 | 117 | 4,7 s | 1473 |
| v2 treinada só no calibrado | 10,1 s | 1602 | 0 | 8,3 s | 1469 |
| **v2 treinada nos dois cenários** | **8,6 s** | **1603** | **4** | **4,4 s** | **1474** |
| max-pressure | 10,8 s | 1492 | 108 | 4,6 s | 1474 |

Treinar com os dois cenários melhorou a v2 nos dois: no calibrado, reduz a
espera em 1,5 s mantendo as chegadas; no original, passa de pior a melhor.

### Versões no ambiente novo — percepção visual (Unity, cenário calibrado)

Rodado em 2026-10-03, depois da correção do filtro da ROI de aproximação
(próxima seção): `compare_versions --scenario calibrated --perception visual`,
seeds 201–203, 300 s + 1800 s, YOLO de duas classes, v2 =
`dqn-v2-roi60-mix-pretrain-best.pt`, sem viaturas. `missing_frames = 0`.
Arquivo: `results/evaluation/versoes-calibrated-visual.json`.

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O | Trocas | Oráculo: espera / chegadas / fila |
|---|---:|---:|---:|---:|---:|---:|---|
| Linha de base (ciclo fixo) | 16,1 s | 36,2 s | 1503 | 97 | 50% | 0 | 16,1 s / 1503 / 97 |
| v1 (heurística) | 10,3 s | 33,9 s | 1488 | 112 | 59% | 112 | 10,3 s / 1486 / 117 |
| v1.1 (DQN estado v1) | 12,9 s | 38,0 s | 1312 | 289 | 50% | 129 | 12,9 s / 1312 / 289 |
| **v2 (DQN estado v2)** | **9,1 s** | **30,3 s** | **1596** | **11** | 61% | 80 | 8,6 s / 1603 / 4 |
| max-pressure | 10,6 s | 33,7 s | 1542 | 59 | 61% | 103 | 10,8 s / 1492 / 108 |

Espera por seed (201/202/203): v2 9,4 / 9,1 / 9,0 s; max-pressure 10,7 / 10,6 /
10,4 s; v1 10,6 / 10,0 / 10,3 s.

- **Ciclo fixo × v2 com câmera:** espera −43% (16,1 → 9,1 s), viagem −16%,
  +93 chegadas, fila de inserção 97 → 11.
- **v2 × max-pressure e v1:** a v2 vence nas três seeds, com 1,5 s a menos de
  espera que o max-pressure e +54 chegadas.
- **Custo da percepção na v2:** caiu de +2,0 s para **+0,5 s** de espera em
  relação ao oráculo (−7 chegadas, +7 na fila). A v1 com câmera agora iguala a
  v1 com oráculo.
- **Verdes da v2:** Leste/Oeste com média de 23,6 s (2% terminam no mínimo, 5%
  chegam aos 40 s); Sul com média de 15,1 s (35% no mínimo).

**Domain gap** (log da v2, 5.433 steps;
`results/evaluation/domain-gap-roi60-calibrated-v2.json`):

| Faixa | Contagem (MAE / viés) | Veículos perdidos | Velocidade (viés) | Espera (viés) |
|---|---|---:|---:|---:|
| east/lane_0 | 0,26 / +0,18 | 7% | −1,44 m/s | +7,3 s |
| east/lane_1 | 0,30 / −0,18 | 20% | −0,87 m/s | +0,4 s |
| south/lane_0–3 | 0,08–0,23 / +0,06 a +0,19 | 1% | −0,3 a −1,0 m/s | +1,4 a +5,2 s |
| west/lane_0 | 0,03 / +0,03 | 0,2% | −0,16 m/s | +0,4 s |

- A ação do DQN com features visuais coincide com a do oráculo em **84,8%**
  das 640 decisões (era 71,1% antes da correção).
- O que sobra no Leste é a oclusão da faixa 1 pela faixa 0 (ângulo lateral da
  câmera). A velocidade continua subestimada e a espera superestimada, sem
  impedir a v2 de ficar a 0,5 s do oráculo.
- Com esse resultado, o ajuste fino visual não é necessário para a conclusão
  principal.

#### Antes da correção do filtro (2026-10-02, registro)


Rodado em 2026-10-02: `compare_versions --scenario calibrated --perception visual`,
seeds 201–203, 300 s + 1800 s, YOLO de duas classes (`--classes 0,1`, 960 px),
v2 = `dqn-v2-roi60-mix-pretrain-best.pt`, sem viaturas de emergência.
`missing_frames = 0`. Arquivo: `results/evaluation/versoes-calibrated-visual-filtro-centro.json`;
logs por step em `results/logs/versoes-calibrated-visual-<versão>-filtro-centro.jsonl`.

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O | Trocas | Oráculo: espera / chegadas / fila |
|---|---:|---:|---:|---:|---:|---:|---|
| Linha de base (ciclo fixo) | 16,1 s | 36,2 s | 1503 | 97 | 50% | 0 | 16,1 s / 1503 / 97 |
| v1 (heurística) | 11,1 s | 35,2 s | 1423 | 179 | 55% | 118 | 10,3 s / 1486 / 117 |
| v1.1 (DQN estado v1) | 12,9 s | 38,0 s | 1311 | 290 | 50% | 129 | 12,9 s / 1312 / 289 |
| **v2 (DQN estado v2)** | **10,6 s** | **32,8 s** | **1556** | **45** | 59% | 88 | 8,6 s / 1603 / 4 |
| max-pressure | 10,5 s | 33,7 s | 1528 | 74 | 60% | 106 | 10,8 s / 1492 / 108 |

A coluna do oráculo é a mesma configuração com percepção perfeita (tabelas
acima). Leitura:

- **Ciclo fixo × adaptativos:** com câmera, a v2 reduz a espera em 34%
  (16,1 → 10,6 s), a viagem em 9% e a fila de inserção de 97 para 45, com mais
  chegadas (+53). A v1 e a v1.1 esperam menos que o ciclo fixo, mas deixam mais
  veículos fora da rede (179 e 290): escoam menos.
- **v2 × max-pressure:** espera praticamente igual (10,6 × 10,5 s), mas a v2
  tem mais chegadas (+28), viagem 0,9 s menor e fila de inserção menor (45 × 74).
- **Custo da percepção na v2:** +2,0 s de espera, −47 chegadas e +41 na fila em
  relação ao oráculo. É a maior perda entre as versões; a v1.1 não muda (alterna
  no ciclo mínimo, independente do estado) e o max-pressure fica igual ao
  oráculo, dentro da variação.
- A v1 e a v1.1 usam checkpoints e regras das câmeras antigas (~25 m); aqui
  entram sem retreino.

**Domain gap visão × oráculo** (`evaluate_lane_features` no log da v2, 5.433
steps, todos com visão; domain gap recalculado a partir do log `-filtro-centro`):

| Faixa | Contagem (viés) | Parados (viés) | Espera (viés) | Velocidade (viés) |
|---|---:|---:|---:|---:|
| east/lane_0 | −0,68 | −0,02 | +6,0 s | −1,31 m/s |
| east/lane_1 | −1,12 | −0,53 | −3,1 s | −0,61 m/s |
| south/lane_0–3 | +0,03 a +0,15 | +0,06 a +0,30 | +0,8 a +4,9 s | −0,4 a −1,2 m/s |
| west/lane_0 | −0,02 | +0,04 | +0,5 s | −0,30 m/s |

- O erro está concentrado no **Leste**, a aproximação saturada que mais pesa:
  a câmera conta ~0,7–1,1 veículo a menos por faixa. Com isso a v2 visual dá
  59% do verde ao Leste/Oeste, contra 63% com o oráculo, e acumula fila.
- A velocidade visual é subestimada em todas as faixas, e a espera do sul é
  superestimada.
- O ponto de solo da visão fica ~0,7–0,8 m a montante do oráculo (mediana:
  −0,81 m no leste, −0,76 m no sul, −0,69 m no oeste);
  `lane_state.visual_ground_offset_m` continua 0.
- A ação do DQN com features visuais coincide com a ação com features do
  oráculo em **71,1%** das 605 decisões.

### Versões no ambiente novo — percepção visual (Unity, cenário original)

Rodado em 2026-10-04, com o filtro corrigido e o mesmo protocolo do calibrado
(seeds 201–203, 300 s + 1800 s, v2 = `dqn-v2-roi60-mix-pretrain-best.pt`,
sem viaturas). `missing_frames = 0`. Arquivo:
`results/evaluation/versoes-original-visual.json` (o resultado do ambiente de
25 m foi preservado em `versoes-original-visual-ambiente-25m.json`).

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O | Trocas | Oráculo: espera / chegadas |
|---|---:|---:|---:|---:|---:|---:|---|
| Linha de base (ciclo fixo) | 14,9 s | 37,3 s | 1431 | 37 | 50% | 0 | 14,9 s / 1431 |
| v1 (heurística) | 4,6 s | 27,2 s | 1472 | 0 | 50% | 129 | 4,7 s / 1473 |
| v1.1 (DQN estado v1) | 4,6 s | 27,3 s | 1474 | 0 | 50% | 127 | — |
| v2 (DQN estado v2) | 4,9 s | 27,5 s | 1471 | 0 | 49% | 122 | 4,4 s / 1474 |
| max-pressure | 6,1 s | 28,6 s | 1470 | 0 | 48% | 98 | 4,6 s / 1474 |

Espera por seed (201/202/203): v2 4,9 / 5,0 / 4,7 s; v1 4,5 / 4,7 / 4,6 s;
max-pressure 6,2 / 5,7 / 6,3 s.

- Com demanda equilibrada, todas as versões adaptativas reduzem a espera do
  ciclo fixo em 59–69% e escoam toda a demanda (fila de inserção zero).
- A v2 com câmera fica 0,3 s atrás da v1 e da v1.1 (4,9 × 4,6 s), com as
  mesmas chegadas: não piora com demanda equilibrada. Em relação ao oráculo,
  perde 0,5 s, como no calibrado. A ação com features visuais coincide com a do
  oráculo em 87,1% das 425 decisões (`domain-gap-roi60-original-v2.json`).
- O max-pressure é a única versão que piora com a câmera (4,6 → 6,1 s): troca
  menos (98 × 129 trocas) e deixa verdes mais longos que o necessário.
- Junto com o calibrado: a v2 é a melhor versão quando a demanda é desigual
  (−43% de espera, maior vazão) e empata com as demais quando é equilibrada.

### Correção: filtro da ROI de aproximação pela base da caixa (2026-10-03)

A análise da subcontagem do Leste (log da v2 visual acima) mostrou:

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
  +0,8 m da do oráculo em todas as faixas e distâncias.
- A faixa 1 do Leste também perde 17–40% a 10–50 m, mais com fila parada (35%)
  que em movimento (26%). Aí as detecções brutas já faltam: é oclusão pela
  faixa 0 no ângulo lateral da câmera Leste, e não se corrige no filtro.

Correção: `filter_detections_to_roi(..., anchor="bottom_center")` no
`VisualPipeline`, com o mesmo ponto de solo das features por faixa (o padrão
`center` continua para o legado `test_unity_vision`). Na detecção de viaturas,
o pedido passa a sair a ~55–60 m da linha, em vez de ~40 m.

**Consequência:** os resultados com percepção visual de 2026-10-02 (versões e
preempção) foram obtidos com o filtro pelo centro. Cada tabela continua
internamente comparável (todas as linhas tinham o mesmo filtro), mas precisa
ser refeita com a correção para valer como resultado do ambiente atual.

### Preempção por aviso V2I (percepção oráculo, seeds 201–203, 1800 s)

- Viaturas de emergência entram a cada ~3 min (10 por seed, 30 por política),
  sorteadas entre Sul, Leste e Oeste, obedecendo ao semáforo.
- O aviso V2I chega 15 s antes de a viatura entrar na rede. A preempção
  assume quando ela está a ≤ 20 s da linha de retenção: mantém o verde dela
  (além do verde máximo, se preciso) ou encerra o outro verde sem esperar o
  mínimo. Amarelo e all-red nunca são pulados.
- Métrica da viatura: perda de tempo até cruzar a linha de retenção
  (`getTimeLoss`).

| Cenário | Política | Perda média da viatura | Perda máxima | Viaturas sem parar | Espera do tráfego | Chegadas |
|---|---|---:|---:|---:|---:|---:|
| calibrado | ciclo fixo | 19,6 → **1,1 s** | 50,4 → 4,3 s | 44% → 100% | 16,1 → 17,1 s | 1511 → 1576 |
| calibrado | v2 | 14,1 → **1,1 s** | 41,4 → 3,8 s | 30% → 100% | 10,1 → 11,5 s | 1612 → 1609 |
| calibrado | max-pressure | 15,9 → **1,3 s** | 42,7 → 4,4 s | 31% → 100% | 11,0 → 14,9 s | 1493 → 1556 |
| original | ciclo fixo | 17,0 → **1,0 s** | 47,5 → 3,8 s | 40% → 100% | 14,9 → 18,4 s | 1438 → 1425 |
| original | v2 | 8,9 → **1,1 s** | 37,9 → 3,5 s | 50% → 100% | 8,5 → 11,7 s | 1481 → 1474 |
| original | max-pressure | 9,8 → **1,3 s** | 20,3 → 3,7 s | 37% → 100% | 4,6 → 7,2 s | 1484 → 1481 |

(Cada célula mostra sem → com preempção.)

- Com preempção, todas as viaturas cruzam sem parar, com ~1 s de perda média
  e no máximo ~4 s, independentemente da política.
- O custo é de +1 a +4 s na espera média do restante do tráfego. No ciclo
  fixo e no max-pressure calibrados, as chegadas até aumentam, porque as
  preempções quebram ciclos mal repartidos para o Leste saturado.
- Com a v2 treinada nos dois cenários, o resultado se mantém: perda média
  9,5 → 1,1 s (calibrado) e 10,1 → 1,3 s (original), 100% sem parar, com a
  espera do tráfego passando de 8,7 → 10,3 s e 4,5 → 7,1 s.
- Arquivos: `results/evaluation/preempcao-{calibrated,original}-oracle.json`,
  `preempcao-mix-{calibrated,original}-oracle.json`,
  `versoes-roi60-{calibrated,original}-oracle.json` e
  `versoes-roi60-mix-{calibrated,original}-oracle.json`.

### Comandos

```bash
../.venv/bin/python -m experiments.extend_lane_rois --length 60     # ROIs a partir da borda próxima
../.venv/bin/python -m experiments.pretrain_dqn_sumo --double-dqn --scenarios calibrated,original \
  --checkpoint-output ../results/models/dqn-v2-roi60-mix-pretrain-last.pt \
  --best-checkpoint-output ../results/models/dqn-v2-roi60-mix-pretrain-best.pt
../.venv/bin/python -m experiments.compare_versions --scenario calibrated --perception oracle \
  --v2-dqn-model ../results/models/dqn-v2-roi60-mix-pretrain-best.pt
../.venv/bin/python -m experiments.evaluate_preemption --scenario calibrated \
  --v2-dqn-model ../results/models/dqn-v2-roi60-mix-pretrain-best.pt
```

## DQN v2 — estado por faixa, pré-treino SUMO e avaliação visual

Status: concluído (branch `feat/estado-faixa-v2`, 2026-09-28/29). Os números
abaixo vêm de arquivos locais em `results/` (ignorados pelo Git) e podem ser
reproduzidos com os comandos do fim da seção.

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
  vídeos de drone, Leste com v/c≈1,0) e `original`; escolha com `--scenario`.
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
**manter as ROIs como estão** e declarar a limitação — o estado satura em
~3–4 veículos por faixa quando a fila do Leste passa da ROI.

### Estado v2 e treino

- Por faixa (7): contagem, parados (< 1,39 m/s por ≥ 1 s, padrão do E2),
  ocupação espacial, velocidade média e espera, normalizados pela capacidade
  da ROI (comprimento / 7,5 m); mais a fase em one-hot e o tempo da fase — 41
  entradas.
- As features vêm de `ApproachKinematicsTracker`, alimentado por duas fontes
  com o mesmo contrato: visão (base das bboxes projetada pela homografia da
  ROI) e oráculo TraCI (posições reais no mesmo intervalo da ROI). Um teste de
  paridade garante features idênticas para a mesma trajetória.
- A política só decide em verde, entre o verde mínimo e o máximo, a cada 5 s;
  as transições são SMDP (recompensa acumulada com desconto γ^k, γ=0,99/s).
- Recompensa: nível em [−1, 0] sobre as lanes de entrada inteiras (parados,
  espera nativa e fila de inserção), vinda do TraCI; não é entrada da política.
- Pré-treino só SUMO com o oráculo: 40 episódios de 300 s de aquecimento +
  1800 s controlados (~6 s por episódio), seeds 1–40, Double DQN, ε linear por
  decisão. Melhor checkpoint: episódio 34 (6.797 passos de gradiente), escore
  de validação −0,059 contra −0,314 do ciclo fixo e −0,340 do max-pressure.

### Resultados — percepção oráculo (seeds 201–203, 1800 s, média)

| Cenário | Política | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O |
|---|---|---:|---:|---:|---:|---:|
| calibrado | ciclo fixo 40/40 | 16,1 s | 36,2 s | 1503 | 97 | 50% |
| calibrado | max-pressure | 12,8 s | 37,5 s | 1317 | 284 | 50% |
| calibrado | DQN v2 | 9,1 s | 30,9 s | 1598 | 6 | 66% |
| original | ciclo fixo 40/40 | 14,9 s | 37,3 s | 1431 | 37 | 50% |
| original | max-pressure | 4,6 s | 27,2 s | 1474 | 0 | 50% |
| original | DQN v2 | 5,1 s | 27,6 s | 1472 | 0 | 55% |

O DQN v2 aprendeu a dar mais verde ao Leste saturado; no cenário original, em
que não treinou, empata com o max-pressure.

### Domain gap visão × oráculo (Unity, seed 1001, 900 s)

911 steps, 0 frames perdidos. Com a política pré-treinada usada direto com
visão (zero-shot), a espera foi 10,9 s contra 8,3 s com o oráculo, com o mesmo
número de chegadas (790 × 791) e a mesma fração de verde (68%). A ação gulosa
coincidiu com a do oráculo em 82,7% das 98 decisões.

- Contagem e parados: correlação 0,82–0,95, exceto `south/lane_3` (subconta
  0,74 veículo em média, r=0,59 — provável oclusão pelas outras faixas).
- Velocidade subestimada (Leste −1,4 a −1,9 m/s; r≈0,6–0,7) e espera
  superestimada (até +11,8 s em `south/lane_1`), coerentes com o atraso da
  regressão de 3 pontos a 1 fps.
- Offset do ponto de solo (mediana): −0,66 m (Leste), −0,54 m (Sul) e
  −0,75 m (Oeste); abaixo de 1 m, então `visual_ground_offset_m` ficou em 0.

### Ajuste fino visual

10 episódios de 900 s nas seeds 41–50 (~100 transições por episódio, ~900
passos de gradiente) pioraram a validação visual: −0,080 (zero-shot) → −0,102
→ −0,139. O critério manteve o zero-shot; `dqn-v2-visual-best.pt` tem os mesmos
pesos de `dqn-v2-pretrain-best.pt`. Causa provável, não verificada: o replay
recomeça vazio e só com as transições correlacionadas do ajuste fino.

### Resultado final — percepção visual (Unity, seeds 201–203, 1800 s, média)

| Política | Percepção | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O |
|---|---|---:|---:|---:|---:|---:|
| ciclo fixo 40/40 | — | 16,1 s | 36,2 s | 1503 | 97 | 50% |
| max-pressure | visual | 11,1 s | 33,9 s | 1498 | 104 | 56% |
| **DQN v2 (zero-shot)** | **visual** | **10,3 s** | **32,1 s** | **1599** | **1** | **67%** |
| DQN v2 | oráculo | 9,1 s | 30,9 s | 1598 | 6 | 66% |

Pela câmera, o DQN v2 reduz a espera em 36% em relação ao ciclo fixo, escoa 6%
mais veículos e zera a fila de inserção; o max-pressure visual tem espera
parecida, mas acumula 104 veículos esperando para entrar. O custo da visão em
relação ao oráculo é de 1,2 s de espera. As execuções visuais foram
reprodutíveis seed a seed e sem frames perdidos.

### Comparação das versões no mesmo ambiente

`experiments.compare_versions` roda a linha de base, a v1, a v1.1, a v2 e o
max-pressure com o mesmo cenário, as mesmas seeds (201–203), 300 s de
aquecimento, 1800 s controlados, a mesma camada de segurança e a mesma
percepção. As regras de cada versão estão em `experiments/version_policies.py`.
A v1 e a v1.1 recebem a contagem por faixa da mesma percepção usada pela v2,
em vez do centro da bbox com média móvel da época, e decidem a cada 1 s.

Percepção oráculo, cenário calibrado:

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O | Trocas |
|---|---:|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 16,1 s | 36,2 s | 1503 | 97 | 50% | 0 |
| v1 (heurística) | 12,2 s | 36,9 s | 1349 | 254 | 52% | 126 |
| v1.1 (DQN estado v1) | 12,9 s | 38,0 s | 1311 | 290 | 50% | 129 |
| v2 (DQN estado v2) | 9,1 s | 30,9 s | 1598 | 6 | 66% | 93 |
| max-pressure | 12,8 s | 37,5 s | 1317 | 284 | 50% | 127 |

Percepção oráculo, cenário original:

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O | Trocas |
|---|---:|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 14,9 s | 37,3 s | 1431 | 37 | 50% | 0 |
| v1 (heurística) | 4,7 s | 27,4 s | 1473 | 0 | 50% | 129 |
| v1.1 (DQN estado v1) | 4,6 s | 27,3 s | 1474 | 0 | 50% | 127 |
| v2 (DQN estado v2) | 5,1 s | 27,6 s | 1472 | 0 | 55% | 116 |
| max-pressure | 4,6 s | 27,2 s | 1474 | 0 | 50% | 129 |

- **No cenário calibrado,** a v1 e a v1.1 alternam no ciclo mínimo e dividem o
  verde 50/50. Escoam menos veículos que o ciclo fixo e deixam 250–290
  veículos fora da rede; a espera média delas só parece melhor porque esses
  veículos não entram na conta. A v2 dá 66% do verde ao Leste e ganha em todas
  as métricas.
- **No cenário original,** com demanda equilibrada, as versões adaptativas
  empatam; a v2, que não treinou nele, fica 0,4–0,5 s atrás.
Percepção visual (Unity), cenário calibrado, 0 frames perdidos:

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O |
|---|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 16,1 s | 36,2 s | 1503 | 97 | 50% |
| v1 (heurística) | 12,1 s | 36,7 s | 1351 | 253 | 52% |
| v1.1 (DQN estado v1) | 12,9 s | 38,0 s | 1312 | 289 | 50% |
| v2 (DQN estado v2) | 10,3 s | 32,1 s | 1599 | 1 | 67% |
| max-pressure | 11,1 s | 33,9 s | 1498 | 104 | 56% |

Com a câmera, a ordem é a mesma do oráculo: só a v2 dá mais verde ao Leste,
e a v1/v1.1 ficam abaixo do ciclo fixo em chegadas.

Percepção visual (Unity), cenário original, 0 frames perdidos:

| Versão | Espera | Viagem | Chegadas | Fila de inserção final | Verde L/O |
|---|---:|---:|---:|---:|---:|
| Linha de base (ciclo fixo) | 14,9 s | 37,3 s | 1431 | 37 | 50% |
| v1 (heurística) | 4,6 s | 27,2 s | 1473 | 0 | 50% |
| v1.1 (DQN estado v1) | 4,6 s | 27,2 s | 1474 | 0 | 50% |
| v2 (DQN estado v2) | 5,4 s | 28,0 s | 1469 | 1 | 56% |
| max-pressure | 5,8 s | 28,3 s | 1472 | 0 | 49% |

No cenário equilibrado, as versões adaptativas empatam também com a câmera; a
v2 fica 0,8 s atrás da v1 em espera, com as mesmas chegadas.

Arquivos: `results/evaluation/versoes-calibrated-oracle.json`,
`versoes-original-oracle.json`, `versoes-original-visual.json` e `versoes-calibrated-visual-v1.json` (v1 e
v1.1 visuais; a v2 e o max-pressure visuais estão em
`teste-visual-dqn-zero-shot.json` e `teste-visual-max-pressure.json`).

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

### Limitações registradas

- ROIs de ~25 m: filas longas do Leste saturam o estado.
- Velocidade visual subestimada e oclusão na faixa sul mais distante.
- A recompensa do treino vem do TraCI (a política é que é só visual).
- Três seeds de teste; o ajuste fino simples não melhorou o zero-shot.

### Comandos (a partir de `python/`)

```bash
# Pré-treino e avaliação só SUMO (percepção oráculo)
../.venv/bin/python -m experiments.pretrain_dqn_sumo --double-dqn
../.venv/bin/python -m experiments.compare_versions --scenario calibrated --perception oracle
../.venv/bin/python -m experiments.evaluate_policies_sumo --scenario calibrated \
  --dqn-model ../results/models/dqn-v2-pretrain-best.pt \
  --output ../results/evaluation/teste-sumo-oraculo.json

# Com a Unity em Play Mode (SPImport, Dataset Capture desativado; reinicie o Play Mode antes de cada comando)
../.venv/bin/python -m experiments.run_visual_policy --scenario calibrated --policy dqn \
  --dqn-model ../results/models/dqn-v2-pretrain-best.pt --seeds 201,202,203 --control-seconds 1800 \
  --step-log-output ../results/logs/teste-visual-dqn-zero-shot.jsonl \
  --output ../results/evaluation/teste-visual-dqn-zero-shot.json
../.venv/bin/python -m experiments.evaluate_lane_features \
  --step-log ../results/logs/etapa11-gap-seed-1001.jsonl \
  --dqn-model ../results/models/dqn-v2-pretrain-best.pt
../.venv/bin/python -m experiments.finetune_dqn_visual \
  --init-checkpoint ../results/models/dqn-v2-pretrain-best.pt
```

## Avaliação visão versus E2 — cenário SP

Status: implementada e executada em 100 steps com as câmeras e calibrações
atuais.

O E2 permanece exclusivamente como verdade de terreno de avaliação. A decisão
online continua recebendo somente a saída visual. A comparação desta seção é
diagnóstica, não uma medida direta de erro do detector. Na época, os E2
cobriam 20 m; hoje cobrem 42,6–45,8 m, enquanto as ROIs das câmeras cobrem
23–26 m. A medida estrita passou a ser a do DQN v2 (seção anterior): visão ×
oráculo TraCI no mesmo intervalo físico de cada ROI.

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
(seção **DQN v2**). Pendente: teste visual no cenário `original`.
