"""Issue #16: lietotāja plūsma AppTest līmenī: AD PDF → kandidāti/apstiprināšana → tāme → versijas fiksēšana → kontroltāme → salīdzinājums."""
import copy
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.building_estimate import estimate
from src.control_import import parse_control_sheet
from src.forecast_compare import compare_to_actual
from tools.synthetic_ad_building import build_ad_building_pdf, build_control_csv, build_control_xlsx

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def building_app():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.radio[0].set_value("Pilnas ēkas tāme").run()
    assert not at.exception, at.exception
    return at


def upload_ad_pdf(at):
    at.file_uploader(key="bp_adpdf").upload("AD_sintetiska_eka.pdf", build_ad_building_pdf(), "application/pdf").run()
    assert not at.exception, at.exception
    return at


class TestAdPdfFlow(unittest.TestCase):
    def test_nothing_is_applied_without_confirmation(self):
        at = upload_ad_pdf(building_app())
        project = at.session_state["bp_project"]
        self.assertEqual((project["modules"], project["ext_walls"], project["openings"], project["roof_slopes"]), ([], [], [], []))
        self.assertTrue(any("kandidāti: **35**" in m.value or "kandidāti" in m.value for m in at.markdown))

    def test_pdf_to_estimate_flow_with_confirmation(self):
        at = upload_ad_pdf(building_app())
        at.button(key="bp_adsafe_0").click().run()
        at.button(key="bp_adapply_0").click().run()
        self.assertFalse(at.exception)
        p = at.session_state["bp_project"]
        self.assertEqual(sorted((m["length_mm"], m["width_mm"]) for m in p["modules"]), [(8000, 4000), (12000, 4000)])
        self.assertEqual(len(p["ext_walls"]), 4)
        self.assertEqual(len(p["int_walls"]), 3)
        self.assertEqual(len(p["gables"]), 2)
        self.assertEqual(len(p["roof_slopes"]), 2)
        self.assertEqual(p["floor_net_m2"], 72.0)
        self.assertEqual(p["layers_mode"], "types")
        self.assertEqual(p["roof"]["mode"], "slopes")
        self.assertTrue(p["ad_import"]["fields"])
        names = {w["name"] for w in p["ext_walls"] + p["int_walls"]}
        self.assertNotIn("X", names)                                   # nenolasāmais netiek pārnests
        self.assertNotIn("D3", [o["name"] for o in p["openings"]])
        est = estimate(p)
        self.assertAlmostEqual(est.areas["ext_walls_net_m2"], 122.7, 6)
        self.assertTrue(any("NEPILNA TĀME" in w.value or "Budžets ir NEPILNS" in w.value for w in at.warning))     # cenu/normu vēl nav

    def test_pdf_removal_clears_session_scan(self):
        at = upload_ad_pdf(building_app())
        self.assertIn("bp_ad_scan", at.session_state)
        at.file_uploader(key="bp_adpdf").upload("x.pdf", b"%PDF-1.4\n%%EOF", "application/pdf").run()
        self.assertFalse(at.exception)

    def test_invalid_pdf_is_reported_not_crash(self):
        at = building_app()
        at.file_uploader(key="bp_adpdf").upload("bad.pdf", b"nav pdf", "application/pdf").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("neizdevās nolasīt" in e.value for e in at.error))

    def test_pdf_is_not_stored_in_project(self):
        at = upload_ad_pdf(building_app())
        at.button(key="bp_adsafe_0").click().run()
        at.button(key="bp_adapply_0").click().run()
        from src.project_io import export_project
        raw = export_project(at.session_state["bp_project"])
        self.assertNotIn(b"%PDF", raw)
        self.assertLess(len(raw), 400_000)


