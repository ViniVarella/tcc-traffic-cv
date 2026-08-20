// Adapted from the MIT-licensed SUMO2Unity RoadNetworkBuilder.
// This version deliberately contains only static SUMO-to-Unity scene import.
// Runtime SUMO communication remains owned by PythonStateReceiver.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Xml.Linq;
using UnityEngine;

namespace TccTrafficVision.SumoImport
{
    [ExecuteAlways]
    public sealed class SumoRoadNetworkImporter : MonoBehaviour
    {
        [Header("SUMO source files")]
        [SerializeField] private TextAsset networkXml;
        [SerializeField] private TextAsset polygonXml;
        [SerializeField] private bool useNetworkOffset = true;

        [Header("Materials")]
        [SerializeField] private Material roadMaterial;
        [SerializeField] private Material junctionMaterial;
        [SerializeField] private Material polygonMaterial;
        [SerializeField] private Material laneMarkingMaterial;
        [SerializeField] private float defaultLaneWidth = 3.2f;
        [SerializeField] private bool generateLaneCenterLines = true;
        [SerializeField, Min(0.01f)] private float laneMarkingWidth = 0.16f;
        [SerializeField, Min(0.1f)] private float laneMarkingDashLength = 2.5f;
        [SerializeField, Min(0f)] private float laneMarkingGapLength = 4f;

        [Header("Generated scene")]
        [SerializeField, HideInInspector] private Transform generatedRoot;

        private static readonly CultureInfo Invariant = CultureInfo.InvariantCulture;

