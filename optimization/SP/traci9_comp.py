"""
=============================================================================
Comparacao final -- quatro controladores no cruzamento de SP
=============================================================================

Protocolo de avaliacao:

  Quatro bracos, todos no mesmo ambiente de sp_env.py:
    fixed         programa estatico do net.xml, ciclo de 90 s, intocado
    alwaysswitch  troca sempre no verde minimo (ciclo curto de duracao fixa)
    maxpressure   heuristica gulosa por fila, com custo de troca
    dqn           politica aprendida
  Os tres ultimos usam o MESMO controlador de transicoes seguras, entao todos
  pagam o mesmo amarelo e all-red.

  Por que quatro e nao dois: medido neste cenario, ganhar do tempo fixo e
  facil (185,6 -> ~146 s) porque o ciclo de 90 s e longo demais para
  aproximacoes de 68-78 m. Ja um ciclo curto de duracao FIXA chega a 133,9 s,
  melhor que as duas heuristicas adaptativas. Comparar o DQN apenas contra o
  tempo fixo inflaria o merito do aprendizado; os bracos "alwaysswitch" e
  "maxpressure" sao a regua honesta.

  Cuidado com a metrica: em cruzamento saturado, qualquer indicador medido so
  DENTRO da rede pode ser melhorado apenas impedindo veiculos de entrar. Por
  isso "Atraso total" soma time loss e atraso de insercao (departDelay). Uma
  politica pode ter o melhor time loss e a menor fila de todas e ainda assim
  ser a pior no atraso total.

  Desenho pareado: todos os bracos rodam nas MESMAS seeds, entao a variacao de
  demanda e comum e a comparacao usa as diferencas par a par.

  Metricas por veiculo vem do tripinfo do SUMO, do inicio ao fim da viagem.
  A versao anterior usava getArrivedNumber() como se fosse acumulado (era o
  numero de chegadas do ultimo step) e --time-to-teleport 60, que removia
  veiculos travados e apagava o tempo de espera deles.

  Os primeiros WARMUP_STEPS segundos ficam fora das metricas, para que nenhum
  braco seja medido durante o enchimento da rede.

Uso:
  python traci9_comp.py                            # 10 seeds, demanda 1.0
  python traci9_comp.py --seeds 20                 # mais poder estatistico
  python traci9_comp.py --demand 0.8 0.9 1.0       # varredura de demanda
  python traci9_comp.py --scenario original        # cenario de demanda antigo
  python traci9_comp.py --seeds 1 --arms dqn --gui # inspecao visual
=============================================================================
"""

import argparse
import csv
import math
import os
import sys

import numpy as np

import sp_env
from sp_env import EnvConfig, SpIntersection, max_pressure_action

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

# "alwaysswitch" (ciclar no verde minimo) entra como braco porque se mostrou
# uma baseline forte: omiti-lo inflaria artificialmente o merito do DQN.
ARMS = ("fixed", "alwaysswitch", "shortcycle", "maxpressure", "dqn")
ARM_LABEL = {"fixed": "Tempo Fixo", "alwaysswitch": "Ciclo Min",
             "shortcycle": "Ciclo Curto", "maxpressure": "Max-Press",
             "dqn": "DQN"}
ARM_COLOR = {"fixed": "steelblue", "alwaysswitch": "slategray",
             "shortcycle": "darkkhaki", "maxpressure": "seagreen",
             "dqn": "darkorange"}

# Verde do braco "shortcycle". Nao e um chute: a varredura de min_green mediu
# uma curva em U com minimo em 20 s nas tres demandas testadas (0.8/0.9/1.0),
# e 20 s bate as duas heuristicas adaptativas. E o baseline mais forte que
# existe aqui, e por isso tem de estar na tabela: um ciclo curto de duracao
# FIXA nao precisa de camera, sensor nem aprendizado.
SHORT_CYCLE_GREEN = 20

HORIZON = 3600
WARMUP_STEPS = 300
DECISION_INTERVAL = 5
MIN_GREEN_STEPS = 10
MAX_GREEN_STEPS = 60

