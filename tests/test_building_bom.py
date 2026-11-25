"""Issue #12 (2. posms): CLT recepte, BOM datu modelis, patēriņa normu receptes, katalogs, grupu pārklājums, budžets.

Sintētiski dati. Gaidāmās vērtības tiek rēķinātas testā ar vienkāršu aritmētiku (nevis kopētas no koda izvades).
"""
import copy
import math
import unittest
from dataclasses import fields
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.building_demo import demo_frame_project, demo_project
from src.building_estimate import (
    confirm_review, set_price, EXPORT_HEADER, G_ELEC, G_EQUIP, G_EXT, G_FASTEN, G_FLOOR, G_INT, G_MANUAL, G_ROOF, G_VENT, MANDATORY_GROUPS, ST_MISSING,
    ST_UNAPPROVED, Row, default_layers, empty_project, estimate, export_rows,
)

APP = str(Path(__file__).resolve().parent.parent / "app.py")
ROOF = 120 / math.cos(math.radians(20))
EXT_NET, INT_NET = 116.7, 20.61


def bare_demo():
    """CLT demo BEZ cenām, darba un cenojuma (veco budžeta testu pamats): tikai ģeometrija, recepšu rindas un katalogs bez cenām."""
    p = demo_project()
    p["prices"] = {}
    for c in p["catalog"]:
        c["unit_price"] = None
    p["labour"] = {"rate_eur_h": None, "operations": []}
    p["pricing"] = {"overhead_pct": None, "method": None, "markup_pct": None, "margin_pct": None, "vat_enabled": False, "vat_pct": None}
    p["other_costs"] = [{"id": "a", "name": "MEP darbs un montāža", "category": "Ārpakalpojumi", "group": None, "amount_eur": None},
                        {"id": "b", "name": "Transports", "category": "Transports", "group": None, "amount_eur": None},
                        {"id": "c", "name": "Montāža objektā", "category": "Montāža", "group": None, "amount_eur": None}]
    return p


def one(est, group, text):
    found = [r for r in est.rows if r.group == group and text in r.material]
    assert len(found) == 1, (group, text, [r.material for r in found])
    return found[0]


