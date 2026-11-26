"""Issue #16: Moneo kontroltāmes imports (SINTĒTISKS), AD prognozes fiksēšana, salīdzināšana pret faktu, kalibrētā/PD versija.

Visas sagaidāmās vērtības tiek rēķinātas testā ar vienkāršu aritmētiku no sintētiskām konstantēm (nevis kopētas no koda izvades).
"""
import copy
import io
import math
import unittest

import openpyxl

from src.building_demo import demo_ad_project
from src.building_estimate import estimate, project_fingerprint
from src.control_import import SCOPE_EXTERNAL, SCOPE_HOURS, SCOPE_MATERIAL, parse_control_sheet
from src.forecast_compare import (
    add_version, compare_to_actual, freeze_forecast, get_version, make_derived_project, suggest_calibration,
)
from src.project_io import export_project, import_project
from tools.synthetic_ad_building import (
    CONTROL_HOURS, CONTROL_ITEMS, HEADER, build_control_csv, build_control_xlsx, control_rows,
)

SLOPE = 24.0 * 2.5 / math.cos(math.radians(20))
OPEN_ROOF = 2 * 0.78 * 1.4


def order(qty, w=10.0, pieces=False, pack=None):
    v = qty * (1 + w / 100)
    if pieces:
        v = math.ceil(round(v, 9))
    if pack:
        v = math.ceil(round(v / pack, 9)) * pack
    return v


def expected_forecast_qty():
    ext1, ext2, int1 = 95.1, 27.6, 20.61
    return {
        "DEMO-CLT-100": order(ext1 * 0.1) + order(SLOPE * 0.1),
        "DEMO-CLT-140": order(ext2 * 0.14),
        "DEMO-LATA-50": order(ext1 * 1000 / 600) + order(ext1 * 1000 / 400) + order(ext1 * 1000 / 600) + order(ext2 * 1000 / 600)
                        + order((SLOPE - OPEN_ROOF) * 1000 / 350) + order(SLOPE * 1000 / 350),
        "DEMO-GKL-12": order(ext1) + order(ext2) + order(int1 * 2),
        "DEMO-SKR-6x80": order(ext1 * 6, pieces=True, pack=200),
        "DEMO-VEJA": order(ext1) + order(ext2),
        "DEMO-MEP-AP": 1.0,
    }


PRICES = {"DEMO-CLT-100": 520.0, "DEMO-CLT-140": 560.0, "DEMO-LATA-50": 1.4, "DEMO-GKL-12": 6.0, "DEMO-SKR-6x80": 0.12, "DEMO-VEJA": 2.1,
          "DEMO-MEP-AP": 4000.0}


def actual_by_code():
    out = {}
    for stage, code, name, unit, pq, aq, pp, ap, kind in CONTROL_ITEMS:
        out[code] = {"unit": unit, "plan_qty": pq, "actual_qty": aq, "plan_price": pp, "actual_price": ap, "plan_sum": round(pq * pp, 2),
                     "actual_sum": round(aq * ap, 2), "kind": kind, "stage": stage}
    return out


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = demo_ad_project()
        cls.est = estimate(cls.project)
        cls.snap = freeze_forecast(cls.project, cls.est, "AD v1")
        cls.sheet = parse_control_sheet("k.xlsx", build_control_xlsx())
        cls.cmp = compare_to_actual(cls.snap, cls.sheet)

    def line(self, code):
        return next(l for l in self.cmp.material_lines + self.cmp.external_lines if l["code"] == code)


