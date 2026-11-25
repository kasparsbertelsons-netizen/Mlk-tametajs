"""Issue #14: darba pašizmaksa, budžeta formulas (uzcenojums ≠ marža), stabila rindas identitāte, rezerves pēc grupām, DEMO kontrolsummas.

Visas sagaidāmās summas tiek rēķinātas TESTĀ ar vienkāršu aritmētiku (nevis kopētas no koda izvades). Sintētiski dati.
"""
import math
import unittest

from src.building_demo import DEMO_CATALOG, demo_project
from src.building_estimate import (
    G_ELEC, G_EQUIP, G_EXT, G_FASTEN, G_FLOOR, G_INT, G_OPEN, G_SANIT, G_VENT, ST_MISSING, ST_NO_RATE, empty_project, ensure_ids,
    estimate, set_price,
)

ROOF = 120 / math.cos(math.radians(20))
EXT, INT = 116.7, 20.61


def order(qty, waste, pieces=False, pack=None):
    out = qty * (1 + waste / 100)
    if pieces:
        out = math.ceil(round(out, 9))
    if pack:
        out = math.ceil(round(out / pack, 9)) * pack
    return out


def price(article):
    return DEMO_CATALOG[article][2]


def expected_demo():
    """Neatkarīgi rēķināta DEMO ēka: (materiāli, darba stundas, darbs EUR, tiešās, pašizmaksa, pārdošanas cena, PVN, kopā)."""
    mat = 0.0
    mat += order(2.37888, 10) * 420 + order(1.54128, 10) * 420                                   # grīdas rāmis A, B
    free = (12000 - 400 - 16 * 45 - 2 * 150) * 3.6 / 1000 + (8000 - 400 - 11 * 45) * 3.6 / 1000    # PIR m²
    mat += order(free, 10) * 18.5
    mat += 6 * price("DEMO-LOGS") + 1 * price("DEMO-DURV-ARD") + 3 * price("DEMO-DURV-IEK")       # logi/durvis, 0% rezerve
    mat += order(EXT * .1, 10) * price("DEMO-CLT-100") + order(INT, 10) * price("DEMO-CLT-80") + order(ROOF * .12, 10) * price("DEMO-CLT-120")
    mat += order(72, 10) * price("DEMO-GRIDA-APD")
    mat += order(EXT, 10) * (price("DEMO-FAS-APD") + price("DEMO-VEJA") + price("DEMO-IEKS-APD"))
    mat += order(EXT * 1000 / 600, 10) * price("DEMO-FAS-LAT")
    mat += order(EXT * .150, 10) * price("DEMO-SILT-EXT") + order(EXT * .050, 10) * price("DEMO-INSTAL")
    mat += order(INT * 2, 10) * price("DEMO-INT-APD")
    mat += order(ROOF * .2, 10) * price("DEMO-SILT-JUMTS") + order(ROOF, 10) * (price("DEMO-MEMBR") + price("DEMO-SEGUMS"))
    mat += order(ROOF * 1000 / 350, 10) * price("DEMO-J-LAT") + order(72, 10) * price("DEMO-GRIESTI")
    mat += 12 * price("DEMO-TERASE") + 1 * price("DEMO-HIDRO")
    mat += order(EXT * 6, 10, pieces=True, pack=200) * price("DEMO-SKR-6x80")                    # 700,2 → 771 → 800 gab.
    mat += order(48 * 3, 10) * price("DEMO-LENTE") + order(80, 10, pieces=True) * price("DEMO-LENSKAVA")
    mat += order(36, 10) * price("DEMO-VENT-D125") + order(8, 10, pieces=True) * price("DEMO-RESTE")
    mat += order(72 * 2.5, 10) * price("DEMO-KABELIS") + order(42, 10, pieces=True) * price("DEMO-SLEDZI")
    mat += order(40, 10) * price("DEMO-UDENS") + order(18, 10) * price("DEMO-KANAL")
    mat += 1 * price("DEMO-SANIT") + 1 * price("DEMO-REKUP")                                     # 0% rezerve (sanitārtehnika, iekārtas)
    hours = [80 * .6, EXT * .5, EXT * .3, INT * .4, INT * 2 * .35, ROOF * .45, 6 * 1.5, 4 * 2.0, 72 * .25, 48 * .1, 24, 60, 40, 16, 12]
    h = sum(hours)
    labour = h * 32.0
    other = 650 + 1850 + 5400
    direct = mat + labour + other
    cost = direct * 1.08
    sell = cost * 1.15
    return mat, h, labour, direct, cost, sell, sell * .21, sell * 1.21


