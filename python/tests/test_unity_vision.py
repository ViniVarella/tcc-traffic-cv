import unittest

from experiments.test_unity_vision import parse_class_ids


class UnityVisionArgumentTests(unittest.TestCase):
    def test_parses_coco_and_single_class_filters(self) -> None:
        self.assertEqual(parse_class_ids("2,3,5,7"), [2, 3, 5, 7])
        self.assertEqual(parse_class_ids("0"), [0])

    def test_rejects_empty_or_negative_class_filter(self) -> None:
        with self.assertRaises(ValueError):
            parse_class_ids("")
        with self.assertRaises(ValueError):
            parse_class_ids("-1")


if __name__ == "__main__":
    unittest.main()
