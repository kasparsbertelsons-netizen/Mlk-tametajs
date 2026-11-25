"""Diagnostikas interaktīvā režīma testi (tools/ad_diagnostics.py --interactive, Issue #8).

Ievadi apstrādā Python (input, validācija, pathlib); `.bat` tikai palaiž fiksētu komandu. Testi izmanto naidīgas
ievades (`&`, `%`, `^`, pēdiņas, komandu fragmenti), sinhronizētu mapju nosaukumus un pārrakstīšanas gadījumus.
"""
import ast
import datetime
import io
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from src import ad_diagnostics as diag
from tests.synthetic_pdfs import SECRET, sensitive_pdf
from tools import ad_diagnostics as cli
from tools import synthetic_ad_pdf as gen

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLE = (ROOT / "samples" / "ad_vector" / "ad_vector_01_12000x4000_1to50.pdf").read_bytes()
HOSTILE_NAME = "Mans & rasējums %PATH% ^ ! (1) ā ; calc.pdf"
SUMMARY_MARK = "=== SANITIZĒTAIS KOPSAVILKUMS"


def scripted(*answers):
    """Simulē lietotāja ievadi; kad atbildes beidzas, kā aizvērts stdin (EOFError)."""
    queue = list(answers)
    prompts = []

    def input_fn(prompt=""):
        prompts.append(prompt)
        if not queue:
            raise EOFError
        return queue.pop(0)
    input_fn.prompts = prompts
    return input_fn


class Workdir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)
        self.localappdata = self.dir / "localappdata"
        self.env = {"LOCALAPPDATA": str(self.localappdata)}
        self._cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self._cwd)

    def write_pdf(self, data=SAMPLE, name=HOSTILE_NAME):
        path = self.dir / name
        path.write_bytes(data)
        return path

    def run_main(self, args, *answers, env=None):
        out = io.StringIO()
        input_fn = scripted(*answers)
        code = cli.main(args, out=out, input_fn=input_fn, environ=self.env if env is None else env)
        return code, out.getvalue(), input_fn

    def tree(self):
        return sorted(str(p.relative_to(self.dir)) for p in self.dir.rglob("*"))


