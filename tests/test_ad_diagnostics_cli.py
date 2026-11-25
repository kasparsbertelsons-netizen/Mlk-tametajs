"""Lokālā diagnostikas komandrindas rīka testi (tools/ad_diagnostics.py, Issue #8). Tikai sintētiski PDF."""
import ast
import contextlib
import io
import json
import os
import pathlib
import re
import socket
import tempfile
import unittest
from unittest import mock

from src import ad_diagnostics as diag
from tests.synthetic_pdfs import SECRET, custom_pdf, plan_view_pdf, sensitive_pdf
from tools import ad_diagnostics as cli
from tools import synthetic_ad_pdf as gen

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "samples" / "ad_vector" / "ad_vector_01_12000x4000_1to50.pdf"
FORBIDDEN_IMPORTS = {"socket", "ssl", "urllib", "http", "httpx", "requests", "aiohttp", "ftplib", "smtplib", "telnetlib",
                     "webbrowser", "subprocess", "xmlrpc", "imaplib", "poplib", "websocket", "websockets"}


def run_cli(*args):
    out = io.StringIO()
    code = cli.main([str(a) for a in args], out=out)
    return code, out.getvalue()


class Workdir(unittest.TestCase):
    """Katrs tests darbojas pagaidu mapē, lai pārbaudītu, vai rīks neveido nevēlamus failus."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self._cwd)

    def write_pdf(self, data, name="plans.pdf"):
        path = self.dir / name
        path.write_bytes(data)
        return path

    def files(self):
        return sorted(str(p.relative_to(self.dir)) for p in self.dir.rglob("*"))


class TestDefaultBehaviour(Workdir):
    def test_default_run_prints_a_report_and_creates_no_files(self):
        pdf = self.write_pdf(SAMPLE.read_bytes())
        before = self.files()
        code, text = run_cli(pdf)
        self.assertEqual(code, 0)
        self.assertEqual(self.files(), before)
        for expected in ("LOKĀLS PĀRSKATS", "Nekopīgot", "LAPAS (NOLASĪTS NO PDF)", "ANALĪZE, 2. LAPA (NOLASĪTS NO PDF",
                         "Mērogs lapā norādīts: 1:50", "kandidāts P2-K1", "izslēgts (room)", "izslēgts (terrace)",
                         "pamatrāmis neietver 150×240"):
            self.assertIn(expected, text)
        self.assertNotIn("SANITIZĒTAIS KOPSAVILKUMS", text)                 # kopsavilkums tikai pēc pieprasījuma

    def test_page_table_shows_every_page_with_vector_counts(self):
        _, text = run_cli(self.write_pdf(SAMPLE.read_bytes()))
        self.assertRegex(text, r"1\s+titullapa/saraksts")
        self.assertRegex(text, r"2\s+grīdas plāns\s+\d+\s+25\s+5/0\s+5/7\s+8/0\s+0\s+0\s+\*")
        self.assertRegex(text, r"3\s+jumta plāns")

    def test_read_data_and_user_controls_are_separated(self):
        _, text = run_cli(self.write_pdf(SAMPLE.read_bytes()), "--control", "9999x3333", "--control", "12000x4000")
        marker = "LIETOTĀJA KONTROLIZMĒRI (ievadīti ar --control; NAV nolasīti no PDF)"
        self.assertIn(marker, text)
        read_part, control_part = text.split(marker)
        self.assertNotIn("9999", read_part)                                  # kontrolizmērs nav nolasītajā daļā
        self.assertIn("1. 9999×3333 mm", control_part)
        self.assertIn("SALĪDZINĀJUMS: nolasītais pret lietotāja kontroli", control_part)
        self.assertIn("kontrole 2 (12000×4000) ↔ P2-K1", control_part)
        self.assertIn("sakrīt (≤ 0,5 %)", control_part)
        self.assertIn("kontrole 1 (9999×3333): nav nolasīta kandidāta", control_part)

    def test_deviation_is_reported_with_numbers_locally(self):
        _, text = run_cli(self.write_pdf(SAMPLE.read_bytes()), "--control", "12300x4000")
        self.assertRegex(text, r"novirze L -300 mm, W \+0 mm \(2\.44 %\): vidēja novirze")

    def test_manual_page_when_the_classifier_misses_the_plan(self):
        pdf = self.write_pdf(plan_view_pdf())
        code, auto = run_cli(pdf)
        self.assertEqual(code, 0)
        self.assertIn("Automātiskais klasifikators neatrada grīdas plāna lapu", auto)
        self.assertIn("--page N", auto)
        self.assertNotIn("kandidāts P1-K1", auto)
        _, manual = run_cli(pdf, "--page", "1", "--control", "12000x4000")
        self.assertIn("režīms 'manual'", manual)
        self.assertIn("kandidāts P1-K1: ģeometriski saskaņots, 12000×4000 mm", manual)
        self.assertIn("sakrīt (≤ 0,5 %)", manual)

    def test_failure_reasons_are_shown_for_pages_without_vectors_l_shapes_and_scale_conflicts(self):
        _, text = run_cli(self.write_pdf(gen.build_sample_08()))
        self.assertIn("NEVEICĀS/NEPIETIEK: Lapā nav vektoru ģeometrijas", text)
        _, text = run_cli(self.write_pdf(gen.build_sample_04(), "l.pdf"))
        self.assertIn("kandidāts P1-K1: atteikums, L/W netiek piedāvāti, iemeslu kodi: SHAPE_NOT_RECTANGLE", text)
        _, text = run_cli(self.write_pdf(gen.build_sample_06(), "s.pdf"))
        self.assertIn("SCALE_CONFLICT", text)
        self.assertIn("Norādīts mērogs 1:100, bet izmēru norādes izsaka 1:50", text)
        self.assertIn("Mērogs lapā norādīts: 1:100", text)

    def test_unicode_and_spaces_in_the_file_name(self):
        pdf = self.write_pdf(SAMPLE.read_bytes(), "Mans rasējums ā ē.pdf")
        code, text = run_cli(pdf)
        self.assertEqual(code, 0)
        self.assertIn("Mans rasējums ā ē.pdf", text)


class TestErrors(Workdir):
    def test_user_errors_give_exit_code_2_and_clear_messages(self):
        pdf = self.write_pdf(SAMPLE.read_bytes())
        cases = ([], [self.dir / "nav.pdf"], [pdf, "--control", "abc"], [pdf, "--page", "0"], [pdf, "--page", "x"])
        expected = ("Norādiet PDF failu", "Fails nav atrasts", "Nederīgs kontrolizmērs", "Nederīgs lapu", "Nederīgs lapu")
        for args, message in zip(cases, expected):
            code, text = run_cli(*args)
            self.assertEqual(code, 2, args)
            self.assertIn("KĻŪDA:", text)
            self.assertIn(message, text)
            self.assertNotIn("Traceback", text)

    def test_not_a_pdf_is_reported_not_crashed(self):
        code, text = run_cli(self.write_pdf(b"this is not a pdf", "fake.pdf"))
        self.assertEqual(code, 1)
        self.assertIn("Ievades statuss: invalid_pdf", text)
        self.assertIn("Fails nav atpazīts kā PDF", text)

    def test_page_out_of_range_is_reported(self):
        _, text = run_cli(self.write_pdf(SAMPLE.read_bytes()), "--page", "2,99")
        self.assertIn("Nederīgi lapu numuri (ārpus 1–3): [99]", text)
        self.assertIn("kandidāts P2-K1", text)


class TestOptionalLocalOutputs(Workdir):
    def test_html_report_is_saved_only_when_requested(self):
        pdf = self.write_pdf(SAMPLE.read_bytes())
        code, text = run_cli(pdf, "--html", "local_reports/parskats.html", "--control", "12000x4000")
        self.assertEqual(code, 0)
        self.assertEqual(self.files(), ["local_reports", "local_reports/parskats.html", "plans.pdf"])
        self.assertIn("HTML pārskats saglabāts LOKĀLI", text)
        page = (self.dir / "local_reports" / "parskats.html").read_text(encoding="utf-8")
        for expected in ("NOLASĪTS NO PDF", "LIETOTĀJA KONTROLIZMĒRI (nav nolasīti no PDF)", "Content-Security-Policy",
                         "default-src 'none'", "<img alt='Lapas priekšskatījums' src='data:image/png;base64,", "Nekopīgot"):
            self.assertIn(expected, page)
        self.assertNotIn("<script", page.lower())
        self.assertIsNone(re.search(r"(?:src|href)=['\"]https?:", page))     # nekādu ārēju resursu

    def test_no_preview_flag_omits_images(self):
        pdf = self.write_pdf(SAMPLE.read_bytes())
        run_cli(pdf, "--html", "r.html", "--no-preview")
        self.assertNotIn("<img", (self.dir / "r.html").read_text(encoding="utf-8"))

    def test_pdf_text_is_html_escaped_in_the_report(self):
        def draw(sheet):
            gen._module(sheet, 150, 260, 12000, 4000, 50, label="<script>alert('x')</script> MODULIS")
        pdf = self.write_pdf(custom_pdf(draw))
        run_cli(pdf, "--html", "r.html")
        page = (self.dir / "r.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; MODULIS", page)
        self.assertEqual(page.lower().count("<script"), 0)

    def test_existing_files_are_not_overwritten_without_flag(self):
        pdf = self.write_pdf(SAMPLE.read_bytes())
        (self.dir / "r.html").write_text("vecs saturs", encoding="utf-8")
        code, text = run_cli(pdf, "--html", "r.html")
        self.assertEqual(code, 2)
        self.assertIn("Fails jau pastāv", text)
        self.assertEqual((self.dir / "r.html").read_text(encoding="utf-8"), "vecs saturs")
        code, _ = run_cli(pdf, "--html", "r.html", "--overwrite")
        self.assertEqual(code, 0)
        self.assertIn("Lokāls AD diagnostikas pārskats", (self.dir / "r.html").read_text(encoding="utf-8"))

    def test_output_can_never_overwrite_a_pdf(self):
        pdf = self.write_pdf(SAMPLE.read_bytes())
        original = pdf.read_bytes()
        for target in (pdf, self.dir / "other.PDF", self.dir / "x.pdf"):
            code, text = run_cli(pdf, "--summary-out", target, "--overwrite")
            self.assertEqual(code, 2, target)
            self.assertIn("nedrīkst būt PDF", text)
        self.assertEqual(pdf.read_bytes(), original)

    def test_html_and_summary_must_be_different_files(self):
        pdf = self.write_pdf(SAMPLE.read_bytes())
        code, text = run_cli(pdf, "--html", "same.txt", "--summary-out", "same.txt")
        self.assertEqual(code, 2)
        self.assertIn("dažādiem failiem", text)
        self.assertNotIn("same.txt", self.files())


class TestSanitisedSummaryOutput(Workdir):
    def test_summary_is_printed_for_review_and_saved_only_on_request(self):
        pdf = self.write_pdf(sensitive_pdf(), f"{SECRET}-PROJ-9981.pdf")
        code, text = run_cli(pdf, "--control", "12399x4300", "--print-summary")
        self.assertEqual(code, 0)
        self.assertIn("SANITIZĒTAIS KOPSAVILKUMS (apskatiet pirms kopīgošanas; rīks to nekur nesūta)", text)
        self.assertEqual(self.files(), [f"{SECRET}-PROJ-9981.pdf"])         # nekas nav saglabāts
        printed = text.split("kopīgošanas; rīks to nekur nesūta) ===")[1].split("Satur tikai")[0]
        summary = json.loads(printed)
        diag.validate_summary(summary)
        for leaked in (SECRET, "PROJ-9981", "12345", "4321", "12399", "4300", ".pdf"):
            self.assertNotIn(leaked, printed)

    def test_summary_file_contains_only_the_allowed_fields(self):
        pdf = self.write_pdf(sensitive_pdf(), f"{SECRET}-PROJ-9981.pdf")
        code, text = run_cli(pdf, "--control", "12399x4300", "--summary-out", "kopsavilkums.json")
        self.assertEqual(code, 0)
        saved = (self.dir / "kopsavilkums.json").read_text(encoding="utf-8")
        diag.validate_summary(json.loads(saved))
        self.assertEqual(list(json.loads(saved)), list(diag.SUMMARY_FIELDS))
        for leaked in (SECRET, "PROJ-9981", "12345", "4321", "12399", "4300", "pdf"):
            self.assertNotIn(leaked, saved)
        self.assertIn("nekas netiek sūtīts automātiski", text)
        self.assertEqual(self.files(), [f"{SECRET}-PROJ-9981.pdf", "kopsavilkums.json"])

    def test_the_report_printed_next_to_the_summary_is_the_local_one(self):
        # Pilnais pārskats konsolē drīkst saturēt PDF saturu (tas ir lokāls); kopsavilkuma daļa nedrīkst.
        pdf = self.write_pdf(sensitive_pdf(), "x.pdf")
        _, text = run_cli(pdf, "--print-summary")
        local, summary = text.split("=== SANITIZĒTAIS KOPSAVILKUMS")
        self.assertIn("12345", local)
        self.assertNotIn("12345", summary)

    def test_allowed_fields_listing_needs_no_pdf(self):
        code, text = run_cli("--allowed-fields")
        self.assertEqual(code, 0)
        for name in diag.SUMMARY_FIELDS:
            self.assertIn(name, text)
        self.assertIn("NEKAD netiek iekļauts", text)
        self.assertIn("faktiskie izmēri", text)


class TestNothingIsSentAnywhere(Workdir):
    def test_modules_import_no_network_or_process_libraries(self):
        for path in (ROOT / "src" / "ad_diagnostics.py", ROOT / "tools" / "ad_diagnostics.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertEqual(imported & FORBIDDEN_IMPORTS, set(), path.name)

    def test_a_full_run_makes_no_network_connection(self):
        pdf = self.write_pdf(SAMPLE.read_bytes())
        with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("tīkla savienojums")), \
             mock.patch.object(socket.socket, "connect_ex", side_effect=AssertionError("tīkla savienojums")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("tīkla savienojums")):
            code, _ = run_cli(pdf, "--control", "12000x4000", "--html", "r.html", "--summary-out", "s.json")
        self.assertEqual(code, 0)

    def test_report_banner_says_not_to_share(self):
        _, text = run_cli(self.write_pdf(SAMPLE.read_bytes()))
        self.assertIn("Nekopīgot, nepublicēt, neievietot GitHub", text)


if __name__ == "__main__":
    unittest.main()