class TestDemoFullBudget(unittest.TestCase):
    def setUp(self):
        self.p = demo_project()
        self.e = estimate(self.p)
        self.b = self.e.budget()

    def test_demo_is_fully_priced_and_complete(self):
        self.assertEqual(self.e.errors, [])
        self.assertEqual(self.b["unpriced_rows"], 0)
        self.assertEqual(self.b["labour_missing"], 0)
        self.assertEqual(self.b["reasons"], [])
        self.assertFalse(self.b["incomplete"])
        self.assertEqual(self.b["priced_rows"], len([r for r in self.e.rows if r.qty is not None]))

    def test_expected_totals_independently_calculated(self):
        mat, h, labour, direct, cost, sell, vat, incl = expected_demo()
        self.assertAlmostEqual(self.b["materials"], mat, 6)
        self.assertAlmostEqual(self.b["labour_hours"], h, 9)
        self.assertAlmostEqual(self.b["labour_cost"], labour, 6)
        self.assertAlmostEqual(self.b["direct"], direct, 6)
        self.assertAlmostEqual(self.b["overhead"], direct * 0.08, 6)
        self.assertAlmostEqual(self.b["cost_total"], cost, 6)
        self.assertAlmostEqual(self.b["sell"], sell, 6)
        self.assertAlmostEqual(self.b["vat"], vat, 6)
        self.assertAlmostEqual(self.b["total_incl"], incl, 6)
        self.assertAlmostEqual(self.b["profit"], sell - cost, 6)

    def test_published_expected_figures(self):
        # skaitļi, kas norādīti PR/Issue atskaitē (EUR, DEMO)
        self.assertEqual(round(self.b["materials"], 2), 47955.46)
        self.assertEqual(round(self.b["labour_hours"], 2), 413.30)
        self.assertEqual(round(self.b["labour_cost"], 2), 13225.49)
        self.assertEqual(round(self.b["cost_total"], 2), 74607.43)
        self.assertEqual(round(self.b["sell"], 2), 85798.54)
        self.assertEqual(round(self.b["total_incl"], 2), 103816.24)

    def test_markup_and_margin_are_different_formulas(self):
        cost = self.b["cost_total"]
        self.p["pricing"].update(method="markup", markup_pct=20.0)
        self.assertAlmostEqual(estimate(self.p).budget()["sell"], cost * 1.2, 6)
        self.p["pricing"].update(method="margin", margin_pct=20.0)
        sell = estimate(self.p).budget()["sell"]
        self.assertAlmostEqual(sell, cost / 0.8, 6)
        self.assertAlmostEqual((sell - cost) / sell, 0.20, 9)            # marža ir daļa no CENAS
        self.assertNotAlmostEqual(sell, cost * 1.2, 2)

    def test_margin_100_is_rejected_and_no_method_means_no_price(self):
        self.p["pricing"].update(method="margin", margin_pct=100.0)
        e = estimate(self.p)
        self.assertTrue(any("margin_pct" in x for x in e.errors))
        self.assertIsNone(e.budget()["sell"])
        self.p["pricing"].update(method=None)
        b = estimate(self.p).budget()
        self.assertIsNone(b["sell"])
        self.assertTrue(any("nav ievadīta — pārdošanas cena nav aprēķināta" in r for r in b["reasons"]))

    def test_vat_optional_and_requires_rate(self):
        self.p["pricing"]["vat_enabled"] = False
        b = estimate(self.p).budget()
        self.assertIsNone(b["vat"])
        self.assertIsNone(b["total_incl"])
        self.p["pricing"].update(vat_enabled=True, vat_pct=None)
        b = estimate(self.p).budget()
        self.assertTrue(any("PVN likme nav ievadīta" in r for r in b["reasons"]))
        self.assertTrue(b["incomplete"])

    def test_overhead_missing_is_not_zero(self):
        self.p["pricing"]["overhead_pct"] = None
        b = estimate(self.p).budget()
        self.assertIsNone(b["overhead"])
        self.assertTrue(any("pieskaitāmās" in r for r in b["reasons"]))
        self.assertTrue(b["incomplete"])

    def test_empty_project_budget_is_incomplete_without_invented_numbers(self):
        b = estimate(empty_project()).budget()
        self.assertTrue(b["incomplete"])
        self.assertIsNone(b["sell"])
        self.assertEqual(b["materials"], 0)
        self.assertIn("darba operācijas nav ievadītas", b["reasons"])


