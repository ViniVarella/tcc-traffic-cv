using UnityEngine;

namespace TccTrafficVision
{
    /// <summary>
    /// One pedestrian signal head. linkIndex is the SUMO traffic-light link of
    /// its crossing (10-13 in Cruzamento.ped.net.xml); TrafficLightVisualController
    /// feeds it the character of that link: green walks, anything else is red.
    /// </summary>
    public class PedestrianSignalHead : MonoBehaviour
    {
        private static readonly Color Red = new Color(0.95f, 0.12f, 0.08f);
        private static readonly Color Green = new Color(0.15f, 0.9f, 0.3f);
        private const float OffFactor = 0.18f;

        [SerializeField] private int linkIndex = -1;
        [SerializeField] private Renderer redLamp;
        [SerializeField] private Renderer greenLamp;

        private MaterialPropertyBlock properties;

        public int LinkIndex => linkIndex;

        public void Configure(int link, Renderer red, Renderer green)
        {
            linkIndex = link;
            redLamp = red;
            greenLamp = green;
        }

        public void ApplyState(string state)
        {
            bool walk = linkIndex >= 0 && state != null && linkIndex < state.Length &&
                        (state[linkIndex] == 'G' || state[linkIndex] == 'g');
            SetLamp(redLamp, Red, !walk);
            SetLamp(greenLamp, Green, walk);
        }

        private void SetLamp(Renderer lamp, Color color, bool isOn)
        {
            if (lamp == null)
            {
                return;
            }

            properties ??= new MaterialPropertyBlock();
            Color shown = isOn ? color : color * OffFactor;
            lamp.GetPropertyBlock(properties);
            properties.SetColor("_Color", shown);
            properties.SetColor("_BaseColor", shown);
            lamp.SetPropertyBlock(properties);
        }
    }
}
