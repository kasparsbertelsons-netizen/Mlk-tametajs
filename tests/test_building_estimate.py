"""Issue #12: pilnas ēkas provizoriskā materiālu tāme. Sintētiski dati.

Gaidāmās vērtības tiek rēķinātas TESTĀ ar vienkāršu aritmētiku no demonstrācijas ievaddatiem (nevis kopētas no koda izvades).
"""
import copy
import math
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.building_demo import demo_frame_project, demo_project
from src.building_estimate import (
    G_EXT, G_FLOOR, G_INT, G_MANUAL, G_OPEN, G_ROOF, G_TERRACE, NOT_FINAL, ST_DUP, ST_MISSING, empty_project, estimate,
    EXPORT_HEADER, export_rows, set_price,
)
from src.floor_frame import calculate_module

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def rows_of(est, group=None, text=None):
    return [r for r in est.rows if (group is None or r.group == group) and (text is None or text in r.material)]


def one(est, group, text):
    found = rows_of(est, group, text)
    assert len(found) == 1, (group, text, [r.material for r in found])
    return found[0]


class TestDemoControlValues(unittest.TestCase):
    def setUp(self):
        self.p = demo_frame_project()
        self.e = estimate(self.p)

    def test_no_errors_and_all_main_groups_present(self):
        self.assertEqual(self.e.errors, [])
        self.assertEqual(self.e.missing, {})
        for group in (G_FLOOR, G_EXT, G_INT, G_ROOF, G_OPEN, G_TERRACE, G_MANUAL):
            self.assertTrue(rows_of(self.e, group), group)
        self.assertTrue(self.e.complete)

    def test_external_walls_with_openings_and_shared_seams(self):
        gross = (20 + 20 + 4 + 4) * 2.7                       # 48 m fasādes; šuves (8 m) nav iekļautas
        openings = 6 * 1.2 * 1.5 + 1.0 * 2.1                  # 12,9 m²
        self.assertAlmostEqual(self.e.areas["ext_walls_gross_m2"], gross, 6)
        self.assertAlmostEqual(self.e.areas["ext_walls_net_m2"], gross - openings, 6)
        self.assertAlmostEqual(one(self.e, G_EXT, "Fasādes apdare").qty, 116.7, 6)
        self.assertLess(self.e.areas["ext_walls_length_m"], self.e.areas["module_perimeters_m"])
        self.assertEqual(self.e.areas["module_perimeters_m"], 2 * (12 + 4) + 2 * (8 + 4))

    def test_internal_walls_both_sides(self):
        net = (4 + 3 + 2.5) * 2.7 - 3 * 0.8 * 2.1
        self.assertAlmostEqual(self.e.areas["int_walls_net_m2"], net, 6)
        self.assertAlmostEqual(one(self.e, G_INT, "Apdare abās pusēs").qty, 2 * net, 6)
        self.assertAlmostEqual(one(self.e, G_INT, "pildījums").qty, net * 0.070, 6)      # m³ = laukums × 70 mm

    def test_floor_uses_existing_core_unchanged(self):
        a = one(self.e, G_FLOOR, "Modulis A")
        b = one(self.e, G_FLOOR, "Modulis B")
        self.assertAlmostEqual(a.qty, calculate_module(12000, 4000, name="x", reinforcements=[822.5, 1150]).total_volume_m3, 9)
        self.assertAlmostEqual(a.qty, 2.37888, 9)            # Issue #10 kontrolvērtība
        self.assertAlmostEqual(b.qty, 2 * .2 * .24 * 8 + 2 * .2 * .24 * 3.6 + 11 * .045 * .24 * 3.6, 6)   # 1,54128
        self.assertTrue(a.timber and b.timber)

    def test_pir_free_zones_and_floor_slab_and_finish(self):
        free = (12000 - 400 - 16 * 45 - 2 * 150) * 3600 / 1e6 + (8000 - 400 - 11 * 45) * 3600 / 1e6
        pir = one(self.e, G_FLOOR, "PIR")
        self.assertAlmostEqual(pir.qty, free, 6)
        self.assertEqual(pir.unit, "m²")
        self.assertAlmostEqual(one(self.e, G_FLOOR, "Grīdas plātne").qty, 12 * 4 + 8 * 4, 9)
        self.assertAlmostEqual(one(self.e, G_FLOOR, "Grīdas apdare").qty, 72.0, 9)      # neto platība, bez terases

    def test_roof_slope(self):
        expected = 120 / math.cos(math.radians(20))
        self.assertAlmostEqual(self.e.areas["roof_m2"], expected, 5)
        self.assertAlmostEqual(one(self.e, G_ROOF, "Jumta segums").qty, expected, 5)
        self.assertAlmostEqual(one(self.e, G_ROOF, "Jumta siltinājums").qty, expected * 0.2, 5)
        self.assertAlmostEqual(one(self.e, G_ROOF, "Latojums").qty, expected / 0.35, 4)  # m = laukums / solis

    def test_wall_frame_quantities(self):
        studs = (math.ceil(20000 / 600) + 1) * 2 + (math.ceil(4000 / 600) + 1) * 2 + 2 * 7       # 86 + 14 atveru statņi
        self.assertEqual(one(self.e, G_EXT, "karkasa statņi").qty, studs)
        self.assertEqual(studs, 100)
        metres = (86 * 2.7 + 14 * 2.7) + 2 * 48 + 2 * (6 * 1.2 + 1.0)
        self.assertAlmostEqual(one(self.e, G_EXT, "kokmateriāls kopā").qty, metres * 0.045 * 0.145, 6)

    def test_waste_is_separate_from_net(self):
        r = one(self.e, G_EXT, "Vēja plēve")
        self.assertEqual(r.waste_pct, 10.0)
        self.assertAlmostEqual(r.order_qty, r.qty * 1.1, 9)
        self.assertAlmostEqual(r.qty, 116.7, 6)                 # neto nemainīts
        win = one(self.e, G_OPEN, "L1")
        self.assertEqual((win.qty, win.order_qty), (6, 6))     # logiem rezerves nav
        pcs = one(self.e, G_EXT, "karkasa statņi")
        self.assertEqual(pcs.order_qty, 110)                      # 100 × 1,10 = 110 gab. (uz augšu)

    def test_terrace_is_separate(self):
        t = one(self.e, G_TERRACE, "Priekšējā terase")
        self.assertEqual(t.qty, 12.0)
        self.assertEqual(self.e.areas["floor_net_m2"], 72.0)

    def test_finish_not_counted_twice(self):
        # griestu apdare ir tikai grupā «Iekšējā apdare»; grīdas apdare tikai grupā «Grīda»
        names = [(r.material, r.unit) for r in self.e.rows if "apdare" in r.material.lower()]
        self.assertEqual(len(names), len(set((m, g) for (m, _u), g in zip(names, range(len(names))))))
        self.assertEqual(len(rows_of(self.e, text="Griestu apdare")), 1)
        self.assertEqual(len(rows_of(self.e, text="Grīdas apdare")), 1)

    def test_summary_does_not_mix_units(self):
        for s in self.e.summary():
            self.assertNotIn("unit", s)
        total = sum(s["timber_net"] for s in self.e.summary())
        self.assertAlmostEqual(total, sum(r.qty for r in self.e.rows if r.timber), 9)
        self.assertTrue(all(r.unit == "m³" for r in self.e.rows if r.timber))

    def test_manual_row_marked(self):
        r = one(self.e, G_MANUAL, "Vannasistabas")
        self.assertEqual(r.status, "manuāli")
        self.assertEqual(self.e.group_status(G_MANUAL), "tikai manuāla")