class TestLabour(unittest.TestCase):
    def setUp(self):
        self.p = demo_project()

    def op(self, name):
        e = estimate(self.p)
        return next(x for x in e.labour if x.name == name), e

    def test_norm_times_driver_times_rate(self):
        x, _ = self.op("CLT ārsienu montāža un apstrāde")
        self.assertAlmostEqual(x.hours, EXT * 0.5, 9)
        self.assertEqual(x.rate, 32.0)
        self.assertAlmostEqual(x.cost, EXT * 0.5 * 32.0, 9)

    def test_direct_hours(self):
        x, _ = self.op("Elektroinstalācija")
        self.assertEqual((x.hours, x.qty, x.cost), (60.0, None, 60.0 * 32.0))

    def test_rate_override_per_operation(self):
        next(o for o in self.p["labour"]["operations"] if o["name"] == "Elektroinstalācija")["rate_eur_h"] = 50.0
        x, _ = self.op("Elektroinstalācija")
        self.assertEqual(x.cost, 3000.0)

    def test_missing_rate_marks_incomplete_not_zero(self):
        self.p["labour"]["rate_eur_h"] = None
        e = estimate(self.p)
        x = next(x for x in e.labour if x.name == "Elektroinstalācija")
        self.assertEqual((x.status, x.hours, x.cost), (ST_NO_RATE, 60.0, None))
        self.assertTrue(any("likme" in m for m in e.missing[G_ELEC]))
        b = e.budget()
        self.assertEqual(b["labour_cost"], 0)
        self.assertEqual(b["labour_missing"], 15)
        self.assertTrue(b["incomplete"])

    def test_missing_norm_and_missing_basis(self):
        for o in self.p["labour"]["operations"]:
            if o["name"] == "Griestu apdare":
                o["norm_h"] = None
        x, e = self.op("Griestu apdare")
        self.assertEqual((x.status, x.hours, x.cost), (ST_MISSING, None, None))
        self.assertTrue(any("norma" in m for ms in e.missing.values() for m in ms))
        self.p["ceiling_m2"] = None                                    # pamata nav → arī «nav ievadīts»
        for o in self.p["labour"]["operations"]:
            if o["name"] == "Griestu apdare":
                o["norm_h"] = 0.25
        x, _ = self.op("Griestu apdare")
        self.assertIsNone(x.hours)

    def test_norm_and_direct_hours_together_are_blocked(self):
        for o in self.p["labour"]["operations"]:
            if o["name"] == "Ventilācijas montāža":
                o["norm_h"] = 0.5
        e = estimate(self.p)
        self.assertTrue(any("gan normstundas" in x for x in e.errors))
        self.assertNotIn("Ventilācijas montāža", [x.name for x in e.labour])

    def test_duplicate_operation_counted_once(self):
        dup = dict(next(o for o in self.p["labour"]["operations"] if o["name"] == "Elektroinstalācija"), id="x-dup")
        self.p["labour"]["operations"].append(dup)
        e = estimate(self.p)
        self.assertEqual([x.name for x in e.labour].count("Elektroinstalācija"), 1)
        self.assertTrue(any("dublikāts" in w for w in e.warnings))
        self.assertAlmostEqual(e.budget()["labour_hours"], expected_demo()[1], 9)

    def test_same_work_in_other_module_or_stage_is_not_duplicate(self):
        base = next(o for o in self.p["labour"]["operations"] if o["name"] == "Elektroinstalācija")
        self.p["labour"]["operations"].append(dict(base, id="x2", module="Modulis B", stage="posms X", hours=5.0))
        e = estimate(self.p)
        self.assertEqual([x.name for x in e.labour].count("Elektroinstalācija"), 2)
        self.assertEqual([x.stage for x in e.labour if x.module == "Modulis B"], ["posms X"])

    def test_labour_hours_in_material_rows_are_blocked(self):
        self.p["manual"].append({"id": "h1", "group": G_ELEC, "material": "Elektriķa darbs", "qty": 40, "unit": "h", "waste_pct": 0})
        self.p["recipes"].append({"id": "h2", "group": G_VENT, "name": "Montāža", "unit": "stundas", "driver": "direct", "qty": 10})
        e = estimate(self.p)
        self.assertEqual(len([x for x in e.errors if "darba stundas" in x]), 2)
        self.assertNotIn("Elektriķa darbs", [r.material for r in e.rows])

    def test_outsourced_cost_double_counting_with_operations_is_blocked(self):
        self.p["other_costs"].append({"id": "mep", "name": "MEP apakšuzņēmējs", "category": "Ārpakalpojumi", "group": G_ELEC,
                                      "amount_eur": 3000.0})
        e = estimate(self.p)
        self.assertTrue(any("Dubultošana" in x and G_ELEC in x for x in e.errors))
        self.assertTrue(e.budget()["incomplete"])
        self.p["other_costs"][-1]["group"] = None                       # bez grupas — nav sakritības
        self.assertFalse(any("Dubultošana" in x for x in estimate(self.p).errors))

    def test_free_stage_and_module_fields_pass_through(self):
        for o in self.p["labour"]["operations"]:
            if o["name"] == "Griestu apdare":
                o["stage"], o["module"] = "lietotāja posms", "Modulis A"
        x, _ = self.op("Griestu apdare")
        self.assertEqual((x.stage, x.module), ("lietotāja posms", "Modulis A"))
        self.assertTrue(all(x.stage == "" for x in estimate(demo_project()).labour))


