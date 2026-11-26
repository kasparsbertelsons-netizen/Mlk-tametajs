"""Issue #20: lokāla recepšu/cenu/normstundu bibliotēka, komplektācijas, draiveri (tikai sintētiski dati)."""
import copy
import json
import unittest
from pathlib import Path

from src.building_demo import demo_ad_project
from src.building_estimate import DRIVERS, G_FURN, G_OPEN, G_SANIT, empty_project, estimate
from src.forecast_compare import add_version, freeze_forecast
from src.library import (
    ST_APPROVED, ST_HISTORICAL, ST_UNAPPROVED, apply_kits, apply_library, export_library, kit_total, parse_library, preview_library,
)
from src.project_io import export_project, import_project
from tools.synthetic_library import build_library

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "library" / "biblioteka_sintetiska.json"
TODAY = "2026-11-26"


def lib_of(data=None):
    result = parse_library(export_library(data or build_library()))
    assert not result.errors, result.errors
    return result.library


def ad_geometry():
    """Sintētiskā AD ģeometrija bez receptēm/darba operācijām (tās nāk no bibliotēkas)."""
    p = demo_ad_project()
    p["recipes"], p["catalog"] = [], []
    p["labour"]["operations"] = []
    p["openings"] = []                              # logi/durvis kā atveres NAV ievadītas (komplekts tos dod)
    p["rooms"] = [{"id": "r1", "name": "Vannasistaba", "type": "wet", "count": 1}, {"id": "r2", "name": "WC", "type": "wet", "count": 1}]
    p["kitchen_len_m"] = 4.0
    return p


def rows_of(est, group=None):
    return [r for r in est.rows if group is None or r.group == group]


class TestParse(unittest.TestCase):
    def test_sample_file_in_repo_is_valid_and_current(self):
        result = parse_library(SAMPLE.read_bytes())
        self.assertEqual((result.errors, result.warnings), ([], []))
        self.assertEqual(SAMPLE.read_bytes(), export_library(build_library()), "samples/library jāpārģenerē: python -m tools.synthetic_library")
        self.assertTrue(result.library["meta"]["synthetic"])

    def bad(self, mutate):
        data = build_library()
        mutate(data)
        return parse_library(export_library(data))

    def test_unknown_unit_rejected_not_guessed(self):
        r = self.bad(lambda d: d["recipes"][0].update(unit="kaste"))
        self.assertTrue(any("nezināma mērvienība" in e for e in r.errors))
        self.assertNotIn("R-LENTE", [x["code"] for x in r.library["recipes"]])
        r = self.bad(lambda d: d["catalog"][0].update(unit=""))
        self.assertTrue(any("nezināma mērvienība" in e for e in r.errors))

    def test_labour_unit_in_recipe_rejected(self):
        r = self.bad(lambda d: d["recipes"][0].update(unit="h"))
        self.assertTrue(any("darba stundas" in e for e in r.errors))

    def test_bad_values_and_duplicates(self):
        r = self.bad(lambda d: (d["catalog"][0].update(unit_price=-5), d["catalog"][1].update(price_valid_from="2026-13-40"),
                                d["recipes"][1].update(code=d["recipes"][0]["code"]), d["recipes"][2].update(driver="nezinams"),
                                d["labour"][0].update(group="Nav grupa")))
        text = " | ".join(r.errors)
        for needle in ("nenegatīvam", "nederīgs datums", "dublikāts kods", "nezināms draiveris", "nezināma grupa"):
            self.assertIn(needle, text)

    def test_missing_price_and_norm_stay_empty(self):
        r = self.bad(lambda d: (d["catalog"][0].update(unit_price=None), d["recipes"][0].update(norm=None)))
        self.assertEqual(r.errors, [])
        self.assertIsNone(r.library["catalog"][0]["unit_price"])
        self.assertIsNone(r.library["recipes"][0]["norm"])
        self.assertTrue(any("norma nav norādīta" in w for w in r.warnings))

    def test_historical_cannot_be_approved(self):
        r = self.bad(lambda d: d["recipes"][0].update(kind="vēsturisks koeficients", status=ST_APPROVED))
        self.assertEqual(r.library["recipes"][0]["status"], ST_HISTORICAL)
        self.assertTrue(any("nevar būt" in w for w in r.warnings))

    def test_tampered_checksum_downgrades_approvals(self):
        doc = json.loads(SAMPLE.read_text(encoding="utf-8"))
        doc["data"]["recipes"][0]["norm"] = 99.0
        r = parse_library(json.dumps(doc).encode("utf-8"))
        self.assertTrue(any("Kontrolsumma" in w for w in r.warnings))
        self.assertNotIn(ST_APPROVED, [e["status"] for e in r.library["recipes"] + r.library["labour"]])

    def test_file_level_errors(self):
        self.assertTrue(parse_library(b"nav json").errors)
        self.assertTrue(parse_library(json.dumps({"schema_version": 1, "app": "cits", "data": {}}).encode()).errors)
        self.assertTrue(parse_library(json.dumps({"schema_version": 99, "app": "mlk-tametajs-biblioteka", "data": {}}).encode()).errors)
        self.assertTrue(parse_library(b"x" * (5 * 1024 * 1024 + 1)).errors)

    def test_kit_validation(self):
        r = self.bad(lambda d: d["kits"][0].update(default_level="nav"))
        self.assertTrue(any("noklusējuma līmenis" in e for e in r.errors))
        r = self.bad(lambda d: d["kits"][0]["positions"][0]["options"].update({"nezināms": "X"}))
        self.assertTrue(any("nav komplekta līmeņu sarakstā" in e for e in r.errors))
        r = self.bad(lambda d: d["kits"][0]["positions"][0].update(opening="x"))
        self.assertTrue(any("opening" in e for e in r.errors))


