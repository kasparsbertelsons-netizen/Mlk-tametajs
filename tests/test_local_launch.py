"""Lokālās palaišanas (Windows 11) konfigurācijas testi (Issue #8).

PLATFORMAS: šie testi darbojas uz Linux (izstrādes sesijas konteiners). `.bat` skripti Windows šeit NAV izpildīti:
tiek pārbaudīts to saturs (statiski). Visa loģika, kas var salūzt (atkarību pārbaude, instalēšana, ports, palaišana,
ievades apstrāde), ir Python (`tools/local_setup.py`, `tools/ad_diagnostics.py`) un tiek testēta īstā procesā.
"""
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import tomllib
import unittest
import urllib.request
from importlib.metadata import metadata

from tools import local_setup

ROOT = pathlib.Path(__file__).resolve().parent.parent
START = ROOT / "start_mlk_windows.bat"
DIAG = ROOT / "diagnostika_windows.bat"
FORBIDDEN_WORDS = ("ngrok", "tunnel", "cloudflared", "localtunnel", "serveo", "curl ", "wget", "invoke-webrequest",
                   "bitsadmin", "certutil", "0.0.0.0", "--server.address 0", "share.streamlit", "streamlit.io")
START_RUN_LINE = '".venv\\Scripts\\python.exe" tools\\local_setup.py start %UPDATE%'
DIAG_RUN_LINE = '".venv\\Scripts\\python.exe" -m tools.ad_diagnostics --interactive "%~1"'
ALLOWED_EXPANSIONS = {"%~dp0", "%~1", "%PY%", "%UPDATE%", "%ERRORLEVEL%", "%EXITCODE%"}


def bat_lines(path):
    return path.read_bytes().decode("ascii").split("\r\n")


def code_lines(path):
    """Rindas bez REM komentāriem."""
    return [l for l in bat_lines(path) if not l.strip().lower().startswith("rem ")]


