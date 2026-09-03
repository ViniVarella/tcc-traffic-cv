# TCC Traffic CV

## Observação

A simulação 3D no Unity ainda não foi finalizada. Neste momento, os dados utilizados no projeto foram extraídos de vídeos reais capturados por drone e processados com o projeto open-source SimJamComputerVision, a partir do qual obtivemos as métricas de contagem de veículos e velocidade média. Os arquivos CSV com essas métricas, organizados por cenário e por sentido, estão nas pastas `SP` e `EUA` em `/simjamcv/DigitalTwinsforSmartCities/`, com nomes no formato `lane_metrics_{sentido}`. Os vídeos com as detecções de veículos para cada cenário e sentido estão disponíveis no Google Drive: https://drive.google.com/drive/folders/1bBa7s3MElVlagaMF5ZkscvY7kFj51qzr?usp=sharing

## Introdução

Sistema experimental de controle semafórico adaptativo baseado em visão computacional.

O projeto integra SUMO, Unity, YOLOv8 e ByteTrack para avaliar uma abordagem de otimização de tráfego urbano em ambiente simulado. O SUMO gera a dinâmica do tráfego, a Unity renderiza a cena 3D, o YOLO detecta veículos nos frames das câmeras virtuais, o ByteTrack associa detecções entre frames e um controlador semafórico tomará decisões com base na estimativa visual de filas.

A decisão de controle não usa sensores perfeitos do SUMO. Os dados internos do SUMO são usados para renderização, sincronização e avaliação posterior.

## Arquitetura

`SUMO -> Python/TraCI -> Unity/SUMO2Unity -> 3 câmeras de entrada -> Python/YOLO+ByteTrack+ROI -> controlador -> SUMO`

## Decisões arquiteturais revisadas

- Simulação `step-based`: o Python avança o SUMO com `simulationStep()` em modo síncrono. O tempo de referência para métricas é o tempo simulado, não o relógio de parede.
- Python como único cliente TraCI: a Unity não se conecta diretamente ao SUMO.
- Três câmeras virtuais operacionais na Unity: `south`, `east` e `west`. A aproximação `north` é apenas de saída no cenário SP e não é observada.
- Cada câmera possui uma ROI de aproximação e ROIs por faixa. Elas são a medida operacional para o controlador; os E2 cobrem outro trecho físico e servem apenas como referência de avaliação.
- Visão a cada `N` steps: a configuração inicial usa `step_length = 0.1s` e `update_every_steps = 5`, o que equivale a rodar a visão a cada `0.5s` simulados.
- Frames Unity -> Python via TCP: a confiabilidade do transporte é prioritária para imagens JPEG completas em localhost.
- Cada frame deve carregar `step_id`, `sim_time`, `camera_id`, `image_format` e `payload_size`.
- Ground truth do SUMO entra apenas em logs e avaliação, nunca na decisão de controle.
- A primeira versão do controlador trabalhará com dois grupos de fluxo: `NS = north + south` e `EW = east + west`.
- O controlador inicial terá verde mínimo, verde máximo, amarelo, all-red e transições seguras entre `NS` e `EW`.

## Escopo inicial deliberadamente simples

- uma interseção;
- duas fases principais: `NS` e `EW`;
- três câmeras operacionais da Unity (`south`, `east` e `west`);
- uma ROI de aproximação e ROIs por faixa por câmera;
- YOLOv8n inicialmente;
- visão a cada `0.5s` simulados;
- ground truth apenas para avaliação.

## Principais módulos

- `python/sumo`: integração TraCI e extração de estado.
- `python/bridge`: comunicação Python e Unity.
- `python/vision`: detecção, rastreamento, ROI e estimativa de fila.
- `python/controller`: política de controle semafórico.
- `python/logging_utils`: logs, métricas e metadados de execução.
- `python/experiments`: execução de cenários e experimentos.

## Teste de visão local

O teste de visão roda sem SUMO e sem Unity, usando imagem ou vídeo local para validar a pipeline YOLO + ByteTrack + ROI.

