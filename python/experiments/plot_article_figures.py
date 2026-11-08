"""Gráficos e estatísticas do artigo final (TCC 2) a partir das avaliações com 10 seeds.

Lê os JSONs de ``results/evaluation`` (percepção *ground truth*, seeds 201–210,
300 s de aquecimento e 1800 s de controle), faz o teste t pareado seed a seed
do modelo global contra cada controlador e grava:

- ``docs/artigo/figuras/*.png`` (300 dpi, largura de coluna do artigo);
- ``docs/artigo/estatisticas.json`` e ``docs/artigo/estatisticas.md``.

Rótulos descritivos: "Especialista" = DQN estado v2 (TraffIQ v5.0); "Modelo global" = TraffIQ v6.0.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from scipy import stats  # noqa: E402

# Cores por controlador (paleta categórica validada; o tempo fixo é a referência neutra).
COLORS = {"baseline": "#a3a29c", "max_pressure": "#eb6834", "v2": "#1baf7a", "global": "#2a78d6", "v1": "#eda100"}
LABELS = {"baseline": "Tempo fixo", "max_pressure": "Max-pressure", "v1": "Regra de fila (v2.0)",
          "v2": "Especialista", "global": "Modelo global"}
TEXT = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
WAIT = "mean_waiting_time_seconds"
STOPPED = "mean_waiting_time_stopped_seconds"
SP_SCENARIOS = {"calibrated": "Demanda medida", "calibrated_ped": "Medida +\npedestres",
                "original": "Demanda\nequilibrada"}
GENERIC_MAP = {"fixed_time": "baseline", "max_pressure": "max_pressure", "dqn_fase_livre": "global"}
DEMANDS = {"baixa": "Baixa", "media": "Média", "desbalanceada": "Desbalanceada"}
WIDTH_IN = 6.3  # ~16 cm, largura do texto na página A4 do template


def style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": MUTED, "axes.labelcolor": TEXT,
        "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.axisbelow": True, "legend.frameon": False, "savefig.dpi": 300, "savefig.bbox": "tight",
    })


def ci95(values: list[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if len(array) < 2:
        return float(array.mean()), 0.0
    half = stats.t.ppf(0.975, len(array) - 1) * array.std(ddof=1) / np.sqrt(len(array))
    return float(array.mean()), float(half)


def paired(candidate: list[float], reference: list[float]) -> dict[str, float]:
    """Diferença pareada (candidato − referência), IC 95% e valor-p do teste t."""
    a, b = np.asarray(candidate, float), np.asarray(reference, float)
    diff = a - b
    mean, half = ci95(list(diff))
    p_value = float(stats.ttest_rel(a, b).pvalue) if np.any(diff != 0) else 1.0
    return {"diff": mean, "ci_low": mean - half, "ci_high": mean + half, "p": p_value,
            "reduction_pct": float(100 * (b.mean() - a.mean()) / b.mean()) if b.mean() else 0.0,
            "wins": int(np.sum(diff < 0)), "n": int(len(diff))}


def sp_runs(evaluation: Path, scenario: str, model: str) -> dict[str, dict[int, dict[str, Any]]]:
    """Controladores do SP; o modelo global vem da avaliação do checkpoint ``model`` (mesmas seeds)."""
    data = json.loads((evaluation / f"versoes-{scenario}-oracle-10seeds.json").read_text(encoding="utf-8"))
    runs = {version: {int(r["seed"]): r for r in item["runs"]} for version, item in data["versions"].items()}
    current = json.loads((evaluation / f"versoes-{scenario}-oracle-10seeds-global-{model}.json").read_text(encoding="utf-8"))
    runs["global"] = {int(r["seed"]): r for r in current["versions"]["global"]["runs"]}
    return runs


def generic_runs(evaluation: Path, model: str) -> dict[str, dict[str, dict[int, dict[str, Any]]]]:
    data = json.loads((evaluation / f"fase-livre-{model}-test-10seeds.json").read_text(encoding="utf-8"))
    result: dict[str, dict[str, dict[int, dict[str, Any]]]] = {}
    for name, scenario in data["scenarios"].items():
        if not name.startswith("cruz-assimetrico"):
            continue
        result[name] = {GENERIC_MAP[p]: {int(r["seed"]): r for r in s["runs"]}
                        for p, s in scenario["policies"].items() if p in GENERIC_MAP}
    return result


def values(runs: dict[int, dict[str, Any]], metric: str, seeds: list[int]) -> list[float]:
    return [float(runs[seed][metric]) for seed in seeds]


def compare(group: dict[str, dict[int, dict[str, Any]]], references: list[str]) -> dict[str, Any]:
    seeds = sorted(group["global"])
    out: dict[str, Any] = {"seeds": seeds, "summary": {}, "paired": {}}
    for name, runs in group.items():
        out["summary"][name] = {metric: dict(zip(("mean", "ci95"), ci95(values(runs, metric, seeds))))
                                for metric in (WAIT, STOPPED, "mean_pending_vehicles") if runs[seeds[0]].get(metric) is not None}
        for metric in ("pedestrian_mean_waiting_s", "pedestrian_p90_waiting_s"):
            if runs[seeds[0]].get(metric) is not None:
                out["summary"][name][metric] = dict(zip(("mean", "ci95"), ci95(values(runs, metric, seeds))))
    for reference in references:
        if reference in group:
            out["paired"][reference] = {metric: paired(values(group["global"], metric, seeds), values(group[reference], metric, seeds))
                                        for metric in (WAIT, STOPPED)}
    return out


def bars(ax, groups: list[str], series: list[str], data: dict[str, dict[str, Any]], metric: str,
         labels: list[str], decimals: int = 1) -> None:
    width = 0.8 / len(series)
    x = np.arange(len(groups))
    for i, name in enumerate(series):
        means = [data[g]["summary"][name][metric]["mean"] if name in data[g]["summary"] else np.nan for g in groups]
        errors = [data[g]["summary"][name][metric]["ci95"] if name in data[g]["summary"] else 0 for g in groups]
        positions = x - 0.4 + width * (i + 0.5)
        ax.bar(positions, means, width * 0.92, color=COLORS[name], label=LABELS[name], zorder=2)
        ax.errorbar(positions, means, yerr=errors, fmt="none", ecolor=TEXT, elinewidth=0.7, capsize=1.8, zorder=3)
        for xpos, mean, err in zip(positions, means, errors):
            if not np.isnan(mean):
                ax.text(xpos, mean + err + 0.4, f"{mean:.{decimals}f}".replace(".", ","), ha="center", va="bottom",
                        fontsize=6, color=TEXT)
    ax.set_xticks(x, labels)
    ax.tick_params(axis="x", length=0)


def figure_sp(sp: dict[str, Any], output: Path) -> None:
    groups = list(SP_SCENARIOS)
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH_IN, 2.7))
    series = ["baseline", "max_pressure", "v2", "global"]
    for ax, metric, title in zip(axes, (WAIT, STOPPED), ("Espera média por veículo (s)", "Espera dos veículos que pararam (s)")):
        bars(ax, groups, series, sp, metric, [SP_SCENARIOS[g] for g in groups])
        ax.set_title(title, fontsize=9, color=TEXT, loc="left")
        ax.set_ylim(0, ax.get_ylim()[1] * 1.08)
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.06))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(output)
    plt.close(fig)


def figure_generic(generic: dict[str, Any], output: Path) -> None:
    order = [f"cruz-assimetrico/{d}{suffix}" for suffix in ("", "+ped") for d in DEMANDS]
    labels = [f"{DEMANDS[name.split('/')[1].replace('+ped', '')]}\n{'com' if '+ped' in name else 'sem'} ped." for name in order]
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.6))
    bars(ax, order, ["baseline", "max_pressure", "global"], generic, WAIT, labels)
    ax.set_ylabel("Espera média por veículo (s)")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.22)  # espaço para a legenda acima das barras mais altas
    ax.legend(loc="upper left", ncol=3)
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def figure_training(log: Path, output: Path) -> None:
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    selections = [r for r in records if r.get("split") == "selection"]
    validation = [r for r in records if r.get("split") == "validation"]
    reference = {p: np.mean([r["metrics"][WAIT] for r in validation if r.get("policy") == p]) for p in ("fixed_time", "max_pressure")}
    dqn = [r for r in validation if r.get("policy") == "dqn"]
    per_eval = len(dqn) // len(selections)
    waits = [np.mean([r["metrics"][WAIT] for r in dqn[i * per_eval:(i + 1) * per_eval]]) for i in range(len(selections))]
    episodes = [max(s["episode"], 0) + 1 for s in selections]
    best = int(np.argmax([s["score"] for s in selections]))  # o escore é negativo; o maior é o checkpoint escolhido
    fig, ax = plt.subplots(figsize=(WIDTH_IN * 0.62, 2.4))
    for policy, name in (("fixed_time", "baseline"), ("max_pressure", "max_pressure")):
        ax.axhline(reference[policy], color=COLORS[name], linewidth=1.4, linestyle="--", zorder=1)
        ax.text(episodes[-1] + 8, reference[policy], LABELS[name], va="center", fontsize=7.5, color=TEXT)
    ax.plot(episodes, waits, color=COLORS["global"], linewidth=2, marker="o", markersize=4, zorder=3, label=LABELS["global"])
    ax.text(episodes[-1] + 8, waits[-1], "Modelo global", va="center", fontsize=7.5, color=TEXT)
    ax.scatter([episodes[best]], [waits[best]], s=70, facecolor="none", edgecolor=TEXT, linewidth=1, zorder=4)
    ax.annotate("modelo escolhido", (episodes[best], waits[best]), xytext=(0, -18), textcoords="offset points",
                ha="center", fontsize=7, color=MUTED)
    ax.set_xlabel("Episódios de treino (0 = só demonstrações)")
    ax.set_ylabel("Espera média na validação (s)")
    ax.set_xlim(-10, episodes[-1] + 10)
    ax.set_ylim(0, max(reference.values()) * 1.15)
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def figure_pedestrians(sp: dict[str, Any], output: Path) -> None:
    data = sp["calibrated_ped"]["summary"]
    series = ["baseline", "max_pressure", "v2", "global"]
    metrics = [("pedestrian_mean_waiting_s", "Espera média"), ("pedestrian_p90_waiting_s", "90% esperam até")]
    fig, ax = plt.subplots(figsize=(WIDTH_IN * 0.62, 2.4))
    x = np.arange(len(metrics))
    width = 0.8 / len(series)
    for i, name in enumerate(series):
        means = [data[name][m]["mean"] for m, _ in metrics]
        errors = [data[name][m]["ci95"] for m, _ in metrics]
        positions = x - 0.4 + width * (i + 0.5)
        ax.bar(positions, means, width * 0.92, color=COLORS[name], label=LABELS[name], zorder=2)
        ax.errorbar(positions, means, yerr=errors, fmt="none", ecolor=TEXT, elinewidth=0.7, capsize=1.8, zorder=3)
        for xpos, mean, err in zip(positions, means, errors):
            ax.text(xpos, mean + err + 1, f"{mean:.0f}", ha="center", va="bottom", fontsize=6, color=TEXT)
    ax.set_xticks(x, [label for _, label in metrics])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Espera dos pedestres (s)")
    ax.legend(loc="upper center", ncol=4, fontsize=6.5, bbox_to_anchor=(0.5, -0.12), handlelength=1.2, columnspacing=0.8)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.08)
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)


def box(ax, xy: tuple[float, float], size: tuple[float, float], text: str, color: str, bold: bool = False) -> None:
    ax.add_patch(FancyBboxPatch(xy, *size, boxstyle="round,pad=0.02,rounding_size=0.06", linewidth=1,
                                edgecolor=color, facecolor=color + "1f"))
    ax.text(xy[0] + size[0] / 2, xy[1] + size[1] / 2, text, ha="center", va="center", fontsize=6.4, color=TEXT,
            fontweight="bold" if bold else "normal", linespacing=1.3)


def arrow(ax, start: tuple[float, float], end: tuple[float, float], label: str = "", offset: float = 0.08) -> None:
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=9, linewidth=1, color=MUTED))
    if label:
        ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + offset, label, ha="center", va="bottom",
                fontsize=6, color=MUTED)


def figure_architecture(output: Path) -> None:
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")
    blue, orange, aqua, gray = COLORS["global"], COLORS["max_pressure"], COLORS["v2"], "#8a8984"
    w, h = 2.5, 1.1
    left, middle, right = 0.05, 3.75, 7.45
    box(ax, (left, 2.6), (w, h), "SUMO\nsimulação do cruzamento\n(demanda medida por drone)", gray, True)
    box(ax, (middle, 2.6), (w, h), "Unity\ngêmeo digital 3D\n(3 câmeras)", aqua, True)
    box(ax, (right, 2.6), (w, h), "YOLOv8 + ByteTrack\ndetecção e rastreamento\nde veículos", orange, True)
    box(ax, (right, 0.3), (w, h), "Atributos por faixa\n(ROIs de 60 m e\nhomografia)", orange)
    box(ax, (middle, 0.3), (w, h), "Agente DQN\nescolhe a próxima fase", blue, True)
    box(ax, (left, 0.3), (w, h), "Camada de segurança\nverde mín./máx., amarelo,\npedestres e viaturas", gray)
    arrow(ax, (left + w, 3.15), (middle, 3.15), "estado")
    arrow(ax, (middle + w, 3.15), (right, 3.15), "imagens")
    arrow(ax, (right + w / 2, 2.6), (right + w / 2, 1.4))
    arrow(ax, (right, 0.85), (middle + w, 0.85), "filas e esperas")
    arrow(ax, (middle, 0.85), (left + w, 0.85), "fase escolhida")
    arrow(ax, (left + w / 2, 1.4), (left + w / 2, 2.6))
    ax.text(left + w / 2 + 0.1, 2.0, "TraCI", fontsize=6.5, color=MUTED, va="center")
    fig.savefig(output)
    plt.close(fig)


def figure_model(output: Path) -> None:
    fig, ax = plt.subplots(figsize=(WIDTH_IN, 2.7))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.3)
    ax.axis("off")
    blue, gray, orange = COLORS["global"], "#8a8984", COLORS["max_pressure"]
    names = ["A", "B", "C"]
    for i, name in enumerate(names):
        y = 3.4 - i * 0.95
        box(ax, (0.05, y), (1.9, 0.65), f"Fase {name}\n21 atributos", gray)
        box(ax, (2.45, y), (1.6, 0.65), "rede φ\n(compartilhada)", blue)
        box(ax, (6.65, y), (1.5, 0.65), f"nota Q(fase {name})", blue)
        arrow(ax, (1.95, y + 0.32), (2.45, y + 0.32))
        arrow(ax, (4.05, y + 0.32), (6.65, y + 0.32))
        arrow(ax, (4.05, y + 0.32), (4.9, 1.0))
        arrow(ax, (8.15, y + 0.32), (8.6, 2.15))
    ax.text(1.0, 0.75, "… até 8 fases", ha="center", fontsize=7.5, color=MUTED)
    box(ax, (4.3, 0.1), (2.0, 0.85), "resumo do cruzamento\n(média e máximo)", orange)
    arrow(ax, (6.3, 0.55), (7.4, 1.5))
    box(ax, (8.6, 1.75), (1.35, 0.8), "abre a fase\nde maior nota", blue, True)
    fig.savefig(output)
    plt.close(fig)


def fmt(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def p_text(p: float) -> str:
    return "< 0,001" if p < 0.001 else fmt(p, 3)


def markdown(sp: dict[str, Any], generic: dict[str, Any]) -> str:
    lines = ["# Estatísticas do artigo (10 seeds, 201–210, percepção ground truth)", "",
             "Média [IC 95%] por controlador; teste t pareado do modelo global contra cada um "
             "(diferença negativa = modelo global espera menos).", ""]
    for title, block in [*((f"SP `{k}`", sp[k]) for k in sp), *((f"`{k}`", generic[k]) for k in generic)]:
        lines += [f"## {title}", "", "| Controlador | Espera média (s) | Espera parado (s) | Fila de inserção |", "|---|---|---|---|"]
        for name, summary in block["summary"].items():
            cells = [f"{fmt(summary[m]['mean'])} ± {fmt(summary[m]['ci95'])}" if m in summary else "—"
                     for m in (WAIT, STOPPED, "mean_pending_vehicles")]
            lines.append(f"| {LABELS[name]} | {' | '.join(cells)} |")
        lines += ["", "| Modelo global contra | Δ espera média [IC 95%] | p | Δ espera parado [IC 95%] | p | seeds em que o modelo global vence |",
                  "|---|---|---|---|---|---|"]
        for reference, result in block["paired"].items():
            w, s = result[WAIT], result[STOPPED]
            lines.append(f"| {LABELS[reference]} | {fmt(w['diff'], 2)} [{fmt(w['ci_low'], 2)}; {fmt(w['ci_high'], 2)}] | {p_text(w['p'])} | "
                         f"{fmt(s['diff'], 2)} [{fmt(s['ci_low'], 2)}; {fmt(s['ci_high'], 2)}] | {p_text(s['p'])} | {w['wins']}/{w['n']} |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Gráficos e estatísticas do artigo final.")
    parser.add_argument("--evaluation-dir", type=Path, default=root / "results" / "evaluation")
    parser.add_argument("--model", default="ped40", help="Sufixo das avaliações do modelo global (checkpoint dqn-fase-livre-<model>-best.pt).")
    parser.add_argument("--training-log", type=Path, default=root / "results" / "logs" / "dqn-fase-livre-ped40-pretrain.jsonl")
    parser.add_argument("--output-dir", type=Path, default=root / "docs" / "artigo")
    args = parser.parse_args()
    style()
    figures = args.output_dir / "figuras"
    figures.mkdir(parents=True, exist_ok=True)
    sp = {scenario: compare(sp_runs(args.evaluation_dir, scenario, args.model), ["baseline", "max_pressure", "v2", "v1"])
          for scenario in SP_SCENARIOS}
    generic = {name: compare(group, ["baseline", "max_pressure"]) for name, group in generic_runs(args.evaluation_dir, args.model).items()}
    figure_architecture(figures / "fig-arquitetura.png")
    figure_model(figures / "fig-modelo-global.png")
    figure_sp(sp, figures / "fig-resultados-sp.png")
    figure_generic(generic, figures / "fig-generalizacao.png")
    figure_training(args.training_log, figures / "fig-treino.png")
    figure_pedestrians(sp, figures / "fig-pedestres.png")
    (args.output_dir / "estatisticas.json").write_text(json.dumps({"sp": sp, "generic": generic}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.output_dir / "estatisticas.md").write_text(markdown(sp, generic) + "\n", encoding="utf-8")
    print(f"article_figures_complete output={args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
