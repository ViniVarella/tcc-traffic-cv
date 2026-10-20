using System.Collections.Generic;
using NUnit.Framework;
using TccTrafficVision.CameraCalibration;
using UnityEngine;

namespace TccTrafficVision.Tests.Editor.CameraCalibration
{
    public sealed class RoiGeometryTests
    {
        [Test]
        public void LaneRoiInsideApproachIsAccepted()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));

            bool accepted = calibration.TryAddLaneRoi(
                "lane_0", Rectangle(0.2f, 0.2f, 0.4f, 0.8f), out string error);

            Assert.That(accepted, Is.True, error);
            Assert.That(calibration.LaneRois, Has.Count.EqualTo(1));
            DestroyCalibration(calibration);
        }

        [Test]
        public void LaneRoiInsideRotatedApproachIsAccepted()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(new List<Vector2>
            {
                new Vector2(0.1f, 0.5f),
                new Vector2(0.5f, 0.1f),
                new Vector2(0.9f, 0.5f),
                new Vector2(0.5f, 0.9f)
            });

            bool accepted = calibration.TryAddLaneRoi(
                "lane_0", Rectangle(0.4f, 0.4f, 0.6f, 0.6f), out string error);

            Assert.That(accepted, Is.True, error);
            DestroyCalibration(calibration);
        }

        [Test]
        public void LaneRoiOutsideApproachIsRejected()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));

            bool accepted = calibration.TryAddLaneRoi(
                "lane_0", Rectangle(0.05f, 0.2f, 0.4f, 0.8f), out string error);

            Assert.That(accepted, Is.False);
            Assert.That(error, Does.Contain("dentro da ROI externa"));
            DestroyCalibration(calibration);
        }

        [Test]
        public void PointOutsideApproachIsRejectedBeforeItIsAdded()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));

            bool accepted = calibration.TryValidateLanePoint(
                new List<Vector2>(), new Vector2(0.05f, 0.5f), null, out string error);

            Assert.That(accepted, Is.False);
            Assert.That(error, Does.Contain("fora da ROI principal"));
            DestroyCalibration(calibration);
        }

        [Test]
        public void OverlappingLaneRoisAreRejected()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));
            Assert.That(calibration.TryAddLaneRoi("lane_0", Rectangle(0.2f, 0.2f, 0.5f, 0.8f), out _), Is.True);

            bool accepted = calibration.TryAddLaneRoi(
                "lane_1", Rectangle(0.4f, 0.2f, 0.7f, 0.8f), out string error);

            Assert.That(accepted, Is.False);
            Assert.That(error, Does.Contain("se sobrepõe"));
            DestroyCalibration(calibration);
        }

        [Test]
        public void PointInsideAnotherLaneIsRejectedBeforeItIsAdded()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));
            Assert.That(calibration.TryAddLaneRoi("lane_0", Rectangle(0.2f, 0.2f, 0.5f, 0.8f), out _), Is.True);

            bool accepted = calibration.TryValidateLanePoint(
                new List<Vector2>(), new Vector2(0.3f, 0.5f), null, out string error);

            Assert.That(accepted, Is.False);
            Assert.That(error, Does.Contain("dentro da ROI da faixa 'lane_0'"));
            DestroyCalibration(calibration);
        }

        [Test]
        public void FourthPointThatWouldEncloseAnotherLaneIsRejectedBeforeItIsAdded()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));
            Assert.That(calibration.TryAddLaneRoi("lane_0", Rectangle(0.4f, 0.4f, 0.6f, 0.6f), out _), Is.True);

            List<Vector2> pending = new List<Vector2>
            {
                new Vector2(0.15f, 0.15f),
                new Vector2(0.85f, 0.15f),
                new Vector2(0.85f, 0.85f)
            };
            bool accepted = calibration.TryValidateLanePoint(
                pending, new Vector2(0.15f, 0.85f), null, out string error);

            Assert.That(accepted, Is.False);
            Assert.That(error, Does.Contain("se sobrepõe"));
            Assert.That(pending, Has.Count.EqualTo(3));
            DestroyCalibration(calibration);
        }

        [Test]
        public void DuplicateLaneIdIsRejected()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));
            Assert.That(calibration.TryAddLaneRoi("lane_0", Rectangle(0.2f, 0.2f, 0.4f, 0.8f), out _), Is.True);

            bool accepted = calibration.TryAddLaneRoi(
                "lane_0", Rectangle(0.5f, 0.2f, 0.7f, 0.8f), out string error);

            Assert.That(accepted, Is.False);
            Assert.That(error, Does.Contain("Já existe"));
            DestroyCalibration(calibration);
        }

        [Test]
        public void ExistingLaneCanBeRedefinedWithoutCollidingWithItself()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));
            Assert.That(calibration.TryAddLaneRoi("lane_0", Rectangle(0.2f, 0.2f, 0.4f, 0.8f), out _), Is.True);

            bool replaced = calibration.TrySetLaneRoi(
                "lane_0", Rectangle(0.3f, 0.2f, 0.6f, 0.8f), out string error);

            Assert.That(replaced, Is.True, error);
            Assert.That(calibration.LaneRois[0].Points[0].x, Is.EqualTo(0.3f));
            DestroyCalibration(calibration);
        }

        [Test]
        public void ExportIncludesCameraPoseResolutionAndNormalizedRois()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.transform.position = new Vector3(2f, 3f, 4f);
            calibration.transform.eulerAngles = new Vector3(10f, 20f, 30f);
            calibration.SetApproachRoi(Rectangle(0.1f, 0.1f, 0.9f, 0.9f));
            Assert.That(calibration.TryAddLaneRoi("lane_0", Rectangle(0.2f, 0.2f, 0.4f, 0.8f), out _), Is.True);

            bool exported = calibration.TryCreateExportData(out CameraCalibrationExport data, out string error);

            Assert.That(exported, Is.True, error);
            Assert.That(data.schemaVersion, Is.EqualTo(1));
            Assert.That(data.capture.width, Is.EqualTo(1280));
            Assert.That(data.capture.height, Is.EqualTo(720));
            Assert.That(data.pose.position, Is.EqualTo(new Vector3(2f, 3f, 4f)));
            Assert.That(data.approachRoi.points[0], Is.EqualTo(new Vector2(0.1f, 0.1f)));
            Assert.That(data.laneRois[0].id, Is.EqualTo("lane_0"));
            DestroyCalibration(calibration);
        }

        [Test]
        public void CrossedQuadrilateralIsRejected()
        {
            List<Vector2> crossed = new List<Vector2>
            {
                new Vector2(0.1f, 0.1f),
                new Vector2(0.9f, 0.9f),
                new Vector2(0.1f, 0.9f),
                new Vector2(0.9f, 0.1f)
            };

            bool valid = RoiGeometry.TryValidateQuadrilateral(crossed, out string error);

            Assert.That(valid, Is.False);
            Assert.That(error, Does.Contain("cruzar"));
        }

        [Test]
        public void FourthPointThatWouldCrossTheRoiIsRejectedBeforeItIsAdded()
        {
            TrafficCameraCalibration calibration = CreateCalibration();
            calibration.SetApproachRoi(Rectangle(0.05f, 0.05f, 0.95f, 0.95f));
            List<Vector2> pending = new List<Vector2>
            {
                new Vector2(0.1f, 0.1f),
                new Vector2(0.9f, 0.9f),
                new Vector2(0.1f, 0.9f)
            };

            bool accepted = calibration.TryValidateLanePoint(
                pending, new Vector2(0.9f, 0.1f), null, out string error);

            Assert.That(accepted, Is.False);
            Assert.That(error, Does.Contain("cruzar"));
            Assert.That(pending, Has.Count.EqualTo(3));
            DestroyCalibration(calibration);
        }

        [Test]
        public void QuadrilateralWithRepeatedCornerIsRejected()
        {
            bool valid = RoiGeometry.TryValidateQuadrilateral(new List<Vector2>
            {
                new Vector2(0.1f, 0.1f),
                new Vector2(0.1f, 0.1f),
                new Vector2(0.9f, 0.9f),
                new Vector2(0.1f, 0.9f)
            }, out string error);

            Assert.That(valid, Is.False);
            Assert.That(error, Does.Contain("distintos"));
        }

        private static TrafficCameraCalibration CreateCalibration()
        {
            GameObject gameObject = new GameObject("Camera");
            return gameObject.AddComponent<TrafficCameraCalibration>();
        }

        private static void DestroyCalibration(TrafficCameraCalibration calibration)
        {
            Object.DestroyImmediate(calibration.gameObject);
        }

        private static List<Vector2> Rectangle(float left, float top, float right, float bottom)
        {
            return new List<Vector2>
            {
                new Vector2(left, top),
                new Vector2(right, top),
                new Vector2(right, bottom),
                new Vector2(left, bottom)
            };
        }
    }
}
