using System;
using System.Collections.Generic;
using UnityEngine;

namespace TccTrafficVision.CameraCalibration
{
    /// <summary>
    /// Persistent calibration data for one Unity camera. ROI coordinates use the
    /// image convention: (0,0) is top-left and (1,1) is bottom-right.
    /// Attach one instance to each traffic camera in the scene.
    /// </summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Camera))]
    public sealed class TrafficCameraCalibration : MonoBehaviour
    {
        [SerializeField] private string cameraId = "north";
        [SerializeField] private bool captureEnabled = true;
        [SerializeField, Min(1)] private int captureWidth = 1280;
        [SerializeField, Min(1)] private int captureHeight = 720;
        [SerializeField] private RoiPolygon approachRoi = new RoiPolygon("approach", null);
        [SerializeField] private List<RoiPolygon> laneRois = new List<RoiPolygon>();

        public string CameraId => cameraId;
        /// <summary>Whether this camera participates in the TCP frame stream.</summary>
        public bool CaptureEnabled => captureEnabled;
        public int CaptureWidth => captureWidth;
        public int CaptureHeight => captureHeight;
        public RoiPolygon ApproachRoi => approachRoi;
        public IReadOnlyList<RoiPolygon> LaneRois => laneRois;
        public Camera CameraComponent => GetComponent<Camera>();

        private void OnValidate()
        {
            captureWidth = Mathf.Max(1, captureWidth);
            captureHeight = Mathf.Max(1, captureHeight);
        }

        /// <summary>
        /// Replacing the outer ROI invalidates all lane ROIs, because each one
        /// must be contained by the new outer polygon.
        /// </summary>
        public bool SetApproachRoi(IReadOnlyList<Vector2> points, out string error)
        {
            if (!RoiGeometry.TryValidateQuadrilateral(points, out error))
            {
                return false;
            }

            approachRoi = new RoiPolygon("approach", points);
            laneRois.Clear();
            return true;
        }

        public void SetApproachRoi(IReadOnlyList<Vector2> points)
        {
            if (!SetApproachRoi(points, out string error))
            {
                throw new ArgumentException(error, nameof(points));
            }
        }

        /// <summary>
        /// Adds a lane ROI. Lane IDs are unique inside one camera calibration.
        /// </summary>
        public bool TryAddLaneRoi(string laneId, IReadOnlyList<Vector2> points, out string error)
        {
            string normalizedId = NormalizeLaneId(laneId);
            if (normalizedId == null)
            {
                error = "Informe um identificador para a faixa.";
                return false;
            }

            if (FindLaneIndex(normalizedId) >= 0)
            {
                error = $"Já existe uma ROI com o identificador '{normalizedId}'.";
                return false;
            }

            if (!TryValidateLaneRoi(points, null, out error))
            {
                return false;
            }

            laneRois.Add(new RoiPolygon(normalizedId, points));
            return true;
        }

        /// <summary>
        /// Replaces an existing lane ROI without allowing it to collide with the
        /// other lanes. This is used by the calibration editor's Edit action.
        /// </summary>
        public bool TrySetLaneRoi(string laneId, IReadOnlyList<Vector2> points, out string error)
        {
            string normalizedId = NormalizeLaneId(laneId);
            if (normalizedId == null)
            {
                error = "Informe um identificador para a faixa.";
                return false;
            }

            int index = FindLaneIndex(normalizedId);
            if (index < 0)
            {
                error = $"Não existe uma ROI com o identificador '{normalizedId}'.";
                return false;
            }

            if (!TryValidateLaneRoi(points, normalizedId, out error))
            {
                return false;
            }

            // Older scene data may have been authored before lane IDs were
            // unique. Replacing a lane also cleans any legacy duplicates.
            laneRois.RemoveAll(lane => string.Equals(lane.Id, normalizedId, StringComparison.Ordinal));
            laneRois.Add(new RoiPolygon(normalizedId, points));
            return true;
        }

