"""Issue #16 (PR #17 korekcija): Moneo vispārīgā pārskata imports (kolonnu burti), stundu pārskats, salīdzināšanas datu integritāte.

Tikai SINTĒTISKA struktūras kopija (tools/synthetic_ad_building.py): nekādi īsti dati, nosaukumi vai summas. Gaidāmās vērtības tiek rēķinātas testā.
"""
import copy
import io
import math
import unittest
from pathlib import Path

import openpyxl
from streamlit.testing.v1 import AppTest

from src.building_demo import demo_ad_project
from src.building_estimate import estimate
from src.control_import import (
    MAX_BYTES, parse_control_sheet, parse_hours_report, parse_moneo_report, detect_layout,
)
from src.forecast_compare import (
    add_version, compare_hours_by_operation, compare_to_actual, freeze_forecast, get_version,
)
from tools.synthetic_ad_building import (
    HOURS_OPS, MONEO_STAGES, build_control_xlsx, build_hours_xlsx, build_moneo_report_xlsx,
)

APP = str(Path(__file__).resolve().parent.parent / "app.py")
SLOPE = 24.0 * 2.5 / math.cos(math.radians(20))


def order(qty, w=10.0, pieces=False, pack=None):
    v = qty * (1 + w / 100)
    if pieces:
        v = math.ceil(round(v, 9))
    if pack:
        v = math.ceil(round(v / pack, 9)) * pack
    return v


def moneo_items():
    """Visas artikulu rindas no struktūras konstantēm (neatkarīgi no parsera)."""
    out = []
    for scode, sdesc, groups in MONEO_STAGES:
        for gcode, gname, items in groups:
            for art, desc, pq, pp, aq, ap in items:
                out.append({"stage": f"{scode} {sdesc}", "stage_code": scode, "group": f"{gcode} {gname}", "code": art, "desc": desc, "plan_qty": pq, "plan_price": pp,
                            "plan_sum": round(pq * pp, 2), "actual_qty": aq, "actual_price": ap, "actual_sum": round(aq * ap, 2)})
    return out


class MoneoBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = build_moneo_report_xlsx()
        cls.sheet = parse_moneo_report("m.xlsx", cls.data)
        cls.project = demo_ad_project()
        cls.est = estimate(cls.project)
        cls.snap = freeze_forecast(cls.project, cls.est, "AD v1")