class TestInteractiveFlow(Workdir):
    def test_full_flow_with_a_hostile_file_name_pasted_in_quotes(self):
        pdf = self.write_pdf()
        before = self.tree()
        code, text, _ = self.run_main(["--interactive"], f'  "{pdf}"  ', "2", "12000x4000", "", "n", "j")
        self.assertEqual(code, 0)
        self.assertIn(HOSTILE_NAME, text)                                  # fails tika atrasts un nolasīts pareizi
        self.assertIn("kandidāts P2-K1", text)
        self.assertIn("sakrīt (≤ 0,5 %)", text)
        self.assertIn(SUMMARY_MARK, text)
        self.assertEqual(self.tree(), before)                              # "n" HTML jautājumam: nekas nav saglabāts

    def test_pdf_given_as_argument_is_not_asked_again_and_empty_argument_is_asked(self):
        pdf = self.write_pdf()
        _, _, asked = self.run_main(["--interactive", str(pdf)], "", "", "n", "n")
        self.assertFalse(any("PDF faila ceļš" in p for p in asked.prompts))
        self.assertTrue(asked.prompts[0].startswith("Plāna lapa(s)"))
        code, text, asked = self.run_main(["--interactive", ""], str(pdf), "", "", "n", "n")      # .bat nodod "" bez faila
        self.assertEqual(code, 0)
        self.assertTrue(asked.prompts[0].startswith("PDF faila ceļš"))
        self.assertIn(HOSTILE_NAME, text)

    def test_quoted_pdf_argument_is_accepted(self):
        pdf = self.write_pdf()
        for argument in (f'"{pdf}"', f"  '{pdf}'  "):
            code, text, asked = self.run_main(["--interactive", argument], "", "", "n", "n")
            self.assertEqual(code, 0, argument)
            self.assertFalse(any("PDF faila ceļš" in p for p in asked.prompts))
            self.assertIn(HOSTILE_NAME, text)

    def test_quotes_and_spaces_are_stripped_only_around_the_path(self):
        self.assertEqual(cli.strip_path_input('  "C:\\a b\\x & y.pdf"  '), "C:\\a b\\x & y.pdf")
        self.assertEqual(cli.strip_path_input("'/tmp/a b.pdf'"), "/tmp/a b.pdf")
        self.assertEqual(cli.strip_path_input('"unclosed.pdf'), '"unclosed.pdf')
        self.assertEqual(cli.strip_path_input("a&b.pdf"), "a&b.pdf")

    def test_hostile_page_and_control_entries_are_rejected_then_valid_ones_accepted(self):
        pdf = self.write_pdf()
        code, text, _ = self.run_main(["--interactive", str(pdf)], "2 & calc", "2;3", "$(whoami)", "2",
                                      "12000x4000 & del *", "abc", "-1x5", "9000x3000", "", "n", "n")
        self.assertEqual(code, 0)
        self.assertEqual(text.count("Nederīgs lapu numurs"), 3)
        self.assertEqual(text.count("Nederīgs kontrolizmērs"), 3)
        self.assertIn("1. 9000×3000 mm", text)                             # tikai derīgais kontrolizmērs
        # injicētie fragmenti parādās TIKAI noraidīšanas ziņojumos (nekas netiek izpildīts vai ielikts citur)
        self.assertEqual([l for l in text.splitlines() if "whoami" in l], ["Nederīgs lapu numurs: '$(whoami)'. Piemērs: 3 vai 3,5 vai 3-6."])
        self.assertEqual([l for l in text.splitlines() if "del *" in l],
                         ["Nederīgs kontrolizmērs: '12000x4000 & del *'. Piemērs: 12000x4000 (mm)."])
        self.assertIn("režīms 'manual', analizētās lapas: [2]", text)

    def test_too_many_invalid_pages_or_paths_end_with_exit_2(self):
        pdf = self.write_pdf()
        code, text, _ = self.run_main(["--interactive", str(pdf)], *["x"] * 5)
        self.assertEqual((code, "Netika saņemts derīgs lapu numurs" in text), (2, True))
        code, text, _ = self.run_main(["--interactive"], "nav.pdf", "", "  ", "C:\\nav\\tāda.pdf", str(self.dir))      # mape nav fails
        self.assertEqual((code, "PDF fails nav norādīts" in text), (2, True))
        self.assertIn("Fails nav atrasts", text)

    def test_closed_input_and_ctrl_c_are_handled(self):
        pdf = self.write_pdf()
        code, text, _ = self.run_main(["--interactive", str(pdf)])                   # nav atbilžu → EOFError
        self.assertEqual((code, "Ievade pārtraukta." in text), (2, True))
        out = io.StringIO()
        def interrupted(prompt=""):
            raise KeyboardInterrupt
        self.assertEqual(cli.main(["--interactive", str(pdf)], out=out, input_fn=interrupted, environ=self.env), 2)
        self.assertIn("Pārtraukts.", out.getvalue())

    def test_other_options_are_not_mixed_with_interactive_mode(self):
        pdf = self.write_pdf()
        for extra in (["--page", "2"], ["--control", "12000x4000"], ["--html", "x.html"], ["--print-summary"], ["--overwrite"]):
            code, text, _ = self.run_main(["--interactive", str(pdf), *extra])
            self.assertEqual(code, 2, extra)
            self.assertIn("Interaktīvajā režīmā norādiet tikai PDF", text)

    def test_non_interactive_mode_still_needs_a_pdf(self):
        code, text, _ = self.run_main([""])
        self.assertEqual((code, "Norādiet PDF failu" in text), (2, True))

    def test_summary_printed_in_interactive_mode_leaks_nothing(self):
        pdf = self.write_pdf(sensitive_pdf(), f"{SECRET}-PROJ-9981.pdf")
        code, text, _ = self.run_main(["--interactive", str(pdf)], "1", "12399x4300", "", "n", "j")
        self.assertEqual(code, 0)
        summary = text.split(SUMMARY_MARK)[1]
        for leaked in (SECRET, "PROJ-9981", "12345", "4321", "12399", "4300", ".pdf"):
            self.assertNotIn(leaked, summary)

    def test_the_tool_never_uses_a_shell(self):
        source = (ROOT / "tools" / "ad_diagnostics.py").read_text(encoding="utf-8")
        for banned in ("shell=True", "os.system", "os.popen", "subprocess", "eval(", "exec("):
            self.assertNotIn(banned, source)