        /// <summary>
        /// Validates one click while a lane ROI is being drawn. An invalid point
        /// is rejected before it becomes part of the pending polygon.
        /// </summary>
        public bool TryValidateLanePoint(
            IReadOnlyList<Vector2> pendingPoints,
            Vector2 candidate,
            string ignoredLaneId,
            out string error)
        {
            if (!approachRoi.IsDefined)
            {
                error = "Crie primeiro a ROI principal da aproximação.";
                return false;
            }

            if (!RoiGeometry.IsPointStrictlyInside(approachRoi.Points, candidate))
            {
                error = "O ponto da faixa está fora da ROI principal.";
                return false;
            }

            if (pendingPoints != null && pendingPoints.Count > 0 &&
                RoiGeometry.SegmentIntersectsPolygon(pendingPoints[pendingPoints.Count - 1], candidate, approachRoi.Points))
            {
                error = "O lado da ROI da faixa sai da ROI principal.";
                return false;
            }

            if (pendingPoints != null && pendingPoints.Count == 3 &&
                RoiGeometry.SegmentIntersectsPolygon(candidate, pendingPoints[0], approachRoi.Points))
            {
                error = "O fechamento da ROI da faixa sai da ROI principal.";
                return false;
            }

            foreach (RoiPolygon lane in laneRois)
            {
                if (string.Equals(lane.Id, ignoredLaneId, StringComparison.Ordinal))
                {
                    continue;
                }

                if (RoiGeometry.IsPointStrictlyInside(lane.Points, candidate))
                {
                    error = $"O ponto está dentro da ROI da faixa '{lane.Id}'.";
                    return false;
                }

                if (pendingPoints != null && pendingPoints.Count > 0 &&
                    RoiGeometry.SegmentIntersectsPolygon(pendingPoints[pendingPoints.Count - 1], candidate, lane.Points))
                {
                    error = $"O lado da ROI da faixa cruza a ROI da faixa '{lane.Id}'.";
                    return false;
                }

                if (pendingPoints != null && pendingPoints.Count == 3 &&
                    RoiGeometry.SegmentIntersectsPolygon(candidate, pendingPoints[0], lane.Points))
                {
                    error = $"O fechamento da ROI da faixa cruza a ROI da faixa '{lane.Id}'.";
                    return false;
                }
            }

            if (pendingPoints == null || pendingPoints.Count < 3)
            {
                error = null;
                return true;
            }

            List<Vector2> completedPoints = new List<Vector2>(pendingPoints) { candidate };
            if (!RoiGeometry.TryValidateQuadrilateral(completedPoints, out error))
            {
                return false;
            }

            if (!RoiGeometry.IsPolygonInside(completedPoints, approachRoi.Points))
            {
                error = "A ROI da faixa deve estar inteiramente dentro da ROI principal.";
                return false;
            }

            foreach (RoiPolygon lane in laneRois)
            {
                if (!string.Equals(lane.Id, ignoredLaneId, StringComparison.Ordinal) &&
                    RoiGeometry.PolygonsOverlap(completedPoints, lane.Points))
                {
                    error = $"A ROI da faixa se sobrepõe à faixa '{lane.Id}'.";
                    return false;
                }
            }

            error = null;
            return true;
        }

        public bool RemoveLaneRoi(string laneId)
        {
            string normalizedId = NormalizeLaneId(laneId);
            if (normalizedId == null)
            {
                return false;
            }

            return laneRois.RemoveAll(lane => string.Equals(lane.Id, normalizedId, StringComparison.Ordinal)) > 0;
        }

        /// <summary>
        /// Builds the stable JSON contract consumed by the Python perception
        /// process. Coordinates stay normalized, so the same calibration can be
        /// rendered at a different image size without changing the ROIs.
        /// </summary>
        public bool TryExportJson(out string json, out string error)
        {
            if (!TryCreateExportData(out CameraCalibrationExport exportData, out error))
            {
                json = null;
                return false;
            }

            json = JsonUtility.ToJson(exportData, true);
            return true;
        }

        public bool TryCreateExportData(out CameraCalibrationExport exportData, out string error)
        {
            if (string.IsNullOrWhiteSpace(cameraId))
            {
                exportData = null;
                error = "Informe o identificador da câmera antes de exportar.";
                return false;
            }

            if (!approachRoi.IsDefined)
            {
                exportData = null;
                error = "Defina a ROI externa da aproximação antes de exportar.";
                return false;
            }

            if (laneRois.Count == 0)
            {
                exportData = null;
                error = "Defina pelo menos uma ROI de faixa antes de exportar.";
                return false;
            }

            HashSet<string> laneIds = new HashSet<string>(StringComparer.Ordinal);
            foreach (RoiPolygon lane in laneRois)
            {
                if (NormalizeLaneId(lane.Id) == null || !laneIds.Add(lane.Id))
                {
                    exportData = null;
                    error = "Cada ROI de faixa precisa ter um identificador único antes de exportar.";
                    return false;
                }
            }

            Camera camera = CameraComponent;
            if (camera == null)
            {
                exportData = null;
                error = "A calibração precisa estar associada a uma Camera do Unity.";
                return false;
            }

            RoiExport[] exportedLanes = new RoiExport[laneRois.Count];
            for (int i = 0; i < laneRois.Count; i++)
            {
                exportedLanes[i] = RoiExport.From(laneRois[i]);
            }

            exportData = new CameraCalibrationExport
            {
                schemaVersion = 1,
                cameraId = cameraId.Trim(),
                capture = new CaptureResolution { width = captureWidth, height = captureHeight },
                pose = CameraPose.From(camera),
                approachRoi = RoiExport.From(approachRoi),
                laneRois = exportedLanes
            };
            error = null;
            return true;
        }