class TestMoneoStructure(MoneoBase):
    def test_layout_is_detected_and_generic_sample_is_not_confused(self):
        self.assertEqual(detect_layout("m.xlsx", self.data), "moneo")
        self.assertEqual(detect_layout("k.xlsx", build_control_xlsx()), "generic")

    def test_no_errors_no_warnings_and_blank_rows_ignored(self):
        self.assertEqual(self.sheet.errors, [])
        self.assertEqual(self.sheet.warnings, [])
        self.assertEqual(self.sheet.layout_checks, [])
        self.assertFalse(self.sheet.fatal)

    def test_row_types_are_separated(self):
        types = [l.row_type for l in self.sheet.lines]
        self.assertEqual(types.count("item"), len(moneo_items()))
        self.assertEqual(types.count("stage_total"), 3)                                     # F=<bez koda> kontrolsummas
        self.assertEqual(types.count("stage_total_repeat"), 3)                              # J=Kopā atkārtotās
        self.assertEqual(types.count("stage_header"), 3)                                    # S01, S02, S01 (atkārtojas)
        self.assertEqual(types.count("project_header"), 1)
        self.assertEqual(types.count("group_total"), 5)
        self.assertEqual(self.sheet.project_heading, "PRJ-SINT Sintētisks projekts (DEMO)")

    def test_item_fields_come_from_the_documented_columns(self):
        exp = moneo_items()
        got = self.sheet.items
        for g, e in zip(got, exp):
            self.assertEqual((g.code, g.name, g.plan_qty, g.plan_price, g.plan_sum, g.actual_qty, g.actual_price, g.actual_sum, g.stage, g.group),
                             (e["code"], e["desc"], e["plan_qty"], e["plan_price"], e["plan_sum"], e["actual_qty"], e["actual_price"], e["actual_sum"], e["stage"], e["group"]))

    def test_units_unknown_codes_are_text_leading_zero_kept(self):
        self.assertTrue(all(l.unit is None for l in self.sheet.items))                       # mērvienību nav: netiek izdomāta
        zero = [l for l in self.sheet.items if l.code == "00123"]
        self.assertEqual(len(zero), 1)
        self.assertIsInstance(zero[0].code, str)

    def test_group_stage_and_repeat_totals_are_not_summed(self):
        exp = moneo_items()
        a_sum = round(sum(e["actual_sum"] for e in exp), 2)
        p_sum = round(sum(e["plan_sum"] for e in exp), 2)
        self.assertEqual(round(sum(l.actual_sum for l in self.sheet.items), 2), a_sum)
        self.assertEqual(round(sum(l.plan_sum for l in self.sheet.items), 2), p_sum)
        every = sum(l.actual_sum for l in self.sheet.lines if l.actual_sum is not None)
        self.assertGreater(every, 2.5 * a_sum)                                              # naivi summējot visu: artikuli + grupas + posmi + atkārtotas kopsummas

    def test_stage_control_sums_reconcile_with_items(self):
        stage = [r for r in self.sheet.reconciliation if r["type"] == "stage_total"]
        self.assertEqual(len(stage), 3)
        self.assertTrue(all(r["ok"] for r in self.sheet.reconciliation))
        first = stage[0]
        exp_first = round(sum(e["actual_sum"] for e in moneo_items()[:3]), 2)                # 1. posma bloks: CLT-100, CLT-140, LATA-50
        self.assertEqual(first["sum_actual"], exp_first)

    def test_repeated_stage_blocks_do_not_double_count(self):
        sums = {}
        for l in self.sheet.items:
            sums.setdefault(l.stage_code, 0.0)
            sums[l.stage_code] += l.actual_sum
        self.assertAlmostEqual(sums["S01"], 5136 + 1680 + 1015 + 696, 6)
        self.assertAlmostEqual(sums["S02"], 4547.5 + 1071 + 120 + 60, 6)

    def test_tampered_stage_total_is_flagged_but_items_unchanged(self):
        bad = parse_moneo_report("m.xlsx", build_moneo_report_xlsx(tamper_stage_total=True))
        self.assertEqual(len(bad.items), len(self.sheet.items))
        self.assertTrue(any(not r["ok"] for r in bad.reconciliation))
        self.assertTrue(any("kontrolsumma neatbilst artikulu rindu summai" in m for _n, m in bad.warnings))
        self.assertTrue(any("atkārtotā posma kopsumma" in m for _n, m in bad.warnings))

    def test_user_column_mapping_when_structure_differs(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.data))
        ws = wb.active
        ws.insert_cols(1, 1)                                                                # visa struktūra nobīdīta par vienu kolonnu pa labi
        buf = io.BytesIO()
        wb.save(buf)
        shifted = buf.getvalue()
        bad = parse_moneo_report("m.xlsx", shifted)
        self.assertTrue(bad.fatal)
        self.assertTrue(any("kolonnu kartējumu" in m for _n, m in bad.errors))
        shift = {"stage_code": "C", "stage_desc": "G", "group_code": "E", "group_name": "H", "code": "F", "desc": "I", "plan_qty": "J", "plan_price": "L",
                 "plan_sum": "O", "actual_qty": "R", "actual_price": "U", "actual_sum": "W", "group_plan_sum": "P", "group_actual_sum": "Y",
                 "stage_plan_sum": "Q", "stage_actual_sum": "AA", "total_label": "K"}
        ok = parse_moneo_report("m.xlsx", shifted, shift)
        self.assertEqual(len(ok.items), len(self.sheet.items))
        self.assertEqual([l.actual_sum for l in ok.items], [l.actual_sum for l in self.sheet.items])
        self.assertTrue(all(r["ok"] for r in ok.reconciliation))

    def test_header_block_mismatch_is_reported(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.data))
        ws = wb.active
        ws["S2"], ws["S3"] = "Budžets", "summa"
        buf = io.BytesIO()
        wb.save(buf)
        sheet = parse_moneo_report("m.xlsx", buf.getvalue())
        self.assertTrue(any(l == "S" for l, _m in sheet.layout_checks))
        self.assertTrue(any("virsrakstu bloks neatbilst" in m for _n, m in sheet.warnings))

    def test_bad_input_formulas_numbers_size_type(self):
        wb = openpyxl.load_workbook(io.BytesIO(self.data))
        ws = wb.active
        row = next(r for r in range(1, ws.max_row + 1) if ws[f"E{r}"].value == "DEMO-GKL-12")
        ws[f"V{row}"] = "=1+1"
        row2 = next(r for r in range(1, ws.max_row + 1) if ws[f"E{r}"].value == "DEMO-SKR-6x80")
        ws[f"I{row2}"] = "abc"
        buf = io.BytesIO()
        wb.save(buf)
        sheet = parse_moneo_report("m.xlsx", buf.getvalue())
        self.assertEqual(len(sheet.errors), 2)
        self.assertNotIn("DEMO-GKL-12", [l.code for l in sheet.items])
        self.assertTrue(parse_moneo_report("m.pdf", b"x").fatal)
        self.assertTrue(parse_moneo_report("m.xlsx", b"PK junk").fatal)
        self.assertTrue(parse_moneo_report("m.csv", b"x" * (MAX_BYTES + 1)).fatal)

    def test_sample_file_in_repo_matches_generator(self):
        base = Path(__file__).resolve().parent.parent / "samples" / "ad_building"
        a = parse_moneo_report("a.xlsx", (base / "moneo_parskats_sintetisks.xlsx").read_bytes())
        self.assertEqual([(l.code, l.actual_sum) for l in a.items], [(l.code, l.actual_sum) for l in self.sheet.items])
        h = parse_hours_report("h.xlsx", (base / "stundas_sintetiskas.xlsx").read_bytes())
        self.assertEqual(len(h.operations), len(HOURS_OPS))


