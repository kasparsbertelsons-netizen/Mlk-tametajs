"""Issue #14: cenu/artikulu kataloga imports (XLSX/CSV), šablons, priekšskatījuma salīdzinājums, piemērošana. Sintētiski dati."""
import io
import unittest

import openpyxl

from src.building_estimate import G_FASTEN, empty_project, estimate
from src.catalog_import import (
    MAX_BYTES, apply_catalog, catalog_template_csv, catalog_template_xlsx, diff_catalog, parse_catalog_file,
)

HEADER = ["Artikuls", "Nosaukums", "Specifikācija", "Mērvienība", "Vienības cena EUR bez PVN", "Iepakojums", "Piegādātājs"]


def xlsx(rows, header=HEADER, sheet="Katalogs"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def csv_bytes(text, enc="utf-8-sig"):
    return text.encode(enc)


class TestParseXlsx(unittest.TestCase):
    def test_valid_rows_and_text_article_with_leading_zeros(self):
        data = xlsx([["00123", "CLT 100", "spec", "m³", 480.5, "", "Piegādātājs A"], ["SKR-1", "Skrūve", "", "gab.", 0.12, 200, ""]])
        r = parse_catalog_file("k.xlsx", data)
        self.assertFalse(r.fatal)
        self.assertEqual(r.errors, [])
        self.assertEqual([x["article"] for x in r.rows], ["00123", "SKR-1"])
        self.assertIsInstance(r.rows[0]["article"], str)
        self.assertEqual((r.rows[0]["unit_price"], r.rows[0]["supplier"], r.rows[1]["pack_size"]), (480.5, "Piegādātājs A", 200.0))

    def test_missing_price_is_none_not_zero(self):
        r = parse_catalog_file("k.xlsx", xlsx([["A-1", "x", "", "m", None, "", ""]]))
        self.assertEqual(r.rows[0]["unit_price"], None)
        self.assertEqual(r.errors, [])

    def test_numeric_article_cell_warns_about_lost_zeros(self):
        r = parse_catalog_file("k.xlsx", xlsx([[123, "x", "", "gab.", 1.0, "", ""]]))
        self.assertEqual(r.rows[0]["article"], "123")
        self.assertTrue(any("sākuma nulles" in m for _n, m in r.warnings))

    def test_formula_cells_are_rejected_not_evaluated(self):
        r = parse_catalog_file("k.xlsx", xlsx([["A-1", "x", "", "gab.", "=1+1", "", ""], ["A-2", "=HYPERLINK(\"x\")", "", "gab.", 1.0, "", ""],
                                                ["A-3", "ok", "", "gab.", 2.0, "", ""]]))
        self.assertEqual([x["article"] for x in r.rows], ["A-3"])
        self.assertEqual(len([m for _n, m in r.errors if "formulu" in m]), 2)

    def test_text_starting_with_formula_symbol_is_kept_as_text_with_warning(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(HEADER)
        ws.append(["A-1", "x", "", "gab.", 1.0, "", ""])
        ws.cell(row=2, column=3).value = "@spec"
        ws.cell(row=2, column=3).data_type = "s"
        buf = io.BytesIO()
        wb.save(buf)
        r = parse_catalog_file("k.xlsx", buf.getvalue())
        self.assertEqual(r.rows[0]["spec"], "@spec")
        self.assertTrue(any("formulas simbolu" in m for _n, m in r.warnings))

    def test_errors_negative_price_bad_price_no_unit_no_article_duplicate(self):
        rows = [["A-1", "x", "", "gab.", -1, "", ""], ["A-2", "x", "", "gab.", "abc", "", ""], ["A-3", "x", "", "", 1.0, "", ""],
                ["", "x", "", "gab.", 1.0, "", ""], ["A-5", "x", "", "gab.", 1.0, "", ""], ["A-5", "y", "", "gab.", 2.0, "", ""],
                ["A-6", "x", "", "gab.", 1.0, "nederīgs", ""], ["A-7", "x", "", "gab.", 1.0, -5, ""]]
        r = parse_catalog_file("k.xlsx", xlsx(rows))
        self.assertEqual([x["article"] for x in r.rows], ["A-5"])
        text = " | ".join(m for _n, m in r.errors)
        for needle in ("negatīva", "nederīga vērtība", "nav mērvienības", "artikuls nav norādīts", "dublikāts artikuls", "iepakojums"):
            self.assertIn(needle, text)
        self.assertEqual(len(r.errors), 7)

    def test_zero_price_warns(self):
        r = parse_catalog_file("k.xlsx", xlsx([["A-1", "x", "", "gab.", 0, "", ""]]))
        self.assertEqual(r.rows[0]["unit_price"], 0.0)
        self.assertTrue(any("TUKŠA" in m for _n, m in r.warnings))

    def test_header_aliases_and_missing_required_columns(self):
        data = xlsx([["A-1", "gab.", "1,5"]], header=["Art.", "Vienība", "Cena"])
        r = parse_catalog_file("k.xlsx", data)
        self.assertEqual((r.rows[0]["article"], r.rows[0]["unit"], r.rows[0]["unit_price"]), ("A-1", "gab.", 1.5))
        r = parse_catalog_file("k.xlsx", xlsx([["A-1", "x"]], header=["Artikuls", "Nosaukums"]))
        self.assertTrue(r.fatal)
        self.assertIn("trūkst obligāto kolonnu", r.errors[0][1])

    def test_corrupt_unsupported_and_oversized_files(self):
        self.assertTrue(parse_catalog_file("k.xlsx", b"PK\x03\x04junk").fatal)
        self.assertTrue(parse_catalog_file("k.pdf", b"%PDF").fatal)
        self.assertTrue(parse_catalog_file("k.csv", b"x" * (MAX_BYTES + 1)).fatal)
        self.assertTrue(parse_catalog_file("k.csv", b"").fatal)

    def test_template_roundtrips_and_is_synthetic(self):
        r = parse_catalog_file("sablons.xlsx", catalog_template_xlsx())
        self.assertEqual(r.errors, [])
        self.assertEqual([x["article"] for x in r.rows], ["00123", "SKR-6x80", "LENTE-01"])
        self.assertIsNone(r.rows[2]["unit_price"])
        self.assertTrue(all("DEMO" in x["name"] for x in r.rows))
        wb = openpyxl.load_workbook(io.BytesIO(catalog_template_xlsx()))
        self.assertEqual(wb["Katalogs"]["A2"].value, "00123")
        self.assertEqual(wb["Katalogs"]["A2"].data_type, "s")
        c = parse_catalog_file("sablons.csv", catalog_template_csv().encode("utf-8"))
        self.assertEqual([x["article"] for x in c.rows], ["00123", "SKR-6x80", "LENTE-01"])


class TestParseCsv(unittest.TestCase):
    def test_semicolon_decimal_comma_and_bom_keeps_leading_zeros(self):
        r = parse_catalog_file("k.csv", csv_bytes("Artikuls;Mērvienība;Cena\n007;m;1,25\nA-8;gab.;\n"))
        self.assertEqual(r.errors, [])
        self.assertEqual([(x["article"], x["unit_price"]) for x in r.rows], [("007", 1.25), ("A-8", None)])

    def test_comma_delimiter_and_thousands_format(self):
        r = parse_catalog_file("k.csv", csv_bytes("Artikuls,Mērvienība,Cena\nA-1,m,\"1,234.50\"\n"))
        self.assertEqual(r.rows[0]["unit_price"], 1234.5)

    def test_cp1257_encoding(self):
        r = parse_catalog_file("k.csv", csv_bytes("Artikuls;Nosaukums;Mērvienība;Cena\nA-1;Ūdensvads žņaugs;gab.;2\n", "cp1257"))
        self.assertEqual(r.rows[0]["name"], "Ūdensvads žņaugs")

    def test_control_characters_stripped_and_long_text_rejected(self):
        r = parse_catalog_file("k.csv", csv_bytes("Artikuls;Nosaukums;Mērvienība;Cena\nA-1;ab\x01c;gab.;1\nA-2;" + "x" * 300 + ";gab.;1\n"))
        self.assertEqual(r.rows[0]["name"], "abc")
        self.assertEqual([x["article"] for x in r.rows], ["A-1"])
        self.assertTrue(any("garāks" in m for _n, m in r.errors))


class TestDiffAndApply(unittest.TestCase):
    def test_diff_categories_and_unit_conflicts(self):
        existing = [{"article": "A-1", "name": "x", "unit": "m", "unit_price": 1.0}, {"article": "A-2", "name": "y", "unit": "m", "unit_price": 2.0}]
        imported = [{"article": "A-1", "name": "x", "spec": "", "unit": "m", "unit_price": 1.0, "pack_size": None, "supplier": ""},
                    {"article": "A-2", "name": "y", "spec": "", "unit": "m", "unit_price": 2.5, "pack_size": None, "supplier": ""},
                    {"article": "A-3", "name": "z", "spec": "", "unit": "gab.", "unit_price": 3.0, "pack_size": None, "supplier": ""}]
        d = diff_catalog(existing, imported, {"A-1": {"m"}, "A-3": {"kompl."}, "A-9": {"m"}})
        self.assertEqual((d["new"], d["updated"], d["unchanged"]), (["A-3"], ["A-2"], ["A-1"]))
        self.assertEqual(d["unmatched"], ["A-2"])                           # neviena rinda nelieto
        self.assertEqual(d["unit_conflicts"], [("A-3", "gab.", ["kompl."])])
        self.assertEqual(d["unknown_in_file"], ["A-9"])

    def test_apply_merges_and_blank_does_not_erase_existing_price(self):
        p = empty_project()
        p["catalog"] = [{"article": "A-1", "name": "vecais", "spec": "", "unit": "m", "unit_price": 1.5, "pack_size": 10, "supplier": "S"}]
        apply_catalog(p, [{"article": "A-1", "name": "jaunais", "spec": "", "unit": "m", "unit_price": None, "pack_size": None, "supplier": ""},
                          {"article": "B-2", "name": "b", "spec": "s", "unit": "gab.", "unit_price": None, "pack_size": None, "supplier": ""}])
        by = {c["article"]: c for c in p["catalog"]}
        self.assertEqual((by["A-1"]["name"], by["A-1"]["unit_price"], by["A-1"]["pack_size"], by["A-1"]["supplier"]), ("jaunais", 1.5, 10, "S"))
        self.assertIsNone(by["B-2"]["unit_price"])                          # trūkstoša cena nav nulle
        self.assertEqual(len(p["catalog"]), 2)

    def test_unit_mismatch_rows_are_skipped_on_apply_and_existing_price_kept(self):
        p = empty_project()
        p["catalog"] = [{"article": "A-1", "name": "Lente", "spec": "", "unit": "m", "unit_price": 2.0, "pack_size": None, "supplier": ""}]
        p["recipes"] = [{"id": "r1", "group": G_FASTEN, "article": "A-1", "name": "Lente", "unit": "m", "driver": "direct", "qty": 10,
                         "waste_pct": 0, "approved": False, "enabled": True}]
        rows = [{"article": "A-1", "name": "Lente", "spec": "", "unit": "kompl.", "unit_price": 9.0, "pack_size": None, "supplier": ""},
                {"article": "A-2", "name": "Jauns", "spec": "", "unit": "gab.", "unit_price": 1.0, "pack_size": None, "supplier": ""}]
        used = {"A-1": {"m"}}
        skipped = apply_catalog(p, rows, used)
        self.assertEqual(skipped, [("A-1", "kompl.", ["m"])])
        by = {c["article"]: c for c in p["catalog"]}
        self.assertEqual((by["A-1"]["unit"], by["A-1"]["unit_price"]), ("m", 2.0))        # nemainīts: cena un vienība saglabāta
        self.assertIn("A-2", by)
        self.assertEqual(next(r for r in estimate(p).rows if r.material == "Lente").cost, 20.0)

    def test_imported_prices_drive_estimate_and_unit_mismatch_is_not_applied(self):
        p = empty_project()
        p["recipes"] = [{"id": "r1", "group": G_FASTEN, "article": "00123", "name": "Lente", "unit": "m", "driver": "direct", "qty": 10,
                         "waste_pct": 0, "approved": False, "enabled": True},
                        {"id": "r2", "group": G_FASTEN, "article": "00124", "name": "Skrūve", "unit": "gab.", "driver": "direct", "qty": 10,
                         "waste_pct": 0, "approved": False, "enabled": True}]
        parsed = parse_catalog_file("k.xlsx", xlsx([["00123", "Lente", "", "m", 2.0, "", ""], ["00124", "Skrūve", "", "kompl.", 5.0, "", ""]]))
        apply_catalog(p, parsed.rows)
        e = estimate(p)
        lente = next(r for r in e.rows if r.material == "Lente")
        screw = next(r for r in e.rows if r.material == "Skrūve")
        self.assertEqual((lente.unit_price, lente.cost), (2.0, 20.0))
        self.assertIsNone(screw.unit_price)
        self.assertTrue(any("cena netiek piemērota" in w for w in e.warnings))


if __name__ == "__main__":
    unittest.main()
