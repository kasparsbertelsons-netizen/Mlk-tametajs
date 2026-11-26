"""Issue #16: AD PDF → pilnas ēkas tāmes kandidāti, apstiprināšana, ģeometrijas kategorijas (zelmiņi, jumta slīpnes, bruto/neto, tipi).

Tikai SINTĒTISKS PDF (tools/synthetic_ad_building.py). Gaidāmās vērtības tiek rēķinātas testā ar vienkāršu aritmētiku.
"""
import math
import unittest

import pymupdf

from src.ad_building import HIGH, LOW, MEDIUM, apply_candidates, parse_layers, scan_ad_building
from src.building_estimate import (
    G_EXT, G_INT, G_ROOF, ST_MISSING, empty_project, estimate,
)
from tools.synthetic_ad_building import build_ad_building_pdf

ROOF_SLOPE = 24.0 * 2.5 / math.cos(math.radians(20))              # bruto vienai slīpnei
OPEN_ROOF = 2 * 0.78 * 1.4


def kinds(scan, kind):
    return [c for c in scan.candidates if c.kind == kind]


def build_project(scan=None, accept=lambda c: c.confidence != LOW, **kw):
    scan = scan or scan_ad_building(build_ad_building_pdf())
    p = empty_project("T", "clt")
    report = apply_candidates(p, scan, [c.id for c in scan.candidates if accept(c)], **kw)
    return p, scan, report


class TestScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = build_ad_building_pdf()
        cls.scan = scan_ad_building(cls.pdf)

    def test_every_candidate_has_page_source_confidence_evidence(self):
        for c in self.scan.candidates:
            self.assertGreaterEqual(c.page, 1, c.id)
            self.assertIn(c.source, ("teksts", "vektors"))
            self.assertIn(c.confidence, (HIGH, MEDIUM, LOW))
            self.assertTrue(c.evidence.strip(), c.id)
            self.assertTrue(c.kind and c.label)

    def test_pages_are_classified(self):
        self.assertEqual({p["page"]: p["kind"] for p in self.scan.pages}, {1: "other", 2: "floor", 3: "other", 4: "other", 5: "roof", 6: "other"})

    def test_modules_from_vector_geometry_and_facade_contour_is_not_a_module(self):
        mods = kinds(self.scan, "module")
        self.assertEqual(sorted((m.data["length_mm"], m.data["width_mm"]) for m in mods), [(8000, 4000), (12000, 4000)])
        self.assertTrue(all(m.source == "vektors" and m.page == 2 for m in mods))
        facade = kinds(self.scan, "facade_contour")[0]
        self.assertEqual((facade.data["length_mm"], facade.data["width_mm"]), (20240, 4240))
        self.assertTrue(any("nav grīdas pamatrāmis" in n for n in facade.notes))
        self.assertNotIn((20240, 4240), [(m.data["length_mm"], m.data["width_mm"]) for m in mods])      # nobīde netiek izsecināta

    def test_rooms_terrace_and_floor_net(self):
        rooms = kinds(self.scan, "room")
        self.assertEqual(sorted(r.data["area_m2"] for r in rooms), [8.0, 8.0, 12.0, 14.0, 30.0])
        terrace = kinds(self.scan, "terrace")[0]
        self.assertEqual(terrace.data["area_m2"], 12.0)
        self.assertNotIn("Terase", [r.data["name"] for r in rooms])
        net = kinds(self.scan, "floor_net")[0]
        self.assertEqual(net.data["area_m2"], 72.0)                    # telpu summa BEZ terases
        self.assertEqual(net.confidence, MEDIUM)
        self.assertTrue(net.data["derived"])

    def test_ceiling_height(self):
        self.assertEqual(kinds(self.scan, "ceiling_height")[0].data["height_mm"], 2700)

    def test_wall_segments_with_types_and_clt(self):
        walls = {w.data["name"]: w for w in kinds(self.scan, "wall")}
        self.assertEqual(set(walls), {"N", "S", "A", "B", "I1", "I2", "I3", "X"})
        n = walls["N"].data
        self.assertEqual((n["wall"], n["length_m"], n["height_mm"], n["type"], n["clt_mm"]), ("Ārsiena", 20.0, 2700.0, "ĀS1", 100.0))
        self.assertEqual(walls["A"].data["clt_mm"], 140.0)                # atšķirīgi CLT biezumi pa posmiem
        self.assertEqual(walls["I2"].data["wall"], "Iekšsiena")
        self.assertEqual(walls["N"].confidence, HIGH)
        x = walls["X"]
        self.assertEqual((x.confidence, x.status), (LOW, "jāpārbauda"))   # nolasāms tikai augstums: garums/veids nav → manuāli
        self.assertIsNone(x.data["length_m"])
        self.assertIsNone(x.data["wall"])

    def test_gables(self):
        gables = kinds(self.scan, "gable")
        self.assertEqual([(g.data["base_m"], g.data["height_m"], g.data["type"], g.data["clt_mm"]) for g in gables], [(4.0, 1.5, "ĀS2", 140.0)] * 2)

    def test_openings_exterior_interior_and_roof_separately(self):
        ops = kinds(self.scan, "opening")
        by = [(o.data["name"], o.data["wall"], o.data["count"], o.data["segment"]) for o in ops]
        self.assertIn(("L1", "Ārsiena", 3, "N"), by)
        self.assertIn(("L1", "Ārsiena", 3, "S"), by)
        self.assertIn(("D1", "Ārsiena", 1, "S"), by)
        self.assertEqual(sorted(s for n, w, c, s in by if n == "D2"), ["I1", "I2", "I3"])
        self.assertIn(("JL1", "Jumts", 2, "Slīpne A"), by)
        self.assertEqual(len([b for b in by if b[0] == "L1"]), 2)          # dublikāts netiek veidots kā trešais kandidāts

    def test_duplicate_and_unlocated_openings_are_flagged(self):
        first = next(o for o in kinds(self.scan, "opening") if o.data["name"] == "L1" and o.data["segment"] == "N")
        self.assertTrue(any("dublikāts ignorēts" in n for n in first.notes))
        self.assertEqual(first.status, "kandidāts")                      # dublikāta piezīme kandidātu neapšauba
        d3 = next(o for o in kinds(self.scan, "opening") if o.data["name"] == "D3")
        self.assertEqual((d3.confidence, d3.status, d3.data["wall"]), (LOW, "jāpārbauda", None))
        self.assertTrue(any("Atrašanās vieta" in i for i in d3.issues))

    def test_plan_tag_counts_match_schedule(self):
        for o in kinds(self.scan, "opening"):
            self.assertFalse(any("marķējumi" in i for i in o.issues), (o.label, o.issues))

    def test_roof_slopes_and_informational_angle(self):
        slopes = kinds(self.scan, "roof_slope")
        self.assertEqual(len(slopes), 2)
        for s in slopes:
            self.assertAlmostEqual(s.data["gross_m2"], ROOF_SLOPE, 3)
            self.assertEqual((s.page, s.confidence), (5, HIGH))
        self.assertEqual(slopes[0].data["clt_mm"], 120.0)
        self.assertEqual(slopes[1].data["type"], "JK2")
        self.assertIsNone(slopes[1].data["clt_mm"])                       # B slīpnei CLT biezums nāk no tipa
        self.assertEqual(kinds(self.scan, "roof_angle")[0].data["angle_deg"], 20.0)

    def test_construction_types_layers_multiple_laths_and_both_sides(self):
        types = {t.data["code"]: t.data for t in kinds(self.scan, "construction_type")}
        self.assertEqual(set(types), {"ĀS1", "ĀS2", "IS1", "JK1", "JK2", "GR1"})
        as1 = types["ĀS1"]["layers"]
        laths = [(l["name"], l["step_mm"]) for l in as1 if l["kind"] == "latojums"]
        self.assertEqual(laths, [("latojums", 600.0), ("latojums", 400.0), ("instalāciju latojums", 600.0)])      # vairākas latojuma kārtas
        self.assertEqual([l["thickness_mm"] for l in as1 if l["kind"] == "CLT"], [100.0])
        self.assertEqual([l["kind"] for l in as1 if l["name"] == "skrūves"], ["stiprinājums"])
        gkl = next(l for l in types["IS1"]["layers"] if l["kind"] == "apdare")
        self.assertEqual(gkl["norm"], 2.0)                                # «abās pusēs»
        gr = next(t for t in kinds(self.scan, "construction_type") if t.data["code"] == "GR1")
        self.assertTrue(gr.issues)

    def test_parse_layers_helper(self):
        layers = parse_layers("CLT 100 mm; latojums 50 mm c/c 600; kaut kas nezināms")
        self.assertEqual([(l["kind"], l["thickness_mm"], l["step_mm"], l["recognised"]) for l in layers],
                         [("CLT", 100.0, None, True), ("latojums", 50.0, 600.0, True), ("cits", None, None, False)])

    def test_image_only_or_invalid_pdf(self):
        doc = pymupdf.open()
        doc.new_page()
        blank = doc.tobytes()
        scan = scan_ad_building(blank)
        self.assertEqual(scan.candidates, [])
        self.assertTrue(any("Nav atpazīts neviens lauks" in n for n in scan.notes))
        with self.assertRaises(ValueError):
            scan_ad_building(b"nav pdf")
        with self.assertRaises(ValueError):
            scan_ad_building(b"%PDF" + b"0" * (31 * 1024 * 1024))

    def test_deterministic(self):
        again = scan_ad_building(build_ad_building_pdf())
        self.assertEqual([(c.kind, c.label, c.page) for c in again.candidates], [(c.kind, c.label, c.page) for c in self.scan.candidates])