class TestNoInventedValues(unittest.TestCase):
    def test_empty_project_is_incomplete_and_does_not_crash(self):
        e = estimate(empty_project())
        self.assertFalse(e.complete)
        self.assertTrue(e.missing[G_FLOOR])
        self.assertTrue(all(r.qty is None for r in e.rows))        # nekas netiek izdomāts
        self.assertEqual(e.group_status(G_FLOOR), "NEPILNA")

    def test_missing_thickness_gives_not_entered(self):
        p = demo_frame_project()
        for layer in p["layers"]:
            if layer["name"] == "Jumta siltinājums":
                layer["thickness_mm"] = None
        e = estimate(p)
        r = one(e, G_ROOF, "Jumta siltinājums")
        self.assertIsNone(r.qty)
        self.assertEqual(r.status, ST_MISSING)
        self.assertFalse(e.complete)
        self.assertTrue(any("biezums" in m for m in e.missing[G_ROOF]))

    def test_missing_step_and_frame_params(self):
        p = demo_frame_project()
        p["frames"]["ext"]["step_mm"] = None
        e = estimate(p)
        self.assertEqual(rows_of(e, G_EXT, "karkasa"), [])
        self.assertTrue(any("karkasa" in m for m in e.missing[G_EXT]))

    def test_unconfirmed_module_not_counted(self):
        p = demo_frame_project()
        p["modules"][1]["confirmed"] = False
        e = estimate(p)
        self.assertEqual(rows_of(e, G_FLOOR, "Modulis B"), [])
        self.assertTrue(any("Modulis B" in m for m in e.missing[G_FLOOR]))
        self.assertFalse(e.complete)

    def test_roof_slope_requires_confirmation(self):
        p = demo_frame_project()
        p["roof"]["slope_confirmed"] = False
        e = estimate(p)
        self.assertIsNone(e.areas["roof_m2"])
        self.assertEqual(rows_of(e, G_ROOF, "Jumta segums")[0].qty, None)
        p["roof"] = {"mode": "area", "area_m2": 130.0, "footprint_m2": None, "angle_deg": None, "slope_confirmed": False}
        self.assertEqual(one(estimate(p), G_ROOF, "Jumta segums").qty, 130.0)

    def test_wall_height_is_editable_default(self):
        p = demo_frame_project()
        p["wall_height_mm"] = 3000
        self.assertAlmostEqual(estimate(p).areas["ext_walls_gross_m2"], 48 * 3.0, 9)
        p["ext_walls"][0]["height_mm"] = 2500                      # posma augstums pārraksta noklusējumu
        self.assertAlmostEqual(estimate(p).areas["ext_walls_gross_m2"], 20 * 2.5 + 28 * 3.0, 9)


