"""
=============================================================================
Treino Double DQN para controle semaforico -- cruzamento de SP (SUMO/TraCI)
=============================================================================

Toda a dinamica (estado, recompensa, transicoes de fase, flags do SUMO) vem de
sp_env.py, o mesmo modulo importado por traci9_comp.py. Isso garante que o
agente e avaliado exatamente no ambiente em que foi treinado.

O que mudou em relacao a versao anterior, e por que:

  1. Transicoes seguras. Antes, setPhase(0 -> 3) saltava amarelo e all-red, e o
     ganho medido vinha de nao pagar o tempo perdido que o programa fixo paga.
     Agora SafeTrafficLight percorre verde -> amarelo -> all-red -> verde.

  2. Autoridade real sobre o semaforo. O programa e "static": antes ele
     continuava ciclando por baixo do agente, e a acao "manter" nao mantinha
     nada. Agora cada fase entra com duracao infinita e so o agente avanca.

  3. Verde minimo e maximo aplicados por mascara de acao, com as transicoes
     forcadas fora do buffer de replay. O agente so aprende de decisoes que
     eram de fato dele.

  4. Estado normalizado pela capacidade do detector em veiculos, nao pelo
     comprimento em metros. Antes as features de fila viviam em [0; 0,15]
     enquanto o one-hot de fase valia 1,0.

  5. Recompensa unica e limitada, definida em sp_env.py. Antes treino e
     comparacao usavam funcoes diferentes, em escalas ~40x distintas.

  6. Demanda aleatorizada por episodio (--scale em [0,85; 1,30]) e seed
     diferente por episodio. Sem isso o agente decorava uma unica realizacao.

  7. Alvo de Bellman aplicado somente a acao tomada, dentro de um tf.function.
     A versao anterior regredia tambem a acao nao tomada contra a propria
     predicao, injetando ruido.

  8. Checkpoint pelo melhor resultado em seeds de validacao separadas, nao
     pelos pesos do ultimo episodio.

Referencias:
  Mnih et al. (2015) Nature 518:529-533.
  Van Hasselt et al. (2016) AAAI -- Double Q-learning.
  Genders & Razavi (2016) arXiv:1611.01142.
=============================================================================
"""

import argparse
import csv
import os
import sys
import random
import time
from collections import deque

import numpy as np

import sp_env
from sp_env import ACTION_SIZE, STATE_SIZE, EnvConfig, SpIntersection

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

# =============================================================================
# Hiperparametros
# =============================================================================

SEED = 42

GAMMA = 0.95               # ~20 decisoes de horizonte efetivo (~100 s, um ciclo)
LEARNING_RATE = 5e-4
BATCH_SIZE = 64
REPLAY_BUFFER_SIZE = 100_000
MIN_REPLAY_SIZE = 800     # so decisoes livres entram no buffer, ver nota abaixo
TARGET_UPDATE_EVERY = 500  # em atualizacoes de gradiente, nao em steps de simulacao
UPDATES_PER_DECISION = 1   # atualizacoes por decisao, independente do armazenamento

EPSILON_START = 1.0
EPSILON_MIN = 0.05
# O decaimento so COMECA quando o buffer atinge MIN_REPLAY_SIZE. Antes disso
# nenhum gradiente e aplicado, e decair epsilon nessa janela desperdicava
# metade do treino explorando sem aprender nada.
EPSILON_DECAY_FRACTION = 0.5   # fracao das decisoes de aprendizado ate o piso

# Liberdade ampla de proposito. A varredura de min_green mostrou que o ponto
# de operacao otimo e segurar o verde ~20 s: em min_green=20 tudo converge para
# o mesmo resultado e nao ha nada a aprender. Deixando min_green=10 e
# max_green=60, segurar o verde passa a ser uma decisao do agente, e a pergunta
# do experimento vira: o DQN descobre sozinho o ponto que a analise indica?
MIN_GREEN_STEPS = 10
MAX_GREEN_STEPS = 60
DECISION_INTERVAL = 5
HORIZON = 1800
WARMUP_STEPS = 300

# Demanda calibrada = 3123 veic/h, com E2 em v/c = 1.00. Varia-se em torno
# de 1.0 para o agente ver desde folga leve ate saturacao.
TRAIN_SCALE_RANGE = (0.80, 1.05)   # demanda aleatorizada por episodio
VALID_SEEDS = (9001, 9002, 9003)   # nunca usadas no treino
VALID_SCALE = 1.0

MODEL_PATH = os.path.join(sp_env.SCRIPT_DIR, "dqn_traffic_model.keras")
LAST_MODEL_PATH = os.path.join(sp_env.SCRIPT_DIR, "dqn_traffic_model_last.keras")


# =============================================================================
# Rede
# =============================================================================