class TestHoursReport(unittest.TestCase):
    def setUp(self):
        self.rep = parse_hours_report("h.xlsx", build_hours_xlsx())

    def test_two_row_header_operations_and_control_total(self):
        self.assertEqual(self.rep.errors, [])
        self.assertEqual([(o.name, o.actual, o.plan) for o in self.rep.operations], list(HOURS_OPS))
        self.assertNotIn("Kopā:", [o.name for o in self.rep.operations])                    # «Kopā:» ir kontrolsumma, nevis operācija
        self.assertEqual(self.rep.total_actual, sum(a for _n, a, _p in HOURS_OPS))
        self.assertEqual(self.rep.total_plan, sum(p for _n, _a, p in HOURS_OPS))
        self.assertTrue(self.rep.reconciliation["ok"])

    def test_repeated_operation_is_warned_and_blank_rows_ignored(self):
        self.assertTrue(any("atkārtotas operācijas" in m for _n, m in self.rep.warnings))
        self.assertEqual(len(self.rep.operations), 6)

    def test_control_total_mismatch_is_flagged_not_used(self):
        bad = parse_hours_report("h.xlsx", build_hours_xlsx(tamper_total=True))
        self.assertFalse(bad.reconciliation["ok"])
        self.assertEqual(len(bad.operations), 6)
        self.assertTrue(any("kontrolsumma neatbilst" in m for _n, m in bad.warnings))

    def test_columns_follow_second_header_row_not_position(self):
        wb = openpyxl.load_workbook(io.BytesIO(build_hours_xlsx()))
        ws = wb.active
        ws["B2"], ws["C2"] = "Plānots", "Reāli"                                              # kolonnas samainītas vietām
        for r in range(4, ws.max_row + 1):
            ws[f"B{r}"].value, ws[f"C{r}"].value = ws[f"C{r}"].value, ws[f"B{r}"].value
        buf = io.BytesIO()
        wb.save(buf)
        swapped = parse_hours_report("h.xlsx", buf.getvalue())
        self.assertEqual([(o.name, o.actual, o.plan) for o in swapped.operations], list(HOURS_OPS))
        self.assertTrue(swapped.reconciliation["ok"])

    def test_missing_headers_and_mapping(self):
        wb = openpyxl.Workbook()
        wb.active.append(["x", 1, 2])
        buf = io.BytesIO()
        wb.save(buf)
        self.assertTrue(parse_hours_report("h.xlsx", buf.getvalue()).fatal)
        wb = openpyxl.load_workbook(io.BytesIO(build_hours_xlsx()))
        ws = wb.active
        ws.insert_cols(1, 1)
        buf = io.BytesIO()
        wb.save(buf)
        self.assertTrue(parse_hours_report("h.xlsx", buf.getvalue()).fatal)
        ok = parse_hours_report("h.xlsx", buf.getvalue(), {"name": "B", "actual": "C", "plan": "D"})
        self.assertEqual(len(ok.operations), 6)

    def test_formula_and_bad_numbers(self):
        wb = openpyxl.load_workbook(io.BytesIO(build_hours_xlsx()))
        ws = wb.active
        ws["B4"] = "=1+1"
        ws["B5"] = "abc"
        buf = io.BytesIO()
        wb.save(buf)
        rep = parse_hours_report("h.xlsx", buf.getvalue())
        self.assertEqual(len(rep.errors), 2)
        self.assertEqual(len(rep.operations), 4)


