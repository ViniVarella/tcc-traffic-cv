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
        [SerializeField] private Material centerLineMaterial;
        [SerializeField] private Material sidewalkMaterial;
        [SerializeField] private float defaultLaneWidth = 3.2f;
        [SerializeField] private bool generateLaneCenterLines = true;
        [SerializeField, Min(0.01f)] private float laneMarkingWidth = 0.16f;
        [SerializeField, Min(0.1f)] private float laneMarkingDashLength = 2.5f;
        [SerializeField, Min(0f)] private float laneMarkingGapLength = 4f;
        [SerializeField, Min(0.01f)] private float stopLineWidth = 0.32f;
        [SerializeField, Min(0f)] private float stopLineOffset = 0f;
        [SerializeField, Min(0f)] private float stopLineOverlap = 0.20f;
        [SerializeField, Min(0.5f)] private float sidewalkWidth = 2.4f;

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
            Material centerLine = centerLineMaterial != null ? centerLineMaterial : CreateCenterLineFallbackMaterial();
            Material sidewalk = sidewalkMaterial != null ? sidewalkMaterial : CreateSidewalkFallbackMaterial();

            int laneCount = 0;
            int generatedLaneCount = 0;
            foreach (XElement edge in network.Descendants("edge"))
            {
                // Internal SUMO lanes describe permitted turning trajectories.
                // The junction polygon is the visual surface for that area;
                // drawing all of those paths creates overlapping strips and
                // misleading markings in the middle of the intersection.
                bool isInternal = string.Equals(edge.Attribute("function")?.Value, "internal", StringComparison.OrdinalIgnoreCase);
                foreach (XElement lane in edge.Elements("lane"))
                {
                    laneCount++;
                    if (isInternal)
                    {
                        continue;
                    }

                    List<Vector3> points = ParseShape(lane.Attribute("shape")?.Value, origin);
                    if (points.Count < 2)
                    {
                        continue;
                    }

                    float width = ParseFloat(lane.Attribute("width")?.Value, defaultLaneWidth);
                    Mesh mesh = CreateLaneMesh(points, width);
                    CreateMeshObject($"Lane_{generatedLaneCount++}_{lane.Attribute("id")?.Value}", mesh, road, generatedRoot);
                }
            }

            CreateRoadSidewalks(network, origin, sidewalk, generatedRoot);

            if (generateLaneCenterLines)
            {
                CreateLaneBoundaryMarkings(network, origin, laneMarking, centerLine, generatedRoot);
                CreateTrafficLightStopLines(network, origin, laneMarking, generatedRoot);
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
            Debug.Log($"Imported SUMO network: {laneCount} SUMO lanes ({generatedLaneCount} rendered road lanes) and {junctionCount} junctions.", this);
        }

        private void CreateLaneBoundaryMarkings(XDocument network, Vector2 origin, Material laneMaterial, Material centerMaterial, Transform parent)
        {
            List<EdgeLaneGeometry> edges = ReadExternalEdgeGeometry(network, origin);

            int markingCount = 0;
            foreach (EdgeLaneGeometry edge in edges)
            {
                for (int laneIndex = 0; laneIndex < edge.laneShapes.Count - 1; laneIndex++)
                {
                    List<Vector3> boundary = CreateMidpointShape(edge.laneShapes[laneIndex], edge.laneShapes[laneIndex + 1]);
                    if (boundary == null)
                    {
                        continue;
                    }

                    Mesh markings = CreateDashedLaneCenterLine(boundary, laneMarkingWidth, laneMarkingDashLength, laneMarkingGapLength);
                    if (markings != null)
                    {
                        CreateMeshObject($"LaneBoundary_{markingCount++}_{edge.edge.Attribute("id")?.Value}_{laneIndex}", markings, laneMaterial, parent);
                    }
                }
            }

            CreateOpposingDirectionCenterLines(edges, centerMaterial, parent);
        }

        private List<EdgeLaneGeometry> ReadExternalEdgeGeometry(XDocument network, Vector2 origin)
        {
            List<EdgeLaneGeometry> edges = new List<EdgeLaneGeometry>();
            foreach (XElement edge in network.Descendants("edge")
                         .Where(candidate => !string.Equals(candidate.Attribute("function")?.Value, "internal", StringComparison.OrdinalIgnoreCase)))
            {
                List<List<Vector3>> shapes = new List<List<Vector3>>();
                List<float> widths = new List<float>();
                foreach (XElement lane in edge.Elements("lane").OrderBy(lane => ParseFloat(lane.Attribute("index")?.Value, 0f)))
                {
                    List<Vector3> shape = ParseShape(lane.Attribute("shape")?.Value, origin);
                    if (shape.Count < 2)
                    {
                        continue;
                    }

                    shapes.Add(shape);
                    widths.Add(ParseFloat(lane.Attribute("width")?.Value, defaultLaneWidth));
                }

                if (shapes.Count > 0)
                {
                    edges.Add(new EdgeLaneGeometry(edge, shapes, widths));
                }
            }

            return edges;
        }

        private void CreateRoadSidewalks(XDocument network, Vector2 origin, Material material, Transform parent)
        {
            List<EdgeLaneGeometry> edges = ReadExternalEdgeGeometry(network, origin);
            int sidewalkCount = 0;
            foreach (EdgeLaneGeometry edge in edges)
            {
                EdgeLaneGeometry opposing = edges.FirstOrDefault(candidate => candidate != edge && AreOpposingEdges(edge.edge, candidate.edge));
                if (opposing == null)
                {
                    CreateOuterSidewalk(edge, 0, edge.laneShapes.Count > 1 ? edge.laneShapes[1] : null, material, parent, ref sidewalkCount);
                    if (edge.laneShapes.Count > 1)
                    {
                        int lastLane = edge.laneShapes.Count - 1;
                        CreateOuterSidewalk(edge, lastLane, edge.laneShapes[lastLane - 1], material, parent, ref sidewalkCount);
                    }

                    continue;
                }

                int outerLane = FindFarthestLaneFromOpposing(edge, opposing);
                List<Vector3> reference = FindClosestReferenceLane(edge, outerLane, opposing);
                CreateOuterSidewalk(edge, outerLane, reference, material, parent, ref sidewalkCount);
            }
        }

        private void CreateOuterSidewalk(
            EdgeLaneGeometry edge,
            int laneIndex,
            IReadOnlyList<Vector3> insideReference,
            Material material,
            Transform parent,
            ref int sidewalkCount)
        {
            IReadOnlyList<Vector3> lane = edge.laneShapes[laneIndex];
            if (insideReference == null)
            {
                CreateSidewalkObject(edge, laneIndex, lane, -1, material, parent, ref sidewalkCount);
                CreateSidewalkObject(edge, laneIndex, lane, 1, material, parent, ref sidewalkCount);
                return;
            }

            int outwardSide = GetOutwardSide(lane, insideReference);
            CreateSidewalkObject(edge, laneIndex, lane, outwardSide, material, parent, ref sidewalkCount);
        }

        private void CreateSidewalkObject(EdgeLaneGeometry edge, int laneIndex, IReadOnlyList<Vector3> lane, int side, Material material, Transform parent, ref int sidewalkCount)
        {
            Mesh sidewalk = CreateSidewalkRibbon(lane, edge.laneWidths[laneIndex], sidewalkWidth, side);
            if (sidewalk != null)
            {
                CreateMeshObject($"Sidewalk_{sidewalkCount++}_{edge.edge.Attribute("id")?.Value}_{laneIndex}", sidewalk, material, parent);
            }
        }

        private static int FindFarthestLaneFromOpposing(EdgeLaneGeometry edge, EdgeLaneGeometry opposing)
        {
            int outerLane = 0;
            float farthestDistance = float.MinValue;
            for (int laneIndex = 0; laneIndex < edge.laneShapes.Count; laneIndex++)
            {
                float nearestDistance = float.MaxValue;
                foreach (List<Vector3> opposingLane in opposing.laneShapes)
                {
                    nearestDistance = Mathf.Min(nearestDistance, MidpointDistance(edge.laneShapes[laneIndex], opposingLane));
                }

                if (nearestDistance > farthestDistance)
                {
                    farthestDistance = nearestDistance;
                    outerLane = laneIndex;
                }
            }

            return outerLane;
        }

        private static List<Vector3> FindClosestReferenceLane(EdgeLaneGeometry edge, int laneIndex, EdgeLaneGeometry opposing)
        {
            List<Vector3> closest = null;
            float shortestDistance = float.MaxValue;
            for (int index = 0; index < edge.laneShapes.Count; index++)
            {
                if (index == laneIndex)
                {
                    continue;
                }

                float distance = MidpointDistance(edge.laneShapes[laneIndex], edge.laneShapes[index]);
                if (distance < shortestDistance)
                {
                    shortestDistance = distance;
                    closest = edge.laneShapes[index];
                }
            }

            if (closest != null)
            {
                return closest;
            }

            foreach (List<Vector3> opposingLane in opposing.laneShapes)
            {
                float distance = MidpointDistance(edge.laneShapes[laneIndex], opposingLane);
                if (distance < shortestDistance)
                {
                    shortestDistance = distance;
                    closest = opposingLane;
                }
            }

            return closest;
        }

        private static int GetOutwardSide(IReadOnlyList<Vector3> lane, IReadOnlyList<Vector3> insideReference)
        {
            Vector3 start = lane[0];
            Vector3 end = lane[lane.Count - 1];
            Vector3 direction = end - start;
            if (direction.sqrMagnitude <= Mathf.Epsilon)
            {
                return 1;
            }

            Vector3 left = new Vector3(-direction.z, 0f, direction.x).normalized;
            Vector3 laneMidpoint = (start + end) * 0.5f;
            Vector3 referenceMidpoint = (insideReference[0] + insideReference[insideReference.Count - 1]) * 0.5f;
            return Vector3.Dot(referenceMidpoint - laneMidpoint, left) >= 0f ? -1 : 1;
        }

        private static float MidpointDistance(IReadOnlyList<Vector3> first, IReadOnlyList<Vector3> second)
        {
            Vector3 firstMidpoint = (first[0] + first[first.Count - 1]) * 0.5f;
            Vector3 secondMidpoint = (second[0] + second[second.Count - 1]) * 0.5f;
            return Vector3.Distance(firstMidpoint, secondMidpoint);
        }

        private void CreateOpposingDirectionCenterLines(IReadOnlyList<EdgeLaneGeometry> edges, Material material, Transform parent)
        {
            int centerLineCount = 0;
            for (int firstIndex = 0; firstIndex < edges.Count; firstIndex++)
            {
                for (int secondIndex = firstIndex + 1; secondIndex < edges.Count; secondIndex++)
                {
                    EdgeLaneGeometry first = edges[firstIndex];
                    EdgeLaneGeometry second = edges[secondIndex];
                    if (!AreOpposingEdges(first.edge, second.edge) || !TryCreateOpposingBoundary(first, second, out List<Vector3> boundary))
                    {
                        continue;
                    }

                    Mesh centerLines = CreateDoubleSolidLine(boundary, laneMarkingWidth, laneMarkingWidth * 2.5f);
                    if (centerLines != null)
                    {
                        CreateMeshObject($"OpposingCenterLine_{centerLineCount++}_{first.edge.Attribute("id")?.Value}_{second.edge.Attribute("id")?.Value}", centerLines, material, parent);
                    }
                }
            }
        }

        private static bool AreOpposingEdges(XElement first, XElement second)
        {
            string firstFrom = first.Attribute("from")?.Value;
            string firstTo = first.Attribute("to")?.Value;
            return !string.IsNullOrEmpty(firstFrom)
                   && !string.IsNullOrEmpty(firstTo)
                   && string.Equals(firstFrom, second.Attribute("to")?.Value, StringComparison.Ordinal)
                   && string.Equals(firstTo, second.Attribute("from")?.Value, StringComparison.Ordinal);
        }

        private static bool TryCreateOpposingBoundary(EdgeLaneGeometry first, EdgeLaneGeometry second, out List<Vector3> boundary)
        {
            boundary = null;
            float shortestDistance = float.MaxValue;
            foreach (List<Vector3> firstLane in first.laneShapes)
            {
                foreach (List<Vector3> secondLane in second.laneShapes)
                {
                    List<Vector3> reversedSecondLane = secondLane.AsEnumerable().Reverse().ToList();
                    List<Vector3> candidate = CreateMidpointShape(firstLane, reversedSecondLane);
                    if (candidate == null)
                    {
                        continue;
                    }

                    float distance = AverageDistance(firstLane, reversedSecondLane);
                    if (distance < shortestDistance)
                    {
                        shortestDistance = distance;
                        boundary = candidate;
                    }
                }
            }

            return boundary != null;
        }

        private static float AverageDistance(IReadOnlyList<Vector3> first, IReadOnlyList<Vector3> second)
        {
            float total = 0f;
            for (int index = 0; index < first.Count; index++)
            {
                total += Vector3.Distance(first[index], second[index]);
            }

            return total / first.Count;
        }

        private void CreateTrafficLightStopLines(XDocument network, Vector2 origin, Material material, Transform parent)
        {
            // A connection with a traffic-light identifier is a movement that
            // reaches a signal. Its source lane is therefore an incoming lane;
            // outgoing lanes never enter this set.
            HashSet<string> controlledLaneIds = new HashSet<string>(
                network.Descendants("connection")
                    .Where(connection => !string.IsNullOrEmpty(connection.Attribute("tl")?.Value))
                    .Select(connection => $"{connection.Attribute("from")?.Value}_{connection.Attribute("fromLane")?.Value}"));

            int stopLineCount = 0;
            foreach (XElement edge in network.Descendants("edge"))
            {
                if (string.Equals(edge.Attribute("function")?.Value, "internal", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                foreach (XElement lane in edge.Elements("lane"))
                {
                    string laneId = lane.Attribute("id")?.Value;
                    if (string.IsNullOrEmpty(laneId) || !controlledLaneIds.Contains(laneId))
                    {
                        continue;
                    }

                    List<Vector3> points = ParseShape(lane.Attribute("shape")?.Value, origin);
                    float laneWidth = ParseFloat(lane.Attribute("width")?.Value, defaultLaneWidth);
                    Mesh stopLine = CreateStopLine(points, laneWidth, stopLineWidth, stopLineOffset, stopLineOverlap);
                    if (stopLine != null)
                    {
                        CreateMeshObject($"StopLine_{stopLineCount++}_{laneId}", stopLine, material, parent);
                    }
                }
            }
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

        private static List<Vector3> CreateMidpointShape(IReadOnlyList<Vector3> firstLane, IReadOnlyList<Vector3> secondLane)
        {
            // SUMO supplies each lane's centreline. The dividing stripe belongs
            // halfway between adjacent centrelines, not in the centre of either
            // driveable lane. Matching vertex counts is the safe case for the
            // current importer; curved lanes with different tessellation simply
            // retain their asphalt without a potentially misplaced stripe.
            if (firstLane.Count != secondLane.Count || firstLane.Count < 2)
            {
                return null;
            }

            List<Vector3> result = new List<Vector3>(firstLane.Count);
            for (int index = 0; index < firstLane.Count; index++)
            {
                result.Add((firstLane[index] + secondLane[index]) * 0.5f);
            }

            return result;
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

        private static Mesh CreateDoubleSolidLine(IReadOnlyList<Vector3> points, float width, float separation)
        {
            if (points.Count < 2)
            {
                return null;
            }

            List<Vector3> vertices = new List<Vector3>();
            List<int> triangles = new List<int>();
            for (int segment = 0; segment < points.Count - 1; segment++)
            {
                Vector3 from = points[segment];
                Vector3 to = points[segment + 1];
                Vector3 delta = to - from;
                if (delta.sqrMagnitude <= Mathf.Epsilon)
                {
                    continue;
                }

                Vector3 direction = delta.normalized;
                Vector3 side = new Vector3(-direction.z, 0f, direction.x);
                Vector3 halfLine = side * (width * 0.5f);
                Vector3 lineOffset = side * (separation * 0.5f);
                Vector3 lift = Vector3.up * 0.02f;

                AddLineQuad(vertices, triangles, from + lineOffset + halfLine + lift, from + lineOffset - halfLine + lift, to + lineOffset + halfLine + lift, to + lineOffset - halfLine + lift);
                AddLineQuad(vertices, triangles, from - lineOffset + halfLine + lift, from - lineOffset - halfLine + lift, to - lineOffset + halfLine + lift, to - lineOffset - halfLine + lift);
            }

            if (vertices.Count == 0)
            {
                return null;
            }

            Mesh mesh = new Mesh
            {
                name = "SumoDoubleSolidCenterLineMesh",
                vertices = vertices.ToArray(),
                triangles = triangles.ToArray()
            };
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }

        private static Mesh CreateSidewalkRibbon(IReadOnlyList<Vector3> lane, float laneWidth, float width, int side)
        {
            if (lane.Count < 2 || laneWidth <= Mathf.Epsilon || width <= Mathf.Epsilon)
            {
                return null;
            }

            List<Vector3> vertices = new List<Vector3>();
            List<int> triangles = new List<int>();
            for (int segment = 0; segment < lane.Count - 1; segment++)
            {
                Vector3 from = lane[segment];
                Vector3 to = lane[segment + 1];
                Vector3 delta = to - from;
                if (delta.sqrMagnitude <= Mathf.Epsilon)
                {
                    continue;
                }

                Vector3 outward = new Vector3(-delta.z, 0f, delta.x).normalized * side;
                Vector3 lift = Vector3.up * -0.01f;
                Vector3 fromInner = from + outward * (laneWidth * 0.5f) + lift;
                Vector3 fromOuter = fromInner + outward * width;
                Vector3 toInner = to + outward * (laneWidth * 0.5f) + lift;
                Vector3 toOuter = toInner + outward * width;
                AddGroundQuad(vertices, triangles, fromInner, fromOuter, toInner, toOuter);
            }

            if (vertices.Count == 0)
            {
                return null;
            }

            Mesh mesh = new Mesh
            {
                name = "SumoSidewalkMesh",
                vertices = vertices.ToArray(),
                triangles = triangles.ToArray()
            };
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }

        private static Mesh CreateStopLine(IReadOnlyList<Vector3> points, float laneWidth, float lineWidth, float offset, float overlap)
        {
            if (points.Count < 2 || laneWidth <= Mathf.Epsilon)
            {
                return null;
            }

            Vector3 laneEnd = points[points.Count - 1];
            Vector3 previousPoint = points[points.Count - 2];
            Vector3 finalSegment = laneEnd - previousPoint;
            float finalSegmentLength = finalSegment.magnitude;
            if (finalSegmentLength <= Mathf.Epsilon)
            {
                return null;
            }

            Vector3 direction = finalSegment / finalSegmentLength;
            Vector3 position = laneEnd - direction * Mathf.Min(offset, finalSegmentLength * 0.5f);
            // Adjacent lane centres are separated by their lane width. A small
            // overlap removes visual seams so multiple per-lane bars read as
            // one continuous stop line across the entire approach.
            Vector3 acrossLane = new Vector3(-direction.z, 0f, direction.x) * Mathf.Max(0.1f, laneWidth + overlap) * 0.5f;
            Vector3 alongLane = direction * lineWidth * 0.5f;
            Vector3 lift = Vector3.up * 0.025f;

            List<Vector3> vertices = new List<Vector3>
            {
                position - acrossLane - alongLane + lift,
                position + acrossLane - alongLane + lift,
                position - acrossLane + alongLane + lift,
                position + acrossLane + alongLane + lift
            };
            // The four vertices are laid out on Unity's XZ ground plane. Use
            // upward-facing winding so the white stop bar is not back-face
            // culled when seen from the traffic cameras or from above.
            List<int> triangles = new List<int> { 0, 1, 2, 2, 1, 3 };
            Mesh mesh = new Mesh
            {
                name = "SumoTrafficLightStopLineMesh",
                vertices = vertices.ToArray(),
                triangles = triangles.ToArray()
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

        private static void AddGroundQuad(List<Vector3> vertices, List<int> triangles, Vector3 fromInner, Vector3 fromOuter, Vector3 toInner, Vector3 toOuter)
        {
            int index = vertices.Count;
            vertices.Add(fromInner);
            vertices.Add(fromOuter);
            vertices.Add(toInner);
            vertices.Add(toOuter);
            bool isUpward = Vector3.Cross(fromOuter - fromInner, toInner - fromInner).y >= 0f;
            if (isUpward)
            {
                triangles.Add(index);
                triangles.Add(index + 1);
                triangles.Add(index + 2);
                triangles.Add(index + 2);
                triangles.Add(index + 1);
                triangles.Add(index + 3);
            }
            else
            {
                triangles.Add(index);
                triangles.Add(index + 2);
                triangles.Add(index + 1);
                triangles.Add(index + 2);
                triangles.Add(index + 3);
                triangles.Add(index + 1);
            }
        }

        private static List<int> Triangulate(IReadOnlyList<Vector2> points)
        {
            List<int> result = new List<int>();
            List<int> indices = Enumerable.Range(0, points.Count).ToList();
            // Ear clipping below expects a counter-clockwise contour in the
            // XZ projection.
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

            // The XZ projection is viewed from above, whereas Unity's upward
            // face normal needs the reverse triangle winding. Flip completed
            // triangles instead of changing the contour consumed by IsEar.
            for (int index = 0; index < result.Count; index += 3)
            {
                (result[index + 1], result[index + 2]) = (result[index + 2], result[index + 1]);
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

        private static Material CreateCenterLineFallbackMaterial()
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
            return new Material(shader) { color = new Color(0.95f, 0.72f, 0.08f) };
        }

        private static Material CreateSidewalkFallbackMaterial()
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
            return new Material(shader) { color = new Color(0.48f, 0.48f, 0.46f) };
        }

        private sealed class EdgeLaneGeometry
        {
            public readonly XElement edge;
            public readonly List<List<Vector3>> laneShapes;
            public readonly List<float> laneWidths;

            public EdgeLaneGeometry(XElement edge, List<List<Vector3>> laneShapes, List<float> laneWidths)
            {
                this.edge = edge;
                this.laneShapes = laneShapes;
                this.laneWidths = laneWidths;
            }
        }
    }
}