MODEL_PATH = os.path.join(sp_env.SCRIPT_DIR, "dqn_traffic_model.keras")

# Metricas em que menor e melhor.
LOWER_IS_BETTER = {
    "mean_wait": True,
    "p90_wait": True,
    "mean_time_loss": True,
    "mean_duration": True,
    "mean_depart_delay": True,
    "mean_total_delay": True,
    "mean_queue": True,
    "teleports": True,
    "throughput_per_hour": False,
    "mean_speed": False,
    "reward": False,
}

REPORT_METRICS = (
    ("mean_wait", "Espera media por veiculo", "s"),
    ("p90_wait", "Espera no percentil 90", "s"),
    ("mean_time_loss", "Time loss medio", "s"),
    ("mean_depart_delay", "Atraso de insercao", "s"),
    ("mean_total_delay", "Atraso total (loss+insercao)", "s"),
    ("mean_duration", "Duracao media da viagem", "s"),
    ("mean_queue", "Fila media nas aproximacoes", "veic."),
    ("mean_speed", "Velocidade media", "m/s"),
    ("throughput_per_hour", "Throughput", "veic./h"),
    ("teleports", "Teleportes", "n"),
)


# =============================================================================
# Estatistica sem dependencias externas
# =============================================================================

# t critico bilateral em 95%, por graus de liberdade.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
       26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def t_crit(df):
    if df <= 0:
        return float("nan")
    if df in T95:
        return T95[df]
    return 1.96


def sign_test_p(diffs, tol=1e-9):
    """
    Teste dos sinais exato, bilateral. Nao-parametrico e sem dependencias:
    conta quantas seeds melhoraram e compara com uma binomial(n, 0.5).
    """
    pos = sum(1 for d in diffs if d > tol)
    neg = sum(1 for d in diffs if d < -tol)
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def paired_stats(base, treat, lower_is_better):
    """
    Estatistica pareada de treat contra base.

    Retorna a melhoria percentual media, o IC 95% dessa melhoria e o p-valor do
    teste dos sinais. O pareamento por seed remove a variacao de demanda, que
    e a maior fonte de ruido aqui.
    """
    base = np.asarray(base, dtype=float)
    treat = np.asarray(treat, dtype=float)
    n = len(base)
    if n == 0:
        return {}

    raw = treat - base
    improvement = -raw if lower_is_better else raw

    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(np.abs(base) > 1e-9, 100.0 * improvement / np.abs(base), 0.0)

    mean_pct = float(np.mean(pct))
    if n > 1:
        sem = float(np.std(pct, ddof=1) / math.sqrt(n))
        half = t_crit(n - 1) * sem
    else:
        half = float("nan")

    return {
        "base_mean": float(np.mean(base)),
        "treat_mean": float(np.mean(treat)),
        "improvement_pct": mean_pct,
        "ci_low": mean_pct - half,
        "ci_high": mean_pct + half,
        "p_value": sign_test_p(list(improvement)),
        "n_better": int(np.sum(improvement > 1e-9)),
        "n": n,
    }


# =============================================================================
# Execucao de um braco
# =============================================================================


def make_env(control):
    return SpIntersection(EnvConfig(
        horizon=HORIZON,
        decision_interval=DECISION_INTERVAL,
        min_green=MIN_GREEN_STEPS,
        max_green=MAX_GREEN_STEPS,
        warmup_steps=WARMUP_STEPS,
        control=control,
    ))


def load_agent():
    if not os.path.exists(MODEL_PATH):
        raise SystemExit(
            "Modelo nao encontrado em %s.\nRode primeiro: python traci8.DQN.py"
            % MODEL_PATH)
    from tensorflow import keras
    model = keras.models.load_model(MODEL_PATH, compile=False)
    expected = model.inputs[0].shape[-1]
    if int(expected) != sp_env.STATE_SIZE:
        raise SystemExit(
            "O modelo espera %d features, o ambiente produz %d.\n"
            "O modelo salvo e de uma versao anterior do estado. "
            "Retreine com: python traci8.DQN.py"
            % (int(expected), sp_env.STATE_SIZE))
    return model