class TestApply(unittest.TestCase):
    def test_only_accepted_candidates_are_applied_and_nothing_else(self):
        scan = scan_ad_building(build_ad_building_pdf())
        p = empty_project("T", "clt")
        only = [c.id for c in scan.candidates if c.kind == "wall" and c.data["name"] == "N"]
        rep = apply_candidates(p, scan, only)
        self.assertEqual(len(rep.applied), 1)
        self.assertEqual([w["name"] for w in p["ext_walls"]], ["N"])
        for key in ("modules", "int_walls", "openings", "gables", "roof_slopes", "construction_types", "terraces"):
            self.assertEqual(p[key], [], key)
        self.assertIsNone(p["floor_net_m2"])

    def test_incomplete_or_unlocated_items_are_not_transferred(self):
        p, scan, rep = build_project(accept=lambda c: True)               # lietotājs apstiprina VISU, arī nenolasāmo
        why = dict(rep.skipped)
        x = next(c.id for c in scan.candidates if c.kind == "wall" and c.data["name"] == "X")
        d3 = next(c.id for c in scan.candidates if c.kind == "opening" and c.data["name"] == "D3")
        self.assertIn("trūkst", why[x])
        self.assertIn("atrašanās vieta", why[d3])
        self.assertNotIn("X", [w["name"] for w in p["ext_walls"] + p["int_walls"]])
        self.assertNotIn("D3", [o["name"] for o in p["openings"]])
        self.assertTrue(any("neesamt" in w or "informatīva" in w for w in why.values()))

    def test_provenance_records_page_source_confidence_and_user_confirmation(self):
        p, scan, rep = build_project()
        fields = p["ad_import"]["fields"]
        self.assertTrue(fields)
        for f in fields:
            self.assertTrue(f["confirmed_by_user"])
            self.assertGreaterEqual(f["page"], 2)
            self.assertIn(f["confidence"], (HIGH, MEDIUM))
        self.assertEqual(p["ad_import"]["stage"], "AD")
        assumed = [f for f in fields if f["field"] == "ceiling_m2"]
        self.assertTrue(assumed and "PIEŅĒMUMS" in assumed[0]["note"])

    def test_ceiling_assumption_is_optional(self):
        p, _s, _r = build_project(ceiling_as_floor=False)
        self.assertEqual(p["floor_net_m2"], 72.0)
        self.assertIsNone(p["ceiling_m2"])

    def test_add_mode_does_not_duplicate_same_source_and_keeps_manual_data(self):
        scan = scan_ad_building(build_ad_building_pdf())
        p = empty_project("T", "clt")
        p["modules"] = [{"name": "Mans modulis", "length_mm": 12000, "width_mm": 4000, "axes": "", "confirmed": False}]
        ids = [c.id for c in scan.candidates if c.confidence != LOW]
        rep = apply_candidates(p, scan, ids)
        self.assertEqual(len(p["modules"]), 3)                            # identitāte NAV izmērs: manuālais modulis netiek zaudēts/aizstāts
        self.assertEqual(p["modules"][0]["name"], "Mans modulis")
        self.assertTrue(any("sakrīt ar esošo moduli «Mans modulis»" in n for n in rep.notes))
        n_walls = len(p["ext_walls"])
        rep2 = apply_candidates(p, scan, ids)                             # atkārtota pārnese no TĀ PAŠA avota nedublē
        self.assertEqual(len(p["modules"]), 3)
        self.assertEqual(len(p["ext_walls"]), n_walls)
        self.assertTrue(any("jau ir pārnests" in why for _i, why in rep2.skipped))

    def test_replace_mode_replaces_only_chosen_categories(self):
        scan = scan_ad_building(build_ad_building_pdf())
        p = empty_project("T", "clt")
        p["terraces"] = [{"name": "Sena", "area_m2": 3.0}]
        p["ext_walls"] = [{"name": "vecā", "length_m": 5.0}]
        mod_ids = [c.id for c in scan.candidates if c.kind == "module"]
        apply_candidates(p, scan, mod_ids, mode="replace")
        self.assertEqual(len(p["modules"]), 2)
        self.assertEqual(p["terraces"][0]["name"], "Sena")                # citas kategorijas nav skartas
        self.assertEqual(p["ext_walls"][0]["name"], "vecā")

    def test_modules_applied_are_user_confirmed_with_fingerprint(self):
        p, _s, _r = build_project()
        self.assertTrue(all(m["confirmed"] for m in p["modules"]))
        self.assertEqual(set(p["module_fp"]), {"0", "1"})

    def test_type_recipes_mode_switch(self):
        p, _s, _r = build_project()
        self.assertEqual(p["layers_mode"], "types")
        p2, _s2, _r2 = build_project(use_type_recipes=False)
        self.assertEqual(p2["layers_mode"], "manual")
        self.assertTrue(p2["type_recipes"])                               # receptes ir, bet režīms paliek manuāls

    def test_applied_type_recipes_have_no_invented_norms_or_prices(self):
        p, _s, _r = build_project()
        self.assertTrue(all(r["norm"] is None or r["name"].startswith("ģipškartons abās") for r in p["type_recipes"]))
        self.assertTrue(all(r["article"] is None and not r["approved"] for r in p["type_recipes"]))


