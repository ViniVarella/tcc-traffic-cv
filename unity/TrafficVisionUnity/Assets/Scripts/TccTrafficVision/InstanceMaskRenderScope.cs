using System;
using System.Collections.Generic;
using UnityEngine;

namespace TccTrafficVision
{
    /// <summary>
    /// Temporarily moves vehicle renderers to the dedicated instance-mask layer
    /// and replaces their materials with unique unlit colors. Dispose restores
    /// the scene before the next visual frame.
    /// </summary>
    internal sealed class InstanceMaskRenderScope : IDisposable
    {
        public const int MaskLayer = 8;

        private readonly List<(GameObject gameObject, int layer)> originalLayers = new List<(GameObject, int)>();
        private readonly List<(Renderer renderer, Material[] materials)> originalMaterials = new List<(Renderer, Material[])>();
        private readonly List<Material> maskMaterials = new List<Material>();
        private bool disposed;

        public static InstanceMaskRenderScope Begin(Material template)
        {
            if (template == null)
            {
                throw new ArgumentNullException(nameof(template));
            }

            var scope = new InstanceMaskRenderScope();
            VehicleGroundTruth[] vehicles = UnityEngine.Object.FindObjectsByType<VehicleGroundTruth>(
                FindObjectsInactive.Exclude,
                FindObjectsSortMode.None);
            if (vehicles.Length > 125)
            {
                throw new InvalidOperationException("Instance-mask palette supports at most 125 active vehicles per frame.");
            }
            for (int index = 0; index < vehicles.Length; index++)
            {
                scope.AddVehicle(vehicles[index], EncodeColor(index + 1), template);
            }

            return scope;
        }

        public void Dispose()
        {
            if (disposed)
            {
                return;
            }

            disposed = true;
            foreach ((Renderer renderer, Material[] materials) in originalMaterials)
            {
                if (renderer != null)
                {
                    renderer.sharedMaterials = materials;
                }
            }

            foreach ((GameObject gameObject, int layer) in originalLayers)
            {
                if (gameObject != null)
                {
                    gameObject.layer = layer;
                }
            }

            foreach (Material material in maskMaterials)
            {
                UnityEngine.Object.Destroy(material);
            }
        }

        private void AddVehicle(VehicleGroundTruth vehicle, Color32 color, Material template)
        {
            if (vehicle == null || !vehicle.gameObject.activeInHierarchy)
            {
                return;
            }

            vehicle.AssignInstanceColor(color);
            foreach (Transform transform in vehicle.GetComponentsInChildren<Transform>(true))
            {
                originalLayers.Add((transform.gameObject, transform.gameObject.layer));
                transform.gameObject.layer = MaskLayer;
            }

            Material material = new Material(template);
            material.SetColor("_BaseColor", color);
            maskMaterials.Add(material);
            foreach (Renderer renderer in vehicle.GetComponentsInChildren<Renderer>(true))
            {
                if (renderer == null || !renderer.enabled)
                {
                    continue;
                }

                Material[] previous = renderer.sharedMaterials;
                originalMaterials.Add((renderer, previous));
                int count = Mathf.Max(1, previous.Length);
                var replacement = new Material[count];
                for (int materialIndex = 0; materialIndex < replacement.Length; materialIndex++)
                {
                    replacement[materialIndex] = material;
                }
                renderer.sharedMaterials = replacement;
            }
        }

        private static Color32 EncodeColor(int value)
        {
            // Five bright levels per channel yield 125 unique IDs. Black is
            // reserved for background, and the result remains easy to inspect.
            int encoded = value - 1;
            return new Color32(
                (byte)(((encoded % 5) + 1) * 51),
                (byte)((((encoded / 5) % 5) + 1) * 51),
                (byte)((((encoded / 25) % 5) + 1) * 51),
                255);
        }
    }
}
