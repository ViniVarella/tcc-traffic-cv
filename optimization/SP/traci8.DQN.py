# =============================================================================
# Deep Q-Network (DQN) for Traffic Signal Control — SUMO/TraCI
# =============================================================================
# Implements the canonical DQN algorithm (Mnih et al., 2015) with:
#   - Experience Replay Buffer
#   - Target Network (frozen, periodically synced)
#   - Epsilon-greedy policy with decay
#
# Key references:
#   Mnih et al. (2015) "Human-level control through deep reinforcement
#       learning." Nature, 518, 529–533.
#   Genders & Razavi (2016) "Using a deep reinforcement learning agent
#       for traffic signal control." arXiv:1611.01142
#   Van Hasselt et al. (2016) "Deep Reinforcement Learning with Double
#       Q-learning." AAAI 2016. [optional extension — see bottom of file]
# =============================================================================

# Step 1: Standard library imports
import os
import sys
import random
from collections import deque  # Efficient fixed-size FIFO buffer

import numpy as np
import matplotlib.pyplot as plt

# Step 1.1: Deep learning framework
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers

# Reproducibility
SEED = 42
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)

# =============================================================================
# Step 2: SUMO environment setup
# =============================================================================
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import traci

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

Sumo_config = [
    'sumo',
    '-c', os.path.join(SCRIPT_DIR, 'Cruzamento.sumocfg'),
    '--step-length', '1.0',
    '--lateral-resolution', '0',
    '--no-warnings', 'true',
]


# =============================================================================
# Step 3: Hyperparameters
# =============================================================================

# --- Simulation ---
TOTAL_STEPS    = 15000   # Total simulation steps (online training horizon)

# --- DQN core ---
GAMMA          = 0.9     # Discount factor γ ∈ [0,1]
#                          γ→0: myopic (immediate reward only)
#                          γ→1: far-sighted (long-term return)

LEARNING_RATE  = 0.001   # Adam optimizer learning rate
#                          NOTE: Do NOT apply a manual α multiplier on top of
#                          the Bellman target — Adam already handles step sizes.

BATCH_SIZE     = 32      # Mini-batch size sampled from the replay buffer
#                          Mnih et al. used 32. Smaller → noisier gradients;
#                          larger → slower but more stable updates.

# --- Experience Replay ---
REPLAY_BUFFER_SIZE = 50000  # Maximum number of transitions stored
#                              Once full, oldest transitions are discarded (FIFO).
MIN_REPLAY_SIZE    = 3000    # Minimum transitions before training starts
#                              Ensures the first mini-batch is representative.

# --- Target Network ---
TARGET_UPDATE_FREQ = 1000    # Steps between target network weight syncs
#                              Low → target moves often → instability
#                              High → slow adaptation
#                              Mnih et al. used 10 000 (longer episodes).

# --- Epsilon-greedy with decay ---
EPSILON_START  = 1.0     # Initial exploration rate (fully random)
EPSILON_MIN    = 0.05    # Floor — agent still explores 5% of the time
EPSILON_DECAY  = 0.999    # Multiplicative decay applied per DECISION (not per sim step)
#                          ε(t) = max(EPSILON_MIN, EPSILON_START * decay^t)

# --- Traffic-signal stability ---
MIN_GREEN_STEPS = 20    # Minimum sim steps between phase switches (avoids flicker)

# --- Action repeat ---
DECISION_INTERVAL = 5   # The agent picks an action every N sim steps; the action
#                         is held for the whole interval and the reward accumulated.
#                         Removes redundant no-op transitions when MIN_GREEN blocks switches.

# --- Problem dimensions ---
DETECTORS = [
    "e2_0",   # E6_0  (WB approach)
    "e2_5",   # E2_1  (EB approach, lane 1)
    "e2_6",   # E2_0  (EB approach, lane 0)
    "e2_1",   # E3_2  (NB approach, lane 2)
    "e2_2",   # E3_3  (NB approach, lane 3)
    "e2_3",   # E3_1  (NB approach, lane 1)
    "e2_4",   # E3_0  (NB approach, lane 0)
]
NUM_PHASES  = 5          # TLS program has 5 phases (0..4); see Cruzamento.net.xml
STATE_SIZE = len(DETECTORS) * 3 + NUM_PHASES  # (queue, halting, occupancy) per detector + one-hot phase
ACTION_SIZE = 2          # 0 = keep current phase | 1 = switch to next phase
ACTIONS     = [0, 1]

# =============================================================================
# Step 4: Detector & TLS identifiers
# =============================================================================
TLS_ID = "clusterJ0_J14_J2_J7"

# logic = traci.trafficlight.getAllProgramLogics(TLS_ID)[0]