class TestCltRecipe(unittest.TestCase):
    def setUp(self):
        self.p = demo_project()
        self.e = estimate(self.p)

    def test_ext_panels_price_by_volume_with_alt_area(self):
        r = one(self.e, G_EXT, "CLT ārsienu paneļi")
        self.assertEqual((r.unit, r.alt_unit), ("m³", "m²"))
        self.assertAlmostEqual(r.qty, EXT_NET * 0.100, 6)
        self.assertAlmostEqual(r.alt_qty, EXT_NET, 6)
        self.assertAlmostEqual(r.order_qty, EXT_NET * 0.1 * 1.10, 6)
        self.assertTrue(r.approved)
        self.assertEqual(r.status, "ievadīts")

    def test_int_panels_price_by_area_with_alt_volume(self):
        r = one(self.e, G_INT, "CLT iekšsienu paneļi")
        self.assertEqual((r.unit, r.alt_unit), ("m²", "m³"))
        self.assertAlmostEqual(r.qty, INT_NET, 6)
        self.assertAlmostEqual(r.alt_qty, INT_NET * 0.080, 6)

    def test_cost_is_never_doubled(self):
        p = self.p
        r = one(self.e, G_EXT, "CLT ārsienu paneļi")
        p["prices"] = {r.price_key(): {"price": 100.0, "hours": None}}
        r2 = one(estimate(p), G_EXT, "CLT ārsienu paneļi")
        self.assertAlmostEqual(r2.cost, r.order_qty * 100.0, 9)               # tikai pēc izvēlētās vienības (m³)
        self.assertNotAlmostEqual(r2.cost, (r.order_qty + EXT_NET * 1.1) * 100.0, 3)
        p["clt"]["ext"]["price_unit"] = "m²"                                   # cena tagad pēc m²
        r3 = one(estimate(p), G_EXT, "CLT ārsienu paneļi")
        self.assertEqual((r3.unit, r3.alt_unit), ("m²", "m³"))
        self.assertAlmostEqual(r3.cost, EXT_NET * 1.1 * 100.0, 6)

    def test_unconfirmed_thickness_is_marked(self):
        r = one(self.e, G_ROOF, "CLT jumta paneļi")                           # demo: biezums nav apstiprināts
        self.assertFalse(r.approved)
        self.assertEqual(r.status, ST_UNAPPROVED)
        self.assertAlmostEqual(r.qty, ROOF * 0.120, 5)

    def test_missing_thickness_is_not_invented(self):
        p = demo_project()
        p["clt"]["ext"]["thickness_mm"] = None
        e = estimate(p)
        r = one(e, G_EXT, "CLT ārsienu paneļi")
        self.assertIsNone(r.qty)
        self.assertEqual(r.status, ST_MISSING)
        self.assertTrue(any("biezums" in m for m in e.missing[G_EXT]))
        self.assertFalse(e.complete)

    def test_clt_waste_is_separate_from_default(self):
        p = demo_project()
        p["waste_default_pct"] = 25
        p["clt"]["ext"]["waste_pct"] = 5
        e = estimate(p)
        self.assertAlmostEqual(one(e, G_EXT, "CLT ārsienu paneļi").order_qty, EXT_NET * 0.1 * 1.05, 6)
        p["clt"]["roof"]["waste_pct"] = None                                                       # tukšs → CLT noklusējums 10%, ne 25%
        self.assertAlmostEqual(one(estimate(p), G_ROOF, "CLT jumta paneļi").order_qty, ROOF * 0.12 * 1.10, 5)
        self.assertAlmostEqual(one(e, G_EXT, "Fasādes apdare").order_qty, EXT_NET * 1.10, 6)      # slānim sava (ievadīta) rezerve
        self.assertAlmostEqual(one(e, G_FASTEN, "Hermetizācijas lente").order_qty, 144.0 * 1.25, 6)  # tukša rezerve → noklusējums

    def test_floor_and_roof_panels_optional_and_floor_frame_switch(self):
        p = demo_project()
        p["clt"]["floor"].update(enabled=True, thickness_mm=140, thickness_confirmed=True)
        e = estimate(p)
        panel = one(e, G_FLOOR, "CLT grīdas paneļi")
        self.assertAlmostEqual(panel.qty, 80.0, 6)                                                # Σ L×W = 48 + 32 (cena pēc m²)
        self.assertAlmostEqual(panel.alt_qty, 80.0 * 0.140, 6)
        p["floor_frame_enabled"] = False
        e = estimate(p)
        self.assertEqual([r for r in e.rows if "rāmja kokmateriāls" in r.material or "PIR" in r.material], [])
        self.assertEqual(e.areas["modules_confirmed"], 2)                                         # ģeometrija saglabāta
        p["clt"]["roof"]["enabled"] = False
        e = estimate(p)
        self.assertTrue(any("jumta nesošā konstrukcija" in m for m in e.missing[G_ROOF]))

    def test_timber_summary_includes_clt_volume(self):
        floor = (2 * .2 * .24 * 12 + 2 * .2 * .24 * 3.6 + 16 * .045 * .24 * 3.6 + 2 * .15 * .24 * 3.6) + \
                (2 * .2 * .24 * 8 + 2 * .2 * .24 * 3.6 + 11 * .045 * .24 * 3.6)
        expected = floor + EXT_NET * .1 + INT_NET * .08 + ROOF * .12
        self.assertAlmostEqual(sum(s["timber_net"] for s in self.e.summary()), expected, 5)

    def test_clt_has_no_frame_recipe_and_frame_keeps_it(self):
        clt_names = {l["name"] for l in default_layers("clt")}
        frame_names = {l["name"] for l in default_layers("frame")}
        self.assertNotIn("Karkasa pildījums (vate)", clt_names)
        self.assertIn("Karkasa pildījums (vate)", frame_names)
        self.assertEqual([r for r in self.e.rows if "karkasa" in r.material.lower()], [])
        fe = estimate(demo_frame_project())
        self.assertEqual(one(fe, G_EXT, "karkasa statņi").qty, 100)                              # karkasa kods nav izmests
        self.assertEqual([r for r in fe.rows if "CLT" in r.material], [])

    def test_existing_floor_core_unchanged_in_clt_project(self):
        self.assertAlmostEqual(one(self.e, G_FLOOR, "Modulis A").qty, 2.37888, 9)
        self.assertAlmostEqual(one(self.e, G_FLOOR, "Modulis B").qty, 1.54128, 9)