        public void Rebuild()
        {
            if (networkXml == null)
            {
                Debug.LogError("Assign a SUMO .net.xml TextAsset before importing.", this);
                return;
            }

            XDocument network;
            try
            {
                network = XDocument.Parse(networkXml.text);
            }
            catch (Exception exception)
            {
                Debug.LogError($"The selected SUMO network is not valid XML: {exception.Message}", this);
                return;
            }

            ClearGenerated();
            generatedRoot = new GameObject("GeneratedSumoRoadNetwork").transform;
            generatedRoot.SetParent(transform, false);

            Vector2 origin = useNetworkOffset ? ReadNetworkOffset(network) : Vector2.zero;
            Material road = roadMaterial != null ? roadMaterial : CreateFallbackMaterial();
            Material junction = junctionMaterial != null ? junctionMaterial : road;
            Material polygon = polygonMaterial != null ? polygonMaterial : road;
            Material laneMarking = laneMarkingMaterial != null ? laneMarkingMaterial : CreateLaneMarkingFallbackMaterial();

            int laneCount = 0;
            foreach (XElement lane in network.Descendants("lane"))
            {
                List<Vector3> points = ParseShape(lane.Attribute("shape")?.Value, origin);
                if (points.Count < 2)
                {
                    continue;
                }

                float width = ParseFloat(lane.Attribute("width")?.Value, defaultLaneWidth);
                Mesh mesh = CreateLaneMesh(points, width);
                CreateMeshObject($"Lane_{laneCount++}_{lane.Attribute("id")?.Value}", mesh, road, generatedRoot);

                if (generateLaneCenterLines)
                {
                    Mesh markings = CreateDashedLaneCenterLine(
                        points,
                        laneMarkingWidth,
                        laneMarkingDashLength,
                        laneMarkingGapLength);
                    if (markings != null)
                    {
                        CreateMeshObject($"LaneMarking_{laneCount - 1}_{lane.Attribute("id")?.Value}", markings, laneMarking, generatedRoot);
                    }
                }
            }

            int junctionCount = 0;
            foreach (XElement junctionElement in network.Descendants("junction"))
            {
                if (string.Equals(junctionElement.Attribute("type")?.Value, "internal", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                List<Vector3> points = ParseShape(junctionElement.Attribute("shape")?.Value, origin);
                if (points.Count < 3)
                {
                    continue;
                }

                Mesh mesh = CreatePolygonMesh(points, $"Junction_{junctionElement.Attribute("id")?.Value}");
                if (mesh != null)
                {
                    CreateMeshObject($"Junction_{junctionCount++}_{junctionElement.Attribute("id")?.Value}", mesh, junction, generatedRoot);
                }
            }

            ImportPolygons(origin, polygon);
            Debug.Log($"Imported SUMO network: {laneCount} lanes and {junctionCount} junctions.", this);
        }

        public void ClearGenerated()
        {
            if (generatedRoot == null)
            {
                Transform existing = transform.Find("GeneratedSumoRoadNetwork");
                if (existing == null)
                {
                    return;
                }

                generatedRoot = existing;
            }

            if (Application.isPlaying)
            {
                Destroy(generatedRoot.gameObject);
            }
            else
            {
                DestroyImmediate(generatedRoot.gameObject);
            }

            generatedRoot = null;
        }

        private void ImportPolygons(Vector2 origin, Material material)
        {
            if (polygonXml == null)
            {
                return;
            }

            try
            {
                XDocument polygons = XDocument.Parse(polygonXml.text);
                foreach (XElement polygon in polygons.Descendants("poly"))
                {
                    List<Vector3> points = ParseShape(polygon.Attribute("shape")?.Value, origin);
                    if (points.Count < 3)
                    {
                        continue;
                    }

                    Mesh mesh = CreatePolygonMesh(points, $"Polygon_{polygon.Attribute("id")?.Value}");
                    if (mesh != null)
                    {
                        CreateMeshObject($"Polygon_{polygon.Attribute("id")?.Value}", mesh, material, generatedRoot);
                    }
                }
            }
            catch (Exception exception)
            {
                Debug.LogError($"The selected SUMO polygon file is not valid XML: {exception.Message}", this);
            }
        }

        private static Vector2 ReadNetworkOffset(XDocument network)
        {
            XElement location = network.Descendants("location").FirstOrDefault();
            string rawOffset = location?.Attribute("netOffset")?.Value;
            string[] values = rawOffset?.Split(',') ?? Array.Empty<string>();
            return values.Length >= 2
                ? new Vector2(ParseFloat(values[0], 0f), ParseFloat(values[1], 0f))
                : Vector2.zero;
        }

        private static List<Vector3> ParseShape(string rawShape, Vector2 origin)
        {
            List<Vector3> points = new List<Vector3>();
            if (string.IsNullOrWhiteSpace(rawShape))
            {
                return points;
            }

            foreach (string coordinate in rawShape.Split((char[])null, StringSplitOptions.RemoveEmptyEntries))
            {
                string[] values = coordinate.Split(',');
                if (values.Length < 2)
                {
                    continue;
                }

                float x = ParseFloat(values[0], float.NaN);
                float y = ParseFloat(values[1], float.NaN);
                float z = values.Length >= 3 ? ParseFloat(values[2], 0f) : 0f;
                if (!float.IsNaN(x) && !float.IsNaN(y))
                {
                    points.Add(new Vector3(x - origin.x, z, y - origin.y));
                }
            }

            if (points.Count > 1 && Vector3.Distance(points[0], points[points.Count - 1]) < 0.0001f)
            {
                points.RemoveAt(points.Count - 1);
            }

            return points;
        }

        private static float ParseFloat(string value, float fallback)
        {
            return float.TryParse(value, NumberStyles.Float, Invariant, out float result) ? result : fallback;
        }

        private static Mesh CreateLaneMesh(IReadOnlyList<Vector3> points, float width)
        {
            int segments = points.Count - 1;
            Vector3[] vertices = new Vector3[segments * 4];
            Vector2[] uv = new Vector2[vertices.Length];
            int[] triangles = new int[segments * 6];
            float distance = 0f;

            for (int index = 0; index < segments; index++)
            {
                Vector3 from = points[index];
                Vector3 to = points[index + 1];
                Vector3 direction = (to - from).normalized;
                Vector3 perpendicular = new Vector3(-direction.z, 0f, direction.x) * (width * 0.5f);
                int vertex = index * 4;
                int triangle = index * 6;

                vertices[vertex] = from + perpendicular;
                vertices[vertex + 1] = from - perpendicular;
                vertices[vertex + 2] = to + perpendicular;
                vertices[vertex + 3] = to - perpendicular;
                triangles[triangle] = vertex;
                triangles[triangle + 1] = vertex + 2;
                triangles[triangle + 2] = vertex + 1;
                triangles[triangle + 3] = vertex + 2;
                triangles[triangle + 4] = vertex + 3;
                triangles[triangle + 5] = vertex + 1;

                float segmentLength = Vector3.Distance(from, to);
                uv[vertex] = new Vector2(0f, distance / 5f);
                uv[vertex + 1] = new Vector2(1f, distance / 5f);
                uv[vertex + 2] = new Vector2(0f, (distance + segmentLength) / 5f);
                uv[vertex + 3] = new Vector2(1f, (distance + segmentLength) / 5f);
                distance += segmentLength;
            }

            Mesh mesh = new Mesh { name = "SumoLaneMesh", vertices = vertices, triangles = triangles, uv = uv };
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }

        private static Mesh CreatePolygonMesh(IReadOnlyList<Vector3> points, string meshName)
        {
            if (points.Count < 3)
            {
                return null;
            }

            // SUMO junction and poly shapes are simple polygons in the XZ plane.
            List<int> triangles = Triangulate(points.Select(point => new Vector2(point.x, point.z)).ToList());
            if (triangles.Count == 0)
            {
                return null;
            }

            Mesh mesh = new Mesh { name = meshName, vertices = points.ToArray(), triangles = triangles.ToArray() };
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }

        private static Mesh CreateDashedLaneCenterLine(
            IReadOnlyList<Vector3> points,
            float width,
            float dashLength,
            float gapLength)
        {
            List<Vector3> vertices = new List<Vector3>();
            List<int> triangles = new List<int>();
            float patternLength = dashLength + gapLength;
            if (points.Count < 2 || patternLength <= Mathf.Epsilon)
            {
                return null;
            }

            float totalDistance = 0f;
            for (int segment = 0; segment < points.Count - 1; segment++)
            {
                Vector3 from = points[segment];
                Vector3 to = points[segment + 1];
                Vector3 delta = to - from;
                float segmentLength = delta.magnitude;
                if (segmentLength <= Mathf.Epsilon)
                {
                    continue;
                }

                Vector3 direction = delta / segmentLength;
                Vector3 perpendicular = new Vector3(-direction.z, 0f, direction.x) * (width * 0.5f);
                float localDistance = 0f;
                while (localDistance < segmentLength)
                {
                    float patternOffset = (totalDistance + localDistance) % patternLength;
                    if (patternOffset >= dashLength)
                    {
                        localDistance += patternLength - patternOffset;
                        continue;
                    }

                    float dashEnd = Mathf.Min(localDistance + dashLength - patternOffset, segmentLength);
                    AddLineQuad(
                        vertices,
                        triangles,
                        from + direction * localDistance + perpendicular + Vector3.up * 0.015f,
                        from + direction * localDistance - perpendicular + Vector3.up * 0.015f,
                        from + direction * dashEnd + perpendicular + Vector3.up * 0.015f,
                        from + direction * dashEnd - perpendicular + Vector3.up * 0.015f);
                    localDistance = dashEnd;
                }

                totalDistance += segmentLength;
            }

            if (vertices.Count == 0)
            {
                return null;
            }

            Mesh mesh = new Mesh
            {
                name = "SumoLaneMarkingMesh",
                vertices = vertices.ToArray(),
                triangles = triangles.ToArray(),
            };
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }

        private static void AddLineQuad(
            List<Vector3> vertices,
            List<int> triangles,
            Vector3 fromLeft,
            Vector3 fromRight,
            Vector3 toLeft,
            Vector3 toRight)
        {
            int index = vertices.Count;
            vertices.Add(fromLeft);
            vertices.Add(fromRight);
            vertices.Add(toLeft);
            vertices.Add(toRight);
            triangles.Add(index);
            triangles.Add(index + 2);
            triangles.Add(index + 1);
            triangles.Add(index + 2);
            triangles.Add(index + 3);
            triangles.Add(index + 1);
        }

        private static List<int> Triangulate(IReadOnlyList<Vector2> points)
        {
            List<int> result = new List<int>();
            List<int> indices = Enumerable.Range(0, points.Count).ToList();
            if (SignedArea(points) < 0f)
            {
                indices.Reverse();
            }

            int guard = points.Count * points.Count;
            while (indices.Count > 2 && guard-- > 0)
            {
                bool clipped = false;
                for (int i = 0; i < indices.Count; i++)
                {
                    int previous = indices[(i - 1 + indices.Count) % indices.Count];
                    int current = indices[i];
                    int next = indices[(i + 1) % indices.Count];
                    if (!IsEar(points, indices, previous, current, next))
                    {
                        continue;
                    }

                    result.Add(previous);
                    result.Add(current);
                    result.Add(next);
                    indices.RemoveAt(i);
                    clipped = true;
                    break;
                }

                if (!clipped)
                {
                    return new List<int>();
                }
            }

            return result;
        }

        private static bool IsEar(IReadOnlyList<Vector2> points, IReadOnlyList<int> polygon, int previous, int current, int next)
        {
            Vector2 a = points[previous];
            Vector2 b = points[current];
            Vector2 c = points[next];
            if (Cross(a, b, c) <= Mathf.Epsilon)
            {
                return false;
            }

            foreach (int index in polygon)
            {
                if (index != previous && index != current && index != next && PointInTriangle(points[index], a, b, c))
                {
                    return false;
                }
            }

            return true;
        }

        private static float SignedArea(IReadOnlyList<Vector2> points)
        {
            float area = 0f;
            for (int i = 0; i < points.Count; i++)
            {
                Vector2 current = points[i];
                Vector2 next = points[(i + 1) % points.Count];
                area += current.x * next.y - next.x * current.y;
            }

            return area * 0.5f;
        }

        private static float Cross(Vector2 a, Vector2 b, Vector2 c)
        {
            return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
        }

        private static bool PointInTriangle(Vector2 point, Vector2 a, Vector2 b, Vector2 c)
        {
            float first = Cross(a, b, point);
            float second = Cross(b, c, point);
            float third = Cross(c, a, point);
            return first >= 0f && second >= 0f && third >= 0f;
        }

        private static void CreateMeshObject(string objectName, Mesh mesh, Material material, Transform parent)
        {
            GameObject gameObject = new GameObject(objectName);
            gameObject.transform.SetParent(parent, false);
            gameObject.AddComponent<MeshFilter>().sharedMesh = mesh;
            gameObject.AddComponent<MeshRenderer>().sharedMaterial = material;
        }

        private static Material CreateFallbackMaterial()
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
            return new Material(shader) { color = new Color(0.16f, 0.16f, 0.16f) };
        }

        private static Material CreateLaneMarkingFallbackMaterial()
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
            return new Material(shader) { color = new Color(0.95f, 0.93f, 0.82f) };
        }
    }
}
