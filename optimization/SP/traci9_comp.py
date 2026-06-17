# =============================================================================
# FINAL TCC COMPARISON SCRIPT — FIXED-TIME vs DQN
# =============================================================================
# Features:
#   - Fair comparison using same SUMO seed
#   - Same state representation as training
#   - DQN inference optimized
#   - Queue / Waiting Time / Speed / Throughput metrics
#   - Smoothed professional graphs
#   - Integer vehicle visualization
#   - Statistical summary
#   - Publication-ready charts for TCC
# =============================================================================

import os
import sys
import csv
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np 

import tensorflow as tf
from tensorflow import keras

# =============================================================================
# SUMO Setup
# =============================================================================

if 'SUMO_HOME' in os.environ:
    sys.path.append(
        os.path.join(os.environ['SUMO_HOME'], 'tools')
    )
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# =============================================================================
# CONFIG
# =============================================================================

TOTAL_STEPS = 2000

TRAINED_MODEL_PATH = os.path.join(SCRIPT_DIR, "dqn_traffic_model.keras")

TLS_ID = "clusterJ0_J14_J2_J7"

DETECTORS = [
    "e2_0",   # E6_0  (WB approach)
    "e2_5",   # E2_1  (EB approach, lane 1)
    "e2_6",   # E2_0  (EB approach, lane 0)
    "e2_1",   # E3_2  (NB approach, lane 2)
    "e2_2",   # E3_3  (NB approach, lane 3)
    "e2_3",   # E3_1  (NB approach, lane 1)
    "e2_4",   # E3_0  (NB approach, lane 0)
]

GREEN_PHASES = [0, 3]  # phases 0 and 3 are the green phases (2 is all-red)

NUM_PHASES = 5         # must match the state encoding used during training

MIN_GREEN_STEPS = 20

SMOOTH_WINDOW = 5

# =============================================================================
# HELPERS
# =============================================================================

def start_sumo(gui=True):

    binary = 'sumo-gui' if gui else 'sumo'

    cfg = [
        binary,

        '-c',
        os.path.join(SCRIPT_DIR, 'Cruzamento.sumocfg'),

        '--seed',
        '42',

        '--step-length',
        '1.0',

        '--time-to-teleport',
        '60',

        '--no-warnings',
        'true',

        '--quit-on-end',
        'true'
    ]

    traci.start(cfg)

    if gui:

        traci.gui.setSchema(
            "View #0",
            "real world"
        )


def get_state():

    state = []

    for d in DETECTORS:

        queue = (
            traci.lanearea.getLastStepVehicleNumber(d)
            / 20.0
        )

        halting = (
            traci.lanearea.getLastStepHaltingNumber(d)
            / 20.0
        )

        occupancy = (
            traci.lanearea.getLastStepOccupancy(d)
            / 100.0
        )

        state.extend([
            queue,
            halting,
            occupancy
        ])

    # One-hot encoding of the current phase (must match the training script).
    phase = traci.trafficlight.getPhase(TLS_ID)
    phase_onehot = [0.0] * NUM_PHASES
    if 0 <= phase < NUM_PHASES:
        phase_onehot[phase] = 1.0
    state.extend(phase_onehot)

    return tuple(state)


def extract_total_queue(state):

    total = 0

    values = list(state[:-NUM_PHASES])

    for i in range(0, len(values), 3):

        total += values[i]

    return total * 20


def get_reward(state):

    total_queue = extract_total_queue(state)

    total_waiting = 0

    for veh in traci.vehicle.getIDList():

        total_waiting += (
            traci.vehicle.getWaitingTime(veh)
            / 100.0
        )

    reward = (
        - total_queue * 2.0
        - total_waiting * 0.5
    )

    return float(reward)


def get_total_waiting_time():

    total_wait = 0

    for veh in traci.vehicle.getIDList():

        total_wait += (
            traci.vehicle.getWaitingTime(veh)
        )

    return total_wait


def get_average_speed():

    vehicles = traci.vehicle.getIDList()

    if len(vehicles) == 0:
        return 0

    speeds = []

    for veh in vehicles:

        speeds.append(
            traci.vehicle.getSpeed(veh)
        )

    return np.mean(speeds)


def moving_average(data, window=5):

    if len(data) < window:
        return data

    return np.convolve(
        data,
        np.ones(window)/window,
        mode='valid'
    )


def save_csv(path, headers, rows):

    with open(path, 'w', newline='') as f:

        writer = csv.writer(f)

        writer.writerow(headers)
        writer.writerows(rows)

# =============================================================================
# BASELINE
# =============================================================================

