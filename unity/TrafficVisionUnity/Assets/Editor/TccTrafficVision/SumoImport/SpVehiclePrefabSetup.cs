using System.Collections.Generic;
using TccTrafficVision;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.SumoImport
{
    /// <summary>
    /// Creates lightweight local vehicle prefabs from the copied Sumo2Unity FBX
    /// models and wires them into the SP scene's VehicleManager.
    /// </summary>
    public static class SpVehiclePrefabSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string PrefabFolder = "Assets/Prefabs/Vehicles";

        private static readonly VehiclePrefabDefinition[] Definitions =
        {
            new VehiclePrefabDefinition("Alma Blue", "Assets/Art/TrafficModels/Models/Cars/AlmaBlue.fbx"),
            new VehiclePrefabDefinition("Alma Grey", "Assets/Art/TrafficModels/Models/Cars/AlmaGrey.fbx"),
            new VehiclePrefabDefinition("Elka Red", "Assets/Art/TrafficModels/Models/Cars/ElkaRed.fbx"),
            new VehiclePrefabDefinition("Elora White", "Assets/Art/TrafficModels/Models/Cars/EloraWhite.fbx"),
        };

        [MenuItem("Traffic Vision/Vehicles/Create SP Vehicle Prefabs")]
        public static void CreateAndConfigure()
        {
            Scene scene = SceneManager.GetActiveScene();
            if (scene.path != SceneAssetPath)
            {
                EditorUtility.DisplayDialog(
                    "Open SPImport first",
                    "Open Assets/Scenes/SPImport.unity before creating the vehicle prefabs.",
                    "OK");
                return;
            }

            EnsureFolder(PrefabFolder);
            List<GameObject> prefabs = new List<GameObject>();
            foreach (VehiclePrefabDefinition definition in Definitions)
            {
                GameObject prefab = CreateOrLoadPrefab(definition);
                if (prefab != null)
                {
                    prefabs.Add(prefab);
                }
            }

            if (prefabs.Count == 0)
            {
                EditorUtility.DisplayDialog(
                    "Vehicle models are not ready",
                    "Unity has not imported the FBX models yet. Wait for the import to finish, then run this action again.",
                    "OK");
                return;
            }

            VehicleManager vehicleManager = Object.FindFirstObjectByType<VehicleManager>();
            if (vehicleManager == null)
            {
                EditorUtility.DisplayDialog(
                    "Configure dynamic sync first",
                    "Run Traffic Vision > SUMO > Configure SP Dynamic Sync before configuring vehicle prefabs.",
                    "OK");
                return;
            }

            SerializedObject serializedManager = new SerializedObject(vehicleManager);
            SerializedProperty prefabProperty = serializedManager.FindProperty("vehiclePrefabs");
            prefabProperty.arraySize = prefabs.Count;
            for (int index = 0; index < prefabs.Count; index++)
            {
                prefabProperty.GetArrayElementAtIndex(index).objectReferenceValue = prefabs[index];
            }

            serializedManager.FindProperty("prefabScale").vector3Value = Vector3.one;
            serializedManager.FindProperty("prefabVerticalOffset").floatValue = 0f;
            // The copied Alma/Elka/Elora FBXs are authored -90° relative to the
            // SUMO-to-Unity heading convention used by VehicleManager.
            serializedManager.FindProperty("prefabYawOffset").floatValue = -90f;
            serializedManager.ApplyModifiedPropertiesWithoutUndo();

            EditorSceneManager.MarkSceneDirty(scene);
            Selection.activeObject = vehicleManager;
            Debug.Log($"Configured {prefabs.Count} SP vehicle prefabs. Enter Play Mode and verify size, ground offset and yaw from a traffic camera.", vehicleManager);
        }

        private static GameObject CreateOrLoadPrefab(VehiclePrefabDefinition definition)
        {
            string prefabPath = $"{PrefabFolder}/{definition.prefabName}.prefab";
            GameObject existing = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (existing != null)
            {
                return existing;
            }

            GameObject model = AssetDatabase.LoadAssetAtPath<GameObject>(definition.modelPath);
            if (model == null)
            {
                Debug.LogWarning($"Vehicle model is missing or not imported: {definition.modelPath}");
                return null;
            }

            GameObject root = new GameObject(definition.prefabName);
            GameObject modelInstance = PrefabUtility.InstantiatePrefab(model) as GameObject;
            modelInstance.transform.SetParent(root.transform, false);
            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(root, prefabPath);
            Object.DestroyImmediate(root);
            return prefab;
        }

        private static void EnsureFolder(string path)
        {
            string[] segments = path.Split('/');
            string current = segments[0];
            for (int index = 1; index < segments.Length; index++)
            {
                string next = $"{current}/{segments[index]}";
                if (!AssetDatabase.IsValidFolder(next))
                {
                    AssetDatabase.CreateFolder(current, segments[index]);
                }

                current = next;
            }
        }

        private readonly struct VehiclePrefabDefinition
        {
            public readonly string prefabName;
            public readonly string modelPath;

            public VehiclePrefabDefinition(string prefabName, string modelPath)
            {
                this.prefabName = prefabName;
                this.modelPath = modelPath;
            }
        }
    }
}
