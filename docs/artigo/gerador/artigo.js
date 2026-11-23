// Gera o artigo final do TCC 2 (ABNT) em .docx, no template de 2026.2 (máximo de 12 páginas com capa e referências).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, AlignmentType,
  HeadingLevel, BorderStyle, LevelFormat, ShadingType, Header, PageNumber, LineRuleType, PageBreak, TableLayoutType,
  ExternalHyperlink, UnderlineType,
} = require("docx");

const ROOT = process.argv[2];
const OUT = process.argv[3];
const FIG = path.join(ROOT, "docs", "artigo", "figuras");
const FONT = "Arial";
const BODY = 24; // 12 pt
const SMALL = 20; // 10 pt (legendas, fontes, tabelas)
const LINE15 = { line: 360, lineRule: LineRuleType.AUTO };
const TEXT_WIDTH_CM = 16; // A4 (21 cm) − 3 cm − 2 cm
const CM = 567; // DXA por cm
const PX_PER_CM = 96 / 2.54;

let figureCount = 0;
let tableCount = 0;
let chartCount = 0;

// Texto com *itálico*, **negrito** e [link](url) simples. O link sai azul e sublinhado,
// como o estilo padrão de hiperlink do Word; U+200B no rótulo deixa a URL quebrar a linha.
function runs(text, opts = {}) {
  const parts = text.split(/(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|\*[^*]+\*)/).filter(Boolean);
  return parts.map((part) => {
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      return new ExternalHyperlink({
        link: link[2],
        children: [new TextRun({ text: link[1], font: FONT, size: opts.size || BODY, color: "0563C1", underline: { type: UnderlineType.SINGLE, color: "0563C1" } })],
      });
    }
    if (part.startsWith("**")) return new TextRun({ text: part.slice(2, -2), bold: true, font: FONT, size: opts.size || BODY });
    if (part.startsWith("*")) return new TextRun({ text: part.slice(1, -1), italics: true, font: FONT, size: opts.size || BODY });
    return new TextRun({ text: part, font: FONT, size: opts.size || BODY, bold: opts.bold });
  });
}

const p = (text, opts = {}) => new Paragraph({
  children: runs(text, opts),
  alignment: opts.align || AlignmentType.JUSTIFIED,
  // Como no template do TCC 2: sem recuo de primeira linha e sem espaço entre parágrafos.
  spacing: { ...LINE15, before: 0, after: opts.after ?? 0 },
});

const bullet = (text) => new Paragraph({
  children: runs(text),
  alignment: AlignmentType.JUSTIFIED,
  numbering: { reference: "bullets", level: 0 },
  spacing: { ...LINE15, after: 0 },
});

// Seção primária: uma linha em branco (1,5) antes, como no template; a primeira da página não tem.
const h1 = (text, opts = {}) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: opts.first ? { before: 0 } : undefined, children: [new TextRun({ text, font: FONT, size: BODY, bold: true })] });
const h2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text, font: FONT, size: BODY, bold: true })] });

function pngSize(file) {
  const buf = fs.readFileSync(file);
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20), buf };
}

const caption = (label, title) => new Paragraph({
  children: [new TextRun({ text: `${label} — `, font: FONT, size: SMALL, bold: true }), new TextRun({ text: title, font: FONT, size: SMALL })],
  alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60 },
});
const source = (text = "Fonte: Autores.") => new Paragraph({
  children: [new TextRun({ text, font: FONT, size: SMALL })], alignment: AlignmentType.CENTER, spacing: { before: 60, after: 200 },
});

function figure(file, title, widthCm = 15, note) {
  figureCount += 1;
  const { width, height, buf } = pngSize(path.join(FIG, file));
  const w = widthCm * PX_PER_CM;
  return [
    caption(`Figura ${figureCount}`, title),
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, children: [new ImageRun({ type: "png", data: buf, transformation: { width: Math.round(w), height: Math.round((w * height) / width) } })] }),
    source(note ? `Fonte: Autores. ${note}` : "Fonte: Autores."),
  ];
}

