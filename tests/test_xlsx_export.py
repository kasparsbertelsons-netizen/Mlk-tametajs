"""Issue #14: īsts XLSX eksports — lapas, šūnu summas, klienta lapa bez iekšējām pašizmaksām, teksta (nevis formulas) šūnas."""
import io
import unittest
import zipfile

import openpyxl

from src.building_demo import demo_project
from src.building_estimate import ST_DUP, estimate
from src.xlsx_export import MAT_HEADER, build_workbook

SHEETS = ["Kopsavilkums", "Klienta piedāvājums", "Materiālu tāme", "Iepirkumi", "Darba operācijas", "Pieņēmumi un neiekļautais"]
FORBIDDEN_IN_CLIENT = ("pašizmaks", "darba stund", "likme", "uzcenoj", "marža", "peļņa", "normstund", "pieskaitām", "EUR/h")


def load(project):
    est = estimate(project)
    data = build_workbook(project, est)
    return openpyxl.load_workbook(io.BytesIO(data)), data, est


def cells(ws):
    return [[c.value for c in row] for row in ws.iter_rows()]


def find(ws, label, col=1):
    for row in ws.iter_rows():
        if row[col - 1].value == label:
            return row
    raise AssertionError(f"nav rindas «{label}»")


class TestWorkbookStructure(unittest.TestCase):
    def setUp(self):
        self.p = demo_project()
        self.wb, self.data, self.est = load(self.p)

    def test_is_real_xlsx_with_all_sheets(self):
        self.assertTrue(self.data.startswith(b"PK"))                                    # zip, nevis pārdēvēts CSV
        self.assertIn("xl/workbook.xml", zipfile.ZipFile(io.BytesIO(self.data)).namelist())
        self.assertEqual(self.wb.sheetnames, SHEETS)

    def test_summary_numbers_are_numeric_cells_with_expected_values(self):
        ws = self.wb["Kopsavilkums"]
        expected = {"PĀRDOŠANAS CENA bez PVN": 85798.54, "Summa ar PVN": 103816.24, "PAŠIZMAKSA": 74607.43, "TIEŠĀS IZMAKSAS": 69080.95}
        for label, value in expected.items():
            cell = find(ws, label)[1]
            self.assertEqual(cell.data_type, "n", label)
            self.assertAlmostEqual(cell.value, value, 2, label)
        self.assertAlmostEqual(find(ws, "Materiāli (pasūtāmais × cena)")[1].value, 47955.46, 2)
        self.assertAlmostEqual(find(ws, "Ražošanas darbs (stundas × likme)")[1].value, 13225.49, 2)
        self.assertIn("413.30 h", find(ws, "Ražošanas darbs (stundas × likme)")[2].value)

    def test_summary_components_add_up(self):
        ws = self.wb["Kopsavilkums"]
        parts = sum(find(ws, name)[1].value for name in ("Materiāli (pasūtāmais × cena)", "Ražošanas darbs (stundas × likme)", "Ārpakalpojumi",
                                                          "Transports", "Montāža", "Citas izmaksas"))
        self.assertAlmostEqual(parts, find(ws, "TIEŠĀS IZMAKSAS")[1].value, 6)
        direct = find(ws, "TIEŠĀS IZMAKSAS")[1].value
        self.assertAlmostEqual(direct * 1.08, find(ws, "PAŠIZMAKSA")[1].value, 6)
        sell = find(ws, "PĀRDOŠANAS CENA bez PVN")[1].value
        self.assertAlmostEqual(sell, find(ws, "PAŠIZMAKSA")[1].value * 1.15, 6)
        self.assertAlmostEqual(find(ws, "Summa ar PVN")[1].value, sell * 1.21, 6)

    def test_demo_and_stage_banners(self):
        text = " ".join(str(v) for row in cells(self.wb["Kopsavilkums"]) for v in row if v)
        self.assertIn("NAV GALA PIEDĀVĀJUMS", text)
        self.assertIn("DEMO", text)
        self.assertIn("AD budžeta stadija", text)
        self.assertNotIn("NEPILNS:", text)                                               # demo ir pilnībā cenots

    def test_materials_sheet_matches_estimate_and_sums(self):
        ws = self.wb["Materiālu tāme"]
        self.assertEqual([c.value for c in ws[1]], MAT_HEADER)
        rows = [r for r in cells(ws)[1:] if r[0] and r[3]]
        self.assertEqual(len(rows), len(self.est.rows))
        cost_col = MAT_HEADER.index("Izmaksas EUR")
        total_row = next(r for r in cells(ws) if r[3] == "Materiāli kopā (tikai rindas ar cenu)")
        self.assertAlmostEqual(sum(r[cost_col] for r in rows if isinstance(r[cost_col], (int, float))), total_row[cost_col], 6)
        self.assertAlmostEqual(total_row[cost_col], 47955.46, 2)
        clt = next(r for r in rows if r[3] == "CLT ārsienu paneļi")
        self.assertEqual((clt[MAT_HEADER.index("Mērvienība")], clt[0]), ("m³", "clt:ext"))
        self.assertIn("116.700 m²", clt[MAT_HEADER.index("Alternatīvā vienība (nav cenota)")])

    def test_procurement_sheet_lists_every_row_unmerged_with_traceability(self):
        ws = self.wb["Iepirkumi"]
        header = [c.value for c in ws[1]]
        for col in ("Artikuls", "Specifikācija", "Mērvienība", "Neto", "Rezerve %", "Pasūtāmais", "Iepakojums", "Cena EUR/vienība", "Modulis",
                    "Ražošanas posms", "Statuss", "Rindas ID"):
            self.assertIn(col, header)
        data = [r for r in cells(ws)[1:] if r[header.index("Rindas ID")]]
        expected = [r for r in self.est.rows if r.status != ST_DUP and not r.group.startswith("Terases")]
        self.assertEqual(len(data), len(expected))
        screws = next(r for r in data if r[0] == "DEMO-SKR-6x80")
        self.assertEqual((screws[header.index("Pasūtāmais")], screws[header.index("Iepakojums")]), (800, 200))

    def test_labour_sheet_totals(self):
        ws = self.wb["Darba operācijas"]
        rows = [r for r in cells(ws)[1:] if r[0]]
        self.assertEqual(len(rows), 15)
        total = next(r for r in cells(ws) if r[2] == "Kopā")
        self.assertAlmostEqual(total[8], sum(r[8] for r in rows), 6)
        self.assertAlmostEqual(total[10], sum(r[10] for r in rows), 6)
        self.assertAlmostEqual(total[10], 13225.49, 2)
        self.assertAlmostEqual(total[8], 413.30, 2)

    def test_assumptions_sheet_lists_exclusions_and_notes(self):
        text = " ".join(str(v) for row in cells(self.wb["Pieņēmumi un neiekļautais"]) for v in row if v)
        for needle in ("Darbs, transports, montāža", "AD budžeta stadija", "Rezerve", "iepirkuma bruto/izgriezumiem", "Nav apstiprinātas rindas"):
            self.assertIn(needle, text)


