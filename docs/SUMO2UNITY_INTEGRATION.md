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
4. Instalar quatro câmeras fixas (`north`, `south`, `east`, `west`) com
   posição, rotação, resolução e ROI versionadas no cenário.
5. Depois de aplicar o estado de um `step_id`, renderizar cada câmera em
   `RenderTexture`, codificar JPEG e devolver um pacote TCP contendo
   `step_id`, `sim_time` e `camera_id`.

O emissor de frames deve esperar a atualização da cena antes de capturar. O
Python descarta frames atrasados e só usa o conjunto associado ao step que
originou a decisão.

## Plano de execução acordado

### Estado atual

- O importador estático organizado para o projeto do TCC já foi iniciado em
  `SumoRoadNetworkImporter`; ele cobre faixas, cruzamentos, polígonos e o
  `netOffset` com parsing invariável à cultura.
- Os arquivos SUMO definitivos ainda serão fornecidos. A validação visual da
  importação depende, portanto, desse cenário real.
- A comunicação Python -> Unity existente continua preservada. Não há ponte
  ZeroMQ nem segundo cliente TraCI no projeto do TCC.

### Fase A — Cenário estático real

Quando os arquivos forem recebidos, importar no projeto Unity o `.net.xml` e,
quando houver, o `.poly.xml`; migrar somente os materiais e assets visuais
necessários do Sumo2Unity; e validar escala, orientação e `netOffset` no
cruzamento real.

O importador de rede não cria automaticamente árvores, prédios ou postes. Eles
são enriquecimento visual e podem ser adicionados depois que o piso viário e a
geometria das faixas estiverem corretos.

### Fase B — Estado dinâmico renderizado

Evoluir `VehicleManager` para escolher prefabs por `vehicle.type`, criar e
remover objetos por ID e interpolar o movimento entre os estados recebidos.
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
   posição, rotação, FOV e resolução de cada câmera (`north`, `south`, `east`,
   `west`);
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

A execução dos testes de Edit Mode permanece pendente apenas porque não há um
Unity Editor instalado no ambiente atual.

### Fase D — Frames, percepção e decisão

Após aplicar o estado de um `step_id`, a Unity renderiza as quatro câmeras em
`RenderTexture`, codifica JPEG e envia cada frame via TCP com `step_id`,
`sim_time` e `camera_id`. O Python executa YOLO, tracking e ROIs, agrega as
contagens e só então decide a ação do semáforo via TraCI.

O arquivo do modelo DQN treinado pertence ao processo Python, não à Unity. Ele
será carregado uma vez no início da execução. Como o DQN atual foi treinado com
detectores E2, ele só poderá ser usado no pipeline visual depois que o vetor de
estado visual estiver definido e o modelo tiver sido retreinado com essa mesma
semântica.

## Contrato da percepção e do DQN

O DQN atual em `optimization/SP/traci8.DQN.py` usa 26 entradas: para cada um
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

Antes de implementar o envio de imagens, importar o cenário SUMO real e
validar visualmente, para um mesmo `step_id`, o alinhamento entre pista, carro,
semáforo e a região vista por cada câmera. Esse teste elimina o maior risco de
integração: uma contagem visual correta em uma coordenada ou abordagem errada.
