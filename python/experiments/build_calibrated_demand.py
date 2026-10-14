"""Gera ``sumo/sp/Cruzamento.calibrated.rou.xml`` a partir dos vídeos de drone.

Por aproximação, a demanda é o ``throughput_per_hour`` do SimJamCV
(``analysis_summary.txt``, travessias completas) vezes a fração de veículos
que formam fila em ``vehicles.csv``. Motos (e os "triciclos", que em SP são
motos mal classificadas) ficam de fora: andam no corredor e não ocupam a faixa.
Os rótulos de pedestre do SimJamCV não são confiáveis e também saem.
Caminhões e ônibus entram como carros.

As proporções de conversão de cada aproximação vêm da rota calibrada anterior
(``Cruzamento.calibrated-motos.rou.xml``, que contava motos como carros); só
o total de cada aproximação muda.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ElementTree

# Pasta do SimJamCV → edge de entrada no SUMO.
APPROACHES = {"DadosLeste": "E2", "DadosSul": "E3", "DadosOeste": "E6"}
KEPT_LABELS = frozenset({"car", "van", "truck", "bus"})
EXCLUDED_LABELS = frozenset({"motor", "tricycle", "pedestrian", "people"})


@dataclass(frozen=True, slots=True)
class Flow:
    flow_id: str
    from_edge: str
    to_edge: str
    rate_per_s: float


def kept_share(labels: Sequence[str]) -> float:
    """Fração dos rótulos que formam fila (carros, vans e pesados)."""
    if not labels:
        raise ValueError("Nenhum veículo rotulado.")
    unknown = set(labels) - KEPT_LABELS - EXCLUDED_LABELS
    if unknown:
        raise ValueError(f"Rótulos sem regra: {sorted(unknown)}.")
    return sum(label in KEPT_LABELS for label in labels) / len(labels)


def approach_demand(throughput_per_hour: float, labels: Sequence[str]) -> float:
    """Veículos/h da aproximação sem motos nem pedestres."""
    return float(throughput_per_hour) * kept_share(labels)


def scale_flows(flows: Iterable[Flow], totals_per_hour: Mapping[str, float]) -> list[Flow]:
    """Reescala os fluxos de cada edge de entrada para o total dado, mantendo as conversões."""
    flows = list(flows)
    current: dict[str, float] = {}
    for flow in flows:
        current[flow.from_edge] = current.get(flow.from_edge, 0.0) + flow.rate_per_s
    missing = set(current) - set(totals_per_hour)
    if missing:
        raise ValueError(f"Sem demanda medida para {sorted(missing)}.")
    return [Flow(flow.flow_id, flow.from_edge, flow.to_edge,
                 flow.rate_per_s * totals_per_hour[flow.from_edge] / 3600.0 / current[flow.from_edge]) for flow in flows]


def read_summary(folder: Path) -> dict[str, float]:
    values = {}
    for line in (folder / "analysis_summary.txt").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"\s*(throughput_per_hour|measurement_duration|total_throughput|avg_control_delay):\s*([\d.]+)", line)
        if match:
            values[match.group(1)] = float(match.group(2))  # o bloco GLOBAL METRICS vem por último
    return values


def read_labels(folder: Path) -> list[str]:
    with (folder / "vehicles.csv").open(encoding="utf-8") as handle:
        return [row["label"] for row in csv.DictReader(handle)]


def read_flows(routes: Path) -> list[Flow]:
    flows = []
    for element in ElementTree.parse(routes).getroot().iter("flow"):
        rate = re.fullmatch(r"exp\(([\d.]+)\)", element.get("period", ""))
        if rate is None:
            raise ValueError(f"Fluxo {element.get('id')} sem period=\"exp(...)\".")
        flows.append(Flow(element.get("id"), element.get("from"), element.get("to"), float(rate.group(1))))
    return flows


def routes_xml(flows: Sequence[Flow], rows: Sequence[tuple[str, str, float, float, float, float]]) -> str:
    table = "\n".join(f"       {folder:<11} {tph:7.1f} x {share:5.1%} = {demand:6.1f} veic/h -> {edge}  (v/c {vc:.2f})"
                      for folder, edge, tph, share, demand, vc in rows)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "",
        "<!-- Demanda calibrada pelos videos de drone (simjamcv/DigitalTwinsforSmartCities/SP),",
        "     gerada por python -m experiments.build_calibrated_demand.",
        "",
        "     Por aproximacao: throughput_per_hour do SimJamCV x fracao de carros, vans,",
        "     caminhoes e onibus em vehicles.csv. Motos e \"triciclos\" ficam de fora (andam",
        "     no corredor e nao formam fila); os rotulos de pedestre tambem. Pesados entram",
        "     como carros. v/c com o plano fixo de 90 s (capacidade 1680/3280/840 veic/h):",
        "",
        table,
        "",
        "     A versao anterior contava motos como carros (Leste com v/c 1,00, contra o",
        "     atraso de 6,6 s - nivel A - medido pelo drone); ficou em",
        "     Cruzamento.calibrated-motos.rou.xml so como registro historico. As proporcoes",
        "     de conversao vem dela; so o total de cada aproximacao mudou.",
        "",
        "     Chegadas Poisson (period=\"exp(taxa)\", taxa em veic/s) e insercao realista",
        "     (departLane=\"best\" departSpeed=\"max\"), como na versao anterior. -->",
        "",
        '<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">',
    ]
    for flow in flows:
        lines.append(f'    <flow id="{flow.flow_id}" departLane="best" departSpeed="max" begin="0.00" end="3600.00" '
                     f'period="exp({flow.rate_per_s:.6f})" from="{flow.from_edge}" to="{flow.to_edge}"/>')
    lines.append("</routes>")
    return "\n".join(lines) + "\n"


CAPACITY_PER_HOUR = {"E2": 1680.0, "E3": 3280.0, "E6": 840.0}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Gera a demanda calibrada (sem motos) do cenário SP.")
    parser.add_argument("--data", type=Path, default=root / "simjamcv" / "DigitalTwinsforSmartCities" / "SP")
    parser.add_argument("--proportions", type=Path, default=root / "sumo" / "sp" / "Cruzamento.calibrated-motos.rou.xml")
    parser.add_argument("--output", type=Path, default=root / "sumo" / "sp" / "Cruzamento.calibrated.rou.xml")
    args = parser.parse_args()

    totals, rows = {}, []
    for folder, edge in APPROACHES.items():
        summary, labels = read_summary(args.data / folder), read_labels(args.data / folder)
        demand = approach_demand(summary["throughput_per_hour"], labels)
        totals[edge] = demand
        rows.append((folder, edge, summary["throughput_per_hour"], kept_share(labels), demand, demand / CAPACITY_PER_HOUR[edge]))
        print(f"approach folder={folder} edge={edge} veh_per_hour={demand:.1f} v_c={demand / CAPACITY_PER_HOUR[edge]:.2f} "
              f"drone_control_delay_s={summary.get('avg_control_delay', float('nan')):.1f}")
    args.output.write_text(routes_xml(scale_flows(read_flows(args.proportions), totals), rows), encoding="utf-8")
    print(f"calibrated_demand_complete output={args.output}")


if __name__ == "__main__":
    main()
