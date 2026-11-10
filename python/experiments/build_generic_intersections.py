"""Gera os cruzamentos sintéticos do experimento de seleção livre de fase.

Para cada cruzamento de ``INTERSECTIONS`` escreve, em ``sumo/generic/<nome>/``:

- ``<nome>.net.xml``: rede de um cruzamento semaforizado gerada pelo
  ``netconvert`` a partir de nós e arestas (aproximações de 200 m). O programa
  vem do ``--tls.layout``: ``incoming`` dá um verde por aproximação;
  ``opposites`` junta as opostas e, com faixa exclusiva de conversão à
  esquerda, acrescenta as conversões protegidas. Verdes de 30 s e conversões
  de 10 s: o tempo fixo cai nos pontos de decisão (a cada 5 s após o mínimo);
- ``<nome>.<demanda>.rou.xml`` e ``.sumocfg``: fluxos com chegadas Poisson
  (``period="exp(...)"``, como o cenário ``calibrated``) de cada entrada para
  cada saída alcançável, 20% à direita, 60% em frente e 20% à esquerda
  (renormalizado sobre as conversões existentes).

Não edite os arquivos à mão: rode este gerador.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile


APPROACHES = {"N": (0.0, 200.0), "S": (0.0, -200.0), "E": (200.0, 0.0), "W": (-200.0, 0.0)}
TURN_SHARES = {"r": 0.2, "s": 0.6, "l": 0.2}
SPEED_MPS = 13.89
HOUR_S = 3600.0


@dataclass(frozen=True, slots=True)
class IntersectionSpec:
    name: str
    layout: str
    # Aproximação -> (faixas de entrada, faixas de saída).
    lanes: dict[str, tuple[int, int]]
    # Demanda -> aproximação -> veículos por hora por faixa de entrada.
    demands: dict[str, dict[str, float]]


def _levels(main: tuple[str, ...], side: tuple[str, ...]) -> dict[str, dict[str, float]]:
    every = (*main, *side)
    return {
        "baixa": {approach: 150.0 for approach in every},
        "media": {approach: 280.0 for approach in every},
        "desbalanceada": {**{approach: 380.0 for approach in main}, **{approach: 100.0 for approach in side}},
    }


INTERSECTIONS = (
    IntersectionSpec("cruz-2x2", "incoming", {"N": (2, 2), "S": (2, 2), "E": (2, 2), "W": (2, 2)}, _levels(("E", "W"), ("N", "S"))),
    IntersectionSpec("cruz-opostas", "opposites", {"N": (1, 1), "S": (2, 2), "E": (3, 2), "W": (3, 2)}, _levels(("E", "W"), ("N", "S"))),
    IntersectionSpec("t-3", "incoming", {"S": (1, 1), "E": (2, 2), "W": (2, 2)}, _levels(("E", "W"), ("S",))),
    IntersectionSpec("t-avenida", "opposites", {"S": (1, 1), "E": (2, 2), "W": (2, 2)}, _levels(("E", "W"), ("S",))),
    # Teste: nunca usado no treino.
    IntersectionSpec("cruz-assimetrico", "opposites", {"N": (2, 2), "S": (1, 1), "E": (2, 2), "W": (3, 2)}, _levels(("W", "N"), ("E", "S"))),
)


def nodes_xml(spec: IntersectionSpec) -> str:
    lines = ['<nodes>', '    <node id="C" x="0" y="0" type="traffic_light"/>']
    for approach in spec.lanes:
        x, y = APPROACHES[approach]
        lines.append(f'    <node id="{approach}" x="{x:g}" y="{y:g}" type="priority"/>')
    return "\n".join([*lines, "</nodes>", ""])


def edges_xml(spec: IntersectionSpec) -> str:
    lines = ["<edges>"]
    for approach, (lanes_in, lanes_out) in spec.lanes.items():
        lines.append(f'    <edge id="in_{approach}" from="{approach}" to="C" numLanes="{lanes_in}" speed="{SPEED_MPS}"/>')
        lines.append(f'    <edge id="out_{approach}" from="C" to="{approach}" numLanes="{lanes_out}" speed="{SPEED_MPS}"/>')
    return "\n".join([*lines, "</edges>", ""])


def build_network(spec: IntersectionSpec, output: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        nodes, edges = Path(tmp) / "n.nod.xml", Path(tmp) / "n.edg.xml"
        nodes.write_text(nodes_xml(spec), encoding="utf-8")
        edges.write_text(edges_xml(spec), encoding="utf-8")
        subprocess.run(
            ["netconvert", "-n", str(nodes), "-e", str(edges), "--no-turnarounds", "--tls.layout", spec.layout,
             "--tls.green.time", "30", "--tls.left-green.time", "10", "--tls.yellow.time", "3", "-o", str(output)],
            check=True, capture_output=True, text=True,
        )


def movements(net_path: Path) -> dict[str, list[tuple[str, str]]]:
    """Entrada -> [(saída, direção r/s/l)] a partir das conexões da rede."""
    import sumolib

    net = sumolib.net.readNet(str(net_path))
    result: dict[str, set[tuple[str, str]]] = {}
    for edge in net.getEdges():
        if not edge.getID().startswith("in_"):
            continue
        for target, connections in edge.getOutgoing().items():
            direction = connections[0].getDirection().lower()
            if direction in TURN_SHARES:
                result.setdefault(edge.getID(), set()).add((target.getID(), direction))
    return {edge: sorted(items) for edge, items in sorted(result.items())}


def routes_xml(spec: IntersectionSpec, demand: str, moves: dict[str, list[tuple[str, str]]]) -> str:
    lines = ["<routes>", f"    <!-- Gerado por experiments.build_generic_intersections ({spec.name}, demanda {demand}). -->"]
    index = 0
    for approach, per_lane in spec.demands[demand].items():
        edge = f"in_{approach}"
        total = per_lane * spec.lanes[approach][0]
        shares = sum(TURN_SHARES[direction] for _, direction in moves[edge])
        for target, direction in moves[edge]:
            rate = total * TURN_SHARES[direction] / shares / HOUR_S
            lines.append(f'    <flow id="f_{index}" departLane="best" departSpeed="max" begin="0.00" end="{HOUR_S:.2f}" '
                         f'period="exp({rate:.6f})" from="{edge}" to="{target}"/>')
            index += 1
    return "\n".join([*lines, "</routes>", ""])


def sumocfg_xml(net: str, routes: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<configuration>\n"
        "    <input>\n"
        f'        <net-file value="{net}"/>\n'
        f'        <route-files value="{routes}"/>\n'
        "    </input>\n"
        "    <report>\n"
        '        <no-step-log value="true"/>\n'
        '        <no-warnings value="true"/>\n'
        "    </report>\n"
        "</configuration>\n"
    )


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gera os cruzamentos sintéticos da seleção livre de fase.")
    parser.add_argument("--output-dir", type=Path, default=base_dir.parent / "sumo" / "generic")
    args = parser.parse_args()
    for spec in INTERSECTIONS:
        folder = args.output_dir / spec.name
        folder.mkdir(parents=True, exist_ok=True)
        net = folder / f"{spec.name}.net.xml"
        build_network(spec, net)
        moves = movements(net)
        for demand in spec.demands:
            routes = f"{spec.name}.{demand}.rou.xml"
            (folder / routes).write_text(routes_xml(spec, demand, moves), encoding="utf-8")
            (folder / f"{spec.name}.{demand}.sumocfg").write_text(sumocfg_xml(net.name, routes), encoding="utf-8")
        print(f"intersection_built name={spec.name} layout={spec.layout} movements={sum(len(items) for items in moves.values())}")


if __name__ == "__main__":
    main()