class TestCompareIntegrity(MoneoBase):
    """Labojums: faktiskās rindas no vairākiem posmiem netiek salīdzinātas ar VISU prognozes artikula summu katra atsevišķi (dubultošana)."""

    def cmp(self, **kw):
        return compare_to_actual(self.snap, self.sheet, default_scope="materiāli", **kw)

    def line(self, cmp, code):
        return next(l for l in cmp.material_lines if l["code"] == code)

    def test_article_in_two_stages_is_aggregated_and_forecast_counted_once(self):
        c = self.cmp()
        clt = self.line(c, "DEMO-CLT-100")
        f_qty = order(95.1 * 0.1) + order(SLOPE * 0.1)
        self.assertAlmostEqual(clt["forecast_qty"], f_qty, 6)
        self.assertAlmostEqual(clt["forecast_sum"], f_qty * 520.0, 6)                        # NE 2 × prognoze
        self.assertAlmostEqual(clt["actual_sum"], 5136.0 + 4547.5, 6)                        # S01 + S02
        self.assertAlmostEqual(clt["diff_eur"], 5136.0 + 4547.5 - f_qty * 520.0, 6)
        self.assertEqual(clt["actual_rows"], 2)
        self.assertEqual([x["stage"] for x in clt["sources"]], ["S01 Karkasa ražošana", "S02 Apdare un montāža"])
        self.assertEqual(sum(1 for l in c.material_lines if l["code"] == "DEMO-CLT-100"), 1)  # viena salīdzinājuma rinda, nevis divas
        self.assertTrue(any("AGREGĒTAS" in i for i in clt["issues"]))

    def test_article_in_repeated_stage_block_is_aggregated(self):
        c = self.cmp()
        lata = self.line(c, "DEMO-LATA-50")
        self.assertAlmostEqual(lata["actual_sum"], 1015.0 + 696.0, 6)
        self.assertEqual(lata["actual_rows"], 2)
        exp_q = (order(95.1 * 1000 / 600) + order(95.1 * 1000 / 400) + order(95.1 * 1000 / 600) + order(27.6 * 1000 / 600)
                 + order((SLOPE - 2 * 0.78 * 1.4) * 1000 / 350) + order(SLOPE * 1000 / 350))
        self.assertAlmostEqual(lata["forecast_sum"], exp_q * 1.4, 6)

    def test_quantities_not_comparable_without_unit_but_sums_are(self):
        clt = self.line(self.cmp(), "DEMO-CLT-100")
        self.assertFalse(clt["qty_comparable"])
        self.assertIsNone(clt["actual_unit"])
        self.assertIsNone(clt["qty_diff"])
        self.assertTrue(any("nav mērvienības" in i for i in clt["issues"]))
        self.assertIsNotNone(clt["diff_eur"])

    def test_tiny_double_count_regression(self):
        snap = {"id": "x", "locked": True, "labour": [], "rows": [{"row_id": "r1", "group": "G", "article": "A-1", "material": "A", "spec": "", "unit": "m",
                                                                    "qty": 10.0, "order_qty": 10.0, "unit_price": 100.0, "cost": 1000.0, "scope": "materiāli",
                                                                    "stage": "", "module": "", "detail": "", "assumption": ""}]}
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Posms", "Artikuls", "Nosaukums", "Mērv.", "Faktiskā summa"])
        ws.append(["S1", "A-1", "A", "m", 500.0])
        ws.append(["S2", "A-1", "A", "m", 600.0])
        buf = io.BytesIO()
        wb.save(buf)
        sheet = parse_control_sheet("k.xlsx", buf.getvalue())
        cmp = compare_to_actual(snap, sheet, default_scope="materiāli")
        l = cmp.material_lines[0]
        self.assertEqual((l["forecast_sum"], l["actual_sum"], l["diff_eur"]), (1000.0, 1100.0, 100.0))          # nevis 1100 − 2000
        self.assertEqual(cmp.totals["materials_forecast"], 1000.0)
        self.assertEqual(cmp.totals["materials_diff"], 100.0)

    def test_stage_split_only_when_both_sides_have_compatible_stages(self):
        snap = {"id": "x", "locked": True, "labour": [], "rows": [
            {"row_id": "r1", "group": "G", "article": "A-1", "material": "A", "spec": "", "unit": "m", "qty": 1, "order_qty": 5.0, "unit_price": 100.0, "cost": 500.0,
             "scope": "materiāli", "stage": "S1 Karkasa", "module": "", "detail": "", "assumption": ""},
            {"row_id": "r2", "group": "G", "article": "A-1", "material": "A", "spec": "", "unit": "m", "qty": 1, "order_qty": 5.0, "unit_price": 100.0, "cost": 500.0,
             "scope": "materiāli", "stage": "S2 Apdare", "module": "", "detail": "", "assumption": ""}]}
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Posms", "Artikuls", "Nosaukums", "Mērv.", "Faktiskā summa"])
        ws.append(["S1 Karkasa", "A-1", "A", "m", 450.0])
        ws.append(["S2 Apdare", "A-1", "A", "m", 650.0])
        buf = io.BytesIO()
        wb.save(buf)
        cmp = compare_to_actual(snap, parse_control_sheet("k.xlsx", buf.getvalue()), default_scope="materiāli")
        l = cmp.material_lines[0]
        self.assertEqual((l["forecast_sum"], l["actual_sum"]), (1000.0, 1100.0))
        self.assertEqual([(x["stage"], x["forecast_sum"], x["actual_sum"], x["diff_eur"]) for x in l["by_stage"]],
                         [("S1 Karkasa", 500.0, 450.0, -50.0), ("S2 Apdare", 500.0, 650.0, 150.0)])
        snap["rows"][1]["stage"] = ""                                                         # viena prognozes rinda bez posma → posmu sadalījuma nav
        cmp2 = compare_to_actual(snap, parse_control_sheet("k.xlsx", buf.getvalue()), default_scope="materiāli")
        self.assertIsNone(cmp2.material_lines[0]["by_stage"])
        self.assertTrue(any("posmu piesaiste nav saderīga" in i for i in cmp2.material_lines[0]["issues"]))
        self.assertEqual(cmp2.material_lines[0]["diff_eur"], 100.0)

    def test_whole_scope_totals_include_unmatched_and_identity_holds(self):
        c = self.cmp()
        tot = c.scope_totals["materiāli"]
        items = moneo_items()
        actual_all = round(sum(e["actual_sum"] for e in items), 2)
        self.assertAlmostEqual(tot["actual_total"], actual_all, 6)
        priced = [r for r in self.snap["rows"] if r["scope"] == "materiāli" and r["cost"] is not None]
        self.assertAlmostEqual(tot["forecast_total"], sum(r["cost"] for r in priced), 6)
        self.assertEqual(tot["forecast_unpriced_rows"], 0)
        self.assertAlmostEqual(tot["matched_actual"] + tot["unmatched_actual"], tot["actual_total"], 6)          # nekas netiek zaudēts
        self.assertAlmostEqual(tot["matched_forecast"] + tot["unmatched_forecast"], tot["forecast_total"], 6)
        self.assertAlmostEqual(tot["unmatched_actual"], 60.0, 6)                                                  # «00123» nav prognozē
        self.assertAlmostEqual(tot["diff_total"], tot["actual_total"] - tot["forecast_total"], 6)
        self.assertLess(tot["coverage_forecast_pct"], 100.0)                                                      # lielākā daļa prognozes nav faktā
        self.assertGreater(tot["coverage_actual_pct"], 99.0)
        self.assertGreater(tot["abs_pct_total"], c.totals["materials_abs_pct"])                                   # visa tvēruma novirze ≠ sasaistīto rindu novirze

    def test_matched_vs_whole_scope_are_reported_separately(self):
        c = self.cmp()
        self.assertNotEqual(round(c.totals["materials_diff"], 2), round(c.scope_totals["materiāli"]["diff_total"], 2))
        self.assertEqual(c.totals["uncomparable_actual_sum"], 0.0)
        self.assertAlmostEqual(c.totals["all_actual_items_sum"], round(sum(e["actual_sum"] for e in moneo_items()), 2), 6)

    def test_uncomparable_scope_amount_is_reported_separately(self):
        c = compare_to_actual(self.snap, self.sheet)                                         # bez noklusējuma seguma
        self.assertEqual(c.material_lines, [])
        self.assertAlmostEqual(c.totals["uncomparable_actual_sum"], round(sum(e["actual_sum"] for e in moneo_items()), 2), 6)
        self.assertEqual(len(c.uncomparable), len(moneo_items()))

    def test_generic_sample_results_are_unchanged(self):
        sheet = parse_control_sheet("k.xlsx", build_control_xlsx())
        c = compare_to_actual(self.snap, sheet)
        self.assertAlmostEqual(c.totals["materials_diff"], 808.158, 3)
        self.assertAlmostEqual(c.totals["external_diff"], 350.0, 6)