class TestAdDemo(unittest.TestCase):
    def test_ad_demo_one_click_full_budget(self):
        at = building_app()
        at.button(key="bp_demo_ad").click().run()
        self.assertFalse(at.exception)
        values = {m.label: m.value for m in at.metric}
        self.assertEqual(values["Pašizmaksa"], "100973.20 EUR")
        self.assertEqual(values["Pārdošanas cena bez PVN"], "116119.18 EUR")
        self.assertFalse(any("Budžets ir NEPILNS" in w.value for w in at.warning))
        self.assertEqual(at.session_state["bp_project"]["stage"], "AD")

    def test_manual_mode_and_old_demo_are_preserved(self):
        at = building_app()
        at.button(key="bp_demo").click().run()
        self.assertFalse(at.exception)
        values = {m.label: m.value for m in at.metric}
        self.assertEqual(values["Pašizmaksa"], "74607.43 EUR")
        self.assertEqual(values["Pārdošanas cena bez PVN"], "85798.54 EUR")


class TestForecastControlFlow(unittest.TestCase):
    def freeze(self, at):
        at.button(key="bp_freeze_1").click().run()
        self.assertFalse(at.exception, at.exception)
        return at

    def test_compare_requires_frozen_forecast(self):
        at = building_app()
        at.button(key="bp_demo_ad").click().run()
        self.assertTrue(any("Nav fiksētas prognozes" in i.value for i in at.info))
        self.assertEqual([m for m in at.metric if "starpība" in m.label], [])

    def test_freeze_import_compare_flow(self):
        at = building_app()
        at.button(key="bp_demo_ad").click().run()
        self.freeze(at)
        versions = at.session_state["bp_project"]["versions"]
        self.assertEqual(len(versions), 1)
        self.assertTrue(versions[0]["locked"])
        self.assertEqual(round(versions[0]["budget"]["sell"], 2), 116119.18)
        at.file_uploader(key="bp_ctrl_1").upload("kontroltame.xlsx", build_control_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet").run()
        self.assertFalse(at.exception, at.exception)
        expected = compare_to_actual(versions[0], parse_control_sheet("k.xlsx", build_control_xlsx())).totals
        labels = {m.label: m.value for m in at.metric}
        self.assertEqual(labels["Materiāli (sasaistītie): starpība (fakts − prognoze)"], f"{expected['materials_diff']:.2f} EUR")
        self.assertEqual(labels["Ārējās izmaksas (sasaistītās): starpība"], "350.00 EUR")                 # 4350 − 4000 (neatkarīgi)
        self.assertEqual(labels["Stundas (sasaistītie posmi): starpība"], f"{expected['hours_diff']:.2f} h")

    def test_importing_actuals_does_not_change_forecast_or_estimate(self):
        at = building_app()
        at.button(key="bp_demo_ad").click().run()
        self.freeze(at)
        before = copy.deepcopy(at.session_state["bp_project"])
        sell_before = {m.label: m.value for m in at.metric}["Pārdošanas cena bez PVN"]
        at.file_uploader(key="bp_ctrl_1").upload("k.csv", build_control_csv(), "text/csv").run()
        self.assertFalse(at.exception, at.exception)
        after = at.session_state["bp_project"]
        for key in before:
            if key != "actuals":
                self.assertEqual(after[key], before[key], key)
        self.assertEqual({m.label: m.value for m in at.metric}["Pārdošanas cena bez PVN"], sell_before)

    def test_calibrated_copy_flow_keeps_ad_project(self):
        at = building_app()
        at.button(key="bp_demo_ad").click().run()
        self.freeze(at)
        at.file_uploader(key="bp_ctrl_1").upload("k.xlsx", build_control_xlsx(), "application/octet-stream").run()
        at.button(key="bp_mkcal_1").click().run()
        self.assertFalse(at.exception, at.exception)
        stage, derived, _n = at.session_state["bp_derived"]
        self.assertEqual(stage, "kalibrēta")
        self.assertEqual(derived["stage"], "kalibrēta")
        self.assertEqual(at.session_state["bp_project"]["stage"], "AD")
        self.assertTrue(any("atsevišķa «kalibrēta» versija" in s.value for s in at.success))

    def test_bad_control_file_is_reported(self):
        at = building_app()
        at.button(key="bp_demo_ad").click().run()
        self.freeze(at)
        at.file_uploader(key="bp_ctrl_1").upload("k.xlsx", b"PK nav xlsx", "application/octet-stream").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("faila nolasīšana neizdevās" in e.value for e in at.error))


if __name__ == "__main__":
    unittest.main()
