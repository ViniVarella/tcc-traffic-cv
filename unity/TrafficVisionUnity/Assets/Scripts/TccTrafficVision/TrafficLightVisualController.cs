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

            string state = trafficLights[0].state;
            // Link indices are defined by Cruzamento.net.xml. E2 (East) owns
            // 0-2, E3 (South) owns 3-8, and E6 (West) owns index 9.
            bool appliedToPosts = ApplyPost("Signal Post East", state, 0, 2)
                                  | ApplyPost("Signal Post South", state, 3, 8)
                                  | ApplyPost("Signal Post West", state, 9, 9);
            if (appliedToPosts)
            {
                return;
            }

            ResolveFallbackRenderer();
            if (targetRenderer == null || targetRenderer.material == null)
            {
                return;
            }

            targetRenderer.material.color = ResolveColor(state);
        }

        private bool ApplyPost(string postName, string state, int firstLinkIndex, int lastLinkIndex)
        {
            Transform post = transform.Find(postName);
            if (post == null)
            {
                return false;
            }

            char approachState = ResolveApproachState(state, firstLinkIndex, lastLinkIndex);
            SetLamp(post.Find("Signal Red")?.GetComponent<Renderer>(), Color.red, approachState == 'r');
            SetLamp(post.Find("Signal Yellow")?.GetComponent<Renderer>(), Color.yellow, approachState == 'y');
            SetLamp(post.Find("Signal Green")?.GetComponent<Renderer>(), Color.green, approachState == 'G');
            return true;
        }

        private static char ResolveApproachState(string state, int firstLinkIndex, int lastLinkIndex)
        {
            if (string.IsNullOrEmpty(state))
            {
                return 'r';
            }

            bool hasYellow = false;
            int lastAvailableIndex = Mathf.Min(lastLinkIndex, state.Length - 1);
            for (int index = Mathf.Max(0, firstLinkIndex); index <= lastAvailableIndex; index++)
            {
                char linkState = state[index];
                if (linkState == 'G' || linkState == 'g')
                {
                    return 'G';
                }

                if (linkState == 'y' || linkState == 'Y')
                {
                    hasYellow = true;
                }
            }

            return hasYellow ? 'y' : 'r';
        }

        private void ResolveFallbackRenderer()
        {
            if (targetRenderer == null)
            {
                targetRenderer = GetComponent<Renderer>() ?? GetComponentInChildren<Renderer>();
            }
        }

        private static void SetLamp(Renderer renderer, Color activeColor, bool isActive)
        {
            if (renderer == null)
            {
                return;
            }

            Color color = isActive ? activeColor : activeColor * 0.18f;
            Material material = renderer.material;
            material.color = color;
            if (material.HasProperty("_BaseColor"))
            {
                material.SetColor("_BaseColor", color);
            }
        }

        private static Color ResolveColor(string signalState)
        {
            if (string.IsNullOrEmpty(signalState))
            {
                return Color.gray;
            }

            if (HasGreen(signalState))
            {
                return Color.green;
            }

            if (HasYellow(signalState))
            {
                return Color.yellow;
            }

            return Color.red;
        }

        private static bool HasGreen(string signalState)
        {
            return !string.IsNullOrEmpty(signalState) && (signalState.Contains("G") || signalState.Contains("g"));
        }

        private static bool HasYellow(string signalState)
        {
            return !string.IsNullOrEmpty(signalState) && signalState.Contains("y");
        }
    }
}
