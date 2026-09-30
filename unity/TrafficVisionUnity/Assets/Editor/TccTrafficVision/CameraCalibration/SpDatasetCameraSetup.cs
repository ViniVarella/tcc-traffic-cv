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
            // Variants of the operational poses (SpSouthCameraSetup), all framing
            // the stop line up to 60 m upstream: higher/lower, shifted sideways
            // (south) or closer/farther (east, west). Unlike the operational
            // cameras, south_ds_right lets the south signal post touch the lane
            // edge (~0.5% of the lane area): partial occlusion is useful training
            // data, and the labels come from visible-pixel masks.
            new CameraDefinition("south_ds_left", "SP Dataset South Left", new Vector3(-4.63f, 10f, -6.25f), new Vector3(20.5f, 172.92f, 0f), 32f),
            new CameraDefinition("south_ds_right", "SP Dataset South Right", new Vector3(-0.46f, 8f, -9.02f), new Vector3(19.99f, 178.1f, 0f), 33.8f),
            new CameraDefinition("east_ds_near", "SP Dataset East Near", new Vector3(7.39f, 8f, -6.87f), new Vector3(19.87f, 103.68f, 0f), 33.5f),
            new CameraDefinition("east_ds_far", "SP Dataset East Far", new Vector3(-3.64f, 6f, -1.91f), new Vector3(9.06f, 106.02f, 0f), 12.4f),
            new CameraDefinition("west_ds_near", "SP Dataset West Near", new Vector3(-3.59f, 11f, -1.97f), new Vector3(16.86f, 280.88f, 0f), 23f),
            new CameraDefinition("west_ds_far", "SP Dataset West Far", new Vector3(9.37f, 7.5f, -7.48f), new Vector3(8.09f, 283.45f, 0f), 9.1f),
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
