# Guia de Implementação — TCC: Otimização de Tráfego com Visão Computacional, SUMO, Unity e YOLO

## 1. Introdução

Este projeto tem como objetivo desenvolver um sistema de controle semafórico adaptativo baseado em visão computacional. A proposta é simular o tráfego urbano no SUMO, renderizar esse tráfego em ambiente 3D na Unity, processar os frames da câmera virtual com YOLO + tracking e usar a estimativa visual de veículos/fila para tomar decisões de controle semafórico.

O sistema deve ser construído com a seguinte arquitetura principal:

```text
SUMO → Python/TraCI → Unity/SUMO2Unity → câmera → Python/YOLO+SORT → controlador → SUMO
```

O ponto central do projeto é que a decisão semafórica deve ser tomada a partir da imagem renderizada pela Unity, não diretamente a partir dos sensores internos do SUMO. O SUMO será usado para gerar a dinâmica do tráfego, controlar a simulação e fornecer ground truth para avaliação posterior. A Unity será usada como ambiente visual 3D. O YOLO e o SORT serão usados para detectar, rastrear e contar veículos a partir da imagem.

O projeto reaproveitará dois trabalhos existentes:

1. O repositório `car-counter`, que já contém uma implementação em Python de detecção e contagem de veículos usando YOLOv8 e SORT. O README do projeto descreve que ele detecta, rastreia e conta veículos em vídeos, usando YOLO para detecção e SORT para manter IDs de rastreamento ao longo dos frames.

2. O projeto SUMO2Unity, que fornece uma base de integração entre SUMO e Unity. O README do SUMO2Unity informa que a ferramenta importa redes viárias complexas do SUMO para Unity e programa a troca de coordenadas de veículos e informações semafóricas em intervalos de 0,10 s.

Neste projeto, o SUMO2Unity será usado principalmente como base visual/importador de cenário Unity, mas a arquitetura de controle será centralizada no Python. Isso significa que a Unity não deve ser o cliente TraCI principal. O Python deve ser o único cliente TraCI responsável por avançar a simulação, extrair o estado necessário para renderização, enviar esse estado para Unity, receber os frames da câmera e aplicar as decisões de controle no SUMO.

---

## 2. Objetivo técnico

Construir um sistema completo capaz de:

```text
1. Iniciar uma simulação SUMO.
2. Avançar a simulação passo a passo via Python/TraCI.
3. Extrair posições, rotações e estados de veículos/semaforos do SUMO.
4. Enviar esse estado para Unity.
5. Atualizar a cena 3D na Unity usando a base do SUMO2Unity.
6. Renderizar uma câmera virtual.
7. Enviar o frame da câmera de volta para Python.
8. Detectar veículos no frame usando YOLO.
9. Rastrear veículos usando SORT.
10. Estimar filas por região de interesse.
11. Tomar uma decisão semafórica.
12. Aplicar a decisão no SUMO via TraCI.
13. Salvar logs e métricas para avaliação experimental.
```

---

## 3. Decisão arquitetural principal

### 3.1 Python será o único cliente TraCI

O Python deve controlar o SUMO diretamente via TraCI. A Unity não deve conectar diretamente ao SUMO para consultar veículos ou controlar a simulação.

Fluxo correto:

```text
SUMO ←→ Python ←→ Unity
          ↓
      YOLO + SORT
          ↓
  controle semafórico
```

Fluxo que deve ser evitado neste projeto:

```text
SUMO ←→ Python
SUMO ←→ Unity
```

O motivo é reduzir a complexidade de sincronização. Com dois clientes TraCI, seria necessário garantir ordem de execução, sincronização de `simulationStep()` e correspondência exata entre o estado simulado e o frame renderizado. Para o TCC, é mais seguro e mais defensável manter o Python como orquestrador único.

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

Criar um novo repositório principal, por exemplo:

```text
tcc-traffic-cv/
```

Estrutura sugerida:

```text
tcc-traffic-cv/
│
├── README.md
├── docs/
│   ├── IMPLEMENTATION_GUIDE.md
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
│       └── batch_runner.py
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

### Observação sobre `third_party`

Não é obrigatório versionar os repositórios externos inteiros. Uma estratégia limpa é:

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

Exemplo esperado:

```python
sumo_cmd = ["sumo-gui", "-c", "sumo/configs/simulacao.sumocfg"]
traci.start(sumo_cmd)
```

Não usar:

```python
sumo_cmd = ["sumo-gui", "-c", "sumo/configs/simulacao.sumocfg", "--num-clients", "2"]
```

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

Conversão inicial sugerida:

```text
SUMO x → Unity x
SUMO y → Unity z
Unity y → 0 ou altura do veículo
```

A função de conversão deve ficar isolada para permitir ajustes posteriores de escala, offset e rotação.

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
- receber frame da câmera Unity;
- validar step_id;
- medir latência;
- tratar timeout;
- descartar frames atrasados.
```