class TestWasteDefaults(unittest.TestCase):
    def test_zero_waste_for_equipment_openings_sanitary_by_default(self):
        p = demo_project()
        for rec in p["recipes"]:
            rec["waste_pct"] = None
        p["manual"].append({"id": "eq", "group": G_EQUIP, "material": "Kondicionieris", "qty": 1, "unit": "gab.", "waste_pct": None,
                            "approved": False})
        p["manual"].append({"id": "mat", "group": G_FASTEN, "material": "Skrūves M", "qty": 10, "unit": "gab.", "waste_pct": None,
                            "approved": False})
        e = estimate(p)
        by = {r.material: r for r in e.rows}
        self.assertEqual(by["Kondicionieris"].waste_pct, 0.0)
        self.assertEqual(by["Kondicionieris"].order_qty, 1)
        self.assertEqual(by["Sanitārtehnikas komplekts (DEMO)"].order_qty, 1)
        self.assertEqual(by["Rekuperators (DEMO; modelis nav izvēlēts)"].order_qty, 1)
        self.assertEqual(by["Skrūves M"].waste_pct, 10.0)                # materiāliem — rediģējams 10%
        self.assertEqual(by["Skrūves M"].order_qty, 11)
        self.assertEqual([r.order_qty for r in e.rows if r.group == G_OPEN], [6, 1, 3])

    def test_material_default_is_editable(self):
        p = demo_project()
        p["waste_default_pct"] = 20
        for rec in p["recipes"]:
            rec["waste_pct"] = None
        e = estimate(p)
        lente = next(r for r in e.rows if r.material.startswith("Hermetizācijas lente"))
        self.assertAlmostEqual(lente.order_qty, 144 * 1.2, 9)
        self.assertEqual(next(r for r in e.rows if r.material.startswith("Rekuperators")).order_qty, 1)     # 0% paliek

    def test_clt_waste_note_present(self):
        e = estimate(demo_project())
        row = next(r for r in e.rows if r.material == "CLT ārsienu paneļi")
        self.assertIn("Alternatīvā vienība", row.note)                  # neto vs iepirkuma bruto: lietotāja regulējama rezerve


def manual_rows(e):
    return [r for r in e.rows if r.row_id.startswith("manual")]


