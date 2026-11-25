"""Issue #14: projekta saglabāšana/atjaunošana JSON (shēmas versija, validācija, apstiprinājumu neuzticēšanās, identisks rezultāts)."""
import copy
import json
import unittest

from src.building_demo import demo_project
from src.building_estimate import confirm_review, empty_project, estimate
from src.project_io import APP_ID, MAX_BYTES, SCHEMA_VERSION, export_project, import_project


def snapshot(project):
    e = estimate(project)
    return ([(r.row_id, r.material, r.qty, r.order_qty, r.unit_price, r.cost, r.status, r.approved) for r in e.rows],
            [(x.row_id, x.name, x.hours, x.cost) for x in e.labour], e.budget(), e.errors, e.warnings, e.missing)


class TestRoundtrip(unittest.TestCase):
    def test_demo_roundtrip_gives_identical_result(self):
        p = demo_project()
        back = import_project(export_project(p))
        self.assertEqual(back.errors, [])
        self.assertEqual(back.notices, [])
        self.assertEqual(snapshot(back.project), snapshot(p))
        self.assertEqual(round(estimate(back.project).budget()["sell"], 2), 85798.54)

    def test_user_approvals_survive_when_file_untouched(self):
        p = demo_project()
        back = import_project(export_project(p)).project
        self.assertTrue(all(m["confirmed"] for m in back["modules"]))
        self.assertTrue(back["clt"]["ext"]["thickness_confirmed"])
        self.assertTrue(back["roof"]["slope_confirmed"])

    def test_schema_version_checksum_and_no_pdf_in_file(self):
        doc = json.loads(export_project(demo_project()))
        self.assertEqual((doc["schema_version"], doc["app"]), (SCHEMA_VERSION, APP_ID))
        self.assertTrue(doc["checksum"])
        self.assertNotIn("pdf", json.dumps(doc).lower().replace("nav nolasīts no pdf", ""))
        for key in ("catalog", "recipes", "labour", "prices", "pricing", "other_costs", "layers"):
            self.assertIn(key, doc["data"])

    def test_catalog_leading_zeros_and_ids_preserved(self):
        p = demo_project()
        p["catalog"].append({"article": "00123", "name": "x", "spec": "", "unit": "m", "unit_price": 1.0, "pack_size": None, "supplier": "",
                             "source": ""})
        back = import_project(export_project(p)).project
        self.assertIn("00123", [c["article"] for c in back["catalog"]])
        self.assertEqual([l["id"] for l in back["layers"]], [l["id"] for l in p["layers"]])

    def test_empty_project_roundtrip(self):
        p = empty_project()
        back = import_project(export_project(p))
        self.assertEqual(back.errors, [])
        self.assertEqual(snapshot(back.project)[2], snapshot(p)[2])


class TestDoesNotTrustImportedStatus(unittest.TestCase):
    def test_review_confirmation_is_never_imported(self):
        p = demo_project()
        confirm_review(p, "Jānis")
        self.assertNotIn("NAV GATAVS", estimate(p).procurement_status)
        back = import_project(export_project(p))
        self.assertTrue(any("netiek pārņemta" in n for n in back.notices))
        self.assertFalse(back.project["review"]["confirmed"])
        self.assertIsNone(back.project["review"]["fp"])
        self.assertIn("nav atbildīgās personas pārbaudes", estimate(back.project).procurement_status)

    def test_forged_review_in_hand_edited_file_is_ignored(self):
        doc = json.loads(export_project(demo_project()))
        doc["data"]["review"] = {"reviewer": "Krāpnieks", "confirmed": True, "fp": "zzz"}
        back = import_project(json.dumps(doc).encode())
        self.assertFalse(back.project["review"]["confirmed"])

    def test_tampered_file_drops_all_user_approvals(self):
        doc = json.loads(export_project(demo_project()))
        doc["data"]["catalog"][0]["unit_price"] = 1.0                      # mainīts ārpus programmas, kontrolsumma neatbilst
        back = import_project(json.dumps(doc).encode())
        self.assertEqual(back.errors, [])
        self.assertTrue(any("Kontrolsumma neatbilst" in n for n in back.notices))
        p = back.project
        self.assertFalse(any(m["confirmed"] for m in p["modules"]))
        self.assertEqual(p["module_fp"], {})
        self.assertFalse(any(v["thickness_confirmed"] for v in p["clt"].values()))
        self.assertFalse(p["roof"]["slope_confirmed"])
        self.assertFalse(any(l.get("approved") for k in ("layers", "recipes", "manual") for l in p[k]))
        self.assertFalse(any(o["approved"] for o in p["labour"]["operations"]))
        e = estimate(p)
        self.assertFalse(e.complete)                                       # moduļi neapstiprināti → nepilns


