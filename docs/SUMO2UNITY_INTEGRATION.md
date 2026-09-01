# Integração do SUMO2Unity ao pipeline de visão e DQN

## Decisão arquitetural

O diretório `sumo2unity/SUMO2Unity-main` será usado como referência e fonte de
recursos para a renderização Unity: importador de rede SUMO, materiais, prefabs
de veículos e convenções visuais de semáforos. Ele **não** será executado como
a ponte de simulação do TCC.

O Python continua sendo o único cliente TraCI e o único componente que avança o
SUMO. A comunicação do TCC permanece:

```text
SUMO <-> Python/TraCI -> UDP/JSON -> Unity
                                      -> TCP/JPEG -> Python/visão -> DQN -> TraCI
```

Não executar a ponte `Sumo2UnityTool.exe` junto com esse fluxo. A ferramenta
original usa ZeroMQ nas portas 5556 e 5557 e também assume a coordenação do
SUMO; isso criaria duas fontes de estado e de controle.

## O que o Sumo2Unity realmente fornece

### Importação estática da rede

`RoadNetworkBuilder` lê `Sumo2Unity.net.xml` e `Sumo2Unity.poly.xml`,
desserializa os XMLs e gera:

- uma faixa como uma malha extrudada ao longo de cada `lane`;
- uma malha triangulada para cada cruzamento não interno;
- polígonos dos tipos `terrain`, `roadside`, `wood` e `residential`;
- marcações de faixa com `DecalProjector`.

O conversor aplica `Unity = (SUMO.x - netOffset.x, SUMO.z, SUMO.y -
netOffset.y)`. Para o cenário de exemplo, `netOffset` é `(0, 0)`, mas o
cenário real deve declarar e testar esse único transform de coordenadas antes
de posicionar carros e câmeras.

Árvores, prédios detalhados e semáforos não são inferidos automaticamente da
rede por esse importador. Os assets existentes podem ser colocados na cena,
mas o posicionamento e a calibração pertencem ao cenário do TCC.

### Renderização dinâmica original

A implementação original recebe mensagens de veículos e cria/atualiza prefabs
por ID. A conversão da mensagem é `Unity(x, y, z) = (position[0],
position[2], position[1])`; o `VehicleController` suaviza o movimento por
`Rigidbody`.

Os sinais são apenas uma atualização visual: para uma mensagem
`trafficlights`, procura `Junctions/<junction_id>/Head0`, `Head1`, etc. Cada
head precisa conter filhos chamados `green_light`, `yellow_light` e
`red_light`. A cena de exemplo possui o root `Junctions`, mas não gera esses
objetos a partir do XML.

## Adaptação necessária no projeto Unity do TCC

O projeto `unity/TrafficVisionUnity` já tem o receptor UDP
`PythonStateReceiver`, além de `VehicleManager` e
`TrafficLightVisualController`. A integração deve evoluir esses scripts, não
copiar `ExchangeData` ou `SimulationController` do Sumo2Unity.

1. Importar ou recriar a rede real do TCC no projeto Unity, reutilizando o
   `RoadNetworkBuilder` e os assets compatíveis.
2. Substituir os cubos de `VehicleManager` por um catálogo de prefabs, mapeado
   a `vehicle.type`, e aplicar o transform SUMO -> Unity centralizado.
3. Criar os modelos de semáforo e um mapeamento explícito entre o TLS do SUMO,
   cada índice da string de estado e cada `Head` Unity.
4. Instalar três câmeras fixas de entrada (`south`, `east`, `west`) com
   posição, rotação, resolução e ROI versionadas no cenário.
5. Depois de aplicar o estado de um `step_id`, renderizar cada câmera em
   `RenderTexture`, codificar JPEG e devolver um pacote TCP contendo
   `step_id`, `sim_time` e `camera_id`.

O emissor de frames deve esperar a atualização da cena antes de capturar. O
Python descarta frames atrasados e só usa o conjunto associado ao step que
originou a decisão. O `FrameBundleCollector` agrupa `south`, `east` e `west`
por `step_id`, preserva frames futuros em buffer e informa explicitamente as
câmeras ausentes antes de a percepção visual ser executada.

O processamento offline `python -m experiments.test_unity_vision` carrega os
JSONs de calibração, escala suas ROIs normalizadas para cada JPEG, executa
YOLO, filtra as detecções pela ROI externa, mantém um ByteTrack independente
por câmera e conta os tracks nas ROIs de faixa. Ele grava imagens anotadas e um
resumo JSONL por step. A sequência é compatível com a inferência do SimJamCV e
será comparada ao ground truth TraCI antes de alimentar qualquer DQN.