class TestBatFiles(unittest.TestCase):
    def test_ascii_only_and_crlf_only(self):
        for path in (START, DIAG):
            raw = path.read_bytes()
            raw.decode("ascii")                                              # ASCII: cmd kodlapu problēmu dēļ
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), path.name)  # nav tukšu LF
            self.assertNotIn(b"\x00", raw)

    def test_gitattributes_keeps_crlf(self):
        self.assertIn("*.bat text eol=crlf", (ROOT / ".gitattributes").read_text(encoding="utf-8"))

    def test_start_script_runs_one_fixed_command_and_no_pip(self):
        lines = code_lines(START)
        self.assertEqual([l for l in lines if "local_setup.py" in l], [START_RUN_LINE])
        for path in (START, DIAG):
            self.assertNotIn("pip", "\n".join(code_lines(path)).lower(), path.name)   # instalēšana nav .bat

    def test_update_flag_is_mapped_to_a_fixed_string_only(self):
        lines = code_lines(START)
        self.assertIn('set "UPDATE="', lines)
        self.assertIn('if /i "%~1"=="--update" set "UPDATE=--update"', lines)
        self.assertEqual([l for l in lines if "UPDATE=" in l], ['set "UPDATE="', 'if /i "%~1"=="--update" set "UPDATE=--update"'])

    def test_diagnostics_script_runs_one_fixed_command_without_user_input(self):
        lines = code_lines(DIAG)
        self.assertEqual([l for l in lines if "tools.ad_diagnostics" in l], [DIAG_RUN_LINE])
        text = "\n".join(lines).lower()
        for banned in ("set /p", "%*", "%pdfpath%", "%pages%", "%controls%", "%args%", "--html", "--summary-out",
                       "--overwrite", "--print-summary", "local_reports", "shell"):
            self.assertNotIn(banned, text, banned)

    def test_only_whitelisted_variable_expansions_and_user_values_always_quoted(self):
        for path in (START, DIAG):
            for line in code_lines(path):
                for token in re.findall(r"%[^%\s]*%|%~\w+", line):
                    self.assertIn(token, ALLOWED_EXPANSIONS, f"{path.name}: {line}")
                if "%~1" in line and "set " not in line.lower():
                    self.assertIn('"%~1"', line)                              # lietotāja arguments tikai pēdiņās

    def test_no_tunnelling_publishing_or_downloading(self):
        for path in (START, DIAG):
            low = "\n".join(bat_lines(path)).lower()
            for word in FORBIDDEN_WORDS:
                self.assertNotIn(word, low, f"{path.name}: {word}")
            for url in re.findall(r"https?://\S+", low):
                self.assertTrue(url.startswith("http://127.0.0.1"), f"{path.name}: {url}")

    def test_start_script_never_calls_the_network_itself(self):
        self.assertEqual([l for l in code_lines(START) if "install" in l.lower()], [])

    def test_python_version_check_matches_streamlit_requirement(self):
        self.assertIn("sys.version_info >= (3, 11)", "\n".join(bat_lines(START)))
        self.assertEqual(local_setup.MIN_PYTHON, (3, 11))
        requires = metadata("streamlit")["Requires-Python"]
        self.assertIn("3.11", requires, "Streamlit minimālā Python versija mainījusies: atjauniniet .bat un dokumentus")
        self.assertIn("Python 3.11", (ROOT / "docs" / "LOCAL_WINDOWS.md").read_text(encoding="utf-8"))

    def test_scripts_report_errors_and_keep_the_window_open(self):
        lines = "\n".join(bat_lines(START))
        for needle in ("if errorlevel 1 goto :venvfail", "if errorlevel 1 goto :oldpython", ":nopython", "pause", 'cd /d "%~dp0"'):
            self.assertIn(needle, lines)
        diag = "\n".join(bat_lines(DIAG))
        self.assertIn("pause", diag)
        self.assertIn(":notready", diag)
        self.assertIn("local_setup.py check", diag)

    def test_goto_targets_exist_and_blocks_have_no_risky_characters(self):
        for path in (START, DIAG):
            lines = bat_lines(path)
            labels = {l.strip().lower() for l in lines if re.match(r"^:\w+", l.strip())}
            for line in lines:
                match = re.search(r"goto\s+(:\w+)", line, flags=re.I)
                if match:
                    self.assertIn(match.group(1).lower(), labels, f"{path.name}: {line}")
            depth = 0                                                         # echo bloku iekšienē nedrīkst būt ) ( & | < > ^ %
            for line in lines:
                stripped = line.strip()
                if depth and stripped.lower().startswith("echo"):
                    self.assertIsNone(re.search(r"[()&|<>^%]", stripped[4:]), f"{path.name}: {line}")
                if stripped.endswith("("):
                    depth += 1
                elif stripped == ")":
                    depth -= 1
            self.assertEqual(depth, 0, path.name)

    def test_the_documented_internet_use_is_in_the_script_banner(self):
        banner = "\n".join(bat_lines(START)).lower()
        self.assertIn("internets vajadzigs tikai atkaribu instalesanai", banner)
        self.assertIn("--update", banner)


class TestRepositorySafety(unittest.TestCase):
    def test_gitignore_protects_pdfs_venv_and_local_reports(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for pattern in ("*.pdf", ".venv/", "local_reports/"):
            self.assertIn(pattern, ignore)
        self.assertNotIn("!*.pdf", ignore)

    def test_public_app_config_is_unchanged(self):
        config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual((config["server"]["maxUploadSize"], config["server"]["enableXsrfProtection"], config["browser"]["gatherUsageStats"]),
                         (30, True, False))
        self.assertNotIn("address", config["server"])

    def test_no_pdf_is_tracked_outside_the_synthetic_samples(self):
        try:
            result = subprocess.run(["git", "ls-files", "*.pdf"], cwd=ROOT, capture_output=True, text=True)
        except FileNotFoundError:
            self.skipTest("git nav pieejams (piem., ZIP lejupielāde)")                     # skaidri paziņots
        if result.returncode != 0:
            self.skipTest("mape nav Git repozitorijs (piem., ZIP lejupielāde)")
        self.assertTrue(all(p.startswith("samples/ad_vector/") for p in result.stdout.split()), result.stdout)

    def test_docs_are_honest_about_what_was_tested_and_about_internet_use(self):
        text = (ROOT / "docs" / "LOCAL_WINDOWS.md").read_text(encoding="utf-8")
        self.assertIn("Windows 11: `.bat` skripti šajā sesijā NAV izpildīti", text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("Parastai atkārtotai palaišanai un PDF apstrādei internets nav vajadzīgs", text)
        self.assertIn("--update", text)
        self.assertIn("%LOCALAPPDATA%", text)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for needle in ("start_mlk_windows.bat", "diagnostika_windows.bat", "127.0.0.1", "nav izpildīts", "nākamajās reizēs internets nav vajadzīgs",
                       "--update", "ārpus sinhronizētām mapēm"):
            self.assertIn(needle, readme)
        validation = (ROOT / "docs" / "REAL_AD_VALIDATION.md").read_text(encoding="utf-8")
        for needle in ("150×240", "TR-126", "--page", "--control", "Nesalīdziniet citu projektu AD un PD", "neko neizdomājiet",
                       "--interactive", "--allow-synced-folder", "nekad netiek pārrakstīts bez jūsu piekrišanas"):
            self.assertIn(needle, validation)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def non_loopback_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))                                 # UDP: nekas netiek sūtīts
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