def run_arm(arm, seed, scale, gui, model, runs_dir):
    """Roda um braco em uma seed e devolve as metricas do episodio."""
    control = "fixed" if arm == "fixed" else "agent"
    env = make_env(control)
    # O cenario entra no nome: sem isso, rodar --scenario original sobrescreve
    # silenciosamente os tripinfo do cenario calibrado na mesma demanda.
    tripinfo = os.path.join(runs_dir, "tripinfo_%s_%s_s%d_d%.2f.xml"
                            % (sp_env.SCENARIO, arm, seed, scale))

    state = env.reset(seed=seed, gui=gui, tripinfo=tripinfo, scale=scale)
    total_reward = 0.0
    try:
        while True:
            if arm == "fixed":
                action = 0
            elif arm == "alwaysswitch":
                action = 1
            elif arm == "shortcycle":
                action = 1 if env.tl.green_elapsed >= SHORT_CYCLE_GREEN else 0
            elif arm == "maxpressure":
                action = max_pressure_action(env)
            else:
                action = int(np.argmax(model(state[None, :], training=False).numpy()[0]))
            state, reward, done, _ = env.step(action)
            total_reward += reward
            if done:
                break
    finally:
        env.close()

    result = env.metrics.summary()
    result.update(sp_env.parse_tripinfo(tripinfo, min_depart=WARMUP_STEPS))
    result["reward"] = total_reward
    result["arm"] = arm
    result["seed"] = seed
    result["demand"] = scale
    return result


# =============================================================================
# Relatorio
# =============================================================================


def print_report(rows, demand):
    subset = [r for r in rows if abs(r["demand"] - demand) < 1e-9]
    by_arm = {a: [r for r in subset if r["arm"] == a] for a in ARMS}
    seeds = sorted({r["seed"] for r in subset})

    print("\n" + "=" * 78)
    print("RESULTADOS -- demanda %.2fx | %d seeds | horizonte %d s "
          "(aquecimento %d s descartado)" % (demand, len(seeds), HORIZON, WARMUP_STEPS))
    print("=" * 78)

    # Tabela gerada a partir de ARMS, para nao desalinhar ao mudar os bracos.
    width = 32 + 12 * len(ARMS) + 8
    print()
    print("%-32s%s  %s" % ("Metrica",
                           "".join("%12s" % ARM_LABEL[a] for a in ARMS), "unid."))
    print("-" * width)
    for key, label, unit in REPORT_METRICS:
        cells = []
        for a in ARMS:
            v = np.mean([r[key] for r in by_arm[a]]) if by_arm[a] else float("nan")
            cells.append("%12.2f" % v)
        print("%-32s%s  %s" % (label, "".join(cells), unit))

    n_trips = {a: np.mean([r["n_trips"] for r in by_arm[a]]) for a in ARMS}
    print("\nViagens concluidas (apos aquecimento): "
          + " | ".join("%s=%.0f" % (ARM_LABEL[a], n_trips[a]) for a in ARMS))
    switches = {a: np.mean([r["switches"] for r in by_arm[a]]) for a in ARMS}
    print("Trocas de fase por hora:              "
          + " | ".join("%s=%.0f" % (ARM_LABEL[a], switches[a]) for a in ARMS))
    lost = {a: np.mean([r["lost_time_s"] for r in by_arm[a]]) for a in ARMS}
    print("Tempo perdido em amarelo/all-red (s): "
          + " | ".join("%s=%.0f" % (ARM_LABEL[a], lost[a]) for a in ARMS))

    if not by_arm["dqn"]:
        print("\nBraco DQN ausente nesta execucao: as comparacoes pareadas"
              " precisam dos quatro bracos.")
        return

    for base_arm in [a for a in ARMS if a != "dqn"]:
        print("\n" + "-" * 78)
        print("DQN vs %s -- diferencas pareadas por seed (IC 95%%, teste dos sinais)"
              % ARM_LABEL[base_arm])
        print("-" * 78)
        print("%-30s %10s %10s %20s %9s"
              % ("Metrica", ARM_LABEL[base_arm][:10], "DQN", "Melhoria (IC 95%)", "p"))
        for key, label, unit in REPORT_METRICS:
            b = [r[key] for r in sorted(by_arm[base_arm], key=lambda x: x["seed"])]
            d = [r[key] for r in sorted(by_arm["dqn"], key=lambda x: x["seed"])]
            if not b or not d:
                continue
            st = paired_stats(b, d, LOWER_IS_BETTER.get(key, True))
            sig = "*" if st["p_value"] < 0.05 else " "
            print("%-30s %10.2f %10.2f  %+7.1f%% [%+6.1f,%+6.1f] %7.3f%s"
                  % (label, st["base_mean"], st["treat_mean"],
                     st["improvement_pct"], st["ci_low"], st["ci_high"],
                     st["p_value"], sig))
        print("  * p < 0,05. Melhoria positiva = DQN melhor. IC que cruza zero "
              "significa efeito nao demonstrado.")