class TestApply(unittest.TestCase):
    def setUp(self):
        self.lib = lib_of()
        self.p = ad_geometry()

    def test_preview_does_not_change_project_and_matches_apply(self):
        before = copy.deepcopy(self.p)
        preview = preview_library(self.p, self.lib, as_of=TODAY)
        self.assertEqual(self.p, before)
        real = apply_library(self.p, self.lib, as_of=TODAY)
        self.assertEqual(preview.added, real.added)
        self.assertTrue(real.added)

    def test_reapply_is_idempotent_no_duplicates(self):
        apply_library(self.p, self.lib, as_of=TODAY)
        snap = copy.deepcopy(self.p)
        second = apply_library(self.p, self.lib, as_of=TODAY)
        self.assertEqual((second.added, second.updated), ([], []))
        self.assertEqual(self.p["recipes"], snap["recipes"])
        self.assertEqual(self.p["labour"]["operations"], snap["labour"]["operations"])
        codes = [r["lib_code"] for r in self.p["recipes"]]
        self.assertEqual(len(codes), len(set(codes)))

    def test_changed_library_entry_updates_in_place_keeps_id(self):
        apply_library(self.p, self.lib, as_of=TODAY)
        rid = next(r["id"] for r in self.p["recipes"] if r["lib_code"] == "R-LENTE")
        data = build_library()
        data["recipes"][0]["norm"] = 4.0
        rep = apply_library(self.p, lib_of(data), as_of=TODAY)
        self.assertIn("R-LENTE", [c for c, _ in rep.updated])
        row = next(r for r in self.p["recipes"] if r["lib_code"] == "R-LENTE")
        self.assertEqual((row["id"], row["norm"]), (rid, 4.0))
        self.assertEqual(len([r for r in self.p["recipes"] if r["lib_code"] == "R-LENTE"]), 1)

    def test_historical_not_applied_by_default_and_never_approved(self):
        rep = apply_library(self.p, self.lib, as_of=TODAY)
        self.assertIn("R-VESTURE", [c for c, _n, _w in rep.skipped])
        self.assertNotIn("R-VESTURE", [r["lib_code"] for r in self.p["recipes"]])
        p2 = ad_geometry()
        apply_library(p2, self.lib, as_of=TODAY, include_historical=True)
        hist = next(r for r in p2["recipes"] if r["lib_code"] == "R-VESTURE")
        self.assertFalse(hist["approved"])
        self.assertEqual(hist["lib_status"], ST_HISTORICAL)
        self.assertIn("VĒSTURISKS", hist["source"])
        e = estimate(p2)
        row = next(r for r in e.rows if r.material.startswith("Fasādes apdares patēriņš"))
        self.assertFalse(row.approved)
        op = next(o for o in p2["labour"]["operations"] if o["lib_code"] == "L-VESTURE")
        self.assertFalse(op["approved"])

    def test_status_mapping(self):
        apply_library(self.p, self.lib, as_of=TODAY)
        by = {r["lib_code"]: r for r in self.p["recipes"]}
        self.assertTrue(by["R-LENTE"]["approved"])
        self.assertFalse(by["R-NEAPST"]["approved"])
        self.assertEqual(by["R-NEAPST"]["lib_status"], ST_UNAPPROVED)

    def test_price_validity_and_source(self):
        rep = apply_library(self.p, self.lib, as_of=TODAY)
        reasons = dict(rep.prices_not_applied)
        self.assertIn("beigusies", reasons["SINT-VECA-CENA"])
        self.assertIn("tikai no", reasons["SINT-NAKOTNE"])
        self.assertIn("nav norādīta", reasons["SINT-BEZ-CENAS"])
        cat = {c["article"]: c for c in self.p["catalog"]}
        self.assertEqual(cat["SINT-LENTE"]["unit_price"], 1.8)
        self.assertEqual(cat["SINT-LENTE"]["price_valid_from"], "2026-01-01")
        self.assertEqual(cat["SINT-LENTE"]["price_source"], "sintētisks cenrādis")
        for art in ("SINT-VECA-CENA", "SINT-NAKOTNE", "SINT-BEZ-CENAS"):
            self.assertIsNone(cat[art]["unit_price"])            # cena netiek izdomāta
        later = apply_library(ad_geometry(), self.lib, as_of="2099-06-01")
        self.assertIn("SINT-NAKOTNE", later.prices_applied)

    def test_expired_price_does_not_erase_or_replace_existing_price(self):
        self.p["catalog"] = [{"article": "SINT-VECA-CENA", "name": "x", "unit": "gab.", "unit_price": 5.0}]
        apply_library(self.p, self.lib, as_of=TODAY)
        self.assertEqual(next(c for c in self.p["catalog"] if c["article"] == "SINT-VECA-CENA")["unit_price"], 5.0)

    def test_catalog_unit_conflict_skipped(self):
        self.p["recipes"] = [{"id": "u1", "group": "Stiprinājumi", "article": "SINT-LENTE", "name": "Mana lente", "unit": "gab.", "driver": "direct", "qty": 1}]
        rep = apply_library(self.p, self.lib, as_of=TODAY)
        self.assertTrue(any(c == "SINT-LENTE" and "mērvienība" in why for c, _n, why in rep.skipped))

    def test_existing_user_recipe_not_duplicated(self):
        self.p["recipes"] = [{"id": "u1", "group": "Stiprinājumi un hermetizācija", "name": "Hermetizācijas lente savienojumiem", "unit": "m",
                              "driver": "ext_len", "norm": 2.0}]
        from src.building_estimate import G_FASTEN
        self.p["recipes"][0]["group"] = G_FASTEN
        rep = apply_library(self.p, self.lib, as_of=TODAY)
        self.assertTrue(any(c == "R-LENTE" and "nedublē" in why for c, _n, why in rep.skipped))
        self.assertEqual(len([r for r in self.p["recipes"] if norm(r["name"]) == norm("Hermetizācijas lente savienojumiem")]), 1)

    def test_cannot_double_construction_layers(self):
        from src.building_estimate import G_EXT
        data = build_library()
        data["recipes"].append({"code": "R-SLANIS", "group": G_EXT, "name": "Fasādes apdare", "unit": "m²", "driver": "ext_net", "norm": 1.0,
                                "status": ST_APPROVED, "kind": "ģeometriska formula", "source": "SINT"})
        lib = lib_of(data)
        p = ad_geometry()
        p["layers_mode"] = "manual"
        p["layers"] = [{"id": "l1", "group": G_EXT, "name": "Fasādes apdare", "basis": "ext_net", "unit": "m²", "enabled": True, "approved": False}]
        rep = apply_library(p, lib, as_of=TODAY)
        self.assertTrue(any(c == "R-SLANIS" and "dubultošana" in why for c, _n, why in rep.skipped))
        # arī ja receptes tiek pievienotas vēlāk (apejot piemērošanu), aprēķins bloķē dublēšanu
        p2 = ad_geometry()
        apply_library(p2, lib, as_of=TODAY)
        p2["layers_mode"] = "manual"
        p2["layers"] = [{"id": "l1", "group": G_EXT, "name": "Fasādes apdare", "basis": "ext_net", "unit": "m²", "enabled": True, "approved": False}]
        e = estimate(p2)
        self.assertTrue(any("Dubultošana: bibliotēkas recepte" in x for x in e.errors))

    def test_layer_dup_in_type_mode_is_checked_by_article(self):
        from src.building_estimate import G_EXT
        data = build_library()
        data["recipes"].append({"code": "R-ART", "group": G_EXT, "name": "Cits nosaukums", "article": "SINT-LENTE", "unit": "m", "driver": "ext_len",
                                "norm": 1.0, "status": ST_APPROVED, "kind": "ģeometriska formula", "source": "SINT"})
        p = ad_geometry()
        p["type_recipes"] = [{"id": "t1", "group": G_EXT, "name": "Latojums", "article": "SINT-LENTE", "enabled": True}]
        rep = apply_library(p, lib_of(data), as_of=TODAY)
        self.assertTrue(any(c == "R-ART" and "dubultošana" in why for c, _n, why in rep.skipped))

    def test_library_reusable_in_another_project(self):
        a, b = ad_geometry(), empty_project("Cits projekts")
        ra = apply_library(a, self.lib, as_of=TODAY)
        rb = apply_library(b, self.lib, as_of=TODAY)
        self.assertEqual(sorted(c for c, _ in ra.added), sorted(c for c, _ in rb.added))
        self.assertEqual(len(a["recipes"]), len(b["recipes"]))
        e = estimate(b)                                  # tukšā projektā ģeometrijas nav: draiveri paliek neaprēķināti, nekas netiek izdomāts
        self.assertTrue(all(r.qty is None for r in e.rows if r.article in ("SINT-LENTE", "SINT-LENSKAVA")))