class TestClientSheet(unittest.TestCase):
    def test_client_sheet_has_no_internal_costs(self):
        wb, _data, _est = load(demo_project())
        ws = wb["Klienta piedāvājums"]
        text = " ".join(str(v) for row in cells(ws) for v in row if v is not None)
        low = text.lower()
        for word in FORBIDDEN_IN_CLIENT:
            self.assertNotIn(word.lower(), low, word)
        numbers = [v for row in cells(ws) for v in row if isinstance(v, (int, float))]
        for internal in (74607.43, 47955.46, 13225.49, 413.30, 69080.95, 32.0, 11191.11):
            self.assertFalse(any(abs(n - internal) < 0.01 for n in numbers), internal)
        sell = find(ws, "Provizoriskā cena bez PVN")[1].value
        self.assertAlmostEqual(sell, 85798.54, 2)
        self.assertAlmostEqual(find(ws, "Summa ar PVN")[1].value, 103816.24, 2)
        for needle in ("PROVIZORISKS BUDŽETA PIEDĀVĀJUMS", "Nav gala piedāvājums", "DEMO", "NAV iekļauts"):
            self.assertIn(needle, text)
        self.assertNotIn("NEPILNS", text)

    def test_incomplete_budget_is_marked_and_price_not_invented(self):
        p = demo_project()
        p["pricing"]["method"] = None
        p["catalog"][0]["unit_price"] = None
        wb, _data, est = load(p)
        ws = wb["Klienta piedāvājums"]
        text = " ".join(str(v) for row in cells(ws) for v in row if v is not None)
        self.assertIn("NEPILNS", text)
        price = find(ws, "Provizoriskā cena bez PVN")[1]
        self.assertEqual(price.value, "nav ievadīts")                                    # nevis 0
        self.assertEqual(price.data_type, "s")
        summary = " ".join(str(v) for row in cells(wb["Kopsavilkums"]) for v in row if v)
        self.assertIn("NEPILNS:", summary)