# for i, phase in enumerate(logic.phases):

#     print(f"\nPhase {i}")
#     print("Duration:", phase.duration)
#     print("State:", phase.state)
#     print("-" * 30)

# =============================================================================
# Step 5: Neural network architecture
# =============================================================================

def build_model(state_size: int, action_size: int) -> keras.Model:
    """
    Builds a fully-connected Q-network.

    Architecture (Mnih et al. used convolutional layers for pixel input;
    for low-dimensional state vectors a 2-layer MLP is standard):
        Input  → Dense(64, ReLU) → Dense(64, ReLU) → Dense(action_size, linear)

    The output layer has *linear* activation because Q-values are unbounded.
    Loss = MSE between predicted Q(s,a) and the Bellman target.
    """
    model = keras.Sequential([
        layers.Input(shape=(state_size,)),
        layers.Dense(128, activation='relu'),
        layers.Dense(128, activation='relu'),
        layers.Dense(64, activation='relu'),
        layers.Dense(action_size, activation='linear'),
    ])
    model.compile(
        loss=keras.losses.Huber(),
        optimizer=keras.optimizers.Adam(learning_rate=LEARNING_RATE,clipnorm=1.0)
    )
    return model


# Main network — updated every step (after warm-up)
online_network = build_model(STATE_SIZE, ACTION_SIZE)

# Target network — weights frozen; synced with online_network every TARGET_UPDATE_FREQ steps
target_network = build_model(STATE_SIZE, ACTION_SIZE)
target_network.set_weights(online_network.get_weights())  # Initial sync

print("Online network architecture:")
online_network.summary()

# =============================================================================
# Step 6: Experience Replay Buffer
# =============================================================================
# A deque with maxlen automatically discards the oldest element when full.
# Each element is a tuple: (state, action, reward, next_state, done)
# 'done' signals episode termination — here every step is within one episode,
# so done=False always, but included for generality.

replay_buffer = deque(maxlen=REPLAY_BUFFER_SIZE)


def store_transition(state, action, reward, next_state, done=False):
    """Append one transition to the replay buffer."""
    replay_buffer.append((state, action, reward, next_state, done))


# =============================================================================
# Step 7: Helper functions
# =============================================================================

def state_to_array(state_tuple) -> np.ndarray:
    """Convert state tuple → (1, STATE_SIZE) float32 array for model input."""
    return np.array(state_tuple, dtype=np.float32).reshape(1, -1)


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

    # One-hot encoding of the current phase. A scalar (phase/10) would imply a
    # spurious ordinal relationship between phases; one-hot lets the network treat
    # each phase as an independent category.
    phase = traci.trafficlight.getPhase(TLS_ID)
    phase_onehot = [0.0] * NUM_PHASES
    if 0 <= phase < NUM_PHASES:
        phase_onehot[phase] = 1.0
    state.extend(phase_onehot)

    return tuple(state)


prev_total_wait = 0.0  # running total accumulated waiting time (set per episode)


def get_reward(state, action):
    """
    Reward based on the *reduction* of accumulated waiting time between steps
    (delta reward) plus a small penalty on standing queues/occupancy.

    Delta rewards have lower variance than absolute-level rewards and align the
    learning signal directly with "did this action reduce congestion?".
    """
    global prev_total_wait

    total_queue = 0.0
    total_occupancy = 0.0

    # Detector block excludes the trailing NUM_PHASES one-hot entries.
    values = list(state[:-NUM_PHASES])
    for i in range(0, len(values), 3):
        total_queue += values[i]
        total_occupancy += values[i + 2]

    total_waiting = 0.0
    for veh in traci.vehicle.getIDList():
        total_waiting += traci.vehicle.getWaitingTime(veh) / 100.0

    # Positive when accumulated waiting time went down vs. previous step.
    delta_wait = prev_total_wait - total_waiting
    prev_total_wait = total_waiting

    reward = (
        delta_wait * 1.0
        - total_queue * 0.5
        - total_occupancy * 0.5
    )

    # penaliza troca excessiva
    if action == 1:
        reward -= 0.3

    return float(reward)

last_switch_step = -MIN_GREEN_STEPS  # initialise before training loop


def apply_action(action: int, current_step: int):
    """
    Execute the chosen action on the traffic light.
    Constraint 5: enforce MIN_GREEN_STEPS between consecutive phase switches
    to prevent rapid oscillation (green-time guarantee).
    """
    global last_switch_step

    if action == 0:
        return  # keep current phase

    # action == 1: switch phase only if minimum green time has elapsed
    if current_step - last_switch_step >= MIN_GREEN_STEPS:
        GREEN_PHASES = [0, 3]  # phases 0 and 3 are the green phases (2 is all-red)
        current_phase = traci.trafficlight.getPhase(TLS_ID)
        if current_phase == GREEN_PHASES[0]:
            traci.trafficlight.setPhase(TLS_ID, GREEN_PHASES[1])
        else:
            traci.trafficlight.setPhase(TLS_ID, GREEN_PHASES[0])
        last_switch_step = current_step