class TestBomDataModel(unittest.TestCase):
    def test_row_has_all_required_fields(self):
        names = {f.name for f in fields(Row)}
        for needed in ("article", "material", "spec", "unit", "qty", "waste_pct", "order_qty", "unit_price", "module", "group", "stage",
                       "pack_size", "approved", "source", "status"):
            self.assertIn(needed, names)

    def test_header_covers_required_columns(self):
        for col in ("Artikuls", "Materiāls", "Specifikācija", "Mervienība", "Neto", "Rezerve_%", "Pasūtāmais", "Vienības_cena_EUR",
                    "Modulis_telpa_sistēma", "Konstrukciju_grupa", "Ražošanas_posms", "Apstiprinājums"):
            self.assertIn(col, EXPORT_HEADER)

    def test_production_stage_is_free_and_empty_by_default(self):
        e = estimate(demo_project())
        self.assertTrue(all(r.stage == "" for r in e.rows))
        p = demo_project()
        p["recipes"][0]["stage"] = "lietotāja posms X"
        self.assertEqual(one(estimate(p), G_FASTEN, "Skrūves").stage, "lietotāja posms X")

    def test_unknown_is_not_zero_in_csv(self):
        rows = export_rows("DEMO", estimate(bare_demo()))
        head = rows.index(EXPORT_HEADER)
        price_col, cost_col = EXPORT_HEADER.index("Vienības_cena_EUR"), EXPORT_HEADER.index("Izmaksas_EUR")
        data = rows[head + 1:]
        unpriced = [r for r in data if len(r) == len(EXPORT_HEADER) and r[price_col] == "" and r[3] != ""]
        self.assertGreater(len(unpriced), 20)
        self.assertTrue(all(r[cost_col] == "" for r in unpriced))                          # nav «0,00»
class TestRecipes(unittest.TestCase):
    def test_norm_times_driver_with_pack_rounding_and_catalog_price(self):
        e = estimate(demo_project())
        r = one(e, G_FASTEN, "Skrūves")
        self.assertAlmostEqual(r.qty, EXT_NET * 6.0, 6)                                     # 700,2 gab.
        self.assertEqual(r.order_qty, 800)                                                  # ⌈700,2×1,1⌉ = 771 → iepakojumi pa 200
        self.assertEqual(r.pack_size, 200)
        self.assertAlmostEqual(r.cost, 800 * 0.12, 9)                                       # cena no kataloga par artikulu
        self.assertEqual(r.article, "DEMO-SKR-6x80")

    def test_length_and_count_drivers(self):
        e = estimate(demo_project())
        self.assertAlmostEqual(one(e, G_FASTEN, "Hermetizācijas lente").qty, 48.0 * 3.0, 9)     # ārsienu garums × norma
        self.assertEqual(one(e, G_FASTEN, "Leņķskavas").qty, 2 * 40.0)                           # moduļu skaits × norma
        self.assertAlmostEqual(one(e, G_ELEC, "Elektrokabelis").qty, 72.0 * 2.5, 9)              # neto grīda × norma

    def test_missing_norm_is_not_invented(self):
        p = demo_project()
        p["recipes"][0]["norm"] = None
        e = estimate(p)
        r = one(e, G_FASTEN, "Skrūves")
        self.assertIsNone(r.qty)
        self.assertEqual(r.status, ST_MISSING)
        self.assertTrue(any("norma" in m for m in e.missing[G_FASTEN]))
        self.assertFalse(e.complete)

    def test_missing_direct_quantity_and_missing_driver(self):
        p = demo_project()
        p["recipes"][3]["qty"] = None                                                       # vent. caurule
        p["ext_walls"] = []
        e = estimate(p)
        self.assertIsNone(one(e, G_VENT, "caurule").qty)
        self.assertTrue(any("daudzums nav ievadīts" in m for m in e.missing[G_VENT]))
        self.assertIsNone(one(e, G_FASTEN, "Skrūves").qty)                                  # nav pamata «ārsienu neto»
        self.assertTrue(any("nav pieejams pamats" in m for m in e.missing[G_FASTEN]))

    def test_equipment_with_zero_reserve_stays_one_piece(self):
        r = one(estimate(demo_project()), G_EQUIP, "Rekuperators")
        self.assertEqual((r.qty, r.order_qty, r.waste_pct), (1.0, 1.0, 0.0))

    def test_catalog_fills_blank_fields_and_explicit_price_wins(self):
        p = empty_project()
        p["catalog"] = [{"article": "A-1", "name": "Skrūve X", "spec": "spec X", "unit": "gab.", "unit_price": 0.5, "pack_size": 10,
                         "source": "t"}]
        p["recipes"] = [{"group": G_FASTEN, "article": "A-1", "name": "", "spec": "", "unit": "", "driver": "direct", "norm": None,
                         "qty": 23, "waste_pct": 0, "pack_size": None, "module": "M1", "stage": "", "approved": True, "source": "t",
                         "enabled": True}]
        r = one(estimate(p), G_FASTEN, "Skrūve X")
        self.assertEqual((r.spec, r.unit, r.module, r.status, r.order_qty), ("spec X", "gab.", "M1", "ievadīts", 30))
        self.assertAlmostEqual(r.cost, 30 * 0.5, 9)
        set_price(p, r.row_id, 2.0, r.unit, r.article, r.spec)
        r = one(estimate(p), G_FASTEN, "Skrūve X")
        self.assertAlmostEqual(r.cost, 60.0, 9)

    def test_catalog_price_with_other_unit_is_not_applied(self):
        p = empty_project()
        p["catalog"] = [{"article": "A-2", "name": "Lente", "unit": "ruļļi", "unit_price": 5.0}]
        p["recipes"] = [{"group": G_FASTEN, "article": "A-2", "name": "Lente", "unit": "m", "driver": "direct", "qty": 10,
                         "approved": False, "enabled": True}]
        e = estimate(p)
        self.assertIsNone(one(e, G_FASTEN, "Lente").cost)
        self.assertTrue(any("cena netiek piemērota" in w for w in e.warnings))

    def test_invalid_recipe_rows_are_reported(self):
        p = empty_project()
        p["recipes"] = [{"group": "Nezināma", "name": "x", "unit": "m", "driver": "direct", "qty": 1}]
        self.assertTrue(any("nepilnīga" in x for x in estimate(p).errors))
        p["recipes"] = [{"group": G_FASTEN, "name": "x", "unit": "m", "driver": "direct", "qty": -3}]
        self.assertTrue(any("nenegatīvam" in x for x in estimate(p).errors))

    def test_manual_rows_carry_bom_fields(self):
        p = demo_project()
        p["manual"].append({"group": G_MANUAL, "material": "Skrūves M", "qty": 95, "unit": "gab.", "waste_pct": 0, "pack_size": 50,
                            "article": "X-9", "spec": "sp", "module": "Modulis B", "stage": "", "approved": True, "source": "manuāli"})
        r = one(estimate(p), G_MANUAL, "Skrūves M")
        self.assertEqual((r.order_qty, r.article, r.module, r.status, r.approved), (100, "X-9", "Modulis B", "manuāli", True))


