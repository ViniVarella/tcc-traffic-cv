using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.SumoImport
{
    /// <summary>
    /// Builds a lightweight, presentation-oriented urban context around the SP
    /// road network. It deliberately lives outside GeneratedSumoRoadNetwork so
    /// rebuilding the importer never removes it.
    /// </summary>
    public static class SpEnvironmentSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string EnvironmentRootName = "SP Environment";
        private const string MaterialsDirectory = "Assets/Materials/SP";

        private const string House04Path = "Assets/Art/TrafficModels/Models/Buildings/Residential House 04/Residential House 04.fbx";
        private const string House05Path = "Assets/Art/TrafficModels/Models/Buildings/Residential House 05/Residential House 05.fbx";
        private const string House06Path = "Assets/Art/TrafficModels/Models/Buildings/Residential House 06/ResidentialHouse 06.fbx";
        private const string House08Path = "Assets/Art/TrafficModels/Models/Buildings/Residential House 08/Residential House 08.fbx";
        private const string MaplePath = "Assets/Art/TrafficModels/Models/Trees/Maple/Maple.fbx";
        private const string PinePath = "Assets/Art/TrafficModels/Models/Trees/Pine/Pine.fbx";

        [MenuItem("Traffic Vision/SUMO/Build SP Presentation Environment")]
        public static void Build()
        {
            if (SceneManager.GetActiveScene().path != SceneAssetPath)
            {
                EditorUtility.DisplayDialog(
                    "Open the SP import scene",
                    "Open Assets/Scenes/SPImport.unity before building the presentation environment.",
                    "OK");
                return;
            }

            Transform existing = GameObject.Find(EnvironmentRootName)?.transform;
            if (existing != null)
            {
                UnityEngine.Object.DestroyImmediate(existing.gameObject);
            }

            EnsureMaterialsDirectory();
            Material grass = GetOrCreateMaterial("SP Grass", "SP_Grass.mat", new Color(0.19f, 0.42f, 0.20f));
            if (grass == null)
            {
                return;
            }

            GameObject root = new GameObject(EnvironmentRootName);
            CreateGround(root.transform, grass);
            CreateBuildings(root.transform);
            CreateVegetation(root.transform);
            ConfigureLighting();

            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            AssetDatabase.SaveAssets();
            if (!EditorSceneManager.SaveScene(SceneManager.GetActiveScene()))
            {
                Debug.LogError("Could not save the SP scene after building its presentation environment.", root);
                return;
            }

            Selection.activeGameObject = root;
            Debug.Log("Built SP presentation environment. Re-run this menu item to replace only the SP Environment root.", root);
        }

        private static void CreateGround(Transform root, Material grass)
        {
            CreateBox("Grass", root, new Vector3(-7f, -0.16f, -2f), new Vector3(230f, 0.15f, 230f), grass);
        }

        private static void CreateBuildings(Transform root)
        {
            // This layout was refined manually against the imported SP road
            // geometry. Keep the recorded transforms here so rebuilding the
            // presentation environment preserves the approved neighbourhood.
            PlaceModel(House04Path, "Roadside House 01", root, new Vector3(28.31f, 0f, 32.42f), new Quaternion(0f, 0.6301428f, 0f, -0.7764793f), 6.5f);
            PlaceModel(House05Path, "Roadside House 02", root, new Vector3(-6.58f, 0f, 71.15f), new Quaternion(0f, 0.7878067f, 0f, 0.6159226f), 7.5f);
            PlaceModel(House06Path, "Roadside House 03", root, new Vector3(48.46f, 0f, -46.77f), new Quaternion(0f, 0.1869907f, 0f, 0.9823617f), 6.5f);
            PlaceModel(House08Path, "Roadside House 04", root, new Vector3(42.93f, 0f, 2.55f), new Quaternion(0f, 0.980449f, 0f, -0.1967731f), 7.5f);
            PlaceModel(House04Path, "Roadside House 05", root, new Vector3(11.18f, 0f, -63.78f), new Quaternion(0f, 0.6490228f, 0f, -0.7607689f), 6.5f);
            PlaceModel(House05Path, "Roadside House 06", root, new Vector3(-30.82f, 0f, -32.16f), new Quaternion(0f, 0.7707634f, 0f, 0.6371215f), 7.5f);
            PlaceModel(House06Path, "Roadside House 07", root, new Vector3(-32.63f, 0f, 32.84f), new Quaternion(0f, 0.9755423f, 0f, -0.2198116f), 6.5f);
            PlaceModel(House08Path, "Roadside House 08", root, new Vector3(-67.66f, 0f, -4.58f), new Quaternion(0f, 0.17772f, 0f, 0.9840811f), 7.5f);
        }

        private static void CreateVegetation(Transform root)
        {
            Vector3[] maplePositions =
            {
                new Vector3(-59.3f, 0f, 79.4f), new Vector3(-51.9f, 0f, 68.2f), new Vector3(-32.4f, 0f, 79.6f), new Vector3(-21.4f, 0f, 70.8f), new Vector3(-59.5f, 0f, 37.7f),
                new Vector3(35.9f, 0f, 63.0f), new Vector3(52.0f, 0f, 57.9f), new Vector3(67.5f, 0f, 49.4f), new Vector3(79.2f, 0f, 41.2f), new Vector3(73.1f, 0f, 15.7f),
                new Vector3(-82.2f, 0f, -42.9f), new Vector3(-76.8f, 0f, -56.8f), new Vector3(-64.1f, 0f, -60.1f), new Vector3(-65.6f, 0f, -26.8f), new Vector3(-51.3f, 0f, -62.2f),
                new Vector3(1.8f, 0f, -78.0f), new Vector3(24.8f, 0f, -78.2f), new Vector3(51.9f, 0f, -69.3f), new Vector3(69.0f, 0f, -54.9f), new Vector3(77.2f, 0f, -13.5f)
            };
            for (int index = 0; index < maplePositions.Length; index++)
            {
                PlaceModel(MaplePath, $"Maple {index + 1:00}", root, maplePositions[index], index * 29f, 7f);
            }

            Vector3[] pinePositions =
            {
                new Vector3(-73.7f, 0f, 82.0f), new Vector3(-78.2f, 0f, 47.5f), new Vector3(90.2f, 0f, 46.5f), new Vector3(86.3f, 0f, 17.5f),
                new Vector3(-93.7f, 0f, -46.4f), new Vector3(-80.7f, 0f, -69.2f), new Vector3(46.1f, 0f, -87.0f), new Vector3(82.2f, 0f, -54.5f)
            };
            for (int index = 0; index < pinePositions.Length; index++)
            {
                PlaceModel(PinePath, $"Pine {index + 1:00}", root, pinePositions[index], index * 47f, 10f);
            }

            // Extra trees sampled outside the road network: at least 9 m from
            // any lane, sidewalk or junction of Cruzamento.ped.net.xml (and from
            // each road's extension past the map edge, which the cameras see in
            // the background), 14 m from the houses and 9 m from other trees.
            Vector3[] extraMaplePositions =
            {
                new Vector3(72.2f, 0f, 81.2f), new Vector3(55.8f, 0f, 79.5f), new Vector3(40.3f, 0f, 82.5f), new Vector3(-19.3f, 0f, 95.4f),
                new Vector3(75.4f, 0f, 72.1f), new Vector3(29.3f, 0f, 49.2f), new Vector3(56.1f, 0f, 44.6f), new Vector3(-90.9f, 0f, 60.7f),
                new Vector3(-99.1f, 0f, 47.1f), new Vector3(81.7f, 0f, 30.1f), new Vector3(42.1f, 0f, 28.4f), new Vector3(51.3f, 0f, 12.6f),
                new Vector3(31.9f, 0f, 13.3f), new Vector3(90.7f, 0f, 7.1f), new Vector3(62.1f, 0f, 4.3f), new Vector3(-106.2f, 0f, 4.6f),
                new Vector3(-86.2f, 0f, 2.1f), new Vector3(59.3f, 0f, -5.6f), new Vector3(85.4f, 0f, -10.2f), new Vector3(-49.8f, 0f, -7.9f),
                new Vector3(-57.8f, 0f, -14.2f), new Vector3(-48.1f, 0f, -16.2f), new Vector3(-103.7f, 0f, -24.9f), new Vector3(-83.3f, 0f, -32.3f),
                new Vector3(25.5f, 0f, -48.8f), new Vector3(-49.1f, 0f, -36.7f), new Vector3(-43.2f, 0f, -60.3f), new Vector3(26.3f, 0f, -89.6f),
                new Vector3(-61.2f, 0f, -72.6f), new Vector3(10.6f, 0f, -102.6f)
            };
            for (int index = 0; index < extraMaplePositions.Length; index++)
            {
                int number = maplePositions.Length + index + 1;
                PlaceModel(MaplePath, $"Maple {number:00}", root, extraMaplePositions[index], number * 29f, 7f);
            }

            Vector3[] extraPinePositions =
            {
                new Vector3(84.8f, 0f, 88.2f), new Vector3(105.0f, 0f, 82.8f), new Vector3(105.0f, 0f, 72.5f), new Vector3(-70.8f, 0f, 92.0f),
                new Vector3(105.0f, 0f, 55.7f), new Vector3(-87.7f, 0f, 71.2f), new Vector3(68.1f, 0f, -100.1f), new Vector3(-77.6f, 0f, -88.4f),
                new Vector3(-92.1f, 0f, -90.1f), new Vector3(-119.0f, 0f, -89.6f)
            };
            for (int index = 0; index < extraPinePositions.Length; index++)
            {
                int number = pinePositions.Length + index + 1;
                PlaceModel(PinePath, $"Pine {number:00}", root, extraPinePositions[index], number * 47f, 10f);
            }
        }

        private static void ConfigureLighting()
        {
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(0.70f, 0.75f, 0.80f);
            // No fog: the approved scene keeps it off, and it washes out the camera backgrounds.
            RenderSettings.fog = false;
            RenderSettings.fogColor = new Color(0.68f, 0.77f, 0.82f);
            RenderSettings.fogMode = FogMode.Linear;
            RenderSettings.fogStartDistance = 85f;
            RenderSettings.fogEndDistance = 180f;

            Light overviewLight = GameObject.Find("SP Overview Light")?.GetComponent<Light>();
            if (overviewLight != null)
            {
                overviewLight.intensity = 1.35f;
                overviewLight.color = new Color(1f, 0.94f, 0.84f);
                overviewLight.shadows = LightShadows.Soft;
            }
        }

        /// <summary>
        /// Turns the model around the vertical axis only. Some FBX roots carry
        /// their own rotation (Maple and Pine: trunk node at 90 degrees in X);
        /// replacing it with the yaw laid the trees on their side, so the yaw
        /// is composed with the imported root rotation instead.
        /// </summary>
        private static void PlaceModel(string assetPath, string objectName, Transform parent, Vector3 position, float yaw, float targetHeight)
        {
            GameObject model = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            Quaternion rootRotation = model != null ? model.transform.localRotation : Quaternion.identity;
            PlaceModel(assetPath, objectName, parent, position, Quaternion.Euler(0f, yaw, 0f) * rootRotation, targetHeight);
        }

        private static void PlaceModel(string assetPath, string objectName, Transform parent, Vector3 position, Quaternion rotation, float targetHeight)
        {
            GameObject model = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            if (model == null)
            {
                Debug.LogWarning($"SP presentation environment could not load '{assetPath}'.");
                return;
            }

            GameObject instance = PrefabUtility.InstantiatePrefab(model, parent) as GameObject;
            if (instance == null)
            {
                return;
            }

            instance.name = objectName;
            instance.transform.SetPositionAndRotation(position, rotation);
            NormalizeModelHeight(instance, targetHeight, position.y);
        }

        /// <summary>
        /// The downloaded FBX models use different authoring units. Normalize
        /// against their renderer bounds, so all decoration is sized in the
        /// same metres as the SUMO network rather than by arbitrary FBX scale.
        /// </summary>
        private static void NormalizeModelHeight(GameObject instance, float targetHeight, float groundY)
        {
            if (!TryGetRendererBounds(instance, out Bounds bounds) || bounds.size.y <= 0.0001f)
            {
                Debug.LogWarning($"Could not determine bounds for '{instance.name}'; retaining its imported scale.", instance);
                return;
            }

            float multiplier = targetHeight / bounds.size.y;
            instance.transform.localScale *= multiplier;

            if (TryGetRendererBounds(instance, out bounds))
            {
                instance.transform.position += Vector3.up * (groundY - bounds.min.y);
            }
        }

        private static bool TryGetRendererBounds(GameObject instance, out Bounds bounds)
        {
            Renderer[] renderers = instance.GetComponentsInChildren<Renderer>();
            bool hasBounds = false;
            bounds = default;
            foreach (Renderer renderer in renderers)
            {
                if (!renderer.enabled)
                {
                    continue;
                }

                if (!hasBounds)
                {
                    bounds = renderer.bounds;
                    hasBounds = true;
                }
                else
                {
                    bounds.Encapsulate(renderer.bounds);
                }
            }

            return hasBounds;
        }

        private static void CreateBox(string objectName, Transform parent, Vector3 position, Vector3 scale, Material material)
        {
            CreateOrientedBox(objectName, parent, position, scale, 0f, material);
        }

        private static void CreateOrientedBox(string objectName, Transform parent, Vector3 position, Vector3 scale, float yaw, Material material)
        {
            GameObject box = GameObject.CreatePrimitive(PrimitiveType.Cube);
            box.name = objectName;
            box.transform.SetParent(parent, false);
            box.transform.SetPositionAndRotation(position, Quaternion.Euler(0f, yaw, 0f));
            box.transform.localScale = scale;
            box.GetComponent<Renderer>().sharedMaterial = material;
            UnityEngine.Object.DestroyImmediate(box.GetComponent<Collider>());
        }


        private static void EnsureMaterialsDirectory()
        {
            if (!AssetDatabase.IsValidFolder("Assets/Materials"))
            {
                AssetDatabase.CreateFolder("Assets", "Materials");
            }

            if (!AssetDatabase.IsValidFolder(MaterialsDirectory))
            {
                AssetDatabase.CreateFolder("Assets/Materials", "SP");
            }
        }

        private static Material GetOrCreateMaterial(string materialName, string fileName, Color color)
        {
            string path = $"{MaterialsDirectory}/{fileName}";
            Material material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                Shader shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
                if (shader == null)
                {
                    EditorUtility.DisplayDialog("No supported shader", "Neither URP/Lit nor Standard shader is available.", "OK");
                    return null;
                }

                material = new Material(shader) { name = materialName };
                AssetDatabase.CreateAsset(material, path);
            }

            if (material.HasProperty("_BaseColor"))
            {
                material.SetColor("_BaseColor", color);
            }

            if (material.HasProperty("_Color"))
            {
                material.SetColor("_Color", color);
            }

            EditorUtility.SetDirty(material);
            return material;
        }
    }
}