class TestTextSafety(unittest.TestCase):
    def test_formula_like_text_is_stored_as_text_not_formula(self):
        p = demo_project()
        evil = "=HYPERLINK(\"http://x\",\"klik\")"
        p["name"] = "DEMO " + evil
        p["manual"].append({"id": "e1", "group": "Manuālās rindas", "material": evil, "qty": 1, "unit": "gab.", "waste_pct": 0, "article": "+SUM(1)",
                            "spec": "@cmd", "module": "-1+1", "stage": "=1+1", "approved": False})
        p["catalog"].append({"article": "=A1", "name": "x", "spec": "", "unit": "m", "unit_price": 1.0, "pack_size": None, "supplier": "",
                             "source": ""})
        data = build_workbook(p, estimate(p))
        wb = openpyxl.load_workbook(io.BytesIO(data))
        found = []
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    self.assertNotEqual(c.data_type, "f", (ws.title, c.coordinate, c.value))        # nevienā šūnā nav formulas
                    if isinstance(c.value, str) and c.value.startswith(("=", "+", "-", "@")):
                        found.append((ws.title, c.value))
        self.assertTrue(any(v == evil for _t, v in found))                                          # saturs saglabāts kā teksts
        ws = wb["Materiālu tāme"]
        row = next(r for r in ws.iter_rows() if r[3].value == evil)
        self.assertEqual((row[3].data_type, row[2].value, row[4].value), ("s", "+SUM(1)", "@cmd"))
        self.assertEqual(wb["Kopsavilkums"]["A1"].data_type, "s")

    def test_empty_project_exports_without_error_and_marks_incomplete(self):
        from src.building_estimate import empty_project
        p = empty_project()
        wb, _d, est = load(p)
        self.assertEqual(wb.sheetnames, SHEETS)
        text = " ".join(str(v) for row in cells(wb["Kopsavilkums"]) for v in row if v)
        self.assertIn("NEPILNS", text)
        self.assertEqual(find(wb["Klienta piedāvājums"], "Provizoriskā cena bez PVN")[1].value, "nav ievadīts")

    def test_same_article_different_specs_stay_separate_in_procurement(self):
        p = demo_project()
        for spec in ("6×80", "6×120"):
            p["manual"].append({"id": f"s-{spec}", "group": "Manuālās rindas", "material": "Skrūves", "article": "SKR", "spec": spec, "qty": 10,
                                "unit": "gab.", "waste_pct": 0, "approved": False})
        wb, _d, _e = load(p)
        ws = wb["Iepirkumi"]
        rows = [r for r in cells(ws) if r[2] == "Skrūves"]
        self.assertEqual(sorted(r[1] for r in rows), ["6×120", "6×80"])


if __name__ == "__main__":
    unittest.main()