        private bool TryValidateLaneRoi(IReadOnlyList<Vector2> points, string ignoredLaneId, out string error)
        {
            if (!RoiGeometry.TryValidateQuadrilateral(points, out error))
            {
                return false;
            }

            if (!approachRoi.IsDefined)
            {
                error = "Crie primeiro a ROI externa da aproximação.";
                return false;
            }

            if (!RoiGeometry.IsPolygonInside(points, approachRoi.Points))
            {
                error = "A ROI da faixa deve estar inteiramente dentro da ROI externa.";
                return false;
            }

            foreach (RoiPolygon lane in laneRois)
            {
                if (string.Equals(lane.Id, ignoredLaneId, StringComparison.Ordinal))
                {
                    continue;
                }

                if (RoiGeometry.PolygonsOverlap(points, lane.Points))
                {
                    error = $"A ROI da faixa se sobrepõe à faixa '{lane.Id}'.";
                    return false;
                }
            }

            error = null;
            return true;
        }

        private int FindLaneIndex(string laneId)
        {
            for (int i = 0; i < laneRois.Count; i++)
            {
                if (string.Equals(laneRois[i].Id, laneId, StringComparison.Ordinal))
                {
                    return i;
                }
            }

            return -1;
        }

        private static string NormalizeLaneId(string laneId)
        {
            return string.IsNullOrWhiteSpace(laneId) ? null : laneId.Trim();
        }
    }

    [Serializable]
    public sealed class RoiPolygon
    {
        [SerializeField] private string id;
        [SerializeField] private List<Vector2> points = new List<Vector2>();

        public string Id => id;
        public IReadOnlyList<Vector2> Points => points;
        public bool IsDefined => points != null && points.Count == 4;

        public RoiPolygon(string id, IReadOnlyList<Vector2> sourcePoints)
        {
            this.id = id;
            points = sourcePoints == null ? new List<Vector2>() : new List<Vector2>(sourcePoints);
        }
    }

    [Serializable]
    public sealed class CameraCalibrationExport
    {
        public int schemaVersion;
        public string cameraId;
        public CaptureResolution capture;
        public CameraPose pose;
        public RoiExport approachRoi;
        public RoiExport[] laneRois;
    }

    [Serializable]
    public sealed class CaptureResolution
    {
        public int width;
        public int height;
    }

    [Serializable]
    public sealed class CameraPose
    {
        public Vector3 position;
        public Vector3 rotationEulerDegrees;
        public float fieldOfView;
        public bool orthographic;
        public float orthographicSize;
        public float nearClipPlane;
        public float farClipPlane;

        public static CameraPose From(Camera camera)
        {
            return new CameraPose
            {
                position = camera.transform.position,
                rotationEulerDegrees = camera.transform.eulerAngles,
                fieldOfView = camera.fieldOfView,
                orthographic = camera.orthographic,
                orthographicSize = camera.orthographicSize,
                nearClipPlane = camera.nearClipPlane,
                farClipPlane = camera.farClipPlane
            };
        }
    }

    [Serializable]
    public sealed class RoiExport
    {
        public string id;
        public Vector2[] points;

        public static RoiExport From(RoiPolygon roi)
        {
            Vector2[] copiedPoints = new Vector2[roi.Points.Count];
            for (int i = 0; i < roi.Points.Count; i++)
            {
                copiedPoints[i] = roi.Points[i];
            }

            return new RoiExport { id = roi.Id, points = copiedPoints };
        }
    }

    public static class RoiGeometry
    {
        private const float Epsilon = 0.00001f;

        public static bool TryValidateQuadrilateral(IReadOnlyList<Vector2> points, out string error)
        {
            if (points == null || points.Count != 4)
            {
                error = "Uma ROI deve ter exatamente quatro pontos.";
                return false;
            }

            foreach (Vector2 point in points)
            {
                if (point.x < 0f || point.x > 1f || point.y < 0f || point.y > 1f)
                {
                    error = "Todos os pontos devem ficar dentro da imagem.";
                    return false;
                }
            }

            for (int i = 0; i < points.Count; i++)
            {
                Vector2 current = points[i];
                Vector2 next = points[(i + 1) % points.Count];
                if ((current - next).sqrMagnitude < Epsilon * Epsilon)
                {
                    error = "Os quatro cantos da ROI devem ser distintos.";
                    return false;
                }
            }

            if (SegmentsIntersect(points[0], points[1], points[2], points[3]) ||
                SegmentsIntersect(points[1], points[2], points[3], points[0]))
            {
                error = "Os lados da ROI não podem se cruzar.";
                return false;
            }

            if (Mathf.Abs(SignedArea(points)) < Epsilon)
            {
                error = "A ROI não pode ter área nula.";
                return false;
            }

            error = null;
            return true;
        }