class TestYesNo(unittest.TestCase):
    def test_yes_and_no_variants(self):
        for answer in ("j", "J", " jā ", "ja", "yes", "Y"):
            self.assertTrue(cli.ask_yes_no("?", scripted(answer), lambda _: None), answer)
        for answer in ("", "n", "N", "nē", "ne", "No", "   "):
            self.assertFalse(cli.ask_yes_no("?", scripted(answer), lambda _: None), answer)

    def test_default_is_no_and_garbage_is_asked_again(self):
        said = []
        self.assertTrue(cli.ask_yes_no("?", scripted("x", "??", "j"), said.append))
        self.assertEqual(said, ["Atbildiet j vai n.", "Atbildiet j vai n."])
        with self.assertRaises(diag.DiagnosticsError):
            cli.ask_yes_no("?", scripted(*["x"] * 5), lambda _: None)


class TestHtmlIsSavedOnlyWithConsentAndNeverOverwritten(Workdir):
    def test_html_is_saved_only_after_an_explicit_yes_in_the_default_folder(self):
        pdf = self.write_pdf()
        code, text, _ = self.run_main(["--interactive", str(pdf)], "", "", "j", "n")
        self.assertEqual(code, 0)
        saved = sorted((self.localappdata / "MLK_diagnostika").glob("diagnostika_*.html"))
        self.assertEqual(len(saved), 1)
        self.assertRegex(saved[0].name, r"^diagnostika_\d{8}_\d{6}\.html$")
        self.assertIn("Content-Security-Policy", saved[0].read_text(encoding="utf-8"))
        self.assertIn("HTML pārskats saglabāts LOKĀLI", text)

    def test_no_consent_means_no_file_and_no_folder(self):
        pdf = self.write_pdf()
        self.run_main(["--interactive", str(pdf)], "", "", "n", "n")
        self.run_main(["--interactive", str(pdf)], "", "", "", "")                 # Enter = n
        self.assertFalse(self.localappdata.exists())

    def test_existing_reports_are_never_overwritten(self):
        folder = self.dir / "r"
        folder.mkdir()
        fixed = lambda: datetime.datetime(2026, 1, 2, 3, 4, 5)
        (folder / "diagnostika_20260102_030405.html").write_text("VECS", encoding="utf-8")
        (folder / "diagnostika_20260102_030405-1.html").write_text("VECS 1", encoding="utf-8")
        pdf = self.write_pdf()
        env = {"LOCALAPPDATA": str(self.dir / "la")}
        (self.dir / "la" / "MLK_diagnostika").mkdir(parents=True)
        for name in ("diagnostika_20260102_030405.html",):
            (self.dir / "la" / "MLK_diagnostika" / name).write_text("VECS", encoding="utf-8")
        options = cli.interactive_session(str(pdf), input_fn=scripted("", "", "j", "n"), say=lambda _: None, environ=env, now=fixed)
        self.assertEqual(options["html_path"].name, "diagnostika_20260102_030405-1.html")
        self.assertEqual((self.dir / "la" / "MLK_diagnostika" / "diagnostika_20260102_030405.html").read_text(encoding="utf-8"), "VECS")

    def test_unique_path_skips_existing_names(self):
        (self.dir / "a.html").write_text("1", encoding="utf-8")
        (self.dir / "a-1.html").write_text("2", encoding="utf-8")
        self.assertEqual(cli.unique_path(self.dir, "a", ".html").name, "a-2.html")
        self.assertEqual(cli.unique_path(self.dir, "b", ".html").name, "b.html")

    def test_a_default_folder_that_looks_synced_is_refused_even_after_yes(self):
        pdf = self.write_pdf()
        env = {"LOCALAPPDATA": str(self.dir / "OneDrive - Firma" / "AppData")}
        code, text, _ = self.run_main(["--interactive", str(pdf)], "", "", "j", "n", env=env)
        self.assertEqual(code, 0)
        self.assertIn("šķiet sinhronizēta: pārskats netiek saglabāts", text)
        self.assertFalse((self.dir / "OneDrive - Firma").exists())


