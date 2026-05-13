# Guia de Implementação — TCC: Otimização de Tráfego com Visão Computacional, SUMO, Unity e YOLO

## 1. Introdução

Este projeto tem como objetivo desenvolver um sistema de controle semafórico adaptativo baseado em visão computacional. A proposta é simular o tráfego urbano no SUMO, renderizar esse tráfego em ambiente 3D na Unity, processar os frames das câmeras virtuais com YOLO e usar a estimativa visual de veículos em fila para tomar decisões de controle semafórico.

O sistema deve ser construído com a seguinte arquitetura principal:

```text
SUMO → Python/TraCI → Unity/SUMO2Unity → 4 câmeras → Python/YOLO+ROI(+SORT) → controlador → SUMO
```

O ponto central do projeto é que a decisão semafórica deve ser tomada a partir da imagem renderizada pela Unity, não diretamente a partir dos sensores internos do SUMO. O SUMO será usado para gerar a dinâmica do tráfego, controlar a simulação e fornecer ground truth para avaliação posterior. A Unity será usada como ambiente visual 3D. O YOLO será usado para detectar veículos a partir da imagem, as ROIs por câmera serão a base da contagem usada pelo controlador e o SORT poderá ser usado como apoio de tracking e debug.

O projeto reaproveitará dois trabalhos existentes:

1. O repositório `car-counter`, que já contém uma implementação em Python de detecção e contagem de veículos usando YOLOv8 e SORT.
2. O projeto SUMO2Unity, que fornece uma base de integração entre SUMO e Unity.

Neste projeto, o SUMO2Unity será usado principalmente como base visual e importador de cenário Unity, mas a arquitetura de controle será centralizada no Python. A Unity não deve ser o cliente TraCI principal. O Python deve ser o único cliente TraCI responsável por avançar a simulação, extrair o estado necessário para renderização, enviar esse estado para a Unity, receber os frames das câmeras e aplicar as decisões de controle no SUMO.

---

## 2. Objetivo técnico

Construir um sistema completo capaz de:

```text
1. Iniciar uma simulação SUMO.
2. Avançar a simulação passo a passo via Python/TraCI.
3. Extrair posições, rotações e estados de veículos/semaforos do SUMO.
4. Enviar esse estado para Unity.
5. Atualizar a cena 3D na Unity usando a base do SUMO2Unity.
6. Renderizar quatro câmeras virtuais.
7. Enviar os frames das câmeras de volta para Python.
8. Detectar veículos nos frames usando YOLO.
9. Opcionalmente rastrear veículos usando SORT.
10. Estimar filas por região de interesse em cada câmera.
11. Agregar contagens em grupos NS e EW.
12. Tomar uma decisão semafórica.
13. Aplicar a decisão no SUMO via TraCI.
14. Salvar logs e métricas para avaliação experimental.
```

---

## 3. Decisões arquiteturais principais

### 3.1 Python será o único cliente TraCI

O Python deve controlar o SUMO diretamente via TraCI. A Unity não deve conectar diretamente ao SUMO para consultar veículos ou controlar a simulação.

Fluxo correto:

```text
SUMO ←→ Python ←→ Unity
          ↓
      YOLO + ROI
          ↓
  controle semafórico
```

Fluxo que deve ser evitado:

```text
SUMO ←→ Python
SUMO ←→ Unity
```

O motivo é reduzir a complexidade de sincronização. Com dois clientes TraCI, seria necessário garantir ordem de execução, sincronização de `simulationStep()` e correspondência exata entre o estado simulado e o frame renderizado.

### 3.2 Simulação step-based, não tempo real estrito

O sistema deve operar em modo síncrono orientado a passos discretos da simulação. O Python avança o SUMO via `simulationStep()` e só então executa as demais etapas do pipeline.

Regra operacional:

```text
- o relógio de referência do experimento é o tempo simulado do SUMO;
- não é necessário que 0,1 s simulados sejam processados em 0,1 s de tempo real;
- se YOLO, renderização ou comunicação adicionarem latência, isso é aceitável;
- determinismo, simplicidade e reprodutibilidade têm prioridade sobre tempo real estrito.
```

### 3.3 Quatro câmeras virtuais na Unity

A arquitetura final deve usar quatro câmeras virtuais fixas:

```text
- north
- south
- east
- west
```

Cada câmera observa uma aproximação da interseção.

Motivação:

```text
- veículos maiores no frame;
- menos oclusão;
- ROIs mais simples;
- melhor probabilidade de detecção pelo YOLO.
```

### 3.4 Uma ROI fixa por câmera

Cada câmera terá sua própria ROI fixa, calibrada manualmente em pixels. Essa ROI representa a região da imagem onde veículos aguardando o semáforo devem ser contados.

Regra metodológica:

```text
YOLO detecta no frame inteiro.
O controlador usa apenas a contagem dos veículos dentro da ROI relevante.
```

### 3.5 Estrutura inicial do controle

A primeira versão do controlador trabalhará com dois grupos de fluxo:

```text
NS = north + south
EW = east + west
```

Isso reduz a complexidade inicial e é suficiente para uma primeira validação do ciclo completo.

### 3.6 Visão a cada N steps

A visão não precisa ser executada a cada `simulationStep()`. A configuração inicial recomendada é:

```text
step_length = 0.1 s
update_every_steps = 5
```

Isso equivale a executar a percepção a cada `0,5 s` simulados. Se o custo computacional ficar alto com quatro câmeras, esse intervalo pode ser aumentado para `1,0 s` simulado ou outro valor adequado.

### 3.7 Frames Unity → Python via TCP

O envio de frames da Unity para o Python deve usar TCP, não UDP.

Motivação:

```text
- frames JPEG podem ser grandes;
- UDP pode sofrer fragmentação e perda;
- o experimento é step-based, então confiabilidade vale mais que latência mínima;
- localhost com TCP é suficiente para o TCC.
```

### 3.8 Timeout de frame não deve travar o experimento

Se um frame não chegar dentro do timeout:

```text
- registrar missing_frame para aquela câmera;
- usar a última contagem válida daquela câmera;
- continuar a simulação.
```

Isso evita que uma falha transitória de renderização ou comunicação derrube o experimento inteiro.

### 3.9 Ground truth do SUMO apenas para avaliação

O SUMO pode fornecer métricas perfeitas da simulação, mas essas informações devem ser usadas apenas para:

```text
- logs;
- métricas;
- comparação entre contagem visual e verdade de terreno;
- avaliação final dos experimentos.
```

O controlador principal não deve receber sensores perfeitos do SUMO.

### 3.10 Reprodutibilidade por seed fixa

A configuração do experimento deve prever uma seed fixa.

Motivação:

```text
- comparar controle fixo e controle por visão nas mesmas condições;
- tornar os resultados reproduzíveis;
- evitar comparações enviesadas por aleatoriedade da simulação.
```

### 3.11 Validar cedo o YOLO em frames da Unity

Antes de implementar o controle completo, o projeto deve capturar frames estáticos da Unity e verificar se o YOLO detecta adequadamente os veículos renderizados. Esse risco deve ser validado cedo porque o modelo foi treinado em imagens reais, e os frames sintéticos da Unity podem divergir do domínio visual esperado.

---

## 4. Uso metodológico do SUMO

O SUMO pode ser usado para:

```text
- gerar a dinâmica dos veículos;
- controlar a simulação;
- fornecer posições para renderização na Unity;
- aplicar mudanças semafóricas;
- registrar ground truth para avaliação;
- medir tempo de espera, fila real e tempo de viagem.
```

O SUMO não deve ser usado para:

```text
- decidir diretamente o semáforo com base em sensores perfeitos;
- substituir a contagem feita por visão computacional;
- alimentar o controlador principal com `lane.getLastStepHaltingNumber` ou métricas equivalentes.
```

A regra metodológica do projeto é:

```text
TraCI pode ser usado para renderização, sincronização, controle e avaliação.
TraCI não deve ser usado como sensor principal do algoritmo de decisão.
```

---

## 5. Estrutura recomendada do repositório

