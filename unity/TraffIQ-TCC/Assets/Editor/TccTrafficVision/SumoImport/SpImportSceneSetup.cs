using TccTrafficVision.SumoImport;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.SumoImport
{
    /// <summary>
    /// Creates the scene used to import and visually validate the SP SUMO network.
    /// </summary>
    public static class SpImportSceneSetup
    {
        private const string NetworkAssetPath = "Assets/Sumo/SP/Cruzamento.net.xml";
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";

        [MenuItem("Traffic Vision/SUMO/Create SP Import Scene")]
        public static void CreateScene()
        {
            TextAsset networkXml = AssetDatabase.LoadAssetAtPath<TextAsset>(NetworkAssetPath);
            if (networkXml == null)
            {
                EditorUtility.DisplayDialog(
                    "SP SUMO network not found",
                    $"Expected the network TextAsset at '{NetworkAssetPath}'.",
                    "OK");
                return;
            }

            if (AssetDatabase.LoadAssetAtPath<SceneAsset>(SceneAssetPath) != null)
            {
                bool openExisting = EditorUtility.DisplayDialog(
                    "SP import scene already exists",
                    "The existing scene will be opened without overwriting its calibration work.",
                    "Open existing",
                    "Cancel");
                if (openExisting)
                {
                    EditorSceneManager.OpenScene(SceneAssetPath, OpenSceneMode.Single);
                }

                return;
            }

            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
            {
                return;
            }

            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            CreateOverviewLight();
            CreateOverviewCamera();

            GameObject importerObject = new GameObject("SP Road Network Importer");
            SumoRoadNetworkImporter importer = importerObject.AddComponent<SumoRoadNetworkImporter>();
            SerializedObject serializedImporter = new SerializedObject(importer);
            serializedImporter.FindProperty("networkXml").objectReferenceValue = networkXml;
            serializedImporter.FindProperty("useNetworkOffset").boolValue = true;
            serializedImporter.ApplyModifiedPropertiesWithoutUndo();

            EditorSceneManager.MarkSceneDirty(scene);
            if (!EditorSceneManager.SaveScene(scene, SceneAssetPath))
            {
                Debug.LogError($"Could not save SP import scene at '{SceneAssetPath}'.", importerObject);
                return;
            }

            Selection.activeGameObject = importerObject;
            Debug.Log(
                "SP import scene created. Select 'SP Road Network Importer' and click " +
                "'Import / rebuild SUMO road network' in the Inspector.",
                importerObject);
        }

        private static void CreateOverviewCamera()
        {
            GameObject cameraObject = new GameObject("SP Overview Camera");
            Camera overviewCamera = cameraObject.AddComponent<Camera>();
            overviewCamera.orthographic = true;
            overviewCamera.orthographicSize = 130f;
            overviewCamera.clearFlags = CameraClearFlags.SolidColor;
            overviewCamera.backgroundColor = new Color(0.12f, 0.16f, 0.2f);
            cameraObject.transform.SetPositionAndRotation(
                new Vector3(0f, 140f, 0f),
                Quaternion.Euler(90f, 0f, 0f));
        }

        private static void CreateOverviewLight()
        {
            GameObject lightObject = new GameObject("SP Overview Light");
            Light overviewLight = lightObject.AddComponent<Light>();
            overviewLight.type = LightType.Directional;
            overviewLight.intensity = 1.2f;
            lightObject.transform.rotation = Quaternion.Euler(50f, -30f, 0f);
        }
    }
}
