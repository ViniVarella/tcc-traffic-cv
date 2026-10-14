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
            PlaceModel(House04Path, "Roadside House 01", root, new Vector3(18.1f, 0f, 39.6f), new Quaternion(0f, 0.7199983f, 0f, -0.6939759f), 6.5f);
            PlaceModel(House05Path, "Roadside House 02", root, new Vector3(-27.8f, 0f, 68f), new Quaternion(0f, 0.69397604f, 0f, 0.7199981f), 7.5f);
            PlaceModel(House06Path, "Roadside House 03", root, new Vector3(51.5f, 0f, -42.4f), new Quaternion(0f, 0.14853147f, 0f, 0.9889077f), 6.5f);
            PlaceModel(House08Path, "Roadside House 04", root, new Vector3(41.9f, 0f, 7.3f), new Quaternion(0f, 0.9889077f, 0f, -0.14853142f), 7.5f);
            PlaceModel(House04Path, "Roadside House 05", root, new Vector3(23.202461f, 0f, -58.76776f), new Quaternion(0f, 0.72694445f, 0f, -0.6866963f), 6.5f);
            PlaceModel(House05Path, "Roadside House 06", root, new Vector3(-23.6f, 0f, -37.4f), new Quaternion(0f, 0.6866963f, 0f, 0.72694445f), 7.5f);
            PlaceModel(House06Path, "Roadside House 07", root, new Vector3(-38f, 0f, 28.5f), new Quaternion(0f, 0.9891182f, 0f, -0.14712313f), 6.5f);
            PlaceModel(House08Path, "Roadside House 08", root, new Vector3(-67.6f, 0f, -8.4f), new Quaternion(0f, 0.1471231f, 0f, 0.9891182f), 7.5f);
        }

        private static void CreateVegetation(Transform root)
        {
            Vector3[] maplePositions =
            {
                new Vector3(-72f, 0f, 70f), new Vector3(-63f, 0f, 60f), new Vector3(-50f, 0f, 72f), new Vector3(-39f, 0f, 65f), new Vector3(-63f, 0f, 33f),
                new Vector3(15f, 0f, 72f), new Vector3(35f, 0f, 70f), new Vector3(55f, 0f, 63f), new Vector3(70f, 0f, 55f), new Vector3(70f, 0f, 25f),
                new Vector3(-75f, 0f, -55f), new Vector3(-65f, 0f, -70f), new Vector3(-50f, 0f, -72f), new Vector3(-62f, 0f, -35f), new Vector3(-35f, 0f, -72f),
                new Vector3(19.7f, 0f, -73.7f), new Vector3(38f, 0f, -71f), new Vector3(59f, 0f, -62f), new Vector3(72f, 0f, -50f), new Vector3(77.5f, 0f, -10f)
            };
            for (int index = 0; index < maplePositions.Length; index++)
            {
                PlaceModel(MaplePath, $"Maple {index + 1:00}", root, maplePositions[index], index * 29f, 7f);
            }

            Vector3[] pinePositions =
            {
                new Vector3(-88f, 0f, 72f), new Vector3(-82f, 0f, 42f), new Vector3(80f, 0f, 62f), new Vector3(83f, 0f, 28f),
                new Vector3(-86f, 0f, -60f), new Vector3(-65f, 0f, -84f), new Vector3(58f, 0f, -78f), new Vector3(81.1f, 0f, -50.1f)
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
                new Vector3(48.9f, 0f, 97.5f), new Vector3(31.1f, 0f, 92.8f), new Vector3(12.3f, 0f, 92.2f), new Vector3(-44.2f, 0f, 88.9f),
                new Vector3(55.7f, 0f, 88.5f), new Vector3(12.8f, 0f, 56.8f), new Vector3(44.3f, 0f, 56.4f), new Vector3(-91.3f, 0f, 52.0f),
                new Vector3(-101.5f, 0f, 42.6f), new Vector3(75.6f, 0f, 42.5f), new Vector3(34.6f, 0f, 37.1f), new Vector3(48.5f, 0f, 19.8f),
                new Vector3(28.3f, 0f, 19.2f), new Vector3(91.0f, 0f, 13.6f), new Vector3(60.9f, 0f, 10.6f), new Vector3(-106.5f, 0f, 0.3f),
                new Vector3(-86.5f, 0f, -1.5f), new Vector3(59.2f, 0f, -1.6f), new Vector3(86.2f, 0f, -6.5f), new Vector3(-49.5f, 0f, -11.3f),
                new Vector3(-56.7f, 0f, -19.4f), new Vector3(-46.5f, 0f, -21.2f), new Vector3(-101.0f, 0f, -35.4f), new Vector3(-78.9f, 0f, -42.7f),
                new Vector3(31.3f, 0f, -43.9f), new Vector3(-41.9f, 0f, -44.8f), new Vector3(-26.6f, 0f, -68.4f), new Vector3(42.2f, 0f, -81.6f),
                new Vector3(-42.2f, 0f, -84.5f), new Vector3(33.2f, 0f, -95.8f)
            };
            for (int index = 0; index < extraMaplePositions.Length; index++)
            {
                int number = maplePositions.Length + index + 1;
                PlaceModel(MaplePath, $"Maple {number:00}", root, extraMaplePositions[index], number * 29f, 7f);
            }

            Vector3[] extraPinePositions =
            {
                new Vector3(60.3f, 0f, 106.9f), new Vector3(86.9f, 0f, 104.2f), new Vector3(97.7f, 0f, 91.6f), new Vector3(-89.3f, 0f, 82.5f),
                new Vector3(95.0f, 0f, 72.7f), new Vector3(-94.2f, 0f, 62.0f), new Vector3(77.8f, 0f, -88.6f), new Vector3(-54.4f, 0f, -103.8f),
                new Vector3(-69.9f, 0f, -107.9f), new Vector3(-109.0f, 0f, -111.0f)
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