def run_baseline(use_gui=True):

    print("\n=================================================")
    print("BASELINE — FIXED TIME")
    print("=================================================")

    start_sumo(gui=use_gui)

    metrics = {
        "step": [],
        "queue": [],
        "reward": [],
        "waiting_time": [],
        "avg_speed": [],
        "throughput": []
    }

    rows = []

    cumulative_reward = 0

    for step in range(TOTAL_STEPS):

        traci.simulationStep()

        if (
            step > 100 and
            traci.simulation.getMinExpectedNumber() <= 0
        ):
            print("Simulation finished early.")
            break

        state = get_state()

        reward = get_reward(state)

        cumulative_reward += reward

        total_queue = extract_total_queue(state)

        waiting_time = get_total_waiting_time()

        avg_speed = get_average_speed()

        throughput = traci.simulation.getArrivedNumber()

        if step % 50 == 0:

            metrics["step"].append(step)
            metrics["queue"].append(total_queue)
            metrics["reward"].append(cumulative_reward)
            metrics["waiting_time"].append(waiting_time)
            metrics["avg_speed"].append(avg_speed)
            metrics["throughput"].append(throughput)

            rows.append([
                step,
                total_queue,
                cumulative_reward,
                waiting_time,
                avg_speed,
                throughput
            ])

            print(
                f"[BASELINE] "
                f"Step={step:>5} | "
                f"Queue={int(total_queue):>3} | "
                f"Wait={waiting_time:.1f} | "
                f"Speed={avg_speed:.2f}"
            )

    traci.close()

    save_csv(
        "baseline_metrics.csv",
        [
            "step",
            "queue",
            "reward",
            "waiting_time",
            "avg_speed",
            "throughput"
        ],
        rows
    )

    return metrics

# =============================================================================
# DQN
# =============================================================================

def run_dqn(use_gui=True):

    print("\n=================================================")
    print("DQN AGENT")
    print("=================================================")

    if not os.path.exists(TRAINED_MODEL_PATH):

        print("Model not found.")
        return {}

    model = keras.models.load_model(
        TRAINED_MODEL_PATH
    )

    start_sumo(gui=use_gui)

    metrics = {
        "step": [],
        "queue": [],
        "reward": [],
        "waiting_time": [],
        "avg_speed": [],
        "throughput": []
    }

    rows = []

    cumulative_reward = 0

    last_switch = -MIN_GREEN_STEPS

    switch_count = 0

    for step in range(TOTAL_STEPS):

        state = get_state()

        state_arr = np.array(
            state,
            dtype=np.float32
        ).reshape(1, -1)

        q_values = model(
            state_arr,
            training=False
        ).numpy()[0]

        action = int(np.argmax(q_values))

        current_phase = traci.trafficlight.getPhase(TLS_ID)

        if action == 1:

            if (
                step - last_switch
            ) >= MIN_GREEN_STEPS:

                if current_phase == GREEN_PHASES[0]:

                    traci.trafficlight.setPhase(
                        TLS_ID,
                        GREEN_PHASES[1]
                    )

                else:

                    traci.trafficlight.setPhase(
                        TLS_ID,
                        GREEN_PHASES[0]
                    )

                last_switch = step

                switch_count += 1

        traci.simulationStep()

        if (
            step > 100 and
            traci.simulation.getMinExpectedNumber() <= 0
        ):
            print("Simulation finished early.")
            break

        next_state = get_state()

        reward = get_reward(next_state)

        cumulative_reward += reward

        total_queue = extract_total_queue(next_state)

        waiting_time = get_total_waiting_time()

        avg_speed = get_average_speed()

        throughput = traci.simulation.getArrivedNumber()

        if step % 50 == 0:

            metrics["step"].append(step)
            metrics["queue"].append(total_queue)
            metrics["reward"].append(cumulative_reward)
            metrics["waiting_time"].append(waiting_time)
            metrics["avg_speed"].append(avg_speed)
            metrics["throughput"].append(throughput)

            rows.append([
                step,
                total_queue,
                cumulative_reward,
                waiting_time,
                avg_speed,
                throughput
            ])

            print(
                f"[DQN] "
                f"Step={step:>5} | "
                f"Queue={int(total_queue):>3} | "
                f"Wait={waiting_time:.1f} | "
                f"Speed={avg_speed:.2f} | "
                f"Switches={switch_count}"
            )

    traci.close()

    print(f"\nTotal DQN phase switches: {switch_count}")

    save_csv(
        "dqn_metrics.csv",
        [
            "step",
            "queue",
            "reward",
            "waiting_time",
            "avg_speed",
            "throughput"
        ],
        rows
    )

    return metrics

# =============================================================================
# PLOTS
# =============================================================================

