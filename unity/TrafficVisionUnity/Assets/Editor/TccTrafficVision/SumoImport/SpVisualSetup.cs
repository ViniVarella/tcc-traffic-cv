using TccTrafficVision.SumoImport;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.SumoImport
{
    /// <summary>
    /// Applies durable visual assets to the SP import scene and rebuilds its road meshes.
    /// </summary>
    public static class SpVisualSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string MaterialsDirectory = "Assets/Materials/SP";

        [MenuItem("Traffic Vision/SUMO/Configure SP Visuals")]
        public static void ConfigureScene()
        {
            if (SceneManager.GetActiveScene().path != SceneAssetPath)
            {
                EditorUtility.DisplayDialog(
                    "Open the SP import scene",
                    "Open Assets/Scenes/SPImport.unity before configuring the SP visuals.",
                    "OK");
                return;
            }

            SumoRoadNetworkImporter importer = Object.FindFirstObjectByType<SumoRoadNetworkImporter>();
            if (importer == null)
            {
                EditorUtility.DisplayDialog("SUMO importer not found", "Add or restore the SP Road Network Importer first.", "OK");
                return;
            }

            EnsureMaterialsDirectory();
            Material road = GetOrCreateMaterial("SP Road", "SP_Road.mat", new Color(0.13f, 0.15f, 0.18f));
            Material junction = GetOrCreateMaterial("SP Junction", "SP_Junction.mat", new Color(0.18f, 0.21f, 0.25f));
            Material marking = GetOrCreateMaterial("SP Lane Marking", "SP_LaneMarking.mat", new Color(0.95f, 0.93f, 0.82f));
            if (road == null || junction == null || marking == null)
            {
                return;
            }

            SerializedObject serializedImporter = new SerializedObject(importer);
            serializedImporter.FindProperty("roadMaterial").objectReferenceValue = road;
            serializedImporter.FindProperty("junctionMaterial").objectReferenceValue = junction;
            serializedImporter.FindProperty("laneMarkingMaterial").objectReferenceValue = marking;
            serializedImporter.FindProperty("generateLaneCenterLines").boolValue = true;
            serializedImporter.FindProperty("laneMarkingWidth").floatValue = 0.16f;
            serializedImporter.FindProperty("laneMarkingDashLength").floatValue = 2.5f;
            serializedImporter.FindProperty("laneMarkingGapLength").floatValue = 4f;
            serializedImporter.ApplyModifiedPropertiesWithoutUndo();

            importer.Rebuild();
            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            AssetDatabase.SaveAssets();
            Selection.activeGameObject = importer.gameObject;
            Debug.Log("Configured SP visual materials and lane markings. The road network was rebuilt.", importer);
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
