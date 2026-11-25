"""AD PDF teksta kandidātu atlase (src/ad_plan.py, Issue #4).

Tikai sintētiski teksti. Tie ir teksta PDF imitācija un NEPIERĀDA vektoru
ģeometrijas atpazīšanu; kandidāti vienmēr jāapstiprina lietotājam.
"""
import unittest

from src.ad_plan import classify_page, extract_dimension_candidates, scan_plan_pages

COVER = "Drawing list\n1 Floor plan\n2 Roof plan\nProject number 15000"
FLOOR = "Floor plan 1:50\n12000\n4000\nKitchen 12.5 m2\nWindow 1200x1500\n25.09.2026"
ROOF = "Roof plan 1:100\n12600\n4600"


def values(candidates):
    return [c["value_mm"] for c in candidates]


class TestClassifyPage(unittest.TestCase):
    def test_floor_page(self):
        self.assertEqual(classify_page(FLOOR)[0], "floor")

    def test_roof_page(self):
        kind, reason = classify_page(ROOF)
        self.assertEqual(kind, "roof")
        self.assertIn("Jumta plāns", reason)

    def test_cover_or_list_page_is_not_a_floor_plan(self):
        kind, reason = classify_page(COVER)
        self.assertEqual(kind, "list")
        self.assertIn("netiek izmantoti", reason)

    def test_floor_and_roof_on_same_page_is_not_trusted(self):
        self.assertEqual(classify_page("Floor plan\nRoof plan\n12000")[0], "list")

    def test_list_marker_without_roof(self):
        self.assertEqual(classify_page("Title page\nFloor plan, Sections")[0], "list")
        self.assertEqual(classify_page("Zīmējumu saraksts\nFloor plan")[0], "list")

    def test_other_page(self):
        self.assertEqual(classify_page("Elevation\n12000\n4000")[0], "other")
        self.assertEqual(classify_page("")[0], "other")


class TestCandidates(unittest.TestCase):
    def test_plain_dimensions_are_candidates(self):
        found, excluded = extract_dimension_candidates(FLOOR)
        self.assertEqual(values(found), [4000, 12000])
        self.assertEqual(excluded, [])

    def test_areas_window_sizes_decimals_and_dates_are_not_candidates(self):
        text = "Area 12.5 m2\nWindow 1200x1500\nWindow 1500 x 1200\nValue 4000,5\nDate 25.09.2026\nRev 3"
        self.assertEqual(extract_dimension_candidates(text)[0], [])

    def test_out_of_range_numbers_ignored(self):
        found, _ = extract_dimension_candidates("1999\n20001\n123456\n2000\n20000")
        self.assertEqual(values(found), [2000, 20000])

    def test_terrace_numbers_are_excluded_and_reported(self):
        found, excluded = extract_dimension_candidates("Terase 6000\nTerrace 5000\nVeranda 3000\n12000")
        self.assertEqual(values(found), [12000])
        self.assertEqual(sorted(item["value_mm"] for item in excluded), [3000, 5000, 6000])
        self.assertTrue(all(item["reason"] == "Terase" for item in excluded))

    def test_thousands_separator_is_not_read(self):
        # "12 000" netiek atpazīts; lietotājs ievada izmēru pats.
        self.assertEqual(extract_dimension_candidates("12 000\n4 000")[0], [])

    def test_counts_are_informational_and_nothing_is_ranked_or_preselected(self):
        found, _ = extract_dimension_candidates("3500\n3500\n3500\n4000\n12000")
        self.assertEqual(values(found), [3500, 4000, 12000])      # pēc vērtības, nevis biežuma
        self.assertEqual({c["value_mm"]: c["count"] for c in found}, {3500: 3, 4000: 1, 12000: 1})
        for candidate in found:
            self.assertEqual(set(candidate), {"value_mm", "count", "context"})


class TestScanPlanPages(unittest.TestCase):
    def test_cover_floor_roof(self):
        scan = scan_plan_pages([COVER, FLOOR, ROOF])
        self.assertEqual([p["page"] for p in scan["floor_pages"]], [2])
        self.assertEqual(sorted((p["page"], p["kind"]) for p in scan["skipped_pages"]),
                         [(1, "list"), (3, "roof")])
        all_values = values([c for p in scan["floor_pages"] for c in p["candidates"]])
        self.assertEqual(all_values, [4000, 12000])
        self.assertNotIn(12600, all_values)      # jumta skaitļi
        self.assertNotIn(15000, all_values)      # titullapas skaitļi

    def test_several_floor_pages_keep_their_own_source_page(self):
        scan = scan_plan_pages(["Floor plan A\n12000", "Elevation", "Floor plan B\n9000"])
        self.assertEqual([(p["page"], values(p["candidates"])) for p in scan["floor_pages"]],
                         [(1, [12000]), (3, [9000])])

    def test_no_floor_plan(self):
        scan = scan_plan_pages(["Elevation\n12000\n4000", ""])
        self.assertEqual(scan, {"floor_pages": [], "skipped_pages": []})

    def test_empty_input(self):
        self.assertEqual(scan_plan_pages([]), {"floor_pages": [], "skipped_pages": []})


if __name__ == "__main__":
    unittest.main()