class TestValidation(unittest.TestCase):
    def bad(self, raw, needle):
        res = import_project(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
        self.assertIsNone(res.project)
        self.assertTrue(any(needle in e for e in res.errors), res.errors)

    def good_doc(self):
        return json.loads(export_project(demo_project()))

    def test_not_json_and_wrong_structure(self):
        self.bad(b"nav json", "nav derīgs JSON")
        self.bad(b"\xff\xfe", "nav derīgs JSON")
        self.bad([1, 2], "struktūra")
        self.bad({"schema_version": 1, "app": APP_ID}, "struktūra")

    def test_schema_version_and_app(self):
        d = self.good_doc()
        d["schema_version"] = SCHEMA_VERSION + 1
        self.bad(d, "jaunākas shēmas versijas")
        d["schema_version"] = "1"
        self.bad(d, "shēmas versijas")
        d["schema_version"] = 0
        self.bad(d, "nederīga shēmas versija")
        d = self.good_doc()
        d["app"] = "cita-lietotne"
        self.bad(d, "nav šīs programmas")

    def test_size_depth_list_and_types(self):
        self.bad(b" " * (MAX_BYTES + 1), "5 MB")
        d = self.good_doc()
        d["data"]["manual"] = [{"material": "x"}] * 2001
        self.bad(d, "pārāk daudz ierakstu")
        d = self.good_doc()
        d["data"]["modules"] = "nav saraksts"
        self.bad(d, "nepareizs tips")
        d = self.good_doc()
        d["data"]["layers"] = [1, 2]
        self.bad(d, "katram ierakstam jābūt objektam")
        d = self.good_doc()
        d["data"]["labour"] = {"rate_eur_h": 1, "operations": "x"}
        self.bad(d, "labour.operations")
        d = self.good_doc()
        d["data"]["roof"] = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": 1}}}}}}}}}
        self.bad(d, "dziļa")
        d = self.good_doc()
        d["data"]["modules"] = d["data"]["modules"] * 6
        self.bad(d, "pārāk daudz moduļu")

    def test_non_finite_numbers_rejected(self):
        raw = export_project(demo_project()).decode().replace('"floor_net_m2": 72.0', '"floor_net_m2": NaN')
        self.bad(raw.encode(), "nav galīgs skaitlis")

    def test_unknown_fields_are_dropped_with_notice_and_defaults_filled(self):
        d = self.good_doc()
        d["data"]["__proto__"] = {"x": 1}
        d["data"]["pdf_bytes"] = "AAAA"
        del d["data"]["labour"]
        res = import_project(json.dumps(d).encode())
        self.assertEqual(res.errors, [])
        self.assertTrue(any("nezināmi lauki" in n for n in res.notices))
        self.assertNotIn("pdf_bytes", res.project)
        self.assertEqual(res.project["labour"], {"rate_eur_h": None, "operations": []})

    def test_missing_line_ids_are_assigned(self):
        d = self.good_doc()
        for l in d["data"]["layers"]:
            l.pop("id")
        res = import_project(json.dumps(d).encode())
        ids = [l["id"] for l in res.project["layers"]]
        self.assertTrue(all(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_import_does_not_mutate_input_and_is_pure_json(self):
        raw = export_project(demo_project())
        before = copy.deepcopy(raw)
        import_project(raw)
        self.assertEqual(raw, before)
        self.assertNotIn(b"pickle", raw)


if __name__ == "__main__":
    unittest.main()