Esse teste é preliminar. Ele usa um vídeo top-down local apenas para validar a pipeline de visão em isolamento. A arquitetura final dos experimentos usa frames das três câmeras operacionais da Unity, cada uma com suas próprias ROIs.

1. Instale as dependências do ambiente virtual:

```powershell
cd python
python -m pip install -r requirements.txt
```

2. Execute o teste com um vídeo local:

```powershell
cd python
python -m experiments.test_vision --input ../samples/traffic_top_view.mp4
```

3. Para imagem única:

```powershell
cd python
python -m experiments.test_vision --input ../samples/minha_imagem.jpg
```

Os frames de debug são salvos em `results/frames` com bounding boxes, `track_id`, ROIs e contagens suavizadas.

No modo preliminar com vídeo único, o script ainda aceita ROIs derivadas do frame ou compatibilidade temporária com ROIs globais. Na arquitetura final, a configuração principal passa a ser por câmera em `cameras.north.roi`, `cameras.south.roi`, `cameras.east.roi` e `cameras.west.roi`.

## Teste inicial com SUMO

O teste inicial de integração TraCI roda sem Unity e sem controle adaptativo. Ele apenas inicia o SUMO, avança alguns steps e imprime tempo simulado, número de veículos ativos e estado do semáforo configurado.

```powershell
cd python
python -m experiments.test_sumo_traci
```

Observações:

- o Python continua sendo o único cliente TraCI;
- o script sempre fecha a conexão TraCI em `finally`;
- se o arquivo configurado em `sumo.config_path` não existir, o teste falha com uma mensagem clara explicando que o `.sumocfg` não foi encontrado;
- o módulo `python/sumo/ground_truth.py` existe apenas para avaliação futura, não para decisão de controle.

## Validação TraCI do cenário SP

O cenário SP possui um perfil independente em `python/configs/sp.yaml`. O teste
inicia `sumo/sp/Cruzamento.sumocfg`, valida o semáforo
`clusterJ0_J14_J2_J7`, os sete detectores E2 e uma troca controlada para a
fase verde secundária. Ele não inicia Unity nem executa inferência do DQN.

```powershell
cd python
python -m experiments.test_sp_traci
```

O perfil usa a porta TraCI local `8873`, para tornar a conexão explícita e
facilitar diagnósticos de inicialização.

## Teste de importação SP no Unity

No Unity, execute `Traffic Vision > SUMO > Create SP Import Scene`. A ação cria
e seleciona `SP Road Network Importer`, já configurado com
`Cruzamento.net.xml`. No Inspector, clique em `Import / rebuild SUMO road
network`; a cena resultante é salva como `Assets/Scenes/SPImport.unity`.

O teste esperado confirma 22 faixas e um cruzamento. O botão `Clear generated
road network` deve remover a geometria e uma nova importação deve recriá-la sem
duplicar objetos.

## Teste inicial Python -> Unity

O primeiro teste de comunicação Python -> Unity envia estados JSON fake via UDP. Ele valida apenas o lado Python da ponte e a recepção manual do `step` ou `step_id` no log da Unity.

```powershell
cd python
python -m experiments.test_unity_comm
```

Cada mensagem inclui:

- `step`
- `step_id`
- `sim_time`
- `vehicles`
- `traffic_lights`

O teste usa:

- `unity.state_host`
- `unity.state_port`

Receptor Unity mínimo:

- arquivo: [unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs](C:/Users/vinic/PycharmProjects/tcc-traffic-cv/unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs)
- na Unity, crie um `GameObject` vazio, anexe `PythonStateReceiver` e rode a cena;
- o Console da Unity deve mostrar `step` e `step_id` recebidos.

Observações:

- este marco cobre apenas Python -> Unity;
- o envio usa JSON simples por UDP;
- a Unity não deve se conectar diretamente ao SUMO;
- captura de frames Unity -> Python fica para um marco posterior.

## Teste inicial SUMO -> Python -> Unity

O teste deste marco substitui o estado fake por estado real extraído do SUMO via TraCI e enviado para a Unity por UDP.

```powershell
cd python
python -m experiments.test_sumo_to_unity
```

