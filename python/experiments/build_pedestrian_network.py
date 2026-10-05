"""Gera a variante com pedestres do cenário SP a partir da rede atual.

Saídas em ``sumo/sp/`` (a rede sem pedestres não muda):

- ``Cruzamento.ped.net.xml``: calçadas e faixas de pedestre (``netconvert
  --sidewalks.guess --crossings.guess``). A geometria das faixas de veículos e
  os links 0–9 do semáforo são preservados; as travessias viram os links
  seguintes. A calçada vira a faixa 0 de cada via, então as faixas de veículos
  ganham +1 no índice (``E3_0`` → ``E3_1``).
- Programa do semáforo com as fases 0–4 atuais, 5 = verde de pedestres e
  6 = vermelho total de liberação. O Python controla a ordem; o programa
  estático só serve ao baseline legado ``run_fixed_time_baseline``.
- ``Cruzamento.ped.add.xml``: os mesmos detectores E2 nas faixas renumeradas.
- ``Cruzamento.pedestrians.rou.xml``: ``personFlow`` com chegadas Poisson entre
  as calçadas de todas as vias.
- ``Cruzamento[.calibrated].ped.sumocfg``.

Também imprime o maior percurso em "L" (duas travessias vizinhas + a esquina) e
o verde de pedestre resultante à velocidade de projeto.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import itertools
import math
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ElementTree

TLS_ID = "clusterJ0_J14_J2_J7"
PEDESTRIAN_EDGES = ("E0", "E1", "E2", "E3", "E5", "E6")
LANE_ID = re.compile(r'lane="(E\d+)_(\d+)"')


def shift_lane_ids(text: str) -> str:
    """Renumera ``lane="E3_0"`` para ``lane="E3_1"`` (a calçada ocupa a faixa 0)."""
    return LANE_ID.sub(lambda match: f'lane="{match.group(1)}_{int(match.group(2)) + 1}"', text)


def pedestrian_program(vehicle_states: Sequence[str], crossing_count: int) -> list[tuple[str, str]]:
    """Fases (nome, estado) com as travessias: vermelhas nas fases de veículos,
    verdes na fase 5 e vermelhas na liberação (fase 6)."""
    if len(vehicle_states) != 5 or crossing_count <= 0:
        raise ValueError("Esperadas as 5 fases de veículos e ao menos uma travessia.")
    width = len(vehicle_states[0])
    phases = [(f"vehicle_{index}", state + "r" * crossing_count) for index, state in enumerate(vehicle_states)]
    phases.append(("pedestrian_green", "r" * width + "G" * crossing_count))
    phases.append(("pedestrian_clearance", "r" * (width + crossing_count)))
    return phases


def pedestrian_flows(edges: Sequence[str], total_per_hour: float, end_s: float) -> list[tuple[str, str, str, float]]:
    """Um ``personFlow`` Poisson por par ordenado de vias distintas, dividindo a demanda total."""
    if total_per_hour <= 0:
        raise ValueError("A demanda de pedestres deve ser positiva.")
    pairs = [(origin, target) for origin, target in itertools.permutations(edges, 2)]
    rate_per_second = total_per_hour / 3600.0 / len(pairs)
    return [(f"ped_{origin}_{target}", origin, target, rate_per_second) for origin, target in pairs]


def flows_xml(flows: Sequence[tuple[str, str, str, float]], end_s: float) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- Gerado por python -m experiments.build_pedestrian_network. Demanda",
        "     sintética (o drone não mediu pedestres): chegadas Poisson entre as",
        "     calçadas de todas as vias, divididas igualmente entre os pares. -->",
        '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">',
    ]
    for flow_id, origin, target, rate in flows:
        lines.append(f'    <personFlow id="{flow_id}" begin="0.00" end="{end_s:.2f}" period="exp({rate:.6f})" '
                     f'departPos="random">')
        lines.append(f'        <walk from="{origin}" to="{target}" arrivalPos="random"/>')
        lines.append("    </personFlow>")
    lines.append("</routes>")
    return "\n".join(lines) + "\n"


def sumocfg(net: str, routes: Sequence[str], additional: str, comment: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n\n'
        f"<!-- {comment} -->\n\n"
        '<sumoConfiguration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">\n\n'
        "    <input>\n"
        f'        <net-file value="{net}"/>\n'
        f'        <route-files value="{",".join(routes)}"/>\n'
        f'        <additional-files value="{additional}"/>\n'
        "    </input>\n\n"
        "</sumoConfiguration>\n"
    )


def l_paths(net_path: Path) -> list[tuple[str, str, float]]:
    """Comprimento de cada "L": travessia + caminho na esquina + travessia vizinha.

    Duas travessias são vizinhas quando se ligam pela mesma área de espera
    (walking area) de uma esquina; o caminho na esquina é a menor distância
    entre as pontas delas.
    """
    import sumolib

    net = sumolib.net.readNet(str(net_path), withInternal=True, withPedestrianConnections=True)
    result = []
    for walkingarea in net.getEdges(withInternal=True):
        if walkingarea.getFunction() != "walkingarea":
            continue
        linked = {edge.getID(): edge for edge in list(walkingarea.getOutgoing()) + list(walkingarea.getIncoming())
                  if edge.getFunction() == "crossing"}
        for first, second in itertools.combinations(sorted(linked.values(), key=lambda edge: edge.getID()), 2):
            ends_a, ends_b = first.getLanes()[0].getShape(), second.getLanes()[0].getShape()
            corner = min(math.dist(a, b) for a in (ends_a[0], ends_a[-1]) for b in (ends_b[0], ends_b[-1]))
            result.append((first.getID(), second.getID(), first.getLength() + corner + second.getLength()))
    if not result:
        raise ValueError("Nenhum par de travessias vizinhas encontrado na rede.")
    return result


def main() -> None:
    root = Path(__file__).resolve().parents[2] / "sumo" / "sp"
    parser = argparse.ArgumentParser(description="Gera a variante com pedestres do cenário SP.")
    parser.add_argument("--pedestrians-per-hour", type=float, default=300.0)
    parser.add_argument("--walking-speed", type=float, default=1.2, help="Velocidade de projeto (m/s) do verde de pedestre.")
    parser.add_argument("--end", type=float, default=3600.0)
    args = parser.parse_args()

    source, target = root / "Cruzamento.net.xml", root / "Cruzamento.ped.net.xml"
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "ped.net.xml"
        subprocess.run(["netconvert", "-s", str(source), "--sidewalks.guess", "--crossings.guess", "--walkingareas",
                        "-o", str(raw)], check=True, capture_output=True)
        tree = ElementTree.parse(raw)
    original = ElementTree.parse(source).getroot().find(f"tlLogic[@id='{TLS_ID}']")
    tl = tree.getroot().find(f"tlLogic[@id='{TLS_ID}']")
    vehicle_states = [phase.get("state") for phase in original.findall("phase")]
    crossings = len(tl.find("phase").get("state")) - len(vehicle_states[0])
    durations = [phase.get("duration") for phase in original.findall("phase")] + ["30", "3"]
    for phase in list(tl):
        tl.remove(phase)
    for (_, state), duration in zip(pedestrian_program(vehicle_states, crossings), durations):
        ElementTree.SubElement(tl, "phase", {"duration": duration, "state": state})
    ElementTree.indent(tree, space="    ")
    tree.write(target, encoding="UTF-8", xml_declaration=True)

    (root / "Cruzamento.ped.add.xml").write_text(shift_lane_ids((root / "Cruzamento.add.xml").read_text(encoding="utf-8")),
                                                 encoding="utf-8")
    (root / "Cruzamento.pedestrians.rou.xml").write_text(
        flows_xml(pedestrian_flows(PEDESTRIAN_EDGES, args.pedestrians_per_hour, args.end), args.end), encoding="utf-8")
    for name, routes in (("Cruzamento.ped.sumocfg", "Cruzamento.rou.xml"),
                         ("Cruzamento.calibrated.ped.sumocfg", "Cruzamento.calibrated.rou.xml")):
        (root / name).write_text(sumocfg("Cruzamento.ped.net.xml", [routes, "Cruzamento.pedestrians.rou.xml"],
                                         "Cruzamento.ped.add.xml",
                                         f"Variante com pedestres de {routes} (gerada por experiments.build_pedestrian_network)."),
                                 encoding="utf-8")

    paths = l_paths(target)
    for first, second, length in paths:
        print(f"pedestrian_l first={first} second={second} length_m={length:.2f}")
    longest = max(length for *_, length in paths)
    print(f"pedestrian_network_complete crossings={crossings} longest_l_m={longest:.2f} "
          f"green_s={math.ceil(longest / args.walking_speed)} output={target}")


if __name__ == "__main__":
    main()