function placeholderFigure(title, instruction) {
  figureCount += 1;
  return [
    caption(`Figura ${figureCount}`, title),
    new Paragraph({
      alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 200, after: 200 },
      border: { top: { style: BorderStyle.DASHED, size: 6, color: "999999" }, bottom: { style: BorderStyle.DASHED, size: 6, color: "999999" } },
      children: [new TextRun({ text: `[INSERIR: ${instruction}]`, font: FONT, size: SMALL, color: "C00000", bold: true })],
    }),
    source(),
  ];
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };

// Tabela no estilo IBGE/ABNT: bordas só em cima, embaixo do cabeçalho e no fim; sem laterais.
function table(kind, title, header, rows, widthsCm, note) {
  if (kind === "Tabela") tableCount += 1; else chartCount += 1;
  const label = `${kind} ${kind === "Tabela" ? tableCount : chartCount}`;
  const widths = widthsCm.map((c) => Math.round(c * CM));
  const total = widths.reduce((a, b) => a + b, 0);
  const isQuadro = kind === "Quadro";
  const cell = (text, i, isHeader, last) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    shading: isHeader ? { type: ShadingType.CLEAR, color: "auto", fill: "F2F2F2" } : undefined,
    borders: isQuadro
      ? { top: border, left: border, bottom: border, right: border }
      : { top: isHeader ? border : none, left: none, bottom: isHeader || last ? border : none, right: none },
    children: [new Paragraph({ alignment: i === 0 ? AlignmentType.LEFT : AlignmentType.CENTER, keepNext: true, children: runs(text, { size: SMALL, bold: isHeader }) })],
  });
  return [
    caption(label, title),
    new Table({
      width: { size: total, type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED, alignment: AlignmentType.CENTER,
      rows: [
        new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, i, true, false)) }),
        ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false, ri === rows.length - 1)) })),
      ],
    }),
    source(note ? `Fonte: Autores. ${note}` : "Fonte: Autores."),
  ];
}

const coverLine = (label, value) => new Paragraph({
  children: [new TextRun({ text: `${label}: `, font: FONT, size: BODY, bold: true }), new TextRun({ text: value, font: FONT, size: BODY })],
  alignment: AlignmentType.JUSTIFIED,
  spacing: { ...LINE15, after: 360 },
});

const ref = (text) => new Paragraph({ children: runs(text), alignment: AlignmentType.LEFT, spacing: { line: 240, lineRule: LineRuleType.AUTO, after: 240 } });

// ---------------------------------------------------------------- conteúdo
const cover = [
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "CENTRO UNIVERSITÁRIO DO INSTITUTO MAUÁ DE TECNOLOGIA", font: FONT, size: BODY, bold: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 }, children: [new TextRun({ text: "Ciência da Computação", font: FONT, size: BODY, bold: true })] }),
  coverLine("TÍTULO", "Aplicação de IA na Otimização Adaptativa de Semáforos Inteligentes"),
  coverLine("CATEGORIA", "Concluído"),
  coverLine("ÁREA", "Ciências Exatas e da Terra"),
  coverLine("SUBÁREA", "Computação e Informática"),
  coverLine("INSTITUIÇÃO", "Centro Universitário do Instituto Mauá de Tecnologia – IMT"),
  coverLine("AUTOR(ES)", "Vinícius Matias Varella, Gabriel Fachini Xavier, Pedro Barboza Robles Guerra e Henrique Lin Ye"),
  coverLine("ORIENTADOR(ES)", "Prof. Alexsander Tressino de Carvalho, Prof. Jhonny Frank Sousa Joca e Prof. Antonio Sergio Ferreira Bonato"),
  new Paragraph({ children: [new PageBreak()] }),
];