def build_model(state_size, action_size):
    """
    MLP de 3 camadas ocultas. Saida linear porque valores Q sao ilimitados.
    A perda e Huber, aplicada manualmente no train_step para evitar depender
    da assinatura de keras.losses entre versoes.
    """
    return keras.Sequential([
        layers.Input(shape=(state_size,)),
        layers.Dense(128, activation="relu"),
        layers.Dense(128, activation="relu"),
        layers.Dense(64, activation="relu"),
        layers.Dense(action_size, activation="linear"),
    ])


class DoubleDQN:
    """Double DQN com replay uniforme e rede alvo."""

    def __init__(self, state_size, action_size, lr=LEARNING_RATE):
        self.online = build_model(state_size, action_size)
        self.target = build_model(state_size, action_size)
        self.target.set_weights(self.online.get_weights())
        self.optimizer = keras.optimizers.Adam(learning_rate=lr, clipnorm=10.0)
        self.buffer = deque(maxlen=REPLAY_BUFFER_SIZE)
        self.updates = 0

    def remember(self, s, a, r, s2, done):
        self.buffer.append((s, a, r, s2, float(done)))

    def act(self, state, epsilon):
        if random.random() < epsilon:
            return random.randrange(ACTION_SIZE)
        q = self.online(state[None, :], training=False).numpy()[0]
        return int(np.argmax(q))

    def act_greedy(self, state):
        q = self.online(state[None, :], training=False).numpy()[0]
        return int(np.argmax(q))

    @tf.function(reduce_retracing=True)
    def _train_step(self, states, actions, rewards, next_states, dones):
        # Double DQN: a acao do proximo estado e escolhida pela rede online e
        # avaliada pela rede alvo, o que corrige o vies de superestimacao.
        next_online = self.online(next_states, training=False)
        best = tf.argmax(next_online, axis=1, output_type=tf.int32)
        next_target = self.target(next_states, training=False)
        rows = tf.range(tf.shape(best)[0], dtype=tf.int32)
        max_q_next = tf.gather_nd(next_target, tf.stack([rows, best], axis=1))
        y = rewards + GAMMA * max_q_next * (1.0 - dones)

        with tf.GradientTape() as tape:
            q = self.online(states, training=True)
            q_taken = tf.gather_nd(q, tf.stack([rows, actions], axis=1))
            err = y - q_taken
            abs_err = tf.abs(err)
            huber = tf.where(abs_err <= 1.0, 0.5 * tf.square(err), abs_err - 0.5)
            loss = tf.reduce_mean(huber)
        grads = tape.gradient(loss, self.online.trainable_variables)
        self.optimizer.apply_gradients(zip(grads, self.online.trainable_variables))
        return loss

    def learn(self):
        if len(self.buffer) < MIN_REPLAY_SIZE:
            return None
        batch = random.sample(self.buffer, BATCH_SIZE)
        s, a, r, s2, d = zip(*batch)
        loss = self._train_step(
            tf.convert_to_tensor(np.asarray(s, dtype=np.float32)),
            tf.convert_to_tensor(np.asarray(a, dtype=np.int32)),
            tf.convert_to_tensor(np.asarray(r, dtype=np.float32)),
            tf.convert_to_tensor(np.asarray(s2, dtype=np.float32)),
            tf.convert_to_tensor(np.asarray(d, dtype=np.float32)),
        )
        self.updates += 1
        if self.updates % TARGET_UPDATE_EVERY == 0:
            self.target.set_weights(self.online.get_weights())
        return float(loss.numpy())


# =============================================================================
# Rollouts
# =============================================================================


def make_env(control="agent"):
    return SpIntersection(EnvConfig(
        horizon=HORIZON,
        decision_interval=DECISION_INTERVAL,
        min_green=MIN_GREEN_STEPS,
        max_green=MAX_GREEN_STEPS,
        warmup_steps=WARMUP_STEPS,
        control=control,
    ))


def run_greedy(agent, env, seed, scale=VALID_SCALE):
    """
    Rollout guloso, sem aprendizado.

    Grava tripinfo porque a selecao de checkpoint tem de usar a METRICA
    OBJETIVO (atraso total por veiculo, incluindo o atraso de insercao). Selecionar
    por fila/espera nas faixas premiaria uma politica que simplesmente retem
    veiculos fora da rede: a fila nas faixas cai e o atraso real sobe.
    """
    tripinfo = os.path.join(sp_env.ensure_runs_dir(),
                            "valid_s%d.xml" % seed)
    state = env.reset(seed=seed, scale=scale, tripinfo=tripinfo)
    total_reward = 0.0
    try:
        while True:
            action = agent.act_greedy(state)
            state, reward, done, _ = env.step(action)
            total_reward += reward
            if done:
                break
    finally:
        env.close()
    summary = env.metrics.summary()
    summary.update(sp_env.parse_tripinfo(tripinfo, min_depart=WARMUP_STEPS))
    summary["reward"] = total_reward
    return summary


