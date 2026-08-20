using System.Collections.Generic;
using UnityEngine;

namespace TccTrafficVision
{
    public class VehicleManager : MonoBehaviour
    {
        [SerializeField] private Transform vehiclesRoot;
        [SerializeField] private Vector3 vehicleScale = new Vector3(1.2f, 1.0f, 2.4f);
        [SerializeField] private float verticalOffset = 0.5f;

        private readonly Dictionary<string, GameObject> vehiclesById = new Dictionary<string, GameObject>();

        public void ApplyState(VehicleStateMessage[] vehicles)
        {
            var activeIds = new HashSet<string>();
            if (vehicles == null)
            {
                SetInactiveMissing(activeIds);
                return;
            }

            foreach (var vehicle in vehicles)
            {
                if (vehicle == null || string.IsNullOrWhiteSpace(vehicle.id))
                {
                    continue;
                }

                activeIds.Add(vehicle.id);
                if (!vehiclesById.TryGetValue(vehicle.id, out var vehicleObject))
                {
                    vehicleObject = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    vehicleObject.name = vehicle.id;
                    vehicleObject.transform.localScale = vehicleScale;
                    vehicleObject.transform.SetParent(vehiclesRoot != null ? vehiclesRoot : transform, false);
                    ConfigureVehicleVisual(vehicleObject, vehicle.type);
                    vehiclesById[vehicle.id] = vehicleObject;
                }

                vehicleObject.SetActive(true);
                vehicleObject.transform.position = new Vector3(vehicle.x, vehicle.y + verticalOffset, vehicle.z);
                // SUMO uses navigational angles: 0° points north (+Z here) and
                // 90° points east (+X here). This matches Unity's positive yaw.
                vehicleObject.transform.rotation = Quaternion.Euler(0f, vehicle.angle, 0f);
            }

            SetInactiveMissing(activeIds);
        }

        private void SetInactiveMissing(HashSet<string> activeIds)
        {
            foreach (var entry in vehiclesById)
            {
                if (!activeIds.Contains(entry.Key))
                {
                    entry.Value.SetActive(false);
                }
            }
        }

        private static void ConfigureVehicleVisual(GameObject vehicleObject, string vehicleType)
        {
            Collider bodyCollider = vehicleObject.GetComponent<Collider>();
            if (bodyCollider != null)
            {
                Object.Destroy(bodyCollider);
            }

            SetRendererColor(vehicleObject.GetComponent<Renderer>(), GetVehicleColor(vehicleType));

            GameObject frontMarker = GameObject.CreatePrimitive(PrimitiveType.Cube);
            frontMarker.name = "Front Marker";
            frontMarker.transform.SetParent(vehicleObject.transform, false);
            frontMarker.transform.localPosition = new Vector3(0f, 0.58f, 0.42f);
            frontMarker.transform.localScale = new Vector3(0.72f, 0.16f, 0.28f);

            Collider markerCollider = frontMarker.GetComponent<Collider>();
            if (markerCollider != null)
            {
                Object.Destroy(markerCollider);
            }

            SetRendererColor(frontMarker.GetComponent<Renderer>(), new Color(0.94f, 0.97f, 1f));
        }

        private static void SetRendererColor(Renderer renderer, Color color)
        {
            if (renderer == null)
            {
                return;
            }

            MaterialPropertyBlock properties = new MaterialPropertyBlock();
            properties.SetColor("_Color", color);
            properties.SetColor("_BaseColor", color);
            renderer.SetPropertyBlock(properties);
        }

        private static Color GetVehicleColor(string vehicleType)
        {
            string normalizedType = vehicleType?.ToLowerInvariant() ?? string.Empty;
            if (normalizedType.Contains("bus"))
            {
                return new Color(0.96f, 0.55f, 0.16f);
            }

            if (normalizedType.Contains("truck"))
            {
                return new Color(0.69f, 0.32f, 0.2f);
            }

            if (normalizedType.Contains("motor"))
            {
                return new Color(0.68f, 0.37f, 0.9f);
            }

            return new Color(0.12f, 0.55f, 0.9f);
        }
    }
}