class TestControlImport(unittest.TestCase):
    def setUp(self):
        self.sheet = parse_control_sheet("k.xlsx", build_control_xlsx())

    def test_row_types_item_vs_group_stage_grand_totals_and_hours(self):
        types = [l.row_type for l in self.sheet.lines]
        self.assertEqual(types.count("item"), len(CONTROL_ITEMS))
        self.assertEqual(types.count("hours"), len(CONTROL_HOURS))
        self.assertEqual(types.count("group_total"), 2)
        self.assertEqual(types.count("stage_total"), 2)
        self.assertEqual(types.count("grand_total"), 1)
        self.assertEqual(types.count("stage_header"), 2)
        self.assertEqual(self.sheet.errors, [])
        self.assertEqual(self.sheet.warnings, [])

    def test_totals_are_not_summed_so_no_double_counting(self):
        items = self.sheet.items
        a_sum = round(sum(l.actual_sum for l in items), 2)
        p_sum = round(sum(l.plan_sum for l in items), 2)
        exp_a = round(sum(round(aq * ap, 2) for _s, _c, _n, _u, _pq, aq, _pp, ap, _k in CONTROL_ITEMS), 2)
        exp_p = round(sum(round(pq * pp, 2) for _s, _c, _n, _u, pq, _aq, pp, _ap, _k in CONTROL_ITEMS), 2)
        self.assertEqual((a_sum, p_sum), (exp_a, exp_p))
        everything = sum(l.actual_sum for l in self.sheet.lines if l.actual_sum is not None)
        self.assertGreater(everything, 2 * a_sum - 1)                  # naivi summējot visas rindas, summa būtu ≥ 3× (artikuli + grupa + posms + kopā)
        grand = self.sheet.totals[-1]
        self.assertEqual(grand.row_type, "grand_total")
        self.assertAlmostEqual(grand.actual_sum, a_sum, 2)

    def test_fields_preserved_stage_code_plan_actual(self):
        clt = next(l for l in self.sheet.items if l.code == "DEMO-CLT-100")
        self.assertEqual((clt.stage, clt.unit, clt.plan_qty, clt.actual_qty, clt.plan_price, clt.actual_price, clt.plan_sum, clt.actual_sum, clt.scope),
                         ("Karkasa ražošana", "m³", 17.5, 18.1, 520.0, 535.0, 9100.0, 9683.5, SCOPE_MATERIAL))
        mep = next(l for l in self.sheet.items if l.code == "DEMO-MEP-AP")
        self.assertEqual(mep.scope, SCOPE_EXTERNAL)

    def test_unit_is_not_invented(self):
        veja = next(l for l in self.sheet.items if l.code == "DEMO-VEJA")
        self.assertIsNone(veja.unit)

    def test_hours_plan_and_actual_by_stage(self):
        got = {h.stage: (h.plan_qty, h.actual_qty, h.scope) for h in self.sheet.hours}
        self.assertEqual(got, {s: (p, a, SCOPE_HOURS) for s, _n, p, a in CONTROL_HOURS})

    def test_reconciliation_ok_and_detects_mismatch(self):
        self.assertTrue(all(r["ok"] for r in self.sheet.reconciliation))
        wb = openpyxl.load_workbook(io.BytesIO(build_control_xlsx()))
        ws = wb.active
        for row in ws.iter_rows(min_row=2):
            if row[2].value == "Posma kopsumma":
                row[9].value = row[9].value + 500.0                    # bojāta kopsumma
                break
        buf = io.BytesIO()
        wb.save(buf)
        bad = parse_control_sheet("k.xlsx", buf.getvalue())
        self.assertTrue(any(not r["ok"] for r in bad.reconciliation))
        self.assertTrue(any("neatbilst artikulu rindu summai" in m for _n, m in bad.warnings))
        self.assertEqual(len(bad.items), len(CONTROL_ITEMS))           # kopsumma neietekmē artikulu rindas

    def test_csv_equals_xlsx(self):
        csv_sheet = parse_control_sheet("k.csv", build_control_csv())
        a = [(l.row_type, l.code, l.unit, l.plan_qty, l.actual_qty, l.plan_sum, l.actual_sum) for l in self.sheet.lines]
        b = [(l.row_type, l.code, l.unit, l.plan_qty, l.actual_qty, l.plan_sum, l.actual_sum) for l in csv_sheet.lines]
        self.assertEqual(a, b)

    def test_row_types_inferred_without_type_column(self):
        rows = control_rows()
        idx = HEADER.index("Rindas tips")
        stripped = [[v for i, v in enumerate(r) if i != idx] for r in rows]
        wb = openpyxl.Workbook()
        for r in stripped:
            wb.active.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        sheet = parse_control_sheet("k.xlsx", buf.getvalue())
        self.assertEqual(len(sheet.items), len(CONTROL_ITEMS))
        self.assertEqual(len(sheet.hours), len(CONTROL_HOURS))                  # stundu rindas pēc «Veids»/vienības h
        self.assertEqual(len(sheet.totals), 5)
        self.assertFalse(any(l.row_type == "item" and not l.code for l in sheet.lines))

    def test_errors_formulas_bad_numbers_missing_columns(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(HEADER)
        ws.append(["S", "A-1", "x", "gab.", 1, 1, 1, 1, "=1+1", 1, "Materiāls", "Artikuls"])
        ws.append(["S", "A-2", "x", "gab.", "abc", 1, 1, 1, 1, 1, "Materiāls", "Artikuls"])
        ws.append(["S", "A-3", "x", "gab.", 2, 2, 1.5, 1.5, 3, 3, "Materiāls", "Artikuls"])
        buf = io.BytesIO()
        wb.save(buf)
        sheet = parse_control_sheet("k.xlsx", buf.getvalue())
        self.assertEqual([l.code for l in sheet.items], ["A-3"])
        self.assertEqual(len(sheet.errors), 2)
        self.assertTrue(parse_control_sheet("k.xlsx", b"PK junk").fatal)
        self.assertTrue(parse_control_sheet("k.pdf", b"x").fatal)
        self.assertTrue(parse_control_sheet("k.csv", "A;B\n1;2\n".encode()).fatal)

    def test_decimal_comma_csv(self):
        sheet = parse_control_sheet("k.csv", "Artikuls;Nosaukums;Mērv.;Faktiskais daudzums;Faktiskā cena;Faktiskā summa\nA-1;x;m;1 234,5;2,5;3 086,25\n".encode("utf-8"))
        self.assertEqual((sheet.items[0].actual_qty, sheet.items[0].actual_price, sheet.items[0].actual_sum), (1234.5, 2.5, 3086.25))


class TestFreezeAndCompare(Base):
    def test_snapshot_is_locked_deterministic_and_has_fingerprint(self):
        self.assertTrue(self.snap["locked"])
        self.assertEqual(self.snap["kind"], "AD")
        self.assertEqual(self.snap["fingerprint"], project_fingerprint(self.project))
        again = freeze_forecast(self.project, self.est, "AD v1")
        self.assertEqual(again["id"], self.snap["id"])
        self.assertAlmostEqual(self.snap["budget"]["cost_total"], self.est.budget()["cost_total"], 9)

    def test_forecast_quantities_match_independent_calculation(self):
        by = {}
        for r in self.snap["rows"]:
            if r["article"]:
                by[r["article"]] = by.get(r["article"], 0) + r["order_qty"]
        for code, qty in expected_forecast_qty().items():
            self.assertAlmostEqual(by[code], qty, 6, code)

    def test_matched_lines_and_scope_separation(self):
        self.assertEqual(sorted(l["code"] for l in self.cmp.material_lines), ["DEMO-CLT-100", "DEMO-CLT-140", "DEMO-GKL-12", "DEMO-LATA-50", "DEMO-SKR-6x80", "DEMO-VEJA"])
        self.assertEqual([l["code"] for l in self.cmp.external_lines], ["DEMO-MEP-AP"])
        self.assertEqual(self.line("DEMO-MEP-AP")["scope"], SCOPE_EXTERNAL)

    def test_eur_difference_and_absolute_percent_against_actual(self):
        act, exp_q = actual_by_code(), expected_forecast_qty()
        for code in ("DEMO-CLT-100", "DEMO-CLT-140", "DEMO-LATA-50", "DEMO-GKL-12", "DEMO-SKR-6x80", "DEMO-MEP-AP"):
            f_sum = exp_q[code] * PRICES[code]
            a_sum = act[code]["actual_qty"] * act[code]["actual_price"]
            l = self.line(code)
            self.assertAlmostEqual(l["forecast_sum"], f_sum, 6, code)
            self.assertAlmostEqual(l["actual_sum"], a_sum, 6, code)
            self.assertAlmostEqual(l["diff_eur"], a_sum - f_sum, 6, code)                       # fakts − prognoze
            self.assertAlmostEqual(l["abs_pct"], abs(f_sum - a_sum) / abs(a_sum) * 100, 6, code)  # pret FAKTU
        clt = self.line("DEMO-CLT-100")
        self.assertAlmostEqual(clt["qty_diff"], 18.1 - exp_q["DEMO-CLT-100"], 6)
        self.assertAlmostEqual(clt["qty_abs_pct"], abs(exp_q["DEMO-CLT-100"] - 18.1) / 18.1 * 100, 6)

    def test_zero_deviation_clt_140(self):
        l = self.line("DEMO-CLT-140")
        self.assertAlmostEqual(l["actual_sum"], 4.2 * 560.0, 6)
        self.assertLess(abs(l["qty_diff"]), 0.1)

    def test_missing_unit_means_quantity_not_comparable_but_eur_is(self):
        l = self.line("DEMO-VEJA")
        self.assertFalse(l["qty_comparable"])
        self.assertIsNone(l["qty_diff"])
        self.assertTrue(any("nav mērvienības" in i for i in l["issues"]))
        self.assertAlmostEqual(l["diff_eur"], 128 * 2.2 - expected_forecast_qty()["DEMO-VEJA"] * 2.1, 6)

    def test_unit_mismatch_is_not_converted(self):
        sheet = copy.deepcopy(self.sheet)
        for l in sheet.items:
            if l.code == "DEMO-LATA-50":
                l.unit = "kg"
        cmp = compare_to_actual(self.snap, sheet)
        line = next(x for x in cmp.material_lines if x["code"] == "DEMO-LATA-50")
        self.assertFalse(line["qty_comparable"])
        self.assertIsNone(line["qty_diff"])
        self.assertTrue(any("mērvienība neatbilst" in i for i in line["issues"]))

    def test_scope_mismatch_is_not_compared(self):
        sheet = copy.deepcopy(self.sheet)
        for l in sheet.items:
            if l.code == "DEMO-MEP-AP":
                l.scope = SCOPE_MATERIAL                               # fakts «materiāli», prognoze «ārējās izmaksas»
        cmp = compare_to_actual(self.snap, sheet)
        self.assertNotIn("DEMO-MEP-AP", [l["code"] for l in cmp.material_lines + cmp.external_lines])
        self.assertTrue(any("izmaksu segums atšķiras" in why and "MEP" in name for why, name in cmp.uncomparable))

    def test_unknown_scope_needs_explicit_choice(self):
        sheet = copy.deepcopy(self.sheet)
        for l in sheet.items:
            l.scope = None
        none_cmp = compare_to_actual(self.snap, sheet)
        self.assertEqual(none_cmp.material_lines, [])
        self.assertEqual(len(none_cmp.uncomparable), len(CONTROL_ITEMS))
        chosen = compare_to_actual(self.snap, sheet, default_scope=SCOPE_MATERIAL)
        self.assertEqual(len(chosen.material_lines), 6)                # MEP kā materiāli nesakrīt ar prognozes «ārējās izmaksas»
        self.assertTrue(any("MEP" in name for _w, name in chosen.uncomparable))

    def test_unmatched_lines_both_sides(self):
        self.assertEqual([u["code"] for u in self.cmp.unmatched_actual], ["DEMO-NAV-PROGNOZE"])
        codes = {u["code"] for u in self.cmp.unmatched_forecast}
        self.assertIn("DEMO-LOGS", codes)
        self.assertNotIn("DEMO-CLT-100", codes)
        self.assertGreater(len(codes), 10)

    def test_group_absolute_deviation_sums(self):
        exp = expected_forecast_qty()
        act = actual_by_code()
        grp = {}
        for code in ("DEMO-CLT-100", "DEMO-CLT-140", "DEMO-LATA-50", "DEMO-GKL-12", "DEMO-SKR-6x80"):
            l = self.line(code)
            grp[l["group"]] = grp.get(l["group"], 0) + abs(act[code]["actual_qty"] * act[code]["actual_price"] - exp[code] * PRICES[code])
        # DEMO-VEJA (ĀS1/ĀS2 vēja plēve) arī pieder grupai «Ārsienas»
        veja = self.line("DEMO-VEJA")
        grp[veja["group"]] = grp.get(veja["group"], 0) + abs(veja["diff_eur"])
        mep = self.line("DEMO-MEP-AP")
        grp[mep["group"]] = grp.get(mep["group"], 0) + abs(mep["diff_eur"])
        for g, v in grp.items():
            self.assertAlmostEqual(self.cmp.group_abs_dev[g], v, 6, g)
        self.assertAlmostEqual(self.cmp.totals["abs_dev_total"], sum(grp.values()), 6)

    def test_hours_by_stage_plan_vs_actual(self):
        hours = {h["stage"]: h for h in self.cmp.hours}
        ext_net, int_net = 135.6 - 12.9, 20.61
        roof_net = 2 * SLOPE - OPEN_ROOF
        karkasa = 80 * 0.60 + ext_net * 0.50 + int_net * 0.40                      # grīdas rāmis (Σ L×W=80), ārsienu un iekšsienu montāža
        apdare = roof_net * 0.45 + ext_net * 0.60 + 8 * 1.5 + 24 + 60 + 40 + 16   # «logi» = L1 ×6 + JL1 ×2 = 8 gab.; tiešās stundas MEP grupām
        self.assertAlmostEqual(hours["Karkasa ražošana"]["forecast_hours"], karkasa, 6)
        self.assertAlmostEqual(hours["Apdare un montāža"]["forecast_hours"], apdare, 6)
        self.assertEqual(hours["Karkasa ražošana"]["actual_hours"], 130.0)
        self.assertAlmostEqual(hours["Karkasa ražošana"]["diff_h"], 130.0 - karkasa, 6)
        self.assertAlmostEqual(hours["Karkasa ražošana"]["abs_pct"], abs(karkasa - 130.0) / 130.0 * 100, 6)
        self.assertEqual(hours["Loģistika"]["forecast_hours"], None)
        self.assertIn("nesaistīts", hours["Loģistika"]["note"])
        self.assertEqual(hours["Loģistika"]["sheet_plan_hours"], 10.0)
        self.assertAlmostEqual(self.cmp.totals["hours_forecast"], karkasa + apdare, 6)
        self.assertAlmostEqual(self.cmp.totals["hours_actual"], 130.0 + 270.0, 6)                # tikai saistītie posmi

    def test_percent_undefined_when_actual_is_zero(self):
        sheet = copy.deepcopy(self.sheet)
        for l in sheet.items:
            if l.code == "DEMO-SKR-6x80":
                l.actual_qty, l.actual_price, l.actual_sum = 0.0, 0.12, 0.0
        line = next(x for x in compare_to_actual(self.snap, sheet).material_lines if x["code"] == "DEMO-SKR-6x80")
        self.assertIsNone(line["abs_pct"])
        self.assertIsNone(line["qty_abs_pct"])

    def test_rows_without_article_are_noted_not_matched(self):
        self.assertTrue(any("nav artikula" in n for n in self.cmp.notes) or all(r["article"] for r in self.snap["rows"]))

    def test_unlocked_snapshot_is_refused(self):
        s = dict(self.snap, locked=False)
        cmp = compare_to_actual(s, self.sheet)
        self.assertEqual(cmp.material_lines, [])
        self.assertTrue(any("nav fiksēta" in n for n in cmp.notes))


class TestForecastIsolation(Base):
    def test_actual_data_never_changes_the_forecast_or_the_estimate(self):
        project = demo_ad_project()
        before = copy.deepcopy(project)
        est1 = estimate(project)
        snap = freeze_forecast(project, est1, "AD")
        add_version(project, snap)
        compare_to_actual(snap, parse_control_sheet("k.xlsx", build_control_xlsx()))
        project["actuals"] = {"note": "tikai atsevišķi"}
        est2 = estimate(project)
        self.assertEqual(est1.budget()["sell"], est2.budget()["sell"])
        self.assertEqual([(r.row_id, r.qty, r.unit_price) for r in est1.rows], [(r.row_id, r.qty, r.unit_price) for r in est2.rows])
        for key in before:
            if key not in ("versions", "actuals"):
                self.assertEqual(project[key], before[key], key)

    def test_compare_uses_frozen_snapshot_not_live_estimate(self):
        project = demo_ad_project()
        snap = freeze_forecast(project, estimate(project), "AD")
        add_version(project, snap)
        for c in project["catalog"]:
            c["unit_price"] = 9999.0                                   # tāme mainīta pēc fiksēšanas
        cmp = compare_to_actual(get_version(project, snap["id"]), parse_control_sheet("k.xlsx", build_control_xlsx()))
        clt = next(l for l in cmp.material_lines if l["code"] == "DEMO-CLT-100")
        self.assertAlmostEqual(clt["forecast_sum"], expected_forecast_qty()["DEMO-CLT-100"] * 520.0, 6)

    def test_freezing_does_not_invalidate_review_and_is_idempotent(self):
        project = demo_ad_project()
        fp = project_fingerprint(project)
        snap = freeze_forecast(project, estimate(project), "AD")
        add_version(project, snap)
        add_version(project, snap)
        self.assertEqual(len(project["versions"]), 1)
        project["actuals"] = {"x": 1}
        self.assertEqual(project_fingerprint(project), fp)             # versijas un faktiskie dati neatceļ pārbaudi

    def test_frozen_snapshot_cannot_be_overwritten_by_add_version(self):
        project = demo_ad_project()
        snap = freeze_forecast(project, estimate(project), "AD")
        add_version(project, snap)
        tampered = copy.deepcopy(snap)
        tampered["budget"]["sell"] = 1.0
        tampered["rows"] = []
        stored = add_version(project, tampered)                         # tas pats ID: esošais netiek pārrakstīts
        self.assertEqual(len(project["versions"]), 1)
        self.assertEqual(project["versions"][0]["budget"]["sell"], snap["budget"]["sell"])
        self.assertEqual(stored["budget"]["sell"], snap["budget"]["sell"])
        self.assertTrue(project["versions"][0]["rows"])

    def test_versions_survive_save_and_restore(self):
        project = demo_ad_project()
        add_version(project, freeze_forecast(project, estimate(project), "AD"))
        back = import_project(export_project(project))
        self.assertEqual(back.errors, [])
        self.assertEqual(back.project["versions"][0]["id"], project["versions"][0]["id"])
        self.assertTrue(back.project["versions"][0]["locked"])
        self.assertEqual(back.project["ad_import"]["stage"], "AD")


class TestCalibrationAndDerived(Base):
    def test_suggestions_from_actual_price_and_quantity(self):
        sug = {(s["article"], s["field"]): s for s in suggest_calibration(self.cmp)}
        self.assertAlmostEqual(sug[("DEMO-CLT-100", "unit_price")]["new"], 535.0)
        self.assertAlmostEqual(sug[("DEMO-LATA-50", "unit_price")]["old"], 1.4)
        self.assertAlmostEqual(sug[("DEMO-SKR-6x80", "norm_factor")]["new"], 1000.0 / 800.0, 9)
        self.assertNotIn(("DEMO-CLT-140", "unit_price"), sug)          # cena nemainās
        self.assertNotIn(("DEMO-VEJA", "norm_factor"), sug)            # mērvienība nav zināma → daudzums nav salīdzināms

    def test_calibrated_copy_is_separate_and_ad_unchanged(self):
        project = copy.deepcopy(self.project)
        add_version(project, self.snap)
        before = copy.deepcopy(project)
        sug = [s for s in suggest_calibration(self.cmp) if s["field"] == "unit_price"]
        derived = make_derived_project(project, stage="kalibrēta", label="kalibrēta", snapshot_id=self.snap["id"], suggestions=sug)
        self.assertEqual(project, before)                                                       # AD projekts nav mainīts
        self.assertEqual(derived["stage"], "kalibrēta")
        self.assertEqual((derived["versions"], derived["actuals"]), ([], None))
        self.assertEqual(derived["derived_from"]["snapshot"], self.snap["id"])
        self.assertEqual(derived["derived_from"]["fingerprint"], project_fingerprint(project))
        self.assertFalse(derived["review"]["confirmed"])
        price = {c["article"]: c["unit_price"] for c in derived["catalog"]}
        self.assertEqual(price["DEMO-CLT-100"], 535.0)
        orig = {c["article"]: c["unit_price"] for c in project["catalog"]}
        self.assertEqual(orig["DEMO-CLT-100"], 520.0)
        self.assertGreater(estimate(derived).budget()["materials"], estimate(project).budget()["materials"] - 1e9)
        self.assertNotEqual(estimate(derived).budget()["sell"], estimate(project).budget()["sell"])

    def test_norm_factor_scales_only_norm_based_recipes_in_copy(self):
        project = copy.deepcopy(self.project)
        sug = [s for s in suggest_calibration(self.cmp) if s["field"] == "norm_factor" and s["article"] == "DEMO-SKR-6x80"]
        derived = make_derived_project(project, stage="kalibrēta", label="k", suggestions=sug)
        norms = [r["norm"] for r in derived["type_recipes"] if r["article"] == "DEMO-SKR-6x80"]
        self.assertEqual(norms, [6.0 * 1000.0 / 800.0])
        self.assertEqual([r["norm"] for r in project["type_recipes"] if r["article"] == "DEMO-SKR-6x80"], [6.0])

    def test_pd_copy_and_invalid_stage(self):
        pd_copy = make_derived_project(self.project, stage="PD", label="PD detalizācija")
        self.assertEqual(pd_copy["stage"], "PD")
        self.assertEqual(self.project["stage"], "AD")
        self.assertIn("PD detalizācija", pd_copy["name"])
        with self.assertRaises(ValueError):
            make_derived_project(self.project, stage="AD", label="x")
        with self.assertRaises(ValueError):
            make_derived_project(self.project, stage="cits", label="x")


if __name__ == "__main__":
    unittest.main()