```text
tcc-traffic-cv/
│
├── README.md
├── docs/
│   ├── IMPLEMENTATION_GUIDE.md
│   ├── IMPLEMENTATION_PROGRESS.md
│   ├── ARCHITECTURE.md
│   ├── EXPERIMENTS.md
│   └── METHODOLOGY.md
│
├── python/
│   ├── main.py
│   ├── config.yaml
│   ├── requirements.txt
│   │
│   ├── bridge/
│   │   ├── __init__.py
│   │   ├── unity_comm.py
│   │   ├── protocol.py
│   │   └── serialization.py
│   │
│   ├── sumo/
│   │   ├── __init__.py
│   │   ├── traci_client.py
│   │   ├── state_extractor.py
│   │   └── ground_truth.py
│   │
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── yolo_detector.py
│   │   ├── sort_tracker.py
│   │   ├── roi_counter.py
│   │   ├── queue_estimator.py
│   │   └── visual_debug.py
│   │
│   ├── controller/
│   │   ├── __init__.py
│   │   ├── traffic_controller.py
│   │   ├── phase_manager.py
│   │   └── policies.py
│   │
│   ├── logging_utils/
│   │   ├── __init__.py
│   │   ├── metrics_logger.py
│   │   └── run_metadata.py
│   │
│   └── experiments/
│       ├── run_experiment.py
│       ├── scenario_config.py
│       ├── batch_runner.py
│       └── test_vision.py
│
├── sumo/
│   ├── networks/
│   ├── routes/
│   ├── configs/
│   ├── additional/
│   └── scenarios/
│
├── unity/
│   └── TrafficVisionUnity/
│       ├── Assets/
│       ├── Packages/
│       └── ProjectSettings/
│
├── results/
│   ├── logs/
│   ├── frames/
│   ├── videos/
│   ├── plots/
│   └── tables/
│
├── notebooks/
│   ├── analyze_results.ipynb
│   └── detector_validation.ipynb
│
└── third_party/
    ├── car-counter-reference/
    └── SUMO2Unity-reference/
```

Observação sobre `third_party`:

```text
- copiar/adaptar o código necessário do car-counter para python/vision;
- usar SUMO2Unity como base do projeto Unity;
- manter uma nota de crédito em docs/ATTRIBUTIONS.md;
- manter licenças quando necessário.
```

---

## 6. Componentes principais

### 6.1 Módulo SUMO/Python

Responsabilidade:

```text
- iniciar o SUMO;
- controlar o clock da simulação;
- avançar a simulação passo a passo;
- extrair estado dos veículos;
- extrair estado dos semáforos;
- aplicar comandos semafóricos;
- coletar ground truth para avaliação.
```

Arquivo principal:

```text
python/sumo/traci_client.py
```

Funções esperadas:

```python
class SumoClient:
    def __init__(self, sumo_binary: str, config_path: str, gui: bool = True):
        pass

    def start(self) -> None:
        pass

    def step(self) -> float:
        """Avança um passo da simulação e retorna o tempo simulado."""
        pass

    def close(self) -> None:
        pass

    def get_vehicle_state(self) -> list[dict]:
        pass

    def get_traffic_light_state(self, tls_id: str) -> dict:
        pass

    def set_traffic_light_phase(self, tls_id: str, phase: int) -> None:
        pass

    def set_traffic_light_phase_duration(self, tls_id: str, duration: float) -> None:
        pass
```

Importante: iniciar o SUMO sem `--num-clients 2`.

---

### 6.2 Módulo de extração de estado para Unity

Arquivo:

```text
python/sumo/state_extractor.py
```

Responsabilidade:

```text
- converter estado do SUMO para mensagem serializável;
- converter coordenadas SUMO para coordenadas Unity;
- incluir step_id e sim_time;
- incluir veículos ativos;
- incluir estado semafórico.
```

Observação arquitetural:

```text
o estado enviado pelo Python é global para o step;
a Unity é responsável por renderizar esse estado nas quatro câmeras;
o Python continua sendo o orquestrador do avanço da simulação.
```

Formato de mensagem Python → Unity:

```json
{
  "step": 123,
  "sim_time": 12.3,
  "vehicles": [
    {
      "id": "veh0",
      "x": 15.2,
      "y": 0.0,
      "z": 32.8,
      "angle": 90.0,
      "speed": 4.7,
      "type": "passenger"
    }
  ],
  "traffic_lights": [
    {
      "id": "center_tls",
      "phase": 0,
      "state": "GGrr"
    }
  ]
}
```

---

### 6.3 Módulo de comunicação Python ↔ Unity

Arquivos:

```text
python/bridge/unity_comm.py
python/bridge/protocol.py
```

Responsabilidade:

```text
- enviar estado do SUMO para Unity;
- receber frames das câmeras Unity;
- validar step_id;
- validar camera_id;
- medir latência;
- tratar timeout;
- descartar frames atrasados.
```

Implementação inicial recomendada:

```text
Python → Unity: UDP com JSON
Unity → Python: TCP com frame JPG + header
```

Cada frame enviado pela Unity deve conter:

```text
- step_id;
- sim_time;
- camera_id;
- image_format;
- tamanho do payload;
- bytes JPEG.
```

Interface desejada:

```python
class UnityBridge:
    def __init__(
        self,
        state_host: str,
        state_port: int,
        frame_host: str,
        frame_port: int,
        timeout: float = 2.0,
    ):
        pass

    def send_state(self, state: dict) -> None:
        pass

    def receive_frame(self) -> tuple | None:
        """
        Retorna:
            (frame_bgr, step_id, sim_time, camera_id, latency_ms)
        ou None em caso de timeout.
        """
        pass

    def close(self) -> None:
        pass
```

Política de timeout:

```text
se um frame não chegar no tempo esperado, registrar o evento e reutilizar a
última contagem válida da câmera correspondente, sem travar a simulação inteira.
```

---

### 6.4 Módulo de visão computacional

O projeto deve reaproveitar a lógica do `car-counter`, mas reorganizada em módulos. O `car-counter` atual deve virar a camada `python/vision`.

#### Arquivo: `python/vision/yolo_detector.py`

Responsabilidade:

```text
- carregar modelo YOLO;
- executar inferência em frames da Unity;
- filtrar classes de veículos;
- aplicar limiar de confiança;
- retornar detecções em formato padronizado.
```

#### Arquivo: `python/vision/sort_tracker.py`

Responsabilidade:

```text
- adaptar o SORT do car-counter;
- receber detecções YOLO;
- retornar tracks com IDs persistentes;
- manter compatibilidade com o formato usado pelo contador de ROI.
```

Importante:

```text
o SORT é auxiliar, não requisito crítico da decisão;
trocas pontuais de ID não devem comprometer o controlador inicial;
a métrica principal continua sendo a contagem em ROI por câmera.
```

#### Arquivo: `python/vision/roi_counter.py`

Responsabilidade:

```text
- definir regiões de interesse por câmera/aproximação;
- verificar se o centro da bbox está dentro da ROI;
- contar tracks únicos por região;
- produzir contagem por câmera.
```

Ao contrário do `car-counter`, este projeto não deve contar apenas cruzamentos de linha. Para controle semafórico, a métrica principal deve ser veículos em região de fila, não veículos que já passaram.

Na arquitetura final, essas ROIs vêm de `cameras.<camera_id>.roi` no `config.yaml`. O teste atual com vídeo top-down local continua sendo apenas uma compatibilidade preliminar.

#### Arquivo: `python/vision/queue_estimator.py`

Responsabilidade:

```text
- suavizar contagens ao longo do tempo;
- reduzir ruído da detecção;
- estimar fila por câmera;
- opcionalmente considerar persistência temporal dos tracks.
```

#### Arquivo: `python/vision/visual_debug.py`

Responsabilidade:

```text
- desenhar bounding boxes;
- desenhar track IDs;
- desenhar ROIs;
- desenhar contagens;
- salvar frames de debug.
```

Observação:

```text
debug frames devem ser configuráveis e não precisam ser salvos em todos os
steps de visão durante os experimentos finais.
```

---

### 6.5 Controlador semafórico

Arquivos:

```text
python/controller/traffic_controller.py
python/controller/phase_manager.py
python/controller/policies.py
```

Responsabilidade:

```text
- receber estimativa de fila por câmera;
- agregar contagens em dois grupos principais, NS e EW;
- decidir qual direção deve receber prioridade;
- respeitar verde mínimo, verde máximo, amarelo e all-red;
- aplicar transições seguras no SUMO.
```

Não fazer troca direta de verde conflitante para outro verde conflitante. Sempre passar por amarelo e, idealmente, all-red.

Estados recomendados:

```text
NS_GREEN
NS_YELLOW
ALL_RED_AFTER_NS
EW_GREEN
EW_YELLOW
ALL_RED_AFTER_EW
```

Parâmetros iniciais:

```yaml
traffic_controller:
  min_green: 10.0
  max_green: 45.0
  yellow_duration: 3.0
  all_red_duration: 1.0
  low_demand_threshold: 0
  switch_margin: 2
```

Mapeamento explícito das fases do SUMO:

```yaml
traffic_light:
  id: "center_tls"
  phases:
    ns_green: 0
    ns_yellow: 1
    all_red_after_ns: 2
    ew_green: 3
    ew_yellow: 4
    all_red_after_ew: 5
```

Política inicial:

