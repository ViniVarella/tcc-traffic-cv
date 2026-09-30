using System.Collections.Generic;
using System.IO;
using TccTrafficVision.CameraCalibration;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace TccTrafficVision.Editor.CameraCalibration
{
    /// <summary>
    /// Loads Assets/Calibration/&lt;cameraId&gt;-calibration.json back into the
    /// scene's TrafficCameraCalibration components. Used after the ROIs are
    /// regenerated outside Unity (python -m experiments.extend_lane_rois), so a
    /// later "Export calibration JSON" does not revert them.
    /// </summary>
    public static class SpCalibrationImporter
    {
        private const string CalibrationFolder = "Assets/Calibration";
        private const float PositionTolerance = 0.01f;
        private const float AngleTolerance = 0.1f;

        [MenuItem("Traffic Vision/Cameras/Import SP Calibration JSON")]
        public static void ImportAll()
        {
            TrafficCameraCalibration[] calibrations =
                Object.FindObjectsByType<TrafficCameraCalibration>(FindObjectsSortMode.None);
            var imported = new List<string>();
            var errors = new List<string>();
            foreach (TrafficCameraCalibration calibration in calibrations)
            {
                string path = Path.Combine(CalibrationFolder, $"{calibration.CameraId}-calibration.json");
                if (!File.Exists(path))
                {
                    // Dataset cameras have no operational calibration JSON.
                    continue;
                }

                CameraCalibrationExport data = JsonUtility.FromJson<CameraCalibrationExport>(File.ReadAllText(path));
                if (TryImport(calibration, data, out string error))
                {
                    imported.Add(calibration.CameraId);
                    WarnIfPoseDiffers(calibration, data);
                }
                else
                {
                    errors.Add($"{calibration.CameraId}: {error}");
                }
            }

            if (imported.Count > 0)
            {
                EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
            }

            string summary = $"Calibração importada para: {(imported.Count == 0 ? "nenhuma câmera" : string.Join(", ", imported))}.";
            if (errors.Count > 0)
            {
                Debug.LogError(summary + " Falhas:\n" + string.Join("\n", errors));
                EditorUtility.DisplayDialog("Import SP Calibration JSON", summary + "\n\nFalhas:\n" + string.Join("\n", errors), "OK");
                return;
            }

            Debug.Log(summary + " Salve a cena (Cmd+S).");
        }

        private static bool TryImport(TrafficCameraCalibration calibration, CameraCalibrationExport data, out string error)
        {
            if (data == null || data.approachRoi == null || data.laneRois == null)
            {
                error = "JSON de calibração inválido.";
                return false;
            }

            if (data.cameraId != calibration.CameraId)
            {
                error = $"o JSON pertence à câmera '{data.cameraId}'.";
                return false;
            }

            // Validate on a temporary copy first, so a rejected lane never
            // leaves the scene component half imported.
            var temporary = new GameObject("SP Calibration Import") { hideFlags = HideFlags.HideAndDontSave };
            try
            {
                TrafficCameraCalibration candidate = temporary.AddComponent<TrafficCameraCalibration>();
                EditorUtility.CopySerialized(calibration, candidate);
                if (!candidate.SetApproachRoi(data.approachRoi.points, out error))
                {
                    error = $"approach: {error}";
                    return false;
                }

                foreach (RoiExport lane in data.laneRois)
                {
                    if (!candidate.TryAddLaneRoi(lane.id, lane.points, out error))
                    {
                        error = $"{lane.id}: {error}";
                        return false;
                    }
                }

                Undo.RecordObject(calibration, "Import SP calibration JSON");
                EditorUtility.CopySerialized(candidate, calibration);
                error = null;
                return true;
            }
            finally
            {
                Object.DestroyImmediate(temporary);
            }
        }

        private static void WarnIfPoseDiffers(TrafficCameraCalibration calibration, CameraCalibrationExport data)
        {
            Camera camera = calibration.CameraComponent;
            if (camera == null || data.pose == null)
            {
                return;
            }

            bool positionDiffers = Vector3.Distance(camera.transform.position, data.pose.position) > PositionTolerance;
            bool rotationDiffers = Quaternion.Angle(camera.transform.rotation, Quaternion.Euler(data.pose.rotationEulerDegrees)) > AngleTolerance;
            bool fovDiffers = Mathf.Abs(camera.fieldOfView - data.pose.fieldOfView) > AngleTolerance;
            if (positionDiffers || rotationDiffers || fovDiffers)
            {
                Debug.LogWarning(
                    $"A pose da câmera {calibration.CameraId} na cena difere da pose do JSON; as ROIs foram calculadas " +
                    "para a pose do JSON. Reposicione a câmera ou regenere as ROIs.",
                    calibration);
            }
        }
    }
}
