import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from experiments.build_unity_yolo_dataset import DatasetSplit, build_dataset, mask_yolo_lines, yolo_line


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


if __name__ == "__main__":
    unittest.main()