class TestEstimateFromAd(unittest.TestCase):
    """Neatkarīgi rēķināti kontroles lielumi sintētiskajam AD paraugam."""

    @classmethod
    def setUpClass(cls):
        cls.p, cls.scan, _ = build_project()
        cls.p["clt"]["roof"]["enabled"] = True
        cls.e = estimate(cls.p)
        cls.a = cls.e.areas

    def row(self, text, group=None):
        found = [r for r in self.e.rows if text in r.material and (group is None or r.group == group)]
        self.assertEqual(len(found), 1, (text, [r.material for r in found]))
        return found[0]

    def test_exterior_walls_gables_and_openings_once(self):
        self.assertAlmostEqual(self.a["ext_walls_gross_m2"], 48 * 2.7 + 2 * 0.5 * 4 * 1.5, 6)            # 135,6
        self.assertAlmostEqual(self.a["gables_m2"], 6.0, 6)
        self.assertAlmostEqual(self.a["openings_ext_m2"], 6 * 1.2 * 1.5 + 2.1, 6)                         # dublikāts L1/N netiek atskaitīts divreiz
        self.assertAlmostEqual(self.a["ext_walls_net_m2"], 135.6 - 12.9, 6)
        self.assertEqual(self.e.errors, [])

    def test_roof_gross_and_net_are_separate_and_roof_window_deducted_once(self):
        self.assertAlmostEqual(self.a["roof_gross_m2"], 2 * ROOF_SLOPE, 5)
        self.assertAlmostEqual(self.a["openings_roof_m2"], OPEN_ROOF, 6)
        self.assertAlmostEqual(self.a["roof_net_m2"], 2 * ROOF_SLOPE - OPEN_ROOF, 5)
        self.assertNotAlmostEqual(self.a["roof_gross_m2"], self.a["roof_net_m2"], 1)
        self.assertEqual(self.a["roof_m2"], self.a["roof_net_m2"])                                         # «roof» bāze = neto

    def test_type_areas_per_segment_with_assigned_openings(self):
        t = self.a["type_areas"]
        self.assertAlmostEqual(t["ext:ĀS1"], 2 * 20 * 2.7 - (3 * 1.8) - (3 * 1.8 + 2.1), 6)               # 95,1
        self.assertAlmostEqual(t["ext:ĀS2"], 2 * 4 * 2.7 + 6.0, 6)                                         # sienas + zelmiņi = 27,6
        self.assertAlmostEqual(t["int:IS1"], (4 + 3 + 2.5) * 2.7 - 3 * 0.8 * 2.1, 6)                      # 20,61
        self.assertAlmostEqual(t["roof:JK1"], ROOF_SLOPE - OPEN_ROOF, 5)                                   # jumta logs piesaistīts A slīpnei
        self.assertAlmostEqual(t["roof:JK2"], ROOF_SLOPE, 5)
        self.assertAlmostEqual(t["ext:ĀS1"] + t["ext:ĀS2"], self.a["ext_walls_net_m2"], 6)                 # tipu summa = kopējais neto

    def test_clt_rows_have_different_thicknesses_per_segment_and_slope(self):
        self.assertAlmostEqual(self.row("CLT ārsienu paneļi 100 mm").qty, 95.1, 6)
        self.assertAlmostEqual(self.row("CLT ārsienu paneļi 140 mm").qty, 27.6, 6)
        self.assertAlmostEqual(self.row("CLT iekšsienu paneļi 80 mm").qty, 20.61, 6)
        self.assertAlmostEqual(self.row("CLT jumta paneļi 120 mm").qty, (ROOF_SLOPE - OPEN_ROOF) * 0.12 / 0.12, 5)   # m² (cena pēc m²)
        self.assertEqual(self.row("CLT jumta paneļi 100 mm").qty, self.row("CLT jumta paneļi 100 mm").qty)
        self.assertAlmostEqual(self.row("CLT jumta paneļi 100 mm").alt_qty, ROOF_SLOPE * 0.1, 5)          # B slīpne: biezums no tipa JK2

    def test_clt_total_volume_matches_sum_of_parts(self):
        vols = [95.1 * .1, 27.6 * .14, 20.61 * .08, (ROOF_SLOPE - OPEN_ROOF) * .12, ROOF_SLOPE * .1]
        got = sum(r.vol_net for r in self.e.rows if r.timber and r.material.startswith("CLT"))
        self.assertAlmostEqual(got, sum(vols), 5)

    def test_multiple_lath_layers_are_separate_rows(self):
        laths = [r for r in self.e.rows if r.material.startswith("latojums (ĀS1)") or r.material.startswith("instalāciju latojums")]
        self.assertEqual(sorted(round(r.qty, 3) for r in laths), sorted([round(95.1 * 1000 / 600, 3), round(95.1 * 1000 / 400, 3), round(95.1 * 1000 / 600, 3)]))
        self.assertEqual(len({r.row_id for r in laths}), 3)

    def test_missing_norm_and_both_sides_multiplier(self):
        screws = self.row("skrūves (ĀS1)")
        self.assertEqual((screws.qty, screws.status), (None, ST_MISSING))                                  # norma nav izdomāta
        self.assertTrue(any("norma" in m for m in self.e.missing[G_EXT]))
        self.assertAlmostEqual(self.row("ģipškartons abās pusēs (IS1)").qty, 20.61 * 2, 6)

    def test_gable_area_is_half_base_times_height(self):
        p = empty_project("T", "clt")
        p["gables"] = [{"name": "Z", "base_m": 5.0, "height_m": 2.0}]
        p["ext_walls"] = [{"name": "W", "length_m": 10.0, "height_mm": 2500}]
        e = estimate(p)
        self.assertAlmostEqual(e.areas["ext_walls_gross_m2"], 25.0 + 5.0, 6)

    def test_types_mode_prevents_double_counting_with_global_layers(self):
        p, _s, _r = build_project()
        p["layers"].append({"id": "g1", "group": G_EXT, "name": "Fasādes apdare", "basis": "ext_net", "unit": "m²", "waste_pct": 10, "enabled": True})
        e = estimate(p)
        self.assertEqual([r for r in e.rows if r.material == "Fasādes apdare"], [])                       # tipu režīmā global slānis netiek skaitīts
        p["layers_mode"] = "manual"
        e2 = estimate(p)
        self.assertEqual(len([r for r in e2.rows if r.material == "Fasādes apdare"]), 2)                  # manuālais režīms saglabāts (noklusējuma + pievienotais slānis)
        self.assertEqual([r for r in e2.rows if r.material.endswith("(ĀS1)")], [])                       # manuālajā režīmā tipu receptes netiek skaitītas (nav dubultošanas)

    def test_unassigned_openings_with_several_segments_are_flagged_not_guessed(self):
        p, _s, _r = build_project()
        for o in p["openings"]:
            o["segment"] = ""                                                                              # piesaistes nav
        e = estimate(p)
        self.assertTrue(any("atveres bez posma piesaistes" in m for m in e.missing[G_EXT]))
        self.assertFalse(e.complete)

    def test_single_segment_gets_unassigned_openings_automatically(self):
        p = empty_project("T", "clt")
        p["ext_walls"] = [{"name": "W", "length_m": 10.0, "height_mm": 2500, "type": "T1", "clt_mm": 100}]
        p["openings"] = [{"kind": "Logs", "name": "L", "width_mm": 1000, "height_mm": 1000, "count": 2, "wall": "Ārsiena"}]
        p["clt"]["ext"].update(enabled=True, thickness_confirmed=True)
        e = estimate(p)
        self.assertAlmostEqual(e.areas["ext_walls_net_m2"], 25.0 - 2.0, 6)
        clt = next(r for r in e.rows if r.material.startswith("CLT ārsienu"))
        self.assertAlmostEqual(clt.qty, 25.0 - 2.0, 6)                                                     # m² (cena pēc m²)
        self.assertAlmostEqual(clt.alt_qty, (25.0 - 2.0) * 0.1, 6)

    def test_segment_clt_overrides_type_clt(self):
        p, _s, _r = build_project()
        for w in p["ext_walls"]:
            if w["name"] == "N":
                w["clt_mm"] = 120.0
        e = estimate(p)
        names = sorted(r.material for r in e.rows if r.material.startswith("CLT ārsienu"))
        self.assertEqual(names, ["CLT ārsienu paneļi 100 mm", "CLT ārsienu paneļi 120 mm", "CLT ārsienu paneļi 140 mm"])

    def test_roof_gross_basis_is_available_for_layers(self):
        p, _s, _r = build_project()
        p["layers_mode"] = "manual"
        p["layers"].append({"id": "rg", "group": G_ROOF, "name": "Jumta palīgslānis", "basis": "roof_gross", "unit": "m²", "waste_pct": 0, "enabled": True})
        r = next(r for r in estimate(p).rows if r.material == "Jumta palīgslānis")
        self.assertAlmostEqual(r.qty, 2 * ROOF_SLOPE, 5)

    def test_unconfirmed_slope_is_not_counted(self):
        p, _s, _r = build_project()
        p["roof_slopes"][0]["confirmed"] = False
        e = estimate(p)
        self.assertIsNone(e.areas["roof_gross_m2"])
        self.assertTrue(any("nav apstiprināta" in m for m in e.missing[G_ROOF]))

    def test_openings_duplicates_in_project_are_not_deducted_twice(self):
        p, _s, _r = build_project()
        before = estimate(p).areas["openings_ext_m2"]
        p["openings"].append(dict(next(o for o in p["openings"] if o["name"] == "L1" and o["segment"] == "N")))
        e = estimate(p)
        self.assertEqual(e.areas["openings_ext_m2"], before)
        self.assertTrue(any("dublikāts netiek skaitīts" in w for w in e.warnings))