Os cubos temporários foram substituídos por prefabs de carros Alma, Elka e
Elora, copiados de forma organizada para `Assets/Art/TrafficModels/` e
instanciados por `VehicleManager`. O pipeline atual foi validado em 100 steps
nas três câmeras e também suporta a captura de máscaras de instância para
gerar dataset sintético. Um YOLOv8n foi ajustado com esse dataset e a inferência
offline usa a classe única `0` do modelo ajustado, ByteTrack e ROIs por faixa.
As comparações com E2/TraCI são diagnósticas: o E2 mede um trecho de 20 m,
enquanto a ROI operacional pode cobrir outro trecho da aproximação.

## Plano de execução acordado

### Estado atual

- O importador estático organizado para o projeto do TCC já foi iniciado em
  `SumoRoadNetworkImporter`; ele cobre faixas, cruzamentos, polígonos e o
  `netOffset` com parsing invariável à cultura.
- O cenário SP já está disponível em `sumo/sp/`: `Cruzamento.sumocfg`,
  `Cruzamento.net.xml`, `Cruzamento.rou.xml` e `Cruzamento.add.xml`. Não há
  `.poly.xml`; a primeira importação deve usar a geometria da rede.
- A rede foi copiada para os assets Unity, importada e salva em
  `Assets/Scenes/SPImport.unity`. A validação manual confirmou 22 faixas, um
  cruzamento e a câmera aérea; limpar e reconstruir a rede não duplicou objetos.
- O perfil `python/configs/sp.yaml` e o teste
  `python -m experiments.test_sp_traci` já validaram o cenário por TraCI: o
  TLS, as cinco fases e os sete detectores E2 estão acessíveis pelo Python.
- A comunicação Python -> Unity existente continua preservada. Não há ponte
  ZeroMQ nem segundo cliente TraCI no projeto do TCC.
- A sincronização SP foi validada manualmente em 2026-08-20: o Python avançou
  o SUMO via TraCI e enviou estados UDP/JSON até o `step_id` 120; a Unity
  atualizou 24--29 veículos por estado sobre a rede importada. As linhas
  tracejadas e materiais básicos agora são gerados pelo importador do TCC.
- A primeira câmera de tráfego, `south`, foi calibrada e exportada em
  `Assets/Calibration/south-calibration.json`. Para cada estado recebido, a
  Unity captura JPEG após a atualização visual e o envia por TCP ao listener
  Python com `step_id`, `sim_time` e `camera_id`; a validação manual confirmou
  o recebimento de frames correspondentes aos steps SP.

### Fase A — Cenário estático real

A importação estática de `sumo/sp/Cruzamento.net.xml` e seu alinhamento com o
estado dinâmico já foram validados no Unity. O importador do TCC gera materiais
básicos e linhas tracejadas; os prefabs completos continuam sendo um
enriquecimento futuro. Um `.poly.xml` poderá ser adicionado no futuro, mas não
bloqueia essa primeira etapa.

O importador de rede não cria automaticamente árvores, prédios ou postes. Eles
são enriquecimento visual e podem ser adicionados depois que o piso viário e a
geometria das faixas estiverem corretos.

### Fase B — Estado dinâmico renderizado

`VehicleManager` já cria e oculta veículos por ID e mostra uma geometria
temporária colorida, com marcador de frente. O próximo refinamento é escolher
prefabs por `vehicle.type` e interpolar o movimento entre os estados recebidos.
Isso substitui, no nosso projeto, apenas a parte visual de veículos do
`SimulationController` e `VehicleController` originais.

O Sumo2Unity contém prefabs e convenções para semáforos, mas não posiciona nem
cria esses objetos automaticamente a partir do XML. Como o objetivo da visão é
contar veículos, o semáforo 3D é opcional para a primeira versão: seu estado já
é controlado corretamente pelo Python/TraCI. A montagem e atualização visual
dos focos fica como item de depuração e realismo, sem bloquear as câmeras.

### Fase C — Câmeras e ROIs por calibração visual

Será criada uma ferramenta de calibração no Editor Unity, em vez de exigir
posicionamento e coordenadas feitos manualmente em código:

1. o usuário navega até a perspectiva desejada na Scene View e registra a
   posição, rotação, FOV e resolução de cada câmera de entrada (`south`,
   `east`, `west`);
2. a ferramenta mostra a imagem renderizada por aquela câmera;
3. quatro cliques definem a ROI externa da aproximação;
4. novos grupos de quatro cliques criam uma prévia de cada ROI de faixa dentro
   da ROI externa; ela só é persistida após o botão `Save Lane`;
5. até salvar, o botão direito remove o último ponto pendente para ajuste;
6. a ferramenta rejeita ROIs de faixa fora da ROI externa ou sobrepostas;
7. as coordenadas são salvas normalizadas entre `0` e `1`, para não dependerem
   da resolução escolhida.

As ROIs são regiões 2D da imagem renderizada, não volumes 3D do cenário. O
posicionamento alto ou junto ao poste de uma câmera real é suficiente para
simular seu ponto de vista; a presença visual de um semáforo no frame não é
necessária para a contagem.

A primeira entrega dessa ferramenta já existe no projeto:

- `TrafficCameraCalibration` persiste, em cada câmera, o identificador, a
  resolução, a ROI externa e as ROIs de faixa;