def run_tag(rows):
    """
    Assinatura da execucao, usada nos nomes de saida.

    Cada execucao antes gravava em comparison_per_seed.csv fixo, entao uma
    inspecao visual (--seeds 1 --arms dqn --gui) apagava o resultado de uma
    varredura de 150 execucoes. Agora cenario, numero de bracos, seeds e
    demandas entram no nome, e execucoes diferentes nao se sobrescrevem.
    """
    arms = len({r["arm"] for r in rows})
    seeds = len({r["seed"] for r in rows})
    dems = sorted({r["demand"] for r in rows})
    d = "d%s" % "-".join("%.2f" % x for x in dems)
    return "%s_%darms_%dseeds_%s" % (sp_env.SCENARIO, arms, seeds, d)


def write_csvs(rows, runs_dir):
    tag = run_tag(rows)
    per_seed = os.path.join(runs_dir, "comparison_per_seed_%s.csv" % tag)
    fields = ["arm", "seed", "demand", "n_trips", "mean_wait", "p90_wait",
              "mean_time_loss", "mean_depart_delay", "mean_total_delay",
              "mean_duration", "mean_queue", "max_queue",
              "mean_speed", "arrived", "throughput_per_hour", "teleports",
              "switches", "lost_time_s", "reward"]
    with open(per_seed, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["demand"], x["arm"], x["seed"])):
            w.writerow({k: r.get(k, "") for k in fields})

    summary = os.path.join(runs_dir, "comparison_summary_%s.csv" % tag)
    with open(summary, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["demand", "baseline", "metric", "baseline_mean", "dqn_mean",
                    "improvement_pct", "ci_low", "ci_high", "p_value",
                    "seeds_better", "n_seeds"])
        for demand in sorted({r["demand"] for r in rows}):
            sub = [r for r in rows if abs(r["demand"] - demand) < 1e-9]
            for base_arm in [a for a in ARMS if a != "dqn"]:
                b_rows = sorted([r for r in sub if r["arm"] == base_arm],
                                key=lambda x: x["seed"])
                d_rows = sorted([r for r in sub if r["arm"] == "dqn"],
                                key=lambda x: x["seed"])
                for key, label, _ in REPORT_METRICS:
                    if not b_rows or not d_rows:
                        continue
                    st = paired_stats([r[key] for r in b_rows],
                                      [r[key] for r in d_rows],
                                      LOWER_IS_BETTER.get(key, True))
                    w.writerow([demand, base_arm, key,
                                round(st["base_mean"], 4), round(st["treat_mean"], 4),
                                round(st["improvement_pct"], 2),
                                round(st["ci_low"], 2), round(st["ci_high"], 2),
                                round(st["p_value"], 4),
                                st["n_better"], st["n"]])
    print("\nCSV por seed: %s" % per_seed)
    print("CSV resumo:   %s" % summary)


