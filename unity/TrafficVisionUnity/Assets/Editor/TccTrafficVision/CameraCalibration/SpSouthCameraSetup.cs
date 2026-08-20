using TccTrafficVision.CameraCalibration;
using TccTrafficVision;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.CameraCalibration
{
    /// <summary>
    /// Creates an initial, disabled traffic camera for the south approach of the
    /// SP scenario. Its pose is intentionally a starting point: the ROI editor
    /// is the authority for the final visual calibration.
    /// </summary>
    public static class SpSouthCameraSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string CamerasRootName = "SP Traffic Cameras";
        private const string SouthCameraName = "SP Camera South";

        [MenuItem("Traffic Vision/Cameras/Create SP South Camera")]
        public static void CreateOrConfigureCamera()
        {
            Scene scene = SceneManager.GetActiveScene();
            if (scene.path != SceneAssetPath)
            {
                EditorUtility.DisplayDialog(
                    "Open the SP import scene",
                    "Open Assets/Scenes/SPImport.unity before creating the south traffic camera.",
                    "OK");
                return;
            }

            GameObject camerasRoot = FindOrCreate(CamerasRootName, null);
            GameObject cameraObject = FindOrCreate(SouthCameraName, camerasRoot.transform);
            Camera trafficCamera = EnsureCamera(cameraObject);
            if (trafficCamera == null)
            {
                Debug.LogError("Could not add a Camera component to the SP south camera.", cameraObject);
                return;
            }

            TrafficCameraCalibration calibration = GetOrAdd<TrafficCameraCalibration>(cameraObject);

            ConfigureCamera(trafficCamera);
            ConfigureCalibration(calibration);
            ConfigureFrameSender(calibration);

            EditorSceneManager.MarkSceneDirty(scene);
            Selection.activeGameObject = cameraObject;
            Debug.Log(
                "SP south camera configured. Select it, open Traffic Vision > Camera ROI Calibration, " +
                "then use Render preview and define the approach and lane ROIs.",
                cameraObject);
        }

        private static void ConfigureCamera(Camera trafficCamera)
        {
            // The south approach is negative Z. This roadside pose was chosen
            // visually in the SP scene: it frames the stop line and incoming
            // queues from beside the entry. The calibration tool renders a
            // disabled copy of this camera.
            Vector3 position = new Vector3(2.984f, 5.25f, -16.34f);
            Quaternion rotation = Quaternion.Euler(28.462f, -160f, 0f);
            trafficCamera.transform.SetPositionAndRotation(position, rotation);
            trafficCamera.orthographic = false;
            trafficCamera.fieldOfView = 48f;
            trafficCamera.nearClipPlane = 0.1f;
            trafficCamera.farClipPlane = 250f;
            trafficCamera.clearFlags = CameraClearFlags.SolidColor;
            trafficCamera.backgroundColor = new Color(0.12f, 0.16f, 0.2f);
            trafficCamera.enabled = false;
        }

        private static void ConfigureCalibration(TrafficCameraCalibration calibration)
        {
            SerializedObject serializedCalibration = new SerializedObject(calibration);
            serializedCalibration.FindProperty("cameraId").stringValue = "south";
            serializedCalibration.FindProperty("captureWidth").intValue = 1280;
            serializedCalibration.FindProperty("captureHeight").intValue = 720;
            serializedCalibration.ApplyModifiedPropertiesWithoutUndo();
        }

        private static GameObject FindOrCreate(string objectName, Transform parent)
        {
            GameObject existing = GameObject.Find(objectName);
            if (existing != null)
            {
                if (parent != null && existing.transform.parent != parent)
                {
                    existing.transform.SetParent(parent, false);
                }

                return existing;
            }

            GameObject created = new GameObject(objectName);
            if (parent != null)
            {
                created.transform.SetParent(parent, false);
            }

            return created;
        }

        private static T GetOrAdd<T>(GameObject gameObject) where T : Component
        {
            return gameObject.GetComponent<T>() ?? gameObject.AddComponent<T>();
        }

        private static Camera EnsureCamera(GameObject cameraObject)
        {
            Camera existing = cameraObject.GetComponent<Camera>();
            if (existing != null)
            {
                return existing;
            }

            return Undo.AddComponent<Camera>(cameraObject);
        }

        private static void ConfigureFrameSender(TrafficCameraCalibration calibration)
        {
            PythonStateReceiver receiver = Object.FindFirstObjectByType<PythonStateReceiver>();
            if (receiver == null)
            {
                Debug.LogWarning(
                    "SP south camera was created without a PythonStateReceiver. " +
                    "Run Traffic Vision > SUMO > Configure SP Dynamic Sync before testing frame capture.",
                    calibration);
                return;
            }

            TrafficCameraFrameSender sender = receiver.GetComponent<TrafficCameraFrameSender>() ??
                                              receiver.gameObject.AddComponent<TrafficCameraFrameSender>();
            SerializedObject serializedSender = new SerializedObject(sender);
            serializedSender.FindProperty("stateReceiver").objectReferenceValue = receiver;
            serializedSender.FindProperty("cameraCalibration").objectReferenceValue = calibration;
            serializedSender.FindProperty("destinationHost").stringValue = "127.0.0.1";
            serializedSender.FindProperty("destinationPort").intValue = 5005;
            serializedSender.ApplyModifiedPropertiesWithoutUndo();
        }
    }
}