def norm(text):
    return " ".join(str(text).lower().split())


class TestDriversAndEstimate(unittest.TestCase):
    def test_new_drivers_registered(self):
        for key in ("ext_gross", "int_gross", "roof_gross", "facade_win", "roof_win", "rooms", "rooms_wet", "rooms_kitchen", "kitchen_len"):
            self.assertIn(key, DRIVERS)

    def test_roof_and_facade_windows_separate_and_win_unchanged(self):
        p = ad_geometry()
        p["openings"] = [{"kind": "Logs", "name": "L", "width_mm": 1200, "height_mm": 1500, "count": 6, "wall": "Ārsiena"},
                         {"kind": "Logs", "name": "JL", "width_mm": 780, "height_mm": 1400, "count": 2, "wall": "Jumts"},
                         {"kind": "Durvis", "name": "D", "width_mm": 1000, "height_mm": 2100, "count": 1, "wall": "Ārsiena"}]
        p["labour"]["operations"] = [
            {"id": f"o{i}", "group": G_OPEN, "name": f"op {d}", "driver": d, "unit": "gab.", "norm_h": 1.0, "enabled": True} for i, d in enumerate(("facade_win", "roof_win", "win"))]
        e = estimate(p)
        hours = {l.name: l.hours for l in e.labour}
        self.assertEqual((hours["op facade_win"], hours["op roof_win"], hours["op win"]), (6.0, 2.0, 8.0))     # «win» = visi logi (nemainīts)

    def test_rooms_and_kitchen_len_drivers_and_missing_stays_uncalculated(self):
        p = ad_geometry()
        p["labour"]["operations"] = [
            {"id": "a", "group": G_SANIT, "name": "wet", "driver": "rooms_wet", "unit": "gab.", "norm_h": 2.0, "enabled": True},
            {"id": "b", "group": G_FURN, "name": "kitchen", "driver": "kitchen_len", "unit": "m", "norm_h": 3.0, "enabled": True},
            {"id": "c", "group": G_FURN, "name": "bedrooms", "driver": "rooms_bed", "unit": "gab.", "norm_h": 1.0, "enabled": True}]
        e = estimate(p)
        h = {l.name: l.hours for l in e.labour}
        self.assertEqual((h["wet"], h["kitchen"]), (4.0, 12.0))
        self.assertIsNone(h["bedrooms"])                              # guļamistabu nav ievadīts → netiek izdomāts
        self.assertTrue(any("bedrooms" in m or "nav apjoma" in m for ms in e.missing.values() for m in ms))
        p["kitchen_len_m"] = None
        self.assertIsNone({l.name: l.hours for l in estimate(p).labour}["kitchen"])

    def test_gross_area_drivers(self):
        p = ad_geometry()
        p["recipes"] = [{"id": "g", "group": "Ārsienas", "name": "bruto", "unit": "m²", "driver": "ext_gross", "norm": 1.0, "enabled": True}]
        from src.building_estimate import G_EXT
        p["recipes"][0]["group"] = G_EXT
        e = estimate(p)
        row = next(r for r in e.rows if r.material == "bruto")
        self.assertAlmostEqual(row.qty, e.areas["ext_walls_gross_m2"], 6)

    def test_geometry_and_kit_change_recalculate_but_fixed_forecast_unchanged(self):
        lib = lib_of()
        p = ad_geometry()
        apply_library(p, lib, as_of=TODAY)
        e1 = estimate(p)
        snap = freeze_forecast(p, e1, "AD prognoze", created="2026-11-26")
        add_version(p, snap)
        frozen = copy.deepcopy(p["versions"][0])
        # ģeometrijas maiņa: virtuves garums un telpas
        p["kitchen_len_m"] = 6.0
        p["rooms"].append({"id": "r3", "name": "Vannas 2", "type": "wet", "count": 1})
        # komplektācijas maiņa
        p["lib"]["kits"]["K-VIRTUVE"] = {"level": "augstāks"}
        apply_kits(p, lib)
        e2 = estimate(p)
        self.assertNotEqual(e1.budget()["labour_hours"], e2.budget()["labour_hours"])
        self.assertNotEqual(e1.budget()["materials"], e2.budget()["materials"])
        self.assertEqual(p["versions"][0], frozen)                    # fiksētā prognoze nemainās
        self.assertEqual(frozen["budget"]["materials"], e1.budget()["materials"])