def reference_baselines(seeds=VALID_SEEDS, scale=VALID_SCALE):
    """
    Mede tempo fixo e max-pressure nas MESMAS seeds de validacao.

    Serve de alvo durante o treino: sem esta referencia e impossivel saber, ao
    olhar a curva de aprendizado, se o agente esta indo bem ou apenas melhorando
    em relacao a si mesmo.
    """
    from sp_env import max_pressure_action
    out = {}
    for name, control, policy in (
        ("Tempo Fixo", "fixed", lambda e, s: 0),
        ("Max-Pressure", "agent", lambda e, s: max_pressure_action(e)),
    ):
        env = make_env(control)
        rows = []
        for seed in seeds:
            tri = os.path.join(sp_env.ensure_runs_dir(), "ref_s%d.xml" % seed)
            state = env.reset(seed=seed, scale=scale, tripinfo=tri)
            try:
                while True:
                    state, _, done, _ = env.step(policy(env, state))
                    if done:
                        break
            finally:
                env.close()
            m = env.metrics.summary()
            m.update(sp_env.parse_tripinfo(tri, min_depart=WARMUP_STEPS))
            rows.append(m)
        out[name] = {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}
    return out


def validate(agent, env, seeds=VALID_SEEDS):
    """Media das seeds de validacao. Menor mean_total_delay e melhor."""
    rows = [run_greedy(agent, env, s) for s in seeds]
    keys = rows[0].keys()
    return {k: float(np.mean([r[k] for r in rows])) for k in keys}


# =============================================================================
# Treino
# =============================================================================


def train(episodes, eval_every, out_csv):
    random.seed(SEED)
    np.random.seed(SEED)
    tf.random.set_seed(SEED)

    agent = DoubleDQN(STATE_SIZE, ACTION_SIZE)
    print("Estado: %d features | Acoes: %d" % (STATE_SIZE, ACTION_SIZE))
    agent.online.summary()

    print()
    print("Referencia nas seeds de validacao %s (demanda %.2fx):"
          % (str(VALID_SEEDS), VALID_SCALE))
    refs = reference_baselines()
    for name, m in refs.items():
        print("  %-13s atraso_total=%6.1f s (loss=%.1f + insercao=%.1f)"
              " | viagens=%.0f | fila=%.2f"
              % (name, m["mean_total_delay"], m["mean_time_loss"],
                 m["mean_depart_delay"], m["n_trips"], m["mean_queue"]))
    target = refs["Max-Pressure"]["mean_total_delay"]
    print("  Alvo: o atraso total de validacao do DQN precisa ficar abaixo de"
          " %.1f s para superar a heuristica gulosa." % target)

    env = make_env("agent")
    decisions_per_ep = HORIZON // DECISION_INTERVAL
    total_decisions = max(episodes * decisions_per_ep, 1)
    eps_decay_steps = max(int(total_decisions * EPSILON_DECAY_FRACTION), 1)

    history = []
    decisions = 0
    learn_decisions = 0
    best_wait = float("inf")
    started = time.time()

    print("\n=== Treino Double DQN ===")
    print("Episodios=%d | horizonte=%d steps | decisao a cada %d steps"
          % (episodes, HORIZON, DECISION_INTERVAL))
    print("epsilon 1.00 -> %.2f em %d decisoes (%.0f%% do treino)\n"
          % (EPSILON_MIN, eps_decay_steps, 100 * EPSILON_DECAY_FRACTION))

    try:
        for episode in range(1, episodes + 1):
            seed = 1000 + episode
            scale = random.uniform(*TRAIN_SCALE_RANGE)
            state = env.reset(seed=seed, scale=scale)

            ep_reward = 0.0
            ep_loss = []
            stored = 0
            ep_decisions = 0

            while True:
                # epsilon linear: previsivel e facil de reportar no TCC.
                frac = min(learn_decisions / eps_decay_steps, 1.0)
                epsilon = EPSILON_START + frac * (EPSILON_MIN - EPSILON_START)

                action = agent.act(state, epsilon)
                next_state, reward, done, info = env.step(action)
                ep_reward += reward
                decisions += 1
                ep_decisions += 1

                # Transicoes forcadas por verde min/max nao foram escolhas do
                # agente, entao nao entram no buffer. As atualizacoes de
                # gradiente, porem, acontecem a cada decisao: atrela-las ao
                # armazenamento reduzia o treino a ~40% das atualizacoes.
                if not info["forced"]:
                    agent.remember(state, info["action"], reward, next_state, done)
                    stored += 1
                for _ in range(UPDATES_PER_DECISION):
                    loss = agent.learn()
                    if loss is not None:
                        ep_loss.append(loss)
                if len(agent.buffer) >= MIN_REPLAY_SIZE:
                    learn_decisions += 1

                state = next_state
                if done:
                    break

            env.close()
            m = env.metrics.summary()
            row = {
                "episode": episode,
                "seed": seed,
                "scale": round(scale, 3),
                "epsilon": round(epsilon, 4),
                "reward": round(ep_reward, 2),
                "reward_per_decision": round(ep_reward / max(ep_decisions, 1), 4),
                "mean_queue": round(m["mean_queue"], 3),
                "mean_lane_wait": round(m["mean_lane_wait"], 2),
                "mean_speed": round(m["mean_speed"], 3),
                "arrived": m["arrived"],
                "teleports": m["teleports"],
                "switches": m["switches"],
                "stored": stored,
                "buffer": len(agent.buffer),
                "updates": agent.updates,
                "loss": round(float(np.mean(ep_loss)), 5) if ep_loss else "",
                "valid_wait": "",
            }

            if episode % eval_every == 0 or episode == episodes:
                v = validate(agent, env)
                row["valid_wait"] = round(v["mean_total_delay"], 2)
                flag = ""
                if v["mean_total_delay"] < best_wait:
                    best_wait = v["mean_total_delay"]
                    agent.online.save(MODEL_PATH)
                    flag = "  <-- melhor, salvo"
                print("  validacao ep %3d: atraso_total=%6.1f s (loss=%.1f + insercao=%.1f)"
                      " | viagens=%.0f | fila=%.2f%s"
                      % (episode, v["mean_total_delay"], v["mean_time_loss"],
                         v["mean_depart_delay"], v["n_trips"], v["mean_queue"], flag))

            history.append(row)
            print("ep %3d/%d | scale=%.2f | eps=%.3f | R=%8.1f | fila=%5.2f | "
                  "espera=%6.1f | trocas=%3d | buf=%6d"
                  % (episode, episodes, scale, epsilon, ep_reward,
                     m["mean_queue"], m["mean_lane_wait"], m["switches"],
                     len(agent.buffer)))
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuario. Salvando o estado atual.")
    finally:
        env.close()
        agent.online.save(LAST_MODEL_PATH)

    if not os.path.exists(MODEL_PATH):
        agent.online.save(MODEL_PATH)

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        if history:
            w = csv.DictWriter(f, fieldnames=list(history[0].keys()))
            w.writeheader()
            w.writerows(history)

    mins = (time.time() - started) / 60.0
    print("\nTreino concluido em %.1f min." % mins)
    print("Melhor atraso total de validacao: %.1f s" % best_wait)
    print("Modelo (melhor): %s" % MODEL_PATH)
    print("Modelo (ultimo): %s" % LAST_MODEL_PATH)
    print("Historico:      %s" % out_csv)
    return history


