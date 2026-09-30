using TccTrafficVision;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.SumoImport
{
    /// <summary>
    /// Builds the emergency vehicle prefab from the downloaded ambulance model
    /// and wires it into the SP scene's VehicleManager.
    ///
    /// The model comes from another source than the car FBXs, so its size and
    /// axes are unknown. The prefab measures it and normalizes it to the car
    /// convention: the longest horizontal axis along root +X (VehicleManager
    /// applies the same -90° yaw to every prefab), the requested length, the
    /// wheels on the ground and the front bumper on the origin (SUMO position). Which end is the front cannot be inferred; if the
    /// ambulance drives backwards in Play Mode, run the Flip action.
    ///
    /// The model is licensed for personal/student use only, so it and this
    /// prefab are git-ignored; see README for where to download it.
    /// </summary>
    public static class SpEmergencyPrefabSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string ModelPath = "Assets/Art/TrafficModels/Models/Cars/Ambulance/ambulance.fbx";
        private const string PrefabPath = "Assets/Prefabs/Vehicles/Ambulance.prefab";
        private const string ModelChildName = "Ambulance Model";
        private const float TargetLengthMeters = 5.8f;
        // The RigModels ambulance ends up rear-first after the axis alignment
        // (checked in Play Mode), so the prefab turns it 180°.
        private const bool ModelFacesBackwards = true;

        [MenuItem("Traffic Vision/Vehicles/Create SP Emergency Prefab")]
        public static void CreateAndConfigure()
        {
            // Recreating overwrites the prefab, including a previous Flip.
            if (!IsSceneOpen())
            {
                return;
            }

            GameObject model = AssetDatabase.LoadAssetAtPath<GameObject>(ModelPath);
            if (model == null)
            {
                EditorUtility.DisplayDialog(
                    "Ambulance model missing",
                    $"Import the ambulance model to {ModelPath} first (see README).",
                    "OK");
                return;
            }

            GameObject root = new GameObject("Ambulance");
            GameObject instance = PrefabUtility.InstantiatePrefab(model) as GameObject;
            instance.name = ModelChildName;
            instance.transform.SetParent(root.transform, false);
            Normalize(instance.transform);
            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(root, PrefabPath);
            Object.DestroyImmediate(root);
            if (prefab == null)
            {
                Debug.LogError($"Could not save {PrefabPath}.");
                return;
            }

            if (!WirePrefab(prefab))
            {
                return;
            }

            Debug.Log(
                $"Emergency prefab saved at {PrefabPath} ({TargetLengthMeters} m long). Save the scene (Cmd+S), then check " +
                "in Play Mode that it drives forwards; if not, run Traffic Vision > Vehicles > Flip SP Emergency Prefab.",
                prefab);
        }

        [MenuItem("Traffic Vision/Vehicles/Flip SP Emergency Prefab")]
        public static void Flip()
        {
            GameObject contents = PrefabUtility.LoadPrefabContents(PrefabPath);
            if (contents == null)
            {
                EditorUtility.DisplayDialog("Emergency prefab missing", "Run Create SP Emergency Prefab first.", "OK");
                return;
            }

            try
            {
                Transform model = contents.transform.Find(ModelChildName);
                if (model == null)
                {
                    Debug.LogError($"{PrefabPath} has no '{ModelChildName}' child.");
                    return;
                }

                // Rotate 180° about the vertical axis, around the prefab origin.
                model.RotateAround(contents.transform.position, Vector3.up, 180f);
                PrefabUtility.SaveAsPrefabAsset(contents, PrefabPath);
                Debug.Log("Emergency prefab flipped 180°. Re-enter Play Mode to check the heading.");
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(contents);
            }
        }

        private static void Normalize(Transform model)
        {
            model.localPosition = Vector3.zero;
            model.localRotation = Quaternion.identity;
            model.localScale = Vector3.one;
            Bounds bounds = CombinedBounds(model);
            if (bounds.size.z > bounds.size.x)
            {
                // Longest axis along Z: turn it to X, the car FBX convention.
                model.localRotation = Quaternion.Euler(0f, 90f, 0f);
                bounds = CombinedBounds(model);
            }

            if (ModelFacesBackwards)
            {
                model.localRotation = Quaternion.Euler(0f, 180f, 0f) * model.localRotation;
                bounds = CombinedBounds(model);
            }

            float scale = TargetLengthMeters / Mathf.Max(bounds.size.x, 1e-4f);
            model.localScale = Vector3.one * scale;
            bounds = CombinedBounds(model);
            // SUMO reports the front bumper position and VehicleManager puts the
            // prefab origin there, so the front (+X, driving direction under the
            // -90° yaw) sits on the origin and the body extends backwards. The
            // model is centred sideways and its wheels touch y = 0.
            model.localPosition -= new Vector3(bounds.max.x, bounds.min.y, bounds.center.z);
        }

        private static Bounds CombinedBounds(Transform model)
        {
            Renderer[] renderers = model.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
            {
                return new Bounds(model.position, Vector3.one);
            }

            Bounds bounds = renderers[0].bounds;
            for (int index = 1; index < renderers.Length; index++)
            {
                bounds.Encapsulate(renderers[index].bounds);
            }

            return bounds;
        }

        private static bool WirePrefab(GameObject prefab)
        {
            VehicleManager vehicleManager = Object.FindFirstObjectByType<VehicleManager>();
            if (vehicleManager == null)
            {
                EditorUtility.DisplayDialog(
                    "Configure dynamic sync first",
                    "Run Traffic Vision > SUMO > Configure SP Dynamic Sync before configuring the emergency prefab.",
                    "OK");
                return false;
            }

            SerializedObject serializedManager = new SerializedObject(vehicleManager);
            serializedManager.FindProperty("emergencyPrefab").objectReferenceValue = prefab;
            serializedManager.FindProperty("emergencyTypeId").stringValue = "emergency";
            serializedManager.ApplyModifiedPropertiesWithoutUndo();
            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            Selection.activeObject = vehicleManager;
            return true;
        }

        private static bool IsSceneOpen()
        {
            if (SceneManager.GetActiveScene().path == SceneAssetPath)
            {
                return true;
            }

            EditorUtility.DisplayDialog("Open SPImport first", "Open Assets/Scenes/SPImport.unity first.", "OK");
            return false;
        }
    }
}
