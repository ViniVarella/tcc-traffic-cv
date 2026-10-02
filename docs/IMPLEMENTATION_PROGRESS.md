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
- Pendentes: dataset e YOLO com a classe ambulância (ângulos novos das
  câmeras), detecção visual das viaturas e avaliações visuais no ambiente
  novo.

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
- **Ressalva:** a antecedência da visão depende do modo. Sem preempção (14,2 s)
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

Rodado em 2026-10-02: `compare_versions --scenario calibrated --perception visual`,
seeds 201–203, 300 s + 1800 s, YOLO de duas classes (`--classes 0,1`, 960 px),
v2 = `dqn-v2-roi60-mix-pretrain-best.pt`, sem viaturas de emergência.
`missing_frames = 0`. Arquivo: `results/evaluation/versoes-calibrated-visual.json`;
logs por step em `results/logs/versoes-calibrated-visual-<versão>.jsonl`.

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
steps, todos com visão; `results/evaluation/domain-gap-roi60-calibrated-v2.json`):

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