class TestKits(unittest.TestCase):
    def setUp(self):
        self.lib = lib_of()
        self.p = ad_geometry()
        apply_library(self.p, self.lib, as_of=TODAY)

    def kit_lines(self, code):
        return [r for r in self.p["recipes"] if r.get("lib_kit") == code]

    def test_standard_default_applied(self):
        lines = self.kit_lines("K-VIRTUVE")
        self.assertEqual(sorted(l["article"] for l in lines), ["SINT-PLITS-STD", "SINT-SINK-STD", "SINT-VIRT-STD"])
        self.assertTrue(all(l["detail"] == "komplekts" and l["assumption"] and "standarta" in l["assumption"] for l in lines))
        self.assertTrue(all(not l["approved"] for l in lines))

    def test_level_choice_replaces_standard_no_double_counting(self):
        before = estimate(self.p)
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"level": "augstāks"}
        apply_kits(self.p, self.lib)
        lines = self.kit_lines("K-VIRTUVE")
        self.assertEqual(sorted(l["article"] for l in lines), ["SINT-PLITS-AUGST", "SINT-SINK-AUGST", "SINT-VIRT-AUGST"])
        self.assertEqual(len(lines), 3)
        after = estimate(self.p)
        self.assertEqual(len([r for r in after.rows if r.group == G_FURN and r.material.startswith("Virtuves komplekts")]), 3)
        self.assertGreater(after.budget()["materials"], before.budget()["materials"])
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"level": "standarta"}
        apply_kits(self.p, self.lib)
        self.assertEqual(sorted(l["article"] for l in self.kit_lines("K-VIRTUVE")), ["SINT-PLITS-STD", "SINT-SINK-STD", "SINT-VIRT-STD"])
        self.assertAlmostEqual(estimate(self.p).budget()["materials"], before.budget()["materials"], 6)

    def test_level_switch_keeps_row_ids(self):
        ids = {l["lib_code"]: l["id"] for l in self.kit_lines("K-VIRTUVE")}
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"level": "augstāks"}
        apply_kits(self.p, self.lib)
        self.assertEqual({l["lib_code"]: l["id"] for l in self.kit_lines("K-VIRTUVE")}, ids)

    def test_replace_single_position_level_and_article(self):
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"level": "standarta", "pos_levels": {"plits": "augstāks"}, "pos_articles": {"jaucejkrans": "SINT-SINK-AUGST"}}
        apply_kits(self.p, self.lib)
        arts = {l["lib_code"].split("/")[1]: l["article"] for l in self.kit_lines("K-VIRTUVE")}
        self.assertEqual(arts, {"iekarta": "SINT-VIRT-STD", "plits": "SINT-PLITS-AUGST", "jaucejkrans": "SINT-SINK-AUGST"})

    def test_skip_position(self):
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"skip": ["plits"]}
        apply_kits(self.p, self.lib)
        self.assertEqual(len(self.kit_lines("K-VIRTUVE")), 2)

    def test_add_position_and_duplicate_guard(self):
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"add": [{"name": "Atvilktņu sistēma", "unit": "gab.", "qty": 2, "article": "SINT-WC-STD"},
                                                      {"name": "Dublikāts", "unit": "gab.", "qty": 1, "article": "SINT-PLITS-STD"},
                                                      {"name": "Bez daudzuma", "unit": "gab."}]}
        rep = apply_kits(self.p, self.lib)
        codes = [l["lib_code"] for l in self.kit_lines("K-VIRTUVE")]
        self.assertIn("K-VIRTUVE/+1", codes)
        self.assertEqual(len(codes), 4)
        reasons = " | ".join(w for _c, _n, w in rep.skipped)
        self.assertIn("dubultošana", reasons)
        self.assertIn("papildu pozīcijai", reasons)

    def test_swap_does_not_make_standard_plus_chosen(self):
        # aizstājot standarta pozīciju ar citu artikulu, standarta artikuls vairs nav projektā
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"pos_articles": {"plits": "SINT-PLITS-AUGST"}}
        apply_kits(self.p, self.lib)
        arts = [l["article"] for l in self.p["recipes"]]
        self.assertNotIn("SINT-PLITS-STD", arts)
        self.assertEqual(arts.count("SINT-PLITS-AUGST"), 1)

    def test_disabled_kit_removed(self):
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"enabled": False}
        rep = apply_kits(self.p, self.lib)
        self.assertEqual(self.kit_lines("K-VIRTUVE"), [])
        self.assertTrue(any(c == "K-VIRTUVE" for c, _n, _w in rep.skipped))

    def test_user_line_covering_kit_blocks_it(self):
        p = ad_geometry()
        p["recipes"] = [{"id": "u", "group": G_FURN, "name": "Mana virtuve (AD)", "unit": "kompl.", "driver": "direct", "qty": 1, "detail": "komplekts"}]
        rep = apply_library(p, self.lib, as_of=TODAY)
        self.assertEqual([r for r in p["recipes"] if r.get("lib_kit") == "K-VIRTUVE"], [])
        self.assertTrue(any(c == "K-VIRTUVE" and "dubultošana" in w for c, _n, w in rep.skipped))

    def test_openings_already_in_estimate_are_not_doubled_by_window_kit(self):
        self.assertTrue(self.kit_lines("K-LOGI"))                    # nav atveru → komplekts dod logus
        p = ad_geometry()
        p["openings"] = [{"kind": "Logs", "name": "L", "width_mm": 1200, "height_mm": 1500, "count": 6, "wall": "Ārsiena"},
                         {"kind": "Durvis", "name": "D", "width_mm": 1000, "height_mm": 2100, "count": 1, "wall": "Ārsiena"}]
        rep = apply_library(p, self.lib, as_of=TODAY)
        codes = [r["lib_code"] for r in p["recipes"] if r.get("lib_kit") == "K-LOGI"]
        self.assertEqual(codes, ["K-LOGI/jlogi"])  # fasādes logi un durvis jau ir atveres rindas
        self.assertTrue(any("K-LOGI/logi" == c for c, _n, _w in rep.skipped))

    def test_kit_total_changes_with_level(self):
        std = kit_total(self.p, self.lib, "K-VIRTUVE")
        self.p["lib"]["kits"]["K-VIRTUVE"] = {"level": "augstāks"}
        high = kit_total(self.p, self.lib, "K-VIRTUVE")
        self.assertAlmostEqual(std, 4 * 520 + 380 + 95)
        self.assertAlmostEqual(high, 4 * 780 + 690 + 210)

    def test_kits_priced_without_option_list_and_complete_estimate(self):
        e = estimate(self.p)
        self.assertEqual(e.errors, [])
        furn = rows_of(e, G_FURN)
        self.assertTrue(furn and all(r.unit_price is not None for r in furn if r.material.startswith("Virtuves komplekts")))
        self.assertTrue(all(r.detail == "komplekts" for r in furn if r.material.startswith("Virtuves komplekts")))