# =============================================================================
# Grafico
# =============================================================================


def plot_history(history, path):
    if not history:
        return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ep = [r["episode"] for r in history]
    fig, ax = plt.subplots(4, 1, figsize=(11, 12), sharex=True)

    ax[0].plot(ep, [r["reward"] for r in history], linewidth=1.6, color="tab:blue")
    ax[0].set_ylabel("Recompensa/episodio")
    ax[0].set_title("Treino Double DQN -- cruzamento de SP")

    ax[1].plot(ep, [r["mean_queue"] for r in history], linewidth=1.6, color="tab:orange")
    ax[1].set_ylabel("Fila media (veic.)")

    ax[2].plot(ep, [r["mean_lane_wait"] for r in history], linewidth=1.6, color="tab:red",
               label="treino (com exploracao)")
    vx = [r["episode"] for r in history if r["valid_wait"] != ""]
    vy = [r["valid_wait"] for r in history if r["valid_wait"] != ""]
    if vx:
        ax[2].plot(vx, vy, "o-", linewidth=2.0, color="tab:green",
                   label="validacao (guloso)")
    ax[2].set_ylabel("Espera nas faixas (s)")
    ax[2].legend(fontsize=9)

    ax[3].plot(ep, [r["epsilon"] for r in history], linewidth=1.6, color="tab:gray")
    ax[3].set_ylabel("epsilon")
    ax[3].set_xlabel("Episodio")

    for a in ax:
        a.grid(True, alpha=0.35)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print("Grafico:        %s" % path)


# =============================================================================
# CLI
# =============================================================================


def main():
    p = argparse.ArgumentParser(description="Treino Double DQN -- cruzamento de SP")
    p.add_argument("--episodes", type=int, default=60)
    p.add_argument("--eval-every", type=int, default=5)
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

    runs = sp_env.ensure_runs_dir()
    out_csv = os.path.join(runs, "training_history.csv")
    history = train(args.episodes, args.eval_every, out_csv)
    plot_history(history, os.path.join(runs, "dqn_training_results.png"))


if __name__ == "__main__":
    main()
