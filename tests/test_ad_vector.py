"""AD vektoru ģeometrijas analīzes testi (src/ad_vector.py, Issue #6).

Tikai sintētiski PDF no tools/synthetic_ad_pdf.py (reāli zīmētas līnijas un izmēru norādes).
Sagaidāmās koordinātes un izmēri ir aprēķināti ar roku no ģeneratora konstantēm (150, 260 pt;
12000 mm / 50 · 72 / 25,4 = 680,31 pt utt.), nevis iegūti no testējamā koda.

Sintētisks rezultāts NEPIERĀDA, ka tiks atpazīti reāli AD rasējumi.
"""
import json
import unittest

import pymupdf

from src.ad_plan import scan_plan_pages
from src.ad_vector import (
    PROVEN, RECOGNISED, REFUSED, UNCLEAR, analyze_pdf, render_preview_png,
)
from src.pdf_reader import read_pdf
from tools import synthetic_ad_pdf as gen

PT = 72 / 25.4


def floor_pages(data):
    """Tā pati lapu izvēle, ko lieto lietotne: teksta klasifikācija (jumts un titullapa tiek izslēgti)."""
    scan = scan_plan_pages([p["text"] for p in read_pdf(data)["pages"]])
    return [p["page"] for p in scan["floor_pages"]], scan


def analyze(data, pages=None):
    pages = pages if pages is not None else floor_pages(data)[0]
    return {p["page"]: p for p in analyze_pdf(data, pages)["pages"]}


def only(analysis_page):
    assert len(analysis_page["candidates"]) == 1, analysis_page["candidates"]
    return analysis_page["candidates"][0]


def custom_pdf(draw, scale_text="Mērogs 1:50"):
    """Vienas lapas PDF ar patvaļīgu zīmējumu (draw(sheet))."""
    doc = gen._new_doc()
    sheet = gen.Sheet(doc, title="Floor plan", scale_text=scale_text)
    draw(sheet)
    sheet.finish()
    return gen._to_bytes(doc)


class TestSample01(unittest.TestCase):
    """12000 × 4000, 1:50, telpa 3500 (maldinošs), terase, titullapa, jumta lapa ar pārkari."""

    @classmethod
    def setUpClass(cls):
        cls.data = gen.build_sample_01()
        cls.pages, cls.scan = floor_pages(cls.data)
        cls.result = analyze(cls.data)

    def test_only_the_floor_plan_page_is_analysed(self):
        self.assertEqual(self.pages, [2])
        self.assertEqual(sorted((p["page"], p["kind"]) for p in self.scan["skipped_pages"]),
                         [(1, "list"), (3, "roof")])
        self.assertEqual(list(self.result), [2])

    def test_module_candidate_with_vector_evidence(self):
        c = only(self.result[2])
        self.assertEqual((c["status"], c["shape"], c["length_mm"], c["width_mm"]), (PROVEN, "rectangle", 12000, 4000))
        self.assertTrue(c["transferable"])
        x0, y0 = 150, 260
        expected = [x0, y0, x0 + 12000 / 50 * PT, y0 + 4000 / 50 * PT]          # 830,31 un 486,77 pt
        for got, want in zip(c["bbox_pt"], expected):
            self.assertAlmostEqual(got, want, delta=0.1)
        self.assertEqual(len(c["vertices_pt"]), 4)
        self.assertEqual(c["line_width_pt"], 2.0)
        self.assertEqual(c["page"], 2)

    def test_dimension_evidence_ties_dimension_lines_to_contour_edges(self):
        c = only(self.result[2])
        by_orientation = {d["orientation"]: d for d in c["dimensions"]}
        self.assertEqual(by_orientation["H"]["value_mm"], 12000)
        self.assertEqual(by_orientation["V"]["value_mm"], 4000)
        self.assertAlmostEqual(by_orientation["H"]["measured_pt"], 680.31, delta=0.1)
        self.assertAlmostEqual(by_orientation["V"]["measured_pt"], 226.77, delta=0.1)
        for d in c["dimensions"]:
            self.assertAlmostEqual(d["implied_denominator"], 50.0, delta=0.1)   # mērogs no pašas ģeometrijas
            self.assertTrue(d["extension_lines_both_ends"])
            self.assertEqual(len(d["text_bbox_pt"]), 4)
        self.assertEqual({d["value_mm"] for d in self.result[2]["dimensions"]}, {12000, 4000, 3500, 4500})

    def test_scale_is_verified_against_dimensions_not_just_title(self):
        scale = only(self.result[2])["scale"]
        self.assertEqual((scale["status"], scale["denominator"]), ("pārbaudīts", 50))
        self.assertIn("1:50", scale["source"])
        for implied in scale["implied"]:
            self.assertAlmostEqual(implied, 50.0, delta=0.1)
        declared = self.result[2]["scale"]["declared"]
        self.assertEqual((declared["status"], declared["denominator"]), ("viens", 50))
        self.assertEqual(len(declared["sources"][0]["bbox"]), 4)

    def test_room_and_terrace_are_not_taken_for_the_module(self):
        page = self.result[2]
        kinds = {e["kind"]: e for e in page["excluded"]}
        self.assertEqual(kinds["room"]["dimensions"], [3500])
        self.assertIn("Virtuve", kinds["room"]["label"])
        self.assertEqual(kinds["terrace"]["dimensions"], [4500])
        self.assertEqual({c["length_mm"] for c in page["candidates"]}, {12000})

    def test_module_label_is_evidence_for_the_contour_role(self):
        c = only(self.result[2])
        self.assertEqual(c["boundary"]["label"], "MODULIS M1")
        self.assertTrue(any("MODULIS M1" in line for line in c["evidence"]))

    def test_roof_overhang_is_not_used_but_is_visible_when_the_roof_page_is_forced(self):
        # Jumta lapa tiek izslēgta ar lapas klasifikāciju; pat ja to analizē, pārkare ir 12600 × 4600, nevis 12000 × 4000.
        roof = only(analyze(self.data, [3])[3])
        self.assertEqual((roof["length_mm"], roof["width_mm"]), (12600, 4600))
        self.assertNotIn(3, self.result)

    def test_result_is_json_serialisable_and_repeatable(self):
        json.dumps(self.result)
        self.assertEqual(self.result, analyze(self.data))