```text
1. Se verde mínimo ainda não foi cumprido, manter fase.
2. Se verde máximo foi atingido, iniciar transição obrigatória.
3. Se já passou do verde mínimo e a demanda atual está baixa enquanto a oposta tem demanda, iniciar transição.
4. Se a fila da direção oposta superar a fila atual por margem definida, iniciar transição.
5. Caso contrário, manter fase atual.
```

---

### 6.6 Logger e métricas

Arquivos:

```text
python/logging_utils/metrics_logger.py
python/logging_utils/run_metadata.py
```

Responsabilidade:

```text
- salvar log por step;
- salvar decisões;
- salvar contagens YOLO;
- salvar ground truth;
- salvar latência;
- salvar metadados do experimento.
```

Importante: as métricas perfeitas do SUMO podem aparecer no log, mas apenas para avaliação, não para decisão.

---

## 7. Scripts Unity

O projeto Unity deve ficar em:

```text
unity/TrafficVisionUnity/
```

Adicionar scripts próprios em:

```text
unity/TrafficVisionUnity/Assets/Scripts/TccTrafficVision/
```

Scripts sugeridos:

```text
PythonStateReceiver.cs
VehicleManager.cs
TrafficLightVisualController.cs
CameraFrameSender.cs
SimulationFrameCoordinator.cs
```

### 7.1 `CameraFrameSender.cs`

Responsabilidade:

```text
- capturar imagem da câmera virtual;
- codificar como JPG;
- enviar para Python via TCP;
- incluir step_id, sim_time e camera_id no header.
```

Regras:

```text
- não enviar frames livremente a cada Update();
- enviar frame somente após a cena ser atualizada com um novo estado;
- incluir o identificador da câmera renderizada.
```

### 7.2 `SimulationFrameCoordinator.cs`

Fluxo Unity:

```text
1. Recebe estado step N.
2. Atualiza veículos e semáforos.
3. Aguarda fim do frame/renderização, se necessário.
4. Captura as quatro câmeras.
5. Envia as imagens com step N e respectivos camera_id para Python.
```

---

## 8. Configuração central

Arquivo:

```text
python/config.yaml
```

Exemplo:

```yaml
experiment:
  scenario: "intersection_basic"
  seed: 42
  duration: 1800
  controller: "vision_adaptive"

sumo:
  config_path: "../sumo/configs/intersection.sumocfg"
  gui: true
  step_length: 0.1

unity:
  state_host: "127.0.0.1"
  state_port: 5004
  frame_host: "127.0.0.1"
  frame_port: 5005
  frame_timeout: 2.0
  frame_transport: "tcp"

cameras:
  north:
    enabled: true
    roi:
      - [100, 250]
      - [540, 250]
      - [540, 620]
      - [100, 620]
  south:
    enabled: true
    roi:
      - [100, 250]
      - [540, 250]
      - [540, 620]
      - [100, 620]
  east:
    enabled: true
    roi:
      - [100, 250]
      - [540, 250]
      - [540, 620]
      - [100, 620]
  west:
    enabled: true
    roi:
      - [100, 250]
      - [540, 250]
      - [540, 620]
      - [100, 620]

vision:
  model_path: "yolov8n.pt"
  confidence_threshold: 0.35
  inference_size: 640
  classes: [2, 3, 5, 7]
  use_tracker: true
  smoothing_window: 5
  update_every_steps: 5

traffic_light:
  id: "center_tls"
  phases:
    ns_green: 0
    ns_yellow: 1
    all_red_after_ns: 2
    ew_green: 3
    ew_yellow: 4
    all_red_after_ew: 5

traffic_controller:
  min_green: 10.0
  max_green: 45.0
  yellow_duration: 3.0
  all_red_duration: 1.0
  low_demand_threshold: 0
  switch_margin: 2

logging:
  output_dir: "../results/logs"
  debug_frame_dir: "../results/frames"
  save_debug_frames: true
  save_every_n_vision_steps: 10
```

Observações:

```text
- os valores acima são placeholders;
- as ROIs reais serão calibradas depois com frames das câmeras da Unity;
- a seed do experimento deve ser fixa para permitir comparações reprodutíveis;
- o teste top-down atual continua apenas como validação preliminar da pipeline de visão.
```

---

## 9. `main.py` esperado

Responsabilidade:

