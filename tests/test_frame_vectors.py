import unittest
from src.frame_vectors import detect_beams, compare_to_schedule
from src.frame_schedule import Beam

class TestFrameVectors(unittest.TestCase):
    def test_geometry_and_scale(self):
        class Rect:
            width, height = 680.2, 14.2
            def __iter__(self): return iter([0, 0, self.width, self.height])
        class Page:
            def get_drawings(self): return [{"fill": (.84, .66, .34), "rect": Rect()}]
        beams = detect_beams(Page(), drawing_scale=40)
        self.assertEqual(len(beams), 1)
        self.assertAlmostEqual(beams[0]["width_mm"], 200, delta=1)
        self.assertAlmostEqual(beams[0]["length_mm"], 9600, delta=2)

    def test_one_to_one(self):
        candidates = [{"width_mm":45, "length_mm":3280} for _ in range(3)]
        ref = [Beam(1, 45, 240, 3280, 2, 2)]
        result = compare_to_schedule(candidates, ref)
        self.assertEqual(len(result["matched"]), 2)
        self.assertEqual(len(result["unmatched_graphics"]), 1)