def get_action(state: tuple, epsilon: float) -> int:
    """
    Epsilon-greedy action selection.
    Constraint 7: balance exploration (random) and exploitation (greedy).

    With probability ε  → random action (exploration)
    With probability 1-ε → argmax Q(s,·) from online_network (exploitation)
    """
    if random.random() < epsilon:
        return random.choice(ACTIONS)
    state_tensor = tf.convert_to_tensor(
        state_to_array(state),
        dtype=tf.float32
    )

    q_values = online_network(
        state_tensor,
        training=False
    ).numpy()[0]
    return int(np.argmax(q_values))


def train_online_network():
    """
    Sample a random mini-batch from the replay buffer and perform one
    gradient-descent step on the online network.

    Bellman target (standard DQN):
        y = r                          if done
        y = r + γ · max_a' Q_target(s', a')   otherwise

    Using the TARGET network for the bootstrap estimate stabilises training
    because the target does not change every step.

    Constraint 6: Q-value update via gradient descent on MSE loss.
    """
    if len(replay_buffer) < MIN_REPLAY_SIZE:
        return  # not enough data yet — skip training

    # Sample a random mini-batch
    batch = random.sample(replay_buffer, BATCH_SIZE)
    states, actions, rewards, next_states, dones = zip(*batch)

    # Vectorise for efficient batch inference
    states_arr      = np.array(states,      dtype=np.float32)   # (BATCH, STATE_SIZE)
    next_states_arr = np.array(next_states, dtype=np.float32)   # (BATCH, STATE_SIZE)
    rewards_arr     = np.array(rewards,     dtype=np.float32)   # (BATCH,)
    dones_arr       = np.array(dones,       dtype=np.float32)   # (BATCH,)

    # Q(s,·) from online network — shape (BATCH, ACTION_SIZE)
    q_current = online_network(
        states_arr,
        training=False
    ).numpy()

    # max_a' Q_target(s', a') from TARGET network — shape (BATCH,)
    q_next_target = target_network(
        next_states_arr,
        training=False
    ).numpy()
    best_actions = np.argmax(
        online_network(
            next_states_arr,
            training=False
        ).numpy(),
        axis=1
    )
    max_q_next = q_next_target[
        np.arange(BATCH_SIZE),
        best_actions
    ]

    # Bellman targets for the taken action only (vectorised).
    # (1 - done) zeroes the bootstrap term on terminal transitions.
    idx = np.arange(BATCH_SIZE)
    actions_arr = np.array(actions, dtype=np.int64)
    targets = q_current.copy()
    targets[idx, actions_arr] = rewards_arr + GAMMA * max_q_next * (1.0 - dones_arr)

    # Single gradient step — train_on_batch avoids the per-call overhead of fit().
    online_network.train_on_batch(states_arr, targets)


# =============================================================================
# Step 8: Training loop
# =============================================================================

step_history      = []
reward_history    = []
queue_history     = []
epsilon_history   = []

cumulative_reward = 0.0
epsilon           = EPSILON_START

eval_history      = []  # (episode, greedy cumulative reward) from periodic evaluation

EPISODES = 20
STEPS_PER_EPISODE = 1000
EVAL_EVERY = 5  # run a greedy evaluation every N episodes


def evaluate_greedy(num_steps: int = STEPS_PER_EPISODE) -> float:
    """
    Run one greedy (ε=0, no learning) rollout to measure true policy quality,
    decoupled from the exploration noise present during training.
    """
    global prev_total_wait, last_switch_step
    traci.start(Sumo_config)
    last_switch_step = -MIN_GREEN_STEPS
    prev_total_wait = 0.0
    total_reward = 0.0
    state = get_state()
    sim_step = 0
    while sim_step < num_steps:
        action = get_action(state, epsilon=0.0)  # pure exploitation
        apply_action(action, current_step=sim_step)
        done = False
        for _ in range(DECISION_INTERVAL):
            traci.simulationStep()
            sim_step += 1
            if sim_step >= 100 and traci.simulation.getMinExpectedNumber() <= 0:
                done = True
                break
        state = get_state()
        total_reward += get_reward(state, action)
        if done:
            break
    traci.close()
    return total_reward


print("\n=== Starting DQN Training ===")
print(f"Replay buffer warms up for {MIN_REPLAY_SIZE} transitions before training begins.\n")

global_step = 0  # monotonic counter across all episodes (drives target sync)