class TestPersistence(unittest.TestCase):
    def test_project_roundtrip_keeps_library_state_rooms_and_kit_choice(self):
        lib = lib_of()
        p = ad_geometry()
        apply_library(p, lib, as_of=TODAY, kit_choices={"K-VIRTUVE": {"level": "augstāks"}})
        raw = export_project(p)
        got = import_project(raw)
        self.assertEqual(got.errors, [])
        q = got.project
        self.assertEqual(q["lib"]["kits"], {"K-VIRTUVE": {"level": "augstāks"}})
        self.assertEqual(q["rooms"], p["rooms"])
        self.assertEqual(q["kitchen_len_m"], 4.0)
        self.assertEqual(sorted(r["lib_code"] for r in q["recipes"]), sorted(r["lib_code"] for r in p["recipes"]))

    def test_old_project_without_new_keys_loads(self):
        p = empty_project("vecs")
        for key in ("rooms", "kitchen_len_m", "lib"):
            p.pop(key)
        got = import_project(export_project(p))
        self.assertEqual(got.errors, [])
        self.assertEqual(got.project["rooms"], [])
        self.assertEqual(got.project["lib"]["kits"], {})


APP = str(Path(__file__).resolve().parent.parent / "app.py")


def ui_app(project):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.session_state["bp_project"] = project
    at.session_state["bp_version"] = 1
    return at.run()