class TestHoursComparison(MoneoBase):
    def setUp(self):
        self.rep = parse_hours_report("h.xlsx", build_hours_xlsx())
        self.cmp = compare_hours_by_operation(self.snap, self.rep)
        ext_net, int_net = 135.6 - 12.9, 20.61
        self.f = {"CLT ārsienu montāža un apstrāde": ext_net * 0.50, "Grīdas rāmja izgatavošana": 80 * 0.60, "CLT iekšsienu montāža": int_net * 0.40,
                  "Elektroinstalācija": 60.0}

    def line(self, name):
        return next(l for l in self.cmp.lines if l["name"] == name)

    def test_matched_operations_and_aggregated_repeat(self):
        self.assertAlmostEqual(self.line("CLT ārsienu montāža un apstrāde")["forecast_hours"], self.f["CLT ārsienu montāža un apstrāde"], 6)
        self.assertEqual(self.line("CLT ārsienu montāža un apstrāde")["actual_hours"], 70.0)
        elec = self.line("Elektroinstalācija")
        self.assertEqual(elec["actual_hours"], 62.0 + 4.0)                                    # atkārtotā operācija agregēta
        self.assertEqual(elec["forecast_hours"], 60.0)                                        # prognoze nav dubultota
        self.assertEqual(elec["diff_h"], 6.0)
        self.assertAlmostEqual(elec["abs_pct"], 6.0 / 66.0 * 100, 9)                          # pret faktu
        self.assertEqual(len(elec["sources"]), 2)

    def test_absolute_percent_and_difference(self):
        l = self.line("Grīdas rāmja izgatavošana")
        self.assertAlmostEqual(l["diff_h"], 50.0 - 48.0, 9)
        self.assertAlmostEqual(l["abs_pct"], abs(48.0 - 50.0) / 50.0 * 100, 9)
        self.assertEqual(l["sheet_plan_hours"], 48.0)

    def test_unmatched_both_sides_and_total_identities(self):
        self.assertEqual([u["name"] for u in self.cmp.unmatched_actual], ["Loģistika"])
        names = {u["name"] for u in self.cmp.unmatched_forecast}
        self.assertIn("Jumta paneļu un seguma montāža", names)
        self.assertNotIn("Elektroinstalācija", names)
        t = self.cmp.totals
        all_f = sum(x["hours"] for x in self.snap["labour"])
        self.assertAlmostEqual(t["all_forecast"], all_f, 6)
        self.assertAlmostEqual(t["all_actual"], 209.0, 9)
        self.assertAlmostEqual(t["matched_actual"] + t["unmatched_actual_hours"], t["all_actual"], 9)
        self.assertAlmostEqual(t["matched_forecast"] + t["unmatched_forecast_hours"], t["all_forecast"], 6)
        self.assertEqual(t["control_total_actual"], 209.0)
        self.assertLess(t["coverage_forecast_pct"], 100.0)
        self.assertNotAlmostEqual(t["matched_diff"], t["all_diff"], 1)                         # sasaistītais ≠ visa tvēruma starpība

    def test_user_mapping_links_differently_named_operation(self):
        cmp = compare_hours_by_operation(self.snap, self.rep, {"Loģistika": "Jumta paneļu un seguma montāža"})
        self.assertEqual(cmp.unmatched_actual, [])
        l = next(x for x in cmp.lines if x["name"] == "Jumta paneļu un seguma montāža")
        self.assertEqual(l["actual_hours"], 14.0)

    def test_unlocked_snapshot_refused(self):
        cmp = compare_hours_by_operation(dict(self.snap, locked=False), self.rep)
        self.assertEqual(cmp.lines, [])
        self.assertTrue(cmp.notes)


