"""Issue #18: AD-first sākumskats, statusi un versijas identifikators (tikai sintētiski dati)."""
import unittest
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

from src import app_shell
from src.ad_pdf_ui import ANALYSING, APPLIED, DEMO, ERROR, NOTHING, RESULT, WAITING, ad_status
from src.building_estimate import estimate
from tools.synthetic_ad_building import build_ad_building_pdf

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def texts(at):
    return " ".join([m.value for m in at.markdown] + [i.value for i in at.info] + [s.value for s in at.success]
                    + [w.value for w in at.warning] + [e.value for e in at.error] + [c.value for c in at.caption])


class TestDefaultView(unittest.TestCase):
    def test_building_ad_is_default_and_modes_named(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.radio[0].value, "Pilnas ēkas AD tāme")
        self.assertEqual(list(at.radio[0].options), ["Pilnas ēkas AD tāme", "Vecais AD: tikai grīdas rāmis", "PD: līmsiju specifikācija"])

    def test_upload_and_demo_visible_without_expanding(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        self.assertEqual(len(at.file_uploader(key="bp_adpdf").proto.type), 1)          # augšupielādes lauks eksistē sākumskatā
        self.assertIn("bp_demo_ad", [b.key for b in at.button])
        # augšupielādes lauks un demo poga nav nevienā izvēršamā sadaļā: izvēršamo sadaļu iekšienē to nav
        for ex in at.expander:
            self.assertNotIn("bp_adpdf", [u.key for u in ex.file_uploader], ex.label)
            self.assertNotIn("bp_demo_ad", [b.key for b in ex.button], ex.label)

    def test_initial_status_is_waiting_with_next_action(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        self.assertIn("Gaida AD PDF", texts(at))
        self.assertIn("Nākamā darbība", texts(at))

    def test_demo_click_gives_priced_estimate(self):
        at = AppTest.from_file(APP, default_timeout=120).run()
        at.button(key="bp_demo_ad").click().run()
        self.assertFalse(at.exception)
        est = estimate(at.session_state["bp_project"])
        self.assertTrue(est.complete)
        self.assertIn("AD demonstrācija ielādēta", texts(at))

    def test_pdf_upload_shows_candidate_count(self):
        at = AppTest.from_file(APP, default_timeout=120).run()
        at.file_uploader(key="bp_adpdf").upload("AD_sintetiska_eka.pdf", build_ad_building_pdf(), "application/pdf").run()
        self.assertFalse(at.exception)
        self.assertIn("atrasti", texts(at))

    def test_invalid_pdf_shows_error_status(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        at.file_uploader(key="bp_adpdf").upload("bad.pdf", b"nav pdf", "application/pdf").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("analīze neizdevās" in e.value for e in at.error))

    def test_old_modes_still_work(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        at.radio[0].set_value("Vecais AD: tikai grīdas rāmis").run()
        self.assertFalse(at.exception)
        at.radio[0].set_value("PD: līmsiju specifikācija").run()
        self.assertFalse(at.exception)

    def test_version_label_is_visible(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        self.assertIn(app_shell.RELEASE_VERSION, texts(at))


class TestStatusFunction(unittest.TestCase):
    def test_all_states_have_status_and_next_action(self):
        for state in (WAITING, ANALYSING, RESULT, ERROR, NOTHING, DEMO, APPLIED):
            level, text, nxt = ad_status(state, 3, "x")
            self.assertIn(level, ("info", "success", "error", "warning"))
            self.assertTrue(text and nxt, state)
        self.assertIn("3 kandidāti", ad_status(RESULT, 3)[1])
        self.assertEqual(ad_status(NOTHING)[0], "warning")
        self.assertEqual(ad_status(ERROR, error="x")[0], "error")


class TestVersion(unittest.TestCase):
    def test_env_sha_preferred_and_shortened(self):
        self.assertEqual(app_shell.commit_sha({"GIT_COMMIT": "ABCDEF1234567890"}), "abcdef1")
        self.assertIn("commit abcdef1", app_shell.version_label({"MLK_COMMIT": "abcdef1234"}))

    def test_invalid_env_value_ignored_falls_back_to_git(self):
        runner = lambda *a, **k: SimpleNamespace(returncode=0, stdout="1234abc\n")
        self.assertEqual(app_shell.commit_sha({"GIT_COMMIT": "not a sha!"}, runner), "1234abc")

    def test_no_git_gives_release_version_only(self):
        def boom(*a, **k):
            raise FileNotFoundError()
        label = app_shell.version_label({}, boom)
        self.assertIn(app_shell.RELEASE_VERSION, label)
        self.assertIn("commit nav pieejams", label)

    def test_git_failure_returncode(self):
        runner = lambda *a, **k: SimpleNamespace(returncode=128, stdout="")
        self.assertIsNone(app_shell.commit_sha({}, runner))


if __name__ == "__main__":
    unittest.main()
