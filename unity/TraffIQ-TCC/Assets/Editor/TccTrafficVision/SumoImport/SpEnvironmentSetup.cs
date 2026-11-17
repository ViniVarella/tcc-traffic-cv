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
            PlaceModel(House04Path, "Roadside House 01", root, new Vector3(28.68f, 0f, 32.09f), new Quaternion(0f, 0.6263174f, 0f, -0.7795681f), 6.5f);
            PlaceModel(House05Path, "Roadside House 02", root, new Vector3(-5.71f, 0f, 71.15f), new Quaternion(0f, 0.7912734f, 0f, 0.6114625f), 7.5f);
            PlaceModel(House06Path, "Roadside House 03", root, new Vector3(48.61f, 0f, -46.57f), new Quaternion(0f, 0.1851272f, 0f, 0.9827146f), 6.5f);
            PlaceModel(House08Path, "Roadside House 04", root, new Vector3(42.96f, 0f, 2.36f), new Quaternion(0f, 0.9800589f, 0f, -0.1987072f), 7.5f);
            PlaceModel(House04Path, "Roadside House 05", root, new Vector3(11.79f, 0f, -63.6f), new Quaternion(0f, 0.6529918f, 0f, -0.757365f), 6.5f);
            PlaceModel(House05Path, "Roadside House 06", root, new Vector3(-30.5f, 0f, -32.46f), new Quaternion(0f, 0.766937f, 0f, 0.6417225f), 7.5f);
            PlaceModel(House06Path, "Roadside House 07", root, new Vector3(-32.4f, 0f, 33f), new Quaternion(0f, 0.9748832f, 0f, -0.222717f), 6.5f);
            PlaceModel(House08Path, "Roadside House 08", root, new Vector3(-67.66f, 0f, -4.76f), new Quaternion(0f, 0.1762364f, 0f, 0.9843479f), 7.5f);
        }

        private static void CreateVegetation(Transform root)
        {
            Vector3[] maplePositions =
            {
                new Vector3(-58.7f, 0f, 79.8f), new Vector3(-51.4f, 0f, 68.5f), new Vector3(-31.6f, 0f, 79.8f), new Vector3(-20.7f, 0f, 70.9f), new Vector3(-59.4f, 0f, 37.9f),
                new Vector3(36.7f, 0f, 62.5f), new Vector3(52.6f, 0f, 57.3f), new Vector3(68.0f, 0f, 48.8f), new Vector3(79.5f, 0f, 40.6f), new Vector3(73.2f, 0f, 15.3f),
                new Vector3(-81.9f, 0f, -43.5f), new Vector3(-76.3f, 0f, -57.5f), new Vector3(-63.5f, 0f, -60.8f), new Vector3(-65.4f, 0f, -27.2f), new Vector3(-50.5f, 0f, -62.8f),
                new Vector3(2.7f, 0f, -77.9f), new Vector3(25.5f, 0f, -77.9f), new Vector3(52.3f, 0f, -68.9f), new Vector3(69.2f, 0f, -54.7f), new Vector3(77.2f, 0f, -13.6f)
            };
            for (int index = 0; index < maplePositions.Length; index++)
            {
                PlaceModel(MaplePath, $"Maple {index + 1:00}", root, maplePositions[index], index * 29f, 7f);
            }

            Vector3[] pinePositions =
            {
                new Vector3(-73.7f, 0f, 82.4f), new Vector3(-78.1f, 0f, 47.7f), new Vector3(90.6f, 0f, 45.8f), new Vector3(86.4f, 0f, 17.1f),
                new Vector3(-93.4f, 0f, -47.1f), new Vector3(-80.1f, 0f, -70.0f), new Vector3(46.7f, 0f, -86.6f), new Vector3(82.3f, 0f, -54.3f)
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
                new Vector3(73.1f, 0f, 80.4f), new Vector3(56.7f, 0f, 78.8f), new Vector3(41.3f, 0f, 81.9f), new Vector3(-18.3f, 0f, 95.6f),
                new Vector3(76.1f, 0f, 71.4f), new Vector3(29.9f, 0f, 48.8f), new Vector3(56.5f, 0f, 44.0f), new Vector3(-81.2f, 0f, 57.5f),
                new Vector3(-99.0f, 0f, 47.3f), new Vector3(81.9f, 0f, 29.6f), new Vector3(42.4f, 0f, 28.0f), new Vector3(51.4f, 0f, 12.3f),
                new Vector3(32.0f, 0f, 13.1f), new Vector3(90.4f, 0f, 6.5f), new Vector3(62.2f, 0f, 4.0f), new Vector3(-106.2f, 0f, 4.4f),
                new Vector3(-86.3f, 0f, 1.9f), new Vector3(59.3f, 0f, -5.8f), new Vector3(85.2f, 0f, -10.6f), new Vector3(-49.8f, 0f, -8.1f),
                new Vector3(-57.8f, 0f, -14.4f), new Vector3(-48.0f, 0f, -16.5f), new Vector3(-103.6f, 0f, -25.4f), new Vector3(-83.2f, 0f, -32.8f),
                new Vector3(25.8f, 0f, -48.5f), new Vector3(-48.8f, 0f, -37.2f), new Vector3(-42.4f, 0f, -60.8f), new Vector3(27.1f, 0f, -89.3f),
                new Vector3(-60.4f, 0f, -73.3f), new Vector3(11.7f, 0f, -102.4f)
            };
            for (int index = 0; index < extraMaplePositions.Length; index++)
            {
                int number = maplePositions.Length + index + 1;
                PlaceModel(MaplePath, $"Maple {number:00}", root, extraMaplePositions[index], number * 29f, 7f);
            }

            Vector3[] extraPinePositions =
            {
                new Vector3(85.7f, 0f, 87.3f), new Vector3(105.0f, 0f, 81.9f), new Vector3(105.0f, 0f, 72.8f), new Vector3(-70.7f, 0f, 92.6f),
                new Vector3(105.0f, 0f, 55.1f), new Vector3(-87.3f, 0f, 72.2f), new Vector3(68.9f, 0f, -98.7f), new Vector3(-76.5f, 0f, -89.3f),
                new Vector3(-91.1f, 0f, -91.1f), new Vector3(-119.0f, 0f, -89.9f)
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
