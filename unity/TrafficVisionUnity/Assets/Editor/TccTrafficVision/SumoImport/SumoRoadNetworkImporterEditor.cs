using TccTrafficVision.SumoImport;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace TccTrafficVision.Editor.SumoImport
{
    [CustomEditor(typeof(SumoRoadNetworkImporter))]
    public sealed class SumoRoadNetworkImporterEditor : UnityEditor.Editor
    {
        public override void OnInspectorGUI()
        {
            DrawDefaultInspector();
            EditorGUILayout.Space();

            SumoRoadNetworkImporter importer = (SumoRoadNetworkImporter)target;
            using (new EditorGUI.DisabledScope(importer == null))
            {
                if (GUILayout.Button("Import / rebuild SUMO road network"))
                {
                    importer.Rebuild();
                    EditorSceneManager.MarkSceneDirty(importer.gameObject.scene);
                }

                if (GUILayout.Button("Clear generated road network"))
                {
                    importer.ClearGenerated();
                    EditorSceneManager.MarkSceneDirty(importer.gameObject.scene);
                }
            }
        }
    }
}