- `CameraRoiCalibrationWindow` alinha a câmera à `Scene View`, renderiza o
  preview por uma cópia temporária e desabilitada da câmera (sem afetar a
  câmera da cena), coleta os quatro cliques, permite desfazer o último ponto
  pendente com o botão direito e editar/remover faixas;
- a validação rejeita o clique antes de criar o ponto quando ele está fora da
  ROI principal ou dentro de outra faixa; também rejeita o quarto ponto que
  fecharia ROIs cruzadas ou sobrepostas, além de IDs duplicados; e
- a exportação JSON versionada entrega ao Python `camera_id`, resolução, pose,
  FOV, ROI externa e ROIs de faixa normalizadas.

Os testes de Edit Mode foram executados manualmente em 2026-08-19. O relatório
`unity/TestResults_20260819_133851.xml` registrou 13 testes aprovados e nenhuma
falha, incluindo a rejeição de quadriláteros com lados cruzados.

### Fase D — Frames, percepção e decisão

Após aplicar o estado de um `step_id`, a Unity renderiza as três câmeras de
entrada em
`RenderTexture`, codifica JPEG e envia cada frame via TCP com `step_id`,
`sim_time` e `camera_id`. O Python executa YOLO, filtra a ROI externa, aplica
ByteTrack e ROIs de faixa, agrega as contagens e só então decide a ação do
semáforo via TraCI.

O arquivo do modelo DQN treinado está em `models/dqn_traffic_model.keras` e
pertence ao processo Python, não à Unity. Ele será carregado uma vez no início
da execução. Como o DQN atual foi treinado com detectores E2, ele só poderá ser
usado no pipeline visual depois que o vetor de estado visual estiver definido e
o modelo tiver sido retreinado com essa mesma semântica.

## Contrato da percepção e do DQN

O script de treinamento de referência em `optimization/sp/traci8.DQN.py` usa
26 entradas: para cada um
dos sete detectores E2, quantidade de veículos, quantidade parada e ocupação,
mais a fase do semáforo em one-hot. Portanto, uma contagem visual simples não
é intercambiável com o modelo atual.

A primeira versão visual deve produzir, por aproximação/faixa:

- `vehicle_count`: detecções ou tracks dentro da ROI de fila;
- `halting_count`: tracks persistentes com velocidade visual abaixo de um
  limiar;
- `occupancy`: estimativa calibrada da fração da ROI ocupada, ou uma nova
  representação de estado que dispense essa variável.

Em seguida, o vetor visual deve ser normalizado e o DQN deve ser treinado
novamente. O modelo treinado com leituras de `traci.lanearea` não pode ser
reutilizado como se uma nova semântica de entrada fosse equivalente.

As leituras de detectores do SUMO podem permanecer em um logger de *ground
truth* para medir erro de contagem e qualidade experimental; elas não podem
alimentar a decisão online.

No cenário SP, a avaliação offline é alinhada pelo mesmo `step_id` do frame e
usa um mapeamento explícito de ROI para detector E2 no perfil
`python/configs/sp.yaml`. O log `results/ground_truth/sp-e2.jsonl` armazena
`vehicle_count`, `halting_count` e `occupancy` a cada step. O avaliador compara
somente `lane_counts` visuais com `vehicle_count`, preservando as outras duas
métricas como contexto experimental, pois elas ainda não têm estimadores
visuais semanticamente equivalentes.

Os detectores E2 do SP possuem extensão de 20 m. Uma ROI de fila maior pode
ser mais útil para a decisão, mas não é diretamente comparável ao E2; quando
for necessário isolar a qualidade da percepção, deve existir uma ROI de
avaliação separada e limitada ao mesmo trecho físico do detector.

## Limites verificados

- O exemplo distribuído em `Scenario1` não é o cenário do TCC e não possui um
  TLS controlado adequado para validar as quatro aproximações.
- O executável `Sumo2UnityTool.exe` contém a lógica Python/TraCI original; o
  arquivo `Sumo2UnityTool_combined.py` distribuído ao lado é apenas um
  cabeçalho, então essa lógica não foi adotada como dependência do TCC.
- O baseline Unity do TCC foi alinhado ao Sumo2Unity: Unity `6000.0.53f1` e
  URP `17.0.4`. Somente o editor, o manifesto e o lock de pacotes foram
  alinhados; cenas, `GraphicsSettings` e assets do Sumo2Unity continuam fora
  do projeto até serem migrados de forma explícita.

## Próximo marco técnico

Executar uma captura com os três fluxos já calibrados (`south`, `east` e
`west`) registrando, no mesmo `step_id`, os snapshots E2 de avaliação. Em
seguida, comparar a saída YOLO + ByteTrack por ROI contra essa referência e
usar as métricas resultantes para calibrar a percepção antes de compor o vetor
visual do DQN. O ramo norte é apenas saída da mão única iniciada no sul e, por
isso, não recebe câmera.