```text
- carregar config;
- iniciar SUMO;
- iniciar comunicação com Unity;
- iniciar YOLO e SORT;
- executar loop principal;
- salvar logs;
- fechar recursos corretamente.
```

Pseudocódigo:

```python
def main():
    config = load_config("config.yaml")

    sumo = SumoClient(...)
    unity = UnityBridge(...)
    detector = YoloVehicleDetector(...)
    tracker = VehicleTracker(...)
    roi_counters = {...}  # um por camera
    queue_estimators = {...}  # um por camera
    controller = TrafficController(...)
    logger = MetricsLogger(...)

    sumo.start()
    step = 0

    try:
        while sumo.has_pending_vehicles():
            sim_time = sumo.step()

            state = sumo.extract_state(step=step, sim_time=sim_time)
            unity.send_state(state)

            if step % config["vision"]["update_every_steps"] == 0:
                camera_counts = {}

                for camera_id in ["north", "south", "east", "west"]:
                    frame_packet = unity.receive_frame()

                    if frame_packet is None:
                        logger.log_missing_frame(step, sim_time, camera_id)
                        camera_counts[camera_id] = logger.get_last_valid_count(camera_id)
                        continue

                    frame, frame_step, frame_sim_time, camera_id, latency_ms = frame_packet

                    if frame_step != step:
                        logger.log_desync(expected=step, received=frame_step, camera_id=camera_id)
                        camera_counts[camera_id] = logger.get_last_valid_count(camera_id)
                        continue

                    detections = detector.detect(frame)
                    tracks = tracker.update(detections)
                    roi_counts = roi_counters[camera_id].count(tracks)
                    queue_counts = queue_estimators[camera_id].update(roi_counts)
                    camera_counts[camera_id] = queue_counts[camera_id]

                    logger.log_vision_step(
                        step=step,
                        sim_time=sim_time,
                        camera_id=camera_id,
                        detections=detections,
                        tracks=tracks,
                        roi_counts=roi_counts,
                        queue_counts=queue_counts,
                        latency_ms=latency_ms,
                    )
            else:
                camera_counts = logger.get_last_valid_counts()

            decision = controller.update(
                sim_time=sim_time,
                visual_counts=camera_counts
            )

            controller.apply(sumo, decision)
            ground_truth = sumo.get_ground_truth_metrics()

            logger.log_step(
                step=step,
                sim_time=sim_time,
                state=state,
                decision=decision,
                ground_truth=ground_truth,
            )

            step += 1

    finally:
        sumo.close()
        unity.close()
        logger.close()
```

---

## 10. Experimentos

Criar cenários em:

```text
sumo/scenarios/
```

Cenários mínimos:

```text
balanced_flow
north_south_peak
east_west_peak
variable_peak
```

Para cada cenário, executar:

```text
1. Controle fixo.
2. Controle por YOLO + ROI (+ SORT opcional).
3. Controle idealizado por ground truth TraCI, opcional, apenas como limite superior.
```

O terceiro caso deve ser claramente documentado como baseline experimental, não como proposta principal.

---

## 11. Métricas finais

Métricas de tráfego:

```text
- tempo médio de espera;
- tempo médio de viagem;
- tamanho médio de fila;
- tamanho máximo de fila;
- número de veículos concluídos;
- throughput;
- atraso médio;
- emissões, opcional.
```

Métricas de visão:

```text
- erro absoluto médio da contagem;
- erro percentual médio da contagem;
- falsos positivos;
- falsos negativos;
- latência de inferência;
- latência total frame → decisão.
```

Métricas de controle:

```text
- número de trocas de fase;
- tempo médio em verde por direção;
- decisões por minuto;
- violações de verde mínimo ou máximo, que devem ser zero.
```

---

## 12. Ordem de implementação recomendada

### Marco 1 — Criar estrutura do repositório

Concluído.

### Marco 2 — Migrar código do `car-counter`

Concluído como pipeline preliminar de visão local.

Observação:

```text
o teste atual com vídeo/imagem local é apenas validação preliminar;
ele não substitui a futura validação em frames reais da Unity.
```

### Marco 3 — Criar cliente SUMO

Implementar:

```text
python/sumo/traci_client.py
python/sumo/state_extractor.py
```

Critério de sucesso:

```text
- Python inicia SUMO;
- Python avança simulationStep;
- Python extrai lista de veículos;
- Python extrai estado do semáforo;
- Python altera fase semafórica manualmente.
```

### Marco 4 — Criar comunicação Python → Unity

