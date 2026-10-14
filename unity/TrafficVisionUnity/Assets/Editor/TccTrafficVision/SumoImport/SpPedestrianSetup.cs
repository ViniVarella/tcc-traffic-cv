using System.Collections.Generic;
using System.Linq;
using TccTrafficVision;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TccTrafficVision.Editor.SumoImport
{
    /// <summary>
    /// Builds the pedestrian prefabs from the Quaternius models (CC0) and wires
    /// them into the SP scene: looping walk/idle clips, one Animator Controller
    /// per skeleton (men and women have different proportions) and a
    /// PedestrianManager fed by PythonStateReceiver.
    /// </summary>
    public static class SpPedestrianSetup
    {
        private const string SceneAssetPath = "Assets/Scenes/SPImport.unity";
        private const string ModelFolder = "Assets/Art/TrafficModels/Models/Pedestrians";
        private const string PrefabFolder = "Assets/Prefabs/Pedestrians";
        private const string SynchronizationRootName = "SP Dynamic Synchronization";
        private const string PedestriansRootName = "SP Pedestrians";

        private static readonly (string folder, string controllerName)[] Groups =
        {
            ("Male", "Male Pedestrian"),
            ("Female", "Female Pedestrian"),
        };

        [MenuItem("Traffic Vision/Pedestrians/Configure SP Pedestrians")]
        public static void Configure()
        {
            Scene scene = SceneManager.GetActiveScene();
            if (scene.path != SceneAssetPath)
            {
                EditorUtility.DisplayDialog(
                    "Open SPImport first",
                    "Open Assets/Scenes/SPImport.unity before configuring the pedestrians.",
                    "OK");
                return;
            }

            GameObject synchronizationRoot = GameObject.Find(SynchronizationRootName);
            PythonStateReceiver receiver = synchronizationRoot != null ? synchronizationRoot.GetComponent<PythonStateReceiver>() : null;
            if (receiver == null)
            {
                EditorUtility.DisplayDialog(
                    "Configure dynamic sync first",
                    "Run Traffic Vision > SUMO > Configure SP Dynamic Sync before configuring the pedestrians.",
                    "OK");
                return;
            }

            EnsureFolder(PrefabFolder);
            List<GameObject> prefabs = new List<GameObject>();
            foreach ((string folder, string controllerName) in Groups)
            {
                string[] modelPaths = AssetDatabase.FindAssets("t:Model", new[] { $"{ModelFolder}/{folder}" })
                    .Select(AssetDatabase.GUIDToAssetPath)
                    .Where(path => path.EndsWith(".fbx", System.StringComparison.OrdinalIgnoreCase))
                    .OrderBy(path => path)
                    .ToArray();
                if (modelPaths.Length == 0)
                {
                    Debug.LogWarning($"No pedestrian models found in {ModelFolder}/{folder}.");
                    continue;
                }

                foreach (string modelPath in modelPaths)
                {
                    EnsureLoopingClips(modelPath);
                }

                AnimatorController controller = CreateController(controllerName, modelPaths[0]);
                if (controller == null)
                {
                    continue;
                }

                foreach (string modelPath in modelPaths)
                {
                    GameObject prefab = CreatePrefab(modelPath, controller);
                    if (prefab != null)
                    {
                        prefabs.Add(prefab);
                    }
                }
            }

            if (prefabs.Count == 0)
            {
                EditorUtility.DisplayDialog(
                    "Pedestrian models are not ready",
                    "No pedestrian prefab was created. Check the Console for missing models or clips.",
                    "OK");
                return;
            }

            GameObject pedestriansRoot = FindOrCreateChild(synchronizationRoot.transform, PedestriansRootName);
            // Explicit null checks: Unity's fake-null objects defeat the ?? operator.
            PedestrianManager manager = synchronizationRoot.GetComponent<PedestrianManager>();
            if (manager == null)
            {
                manager = synchronizationRoot.AddComponent<PedestrianManager>();
            }

            SerializedObject managerProperties = new SerializedObject(manager);
            managerProperties.FindProperty("pedestriansRoot").objectReferenceValue = pedestriansRoot.transform;
            SerializedProperty prefabProperty = managerProperties.FindProperty("pedestrianPrefabs");
            prefabProperty.arraySize = prefabs.Count;
            for (int index = 0; index < prefabs.Count; index++)
            {
                prefabProperty.GetArrayElementAtIndex(index).objectReferenceValue = prefabs[index];
            }

            managerProperties.ApplyModifiedPropertiesWithoutUndo();

            SerializedObject receiverProperties = new SerializedObject(receiver);
            receiverProperties.FindProperty("pedestrianManager").objectReferenceValue = manager;
            receiverProperties.ApplyModifiedPropertiesWithoutUndo();

            EditorSceneManager.MarkSceneDirty(scene);
            Selection.activeObject = manager;
            Debug.Log(
                $"Configured {prefabs.Count} SP pedestrian prefabs. Save the scene (Cmd+S), enter Play Mode and run " +
                "python -m experiments.test_sumo_to_unity --config configs/sp.yaml --scenario calibrated_ped --steps 300 --send-interval 0.1",
                manager);
        }

        private static void EnsureLoopingClips(string modelPath)
        {
            ModelImporter importer = AssetImporter.GetAtPath(modelPath) as ModelImporter;
            if (importer == null)
            {
                return;
            }

            ModelImporterClipAnimation[] clips = importer.clipAnimations.Length > 0
                ? importer.clipAnimations
                : importer.defaultClipAnimations;
            bool changed = importer.clipAnimations.Length == 0;
            foreach (ModelImporterClipAnimation clip in clips)
            {
                bool shouldLoop = IsWalk(clip.name) || IsIdle(clip.name);
                if (clip.loopTime != shouldLoop)
                {
                    clip.loopTime = shouldLoop;
                    changed = true;
                }
            }

            if (changed)
            {
                importer.clipAnimations = clips;
                importer.SaveAndReimport();
            }
        }

        private static AnimatorController CreateController(string controllerName, string clipSourcePath)
        {
            AnimationClip[] clips = AssetDatabase.LoadAllAssetsAtPath(clipSourcePath)
                .OfType<AnimationClip>()
                .Where(clip => !clip.name.StartsWith("__preview__"))
                .ToArray();
            AnimationClip walk = clips.FirstOrDefault(clip => IsWalk(clip.name));
            AnimationClip idle = clips.FirstOrDefault(clip => IsIdle(clip.name));
            if (walk == null || idle == null)
            {
                Debug.LogWarning($"Walk or Idle clip missing in {clipSourcePath}. Clips: {string.Join(", ", clips.Select(clip => clip.name))}");
                return null;
            }

            // Recreated on every run so the menu stays idempotent; the prefabs
            // below are recreated too and pick up the new controller.
            string controllerPath = $"{PrefabFolder}/{controllerName}.controller";
            AssetDatabase.DeleteAsset(controllerPath);
            AnimatorController controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);
            controller.AddParameter(PedestrianManager.WalkingParameter, AnimatorControllerParameterType.Bool);

            AnimatorStateMachine stateMachine = controller.layers[0].stateMachine;
            AnimatorState idleState = stateMachine.AddState("Idle");
            idleState.motion = idle;
            AnimatorState walkState = stateMachine.AddState("Walk");
            walkState.motion = walk;
            stateMachine.defaultState = idleState;

            AddTransition(idleState, walkState, AnimatorConditionMode.If);
            AddTransition(walkState, idleState, AnimatorConditionMode.IfNot);
            AssetDatabase.SaveAssets();
            return controller;
        }

        private static void AddTransition(AnimatorState from, AnimatorState to, AnimatorConditionMode mode)
        {
            AnimatorStateTransition transition = from.AddTransition(to);
            transition.hasExitTime = false;
            transition.duration = 0.15f;
            transition.AddCondition(mode, 0f, PedestrianManager.WalkingParameter);
        }

        private static GameObject CreatePrefab(string modelPath, AnimatorController controller)
        {
            GameObject model = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            if (model == null)
            {
                Debug.LogWarning($"Pedestrian model is missing or not imported: {modelPath}");
                return null;
            }

            string prefabName = System.IO.Path.GetFileNameWithoutExtension(modelPath).Replace("Smooth_", string.Empty);
            GameObject root = new GameObject(prefabName);
            GameObject modelInstance = PrefabUtility.InstantiatePrefab(model) as GameObject;
            modelInstance.transform.SetParent(root.transform, false);

            Animator animator = modelInstance.GetComponent<Animator>();
            if (animator == null)
            {
                animator = modelInstance.AddComponent<Animator>();
            }

            animator.runtimeAnimatorController = controller;
            animator.applyRootMotion = false;
            // Characters outside every camera keep their pose but skip skinning.
            animator.cullingMode = AnimatorCullingMode.CullUpdateTransforms;

            GameObject prefab = PrefabUtility.SaveAsPrefabAsset(root, $"{PrefabFolder}/{prefabName}.prefab");
            Object.DestroyImmediate(root);
            return prefab;
        }

        private static bool IsWalk(string clipName) => clipName.EndsWith("_Walk");

        private static bool IsIdle(string clipName) => clipName.EndsWith("_Idle");

        private static GameObject FindOrCreateChild(Transform parent, string objectName)
        {
            Transform existing = parent.Find(objectName);
            if (existing != null)
            {
                return existing.gameObject;
            }

            GameObject created = new GameObject(objectName);
            created.transform.SetParent(parent, false);
            return created;
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
    }
}