class TestValidation(unittest.TestCase):
    def test_openings_exceed_wall_blocks_net(self):
        p = demo_frame_project()
        p["openings"].append({"kind": "Logs", "name": "Milzu", "width_mm": 9000, "height_mm": 9000, "count": 5, "wall": "Ārsiena"})
        e = estimate(p)
        self.assertTrue(any("atveru laukums" in x for x in e.errors))
        self.assertIsNone(e.areas["ext_walls_net_m2"])
        self.assertIsNone(one(e, G_EXT, "Fasādes apdare").qty)
        self.assertFalse(e.complete)

    def test_ext_length_cannot_exceed_module_perimeters(self):
        p = demo_frame_project()
        p["ext_walls"][0]["length_m"] = 40.0
        e = estimate(p)
        self.assertTrue(any("pārsniedz moduļu perimetru" in x for x in e.errors))

    def test_shared_seams_counted_as_facade_warns(self):
        p = demo_frame_project()
        p["ext_walls"] = [{"name": "viss", "length_m": 56.0, "height_mm": None}]       # = Σ moduļu perimetri → šuves iekļautas
        e = estimate(p)
        self.assertTrue(any("kopīgās moduļu šuves" in w for w in e.warnings))

    def test_negative_and_garbage_input(self):
        p = demo_frame_project()
        p["ext_walls"][0]["length_m"] = -5
        p["terraces"][0]["area_m2"] = "abc"
        e = estimate(p)
        self.assertTrue(any("nenegatīvam" in x for x in e.errors))
        self.assertTrue(any("nederīga" in x for x in e.errors))

    def test_reinforcement_conflict_is_reported_not_hidden(self):
        p = demo_frame_project()
        p["modules"][0]["axes"] = "822"                          # pārklājas ar R1, netiek snapots
        e = estimate(p)
        self.assertTrue(any("Modulis A" in x and "pārklājas" in x for x in e.errors))
        self.assertEqual(rows_of(e, G_FLOOR, "Modulis A"), [])
        self.assertFalse(e.complete)

    def test_duplicate_layer_excluded_once(self):
        p = demo_frame_project()
        p["layers"].append({"group": "Iekšējā apdare", "name": "grīdas  APDARE", "basis": "floor_net", "unit": "m²",
                            "thickness_mm": None, "step_mm": None, "waste_pct": 10, "source": "", "enabled": True})
        e = estimate(p)
        floor = rows_of(e, text="apdare")
        counted = [r for r in floor if r.material.lower().split()[-1] == "apdare" and r.status != ST_DUP and "Grīdas" in r.material]
        self.assertEqual(len(counted), 1)
        self.assertEqual(len([r for r in e.rows if r.status == ST_DUP]), 1)
        self.assertTrue(any("dublikāts" in w for w in e.warnings))
        self.assertEqual(len([s for s in e.summary()]), len(estimate(demo_frame_project()).summary()))

    def test_same_name_other_basis_is_not_duplicate(self):
        e = estimate(demo_frame_project())
        self.assertEqual([r for r in e.rows if r.status == ST_DUP], [])
        self.assertEqual(len(rows_of(e, text="Karkasa pildījums")), 2)     # ārsienas un iekšsienas

    def test_too_many_modules(self):
        p = demo_frame_project()
        p["modules"] = p["modules"] * 6
        self.assertTrue(any("pārāk daudz moduļu" in x for x in estimate(p).errors))


