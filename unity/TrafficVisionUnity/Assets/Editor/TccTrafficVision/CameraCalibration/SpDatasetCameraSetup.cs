using System.Collections.Generic;
using TccTrafficVision.CameraCalibration;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.CameraCalibration
{
    /// <summary>
    /// Creates plausible camera-pose variants for synthetic detection training.
    /// They are deliberately excluded from normal TCP capture until the dataset
    /// profile is enabled from this menu.
    /// </summary>
    public static class SpDatasetCameraSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string RootName = "SP Dataset Cameras";

        private static readonly CameraDefinition[] Definitions =
        {
            // In this scene's orientation, inward aim requires the opposite
            // yaw signs: left turns right (-12°) and right turns left (+12°).
            new CameraDefinition("south_ds_left", "SP Dataset South Left", new Vector3(0.5f, 6.8f, -9.5f), new Vector3(28f, -157f, 0f), 45f),
            new CameraDefinition("south_ds_right", "SP Dataset South Right", new Vector3(9.0f, 4.0f, -19.0f), new Vector3(18f, -158f, 0f), 32f),
            // East and west view directions are perpendicular to south, so
            // their inward horizontal offsets use the opposite yaw signs.
            new CameraDefinition("east_ds_near", "SP Dataset East Near", new Vector3(8.8f, 7.0f, -5.0f), new Vector3(27f, 104f, 0f), 40f),
            new CameraDefinition("east_ds_far", "SP Dataset East Far", new Vector3(17.0f, 4.2f, 1.0f), new Vector3(14f, 146f, 0f), 25f),
            new CameraDefinition("west_ds_near", "SP Dataset West Near", new Vector3(-13.0f, 7.0f, -1.0f), new Vector3(28f, -81f, 0f), 40f),
            new CameraDefinition("west_ds_far", "SP Dataset West Far", new Vector3(-21.0f, 4.0f, -9.0f), new Vector3(12f, -39f, 0f), 23f),
        };

        [MenuItem("Traffic Vision/Dataset/Create SP Dataset Cameras")]
        public static void CreateDatasetCameras()
        {
            if (!EnsureSpScene())
            {
                return;
            }

            GameObject root = FindOrCreate(RootName, null);
            foreach (CameraDefinition definition in Definitions)
            {
                GameObject cameraObject = FindOrCreate(definition.objectName, root.transform);
                // UnityEngine.Object can represent a destroyed/missing
                // component. Its overloaded == is required here; ?? only
                // checks the managed C# reference and would retain it.
                Camera camera = cameraObject.GetComponent<Camera>();
                if (camera == null)
                {
                    camera = cameraObject.AddComponent<Camera>();
                }

                TrafficCameraCalibration calibration = cameraObject.GetComponent<TrafficCameraCalibration>();
                if (calibration == null)
                {
                    calibration = cameraObject.AddComponent<TrafficCameraCalibration>();
                }
                camera.transform.SetPositionAndRotation(definition.position, Quaternion.Euler(definition.rotation));
                camera.orthographic = false;
                camera.fieldOfView = definition.fieldOfView;
                camera.nearClipPlane = 0.1f;
                camera.farClipPlane = 250f;
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.12f, 0.16f, 0.2f);
                camera.enabled = false;
                ConfigureCalibration(calibration, definition.cameraId, captureEnabled: false);
                EditorUtility.SetDirty(cameraObject);
            }

            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            Debug.Log("Created or refreshed six SP dataset cameras. They are disabled for TCP capture by default.");
        }

        [MenuItem("Traffic Vision/Dataset/Enable SP Dataset Capture")]
        public static void EnableDatasetCapture() => SetDatasetCaptureEnabled(true);

        [MenuItem("Traffic Vision/Dataset/Disable SP Dataset Capture")]
        public static void DisableDatasetCapture() => SetDatasetCaptureEnabled(false);

        private static void SetDatasetCaptureEnabled(bool enabled)
        {
            if (!EnsureSpScene())
            {
                return;
            }

            int changed = 0;
            foreach (TrafficCameraCalibration calibration in Object.FindObjectsByType<TrafficCameraCalibration>(FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (!calibration.CameraId.Contains("_ds_"))
                {
                    continue;
                }

                SerializedObject serialized = new SerializedObject(calibration);
                serialized.FindProperty("captureEnabled").boolValue = enabled;
                serialized.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(calibration);
                changed++;
            }

            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            Debug.Log($"Dataset camera capture {(enabled ? "enabled" : "disabled")} for {changed} cameras.");
        }

        private static void ConfigureCalibration(TrafficCameraCalibration calibration, string cameraId, bool captureEnabled)
        {
            SerializedObject serialized = new SerializedObject(calibration);
            serialized.FindProperty("cameraId").stringValue = cameraId;
            serialized.FindProperty("captureEnabled").boolValue = captureEnabled;
            serialized.FindProperty("captureWidth").intValue = 1280;
            serialized.FindProperty("captureHeight").intValue = 720;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }

        private static bool EnsureSpScene()
        {
            if (SceneManager.GetActiveScene().path == SceneAssetPath)
            {
                return true;
            }

            EditorUtility.DisplayDialog("Open the SP import scene", "Open Assets/Scenes/SPImport.unity before configuring dataset cameras.", "OK");
            return false;
        }

        private static GameObject FindOrCreate(string objectName, Transform parent)
        {
            GameObject existing = GameObject.Find(objectName);
            if (existing != null)
            {
                if (existing.transform.parent != parent)
                {
                    existing.transform.SetParent(parent, false);
                }
                return existing;
            }

            GameObject created = new GameObject(objectName);
            created.transform.SetParent(parent, false);
            return created;
        }

        private readonly struct CameraDefinition
        {
            public readonly string cameraId;
            public readonly string objectName;
            public readonly Vector3 position;
            public readonly Vector3 rotation;
            public readonly float fieldOfView;

            public CameraDefinition(string cameraId, string objectName, Vector3 position, Vector3 rotation, float fieldOfView)
            {
                this.cameraId = cameraId;
                this.objectName = objectName;
                this.position = position;
                this.rotation = rotation;
                this.fieldOfView = fieldOfView;
            }
        }
    }
}
