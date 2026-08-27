using TccTrafficVision.CameraCalibration;
using TccTrafficVision;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.CameraCalibration
{
    /// <summary>
    /// Creates disabled SP traffic cameras. Their poses are starting points;
    /// the ROI editor remains the authority for final visual calibration.
    /// </summary>
    public static class SpSouthCameraSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string CamerasRootName = "SP Traffic Cameras";
        private const string SouthCameraName = "SP Camera South";
        private const string EastCameraName = "SP Camera East";
        private const string WestCameraName = "SP Camera West";

        [MenuItem("Traffic Vision/Cameras/Create SP South Camera")]
        public static void CreateOrConfigureCamera()
        {
            CreateOrConfigureCamera(new CameraDefinition(
                "south",
                SouthCameraName,
                new Vector3(4.8f, 5.25f, -13.2f),
                new Vector3(22.613f, -160f, 0f)));
        }

        [MenuItem("Traffic Vision/Cameras/Create SP East Camera")]
        public static void CreateOrConfigureEastCamera()
        {
            CreateOrConfigureCamera(new CameraDefinition(
                "east",
                EastCameraName,
                new Vector3(12.1f, 5.07f, -1.6f),
                new Vector3(21.1f, 130f, 0f)));
        }

        [MenuItem("Traffic Vision/Cameras/Create SP West Camera")]
        public static void CreateOrConfigureWestCamera()
        {
            CreateOrConfigureCamera(new CameraDefinition(
                "west",
                WestCameraName,
                new Vector3(-17.46f, 5f, -4.75f),
                new Vector3(25.153f, -48.282f, -1.867f)));
        }

        private static void CreateOrConfigureCamera(CameraDefinition definition)
        {
            Scene scene = SceneManager.GetActiveScene();
            if (scene.path != SceneAssetPath)
            {
                EditorUtility.DisplayDialog(
                    "Open the SP import scene",
                    "Open Assets/Scenes/SPImport.unity before creating a traffic camera.",
                    "OK");
                return;
            }

            GameObject camerasRoot = FindOrCreate(CamerasRootName, null);
            GameObject cameraObject = FindOrCreate(definition.objectName, camerasRoot.transform);
            Camera trafficCamera = EnsureCamera(cameraObject);
            if (trafficCamera == null)
            {
                Debug.LogError("Could not add a Camera component to the SP south camera.", cameraObject);
                return;
            }

            TrafficCameraCalibration calibration = GetOrAdd<TrafficCameraCalibration>(cameraObject);

            ConfigureCamera(trafficCamera, definition);
            ConfigureCalibration(calibration, definition.cameraId);
            ConfigureFrameSender(calibration);

            EditorSceneManager.MarkSceneDirty(scene);
            Selection.activeGameObject = cameraObject;
            Debug.Log(
                $"SP {definition.cameraId} camera configured. Select it, open Traffic Vision > Camera ROI Calibration, " +
                "then use Render preview and define the approach and lane ROIs.",
                cameraObject);
        }

        private static void ConfigureCamera(Camera trafficCamera, CameraDefinition definition)
        {
            trafficCamera.transform.SetPositionAndRotation(
                definition.position,
                Quaternion.Euler(definition.rotationEulerDegrees));
            trafficCamera.orthographic = false;
            trafficCamera.fieldOfView = 48f;
            trafficCamera.nearClipPlane = 0.1f;
            trafficCamera.farClipPlane = 250f;
            trafficCamera.clearFlags = CameraClearFlags.SolidColor;
            trafficCamera.backgroundColor = new Color(0.12f, 0.16f, 0.2f);
            trafficCamera.enabled = false;
        }

        private static void ConfigureCalibration(TrafficCameraCalibration calibration, string cameraId)
        {
            SerializedObject serializedCalibration = new SerializedObject(calibration);
            serializedCalibration.FindProperty("cameraId").stringValue = cameraId;
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
                    "SP traffic camera was created without a PythonStateReceiver. " +
                    "Run Traffic Vision > SUMO > Configure SP Dynamic Sync before testing frame capture.",
                    calibration);
                return;
            }

            TrafficCameraFrameSender sender = receiver.GetComponent<TrafficCameraFrameSender>() ??
                                              receiver.gameObject.AddComponent<TrafficCameraFrameSender>();
            SerializedObject serializedSender = new SerializedObject(sender);
            serializedSender.FindProperty("stateReceiver").objectReferenceValue = receiver;
            SerializedProperty calibrations = serializedSender.FindProperty("cameraCalibrations");
            AddCalibrationIfMissing(calibrations, serializedSender.FindProperty("cameraCalibration").objectReferenceValue);
            AddCalibrationIfMissing(calibrations, calibration);
            serializedSender.FindProperty("destinationHost").stringValue = "127.0.0.1";
            serializedSender.FindProperty("destinationPort").intValue = 5005;
            serializedSender.ApplyModifiedPropertiesWithoutUndo();
        }

        private static void AddCalibrationIfMissing(SerializedProperty calibrations, Object calibration)
        {
            if (calibration == null)
            {
                return;
            }

            for (int index = 0; index < calibrations.arraySize; index++)
            {
                if (calibrations.GetArrayElementAtIndex(index).objectReferenceValue == calibration)
                {
                    return;
                }
            }

            int newIndex = calibrations.arraySize;
            calibrations.arraySize++;
            calibrations.GetArrayElementAtIndex(newIndex).objectReferenceValue = calibration;
        }

        private readonly struct CameraDefinition
        {
            public readonly string cameraId;
            public readonly string objectName;
            public readonly Vector3 position;
            public readonly Vector3 rotationEulerDegrees;

            public CameraDefinition(string cameraId, string objectName, Vector3 position, Vector3 rotationEulerDegrees)
            {
                this.cameraId = cameraId;
                this.objectName = objectName;
                this.position = position;
                this.rotationEulerDegrees = rotationEulerDegrees;
            }
        }
    }
}
