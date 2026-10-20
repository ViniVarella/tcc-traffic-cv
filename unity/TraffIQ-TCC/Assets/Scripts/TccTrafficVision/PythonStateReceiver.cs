using System;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

namespace TccTrafficVision
{
    [Serializable]
    public class VehicleStateMessage
    {
        public string id;
        public float x;
        public float y;
        public float z;
        public float angle;
        public float speed;
        public string type;
    }

    [Serializable]
    public class PedestrianStateMessage
    {
        public string id;
        public float x;
        public float y;
        public float z;
        public float angle;
        public float speed;
    }

    [Serializable]
    public class TrafficLightStateMessage
    {
        public string id;
        public int phase;
        public string state;
    }

    [Serializable]
    public class SimulationStateMessage
    {
        public int step;
        public int step_id;
        public float sim_time;
        public VehicleStateMessage[] vehicles;
        public TrafficLightStateMessage[] traffic_lights;
        // Empty (or absent, from older senders) on the network without pedestrians.
        public PedestrianStateMessage[] pedestrians;
        // Large states (with pedestrians) exceed the macOS UDP datagram limit
        // and arrive split: part 0..parts-1, each with a share of vehicles and
        // pedestrians. Absent (0) in a state sent whole.
        public int part;
        public int parts;
    }

    public class PythonStateReceiver : MonoBehaviour
    {
        [SerializeField] private string listenHost = "127.0.0.1";
        [SerializeField] private int listenPort = 5004;
        [SerializeField] private VehicleManager vehicleManager;
        [SerializeField] private TrafficLightVisualController trafficLightVisualController;
        [SerializeField] private PedestrianManager pedestrianManager;

        private UdpClient udpClient;
        private Thread receiveThread;
        private volatile bool isRunning;
        private readonly object stateLock = new object();
        private readonly Queue<SimulationStateMessage> pendingStates = new Queue<SimulationStateMessage>();
        private int lastAppliedStep = -1;
        private int assemblingStep = -1;
        private readonly List<SimulationStateMessage> assemblingParts = new List<SimulationStateMessage>();

        /// <summary>
        /// Raised on the Unity main thread after all visual consumers received a
        /// new SUMO state. Frame capture components use this to associate one
        /// rendered image with the exact step that produced it.
        /// </summary>
        public event Action<SimulationStateMessage> StateApplied;

        private void Start()
        {
            if (vehicleManager == null)
            {
                vehicleManager = FindFirstObjectByType<VehicleManager>();
            }

            if (trafficLightVisualController == null)
            {
                trafficLightVisualController = FindFirstObjectByType<TrafficLightVisualController>();
            }

            if (pedestrianManager == null)
            {
                pedestrianManager = FindFirstObjectByType<PedestrianManager>();
            }

            udpClient = new UdpClient(listenPort);
            isRunning = true;
            receiveThread = new Thread(ReceiveLoop) { IsBackground = true };
            receiveThread.Start();

            Debug.Log($"PythonStateReceiver listening on {listenHost}:{listenPort}");
        }

        private void Update()
        {
            SimulationStateMessage stateToApply = null;
            lock (stateLock)
            {
                if (pendingStates.Count > 0)
                {
                    stateToApply = pendingStates.Dequeue();
                }
            }

            if (stateToApply == null || stateToApply.step_id == lastAppliedStep)
            {
                return;
            }

            lastAppliedStep = stateToApply.step_id;
            Debug.Log(
                $"Unity received state: step={stateToApply.step} step_id={stateToApply.step_id} " +
                $"sim_time={stateToApply.sim_time:F2} vehicles={(stateToApply.vehicles == null ? 0 : stateToApply.vehicles.Length)} " +
                $"pedestrians={(stateToApply.pedestrians == null ? 0 : stateToApply.pedestrians.Length)}"
            );

            vehicleManager?.ApplyState(stateToApply.vehicles);
            trafficLightVisualController?.ApplyState(stateToApply.traffic_lights);
            pedestrianManager?.ApplyState(stateToApply.pedestrians);
            StateApplied?.Invoke(stateToApply);
        }

        private void ReceiveLoop()
        {
            try
            {
                while (isRunning)
                {
                    var remoteEndPoint = new System.Net.IPEndPoint(System.Net.IPAddress.Any, 0);
                    byte[] payload = udpClient.Receive(ref remoteEndPoint);
                    string json = Encoding.UTF8.GetString(payload);
                    var state = JsonUtility.FromJson<SimulationStateMessage>(json);

                    if (state == null)
                    {
                        Debug.LogWarning("Unity received invalid state JSON.");
                        continue;
                    }

                    state = AssembleParts(state);
                    if (state == null)
                    {
                        continue;
                    }

                    lock (stateLock)
                    {
                        pendingStates.Enqueue(state);
                    }
                }
            }
            catch (SocketException)
            {
                if (isRunning)
                {
                    Debug.LogWarning("PythonStateReceiver socket closed unexpectedly.");
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"PythonStateReceiver failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Returns the complete state once every part of its step arrived, or null
        /// while parts are missing. A part of a newer step drops the incomplete one.
        /// Runs only on the receive thread.
        /// </summary>
        private SimulationStateMessage AssembleParts(SimulationStateMessage state)
        {
            if (state.parts <= 1)
            {
                return state;
            }

            if (state.step_id != assemblingStep)
            {
                if (assemblingParts.Count > 0)
                {
                    Debug.LogWarning(
                        $"PythonStateReceiver dropped step_id={assemblingStep}: " +
                        $"{assemblingParts.Count} of {assemblingParts[0].parts} parts received.");
                }

                assemblingStep = state.step_id;
                assemblingParts.Clear();
            }

            assemblingParts.Add(state);
            if (assemblingParts.Count < state.parts)
            {
                return null;
            }

            var vehicles = new List<VehicleStateMessage>();
            var pedestrians = new List<PedestrianStateMessage>();
            foreach (SimulationStateMessage part in assemblingParts)
            {
                if (part.vehicles != null)
                {
                    vehicles.AddRange(part.vehicles);
                }

                if (part.pedestrians != null)
                {
                    pedestrians.AddRange(part.pedestrians);
                }
            }

            state.vehicles = vehicles.ToArray();
            state.pedestrians = pedestrians.ToArray();
            state.part = 0;
            state.parts = 1;
            assemblingParts.Clear();
            assemblingStep = -1;
            return state;
        }

        private void OnDestroy()
        {
            isRunning = false;
            udpClient?.Close();

            if (receiveThread != null && receiveThread.IsAlive)
            {
                receiveThread.Join(250);
            }
        }
    }
}
