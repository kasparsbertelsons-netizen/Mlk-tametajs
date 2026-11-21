import unittest
from src.pdf_reader import extract_frame_mentions


class TestPDFReader(unittest.TestCase):
    def test_page_evidence(self):
        pages = ["No frame", "7. GL Frame - 240mm / PIR - 200mm\n6. Timber frame 45x70 / Insulation 2x50mm"]
        found = extract_frame_mentions(pages)
        self.assertEqual(len(found), 2)
        self.assertTrue(all(item["page"] == 2 for item in found))
        self.assertTrue(any("240mm" in item["evidence"] for item in found))

    def test_empty(self):
        self.assertEqual(extract_frame_mentions(["", "No data"]), [])