class TestSample02(unittest.TestCase):
    def test_12100x3600_at_1_to_100(self):
        c = only(analyze(gen.build_sample_02())[1])
        self.assertEqual((c["status"], c["length_mm"], c["width_mm"]), (PROVEN, 12100, 3600))
        self.assertEqual(c["scale"]["denominator"], 100)
        for d in c["dimensions"]:
            self.assertAlmostEqual(d["implied_denominator"], 100.0, delta=0.2)
        self.assertAlmostEqual(c["bbox_pt"][2] - c["bbox_pt"][0], 12100 / 100 * PT, delta=0.1)   # 342,99 pt


class TestTwoModules(unittest.TestCase):
    def test_boundary_proven_gives_two_separate_modules(self):
        page = analyze(gen.build_sample_03())[1]
        a, b = page["candidates"]
        self.assertEqual([(a["status"], a["length_mm"], a["width_mm"]), (b["status"], b["length_mm"], b["width_mm"])],
                         [(PROVEN, 12000, 4000), (PROVEN, 12000, 3600)])
        self.assertEqual((a["boundary"]["adjacent_to"], b["boundary"]["adjacent_to"]), ([b["id"]], [a["id"]]))
        for c in (a, b):
            self.assertIsNotNone(c["boundary"]["separator"])
            self.assertTrue(c["boundary"]["separator"]["dashed"])
            self.assertTrue(any("robeža" in line and "pierādīta" in line for line in c["evidence"]))
        self.assertEqual(b["shape"], "rectangle")            # B zīmēts kā slēgta polilīnija (qu)
        self.assertNotIn(7600, {c["width_mm"] for c in page["candidates"]})   # nav apvienots

    def test_adjacent_without_boundary_is_unclear_and_not_merged(self):
        for kwargs in ({"separator": False}, {"separator": False, "labels": False}):
            page = analyze(gen.build_sample_03(**kwargs))[1]
            self.assertEqual(len(page["candidates"]), 2, kwargs)
            for c in page["candidates"]:
                self.assertEqual(c["status"], UNCLEAR, kwargs)
                self.assertIsNone(c["boundary"]["separator"])
                self.assertTrue(any("robeža nav pierādīta" in i for i in c["issues"]))
                self.assertIn(c["length_mm"], (12000,))