def plot_comparison(baseline, dqn):

    COLORS = {
        "baseline": "steelblue",
        "dqn":      "darkorange"
    }

    fig = plt.figure(figsize=(16, 14))

    fig.suptitle(
        "Traffic Signal Control Comparison\nFixed-Time vs Deep Q-Network",
        fontsize=16,
        fontweight='bold',
        y=1.01
    )

    gs = gridspec.GridSpec(
        3, 2,
        figure=fig,
        hspace=0.55,
        wspace=0.35
    )

    # =========================================================
    # QUEUE
    # =========================================================

    ax1 = fig.add_subplot(gs[0, :])

    baseline_queue = moving_average(baseline["queue"], SMOOTH_WINDOW)
    dqn_queue      = moving_average(dqn["queue"],      SMOOTH_WINDOW)

    line_base, = ax1.plot(
        baseline["step"][:len(baseline_queue)],
        baseline_queue,
        linewidth=2.5,
        label="Fixed-Time",
        color=COLORS["baseline"]
    )

    line_dqn, = ax1.plot(
        dqn["step"][:len(dqn_queue)],
        dqn_queue,
        linewidth=2.5,
        label="DQN",
        color=COLORS["dqn"]
    )

    ax1.set_title("Average Queue Length", pad=10)
    ax1.set_xlabel("Simulation Step")
    ax1.set_ylabel("Vehicles")
    ax1.grid(True, alpha=0.4)
    ax1.margins(y=0.15)

    # =========================================================
    # WAITING TIME
    # =========================================================

    ax2 = fig.add_subplot(gs[1, 0])

    ax2.plot(baseline["step"], baseline["waiting_time"],
             linewidth=2, color=COLORS["baseline"])
    ax2.plot(dqn["step"],      dqn["waiting_time"],
             linewidth=2, color=COLORS["dqn"])

    ax2.set_title("Vehicle Waiting Time", pad=10)
    ax2.set_xlabel("Simulation Step")
    ax2.set_ylabel("Seconds")
    ax2.grid(True, alpha=0.4)
    ax2.margins(y=0.15)

    # =========================================================
    # SPEED
    # =========================================================

    ax3 = fig.add_subplot(gs[1, 1])

    ax3.plot(baseline["step"], baseline["avg_speed"],
             linewidth=2, color=COLORS["baseline"])
    ax3.plot(dqn["step"],      dqn["avg_speed"],
             linewidth=2, color=COLORS["dqn"])

    ax3.set_title("Average Vehicle Speed", pad=10)
    ax3.set_xlabel("Simulation Step")
    ax3.set_ylabel("m/s")
    ax3.grid(True, alpha=0.4)
    ax3.margins(y=0.15)

    # =========================================================
    # REWARD
    # =========================================================

    ax4 = fig.add_subplot(gs[2, 0])

    ax4.plot(baseline["step"], baseline["reward"],
             linewidth=2, color=COLORS["baseline"])
    ax4.plot(dqn["step"],      dqn["reward"],
             linewidth=2, color=COLORS["dqn"])

    ax4.set_title("Cumulative Reward", pad=10)
    ax4.set_xlabel("Simulation Step")
    ax4.grid(True, alpha=0.4)
    ax4.margins(y=0.15)

    # =========================================================
    # BAR COMPARISON
    # =========================================================

    ax5 = fig.add_subplot(gs[2, 1])

    avg_baseline = np.mean(baseline["queue"])
    avg_dqn      = np.mean(dqn["queue"])
    improvement  = ((avg_baseline - avg_dqn) / avg_baseline) * 100

    bars = ax5.bar(
        ["Fixed-Time", "DQN"],
        [avg_baseline, avg_dqn],
        color=[COLORS["baseline"], COLORS["dqn"]],
        width=0.5
    )

    max_val = max(avg_baseline, avg_dqn)
    ax5.set_ylim(0, max_val * 1.30)

    for bar, val in zip(bars, [avg_baseline, avg_dqn]):
        ax5.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max_val * 0.03,
            f"{int(val)}",
            ha='center', va='bottom',
            fontsize=11, fontweight='bold'
        )

    ax5.set_title(f"Queue Reduction: {improvement:.1f}%", pad=10)
    ax5.set_ylabel("Average Vehicles")
    ax5.grid(True, alpha=0.4, axis='y')

    # =========================================================
    # LEGENDA GLOBAL — uma só, fora dos subplots
    # =========================================================

    fig.legend(
        handles=[line_base, line_dqn],
        labels=["Fixed-Time", "DQN"],
        loc='upper center',
        bbox_to_anchor=(0.5, 0.98),   # logo abaixo do suptitle
        ncol=2,
        fontsize=13,
        frameon=True,
        framealpha=0.9
    )

    # =========================================================
    # SALVAR
    # =========================================================

    plt.savefig(
        "comparison_chart.png",
        dpi=300,
        bbox_inches='tight'
    )

    plt.show()

    # =========================================================
    # SUMMARY
    # =========================================================

    print("\n=================================================")
    print("FINAL RESULTS")
    print("=================================================")
    print(f"Average Queue Fixed-Time : {avg_baseline:.1f}")
    print(f"Average Queue DQN        : {avg_dqn:.1f}")
    print(f"Queue Reduction          : {improvement:.1f}%")
    print()
    print(f"Average Waiting Fixed-Time : {np.mean(baseline['waiting_time']):.1f}")
    print(f"Average Waiting DQN        : {np.mean(dqn['waiting_time']):.1f}")
    print()
    print(f"Average Speed Fixed-Time : {np.mean(baseline['avg_speed']):.2f} m/s")
    print(f"Average Speed DQN        : {np.mean(dqn['avg_speed']):.2f} m/s")
    print("\ncomparison_chart.png saved")

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":

    USE_GUI = True

    baseline_metrics = run_baseline(
        use_gui=USE_GUI
    )

    dqn_metrics = run_dqn(
        use_gui=USE_GUI
    )

    if baseline_metrics and dqn_metrics:

        plot_comparison(
            baseline_metrics,
            dqn_metrics
        )

    print("\nDone.")