Critério de sucesso:

```text
- Python envia JSON fake;
- Unity recebe JSON;
- Unity atualiza a cena;
- step_id aparece corretamente no log da Unity.
```

### Marco 5 — Integrar SUMO → Python → Unity

Critério de sucesso:

```text
- SUMO roda;
- Python extrai veículos reais;
- Unity move veículos conforme estado recebido;
- Unity não conecta diretamente ao SUMO.
```

### Marco 6 — Criar captura Unity → Python

Critério de sucesso:

```text
- Unity captura frames das quatro câmeras;
- Unity envia frame com step_id e camera_id;
- Python recebe os frames;
- Python salva debug frames quando configurado;
- step_id recebido é igual ao step enviado.
```

### Marco 7 — YOLO nos frames da Unity

Critério de sucesso:

```text
- Python roda YOLO nos frames recebidos;
- bounding boxes são geradas;
- debug frames são salvos quando configurado;
- latência de inferência é registrada;
- a qualidade de detecção em frames sintéticos é validada cedo.
```

### Marco 8 — ROI + agregação NS/EW

Critério de sucesso:

```text
- contagem por câmera é produzida;
- ROIs são desenhadas no debug frame;
- contagem agregada NS/EW é salva no CSV;
- SORT pode ser usado como apoio sem ser dependência crítica da decisão.
```

### Marco 9 — Controlador semafórico

Critério de sucesso:

```text
- controlador recebe contagem visual;
- controlador respeita verde mínimo;
- controlador respeita amarelo;
- controlador respeita all-red;
- controlador aplica fase no SUMO.
```

### Marco 10 — Experimentos

Critério de sucesso:

```text
- rodar cenário com controle fixo;
- rodar cenário com controle por visão;
- salvar logs;
- gerar tabelas e gráficos comparativos.
```

---

## 13. Regras de implementação

Ao modificar o projeto, seguir estas regras:

```text
1. Não colocar toda a lógica em main.py.
2. Criar classes pequenas e testáveis.
3. Manter comunicação, visão, SUMO e controle em módulos separados.
4. Usar config.yaml para parâmetros.
5. Não usar dados de fila do SUMO no controlador YOLO.
6. Usar dados de fila do SUMO apenas em ground_truth.py e logs.
7. Sempre incluir `step_id` em mensagens Python ↔ Unity e incluir `camera_id` nos frames Unity → Python.
8. Nunca trocar diretamente de uma fase verde conflitante para outra.
9. Salvar logs suficientes para reproduzir experimentos.
10. Manter docstrings nos módulos principais.
11. Tratar timeouts de frame sem travar a simulação inteira.
12. Validar cedo o YOLO em frames reais renderizados pela Unity.
```

---

## 14. Checklist de validade metodológica

Antes de considerar o projeto pronto, verificar:

```text
[ ] Python é o único cliente TraCI.
[ ] Unity não chama TraCI diretamente.
[ ] A simulação opera em modo step-based, não em tempo real estrito.
[ ] Unity renderiza a partir do estado enviado pelo Python.
[ ] Existem quatro câmeras virtuais fixas: north, south, east e west.
[ ] YOLO processa frames reais da Unity.
[ ] SORT rastreia veículos entre frames.
[ ] Contagem é feita por ROI por câmera, não por sensores SUMO.
[ ] Decisão semafórica usa apenas contagem visual.
[ ] Ground truth SUMO é usado somente para avaliação.
[ ] Frames Unity → Python usam TCP com `step_id` e `camera_id`.
[ ] Timeouts de frame reutilizam a última contagem válida em vez de abortar o experimento.
[ ] Logs registram contagem visual e ground truth separadamente.
[ ] Experimentos com semáforo fixo e controle YOLO são comparáveis.
```

---

## 15. Decisão final do projeto

A direção final recomendada é:

```text
- repositório novo para o TCC;
- código do car-counter adaptado para a pasta python/vision;
- SUMO2Unity usado como base visual/importador Unity;
- Python como único cliente TraCI;
- Unity como renderizador de quatro câmeras virtuais;
- YOLO + ROI como base da decisão, com SORT como apoio opcional;
- visão executada a cada N steps simulados;
- TraCI usado para simulação, controle e avaliação, não como sensor perfeito do controlador.
```

Essa organização deixa claro que o projeto é um sistema completo de otimização semafórica baseada em visão computacional, e não apenas um contador de veículos isolado.
