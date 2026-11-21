import unittest
from src.estimate import Wall, calculate_wall


class TestWall(unittest.TestCase):
    def test_simple(self):
        result = calculate_wall(Wall(6, 3, 2))
        self.assertEqual(result["net_area_m2"], 16)
        self.assertEqual(result["estimated_studs_pcs"], 13)
        self.assertEqual(result["approx_insulation_m3"], 3.2)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            calculate_wall(Wall(2, 2, 4))
