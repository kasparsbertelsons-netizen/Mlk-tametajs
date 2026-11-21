import unittest
from src.frame_schedule import parse_beams, summarize

class TestFrameSchedule(unittest.TestCase):
    def test_table(self):
        pages = ["Other", "Structural Frame - TOP\nTimber Element list\n 1 Glued beam / līmsija 200 240 9600 2\n 2 Glued beam / līmsija 45 240 3280 12"]
        result = parse_beams(pages)
        self.assertEqual(summarize(result)["pieces"], 14)
        self.assertEqual(result[0].page, 2)
        self.assertAlmostEqual(result[0].volume_m3, 0.9216)

    def test_no_guessing(self):
        self.assertEqual(parse_beams(["Structural Frame - TOP\n200 240 9600 2"]), [])