class TestPricesAndExport(unittest.TestCase):
    def test_prices_only_when_entered(self):
        p = demo_frame_project()
        r = one(estimate(p), G_EXT, "Vēja plēve")
        self.assertIsNone(r.cost)
        set_price(p, r.row_id, 2.0, r.unit, r.article, r.spec)
        e = estimate(p)
        r = one(e, G_EXT, "Vēja plēve")
        self.assertAlmostEqual(r.cost, r.order_qty * 2.0, 9)
        s = {x["group"]: x for x in e.summary()}[G_EXT]
        self.assertEqual(s["priced_rows"], 1)
        self.assertGreater(s["unpriced_rows"], 0)
    def test_csv_complete_demo(self):
        e = estimate(demo_frame_project())
        rows = export_rows("DEMO", e)
        self.assertEqual(rows[0][0], NOT_FINAL)
        self.assertIn("provizoriska", rows[1][1])
        text = "\n".join(";".join(map(str, r)) for r in rows)
        self.assertIn("NAV IEKĻAUTS", text)
        self.assertIn("Darbs, transports, montāža", text)
        self.assertIn("pieņēmums (nav apstiprināts)", text)
        self.assertIn("manuāli", text)
        self.assertIn(EXPORT_HEADER, rows)
        self.assertEqual(len(rows) - rows.index(EXPORT_HEADER) - 1, len(e.rows) + len(e.excluded) + sum(len(v) for v in e.missing.values()))

    def test_csv_incomplete_is_marked_and_formula_safe(self):
        p = demo_frame_project()
        p["roof"]["slope_confirmed"] = False
        p["name"] = "=HYPERLINK(1)"
        p["manual"].append({"group": G_MANUAL, "material": "=cmd|x", "qty": 1, "unit": "gab.", "waste_pct": 0, "source": "@x"})
        rows = export_rows(p["name"], estimate(p))
        self.assertIn("NEPILNA", rows[1][1])
        self.assertFalse(rows[1][0].startswith("="))
        self.assertTrue(any(len(r) > 1 and r[1] == "'=cmd|x" for r in rows))
        self.assertTrue(any("NEPILNA SADAĻA" in r for r in rows))
        self.assertTrue(any(len(r) > 1 and r[1] == "'=cmd|x" for r in rows))


# ---- UI ---------------------------------------------------------------------------------------------------------
def building_app():
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.radio[0].set_value("Pilnas ēkas tāme").run()
    return at


class TestUi(unittest.TestCase):
    def test_modes_preserved(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        self.assertEqual(list(at.radio[0].options),
                         ["AD — prognozēt rāmi", "PD — nolasīt specifikāciju", "Pilnas ēkas tāme"])

    def test_empty_view_warns_incomplete(self):
        at = building_app()
        self.assertFalse(at.exception)
        self.assertTrue(any("NEPILNA TĀME" in w.value for w in at.warning))

    def test_demo_one_click(self):
        at = building_app()
        at.button(key="bp_demo").click().run()
        self.assertFalse(at.exception)
        values = {m.label: m.value for m in at.metric}
        self.assertEqual(values["Koksne kopā (neto)"], "32.563 m³")
        self.assertTrue(any("Excel" in b.proto.label for b in at.get("download_button")))
        self.assertTrue(any("PROVIZORISKA" in w.value for w in at.warning))
        self.assertTrue(any("NAV IEKĻAUTS" in e.value for e in at.error))
        self.assertFalse(any("NEPILNA TĀME" in w.value for w in at.warning))

    def test_changing_module_dimensions_cancels_confirmation(self):
        at = building_app()
        at.button(key="bp_demo").click().run()
        at.session_state["bp_project"]["modules"][0]["length_mm"] = 12100
        at.run()
        project = at.session_state["bp_project"]
        self.assertFalse(project["modules"][0]["confirmed"])
        self.assertTrue(any("Apstiprinājums atcelts" in w.value for w in at.warning))
        self.assertTrue(any("NEPILNA TĀME" in w.value for w in at.warning))
        project["modules"][0]["length_mm"] = 12000                  # A → B → A: apstiprinājums neatjaunojas
        at.run()
        self.assertFalse(at.session_state["bp_project"]["modules"][0]["confirmed"])

    def test_clear_resets_project(self):
        at = building_app()
        at.button(key="bp_demo").click().run()
        at.button(key="bp_clear").click().run()
        self.assertEqual(at.session_state["bp_project"]["modules"], [])

    def test_demo_is_synthetic(self):
        p = demo_project()
        self.assertIn("DEMO", p["name"])
        self.assertTrue(p["is_demo"])
        self.assertTrue(all(c["source"].startswith("DEMO") for c in p["catalog"]))