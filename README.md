# TCC Traffic CV

Sistema experimental de controle semafórico adaptativo baseado em visão computacional.

O projeto integra SUMO, Unity, YOLOv8 e SORT para avaliar uma abordagem de otimização de tráfego urbano em ambiente simulado. O SUMO gera a dinâmica do tráfego, a Unity renderiza a cena 3D, o YOLO detecta veículos nos frames das câmeras virtuais, o SORT pode auxiliar no rastreamento e um controlador semafórico toma decisões com base na estimativa visual de filas.

A decisão de controle não usa sensores perfeitos do SUMO. Os dados internos do SUMO são usados para renderização, sincronização e avaliação posterior.

## Arquitetura

`SUMO -> Python/TraCI -> Unity/SUMO2Unity -> 4 cameras -> Python/YOLO+ROI -> controlador -> SUMO`

## Decisões arquiteturais revisadas

- Simulação `step-based`: o Python avança o SUMO com `simulationStep()` em modo síncrono. O tempo de referência para métricas é o tempo simulado, não o relógio de parede.
- Python como único cliente TraCI: a Unity não se conecta diretamente ao SUMO.
- Quatro câmeras virtuais na Unity: `north`, `south`, `east` e `west`.
- Uma ROI fixa por câmera: a contagem relevante para o controlador é a quantidade de veículos aguardando dentro da ROI daquela aproximação.
- Visão a cada `N` steps: a configuração inicial usa `step_length = 0.1s` e `update_every_steps = 5`, o que equivale a rodar a visão a cada `0.5s` simulados.
- Frames Unity -> Python via TCP: a confiabilidade do transporte é prioritária para imagens JPEG completas em localhost.
- Cada frame deve carregar `step_id`, `sim_time`, `camera_id`, `image_format` e `payload_size`.
- Ground truth do SUMO entra apenas em logs e avaliação, nunca na decisão de controle.
- A primeira versão do controlador trabalhará com dois grupos de fluxo: `NS = north + south` e `EW = east + west`.
- O controlador inicial terá verde mínimo, verde máximo, amarelo, all-red e transições seguras entre `NS` e `EW`.

## Escopo inicial deliberadamente simples

- uma interseção;
- duas fases principais: `NS` e `EW`;
- quatro câmeras da Unity;
- uma ROI por câmera;
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

O teste de visão roda sem SUMO e sem Unity, usando imagem ou vídeo local para validar a pipeline YOLO + SORT + ROI.

Esse teste é preliminar. Ele usa um vídeo top-down local apenas para validar a pipeline de visão em isolamento. A arquitetura final dos experimentos não usará esse vídeo como entrada principal; ela usará frames vindos de quatro câmeras virtuais da Unity, cada uma com sua ROI própria.

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

## Próxima validação importante

Antes de integrar controle completo, o projeto deve validar cedo se o YOLO detecta bem os veículos renderizados pela Unity. Frames sintéticos podem divergir do domínio visual do COCO, então esse risco precisa ser medido antes de fechar a arquitetura de controle.