const body = [
  h1("Resumo", { first: true }),
  p("Este trabalho apresenta o TraffIQ, um sistema de controle semafórico adaptativo baseado em visão computacional e aprendizado por reforço profundo, avaliado em um cruzamento real de São Paulo. A demanda foi medida por filmagem aérea com drone e reproduzida no simulador SUMO (*Simulation of Urban MObility*); um gêmeo digital no Unity gera as imagens de três câmeras virtuais, das quais o YOLOv8 (*You Only Look Once*) e o ByteTrack extraem filas e esperas por faixa. Um agente *Deep Q-Network* (DQN) escolhe o próximo estágio verde sob uma camada de segurança que inclui um estágio exclusivo de pedestres e prioridade para veículos de emergência. Propõe-se um modelo global, com pesos compartilhados entre os estágios, que controla cruzamentos com diferentes números de faixas e de estágios (até 8) sem novo treino e foi treinado apenas em cruzamentos sintéticos. Decidindo pelas câmeras, ele reduziu a espera média no cruzamento estudado em 29% em relação ao tempo fixo com o estágio de pedestres (21,2 s para 15,1 s) e em 64% sem ele (13,2 s para 4,7 s). Com a percepção *ground truth* (posições exatas do simulador), em dez repetições, as reduções foram de 29,5% (21,1 s para 14,9 s), contra 28,7 s do *max-pressure*, e de 66% (13,0 s para 4,4 s). Em um cruzamento nunca visto no treino, obteve espera menor que a do *max-pressure* em três de seis cenários, sem diferença significativa em dois e maior em um."),
  p("**Palavras-chave:** Controle semafórico adaptativo. Aprendizado por reforço. Visão computacional. Gêmeo digital. Generalização."),

  h1("Abstract"),
  p("This work presents TraffIQ, an adaptive traffic signal control system based on computer vision and deep reinforcement learning, evaluated at a real intersection in São Paulo, Brazil. Traffic demand was measured from aerial drone footage and reproduced in the SUMO (Simulation of Urban MObility) simulator; a digital twin in Unity renders the images of three virtual cameras, from which YOLOv8 (You Only Look Once) and ByteTrack extract per-lane queues and waiting times. A Deep Q-Network (DQN) agent chooses the next green stage under a safety layer that includes an exclusive pedestrian stage and priority for emergency vehicles. This work proposes a global model, with weights shared across stages, that controls intersections with different numbers of lanes and stages (up to 8) without retraining and was trained only on synthetic intersections. Deciding from the cameras, it reduced the mean waiting time at the studied intersection by 29% relative to fixed-time control with the pedestrian stage (21.2 s to 15.1 s) and by 64% without it (13.2 s to 4.7 s). With ground-truth perception (exact simulator positions), over ten runs, the reductions were 29.5% (21.1 s to 14.9 s), against 28.7 s for max-pressure, and 66% (13.0 s to 4.4 s). At an intersection never seen in training, it outperformed max-pressure in three of six scenarios, performed equivalently in two and underperformed in one."),
  p("**Keywords:** Adaptive traffic signal control. Reinforcement learning. Computer vision. Digital twin. Generalization."),

  h1("1. Introdução"),
  p("São Paulo enfrenta desafios de mobilidade: os motoristas perdem mais de 130 horas por ano em congestionamentos (TOMTOM, 2025), com custo econômico-social estimado em R$ 77,7 bilhões (KALAF, 2020). Ainda assim, são comuns os planos de tempo fixo, que não se ajustam à demanda."),
  p("No Aprendizado por Reforço (*Reinforcement Learning* – RL), um agente aprende uma política pela interação com o ambiente, guiado por recompensas (SUTTON; BARTO, 2018). O *Deep Q-Network* (DQN) combina redes neurais profundas e *Q-learning* (MNIH et al., 2015), e o *Double DQN* reduz a superestimação dos valores de ação (VAN HASSELT; GUEZ; SILVER, 2016). O DQN já foi aplicado a cruzamentos isolados (GENDERS; RAZAVI, 2016) e à cooperação entre cruzamentos (WEI et al., 2019). Uma referência clássica sem aprendizado é o *max-pressure* (VARAIYA, 2013), que dá o verde ao estágio com maior pressão de filas."),
  p("Duas limitações são recorrentes: o modelo permanece restrito ao cruzamento de treino, pois o estado tem uma posição fixa para cada faixa, o que representações por estágio buscam evitar (ZHENG et al., 2019; OROOJLOOY et al., 2020); e a percepção usa dados exatos do simulador, indisponíveis em campo. Este trabalho aborda ambas."),
  h2("1.1 Justificativa"),
  p("Uma solução que atue por software sobre câmeras e controladores existentes, sem obras, tende a ter custo menor que soluções com novos sensores, e um modelo que dispense novo treino em cada cruzamento facilita a implantação em larga escala. O trabalho alinha-se ao Objetivo de Desenvolvimento Sustentável 11 da ONU, Cidades e Comunidades Sustentáveis (ONU, 2015)."),

  h1("2. Objetivos"),
  h2("2.1 Objetivo Geral"),
  p("Desenvolver e avaliar um sistema de controle semafórico adaptativo baseado em visão computacional e aprendizado por reforço profundo, capaz de reduzir a espera dos veículos em um cruzamento real de São Paulo e de ser aplicado a outros cruzamentos sem novo treino."),
  h2("2.2 Objetivos Específicos"),
  bullet("Medir a demanda de um cruzamento real com drone e reproduzi-la no simulador SUMO (*Simulation of Urban MObility*);"),
  bullet("Extrair, das câmeras de um gêmeo digital no Unity, as filas e esperas por faixa com YOLOv8 (*You Only Look Once*) e ByteTrack;"),
  bullet("Treinar agentes DQN sob uma camada de segurança, com estágio de pedestres e prioridade para emergências;"),
  bullet("Propor um modelo global, independente do número de faixas e de estágios, treinado apenas em cruzamentos sintéticos;"),
  bullet("Comparar os controladores com o tempo fixo e o *max-pressure* em repetições independentes, com testes estatísticos."),

  h1("3. Metodologia"),
  p("A pesquisa é quantitativa e experimental, baseada em simulação: os controladores foram comparados no mesmo ambiente, mudando apenas a decisão do semáforo. Cada execução teve 300 s de aquecimento e 1800 s de controle. Os resultados finais usaram dez sementes (201 a 210), disjuntas das de treino e de validação; a mesma semente gerou a mesma demanda para todos os controladores, o que permitiu o teste *t* pareado, com média, intervalo de confiança de 95% (IC 95%) e valor-*p*. As métricas foram a espera média por veículo, a espera dos veículos que pararam e a fila de inserção (veículos que ainda não entraram na rede). As referências foram o tempo fixo, com 40 s de verde por estágio (o verde máximo dos adaptativos), e o *max-pressure*. O treino usou a percepção *ground truth* (posições exatas do simulador) e a espera do simulador como recompensa; a avaliação usou também as câmeras."),
  p("O SUMO (LOPEZ et al., 2018), simulador microscópico aberto, foi escolhido por ser controlado passo a passo pela interface TraCI, *Traffic Control Interface* (ECLIPSE SUMO, 2026), o que permite decidir o semáforo a cada segundo e repetir a mesma demanda para todos os controladores. O Unity gerou as imagens das câmeras; o gêmeo digital foi construído a partir do SUMO2Unity (MOHAMMADI et al., 2024), do qual se aproveitaram o importador da rede do SUMO e os recursos visuais, e a comunicação em tempo real entre o simulador, o Unity e o controlador foi desenvolvida neste trabalho. O YOLOv8 (JOCHER; CHAURASIA; QIU, 2023) foi escolhido por detectar em tempo real, e o ByteTrack (ZHANG et al., 2022) mantém a identidade dos veículos entre quadros mesmo com detecções de baixa confiança. Os agentes foram implementados com PyTorch (PASZKE et al., 2019), que facilita redes com pesos compartilhados entre estágios."),

  h1("4. Desenvolvimento e Resultados"),
  h2("4.1 Dados de campo e simulação"),
  p("O cruzamento localiza-se em Santo Amaro, São Paulo (23°39'08,6\"S, 46°43'03,0\"W). Uma filmagem aérea de 13 min foi processada com o SimJamComputerVision (ROADWAYVR, 2026), que conta e rastreia os veículos por faixa (Figura 1), e a geometria foi importada do OpenStreetMap. A demanda resultante é de 976 veículos/h no Leste, 727 no Sul e 139 no Oeste, com chegadas de Poisson. Foram avaliados três cenários: a demanda medida, com e sem o estágio de pedestres, e uma demanda equilibrada."),
  p("O semáforo tem dois estágios verdes, Leste/Oeste e Sul. Uma camada de segurança executa todas as decisões e impõe verde mínimo de 10 s e máximo de 40 s, amarelo de 3 s e vermelho geral de 1 s. No cenário com pedestres, um estágio exclusivo (7 s de verde e 11 s de liberação, com todos os veículos no vermelho) ocorre após cada verde do Sul. Os veículos de emergência, neste trabalho chamados de viaturas, avisam o controlador da aproximação e do tempo de chegada (V2I, *vehicle-to-infrastructure*) e também são detectadas pelas câmeras; enquanto têm prioridade, o verde delas é mantido sem consultar a política."),
  h2("4.2 Gêmeo digital e percepção visual"),
  p("O controlador, em Python, é o único cliente do SUMO (Figura 2). A cada passo, envia o estado da simulação ao Unity, que renderiza a cena e devolve as imagens de três câmeras. Em cada imagem, o detector localiza os veículos, o rastreador os acompanha e uma homografia projeta cada um sobre sua faixa, dentro de uma região de interesse de 60 m antes da linha de retenção (Figura 3). O detector foi ajustado com 18.000 imagens sintéticas rotuladas automaticamente, em duas classes (veículo e veículo de emergência), e atingiu, na validação, mAP50 de 0,995 (*mean Average Precision* com sobreposição mínima de 50%). A Figura 4 mostra o cruzamento reproduzido no gêmeo digital."),
  ...figure("fig-drone-simjamcv.png", "Exemplo da análise do vídeo aéreo no SimJamComputerVision", 13),
  ...figure("fig-arquitetura.png", "Arquitetura do sistema", 11),
  ...figure("fig-carros-camera-yolo.png", "Detecções e regiões de interesse por faixa na câmera Sul do gêmeo digital", 10),
  ...figure("fig-cruzamento-unity.png", "Cruzamento estudado no gêmeo digital (Unity)", 11),
  h2("4.3 Modelos especialista e global"),
  p("O desenvolvimento foi incremental: uma prova de conceito com os detectores do simulador, uma regra de fila e agentes DQN alimentados pelas câmeras. O resultado é o modelo especialista, que descreve cada uma das 7 faixas por contagem, veículos parados, ocupação, velocidade e espera, escolhe entre manter ou trocar o verde e funciona apenas no cruzamento de treino."),
  p("O modelo global trata a decisão como uma escolha entre estágios, lidos automaticamente do programa semafórico da rede com as faixas que cada um libera. Cada estágio é descrito por 21 atributos: a demanda das suas faixas e a do estágio atual, o tempo de verde decorrido, o tempo no vermelho e o tempo perdido para entrar e sair do estágio (amarelo, vermelho geral e, quando houver, o estágio de pedestres)."),
  p("Uma mesma rede φ (duas camadas de 64 neurônios) codifica cada estágio (Figura 5); a média e o máximo das codificações resumem o cruzamento, e cada estágio recebe um valor Q(p) = V(s) + A(p, s) − Ā(s), na forma *dueling* (WANG et al., 2016). Abre-se o estágio válido de maior valor, e escolher o atual equivale a mantê-lo. Como os pesos são compartilhados e o resumo não depende da ordem, à maneira de *Deep Sets* (ZAHEER et al., 2017), os mesmos 26.306 parâmetros controlam cruzamentos de 2 a 8 estágios. Para que nenhum estágio deixe de ser atendido, um estágio com veículo parado que esteja no vermelho há mais tempo do que ficaria no pior caso do tempo fixo, com verde máximo em todos os estágios, é aberto obrigatoriamente."),
  ...figure("fig-modelo-global.png", "Arquitetura do modelo global", 10),
  p("O treino usou apenas quatro cruzamentos sintéticos, cada um com três níveis de demanda, com e sem o estágio de pedestres (24 cenários). Seguindo o *Deep Q-learning from Demonstrations* (HESTER et al., 2018), o agente partiu de demonstrações do *max-pressure* e treinou depois 480 episódios por reforço, com *Double DQN*. Nos cruzamentos sintéticos, o estágio de pedestres entra na primeira troca de verde 40 s após o anterior, intervalo escolhido pelo nível de serviço do pedestre do *Highway Capacity Manual* (TRB, 2000); atrelado a um verde veicular, ele era evitado pelo modelo. O cruzamento de São Paulo e um cruzamento de teste assimétrico, com 1 a 3 faixas por aproximação e 4 estágios, não foram usados no treino."),

  h2("4.4 Resultados no cruzamento de São Paulo"),
  p("A Figura 6 resume os três cenários com percepção *ground truth* (10 sementes, teste *t* pareado). Na demanda medida, o modelo global reduziu a espera média em 66% em relação ao tempo fixo (13,0 s para 4,4 s; p < 0,001), superou o *max-pressure* (5,2 s; p < 0,001) e ficou 0,2 s acima do especialista, treinado nesse cruzamento. Na demanda equilibrada, todos os controladores adaptativos ficaram entre 4,7 e 4,8 s."),
  ...figure("fig-resultados-sp.png", "Espera dos veículos no cruzamento de São Paulo (média e IC 95%, 10 sementes)", 12),
  p("Com o estágio de pedestres, o cenário mais próximo do cruzamento real, o modelo global reduziu a espera média em 29,5% (21,1 s para 14,9 s; p < 0,001) e a dos veículos que pararam em 42% (33,1 s para 19,0 s), sem diferença significativa para o especialista (+0,4 s; p = 0,12). O *max-pressure* decide apenas pelo número de veículos parados e não considera os 18 s com todos os veículos no vermelho a cada estágio de pedestres: escolhe momentos de troca menos eficientes, tem espera maior que a do tempo fixo (28,7 s) e deixa em média 14 veículos sem entrar na rede. Os pedestres esperaram em média 27 s, contra 60 s no tempo fixo."),
  h2("4.5 Generalização para um cruzamento não visto"),
  p("No cruzamento de teste (Figura 7), o modelo global superou o tempo fixo nos seis cenários. Em relação ao *max-pressure*, teve espera menor na demanda baixa, sem e com o estágio de pedestres, e na desbalanceada com ele (p ≤ 0,003), sem diferença significativa na média e na desbalanceada sem ele, e espera maior na média com ele (+6,2 s). Os cenários mais carregados estão perto da saturação, com veículos aguardando para entrar na rede em todos os controladores."),
  ...figure("fig-generalizacao.png", "Espera média no cruzamento de teste, nunca visto no treino (média e IC 95%, 10 sementes)", 12),
  h2("4.6 Percepção visual e emergências"),
  p("Decidindo pelas câmeras (3 sementes, limitadas pela renderização em tempo real no Unity, sem quadros perdidos), o modelo global, que nunca foi treinado com elas, manteve o desempenho: 4,71 s na demanda medida e 15,1 s com o estágio de pedestres, contra 4,54 s e 14,8 s com a percepção *ground truth* nas mesmas sementes (+0,2 s, p = 0,12, e +0,3 s, p = 0,004). Contra o tempo fixo nas mesmas sementes, a redução foi de 64% (13,2 s para 4,7 s; p < 0,001) e de 29% (21,2 s para 15,1 s; p = 0,005), e, com o estágio de pedestres, a espera dos veículos que pararam caiu 41% (33,1 s para 19,4 s). Na prioridade para emergências, também decidindo pelas câmeras, as 18 viaturas avaliadas cruzaram sem parar com o aviso V2I, com perda média de 1,5 s; sem a prioridade, apenas 7 cruzaram sem parar, com 8,9 s. Somente com a detecção visual, 17 das 18 cruzaram sem parar, com todas detectadas e nenhum alarme falso. A prioridade adia um estágio de pedestres ainda não iniciado, mas nunca interrompe uma travessia em andamento. Cada decisão leva cerca de 0,1 ms em um núcleo de processador de *notebook* (Apple M5)."),
  h2("4.7 Objetivos e comparação com a literatura"),
  p("Os cinco objetivos específicos foram atingidos: a demanda foi medida com drone e reproduzida no SUMO (seção 4.1); as câmeras do gêmeo digital forneceram filas e esperas por faixa, com espera no máximo 0,3 s maior que com a percepção *ground truth* (4.2 e 4.6); os agentes operaram sob a camada de segurança, com estágio de pedestres e prioridade para emergências (4.3 e 4.6); o modelo global, treinado apenas em cruzamentos sintéticos, controlou dois cruzamentos não vistos (4.4 e 4.5); e as comparações usaram dez repetições pareadas com teste *t* (4.4 e 4.5)."),
  p("Em relação à literatura, Genders e Razavi (2016) e Wei et al. (2019) treinam e avaliam cada modelo no mesmo cenário, com dados exatos do simulador; neste trabalho, o mesmo modelo foi avaliado em cruzamentos não vistos e decidindo pelas câmeras. Como o FRAP (ZHENG et al., 2019) e o AttendLight (OROOJLOOY et al., 2020), o modelo global descreve o cruzamento por estágio para não depender do número de faixas e de estágios; este trabalho acrescenta o estágio obrigatório de pedestres, a prioridade para emergências e a percepção visual, e disponibiliza a integração em tempo real entre SUMO, Unity e controlador, com o código aberto em [https://github.com/​ViniVarella/​tcc-traffic-cv](https://github.com/ViniVarella/tcc-traffic-cv)."),

  h1("5. Considerações Finais"),
  p("O trabalho atingiu os objetivos propostos e demonstrou, em simulação, a eficácia do TraffIQ no controle semafórico adaptativo por visão computacional e aprendizado por reforço profundo. No cruzamento estudado, decidindo pelas câmeras virtuais, o sistema reduziu a espera média dos veículos em relação ao tempo fixo em 29% com o estágio de pedestres (21,2 s para 15,1 s) e em 64% sem ele (13,2 s para 4,7 s)."),
  p("Os benefícios estenderam-se aos veículos de emergência: com a prioridade V2I, as 18 viaturas avaliadas cruzaram sem parar, com perda média de 1,5 s, ante apenas sete sem a prioridade, com 8,9 s."),
  p("A principal contribuição é o modelo global, treinado apenas em cruzamentos sintéticos e aplicável a outras configurações sem novo treino. No cruzamento real, ficou a menos de 1 s do especialista, treinado nele, e, com o estágio de pedestres, teve espera 13,8 s menor que a do *max-pressure*. Em um cruzamento não usado no treino, superou o *max-pressure* em três de seis cenários, foi estatisticamente equivalente em dois e inferior em um, o que evidencia capacidade de generalização."),
  p("As limitações são a avaliação em simulação, com imagens sintéticas; o treino com percepção *ground truth*; um único cruzamento real; e a calibração das câmeras em cada cruzamento novo, embora sem novo treino. Propõem-se testes com câmeras reais, a coordenação entre cruzamentos vizinhos e a validação em campo."),
  p("Conclui-se que o TraffIQ tem potencial para aumentar a eficiência semafórica e reduzir a espera no trânsito urbano, constituindo uma base promissora para aplicações em ambientes reais."),

  h1("Referências"),
  ref("ECLIPSE SUMO. **SUMO Documentation**. 2026. Disponível em: https://sumo.dlr.de/docs/. Acesso em: 9 mar. 2026."),
  ref("GENDERS, W.; RAZAVI, S. Using a deep reinforcement learning agent for traffic signal control. **arXiv preprint** arXiv:1611.01142, 2016. Disponível em: https://arxiv.org/abs/1611.01142. Acesso em: 2 maio 2026."),
  ref("HESTER, T. et al. Deep Q-learning from demonstrations. In: AAAI CONFERENCE ON ARTIFICIAL INTELLIGENCE, 32., 2018, New Orleans. **Anais** [...]. Palo Alto: AAAI Press, 2018. p. 3223-3230."),
  ref("JOCHER, G.; CHAURASIA, A.; QIU, J. **Ultralytics YOLOv8**. Versão 8.0.0. 2023. Disponível em: https://github.com/ultralytics/ultralytics. Acesso em: 1 out. 2026."),
  ref("KALAF, C. T. M. **O custo econômico social do congestionamento na cidade de São Paulo**. 2020. Monografia (Bacharelado em Ciências Econômicas) — Insper Instituto de Ensino e Pesquisa, São Paulo, 2020."),
  ref("LOPEZ, P. A. et al. Microscopic traffic simulation using SUMO. In: INTERNATIONAL CONFERENCE ON INTELLIGENT TRANSPORTATION SYSTEMS (ITSC), 21., 2018. **Anais** [...]. IEEE, 2018. p. 2575-2582."),
  ref("MNIH, V. et al. Human-level control through deep reinforcement learning. **Nature**, v. 518, n. 7540, p. 529-533, 2015."),
  ref("MOHAMMADI, A. et al. SUMO2Unity: an open-source traffic co-simulation tool to improve road safety. In: IEEE INTELLIGENT VEHICLES SYMPOSIUM (IV), 2024. **Anais** [...]. IEEE, 2024. p. 2523-2528."),
  ref("ONU — ORGANIZAÇÃO DAS NAÇÕES UNIDAS. **Transformando nosso mundo**: a Agenda 2030 para o Desenvolvimento Sustentável. Nova Iorque: ONU, 2015."),
  ref("OROOJLOOY, A. et al. AttendLight: universal attention-based reinforcement learning model for traffic signal control. In: ADVANCES IN NEURAL INFORMATION PROCESSING SYSTEMS, 33., 2020. **Anais** [...]. Red Hook: Curran Associates, 2020."),
  ref("PASZKE, A. et al. PyTorch: an imperative style, high-performance deep learning library. In: ADVANCES IN NEURAL INFORMATION PROCESSING SYSTEMS, 32., 2019, Vancouver. **Anais** [...]. Red Hook: Curran Associates, 2019. p. 8024-8035."),
  ref("ROADWAYVR. **SimJamComputerVision**: traffic analytics app. GitHub, 2026. Disponível em: https://github.com/RoadwayVR/SimJamComputerVision. Acesso em: 17 maio 2026."),
  ref("SUTTON, R. S.; BARTO, A. G. **Reinforcement learning**: an introduction. 2. ed. Cambridge: MIT Press, 2018."),
  ref("TOMTOM. **TomTom Traffic Index**: ranking 2025. 2025. Disponível em: https://www.tomtom.com/traffic-index/. Acesso em: 7 mar. 2026."),
  ref("TRB — TRANSPORTATION RESEARCH BOARD. **Highway Capacity Manual**. Washington, DC: National Research Council, 2000."),
  ref("VAN HASSELT, H.; GUEZ, A.; SILVER, D. Deep reinforcement learning with double Q-learning. In: AAAI CONFERENCE ON ARTIFICIAL INTELLIGENCE, 30., 2016. **Anais** [...]. Palo Alto: AAAI Press, 2016. p. 2094-2100."),
  ref("VARAIYA, P. Max pressure control of a network of signalized intersections. **Transportation Research Part C**: Emerging Technologies, v. 36, p. 177-195, 2013."),
  ref("WANG, Z. et al. Dueling network architectures for deep reinforcement learning. In: INTERNATIONAL CONFERENCE ON MACHINE LEARNING, 33., 2016, New York. **Anais** [...]. PMLR, 2016. p. 1995-2003."),
  ref("WEI, H. et al. CoLight: learning network-level cooperation for traffic signal control. In: ACM INTERNATIONAL CONFERENCE ON INFORMATION AND KNOWLEDGE MANAGEMENT, 28., 2019. **Anais** [...]. New York: ACM, 2019. p. 1913-1922."),
  ref("ZAHEER, M. et al. Deep sets. In: ADVANCES IN NEURAL INFORMATION PROCESSING SYSTEMS, 30., 2017, Long Beach. **Anais** [...]. Red Hook: Curran Associates, 2017. p. 3391-3401."),
  ref("ZHANG, Y. et al. ByteTrack: multi-object tracking by associating every detection box. In: EUROPEAN CONFERENCE ON COMPUTER VISION (ECCV), 2022, Tel Aviv. **Anais** [...]. Cham: Springer, 2022. p. 1-21."),
  ref("ZHENG, G. et al. Learning phase competition for traffic signal control. In: ACM INTERNATIONAL CONFERENCE ON INFORMATION AND KNOWLEDGE MANAGEMENT, 28., 2019. **Anais** [...]. New York: ACM, 2019. p. 1963-1972."),
];

const heading = (size, before) => ({ run: { font: FONT, size, bold: true }, paragraph: { spacing: { before, after: 0, ...LINE15 }, keepNext: true, keepLines: true } });

const doc = new Document({
  creator: "TraffIQ",
  title: "Aplicação de IA na Otimização Adaptativa de Semáforos Inteligentes",
  styles: {
    default: { document: { run: { font: FONT, size: BODY } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, ...heading(BODY, 360) },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, ...heading(BODY, 0) },
    ],
  },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "➔", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 3 * CM, left: 3 * CM, bottom: 2 * CM, right: 2 * CM } } },
    children: [...cover, ...body],
  }],
});

Packer.toBuffer(doc).then((buffer) => { fs.writeFileSync(OUT, buffer); console.log(`docx_ok ${OUT}`); });