class Server:
    """Palaiž procesu un gaida /_stcore/health; `stop()` apturē un atgriež visu izvadi."""

    def __init__(self, argv, port):
        self.port = port
        env = {k: v for k, v in os.environ.items() if k != "STREAMLIT_BROWSER_GATHER_USAGE_STATS"}
        self.proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     start_new_session=(os.name == "posix"))      # procesu grupa: nekas nepaliek dzīvs
        self.output = None
        self.forced = False                                                           # vai vajadzēja piespiedu nogalināšanu
        self.ready = False
        deadline = time.time() + 60
        while time.time() < deadline and self.proc.poll() is None and not self.ready:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as r:
                    self.ready = r.read().strip() == b"ok"
            except OSError:
                time.sleep(0.3)

    def stop(self):
        if self.output is None:
            self.proc.terminate()
            try:
                self.output, _ = self.proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                self.forced = True
                if os.name == "posix":
                    os.killpg(self.proc.pid, 9)                                       # visa grupa, arī bērnprocesi
                else:
                    self.proc.kill()
                self.output, _ = self.proc.communicate(timeout=15)
            if os.name == "posix":
                try:
                    os.killpg(self.proc.pid, 9)                                       # drošības tīkls: bērnprocesu palieku nav
                except ProcessLookupError:
                    pass
        return self.output


class TestRealProcessThroughTheLauncher(unittest.TestCase):
    """Īsts process caur TO PAŠU palīgu, ko palaiž `start_mlk_windows.bat`."""

    def test_launcher_starts_the_app_on_loopback_only_without_reinstalling(self):
        port = free_port()
        server = Server([sys.executable, str(ROOT / "tools" / "local_setup.py"), "start", "--no-browser", "--port", str(port)], port)
        self.addCleanup(server.stop)
        self.assertTrue(server.ready, "lietotne neatbildēja uz 127.0.0.1")
        ip = non_loopback_ip()
        if ip is None:
            self.skipTest("šajā vidē nav ne-loopback IP adreses, ko pārbaudīt")        # skaidri paziņots, nevis kluss
        with self.assertRaises(OSError):                                               # no citas adreses nav pieejams
            socket.create_connection((ip, port), timeout=3).close()
        output = server.stop()
        self.assertIn("Atkarības jau ir instalētas: internets nav vajadzīgs.", output)
        self.assertFalse(server.forced, "palīgs neapturēja Streamlit bērnprocesu pēc SIGTERM")  # nav palicis dzīvs bērnprocess
        self.assertNotIn("Collecting", output)                                         # pip netika izsaukts
        self.assertNotIn("Instalēju", output)
        self.assertIn(f"Uvicorn server started on 127.0.0.1:{port}", output)
        self.assertIn(f"URL: http://127.0.0.1:{port}", output)
        for forbidden in ("Network URL", "External URL", "0.0.0.0"):
            self.assertNotIn(forbidden, output)

    def test_negative_control_without_the_address_flag_is_detected(self):
        # Pārbauda, ka iepriekšējais tests spēj atšķirt: bez --server.address Streamlit klausās arī uz citām adresēm.
        port = free_port()
        command = local_setup.build_streamlit_command(port, headless=True)
        i = command.index("--server.address")
        del command[i:i + 2]
        server = Server(command, port)
        self.addCleanup(server.stop)
        self.assertTrue(server.ready)
        self.assertIn("Network URL", server.stop())

    def test_check_command_succeeds_in_this_prepared_environment(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "local_setup.py"), "check"], cwd=ROOT,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestTelemetryIsOffByEnvironment(unittest.TestCase):
    def test_env_variable_disables_usage_stats(self):
        code = "from streamlit import config; print(config.get_option('browser.gatherUsageStats'))"
        env = {**os.environ, "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "False")


if __name__ == "__main__":
    unittest.main()