class TestCoverageAndBudget(unittest.TestCase):
    def test_empty_project_all_mandatory_groups_uncovered(self):
        e = estimate(empty_project())
        self.assertEqual(e.uncovered, [g for g in MANDATORY_GROUPS if g not in (G_FLOOR, G_EXT, G_INT, G_ROOF, "Iekšējā apdare")])
        status = {s["group"]: s["status"] for s in e.summary()}
        self.assertEqual(status[G_VENT], "NAV IEVADĪTS")
        self.assertEqual(status[G_EXT], "NEPILNA")                                              # ir nosaukti slāņi, bet nav ievaddatu
        self.assertEqual(len([s for s in e.summary() if s["group"] in MANDATORY_GROUPS]), len(MANDATORY_GROUPS))
        self.assertTrue(e.budget()["incomplete"])

    def test_demo_covers_all_groups_and_removal_is_detected(self):
        p = demo_project()
        self.assertEqual(estimate(p).uncovered, [])
        p["recipes"] = [r for r in p["recipes"] if r["group"] != G_VENT]
        e = estimate(p)
        self.assertEqual(e.uncovered, [G_VENT])
        self.assertTrue(e.budget()["incomplete"])
        self.assertTrue(any(len(r) > 1 and r[1] == G_VENT for r in export_rows("x", e)))     # CSV norāda nepārklāto grupu

    def test_budget_sums_only_entered_prices_and_other_costs(self):
        p = bare_demo()
        e0 = estimate(p)
        wind = one(e0, G_EXT, "Vēja membrāna")
        ext = one(e0, G_EXT, "CLT ārsienu paneļi")
        set_price(p, wind.row_id, 2.0, wind.unit, wind.article, wind.spec)
        set_price(p, ext.row_id, 500.0, ext.unit, ext.article, ext.spec)
        p["other_costs"][1]["amount_eur"] = 1200.0                                           # transports
        b = estimate(p).budget()
        materials = wind.order_qty * 2.0 + ext.order_qty * 500.0
        self.assertAlmostEqual(b["materials"], materials, 6)
        self.assertAlmostEqual(b["total"], materials + 1200.0, 6)
        self.assertIn("Transports", [n for n, _a in b["other_entered"]])
        self.assertIn("MEP darbs un montāža", b["other_missing"])
        self.assertTrue(b["incomplete"])
        self.assertEqual(b["priced_rows"], 2)
    def test_budget_marked_complete_only_when_everything_priced(self):
        p = demo_project()
        b = estimate(p).budget()
        self.assertFalse(b["incomplete"])                                                    # pilnībā cenots demo
        self.assertEqual(b["reasons"], [])
        victim = next(r for r in estimate(p).rows if r.material == "Jumta segums")
        for c in p["catalog"]:
            if c["article"] == victim.article:
                c["unit_price"] = None                                                       # cena izņemta → NEPILNS, nevis 0
        b2 = estimate(p).budget()
        self.assertTrue(b2["incomplete"])
        self.assertEqual(b2["unpriced_rows"], 1)
        self.assertTrue(any("bez cenas" in r for r in b2["reasons"]))
    def test_negative_other_cost_is_error(self):
        p = demo_project()
        p["other_costs"][0]["amount_eur"] = -5
        self.assertTrue(any("Citas izmaksas" in x for x in estimate(p).errors))

    def test_procurement_status_requires_review_and_coverage(self):
        p = demo_project()
        self.assertIn("nav atbildīgās personas pārbaudes", estimate(p).procurement_status)
        confirm_review(p, "Jānis")
        status = estimate(p).procurement_status
        self.assertIn("Jānis", status)
        self.assertIn("provizoriski", status)
        self.assertNotIn("NAV GATAVS", status)
        p["review"] = {"reviewer": "", "confirmed": True, "fp": None}                          # bez vārda neder
        self.assertIn("NAV GATAVS", estimate(p).procurement_status)
        confirm_review(p, "Jānis")
        p["recipes"] = []                                                                      # datu izmaiņa atceļ pārbaudi
        self.assertIn("apstiprinājums atcelts", estimate(p).procurement_status)
        confirm_review(p, "Jānis")                                                             # jauna pārbaude bez obligāto grupu → nepilns
        self.assertIn("nepilns pārklājums", estimate(p).procurement_status)
    def test_csv_contains_budget_stage_and_procurement(self):
        rows = export_rows("DEMO", estimate(bare_demo()))
        text = "\n".join(";".join(map(str, r)) for r in rows)
        for needle in ("BUDŽETA KOPSAVILKUMS", "AD budžeta stadija", "NAV GATAVS IEPIRKUMAM", "BEZ CENAS", "GRUPU PĀRKLĀJUMS",
                       "CLT ārsienu paneļi", "DEMO-SKR-6x80", "Alternatīvā", "Rindas_ID"):
            self.assertIn(needle, text)
        self.assertIn("NEPILNA", text)