class TestReportsFolders(Workdir):
    def test_default_reports_dir(self):
        self.assertEqual(cli.default_reports_dir({"LOCALAPPDATA": "C:\\Users\\X\\AppData\\Local"}),
                         pathlib.Path("C:\\Users\\X\\AppData\\Local") / "MLK_diagnostika")
        self.assertEqual(cli.default_reports_dir({"XDG_DATA_HOME": "/data"}), pathlib.Path("/data/MLK_diagnostika"))
        self.assertEqual(cli.default_reports_dir({}).name, "MLK_diagnostika")
        self.assertIn(".local", cli.default_reports_dir({}).parts)

    def test_default_dir_is_not_synced_and_not_inside_the_repository(self):
        folder = cli.default_reports_dir({"LOCALAPPDATA": str(self.localappdata)})
        self.assertFalse(cli.is_synced_folder(folder, {}))
        self.assertNotIn(ROOT, folder.resolve().parents)

    def test_synced_folder_detection(self):
        for name in ("OneDrive", "OneDrive - Firma", "OneDrive - Personal", "Dropbox", "Dropbox (Personal)", "Google Drive",
                     "GoogleDrive", "iCloudDrive", "iCloud Drive", "pCloudDrive", "Nextcloud", "ownCloud", "MEGA", "Box",
                     "Box Sync", "Sync", "SharePoint", "onedrive"):
            self.assertTrue(cli.is_synced_folder(self.dir / name / "Documents" / "x", {}), name)
        for name in ("Documents", "Boxes", "Syncfusion", "Megastore", "Omega", "MLK_diagnostika", "local_reports", "Dropbo", "Downloads"):
            self.assertFalse(cli.is_synced_folder(self.dir / name / "x", {}), name)

    def test_environment_defined_sync_roots_are_detected(self):
        root = self.dir / "Pasts" / "Sinhr"
        env = {"OneDriveCommercial": str(root)}
        self.assertTrue(cli.is_synced_folder(root / "dokumenti", env))
        self.assertFalse(cli.is_synced_folder(self.dir / "cits", env))


class TestExplicitOutputsAreGuardedToo(Workdir):
    def test_explicit_html_and_summary_in_a_synced_folder_are_refused_without_the_flag(self):
        pdf = self.write_pdf()
        for flag in ("--html", "--summary-out"):
            target = self.dir / "Dropbox" / "r.out"
            code, text, _ = self.run_main([str(pdf), flag, str(target)])
            self.assertEqual(code, 2, flag)
            self.assertIn("šķiet sinhronizēta", text)
            self.assertIn("--allow-synced-folder", text)
            self.assertFalse((self.dir / "Dropbox").exists(), flag)

    def test_explicit_consent_allows_a_synced_folder(self):
        pdf = self.write_pdf()
        target = self.dir / "OneDrive" / "r.html"
        code, text, _ = self.run_main([str(pdf), "--html", str(target), "--allow-synced-folder", "--no-preview"])
        self.assertEqual(code, 0)
        self.assertTrue(target.exists())

    def test_explicit_html_still_needs_overwrite_consent(self):
        pdf = self.write_pdf()
        target = self.dir / "r.html"
        target.write_text("VECS", encoding="utf-8")
        code, text, _ = self.run_main([str(pdf), "--html", str(target)])
        self.assertEqual((code, target.read_text(encoding="utf-8")), (2, "VECS"))


if __name__ == "__main__":
    unittest.main()
