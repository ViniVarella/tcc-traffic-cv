using System.Collections.Generic;
using UnityEngine;

namespace TccTrafficVision
{
    /// <summary>
    /// Renders the SUMO persons received from Python. Like VehicleManager it
    /// only follows the transmitted state; it never moves anyone on its own.
    /// Objects of pedestrians that left the network are reused by new ones,
    /// so long runs do not accumulate inactive characters.
    /// </summary>
    public class PedestrianManager : MonoBehaviour
    {
        public const string WalkingParameter = "Walking";

        [SerializeField] private Transform pedestriansRoot;
        [SerializeField] private List<GameObject> pedestrianPrefabs = new List<GameObject>();
        // Extra yaw applied to the prefabs when the model's forward axis is
        // not Unity +Z. SUMO headings map to Unity yaw as for vehicles.
        [SerializeField] private float prefabYawOffset;
        [SerializeField] private float verticalOffset;
        // Below this speed (m/s) the character plays the idle clip.
        [SerializeField, Min(0f)] private float walkingSpeedThreshold = 0.1f;
        // Speed (m/s) at which the walk clip plays at its authored rate.
        [SerializeField, Min(0.1f)] private float clipWalkingSpeed = 1.3f;

        private readonly Dictionary<string, Pedestrian> pedestriansById = new Dictionary<string, Pedestrian>();
        private readonly Dictionary<int, Stack<Pedestrian>> freeByPrefab = new Dictionary<int, Stack<Pedestrian>>();
        private readonly HashSet<string> activeIds = new HashSet<string>();
        private readonly List<string> leftIds = new List<string>();

        private sealed class Pedestrian
        {
            public GameObject gameObject;
            public Animator animator;
            public int prefabIndex;
        }

        public void ApplyState(PedestrianStateMessage[] pedestrians)
        {
            activeIds.Clear();
            if (pedestrians != null)
            {
                foreach (PedestrianStateMessage pedestrian in pedestrians)
                {
                    if (pedestrian == null || string.IsNullOrWhiteSpace(pedestrian.id))
                    {
                        continue;
                    }

                    activeIds.Add(pedestrian.id);
                    if (!pedestriansById.TryGetValue(pedestrian.id, out Pedestrian entry))
                    {
                        entry = Acquire(pedestrian.id);
                        pedestriansById[pedestrian.id] = entry;
                    }

                    Apply(entry, pedestrian);
                }
            }

            leftIds.Clear();
            foreach (KeyValuePair<string, Pedestrian> pair in pedestriansById)
            {
                if (!activeIds.Contains(pair.Key))
                {
                    leftIds.Add(pair.Key);
                }
            }

            foreach (string id in leftIds)
            {
                Release(pedestriansById[id]);
                pedestriansById.Remove(id);
            }
        }

        private void Apply(Pedestrian entry, PedestrianStateMessage state)
        {
            Transform target = entry.gameObject.transform;
            target.position = new Vector3(state.x, state.y + verticalOffset, state.z);
            // SUMO uses navigational angles: 0° points north (+Z) and 90° east (+X).
            target.rotation = Quaternion.Euler(0f, state.angle + prefabYawOffset, 0f);

            if (entry.animator == null)
            {
                return;
            }

            bool walking = state.speed > walkingSpeedThreshold;
            entry.animator.SetBool(WalkingParameter, walking);
            entry.animator.speed = walking ? Mathf.Clamp(state.speed / clipWalkingSpeed, 0.5f, 1.6f) : 1f;
        }

        private Pedestrian Acquire(string pedestrianId)
        {
            int prefabIndex = SelectPrefabIndex(pedestrianId);
            Pedestrian entry;
            if (freeByPrefab.TryGetValue(prefabIndex, out Stack<Pedestrian> free) && free.Count > 0)
            {
                entry = free.Pop();
            }
            else
            {
                entry = Create(prefabIndex);
            }

            entry.gameObject.name = pedestrianId;
            entry.gameObject.SetActive(true);
            return entry;
        }

        private void Release(Pedestrian entry)
        {
            entry.gameObject.SetActive(false);
            if (!freeByPrefab.TryGetValue(entry.prefabIndex, out Stack<Pedestrian> free))
            {
                free = new Stack<Pedestrian>();
                freeByPrefab[entry.prefabIndex] = free;
            }

            free.Push(entry);
        }

        private Pedestrian Create(int prefabIndex)
        {
            Transform parent = pedestriansRoot != null ? pedestriansRoot : transform;
            GameObject instance;
            if (prefabIndex >= 0)
            {
                instance = Instantiate(pedestrianPrefabs[prefabIndex], parent, false);
            }
            else
            {
                // Without configured prefabs, a capsule keeps the pipeline visible.
                instance = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                instance.transform.SetParent(parent, false);
                instance.transform.localScale = new Vector3(0.5f, 0.85f, 0.5f);
                Collider capsuleCollider = instance.GetComponent<Collider>();
                if (capsuleCollider != null)
                {
                    Destroy(capsuleCollider);
                }
            }

            Animator animator = instance.GetComponentInChildren<Animator>();
            if (animator != null)
            {
                animator.applyRootMotion = false;
            }

            return new Pedestrian { gameObject = instance, animator = animator, prefabIndex = prefabIndex };
        }

        private int SelectPrefabIndex(string pedestrianId)
        {
            if (pedestrianPrefabs == null || pedestrianPrefabs.Count == 0)
            {
                return -1;
            }

            int stableIndex = StableHash(pedestrianId) % pedestrianPrefabs.Count;
            for (int offset = 0; offset < pedestrianPrefabs.Count; offset++)
            {
                int index = (stableIndex + offset) % pedestrianPrefabs.Count;
                if (pedestrianPrefabs[index] != null)
                {
                    return index;
                }
            }

            return -1;
        }

        private static int StableHash(string value)
        {
            unchecked
            {
                int hash = 17;
                foreach (char character in value ?? string.Empty)
                {
                    hash = hash * 31 + character;
                }

                return hash & int.MaxValue;
            }
        }
    }
}
