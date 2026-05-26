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

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

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

# =============================================================================
# CONFIG
# =============================================================================

TOTAL_STEPS = 1000

TRAINED_MODEL_PATH = "dqn_traffic_model.keras"

TLS_ID = "Node2"

DETECTORS_EB = [
    "Node1_2_EB_0",
    "Node1_2_EB_1",
    "Node1_2_EB_2"
]

DETECTORS_SB = [
    "Node2_7_SB_0",
    "Node2_7_SB_1",
    "Node2_7_SB_2"
]

GREEN_PHASES = [0, 2]

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
        'RL.sumocfg',

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

    for d in DETECTORS_EB + DETECTORS_SB:

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

    phase = traci.trafficlight.getPhase(TLS_ID)

    state.append(phase / 10.0)

    return tuple(state)


def extract_total_queue(state):

    total = 0

    values = list(state[:-1])

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

    fig = plt.figure(
        figsize=(16, 12)
    )

    fig.suptitle(
        "Traffic Signal Control Comparison\nFixed-Time vs Deep Q-Network",
        fontsize=18,
        fontweight='bold'
    )

    gs = gridspec.GridSpec(
        3,
        2,
        figure=fig,
        hspace=0.35,
        wspace=0.30
    )

    # =========================================================
    # QUEUE
    # =========================================================

    ax1 = fig.add_subplot(gs[0, :])

    baseline_queue = moving_average(
        baseline["queue"],
        SMOOTH_WINDOW
    )

    dqn_queue = moving_average(
        dqn["queue"],
        SMOOTH_WINDOW
    )

    ax1.plot(
        baseline["step"][:len(baseline_queue)],
        baseline_queue,
        linewidth=2.5,
        label="Fixed-Time"
    )

    ax1.plot(
        dqn["step"][:len(dqn_queue)],
        dqn_queue,
        linewidth=2.5,
        label="DQN"
    )

    ax1.set_title(
        "Average Queue Length"
    )

    ax1.set_xlabel(
        "Simulation Step"
    )

    ax1.set_ylabel(
        "Vehicles"
    )

    ax1.grid(True)

    ax1.legend()

    # =========================================================
    # WAITING TIME
    # =========================================================

    ax2 = fig.add_subplot(gs[1, 0])

    ax2.plot(
        baseline["step"],
        baseline["waiting_time"],
        linewidth=2,
        label="Fixed-Time"
    )

    ax2.plot(
        dqn["step"],
        dqn["waiting_time"],
        linewidth=2,
        label="DQN"
    )

    ax2.set_title(
        "Vehicle Waiting Time"
    )

    ax2.set_xlabel(
        "Simulation Step"
    )

    ax2.set_ylabel(
        "Seconds"
    )

    ax2.grid(True)

    ax2.legend()

    # =========================================================
    # SPEED
    # =========================================================

    ax3 = fig.add_subplot(gs[1, 1])

    ax3.plot(
        baseline["step"],
        baseline["avg_speed"],
        linewidth=2,
        label="Fixed-Time"
    )

    ax3.plot(
        dqn["step"],
        dqn["avg_speed"],
        linewidth=2,
        label="DQN"
    )

    ax3.set_title(
        "Average Vehicle Speed"
    )

    ax3.set_xlabel(
        "Simulation Step"
    )

    ax3.set_ylabel(
        "m/s"
    )

    ax3.grid(True)

    ax3.legend()

    # =========================================================
    # REWARD
    # =========================================================

    ax4 = fig.add_subplot(gs[2, 0])

    ax4.plot(
        baseline["step"],
        baseline["reward"],
        linewidth=2,
        label="Fixed-Time"
    )

    ax4.plot(
        dqn["step"],
        dqn["reward"],
        linewidth=2,
        label="DQN"
    )

    ax4.set_title(
        "Cumulative Reward"
    )

    ax4.set_xlabel(
        "Simulation Step"
    )

    ax4.grid(True)

    ax4.legend()

    # =========================================================
    # BAR COMPARISON
    # =========================================================

    ax5 = fig.add_subplot(gs[2, 1])

    avg_baseline = np.mean(
        baseline["queue"]
    )

    avg_dqn = np.mean(
        dqn["queue"]
    )

    improvement = (
        (
            avg_baseline - avg_dqn
        ) / avg_baseline
    ) * 100

    bars = ax5.bar(
        ["Fixed-Time", "DQN"],
        [
            avg_baseline,
            avg_dqn
        ]
    )

    for bar, val in zip(
        bars,
        [
            avg_baseline,
            avg_dqn
        ]
    ):

        ax5.text(
            bar.get_x() + bar.get_width()/2,
            bar.get_height(),
            f"{int(val)}",
            ha='center',
            va='bottom',
            fontsize=11
        )

    ax5.set_title(
        f"Queue Reduction = {improvement:.1f}%"
    )

    ax5.set_ylabel(
        "Average Vehicles"
    )

    ax5.grid(True)

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

    print(
        f"Average Waiting Fixed-Time : "
        f"{np.mean(baseline['waiting_time']):.1f}"
    )

    print(
        f"Average Waiting DQN        : "
        f"{np.mean(dqn['waiting_time']):.1f}"
    )

    print()

    print(
        f"Average Speed Fixed-Time : "
        f"{np.mean(baseline['avg_speed']):.2f} m/s"
    )

    print(
        f"Average Speed DQN        : "
        f"{np.mean(dqn['avg_speed']):.2f} m/s"
    )

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