using UnityEngine;

namespace TccTrafficVision
{
    public class TrafficLightVisualController : MonoBehaviour
    {
        [SerializeField] private Renderer targetRenderer;

        public void ApplyState(TrafficLightStateMessage[] trafficLights)
        {
            if (trafficLights == null || trafficLights.Length == 0 || trafficLights[0] == null)
            {
                return;
            }

            if (targetRenderer == null)
            {
                targetRenderer = GetComponent<Renderer>();
            }

            if (targetRenderer == null || targetRenderer.material == null)
            {
                return;
            }

            targetRenderer.material.color = ResolveColor(trafficLights[0].state);
        }

        private static Color ResolveColor(string signalState)
        {
            if (string.IsNullOrEmpty(signalState))
            {
                return Color.gray;
            }

            if (signalState.Contains("G") || signalState.Contains("g"))
            {
                return Color.green;
            }

            if (signalState.Contains("y"))
            {
                return Color.yellow;
            }

            return Color.red;
        }
    }
}