class TestAmbiguousAndRefused(unittest.TestCase):
    def test_l_shape_is_refused_and_not_split(self):
        page = analyze(gen.build_sample_04())[1]
        c = only(page)
        self.assertEqual((c["shape"], c["status"]), ("polygon", REFUSED))
        self.assertEqual((c["length_mm"], c["width_mm"], c["transferable"]), (None, None, False))
        self.assertEqual(len(c["vertices_pt"]), 6)
        self.assertEqual(c["observed_mm"], {"horizontal": 12000, "vertical": 7000})
        self.assertTrue(any("nav taisnstūris" in i for i in c["issues"]))
        self.assertEqual(len(page["candidates"]), 1)

    def test_missing_scale_is_unclear_and_inferred_from_dimensions(self):
        page = analyze(gen.build_sample_05())[1]
        self.assertEqual(page["scale"]["declared"]["status"], "nav")
        c = only(page)
        self.assertEqual((c["status"], c["length_mm"], c["width_mm"]), (UNCLEAR, 12000, 4000))
        self.assertEqual((c["scale"]["status"], c["scale"]["denominator"]), ("nav norādīts", 50))
        self.assertTrue(any("nav norādīts" in i for i in c["issues"]))

    def test_conflicting_scale_is_refused_without_dimensions(self):
        c = only(analyze(gen.build_sample_06())[1])
        self.assertEqual((c["status"], c["scale"]["status"], c["scale"]["denominator"]), (REFUSED, "pretrunā", 100))
        self.assertEqual((c["length_mm"], c["width_mm"], c["transferable"]), (None, None, False))
        for implied in c["scale"]["implied"]:
            self.assertAlmostEqual(implied, 50.0, delta=0.1)
        self.assertTrue(any("1:100" in i and "1:50" in i for i in c["issues"]))

    def test_multiple_scales_on_page_are_not_trusted(self):
        data = custom_pdf(lambda s: (gen._module(s, 150, 260, 12000, 4000, 50), s.text(150, 600, "Detaļa 1:20")))
        c = only(analyze(data)[1])
        self.assertEqual(c["scale"]["status"], "nenosakāms")
        self.assertEqual(c["status"], UNCLEAR)
        self.assertTrue(any("vairāki" in i for i in c["issues"]))

    def test_dimension_text_not_matching_geometry_without_scale_is_not_accepted(self):
        def draw(sheet):
            x0, y0, x1, y1 = 150, 260, 150 + gen.mm(12000, 50), 260 + gen.mm(4000, 50)
            sheet.rect(x0, y0, x1, y1)
            sheet.dim_h(x0, x1, y1, 45, "12000")
            sheet.dim_v(y0, y1, x0, -45, "3000")             # ģeometrija atbilst 4000, teksts saka 3000
        c = only(analyze(custom_pdf(draw, scale_text=None))[1])
        self.assertEqual(c["status"], UNCLEAR)
        self.assertEqual(c["scale"]["status"], "nenosakāms")
        self.assertTrue(c["transferable"])  # abi skaitļi ir nolasīti, bet statuss paliek neskaidrs un jāpārbauda
        self.assertTrue(any("nav savstarpēji saskaņotas" in i for i in c["issues"]))

    def test_dimension_text_not_matching_geometry_with_declared_scale_is_refused(self):
        def draw(sheet):
            x0, y0, x1, y1 = 150, 260, 150 + gen.mm(12000, 50), 260 + gen.mm(4000, 50)
            sheet.rect(x0, y0, x1, y1)
            sheet.dim_h(x0, x1, y1, 45, "12000")
            sheet.dim_v(y0, y1, x0, -45, "3000")
        c = only(analyze(custom_pdf(draw))[1])
        self.assertEqual((c["status"], c["scale"]["status"]), (REFUSED, "pretrunā"))
        self.assertIsNone(c["length_mm"])

    def test_only_one_dimension_gives_no_values(self):
        def draw(sheet):
            x0, y0, x1, y1 = 150, 260, 150 + gen.mm(12000, 50), 260 + gen.mm(4000, 50)
            sheet.rect(x0, y0, x1, y1)
            sheet.dim_h(x0, x1, y1, 45, "12000")
        c = only(analyze(custom_pdf(draw))[1])
        self.assertEqual((c["status"], c["length_mm"], c["width_mm"], c["transferable"]), (UNCLEAR, None, None, False))
        self.assertEqual(c["observed_mm"], {"horizontal": 12000, "vertical": None})

    def test_dimension_not_ending_at_contour_edges_is_not_associated(self):
        def draw(sheet):
            x0, y0, x1, y1 = 150, 260, 150 + gen.mm(12000, 50), 260 + gen.mm(4000, 50)
            sheet.rect(x0, y0, x1, y1)
            sheet.dim_h(x0 + 20, x1 - 20, y1, 45, "11000")      # izvilkuma līnijas neatrodas pie kontūras malām
            sheet.dim_v(y0 + 20, y1 - 20, x0, -45, "3500")
        page = analyze(custom_pdf(draw))[1]
        self.assertEqual(page["candidates"], [])
        self.assertTrue(any(e["kind"] == "unmeasured" for e in page["excluded"]))

    def test_dimensions_without_extension_lines_are_not_proven(self):
        def draw(sheet):
            x0, y0, x1, y1 = 150, 260, 150 + gen.mm(12000, 50), 260 + gen.mm(4000, 50)
            sheet.rect(x0, y0, x1, y1)
            sheet.line((x0, y1 + 45), (x1, y1 + 45))                       # tikai izmēru līnija, bez izvilkuma līnijām
            sheet.page.insert_text(((x0 + x1) / 2 - 12, y1 + 42), "12000", fontsize=9)
            sheet.line((x0 - 45, y0), (x0 - 45, y1))
            sheet.number_v(x0 - 47.5, (y0 + y1) / 2 + 10, "4000")
            sheet.text(x0 + 300, y0 + 40, "MODULIS M1", size=12)
        c = only(analyze(custom_pdf(draw))[1])
        self.assertEqual(c["status"], UNCLEAR)                              # bez izvilkuma līnijām nav "pierādīts"
        self.assertEqual((c["length_mm"], c["width_mm"]), (12000, 4000))
        self.assertTrue(all(not d["extension_lines_both_ends"] for d in c["dimensions"]))
        self.assertTrue(any("izvilkuma līniju" in i for i in c["issues"]))

    def test_non_numeric_text_near_dimension_lines_is_not_a_dimension(self):
        def draw(sheet):
            x0, y0, x1, y1 = gen._module(sheet, 150, 260, 12000, 4000, 50)
            xm = (x0 + x1) / 2
            sheet.text(xm - 130, y1 + 43, "Garums")                          # vārdi un mērvienības tieši pie izmēru līnijas
            sheet.text(xm + 60, y1 + 43, "mm")
            sheet.text(xm + 120, y1 + 43, "A12")
        page = analyze(custom_pdf(draw))[1]
        self.assertEqual(page["status"], "ok")
        c = only(page)
        self.assertEqual((c["status"], c["length_mm"], c["width_mm"]), (PROVEN, 12000, 4000))
        self.assertEqual({d["value_mm"] for d in page["dimensions"]}, {12000, 4000})

    def test_unlabelled_contour_is_recognised_but_not_proven(self):
        c = only(analyze(gen.build_sample_01(module_label=False))[2])
        self.assertEqual((c["status"], c["length_mm"], c["width_mm"]), (RECOGNISED, 12000, 4000))
        self.assertIsNone(c["boundary"]["label"])
        self.assertTrue(any("fasādes kontūra" in i for i in c["issues"]))