O script:

- inicia o cenário configurado em `sumo.config_path`;
- avança a simulação por alguns steps;
- extrai veículos reais e estado real do semáforo configurado;
- converte o estado para o formato Unity em `python/sumo/state_extractor.py`;
- envia o estado para a Unity via `UnityBridge`.

Configuração mínima na Unity:

- anexe [PythonStateReceiver.cs](C:/Users/vinic/PycharmProjects/tcc-traffic-cv/unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/PythonStateReceiver.cs) a um `GameObject`;
- anexe [VehicleManager.cs](C:/Users/vinic/PycharmProjects/tcc-traffic-cv/unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/VehicleManager.cs) a um `GameObject` na cena;
- opcionalmente anexe [TrafficLightVisualController.cs](C:/Users/vinic/PycharmProjects/tcc-traffic-cv/unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/TrafficLightVisualController.cs) a um objeto com `Renderer`;
- rode a cena em Play Mode antes de executar o script Python.

Validação esperada:

- o terminal Python deve imprimir `state_sent step=... sim_time=... vehicles=... traffic_lights=1`;
- o Console da Unity deve registrar `step`, `step_id`, `sim_time` e quantidade de veículos;
- a cena deve mostrar cubos simples representando veículos se movendo ao longo dos steps recebidos.

## Avaliação: tempo fixo versus controlador visual

O controlador adaptativo já está integrado. Ele usa exclusivamente as contagens
visuais das câmeras `south`, `east` e `west`; E2 e outros dados perfeitos do
SUMO não entram na decisão.

Para comparar as políticas sob a mesma configuração e seed, execute primeiro o
baseline de tempos fixos do SUMO (Unity não é necessária):

```bash
cd python
python -m experiments.run_fixed_time_baseline --config configs/sp.yaml --steps 100 --output ../results/evaluation/fixed-time-baseline-metrics.json
```

Em seguida, com a cena `SPImport` em Play Mode e a captura de dataset desativada,
execute o controlador visual, incluindo a saída de métricas:

```bash
python -m experiments.run_visual_controller --config configs/sp.yaml --steps 100 --camera-ids south,east,west --model ../runs/results/models/yolov8n-unity-run-002-mask/weights/best.pt --classes 0 --metrics-output ../results/evaluation/visual-controller-metrics.json
```

Por fim, gere a comparação:

```bash
python -m experiments.compare_control_experiments --baseline ../results/evaluation/fixed-time-baseline-metrics.json --visual-adaptive ../results/evaluation/visual-controller-metrics.json --output ../results/evaluation/fixed-vs-visual-controller.json
```

As métricas são veículos concluídos, tempo médio de viagem, tempo médio de
espera, fila média/máxima e vazão. O arquivo comparativo registra a diferença
absoluta e percentual; valores maiores são desejáveis apenas para veículos
concluídos e vazão.

Para replicações independentes, informe a mesma `--seed` no baseline e no
controlador visual de cada par, mudando-a entre os pares. O SUMO é
determinístico para uma seed específica; portanto, usar `--seed 7`, por
exemplo, cria um novo padrão de demanda, mas mantém a comparação justa entre
as duas políticas.

### Resultado inicial (três seeds)

Em 100 segundos simulados para as seeds `42`, `7` e `99`, o controlador visual
superou o plano fixo em todos os pares. As médias foram:

| Métrica | Tempo fixo | Controle visual | Variação |
| --- | ---: | ---: | ---: |
| Veículos concluídos | 50,67 | 60,67 | +19,7% |
| Vazão | 1842,4 veh/h | 2206,1 veh/h | +19,7% |
| Tempo médio de viagem | 27,35 s | 26,11 s | -4,6% |
| Tempo médio de espera | 6,77 s | 3,93 s | -42,0% |
| Fila média | 8,70 | 3,89 | -55,3% |
| Fila máxima | 19,67 | 9,33 | -52,5% |

É uma avaliação experimental inicial com três cenários de demanda; ela mostra
consistência entre as seeds, mas não substitui um estudo estatístico de maior
escala.