class TestUiMoneoFlow(unittest.TestCase):
    def test_moneo_and_hours_upload_flow(self):
        at = AppTest.from_file(APP, default_timeout=120).run()
        at.radio[0].set_value("Pilnas ēkas tāme").run()
        at.button(key="bp_demo_ad").click().run()
        at.button(key="bp_freeze_1").click().run()
        at.file_uploader(key="bp_ctrl_1").upload("moneo.xlsx", build_moneo_report_xlsx(), "application/octet-stream").run()
        self.assertFalse(at.exception, at.exception)
        self.assertFalse(any("kartējum" in e.value for e in at.error))
        self.assertTrue(any("Moneo pārskats" in c.value for c in at.caption))
        labels = {m.label: m.value for m in at.metric}
        self.assertIn("Materiāli (sasaistītie): starpība (fakts − prognoze)", labels)
        snap = at.session_state["bp_project"]["versions"][0]
        expected = compare_to_actual(snap, parse_moneo_report("m.xlsx", build_moneo_report_xlsx()), default_scope="materiāli").totals
        self.assertEqual(labels["Materiāli (sasaistītie): starpība (fakts − prognoze)"], f"{expected['materials_diff']:.2f} EUR")
        at.file_uploader(key="bp_hours_1").upload("h.xlsx", build_hours_xlsx(), "application/octet-stream").run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("Visa tvēruma" in m.value for m in at.markdown))

    def test_wrong_structure_asks_for_mapping(self):
        at = AppTest.from_file(APP, default_timeout=120).run()
        at.radio[0].set_value("Pilnas ēkas tāme").run()
        at.button(key="bp_demo_ad").click().run()
        at.button(key="bp_freeze_1").click().run()
        wb = openpyxl.load_workbook(io.BytesIO(build_moneo_report_xlsx()))
        wb.active.insert_cols(1, 1)
        buf = io.BytesIO()
        wb.save(buf)
        at.file_uploader(key="bp_ctrl_1").upload("moneo.xlsx", buf.getvalue(), "application/octet-stream").run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any("kolonnu kartējumu" in e.value or "neatbilst izkārtojumam" in e.value for e in at.error)
                        or any("Atpazīta" in c.value for c in at.caption))


if __name__ == "__main__":
    unittest.main()
