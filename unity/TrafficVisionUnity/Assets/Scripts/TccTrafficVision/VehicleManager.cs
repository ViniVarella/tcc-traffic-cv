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
                    vehiclesById[vehicle.id] = vehicleObject;
                }

                vehicleObject.SetActive(true);
                vehicleObject.transform.position = new Vector3(vehicle.x, vehicle.y + verticalOffset, vehicle.z);
                vehicleObject.transform.rotation = Quaternion.Euler(0f, -vehicle.angle, 0f);
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
    }
}
