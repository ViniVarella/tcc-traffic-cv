using System;
using System.Collections;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;
using TccTrafficVision.CameraCalibration;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace TccTrafficVision
{
    /// <summary>
    /// Captures every calibrated Unity camera after a received SUMO state and
    /// sends one JPEG per camera through length-prefixed TCP connections.
    /// </summary>
    public sealed class TrafficCameraFrameSender : MonoBehaviour
    {
        [SerializeField] private PythonStateReceiver stateReceiver;
        // Kept during the transition from the original single-camera scene.
        // New scenes must use cameraCalibrations.
        [SerializeField, HideInInspector] private TrafficCameraCalibration cameraCalibration;
        [SerializeField] private List<TrafficCameraCalibration> cameraCalibrations = new List<TrafficCameraCalibration>();
        [SerializeField] private string destinationHost = "127.0.0.1";
        [SerializeField] private int destinationPort = 5005;
        [SerializeField, Range(1, 100)] private int jpegQuality = 90;
        [SerializeField] private bool sendInstanceMasks = true;
        [SerializeField, Min(100)] private int connectionTimeoutMilliseconds = 2000;
        [SerializeField] private bool logSuccessfulFrames = true;

        private bool captureScheduled;

        private void Start()
        {
            stateReceiver ??= FindFirstObjectByType<PythonStateReceiver>();
            EnsureCameraCalibrations();
            if (stateReceiver == null || cameraCalibrations.Count == 0)
            {
                Debug.LogError(
                    "TrafficCameraFrameSender needs a PythonStateReceiver and at least one TrafficCameraCalibration.",
                    this);
                enabled = false;
                return;
            }

            stateReceiver.StateApplied += ScheduleCapture;
        }

        private void EnsureCameraCalibrations()
        {
            cameraCalibrations.RemoveAll(calibration => calibration == null || !calibration.CaptureEnabled);
            if (cameraCalibration != null && cameraCalibration.CaptureEnabled && !cameraCalibrations.Contains(cameraCalibration))
            {
                cameraCalibrations.Add(cameraCalibration);
            }

            TrafficCameraCalibration[] discovered = FindObjectsByType<TrafficCameraCalibration>(FindObjectsSortMode.None);
            foreach (TrafficCameraCalibration calibration in discovered)
            {
                if (calibration != null && calibration.CaptureEnabled && !cameraCalibrations.Contains(calibration))
                {
                    cameraCalibrations.Add(calibration);
                }
            }
        }

        private void OnDestroy()
        {
            if (stateReceiver != null)
            {
                stateReceiver.StateApplied -= ScheduleCapture;
            }
        }

        private void ScheduleCapture(SimulationStateMessage state)
        {
            if (captureScheduled)
            {
                Debug.LogWarning($"Skipping frame capture for step {state.step_id}: a capture is already pending.", this);
                return;
            }

            captureScheduled = true;
            StartCoroutine(CaptureAfterFrame(state));
        }

        private IEnumerator CaptureAfterFrame(SimulationStateMessage state)
        {
            yield return new WaitForEndOfFrame();
            captureScheduled = false;

            foreach (TrafficCameraCalibration calibration in cameraCalibrations)
            {
                if (calibration == null)
                {
                    continue;
                }

                byte[] jpeg;
                byte[] maskPng = null;
                GroundTruthVehicle[] annotations;
                try
                {
                    jpeg = CaptureJpeg(calibration);
                    if (sendInstanceMasks)
                    {
                        maskPng = CaptureInstanceMask(calibration, out annotations);
                    }
                    else
                    {
                        annotations = VehicleGroundTruth.Collect(calibration.CameraComponent);
                    }
                }
                catch (Exception exception)
                {
                    Debug.LogError(
                        $"Could not capture frame for camera {calibration.CameraId} at step {state.step_id}: {exception.Message}",
                        this);
                    continue;
                }

                _ = SendFrameAsync(state, calibration.CameraId, jpeg, maskPng, annotations);
            }
        }

        private byte[] CaptureJpeg(TrafficCameraCalibration calibration)
        {
            Camera sourceCamera = calibration.CameraComponent;
            if (sourceCamera == null)
            {
                throw new InvalidOperationException("The calibrated camera has no Camera component.");
            }

            int width = calibration.CaptureWidth;
            int height = calibration.CaptureHeight;
            RenderTexture renderTexture = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);
            Texture2D texture = new Texture2D(width, height, TextureFormat.RGB24, false);
            RenderTexture previousActive = RenderTexture.active;
            try
            {
                RenderCamera(sourceCamera, renderTexture);
                RenderTexture.active = renderTexture;
                texture.ReadPixels(new Rect(0f, 0f, width, height), 0, 0, false);
                texture.Apply(false, false);
                return texture.EncodeToJPG(jpegQuality);
            }
            finally
            {
                RenderTexture.active = previousActive;
                Destroy(texture);
                RenderTexture.ReleaseTemporary(renderTexture);
            }
        }

        private byte[] CaptureInstanceMask(TrafficCameraCalibration calibration, out GroundTruthVehicle[] annotations)
        {
            Camera sourceCamera = calibration.CameraComponent;
            if (sourceCamera == null)
            {
                throw new InvalidOperationException("The calibrated camera has no Camera component.");
            }

            Shader shader = Shader.Find("TccTrafficVision/InstanceMask");
            if (shader == null)
            {
                throw new InvalidOperationException("Could not find the TccTrafficVision/InstanceMask shader.");
            }

            int previousCullingMask = sourceCamera.cullingMask;
            CameraClearFlags previousClearFlags = sourceCamera.clearFlags;
            Color previousBackground = sourceCamera.backgroundColor;
            bool previousAllowMsaa = sourceCamera.allowMSAA;
            Material template = new Material(shader);
            try
            {
                using (InstanceMaskRenderScope scope = InstanceMaskRenderScope.Begin(template))
                {
                    sourceCamera.cullingMask = 1 << InstanceMaskRenderScope.MaskLayer;
                    sourceCamera.clearFlags = CameraClearFlags.SolidColor;
                    sourceCamera.backgroundColor = Color.black;
                    sourceCamera.allowMSAA = false;
                    byte[] png = CapturePng(sourceCamera, calibration.CaptureWidth, calibration.CaptureHeight);
                    annotations = VehicleGroundTruth.Collect(sourceCamera);
                    return png;
                }
            }
            finally
            {
                sourceCamera.cullingMask = previousCullingMask;
                sourceCamera.clearFlags = previousClearFlags;
                sourceCamera.backgroundColor = previousBackground;
                sourceCamera.allowMSAA = previousAllowMsaa;
                Destroy(template);
            }
        }

        private static byte[] CapturePng(Camera sourceCamera, int width, int height)
        {
            RenderTexture renderTexture = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);
            Texture2D texture = new Texture2D(width, height, TextureFormat.RGB24, false, true);
            RenderTexture previousActive = RenderTexture.active;
            try
            {
                RenderCamera(sourceCamera, renderTexture);
                RenderTexture.active = renderTexture;
                texture.ReadPixels(new Rect(0f, 0f, width, height), 0, 0, false);
                texture.Apply(false, false);
                return texture.EncodeToPNG();
            }
            finally
            {
                RenderTexture.active = previousActive;
                Destroy(texture);
                RenderTexture.ReleaseTemporary(renderTexture);
            }
        }

        private static void RenderCamera(Camera sourceCamera, RenderTexture destination)
        {
            UniversalRenderPipeline.SingleCameraRequest request = new UniversalRenderPipeline.SingleCameraRequest
            {
                destination = destination
            };
            if (RenderPipeline.SupportsRenderRequest(sourceCamera, request))
            {
                RenderPipeline.SubmitRenderRequest(sourceCamera, request);
                return;
            }

            RenderTexture previousTarget = sourceCamera.targetTexture;
            try
            {
                sourceCamera.targetTexture = destination;
                sourceCamera.Render();
            }
            finally
            {
                sourceCamera.targetTexture = previousTarget;
            }
        }

        private async Task SendFrameAsync(
            SimulationStateMessage state,
            string cameraId,
            byte[] jpeg,
            byte[] maskPng,
            GroundTruthVehicle[] annotations)
        {
            FrameHeader header = new FrameHeader
            {
                step_id = state.step_id,
                sim_time = state.sim_time,
                camera_id = cameraId,
                image_format = "jpeg",
                payload_size = jpeg.Length,
                mask_format = maskPng == null ? null : "png",
                mask_payload_size = maskPng?.Length ?? 0,
                ground_truth_vehicles = annotations,
            };
            byte[] headerBytes = Encoding.UTF8.GetBytes(JsonUtility.ToJson(header));
            byte[] headerLengthBytes = BitConverter.GetBytes(IPAddress.HostToNetworkOrder(headerBytes.Length));

            try
            {
                using TcpClient client = new TcpClient();
                Task connectTask = client.ConnectAsync(destinationHost, destinationPort);
                if (await Task.WhenAny(connectTask, Task.Delay(connectionTimeoutMilliseconds)) != connectTask)
                {
                    throw new TimeoutException($"TCP connection to {destinationHost}:{destinationPort} timed out.");
                }

                await connectTask;
                using NetworkStream stream = client.GetStream();
                await stream.WriteAsync(headerLengthBytes, 0, headerLengthBytes.Length);
                await stream.WriteAsync(headerBytes, 0, headerBytes.Length);
                await stream.WriteAsync(jpeg, 0, jpeg.Length);
                if (maskPng != null)
                {
                    await stream.WriteAsync(maskPng, 0, maskPng.Length);
                }
                await stream.FlushAsync();

                if (logSuccessfulFrames)
                {
                    Debug.Log(
                        $"Unity sent frame: camera={header.camera_id} step_id={header.step_id} " +
                        $"jpeg_bytes={header.payload_size} mask_bytes={header.mask_payload_size}",
                        this);
                }
            }
            catch (Exception exception)
            {
                Debug.LogWarning(
                    $"Could not send frame for step {state.step_id} to {destinationHost}:{destinationPort}: {exception.Message}",
                    this);
            }
        }

        [Serializable]
        private sealed class FrameHeader
        {
            public int step_id;
            public float sim_time;
            public string camera_id;
            public string image_format;
            public int payload_size;
            public string mask_format;
            public int mask_payload_size;
            public GroundTruthVehicle[] ground_truth_vehicles;
        }
    }
}