class TestIdenticalModules(unittest.TestCase):
    """Datu integritāte (ChatGPT, PR #17): divi fiziski atšķirīgi moduļi ar VIENĀDIEM L/W netiek apvienoti."""

    @classmethod
    def setUpClass(cls):
        from tools.synthetic_ad_building import build_identical_modules_pdf
        cls.pdf = build_identical_modules_pdf()
        cls.scan = scan_ad_building(cls.pdf)
        cls.ids = [c.id for c in cls.scan.candidates if c.kind == "module"]

    def test_scan_gives_two_distinct_candidates_with_same_size(self):
        mods = [c for c in self.scan.candidates if c.kind == "module"]
        self.assertEqual([(m.data["length_mm"], m.data["width_mm"]) for m in mods], [(12000, 4000)] * 2)
        keys = [m.data["source_key"] for m in mods]
        self.assertEqual(len(set(keys)), 2)
        self.assertTrue(all(k.startswith(self.scan.digest) for k in keys))

    def test_both_identical_modules_are_transferred_with_unique_names(self):
        p = empty_project("T")
        rep = apply_candidates(p, self.scan, self.ids)
        self.assertEqual(len(p["modules"]), 2)
        self.assertEqual(len({m["name"] for m in p["modules"]}), 2)
        self.assertEqual(len({m["source_key"] for m in p["modules"]}), 2)
        self.assertEqual(len(rep.applied), 2)
        self.assertTrue(any("ATSEVIŠĶS modulis" in n for n in rep.notes))                # brīdinājums pārbaudīt, bet nezaudē
        self.assertEqual(estimate(p).areas["modules_confirmed"], 2)
        self.assertAlmostEqual(estimate(p).areas["floor_frame_m2"], 2 * 12 * 4, 6)         # abu moduļu laukums

    def test_reimport_of_same_source_does_not_duplicate(self):
        p = empty_project("T")
        apply_candidates(p, self.scan, self.ids)
        rep = apply_candidates(p, self.scan, self.ids)
        rescan = scan_ad_building(self.pdf)                                                 # tas pats PDF vēlreiz skenēts
        rep2 = apply_candidates(p, rescan, [c.id for c in rescan.candidates if c.kind == "module"])
        self.assertEqual(len(p["modules"]), 2)
        self.assertEqual((len(rep.applied), len(rep2.applied)), (0, 0))

    def test_other_pdf_with_same_size_is_a_different_source(self):
        p = empty_project("T")
        apply_candidates(p, self.scan, self.ids)
        other = scan_ad_building(build_ad_building_pdf())                                   # cits PDF ar 12000×4000 moduli
        apply_candidates(p, other, [c.id for c in other.candidates if c.kind == "module" and c.data["length_mm"] == 12000])
        self.assertEqual(len(p["modules"]), 3)

    def test_module_name_collisions_are_made_unique(self):
        p = empty_project("T")
        p["modules"] = [{"name": "Modulis P1-K1", "length_mm": 5000, "width_mm": 3000, "axes": "", "confirmed": True}]
        apply_candidates(p, self.scan, self.ids)
        self.assertEqual(len({m["name"] for m in p["modules"]}), 3)

    def test_module_identity_survives_the_editor_round_trip_in_ui(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        app = str(Path(__file__).resolve().parent.parent / "app.py")
        at = AppTest.from_file(app, default_timeout=120).run()
        at.radio[0].set_value("Pilnas ēkas AD tāme").run()
        at.file_uploader(key="bp_adpdf").upload("m.pdf", self.pdf, "application/pdf").run()
        at.button(key="bp_adsafe_0").click().run()
        at.button(key="bp_adapply_0").click().run()
        mods = at.session_state["bp_project"]["modules"]
        self.assertEqual(len(mods), 2)
        self.assertTrue(all(m["source_key"] for m in mods))
        at.run()                                                                            # papildu izpilde: moduļu tabula pārraksta projektu
        mods2 = at.session_state["bp_project"]["modules"]
        self.assertEqual([m["source_key"] for m in mods2], [m["source_key"] for m in mods])


class TestRevitStyleNotation(unittest.TestCase):
    """Droši nolasāmais no Revit tipa notācijas (SINTĒTISKS fragments); neskaidrais paliek manuāli."""

    @classmethod
    def setUpClass(cls):
        from tools.synthetic_ad_building import build_revit_style_pdf
        cls.scan = scan_ad_building(build_revit_style_pdf())

    def test_room_table_with_number_and_notes(self):
        rooms = {r.data["name"]: r.data["area_m2"] for r in kinds(self.scan, "room")}
        self.assertEqual(rooms, {"Kitchen": 14.0, "Living room": 30.0, "Bedroom": 12.0})
        self.assertEqual(kinds(self.scan, "terrace")[0].data["area_m2"], 12.0)
        net = kinds(self.scan, "floor_net")[0]
        self.assertEqual(net.data["area_m2"], 56.0)                                      # telpu summa; terase un «Total Building Area» nav iekšā

    def test_total_building_area_is_informational_and_never_applied_as_floor(self):
        total = kinds(self.scan, "building_area")[0]
        self.assertEqual(total.data["area_m2"], 80.0)
        self.assertTrue(any("≠ neto grīdas platība" in n for n in total.notes))
        p = empty_project("T")
        rep = apply_candidates(p, self.scan, [total.id])
        self.assertIsNone(p["floor_net_m2"])
        self.assertTrue(any("informatīva" in why for _i, why in rep.skipped))

    def test_window_marks_counts_from_plan_tags_and_unknown_counts_stay_empty(self):
        ops = {o.data["name"]: o for o in kinds(self.scan, "opening")}
        self.assertEqual((ops["W-1"].data["width_mm"], ops["W-1"].data["height_mm"], ops["W-1"].data["count"]), (1200, 1500, 3))
        self.assertEqual((ops["RW-1"].data["count"], ops["RW-1"].data["wall"]), (1, "Jumts"))
        self.assertIsNone(ops["W-2"].data["count"])                                       # nav marķējumu plānā → skaits manuāli
        self.assertTrue(all(o.confidence == LOW for o in ops.values()))
        self.assertTrue(any("ņemts no plāna marķējumiem" in i for i in ops["W-1"].issues))

    def test_unclear_marks_are_not_transferred_but_roof_window_with_known_count_is(self):
        p = empty_project("T")
        rep = apply_candidates(p, self.scan, [c.id for c in self.scan.candidates])
        why = dict(rep.skipped)
        w1 = next(c.id for c in self.scan.candidates if c.kind == "opening" and c.data["name"] == "W-1")
        w2 = next(c.id for c in self.scan.candidates if c.kind == "opening" and c.data["name"] == "W-2")
        self.assertIn("atrašanās vieta", why[w1])                                         # ārējais/iekšējais nav norādīts
        self.assertIn("atrašanās vieta", why[w2])
        self.assertEqual([(o["name"], o["wall"], o["count"]) for o in p["openings"]], [("RW-1", "Jumts", 1)])

    def test_english_roof_angle_in_degrees(self):
        self.assertEqual(kinds(self.scan, "roof_angle")[0].data["angle_deg"], 20.0)


class TestCommittedSamples(unittest.TestCase):
    def test_committed_pdf_matches_generator_and_is_synthetic(self):
        from pathlib import Path
        path = Path(__file__).resolve().parent.parent / "samples" / "ad_building" / "AD_sintetiska_eka.pdf"
        data = path.read_bytes()
        self.assertEqual(data, build_ad_building_pdf())
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            text = "".join(page.get_text() for page in doc)
        self.assertIn("SINTĒTISKS PARAUGS", text)
        self.assertEqual(len(scan_ad_building(data).candidates), len(scan_ad_building(build_ad_building_pdf()).candidates))

    def test_committed_control_sheets_parse_identically(self):
        from pathlib import Path
        from src.control_import import parse_control_sheet
        base = Path(__file__).resolve().parent.parent / "samples" / "ad_building"
        a = parse_control_sheet("a.xlsx", (base / "kontroltame_sintetiska.xlsx").read_bytes())
        b = parse_control_sheet("a.csv", (base / "kontroltame_sintetiska.csv").read_bytes())
        self.assertEqual([(l.row_type, l.code, l.actual_sum) for l in a.lines], [(l.row_type, l.code, l.actual_sum) for l in b.lines])
        self.assertEqual(a.errors, [])


class TestKitsAndTypeRecipeGuards(unittest.TestCase):
    def test_identical_type_recipe_layer_is_counted_once(self):
        p, _s, _r = build_project()
        dup = dict(next(r for r in p["type_recipes"] if r["type"] == "ĀS1" and r["name"] == "ģipškartons"), id="dup-x")
        p["type_recipes"].append(dup)
        e = estimate(p)
        self.assertEqual(len([r for r in e.rows if r.material == "ģipškartons (ĀS1)"]), 1)
        self.assertTrue(any("dublikāts netiek skaitīts" in w for w in e.warnings))

    def test_type_not_used_by_any_segment_is_not_counted_but_reported(self):
        p, _s, _r = build_project()
        p["construction_types"].append({"id": "t9", "code": "ĀS9", "name": "neizmantots", "applies_to": "ext", "source": ""})
        p["type_recipes"].append({"id": "r9", "type": "ĀS9", "name": "tukša kārta", "kind": "apdare", "unit": "m²", "enabled": True})
        e = estimate(p)
        self.assertEqual([r for r in e.rows if "ĀS9" in r.material], [])
        self.assertTrue(any("ĀS9 nav piesaistīts nevienam posmam" in w for w in e.warnings))

    def kit(self, **extra):
        p = empty_project("T", "clt")
        line = {"id": "k1", "group": "Ventilācija", "name": "Ventilācijas komplekts", "unit": "kompl.", "driver": "direct", "qty": 1, "article": None,
                "approved": False, "enabled": True, "detail": "komplekts", "assumption": "", "cost_scope": "materiāli"}
        line.update(extra)
        p["recipes"] = [line]
        return p

    def test_ad_kit_and_norm_need_explicit_assumption(self):
        e = estimate(self.kit())
        self.assertTrue(any("jāpievieno skaidrs pieņēmums" in w for w in e.warnings))
        e2 = estimate(self.kit(assumption="DEMO: rekuperācija visai ēkai"))
        self.assertFalse(any("jāpievieno skaidrs pieņēmums" in w for w in e2.warnings))
        e3 = estimate(self.kit(detail="norma", driver="floor_net", qty=None))
        self.assertTrue(any("norma" in w and "pieņēmums" in w for w in e3.warnings))

    def test_kit_and_external_scope_have_no_reserve_and_furniture_group_zero(self):
        row = next(r for r in estimate(self.kit(assumption="x")).rows if r.material == "Ventilācijas komplekts")
        self.assertEqual((row.order_qty, row.waste_pct, row.detail), (1.0, 0.0, "komplekts"))
        furn = estimate(self.kit(group="Virtuve, mēbeles un tehnika", detail="detalizēts", name="Virtuves iekārta", qty=1.0))
        self.assertEqual(next(r for r in furn.rows if r.material == "Virtuves iekārta").waste_pct, 0.0)
        ext = next(r for r in estimate(self.kit(detail="detalizēts", cost_scope="ārpakalpojums", group="Manuālās rindas")).rows if r.material == "Ventilācijas komplekts")
        self.assertEqual(ext.order_qty, 1.0)

    def test_kit_with_installation_double_counts_with_labour_operations(self):
        p = self.kit(assumption="x", cost_scope="materiāli+montāža")
        p["labour"] = {"rate_eur_h": 30.0, "operations": [{"id": "o1", "group": "Ventilācija", "name": "Montāža", "driver": "direct", "hours": 10.0,
                                                           "unit": "h", "enabled": True}]}
        e = estimate(p)
        self.assertTrue(any("Dubultošana" in x and "Ventilācija" in x for x in e.errors))
        p["recipes"][0]["cost_scope"] = "materiāli"
        self.assertFalse(any("Dubultošana" in x for x in estimate(p).errors))

    def test_cost_scope_is_carried_to_rows_and_snapshot_scopes(self):
        from src.forecast_compare import freeze_forecast
        p = self.kit(assumption="x", cost_scope="ārpakalpojums", group="Manuālās rindas")
        e = estimate(p)
        snap = freeze_forecast(p, e, "t")
        self.assertEqual(next(r for r in snap["rows"] if r["material"] == "Ventilācijas komplekts")["scope"], "ārējās izmaksas")


if __name__ == "__main__":
    unittest.main()