Implementação inicial recomendada:

```text
Python → Unity: UDP com JSON
Unity → Python: UDP ou TCP com frame JPG + header
```

Para a primeira versão, usar UDP é aceitável em localhost, mas todo pacote de frame deve conter:

```text
- step_id;
- sim_time;
- tamanho do payload;
- bytes JPEG.
```

Se o frame for enviado por UDP, tomar cuidado com fragmentação. Para simplificar e aumentar robustez, é preferível usar TCP para os frames da câmera.

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
            (frame_bgr, step_id, sim_time, latency_ms)
        ou None em caso de timeout.
        """
        pass

    def close(self) -> None:
        pass
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

Interface:

```python
class YoloVehicleDetector:
    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence_threshold: float = 0.35,
        classes: list[int] | None = None,
        inference_size: int = 640,
    ):
        pass

    def detect(self, frame) -> list[dict]:
        """
        Retorna:
        [
            {
                "bbox": [x1, y1, x2, y2],
                "confidence": 0.91,
                "class_id": 2
            }
        ]
        """
        pass
```

Classes recomendadas:

```python
classes = [2, 3, 5, 7]
```

Representando, no dataset COCO usado pelo YOLO, carros, motos, ônibus e caminhões.

---

#### Arquivo: `python/vision/sort_tracker.py`

Responsabilidade:

```text
- adaptar o SORT do car-counter;
- receber detecções YOLO;
- retornar tracks com IDs persistentes;
- manter compatibilidade com o formato usado pelo contador de ROI.
```

Interface:

```python
class VehicleTracker:
    def __init__(self, max_age: int = 20, min_hits: int = 3, iou_threshold: float = 0.3):
        pass

    def update(self, detections: list[dict]) -> list[dict]:
        """
        Retorna:
        [
            {
                "track_id": 12,
                "bbox": [x1, y1, x2, y2],
                "confidence": 0.88,
                "class_id": 2
            }
        ]
        """
        pass
```

---

#### Arquivo: `python/vision/roi_counter.py`

Responsabilidade:

```text
- definir regiões de interesse por aproximação;
- verificar se o centro da bbox está dentro da ROI;
- contar tracks únicos por região;
- produzir contagem por aproximação.
```

Ao contrário do `car-counter`, este projeto não deve contar apenas cruzamentos de linha. Para controle semafórico, a métrica principal deve ser veículos em região de fila, não veículos que já passaram.

Interface:

```python
class ROICounter:
    def __init__(self, rois: dict):
        """
        rois:
        {
            "north": [[x1, y1], [x2, y2], ...],
            "south": [[x1, y1], [x2, y2], ...],
            "east": [[x1, y1], [x2, y2], ...],
            "west": [[x1, y1], [x2, y2], ...]
        }
        """
        pass

    def count(self, tracks: list[dict]) -> dict:
        """
        Retorna:
        {
            "north": 4,
            "south": 2,
            "east": 7,
            "west": 1
        }
        """
        pass
```

---

#### Arquivo: `python/vision/queue_estimator.py`

Responsabilidade:

```text
- suavizar contagens ao longo do tempo;
- reduzir ruído da detecção;
- estimar fila por aproximação;
- opcionalmente considerar persistência temporal dos tracks.
```

Interface:

```python
class QueueEstimator:
    def __init__(self, smoothing_window: int = 5):
        pass

    def update(self, roi_counts: dict) -> dict:
        """
        Retorna contagens suavizadas.
        """
        pass
```

---

#### Arquivo: `python/vision/visual_debug.py`

Responsabilidade:

```text
- desenhar bounding boxes;
- desenhar track IDs;
- desenhar ROIs;
- desenhar contagens;
- salvar frames de debug.
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
- receber estimativa de fila por aproximação;
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
  queue_threshold: 5
  imbalance_margin: 3
  cooldown: 5.0
```

Interface:

```python
class TrafficController:
    def __init__(self, tls_id: str, config: dict):
        pass

    def update(self, sim_time: float, visual_counts: dict) -> dict:
        """
        Decide ação de controle.
        Não necessariamente aplica diretamente no SUMO.
        """
        pass

    def apply(self, sumo_client, decision: dict) -> None:
        """
        Aplica decisão usando TraCI.
        """
        pass
```

Política inicial:

```text
1. Se verde mínimo ainda não foi cumprido, manter fase.
2. Se verde máximo foi atingido, iniciar transição.
3. Se a fila da direção oposta superar a fila atual por margem definida, iniciar transição.
4. Caso contrário, manter fase atual.
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

CSV por step:

```text
step
sim_time
tls_phase
tls_state
yolo_count_north
yolo_count_south
yolo_count_east
yolo_count_west
smoothed_count_north
smoothed_count_south
smoothed_count_east
smoothed_count_west
gt_queue_north
gt_queue_south
gt_queue_east
gt_queue_west
decision
frame_latency_ms
inference_latency_ms
tracking_latency_ms
control_latency_ms
vehicles_inserted
vehicles_arrived
mean_waiting_time
```

Importante: as colunas `gt_*` podem usar dados do SUMO, mas apenas para avaliação, não para decisão.

---

## 7. Scripts Unity

O projeto Unity deve ficar em:

```text
unity/TrafficVisionUnity/
```

Usar o SUMO2Unity como base porque ele já é um projeto Unity voltado à visualização 3D de redes SUMO, incluindo importação de redes, veículos e semáforos.

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

### 7.1 `PythonStateReceiver.cs`

Responsabilidade:

```text
- abrir socket para receber JSON do Python;
- desserializar estado;
- armazenar último step recebido;
- acionar atualização da cena.
```

Entrada esperada:

```json
{
  "step": 123,
  "sim_time": 12.3,
  "vehicles": [],
  "traffic_lights": []
}
```

---

### 7.2 `VehicleManager.cs`

Responsabilidade:

```text
- manter Dictionary<string, GameObject>;
- criar veículo quando aparece novo ID;
- atualizar posição e rotação;
- remover veículo que não aparece mais no estado atual;
- mapear tipo de veículo para prefab.
```

Regras:

```text
- Nunca criar duplicado para o mesmo vehicle_id.
- Se o veículo desapareceu do SUMO, remover/desativar GameObject.
- Atualizar transform somente após receber estado completo.
```

---

### 7.3 `TrafficLightVisualController.cs`

Responsabilidade:

```text
- receber estado semafórico do SUMO;
- converter caracteres r/y/g/G em luzes visuais;
- atualizar materiais ou luzes da cena.
```

Mapeamento:

```text
r → vermelho
y → amarelo
g/G → verde
```

---

### 7.4 `CameraFrameSender.cs`

Responsabilidade:

```text
- capturar imagem da câmera virtual;
- codificar como JPG;
- enviar para Python;
- incluir step_id no header.
```

Regras:

```text
- Não enviar frames livremente a cada Update().
- Enviar frame somente após a cena ser atualizada com um novo estado.
- Incluir step_id do estado renderizado.
```

Configuração inicial:

```text
resolução: 640x640
formato: JPG
qualidade: 75 ou 80
câmera: câmera fixa apontando para a interseção
```

---

### 7.5 `SimulationFrameCoordinator.cs`

Responsabilidade:

```text
- coordenar recepção de estado, atualização da cena e captura de frame;
- garantir que cada frame enviado corresponde ao step recebido;
- evitar envio duplicado de frames.
```

Fluxo Unity:

```text
1. Recebe estado step N.
2. Atualiza veículos e semáforos.
3. Aguarda fim do frame/renderização, se necessário.
4. Captura câmera.
5. Envia imagem com step N para Python.
```

---

## 8. Configuração central

Criar:

```text
python/config.yaml
```

Exemplo:

```yaml
sumo:
  config_path: "../sumo/configs/simulacao.sumocfg"
  gui: true
  step_length: 0.1
  tls_id: "center_tls"

unity:
  state_host: "127.0.0.1"
  state_port: 5004
  frame_host: "127.0.0.1"
  frame_port: 5005
  frame_timeout: 2.0

vision:
  model_path: "yolov8n.pt"
  confidence_threshold: 0.35
  inference_size: 640
  classes: [2, 3, 5, 7]
  use_tracker: true
  smoothing_window: 5

rois:
  north:
    - [100, 120]
    - [250, 120]
    - [250, 350]
    - [100, 350]
  south:
    - [390, 300]
    - [540, 300]
    - [540, 540]
    - [390, 540]
  east:
    - [300, 100]
    - [560, 100]
    - [560, 240]
    - [300, 240]
  west:
    - [80, 390]
    - [340, 390]
    - [340, 540]
    - [80, 540]

traffic_controller:
  min_green: 10.0
  max_green: 45.0
  yellow_duration: 3.0
  all_red_duration: 1.0
  queue_threshold: 5
  imbalance_margin: 3
  cooldown: 5.0

logging:
  output_dir: "../results/logs"
  save_debug_frames: true
  debug_frame_dir: "../results/frames"
```

---

## 9. `main.py` esperado

Arquivo:

```text
python/main.py
```

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
    roi_counter = ROICounter(...)
    queue_estimator = QueueEstimator(...)
    controller = TrafficController(...)
    logger = MetricsLogger(...)

    sumo.start()

    step = 0

    try:
        while sumo.has_pending_vehicles():
            sim_time = sumo.step()

            state = sumo.extract_state(step=step, sim_time=sim_time)
            unity.send_state(state)

            frame_packet = unity.receive_frame()

            if frame_packet is None:
                logger.log_missing_frame(step, sim_time)
                step += 1
                continue

            frame, frame_step, frame_sim_time, latency_ms = frame_packet

            if frame_step != step:
                logger.log_desync(expected=step, received=frame_step)
                step += 1
                continue

            detections = detector.detect(frame)
            tracks = tracker.update(detections)
            roi_counts = roi_counter.count(tracks)
            queue_counts = queue_estimator.update(roi_counts)

            decision = controller.update(
                sim_time=sim_time,
                visual_counts=queue_counts
            )

            controller.apply(sumo, decision)

            ground_truth = sumo.get_ground_truth_metrics()

            logger.log_step(
                step=step,
                sim_time=sim_time,
                state=state,
                detections=detections,
                tracks=tracks,
                roi_counts=roi_counts,
                queue_counts=queue_counts,
                decision=decision,
                ground_truth=ground_truth,
                latency_ms=latency_ms
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
2. Controle por YOLO + SORT.
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

## 12. Ordem de implementação recomendada para o Codex

### Marco 1 — Criar estrutura do repositório

Criar pastas e arquivos vazios com docstrings.

Critério de sucesso:

```text
- árvore de diretórios criada;
- README.md inicial criado;
- docs/IMPLEMENTATION_GUIDE.md criado;
- python/config.yaml criado.
```

---

### Marco 2 — Migrar código do `car-counter`

A partir do repositório `car-counter`, adaptar:

```text
- inferência YOLO;
- SORT;
- lógica de tracking;
- utilidades de desenho, se úteis.
```

O `car-counter` atual é um contador de veículos em vídeo com YOLOv8, SORT, OpenCV e visualização do resultado. Neste projeto, ele deve virar a camada `python/vision`.

Critério de sucesso:

```text
- YoloVehicleDetector funciona com uma imagem estática;
- VehicleTracker funciona com lista de detecções;
- ROICounter conta tracks dentro de polígonos;
- teste local com vídeo ou imagem salva funciona.
```

---

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

---

### Marco 4 — Criar comunicação Python → Unity

Implementar:

```text
python/bridge/unity_comm.py
unity/.../PythonStateReceiver.cs
unity/.../VehicleManager.cs
```

Critério de sucesso:

```text
- Python envia JSON fake;
- Unity recebe JSON;
- Unity cria/move um veículo fake;
- step_id aparece corretamente no log da Unity.
```

---

### Marco 5 — Integrar SUMO → Python → Unity

Critério de sucesso:

```text
- SUMO roda;
- Python extrai veículos reais;
- Unity move veículos conforme estado recebido;
- Unity não conecta diretamente ao SUMO.
```

---

### Marco 6 — Criar captura Unity → Python

Implementar:

```text
CameraFrameSender.cs
SimulationFrameCoordinator.cs
```

Critério de sucesso:

```text
- Unity captura frame da câmera;
- Unity envia frame com step_id;
- Python recebe frame;
- Python salva frame_000123.jpg;
- step_id recebido é igual ao step enviado.
```

---

### Marco 7 — YOLO no frame da Unity

Critério de sucesso:

```text
- Python roda YOLO no frame recebido;
- bounding boxes são geradas;
- debug frame é salvo com detecções;
- latência de inferência é registrada.
```

---

### Marco 8 — SORT + ROI

Critério de sucesso:

```text
- tracks possuem IDs estáveis;
- ROIs são desenhadas no debug frame;
- contagem por aproximação é salva no CSV.
```

---

### Marco 9 — Controlador semafórico

Critério de sucesso:

```text
- controlador recebe contagem visual;
- controlador respeita verde mínimo;
- controlador respeita amarelo;
- controlador respeita all-red;
- controlador aplica fase no SUMO.
```

---

### Marco 10 — Experimentos

Critério de sucesso:

```text
- rodar cenário com controle fixo;
- rodar cenário com controle YOLO;
- salvar logs;
- gerar tabelas e gráficos comparativos.
```

---

## 13. Regras de implementação para o Codex

Ao modificar o projeto, seguir estas regras:

```text
1. Não colocar toda a lógica em main.py.
2. Criar classes pequenas e testáveis.
3. Manter comunicação, visão, SUMO e controle em módulos separados.
4. Usar config.yaml para parâmetros.
5. Não usar dados de fila do SUMO no controlador YOLO.
6. Usar dados de fila do SUMO apenas em ground_truth.py e logs.
7. Sempre incluir step_id em mensagens Python ↔ Unity.
8. Nunca trocar diretamente de uma fase verde conflitante para outra.
9. Salvar logs suficientes para reproduzir experimentos.
10. Manter docstrings nos módulos principais.
```

---

## 14. Checklist de validade metodológica

Antes de considerar o projeto pronto, verificar:

```text
[ ] Python é o único cliente TraCI.
[ ] Unity não chama TraCI diretamente.
[ ] Unity renderiza a partir do estado enviado pelo Python.
[ ] YOLO processa frames reais da Unity.
[ ] SORT rastreia veículos entre frames.
[ ] Contagem é feita por ROI, não por sensores SUMO.
[ ] Decisão semafórica usa apenas contagem visual.
[ ] Ground truth SUMO é usado somente para avaliação.
[ ] Logs registram contagem visual e ground truth separadamente.
[ ] Experimentos com semáforo fixo e controle YOLO são comparáveis.
```

---

## 15. README inicial sugerido

O `README.md` do repositório pode começar assim:

```markdown
# TCC Traffic CV

Sistema experimental de controle semafórico adaptativo baseado em visão computacional.

O projeto integra SUMO, Unity, YOLOv8 e SORT para avaliar uma abordagem de otimização de tráfego urbano em ambiente simulado. O SUMO gera a dinâmica do tráfego, a Unity renderiza a cena 3D, o YOLO detecta veículos nos frames da câmera virtual, o SORT rastreia os veículos e um controlador semafórico toma decisões com base na estimativa visual de filas.

A decisão de controle não usa sensores perfeitos do SUMO. Os dados internos do SUMO são usados para renderização, sincronização e avaliação posterior.

## Arquitetura

SUMO → Python/TraCI → Unity/SUMO2Unity → câmera → Python/YOLO+SORT → controlador → SUMO

## Principais módulos

- `python/sumo`: integração TraCI e extração de estado.
- `python/bridge`: comunicação Python ↔ Unity.
- `python/vision`: YOLO, SORT, ROI e estimativa de fila.
- `python/controller`: política de controle semafórico.
- `python/experiments`: execução de cenários e experimentos.
- `unity`: projeto Unity baseado no SUMO2Unity.
- `sumo`: redes, rotas e configurações SUMO.
- `results`: logs, frames, vídeos e tabelas.
```

---

## 16. Primeiro prompt recomendado para o Codex

Quando você criar o repositório, pode dar este prompt ao Codex:

```text
Leia docs/IMPLEMENTATION_GUIDE.md e implemente o Marco 1.

Crie a estrutura inicial do projeto conforme o guia:
- diretórios principais;
- arquivos __init__.py;
- README.md inicial;
- python/config.yaml;
- stubs das classes principais em python/sumo, python/bridge, python/vision, python/controller e python/logging_utils.

Não implemente a lógica completa ainda.
Inclua docstrings explicando a responsabilidade de cada classe.
Garanta que o projeto Python tenha imports válidos e que `python/main.py` carregue o config.yaml e imprima uma mensagem indicando que a estrutura inicial está pronta.
```

Depois, o segundo prompt:

```text
Agora implemente o Marco 2.

Adapte a lógica do repositório car-counter para os módulos:
- python/vision/yolo_detector.py
- python/vision/sort_tracker.py
- python/vision/roi_counter.py
- python/vision/visual_debug.py

Não copie a lógica de contagem por linha como controle principal.
A contagem principal deve ser por ROI.
Mantenha SORT como tracker.
Crie um script simples de teste para rodar YOLO + SORT em uma imagem ou vídeo local.
```

---

## 17. Decisão final do projeto

A direção final recomendada é:

```text
- Repositório novo para o TCC.
- Código do car-counter adaptado para a pasta python/vision.
- SUMO2Unity usado como base visual/importador Unity.
- Python como único cliente TraCI.
- Unity como renderizador/câmera.
- YOLO + SORT como fonte da decisão.
- TraCI usado para simulação, controle e avaliação, não como sensor perfeito do controlador.
```

Essa organização deixa claro que o projeto é um sistema completo de otimização semafórica baseada em visão computacional, e não apenas um contador de veículos isolado.