def plot_comparison(rows, runs_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    demands = sorted({r["demand"] for r in rows})
    panels = [("mean_wait", "Espera media por veiculo (s)"),
              ("mean_time_loss", "Time loss medio (s)"),
              ("mean_queue", "Fila media nas aproximacoes (veic.)"),
              ("throughput_per_hour", "Throughput (veic./h)")]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Controle semaforico no cruzamento de SP\n"
                 "Tempo Fixo vs Max-Pressure vs DQN "
                 "(medias sobre seeds, barras de erro = IC 95%%)",
                 fontsize=14, fontweight="bold")

    for ax, (key, title) in zip(axes.ravel(), panels):
        width = 0.26
        x = np.arange(len(demands))
        for i, arm in enumerate(ARMS):
            means, errs = [], []
            for d in demands:
                vals = [r[key] for r in rows
                        if r["arm"] == arm and abs(r["demand"] - d) < 1e-9]
                means.append(np.mean(vals) if vals else 0.0)
                if len(vals) > 1:
                    sem = np.std(vals, ddof=1) / math.sqrt(len(vals))
                    errs.append(t_crit(len(vals) - 1) * sem)
                else:
                    errs.append(0.0)
            ax.bar(x + (i - 1) * width, means, width, yerr=errs, capsize=4,
                   label=ARM_LABEL[arm], color=ARM_COLOR[arm])
        ax.set_title(title, fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(["%.2fx" % d for d in demands])
        ax.set_xlabel("Fator de demanda")
        ax.grid(True, alpha=0.35, axis="y")

    axes[0][0].legend(fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    path = os.path.join(runs_dir, "comparison_chart_%s.png" % run_tag(rows))
    fig.savefig(path, dpi=200)
    print("Grafico:      %s" % path)


# =============================================================================
# CLI
# =============================================================================


def main():
    p = argparse.ArgumentParser(description="Comparacao Tempo Fixo vs Max-Pressure vs DQN")
    p.add_argument("--seeds", type=int, default=10,
                   help="numero de seeds de avaliacao (pareadas entre bracos)")
    p.add_argument("--seed-base", type=int, default=5000,
                   help="primeira seed; usar valores fora das seeds de treino")
    p.add_argument("--demand", type=float, nargs="+", default=[1.0],
                   help="fatores de demanda a avaliar, ex.: 0.9 1.0 1.2")
    p.add_argument("--gui", action="store_true", help="abrir o sumo-gui")
    p.add_argument("--arms", nargs="+", default=list(ARMS), choices=list(ARMS))
    p.add_argument("--scenario", default="calibrated",
                   choices=list(sp_env.SCENARIOS),
                   help="cenario de demanda (ver sp_env.SCENARIOS)")
    # Sem isto, redirecionar a saida para arquivo ("> log.txt") esconde o
    # progresso ate o processo terminar, porque o Python passa a bufferizar
    # stdout em bloco quando ele nao e um terminal.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    args = p.parse_args()
    sp_env.set_scenario(args.scenario)
    print("Cenario: %s (%s)" % (args.scenario,
          os.path.basename(sp_env.SCENARIOS[args.scenario])))

    runs_dir = sp_env.ensure_runs_dir()
    model = load_agent() if "dqn" in args.arms else None
    seeds = [args.seed_base + i for i in range(args.seeds)]

    rows = []
    total = len(args.demand) * len(args.arms) * len(seeds)
    done = 0
    for demand in args.demand:
        for seed in seeds:
            for arm in args.arms:
                done += 1
                print("[%d/%d] demanda=%.2f seed=%d braco=%-11s ..."
                      % (done, total, demand, seed, arm), end=" ", flush=True)
                r = run_arm(arm, seed, demand, args.gui, model, runs_dir)
                rows.append(r)
                print("espera=%6.1fs fila=%5.2f throughput=%6.0f/h trocas=%3d"
                      % (r["mean_wait"], r["mean_queue"],
                         r["throughput_per_hour"], r["switches"]))

    for demand in args.demand:
        print_report(rows, demand)
    write_csvs(rows, runs_dir)
    if len(args.arms) == len(ARMS):
        plot_comparison(rows, runs_dir)
    print("\nConcluido.")


if __name__ == "__main__":
    main()
