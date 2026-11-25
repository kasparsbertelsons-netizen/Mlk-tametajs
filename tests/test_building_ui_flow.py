"""Issue #14: UI plūsma (AppTest) — vienkliksķa pilnībā cenota demonstrācija, budžets, lejupielādes, pārbaudes atcelšana, notīrīšana."""
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parent.parent / "app.py")


def building_app():
    at = AppTest.from_file(APP, default_timeout=90).run()
    at.radio[0].set_value("Pilnas ēkas tāme").run()
    return at


def demo_app():
    at = building_app()
    at.button(key="bp_demo").click().run()
    return at


class TestOneClickDemo(unittest.TestCase):
    def test_full_budget_in_one_click(self):
        at = demo_app()
        self.assertFalse(at.exception)
        values = {m.label: m.value for m in at.metric}
        self.assertEqual(values["Pašizmaksa"], "74607.43 EUR")
        self.assertEqual(values["Pārdošanas cena bez PVN"], "85798.54 EUR")
        self.assertTrue(any("DEMO" in w.value and "sintētiski" in w.value for w in at.warning))
        self.assertFalse(any("Budžets ir NEPILNS" in w.value for w in at.warning))
        self.assertTrue(any("Visi budžeta lielumi ievadīti" in s.value for s in at.success))
        frames = [df.value for df in at.dataframe]
        budget = next(df for df in frames if "Pozīcija" in list(df.columns))
        by = dict(zip(budget["Pozīcija"], budget["EUR"]))
        self.assertEqual(by["PĀRDOŠANAS CENA bez PVN"], 85798.54)
        self.assertEqual(by["SUMMA AR PVN"], 103816.24)
        self.assertEqual(by["PAŠIZMAKSA"], 74607.43)

    def test_downloads_xlsx_csv_json_and_templates(self):
        labels = [b.proto.label for b in demo_app().get("download_button")]
        for needle in ("Excel (XLSX)", "BOM (CSV)", "Saglabāt projektu (JSON)", "šablons (XLSX", "šablons (CSV"):
            self.assertTrue(any(needle in l for l in labels), (needle, labels))

    def test_local_data_reminder_is_shown(self):
        at = demo_app()
        self.assertTrue(any("127.0.0.1" in w.value and "DEMO" in w.value for w in at.warning))

    def test_removing_a_price_makes_budget_incomplete_in_ui(self):
        at = demo_app()
        project = at.session_state["bp_project"]
        project["catalog"][0]["unit_price"] = None                      # panelis bez cenas
        at.run()
        self.assertTrue(any("Budžets ir NEPILNS" in w.value and "bez cenas" in w.value for w in at.warning))
        values = {m.label: m.value for m in at.metric}
        self.assertTrue(values["Pašizmaksa"].endswith("NEPILNA"))


class TestReviewCancellation(unittest.TestCase):
    def review_checkbox(self, at):
        return next(c for c in at.checkbox if c.key and c.key.startswith("bp_revok_"))

    def test_review_is_bound_to_data_state(self):
        at = demo_app()
        at.text_input(key="bp_rev_1").set_value("Jānis").run()
        self.review_checkbox(at).check().run()
        self.assertTrue(any("Jānis" in i.value and "pārbaudīts" in i.value for i in at.info))
        self.assertTrue(self.review_checkbox(at).value)
        at.session_state["bp_project"]["catalog"][0]["unit_price"] = 999.0       # datu izmaiņa pēc pārbaudes
        at.run()
        self.assertTrue(any("Dati mainīti pēc pārbaudes" in w.value for w in at.warning))
        self.assertTrue(any("nav atbildīgās personas pārbaudes" in i.value for i in at.info))
        self.assertFalse(self.review_checkbox(at).value)
        at.session_state["bp_project"]["catalog"][0]["unit_price"] = 520.0       # A → B → A: apstiprinājums neatjaunojas
        at.run()
        self.assertFalse(self.review_checkbox(at).value)
        self.assertTrue(any("nav atbildīgās personas pārbaudes" in i.value for i in at.info))

    def test_review_needs_name(self):
        at = demo_app()
        self.review_checkbox(at).check().run()
        self.assertTrue(any("Ievadi pārbaudītāja vārdu" in i.value for i in at.info))
        self.assertTrue(any("nav atbildīgās personas pārbaudes" in i.value for i in at.info))


class TestClear(unittest.TestCase):
    def test_clear_gives_incomplete_unpriced_budget(self):
        at = demo_app()
        at.button(key="bp_clear").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["bp_project"]["modules"], [])
        self.assertTrue(any("NEPILNA TĀME" in w.value for w in at.warning))
        self.assertFalse(any("Visi budžeta lielumi ievadīti" in s.value for s in at.success))


if __name__ == "__main__":
    unittest.main()