class TestNotChosenByLargestNumberOrSize(unittest.TestCase):
    def test_large_contour_without_dimensions_is_not_a_candidate(self):
        def draw(sheet):
            sheet.rect(100, 200, 100 + gen.mm(12000, 50), 200 + gen.mm(4000, 50))     # liels, bez izmēriem
            x0, y0 = 150, 520
            x1, y1 = x0 + gen.mm(3500, 50), y0 + gen.mm(2500, 50)
            sheet.rect(x0, y0, x1, y1, width=1.0)                                        # mazs, ar izmēriem
            sheet.dim_h(x0, x1, y1, 25, "3500")
            sheet.dim_v(y0, y1, x0, -25, "2500")
            sheet.text(700, 700, "15000")                                                # liels skaitlis bez izmēru līnijas
        page = analyze(custom_pdf(draw))[1]
        c = only(page)
        self.assertEqual((c["length_mm"], c["width_mm"]), (3500, 2500))
        self.assertEqual({d["value_mm"] for d in page["dimensions"]}, {3500, 2500})     # 15000 nav izmēru norāde
        big = [e for e in page["excluded"] if e["kind"] == "unmeasured" and e["bbox"][2] - e["bbox"][0] > 600]
        self.assertEqual(len(big), 1)

    def test_facade_and_inner_contour_both_unclear(self):
        page = analyze(gen.build_sample_09())[1]
        sizes = {(c["length_mm"], c["width_mm"]): c for c in page["candidates"]}
        self.assertEqual(set(sizes), {(12400, 4400), (12000, 4000)})
        for c in sizes.values():
            self.assertEqual(c["status"], UNCLEAR)
            self.assertTrue(any("Ligzdotas kontūras" in i and "fasādes" in i for i in c["issues"]))

    def test_module_label_on_inner_contour_resolves_the_nesting(self):
        page = analyze(gen.build_sample_09(inner_label=True))[1]
        c = only(page)
        self.assertEqual((c["status"], c["length_mm"], c["width_mm"]), (PROVEN, 12000, 4000))
        self.assertTrue(any(e["kind"] == "nested" and e["dimensions"] == [12400, 4400] for e in page["excluded"]))


class TestRotatedAndVerticalAndNoVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = gen.build_sample_07()
        cls.result = analyze(cls.data)

    def test_rotated_page_gives_same_module(self):
        with pymupdf.open(stream=self.data, filetype="pdf") as doc:
            self.assertEqual(doc[0].rotation, 90)
        c = only(self.result[1])
        self.assertEqual((c["status"], c["length_mm"], c["width_mm"]), (PROVEN, 12000, 4000))
        self.assertEqual(self.result[1]["rotation"], 90)
        self.assertAlmostEqual(c["bbox_pt"][2] - c["bbox_pt"][0], 680.31, delta=0.1)

    def test_vertically_drawn_module(self):
        c = only(self.result[2])
        self.assertEqual((c["status"], c["length_mm"], c["width_mm"], c["orientation"]), (PROVEN, 12000, 4000, "vertikāla"))
        self.assertAlmostEqual(c["bbox_pt"][3] - c["bbox_pt"][1], 680.31, delta=0.1)
        self.assertAlmostEqual(c["bbox_pt"][2] - c["bbox_pt"][0], 226.77, delta=0.1)

    def test_pages_without_vector_geometry(self):
        data = gen.build_sample_08()
        pages, _ = floor_pages(data)
        self.assertEqual(pages, [1, 2])
        result = analyze(data)
        for page in result.values():
            self.assertEqual(page["status"], "no_vector_geometry")
            self.assertEqual(page["candidates"], [])
            self.assertIn("nav vektoru ģeometrijas", page["notes"][0])

    def test_text_only_numbers_are_not_dimensions(self):
        # 12000 un 4000 ir tikai teksts, bez izmēru līnijām: nav kandidātu un nav izdomātu izmēru.
        page = analyze(gen.build_sample_08(), [1])[1]
        self.assertEqual(page["candidates"], [])
        self.assertEqual(page["dimensions"], [])


class TestPreview(unittest.TestCase):
    @staticmethod
    def pixel(png, x, y):
        pixmap = pymupdf.Pixmap(png)
        return pixmap.pixel(int(x), int(y))[:3], pixmap.width, pixmap.height

    def test_selected_contour_is_marked_in_status_colour(self):
        data = gen.build_sample_01()
        page = analyze(data)[2]
        png = render_preview_png(data, page, "P2-K1", dpi=72)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        c = page["candidates"][0]
        (r, g, b), width, height = self.pixel(png, (c["bbox_pt"][0] + c["bbox_pt"][2]) / 2, c["bbox_pt"][1])
        self.assertEqual((width, height), (1191, 842))
        self.assertTrue(g > r + 60 and g > b + 40, (r, g, b))       # zaļš = pierādīts

    def test_refused_candidate_is_red_and_unclear_is_orange(self):
        for builder, expected in ((gen.build_sample_06, "red"), (gen.build_sample_05, "orange")):
            data = builder()
            page = analyze(data)[1]
            c = page["candidates"][0]
            (r, g, b), _, _ = self.pixel(render_preview_png(data, page, c["id"]), (c["bbox_pt"][0] + c["bbox_pt"][2]) / 2, c["bbox_pt"][1])
            if expected == "red":
                self.assertTrue(r > 180 and g < 100 and b < 100, (r, g, b))
            else:
                self.assertTrue(r > 200 and 100 < g < 200 and b < 80, (r, g, b))

    def test_rotated_page_preview_is_rotated_and_does_not_fail(self):
        data = gen.build_sample_07()
        page = analyze(data)[1]
        png = render_preview_png(data, page, page["candidates"][0]["id"])
        _, width, height = self.pixel(png, 5, 5)
        self.assertEqual((width, height), (842, 1191))


if __name__ == "__main__":
    unittest.main()
