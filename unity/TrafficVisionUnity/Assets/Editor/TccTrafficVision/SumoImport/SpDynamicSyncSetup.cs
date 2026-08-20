using TccTrafficVision;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.SumoImport
{
    /// <summary>
    /// Adds the UDP receiver and simple visual placeholders needed to validate
    /// SUMO SP dynamic state in the SPImport scene.
    /// </summary>
    public static class SpDynamicSyncSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string SynchronizationRootName = "SP Dynamic Synchronization";
        private const string VehiclesRootName = "SP Vehicles";
        private const string TrafficLightMarkerName = "SP Traffic Light Marker";

        [MenuItem("Traffic Vision/SUMO/Configure SP Dynamic Sync")]
        public static void ConfigureScene()
        {
            Scene scene = SceneManager.GetActiveScene();
            if (scene.path != SceneAssetPath)
            {
                EditorUtility.DisplayDialog(
                    "Open SPImport first",
                    "Open Assets/Scenes/SPImport.unity before configuring dynamic synchronization.",
                    "OK");
                return;
            }

            GameObject synchronizationRoot = FindOrCreate(SynchronizationRootName, null);
            GameObject vehiclesRoot = FindOrCreate(VehiclesRootName, synchronizationRoot.transform);
            GameObject trafficLightMarker = FindOrCreate(TrafficLightMarkerName, synchronizationRoot.transform);
            ConfigureTrafficLightMarker(trafficLightMarker);

            VehicleManager vehicleManager = GetOrAdd<VehicleManager>(synchronizationRoot);
            TrafficLightVisualController trafficLightController = GetOrAdd<TrafficLightVisualController>(trafficLightMarker);
            PythonStateReceiver receiver = GetOrAdd<PythonStateReceiver>(synchronizationRoot);

            SerializedObject vehicleManagerProperties = new SerializedObject(vehicleManager);
            vehicleManagerProperties.FindProperty("vehiclesRoot").objectReferenceValue = vehiclesRoot.transform;
            vehicleManagerProperties.ApplyModifiedPropertiesWithoutUndo();

            SerializedObject receiverProperties = new SerializedObject(receiver);
            receiverProperties.FindProperty("listenHost").stringValue = "127.0.0.1";
            receiverProperties.FindProperty("listenPort").intValue = 5004;
            receiverProperties.FindProperty("vehicleManager").objectReferenceValue = vehicleManager;
            receiverProperties.FindProperty("trafficLightVisualController").objectReferenceValue = trafficLightController;
            receiverProperties.ApplyModifiedPropertiesWithoutUndo();

            EditorSceneManager.MarkSceneDirty(scene);
            Selection.activeGameObject = synchronizationRoot;
            Debug.Log(
                "SP dynamic synchronization configured. Enter Play Mode, then run " +
                "python -m experiments.test_sumo_to_unity --config configs/sp.yaml --steps 120 --send-interval 0.1",
                synchronizationRoot);
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

        private static void ConfigureTrafficLightMarker(GameObject marker)
        {
            if (marker.GetComponentInChildren<Renderer>() == null)
            {
                GameObject primitive = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                primitive.name = "SP Traffic Light Visual";
                primitive.transform.SetParent(marker.transform, false);
                primitive.transform.localScale = new Vector3(1.2f, 2.5f, 1.2f);
            }

            // The TLS junction is (-6.04, -5.60) in SUMO; Unity maps (x, y)
            // to (x, z) and the marker is raised above the road for visibility.
            marker.transform.position = new Vector3(-6.04f, 2.5f, -5.60f);
        }
    }
}
