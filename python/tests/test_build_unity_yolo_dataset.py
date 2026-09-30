import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from bridge import UnityBridge
from experiments.build_unity_yolo_dataset import CaptureRun, DatasetSplit, assign_runs, build_dataset, mask_yolo_lines, yolo_line
from vision.dataset_classes import DATASET_CLASSES, class_for_vehicle_type


class BuildUnityYoloDatasetTests(unittest.TestCase):
    def test_yolo_line_uses_normalized_vehicle_box(self) -> None:
        line = yolo_line({"class_id": 0, "center_x": 0.5, "center_y": 0.25, "width": 0.1, "height": 0.2})

        self.assertEqual(line, "0 0.500000 0.250000 0.100000 0.200000")

    def test_builds_images_labels_and_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            frames_root = root / "frames"
            labels_root = root / "annotations"
            (frames_root / "south").mkdir(parents=True)
            (labels_root / "south").mkdir(parents=True)
            (frames_root / "south" / "step_000001.jpg").write_bytes(b"jpeg")
            (labels_root / "south" / "step_000001.json").write_text(
                json.dumps(
                    {
                        "vehicles": [
                            {"class_id": 0, "center_x": 0.5, "center_y": 0.5, "width": 0.2, "height": 0.3}
                        ]
                    }
                ),
                encoding="utf-8",
            )

            output = root / "dataset"
            counts = build_dataset(frames_root, labels_root, output, DatasetSplit(), seed=7)

            self.assertEqual(sum(counts[name] for name in ("train", "val", "test")), 1)
            label_files = list((output / "labels").glob("*/*.txt"))
            self.assertEqual(len(label_files), 1)
            self.assertEqual(label_files[0].read_text(encoding="utf-8"), "0 0.500000 0.500000 0.200000 0.300000\n")
            data_yaml = (output / "data.yaml").read_text(encoding="utf-8")
            self.assertIn(f"path: {output.resolve()}", data_yaml)
            self.assertIn("0: vehicle", data_yaml)

    def test_mask_yolo_lines_uses_visible_instance_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            mask_path = Path(temporary_directory) / "mask.png"
            image = Image.new("RGB", (10, 8), (0, 0, 0))
            for x in range(2, 6):
                for y in range(1, 4):
                    image.putpixel((x, y), (51, 102, 153))
            image.save(mask_path)

            lines = mask_yolo_lines(
                mask_path,
                [
                    {"class_id": 0, "color_r": 51, "color_g": 102, "color_b": 153},
                    {"class_id": 0, "color_r": 102, "color_g": 102, "color_b": 102},
                ],
            )

            self.assertEqual(lines, ["0 0.400000 0.312500 0.400000 0.375000"])

    def test_rejects_non_empty_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "dataset"
            output.mkdir()

            with self.assertRaises(FileExistsError):
                build_dataset(root, root, output, DatasetSplit(), seed=42)

    def test_emergency_vehicles_get_their_own_class(self) -> None:
        self.assertEqual(DATASET_CLASSES, ("vehicle", "emergency"))
        self.assertEqual((class_for_vehicle_type("emergency"), class_for_vehicle_type("DEFAULT_VEHTYPE"), class_for_vehicle_type(None)), (1, 0, 0))
        line = yolo_line({"vehicle_type": "emergency", "class_id": 0, "center_x": 0.5, "center_y": 0.5, "width": 0.1, "height": 0.1})
        self.assertTrue(line.startswith("1 "))
        with self.assertRaises(ValueError):
            yolo_line({"class_id": 7, "center_x": 0.5, "center_y": 0.5, "width": 0.1, "height": 0.1})

    def test_bridge_derives_class_from_vehicle_type(self) -> None:
        box = {"center_x": 0.5, "center_y": 0.5, "width": 0.1, "height": 0.1}
        annotations = UnityBridge._parse_ground_truth_vehicles([
            {"vehicle_id": "amb", "vehicle_type": "emergency", "class_id": 0, **box},
            {"vehicle_id": "car", "vehicle_type": "DEFAULT_VEHTYPE", **box},
        ])
        self.assertEqual([item["class_id"] for item in annotations], [1, 0])

    def test_runs_are_assigned_whole_to_one_split(self) -> None:
        runs = [CaptureRun(f"run-{index:02d}", Path("f"), Path("l")) for index in range(10)]
        assignment = assign_runs(runs, DatasetSplit(), seed=3)
        self.assertEqual(sorted(assignment), [run.name for run in runs])
        self.assertEqual(sorted(assignment.values()).count("test"), 1)
        self.assertEqual(sorted(assignment.values()).count("val"), 1)
        self.assertEqual(assignment, assign_runs(runs, DatasetSplit(), seed=3))
        with self.assertRaises(ValueError):
            assign_runs(runs[:2], DatasetSplit(), seed=3)

    def test_build_with_runs_keeps_each_run_in_one_split(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run_dirs = []
            for index in range(3):
                run_dir = root / f"run-{index}"
                (run_dir / "frames" / "east").mkdir(parents=True)
                (run_dir / "labels" / "east").mkdir(parents=True)
                for step in range(2):
                    (run_dir / "frames" / "east" / f"step_{step:06d}.jpg").write_bytes(b"jpeg")
                    vehicles = [{"vehicle_type": "emergency" if index == 0 else "car", "class_id": 0,
                                 "center_x": 0.5, "center_y": 0.5, "width": 0.2, "height": 0.2}]
                    (run_dir / "labels" / "east" / f"step_{step:06d}.json").write_text(json.dumps({"vehicles": vehicles}), encoding="utf-8")
                run_dirs.append(run_dir)
            output = root / "dataset"
            counts = build_dataset(None, None, output, DatasetSplit(), seed=1, runs=[CaptureRun.from_dir(path) for path in run_dirs])
            self.assertEqual((counts["train"], counts["val"], counts["test"]), (2, 2, 2))
            self.assertEqual((counts["class_vehicle"], counts["class_emergency"]), (4, 2))
            assignment = json.loads((output / "runs.json").read_text(encoding="utf-8"))
            for run_name, split_name in assignment.items():
                files = list((output / "images" / split_name).glob(f"{run_name}_*.jpg"))
                self.assertEqual(len(files), 2)
            self.assertIn("1: emergency", (output / "data.yaml").read_text(encoding="utf-8"))
            strided = build_dataset(None, None, root / "strided", DatasetSplit(), seed=1,
                                    runs=[CaptureRun.from_dir(path) for path in run_dirs], frame_stride=2)
            self.assertEqual(strided["train"] + strided["val"] + strided["test"], 3)


if __name__ == "__main__":
    unittest.main()