class TestUi(unittest.TestCase):
    def test_library_section_visible_and_demo_load_preview_then_apply(self):
        at = ui_app(ad_geometry())
        self.assertFalse(at.exception)
        at.button(key="bp_lib_demo").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Sintētiskā bibliotēka" in s.value for s in at.success))
        self.assertEqual(at.session_state["bp_project"]["recipes"], [])          # priekšskatījums projektu nemaina
        at.button(key="bp_lib_apply_1").click().run()
        self.assertFalse(at.exception)
        project = at.session_state["bp_project"]
        self.assertTrue(project["recipes"])
        self.assertTrue(estimate(project).rows)
        n = len(project["recipes"])
        at.button(key="bp_lib_apply_2").click().run()                              # atkārtota piemērošana nedublē
        self.assertEqual(len(at.session_state["bp_project"]["recipes"]), n)

    def test_kit_level_switch_in_ui_replaces_standard_and_keeps_tags_after_table_edit(self):
        at = ui_app(ad_geometry())
        at.button(key="bp_lib_demo").click().run()
        at.button(key="bp_lib_apply_1").click().run()
        ver = at.session_state["bp_version"]
        at.selectbox(key=f"bp_kit_lvl_K-VIRTUVE_{ver}").set_value("augstāks").run()
        self.assertFalse(at.exception)
        project = at.session_state["bp_project"]
        arts = sorted(r["article"] for r in project["recipes"] if r.get("lib_kit") == "K-VIRTUVE")
        self.assertEqual(arts, ["SINT-PLITS-AUGST", "SINT-SINK-AUGST", "SINT-VIRT-AUGST"])
        self.assertTrue(all(r.get("lib_code") for r in project["recipes"]))        # tabulu pārbūve nezaudē bibliotēkas atzīmes
        self.assertEqual(estimate(project).errors, [])

    def test_rooms_and_kitchen_inputs_present(self):
        at = ui_app(ad_geometry())
        self.assertTrue(any("Virtuves garums" in n.label for n in at.number_input))


if __name__ == "__main__":
    unittest.main()
