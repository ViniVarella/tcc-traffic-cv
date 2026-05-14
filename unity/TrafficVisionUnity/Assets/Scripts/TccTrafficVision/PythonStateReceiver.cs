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
    }

    public class PythonStateReceiver : MonoBehaviour
    {
        [SerializeField] private string listenHost = "127.0.0.1";
        [SerializeField] private int listenPort = 5004;
        [SerializeField] private VehicleManager vehicleManager;
        [SerializeField] private TrafficLightVisualController trafficLightVisualController;

        private UdpClient udpClient;
        private Thread receiveThread;
        private volatile bool isRunning;
        private readonly object stateLock = new object();
        private readonly Queue<SimulationStateMessage> pendingStates = new Queue<SimulationStateMessage>();
        private int lastAppliedStep = -1;

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
                $"sim_time={stateToApply.sim_time:F2} vehicles={(stateToApply.vehicles == null ? 0 : stateToApply.vehicles.Length)}"
            );

            vehicleManager?.ApplyState(stateToApply.vehicles);
            trafficLightVisualController?.ApplyState(stateToApply.traffic_lights);
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