        public static bool IsPolygonInside(IReadOnlyList<Vector2> inner, IReadOnlyList<Vector2> outer)
        {
            if (inner == null || outer == null || inner.Count < 3 || outer.Count < 3)
            {
                return false;
            }

            foreach (Vector2 point in inner)
            {
                if (!ContainsPoint(outer, point))
                {
                    return false;
                }
            }

            return !AnyEdgesIntersect(inner, outer);
        }

        public static bool PolygonsOverlap(IReadOnlyList<Vector2> first, IReadOnlyList<Vector2> second)
        {
            if (first == null || second == null || first.Count < 3 || second.Count < 3)
            {
                return false;
            }

            if (AnyEdgesIntersect(first, second))
            {
                return true;
            }

            return ContainsPoint(first, second[0]) || ContainsPoint(second, first[0]);
        }

        public static bool IsPointStrictlyInside(IReadOnlyList<Vector2> polygon, Vector2 point)
        {
            return polygon != null && polygon.Count >= 3 && ContainsPoint(polygon, point);
        }

        public static bool SegmentIntersectsPolygon(Vector2 start, Vector2 end, IReadOnlyList<Vector2> polygon)
        {
            if (polygon == null || polygon.Count < 3)
            {
                return false;
            }

            for (int i = 0; i < polygon.Count; i++)
            {
                Vector2 edgeStart = polygon[i];
                Vector2 edgeEnd = polygon[(i + 1) % polygon.Count];
                if (SegmentsIntersect(start, end, edgeStart, edgeEnd))
                {
                    return true;
                }
            }

            return false;
        }

        private static bool AnyEdgesIntersect(IReadOnlyList<Vector2> first, IReadOnlyList<Vector2> second)
        {
            for (int i = 0; i < first.Count; i++)
            {
                Vector2 a = first[i];
                Vector2 b = first[(i + 1) % first.Count];
                for (int j = 0; j < second.Count; j++)
                {
                    Vector2 c = second[j];
                    Vector2 d = second[(j + 1) % second.Count];
                    if (SegmentsIntersect(a, b, c, d))
                    {
                        return true;
                    }
                }
            }

            return false;
        }

        private static bool ContainsPoint(IReadOnlyList<Vector2> polygon, Vector2 point)
        {
            bool inside = false;
            for (int i = 0, previous = polygon.Count - 1; i < polygon.Count; previous = i++)
            {
                Vector2 current = polygon[i];
                Vector2 prior = polygon[previous];

                if (IsPointOnSegment(prior, current, point))
                {
                    return false;
                }

                bool crosses = (current.y > point.y) != (prior.y > point.y) &&
                    point.x < (prior.x - current.x) * (point.y - current.y) /
                    (prior.y - current.y) + current.x;
                if (crosses)
                {
                    inside = !inside;
                }
            }

            return inside;
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

        private static bool SegmentsIntersect(Vector2 a, Vector2 b, Vector2 c, Vector2 d)
        {
            float abC = Cross(a, b, c);
            float abD = Cross(a, b, d);
            float cdA = Cross(c, d, a);
            float cdB = Cross(c, d, b);

            if (((abC > Epsilon && abD < -Epsilon) || (abC < -Epsilon && abD > Epsilon)) &&
                ((cdA > Epsilon && cdB < -Epsilon) || (cdA < -Epsilon && cdB > Epsilon)))
            {
                return true;
            }

            return (Mathf.Abs(abC) <= Epsilon && IsPointOnSegment(a, b, c)) ||
                   (Mathf.Abs(abD) <= Epsilon && IsPointOnSegment(a, b, d)) ||
                   (Mathf.Abs(cdA) <= Epsilon && IsPointOnSegment(c, d, a)) ||
                   (Mathf.Abs(cdB) <= Epsilon && IsPointOnSegment(c, d, b));
        }

        private static bool IsPointOnSegment(Vector2 a, Vector2 b, Vector2 point)
        {
            if (Mathf.Abs(Cross(a, b, point)) > Epsilon)
            {
                return false;
            }

            return point.x >= Mathf.Min(a.x, b.x) - Epsilon &&
                   point.x <= Mathf.Max(a.x, b.x) + Epsilon &&
                   point.y >= Mathf.Min(a.y, b.y) - Epsilon &&
                   point.y <= Mathf.Max(a.y, b.y) + Epsilon;
        }

        private static float Cross(Vector2 a, Vector2 b, Vector2 c)
        {
            return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
        }
    }
}
