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
            // Replace the old cylinder placeholder on every configuration so
            // the scene cannot retain the previous obelisk-like marker.
            for (int childIndex = marker.transform.childCount - 1; childIndex >= 0; childIndex--)
            {
                Object.DestroyImmediate(marker.transform.GetChild(childIndex).gameObject);
            }

            // E2, E3 and E6 are the three incoming approaches controlled by
            // this TLS. Each post is placed right of its vehicle direction,
            // just beyond the respective stop line and sidewalk.
            marker.transform.position = Vector3.zero;
            CreateTrafficSignalPost(marker.transform, "Signal Post East", new Vector3(19.36f, 0f, -2.93f), new Quaternion(0f, -0.5941611f, 0f, 0.80434614f));
            CreateTrafficSignalPost(marker.transform, "Signal Post South", new Vector3(6.3f, 0f, -19.46f), new Quaternion(0f, -0.028023053f, 0f, 0.99960726f));
            CreateTrafficSignalPost(marker.transform, "Signal Post West", new Vector3(-25.95f, 0f, -4.01f), new Quaternion(0f, 0.8f, 0f, 0.6000001f));
        }

        private static void CreateTrafficSignalPost(Transform parent, string objectName, Vector3 position, Quaternion rotation)
        {
            GameObject post = new GameObject(objectName);
            post.transform.SetParent(parent, false);
            post.transform.localPosition = position;
            post.transform.localRotation = rotation;

            CreateVisualPrimitive(PrimitiveType.Cylinder, "Signal Pole", post.transform, new Vector3(0f, 2.5f, 0f), new Vector3(0.18f, 2.5f, 0.18f), new Color(0.12f, 0.13f, 0.14f));
            CreateVisualPrimitive(PrimitiveType.Cylinder, "Signal Base", post.transform, new Vector3(0f, 0.12f, 0f), new Vector3(0.52f, 0.12f, 0.52f), new Color(0.18f, 0.19f, 0.20f));
            // The post is on the right sidewalk; the arm extends left over the road.
            CreateVisualPrimitive(PrimitiveType.Cube, "Signal Arm", post.transform, new Vector3(-1.45f, 4.65f, 0f), new Vector3(2.9f, 0.16f, 0.16f), new Color(0.12f, 0.13f, 0.14f));
            CreateVisualPrimitive(PrimitiveType.Cube, "Signal Housing", post.transform, new Vector3(-2.72f, 4.15f, 0f), new Vector3(0.78f, 1.72f, 0.38f), new Color(0.06f, 0.07f, 0.08f));
            CreateVisualPrimitive(PrimitiveType.Sphere, "Signal Red", post.transform, new Vector3(-2.72f, 4.66f, -0.22f), new Vector3(0.36f, 0.36f, 0.12f), new Color(0.25f, 0.02f, 0.02f));
            CreateVisualPrimitive(PrimitiveType.Sphere, "Signal Yellow", post.transform, new Vector3(-2.72f, 4.15f, -0.22f), new Vector3(0.36f, 0.36f, 0.12f), new Color(0.25f, 0.18f, 0.01f));
            CreateVisualPrimitive(PrimitiveType.Sphere, "Signal Green", post.transform, new Vector3(-2.72f, 3.64f, -0.22f), new Vector3(0.36f, 0.36f, 0.12f), new Color(0.01f, 0.22f, 0.03f));
        }

        private static void CreateVisualPrimitive(PrimitiveType primitiveType, string objectName, Transform parent, Vector3 localPosition, Vector3 localScale, Color color)
        {
            GameObject visual = GameObject.CreatePrimitive(primitiveType);
            visual.name = objectName;
            visual.transform.SetParent(parent, false);
            visual.transform.localPosition = localPosition;
            visual.transform.localScale = localScale;
            Object.DestroyImmediate(visual.GetComponent<Collider>());

            Renderer renderer = visual.GetComponent<Renderer>();
            if (renderer == null)
            {
                return;
            }

            Material material = new Material(renderer.sharedMaterial);
            material.color = color;
            if (material.HasProperty("_BaseColor"))
            {
                material.SetColor("_BaseColor", color);
            }

            renderer.sharedMaterial = material;
        }
    }
}