for episode in range(EPISODES):

    traci.start(Sumo_config)

    last_switch_step = -MIN_GREEN_STEPS
    prev_total_wait  = 0.0
    cumulative_reward = 0.0

    state = get_state()
    sim_step = 0

    while sim_step < STEPS_PER_EPISODE:

        # --- Select action (held for DECISION_INTERVAL sim steps) ---
        action = get_action(state, epsilon)
        apply_action(action, current_step=sim_step)

        # --- Advance simulation, accumulating reward over the interval ---
        done = False
        for _ in range(DECISION_INTERVAL):
            traci.simulationStep()
            sim_step += 1
            global_step += 1
            if sim_step >= 100 and traci.simulation.getMinExpectedNumber() <= 0:
                done = True
                break

        # --- Observe outcome ---
        next_state = get_state()
        reward     = get_reward(next_state, action)
        cumulative_reward += reward

        # --- Store transition ---
        store_transition(state, action, reward, next_state, done)

        # --- Learn from replay buffer ---
        train_online_network()

        # --- Sync target network periodically (uses the global step counter) ---
        if global_step % TARGET_UPDATE_FREQ < DECISION_INTERVAL:
            target_network.set_weights(online_network.get_weights())
            print(f"  [GlobalStep {global_step:>6}] Target network synced. ε={epsilon:.4f}")

        # --- Decay epsilon (per decision, not per sim step) ---
        epsilon = max(EPSILON_MIN, epsilon * EPSILON_DECAY)

        # --- Logging (roughly every 100 sim steps) ---
        if sim_step % 100 < DECISION_INTERVAL:
            q_vals = online_network(state_to_array(state), training=False).numpy()[0]
            total_q = sum(next_state[i] for i in range(0, len(next_state[:-NUM_PHASES]), 3))
            print(
                f"Episode={episode+1} | "
                f"Step={sim_step:>5} | "
                f"ε={epsilon:.4f} | "
                f"Reward={reward:.2f} | "
                f"TotalQ={total_q:.2f} | "
                f"CumReward={cumulative_reward:.1f} | "
                f"Buffer={len(replay_buffer)} | "
                f"Q={np.round(q_vals, 2)}"
            )
            step_history.append(global_step)
            reward_history.append(cumulative_reward)
            queue_history.append(total_q)
            epsilon_history.append(epsilon)

        state = next_state
        if done:
            print(f"\nEpisode {episode+1} finished early.")
            break

    print(f"\nEpisode {episode+1} finished. CumReward={cumulative_reward:.1f}")
    traci.close()

    # --- Periodic greedy evaluation ---
    if (episode + 1) % EVAL_EVERY == 0:
        eval_reward = evaluate_greedy()
        eval_history.append((episode + 1, eval_reward))
        print(f"  >> Greedy eval after episode {episode+1}: CumReward={eval_reward:.1f}")

# =============================================================================
# Step 9: Close SUMO
# =============================================================================
print("\nTraining complete.")
print("Online network summary:")
online_network.summary()

# =============================================================================
# Step 10: Save trained model
# =============================================================================
online_network.save("dqn_traffic_model.keras")
print("Model saved to dqn_traffic_model.keras")

# =============================================================================
# Step 11: Visualisation
# =============================================================================

fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

axes[0].plot(step_history, reward_history, linewidth=1.5)
axes[0].set_ylabel("Cumulative Reward")
axes[0].set_title("DQN Training — Traffic Signal Control (SUMO)")
axes[0].grid(True, alpha=0.4)

axes[1].plot(step_history, queue_history, color='tab:orange', linewidth=1.5)
axes[1].set_ylabel("Total Queue Length (vehicles)")
axes[1].grid(True, alpha=0.4)

axes[2].plot(step_history, epsilon_history, color='tab:green', linewidth=1.5)
axes[2].set_ylabel("Epsilon (ε)")
axes[2].set_xlabel("Simulation Step")
axes[2].grid(True, alpha=0.4)

plt.tight_layout()
plt.savefig("dqn_training_results.png", dpi=150)
plt.show()
print("Plot saved to dqn_training_results.png")

# =============================================================================
# NOTE: Double DQN is ALREADY active in train_online_network():
#   action *selection* uses the online network (best_actions) while action
#   *evaluation* uses the target network (q_next_target). This corrects the
#   overestimation bias of vanilla DQN.
# Reference: Van Hasselt, H., Guez, A., & Silver, D. (2016).
#   "Deep Reinforcement Learning with Double Q-learning." AAAI 2016.
#
# Possible further extensions: Dueling DQN architecture, Prioritized Experience
# Replay, n-step returns, and richer action space (per-phase green-time control).
# =============================================================================