class TestStableRowIdentity(unittest.TestCase):
    def two_manual(self):
        p = empty_project()
        p["manual"] = [
            {"id": "m1", "group": G_FASTEN, "material": "Skrūves", "article": "A-1", "spec": "6×80", "qty": 100, "unit": "gab.", "waste_pct": 0},
            {"id": "m2", "group": G_FASTEN, "material": "Skrūves", "article": "A-2", "spec": "6×120", "qty": 100, "unit": "gab.", "waste_pct": 0},
        ]
        return p

    def test_same_name_different_spec_keep_separate_prices(self):
        p = self.two_manual()
        e = estimate(p)
        r1, r2 = manual_rows(e)
        self.assertNotEqual(r1.row_id, r2.row_id)
        set_price(p, r1.row_id, 0.10, r1.unit, r1.article, r1.spec)
        set_price(p, r2.row_id, 0.25, r2.unit, r2.article, r2.spec)
        e = estimate(p)
        self.assertEqual([r.unit_price for r in e.rows if r.material == "Skrūves"], [0.10, 0.25])

    def test_identical_rows_get_distinct_ids(self):
        p = self.two_manual()
        for m in p["manual"]:
            m.pop("id")
            m["article"], m["spec"] = "A-1", "6×80"
        ids = [r.row_id for r in manual_rows(estimate(p))]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(ids), len(set(ids)))

    def test_prices_follow_row_not_position_or_name(self):
        p = self.two_manual()
        r2 = manual_rows(estimate(p))[1]
        set_price(p, r2.row_id, 0.25, r2.unit, r2.article, r2.spec)
        p["manual"].insert(0, {"id": "new", "group": G_FASTEN, "material": "Cits", "article": "A-9", "qty": 1, "unit": "gab.", "waste_pct": 0})
        p["manual"][2]["material"] = "Pārdēvēta skrūve"                    # nosaukuma maiņa neatņem cenu (vienība/artikuls/spec tie paši)
        e = estimate(p)
        renamed = next(r for r in e.rows if r.material == "Pārdēvēta skrūve")
        self.assertEqual(renamed.unit_price, 0.25)
        self.assertIsNone(next(r for r in e.rows if r.material == "Cits").unit_price)

    def test_price_not_applied_when_spec_article_or_unit_changed(self):
        for field, value in (("spec", "6×200"), ("article", "A-77"), ("unit", "kompl.")):
            p = self.two_manual()
            r = manual_rows(estimate(p))[0]
            set_price(p, r.row_id, 0.10, r.unit, r.article, r.spec)
            p["manual"][0][field] = value
            e = estimate(p)
            self.assertIsNone(manual_rows(e)[0].unit_price, field)
            self.assertTrue(any("cena netiek piemērota" in w for w in e.warnings), field)

    def test_row_ids_unique_and_stable_across_runs(self):
        p = demo_project()
        a = [r.row_id for r in estimate(p).rows]
        b = [r.row_id for r in estimate(p).rows]
        self.assertEqual(a, b)
        self.assertEqual(len(a), len(set(a)))

    def test_ensure_ids_assigns_unique_ids(self):
        p = empty_project()
        p["manual"] = [{"material": "a"}, {"material": "b", "id": "x"}, {"material": "c", "id": "x"}]
        ensure_ids(p)
        ids = [m["id"] for m in p["manual"]]
        self.assertEqual(len(set(ids)), 3)
        self.assertTrue(all(ids))


class TestReviewCancelledOnDataChange(unittest.TestCase):
    def test_any_data_change_cancels_review(self):
        from src.building_estimate import confirm_review
        p = demo_project()
        confirm_review(p, "Jānis")
        self.assertNotIn("NAV GATAVS", estimate(p).procurement_status)
        for mutate in (lambda q: q["clt"]["ext"].update(thickness_mm=110),
                       lambda q: q["pricing"].update(markup_pct=16.0),
                       lambda q: q["catalog"][0].update(unit_price=1.0),
                       lambda q: q["labour"].update(rate_eur_h=33.0)):
            q = demo_project()
            confirm_review(q, "Jānis")
            mutate(q)
            self.assertIn("apstiprinājums atcelts", estimate(q).procurement_status)


if __name__ == "__main__":
    unittest.main()