def building_app():
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.radio[0].set_value("Pilnas ēkas tāme").run()
    return at


class TestUiClt(unittest.TestCase):
    def test_demo_loads_clt_house_with_budget_and_coverage(self):
        at = building_app()
        at.button(key="bp_demo").click().run()
        self.assertFalse(at.exception)
        values = {m.label: m.value for m in at.metric}
        expected = (3.92016 + EXT_NET * .1 + INT_NET * .08 + ROOF * .12)
        self.assertEqual(values["Koksne kopā (neto)"], f"{expected:.3f} m³")
        self.assertEqual(values["Pašizmaksa"], "74607.43 EUR")
        self.assertEqual(values["Pārdošanas cena bez PVN"], "85798.54 EUR")
        self.assertTrue(any("Iepirkuma gatavība" in i.value and "NAV GATAVS" in i.value for i in at.info))
        self.assertEqual(at.session_state["bp_project"]["construction"], "clt")
        self.assertFalse(any("Budžets ir NEPILNS" in w.value for w in at.warning))
    def test_switching_construction_resets_layers_with_notice(self):
        at = building_app()
        at.button(key="bp_demo").click().run()
        radio = next(r for r in at.radio if r.label.startswith("Konstrukcijas tips"))
        radio.set_value("Koka karkass (2. posms)").run()
        self.assertFalse(at.exception)
        project = at.session_state["bp_project"]
        self.assertEqual(project["construction"], "frame")
        self.assertIn("Karkasa pildījums (vate)", [l["name"] for l in project["layers"]])
        self.assertTrue(any("Konstrukcijas tips mainīts" in w.value for w in at.warning))

    def test_download_present_and_empty_project_ok(self):
        at = building_app()
        self.assertFalse(at.exception)
        self.assertTrue(any("NEPILNA TĀME" in w.value for w in at.warning))
        at.button(key="bp_demo").click().run()
        labels = [b.proto.label for b in at.get("download_button")]
        self.assertTrue(any("Excel" in l for l in labels))
        self.assertTrue(any("projektu" in l.lower() for l in labels))