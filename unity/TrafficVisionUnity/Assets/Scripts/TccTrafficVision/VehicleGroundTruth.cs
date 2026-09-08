using System;
using System.Collections.Generic;
using UnityEngine;

namespace TccTrafficVision
{
    /// <summary>
    /// Associates a Unity vehicle instance with its SUMO identity and exposes a
    /// normalized 2D bounding box for a calibrated camera.  This is training
    /// metadata only; it never participates in the traffic controller.
    /// </summary>
    public sealed class VehicleGroundTruth : MonoBehaviour
    {
        [SerializeField] private string vehicleId;
        [SerializeField] private string vehicleType;
        private Color32 instanceColor;

        private Renderer[] cachedRenderers;

        public string VehicleId => vehicleId;
        public string VehicleType => vehicleType;

        public void AssignInstanceColor(Color32 color)
        {
            instanceColor = color;
        }

        public void Configure(string id, string type)
        {
            vehicleId = id;
            vehicleType = type;
            cachedRenderers = GetComponentsInChildren<Renderer>(true);
        }

        public bool TryGetNormalizedBox(Camera camera, out GroundTruthVehicle annotation)
        {
            annotation = default;
            if (camera == null || !isActiveAndEnabled || !gameObject.activeInHierarchy)
            {
                return false;
            }

            cachedRenderers ??= GetComponentsInChildren<Renderer>(true);
            float minX = 1f;
            float minY = 1f;
            float maxX = 0f;
            float maxY = 0f;
            bool hasVisiblePoint = false;

            foreach (Renderer renderer in cachedRenderers)
            {
                if (renderer == null || !renderer.enabled || !renderer.gameObject.activeInHierarchy)
                {
                    continue;
                }

                Bounds bounds = renderer.bounds;
                foreach (Vector3 corner in GetBoundsCorners(bounds))
                {
                    Vector3 viewport = camera.WorldToViewportPoint(corner);
                    if (viewport.z <= camera.nearClipPlane)
                    {
                        continue;
                    }

                    minX = Mathf.Min(minX, viewport.x);
                    minY = Mathf.Min(minY, viewport.y);
                    maxX = Mathf.Max(maxX, viewport.x);
                    maxY = Mathf.Max(maxY, viewport.y);
                    hasVisiblePoint = true;
                }
            }

            minX = Mathf.Clamp01(minX);
            minY = Mathf.Clamp01(minY);
            maxX = Mathf.Clamp01(maxX);
            maxY = Mathf.Clamp01(maxY);
            float width = maxX - minX;
            float height = maxY - minY;
            if (!hasVisiblePoint || width <= 0.002f || height <= 0.002f)
            {
                return false;
            }

            annotation = new GroundTruthVehicle
            {
                vehicle_id = vehicleId,
                vehicle_type = vehicleType,
                class_id = 0,
                color_r = instanceColor.r,
                color_g = instanceColor.g,
                color_b = instanceColor.b,
                center_x = (minX + maxX) * 0.5f,
                // Unity viewport coordinates start at the bottom; YOLO labels
                // use a conventional image origin at the top.
                center_y = 1f - ((minY + maxY) * 0.5f),
                width = width,
                height = height,
            };
            return true;
        }

        public static GroundTruthVehicle[] Collect(Camera camera)
        {
            VehicleGroundTruth[] vehicles = FindObjectsByType<VehicleGroundTruth>(FindObjectsInactive.Exclude, FindObjectsSortMode.None);
            var annotations = new List<GroundTruthVehicle>(vehicles.Length);
            foreach (VehicleGroundTruth vehicle in vehicles)
            {
                if (vehicle.TryGetNormalizedBox(camera, out GroundTruthVehicle annotation))
                {
                    annotations.Add(annotation);
                }
            }

            return annotations.ToArray();
        }

        private static IEnumerable<Vector3> GetBoundsCorners(Bounds bounds)
        {
            Vector3 min = bounds.min;
            Vector3 max = bounds.max;
            yield return new Vector3(min.x, min.y, min.z);
            yield return new Vector3(min.x, min.y, max.z);
            yield return new Vector3(min.x, max.y, min.z);
            yield return new Vector3(min.x, max.y, max.z);
            yield return new Vector3(max.x, min.y, min.z);
            yield return new Vector3(max.x, min.y, max.z);
            yield return new Vector3(max.x, max.y, min.z);
            yield return new Vector3(max.x, max.y, max.z);
        }
    }

    [Serializable]
    public struct GroundTruthVehicle
    {
        public string vehicle_id;
        public string vehicle_type;
        public int class_id;
        public byte color_r;
        public byte color_g;
        public byte color_b;
        public float center_x;
        public float center_y;
        public float width;
        public float height;
    }
}
