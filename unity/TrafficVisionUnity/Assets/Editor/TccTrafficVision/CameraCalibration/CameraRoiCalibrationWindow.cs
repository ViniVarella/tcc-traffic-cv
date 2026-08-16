using System;
using System.Collections.Generic;
using System.IO;
using TccTrafficVision.CameraCalibration;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace TccTrafficVision.Editor.CameraCalibration
{
    /// <summary>
    /// Editor-only tool for calibrating one traffic camera from its rendered image.
    /// It intentionally renders with a hidden disabled copy of the selected camera,
    /// never by manually rendering the scene camera itself.
    /// </summary>
    public sealed class CameraRoiCalibrationWindow : EditorWindow
    {
        private enum EditMode { None, Approach, Lane }

        private TrafficCameraCalibration calibration;
        private RenderTexture previewTexture;
        private GameObject previewCameraObject;
        private Camera previewCamera;
        private readonly List<Vector2> pendingPoints = new List<Vector2>(4);
        private EditMode editMode;
        private string laneId = "lane_0";
        private string editingLaneId;
        private string feedback;

        [MenuItem("Traffic Vision/Camera ROI Calibration")]
        public static void Open()
        {
            GetWindow<CameraRoiCalibrationWindow>("Camera ROI Calibration");
        }

        private void OnDisable()
        {
            ReleasePreviewTexture();
            ReleasePreviewCamera();
        }

        private void OnGUI()
        {
            EditorGUILayout.HelpBox(
                "1. Selecione uma câmera. 2. Posicione-a manualmente ou alinhe-a à Scene View. " +
                "3. Renderize o preview. 4. Clique quatro pontos para a ROI externa e para cada faixa. " +
                "Use o botão direito para desfazer o último ponto ainda pendente.",
                MessageType.Info);

            calibration = (TrafficCameraCalibration)EditorGUILayout.ObjectField(
                "Camera calibration", calibration, typeof(TrafficCameraCalibration), true);

            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Use selected camera"))
                {
                    UseSelectedCamera();
                }

                using (new EditorGUI.DisabledScope(calibration == null))
                {
                    if (GUILayout.Button("Align with Scene View"))
                    {
                        AlignWithSceneView();
                    }

                    if (GUILayout.Button("Render preview"))
                    {
                        RenderPreview();
                    }

                    if (GUILayout.Button("Export calibration JSON"))
                    {
                        ExportCalibrationJson();
                    }
                }
            }

            if (calibration == null)
            {
                DrawFeedback();
                return;
            }

            DrawControls();
            Rect imageRect = DrawPreview();
            DrawPolygons(imageRect);
            HandleImageClick(imageRect);
            DrawFeedback();
        }

        private void DrawControls()
        {
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("ROI setup", EditorStyles.boldLabel);

            string approachButton = calibration.ApproachRoi.IsDefined
                ? "Redefine approach ROI (clears lanes)"
                : "Define approach ROI";
            using (new EditorGUI.DisabledScope(editMode != EditMode.None))
            {
                if (GUILayout.Button(approachButton))
                {
                    Begin(EditMode.Approach, null);
                }
            }

            using (new EditorGUILayout.HorizontalScope())
            {
                using (new EditorGUI.DisabledScope(editingLaneId != null))
                {
                    laneId = EditorGUILayout.TextField("Lane ID", laneId);
                }

                using (new EditorGUI.DisabledScope(editMode != EditMode.None))
                {
                    if (GUILayout.Button("New Lane"))
                    {
                        Begin(EditMode.Lane, null);
                    }
                }

                using (new EditorGUI.DisabledScope(editMode != EditMode.Lane || pendingPoints.Count != 4))
                {
                    if (GUILayout.Button("Save Lane"))
                    {
                        CommitPendingPoints();
                    }
                }

                using (new EditorGUI.DisabledScope(editMode == EditMode.None))
                {
                    if (GUILayout.Button("Cancel"))
                    {
                        CancelEdit();
                    }
                }
            }

            DrawLaneList();
            if (editMode != EditMode.None)
            {
                string target = editMode == EditMode.Approach
                    ? "ROI externa"
                    : $"faixa '{laneId}'";
                string action = editMode == EditMode.Lane && pendingPoints.Count == 4
                    ? "Prévia completa. Ajuste com o botão direito ou clique em Save Lane."
                    : "Botão direito remove o último ponto pendente.";
                EditorGUILayout.HelpBox(
                    $"Clique quatro pontos para {target}. ({pendingPoints.Count}/4) " +
                    action,
                    MessageType.Info);
            }
        }

        private void DrawLaneList()
        {
            EditorGUILayout.Space();
            EditorGUILayout.LabelField("Lane ROIs", EditorStyles.boldLabel);
            if (calibration.LaneRois.Count == 0)
            {
                EditorGUILayout.LabelField("Nenhuma faixa configurada.", EditorStyles.miniLabel);
                return;
            }

            for (int i = 0; i < calibration.LaneRois.Count; i++)
            {
                RoiPolygon lane = calibration.LaneRois[i];
                using (new EditorGUILayout.HorizontalScope())
                {
                    EditorGUILayout.LabelField(lane.Id, GUILayout.MinWidth(160f));
                    using (new EditorGUI.DisabledScope(editMode != EditMode.None))
                    {
                        if (GUILayout.Button("Edit", GUILayout.Width(58f)))
                        {
                            laneId = lane.Id;
                            Begin(EditMode.Lane, lane.Id);
                        }

                        if (GUILayout.Button("Delete", GUILayout.Width(58f)))
                        {
                            Undo.RecordObject(calibration, "Delete traffic lane ROI");
                            calibration.RemoveLaneRoi(lane.Id);
                            SaveCalibration("ROI da faixa removida.");
                            return;
                        }
                    }
                }
            }
        }

        private Rect DrawPreview()
        {
            const float padding = 20f;
            float width = Mathf.Max(240f, position.width - padding * 2f);
            float aspect = calibration == null ? 16f / 9f : (float)calibration.CaptureWidth / calibration.CaptureHeight;
            Rect rect = GUILayoutUtility.GetRect(width, width / aspect, GUILayout.ExpandWidth(true));
            rect.x = (position.width - rect.width) * 0.5f;

            if (previewTexture == null)
            {
                EditorGUI.DrawRect(rect, new Color(0.08f, 0.08f, 0.08f));
                GUI.Label(rect, "Click Render preview", EditorStyles.centeredGreyMiniLabel);
            }
            else
            {
                GUI.DrawTexture(rect, previewTexture, ScaleMode.StretchToFill, false);
            }

            return rect;
        }

        private void DrawPolygons(Rect imageRect)
        {
            if (calibration == null || imageRect.width <= 0f || imageRect.height <= 0f)
            {
                return;
            }

            Handles.BeginGUI();
            DrawPolygon(calibration.ApproachRoi.Points, imageRect, Color.green, "approach");
            foreach (RoiPolygon lane in calibration.LaneRois)
            {
                DrawPolygon(lane.Points, imageRect, Color.cyan, lane.Id);
            }

            if (pendingPoints.Count > 0)
            {
                DrawPolygon(pendingPoints, imageRect, Color.yellow, editMode.ToString());
            }
            Handles.EndGUI();
        }

        private static void DrawPolygon(IReadOnlyList<Vector2> points, Rect imageRect, Color color, string label)
        {
            if (points == null || points.Count == 0)
            {
                return;
            }

            Vector3[] screenPoints = new Vector3[points.Count];
            for (int i = 0; i < points.Count; i++)
            {
                screenPoints[i] = ToScreenPoint(points[i], imageRect);
            }

            Handles.color = color;
            if (screenPoints.Length > 1)
            {
                Handles.DrawPolyLine(screenPoints);
                if (screenPoints.Length == 4)
                {
                    Handles.DrawLine(screenPoints[3], screenPoints[0]);
                }
            }

            for (int i = 0; i < screenPoints.Length; i++)
            {
                Handles.DrawSolidDisc(screenPoints[i], Vector3.forward, 4f);
            }

            GUI.Label(new Rect(screenPoints[0].x + 4f, screenPoints[0].y + 4f, 140f, 18f), label);
        }

        private static Vector3 ToScreenPoint(Vector2 normalizedPoint, Rect imageRect)
        {
            return new Vector3(
                Mathf.Lerp(imageRect.xMin, imageRect.xMax, normalizedPoint.x),
                Mathf.Lerp(imageRect.yMin, imageRect.yMax, normalizedPoint.y),
                0f);
        }

        private void HandleImageClick(Rect imageRect)
        {
            Event current = Event.current;
            if (editMode == EditMode.None || current.type != EventType.MouseDown ||
                !imageRect.Contains(current.mousePosition))
            {
                return;
            }

            if (current.button == 1)
            {
                current.Use();
                if (pendingPoints.Count == 0)
                {
                    feedback = "Não há ponto pendente para remover.";
                }
                else
                {
                    pendingPoints.RemoveAt(pendingPoints.Count - 1);
                    feedback = "Último ponto pendente removido.";
                }

                Repaint();
                return;
            }

            if (current.button != 0)
            {
                return;
            }

            if (editMode == EditMode.Lane && pendingPoints.Count == 4)
            {
                current.Use();
                feedback = "A faixa já possui quatro pontos. Clique em Save Lane ou use o botão direito para ajustar.";
                Repaint();
                return;
            }

            Vector2 candidate = new Vector2(
                Mathf.InverseLerp(imageRect.xMin, imageRect.xMax, current.mousePosition.x),
                Mathf.InverseLerp(imageRect.yMin, imageRect.yMax, current.mousePosition.y));
            current.Use();

            if (editMode == EditMode.Lane &&
                !calibration.TryValidateLanePoint(pendingPoints, candidate, editingLaneId, out string error))
            {
                feedback = error;
                Repaint();
                return;
            }

            pendingPoints.Add(candidate);

            if (editMode == EditMode.Approach && pendingPoints.Count == 4)
            {
                CommitPendingPoints();
            }

            Repaint();
        }

        private void CommitPendingPoints()
        {
            if (editMode == EditMode.Lane && pendingPoints.Count != 4)
            {
                feedback = "Crie os quatro pontos da faixa antes de salvá-la.";
                return;
            }

            Undo.RecordObject(calibration, "Set traffic camera ROI");
            bool success;
            string error;
            if (editMode == EditMode.Approach)
            {
                success = calibration.SetApproachRoi(pendingPoints, out error);
            }
            else if (editingLaneId == null)
            {
                success = calibration.TryAddLaneRoi(laneId, pendingPoints, out error);
            }
            else
            {
                success = calibration.TrySetLaneRoi(editingLaneId, pendingPoints, out error);
            }

            if (success)
            {
                string message = editMode == EditMode.Approach
                    ? "ROI externa salva. As ROIs das faixas foram limpas."
                    : $"ROI da faixa '{laneId}' salva.";
                SaveCalibration(message);
                CancelEdit();
            }
            else
            {
                feedback = error;
            }
        }

        private void Begin(EditMode mode, string existingLaneId)
        {
            editMode = mode;
            editingLaneId = existingLaneId;
            pendingPoints.Clear();
            feedback = null;
        }

        private void CancelEdit()
        {
            editMode = EditMode.None;
            editingLaneId = null;
            pendingPoints.Clear();
        }

        private void UseSelectedCamera()
        {
            GameObject selected = Selection.activeGameObject;
            if (selected == null)
            {
                feedback = "Selecione um GameObject que tenha uma Camera.";
                return;
            }

            Camera selectedCamera = selected.GetComponent<Camera>();
            if (selectedCamera == null)
            {
                feedback = "O GameObject selecionado não possui uma Camera.";
                return;
            }

            calibration = selected.GetComponent<TrafficCameraCalibration>();
            if (calibration == null)
            {
                calibration = Undo.AddComponent<TrafficCameraCalibration>(selected);
            }

            CancelEdit();
            feedback = $"Usando a câmera '{selectedCamera.name}'.";
        }

        private void AlignWithSceneView()
        {
            SceneView sceneView = SceneView.lastActiveSceneView;
            if (sceneView == null || sceneView.camera == null)
            {
                feedback = "Abra e posicione uma Scene View antes de alinhar a câmera.";
                return;
            }

            Camera sceneCamera = sceneView.camera;
            Camera targetCamera = calibration.CameraComponent;
            Undo.RecordObject(calibration.transform, "Align traffic camera with Scene View");
            Undo.RecordObject(targetCamera, "Copy Scene View camera projection");
            calibration.transform.SetPositionAndRotation(sceneCamera.transform.position, sceneCamera.transform.rotation);
            targetCamera.fieldOfView = sceneCamera.fieldOfView;
            targetCamera.orthographic = sceneCamera.orthographic;
            targetCamera.orthographicSize = sceneCamera.orthographicSize;
            targetCamera.nearClipPlane = sceneCamera.nearClipPlane;
            targetCamera.farClipPlane = sceneCamera.farClipPlane;
            SaveCalibration("Câmera alinhada à Scene View.");
        }

        private void RenderPreview()
        {
            Camera sourceCamera = calibration.CameraComponent;
            EnsurePreviewTexture(calibration.CaptureWidth, calibration.CaptureHeight);
            EnsurePreviewCamera();

            try
            {
                previewCamera.CopyFrom(sourceCamera);
                previewCamera.transform.SetPositionAndRotation(
                    sourceCamera.transform.position,
                    sourceCamera.transform.rotation);
                previewCamera.enabled = false;
                previewCamera.targetTexture = previewTexture;
                previewCamera.Render();
                previewCamera.targetTexture = null;
                feedback = "Preview atualizado.";
            }
            catch (Exception exception)
            {
                previewCamera.targetTexture = null;
                feedback = $"Não foi possível renderizar o preview: {exception.Message}";
            }
        }

        private void ExportCalibrationJson()
        {
            if (!calibration.TryExportJson(out string json, out string error))
            {
                feedback = error;
                return;
            }

            string defaultName = string.IsNullOrWhiteSpace(calibration.CameraId)
                ? "camera-calibration"
                : $"{calibration.CameraId}-calibration";
            string path = EditorUtility.SaveFilePanel(
                "Export traffic camera calibration", Application.dataPath, defaultName, "json");
            if (string.IsNullOrEmpty(path))
            {
                return;
            }

            File.WriteAllText(path, json);
            if (path.StartsWith(Application.dataPath, StringComparison.Ordinal))
            {
                AssetDatabase.Refresh();
            }

            feedback = $"Calibração exportada para {path}.";
        }

        private void EnsurePreviewTexture(int width, int height)
        {
            if (previewTexture != null && previewTexture.width == width && previewTexture.height == height)
            {
                return;
            }

            ReleasePreviewTexture();
            previewTexture = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32)
            {
                name = "Traffic Camera ROI Preview",
                hideFlags = HideFlags.HideAndDontSave
            };
            previewTexture.Create();
        }

        private void EnsurePreviewCamera()
        {
            if (previewCamera != null)
            {
                return;
            }

            previewCameraObject = new GameObject("Traffic Camera ROI Preview (temporary)")
            {
                hideFlags = HideFlags.HideAndDontSave
            };
            previewCamera = previewCameraObject.AddComponent<Camera>();
            previewCamera.enabled = false;
        }

        private void ReleasePreviewTexture()
        {
            if (previewTexture == null)
            {
                return;
            }

            previewTexture.Release();
            DestroyImmediate(previewTexture);
            previewTexture = null;
        }

        private void ReleasePreviewCamera()
        {
            if (previewCameraObject != null)
            {
                DestroyImmediate(previewCameraObject);
            }

            previewCameraObject = null;
            previewCamera = null;
        }

        private void SaveCalibration(string message)
        {
            EditorUtility.SetDirty(calibration);
            EditorSceneManager.MarkSceneDirty(calibration.gameObject.scene);
            feedback = message;
        }

        private void DrawFeedback()
        {
            if (!string.IsNullOrEmpty(feedback))
            {
                EditorGUILayout.HelpBox(feedback, MessageType.None);
            }
        }
    }
}
