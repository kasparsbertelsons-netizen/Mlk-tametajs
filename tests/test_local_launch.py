"""Lokālās palaišanas (Windows 11) konfigurācijas testi (Issue #8).

PLATFORMAS: šie testi darbojas uz Linux (izstrādes sesijas konteiners). `.bat` skripti Windows šeit NAV izpildīti:
tiek pārbaudīts to saturs (statiski), un reāls Streamlit process tiek palaists ar TIEŠI tiem pašiem parametriem, kas
ir `.bat`, lai pārbaudītu, ka tas klausās tikai loopback adresē.
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

ROOT = pathlib.Path(__file__).resolve().parent.parent
START = ROOT / "start_mlk_windows.bat"
DIAG = ROOT / "diagnostika_windows.bat"
FORBIDDEN_WORDS = ("ngrok", "tunnel", "cloudflared", "localtunnel", "serveo", "curl ", "wget", "invoke-webrequest",
                   "bitsadmin", "certutil", "0.0.0.0", "--server.address 0", "share.streamlit", "streamlit.io")


def bat_lines(path):
    return path.read_bytes().decode("ascii").split("\r\n")


class TestBatFiles(unittest.TestCase):
    def test_ascii_only_and_crlf_only(self):
        for path in (START, DIAG):
            raw = path.read_bytes()
            raw.decode("ascii")                                              # ASV: cmd kodlapu problēmu dēļ
            self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), path.name)  # nav tukšu LF
            self.assertNotIn(b"\x00", raw)

    def test_gitattributes_keeps_crlf(self):
        self.assertIn("*.bat text eol=crlf", (ROOT / ".gitattributes").read_text(encoding="utf-8"))

    def test_start_script_binds_only_to_loopback_without_telemetry(self):
        text = "\n".join(bat_lines(START))
        self.assertIn("--server.address 127.0.0.1", text)
        self.assertIn("--browser.gatherUsageStats false", text)
        self.assertIn('set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"', text)
        self.assertEqual(len(re.findall(r"--server\.address\s+(\S+)", text)), 1)
        self.assertEqual(re.findall(r"--server\.address\s+(\S+)", text), ["127.0.0.1"])
        self.assertIn('-m streamlit run app.py', text)
        self.assertIn('".venv\\Scripts\\python.exe"', text)

    def test_no_tunnelling_publishing_or_downloading(self):
        for path in (START, DIAG):
            low = "\n".join(bat_lines(path)).lower()
            for word in FORBIDDEN_WORDS:
                self.assertNotIn(word, low, f"{path.name}: {word}")
            for url in re.findall(r"https?://\S+", low):
                self.assertTrue(url.startswith("http://127.0.0.1"), f"{path.name}: {url}")

    def test_only_requirements_are_installed(self):
        installs = [l for l in bat_lines(START) if "pip install" in l.lower()]
        self.assertEqual(len(installs), 1)
        self.assertRegex(installs[0], r"-m pip install --disable-pip-version-check -r requirements\.txt$")
        self.assertEqual([l for l in bat_lines(DIAG) if "pip" in l.lower()], [])

    def test_python_version_check_matches_streamlit_requirement(self):
        self.assertIn("sys.version_info >= (3, 11)", "\n".join(bat_lines(START)))
        requires = metadata("streamlit")["Requires-Python"]
        self.assertIn("3.11", requires, "Streamlit minimālā Python versija mainījusies: atjauniniet .bat un dokumentus")
        self.assertIn("Python 3.11", (ROOT / "docs" / "LOCAL_WINDOWS.md").read_text(encoding="utf-8"))

    def test_scripts_stop_and_report_errors_and_keep_the_window_open(self):
        lines = "\n".join(bat_lines(START))
        for needle in ("if errorlevel 1 goto :venvfail", "if errorlevel 1 goto :pipfail", "if errorlevel 1 goto :oldpython",
                       ":nopython", "pause", 'cd /d "%~dp0"'):
            self.assertIn(needle, lines)
        self.assertIn("pause", "\n".join(bat_lines(DIAG)))

    def test_goto_targets_exist_and_blocks_have_no_risky_characters(self):
        for path in (START, DIAG):
            lines = bat_lines(path)
            labels = {l.strip().lower() for l in lines if re.match(r"^:\w+", l.strip())}
            for line in lines:
                match = re.search(r"goto\s+(:\w+)", line, flags=re.I)
                if match:
                    self.assertIn(match.group(1).lower(), labels, f"{path.name}: {line}")
            depth = 0                                                         # echo bloku iekšienē nedrīkst būt ) ( & | < >
            for line in lines:
                stripped = line.strip()
                if depth and stripped.lower().startswith("echo"):
                    self.assertIsNone(re.search(r"[()&|<>^%]", stripped[4:]), f"{path.name}: {line}")
                if stripped.endswith("("):
                    depth += 1
                elif stripped == ")":
                    depth -= 1
            self.assertEqual(depth, 0, path.name)

    def test_diagnostics_script_is_local_and_saves_only_on_request(self):
        lines = bat_lines(DIAG)
        text = "\n".join(lines)
        self.assertIn('".venv\\Scripts\\python.exe" -m tools.ad_diagnostics', text)
        self.assertEqual([l for l in lines if "--summary-out" in l], [])     # kopsavilkums tiek tikai rādīts, nevis saglabāts
        html_lines = [l for l in lines if "--html" in l]
        self.assertEqual(len(html_lines), 1)
        self.assertTrue(html_lines[0].lower().startswith('if /i "%save%"=="j"'))   # tikai pēc lietotāja "J"
        self.assertIn("local_reports\\", html_lines[0])
        self.assertTrue(any(l.lower().startswith('if /i "%summ%"=="j"') and "--print-summary" in l for l in lines))


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

    def test_docs_are_honest_about_what_was_tested(self):
        text = (ROOT / "docs" / "LOCAL_WINDOWS.md").read_text(encoding="utf-8")
        self.assertIn("Windows 11: `.bat` skripti šajā sesijā NAV izpildīti", text)
        self.assertIn("127.0.0.1", text)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for needle in ("start_mlk_windows.bat", "diagnostika_windows.bat", "127.0.0.1", "nav izpildīts"):
            self.assertIn(needle, readme)
        validation = (ROOT / "docs" / "REAL_AD_VALIDATION.md").read_text(encoding="utf-8")
        for needle in ("150×240", "TR-126", "--page", "--control", "Nesalīdziniet citu projektu AD un PD", "neko neizdomājiet"):
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


def bat_streamlit_flags(port, drop_address=False):
    """Karodziņi no start_mlk_windows.bat; port aizvietots, headless ieslēgts (testā nevajag atvērt pārlūku)."""
    line = next(l for l in bat_lines(START) if "-m streamlit run" in l)
    flags = [str(port) if f == "%MLK_PORT%" else f for f in line.split("app.py", 1)[1].split()]
    flags[flags.index("--server.headless") + 1] = "true"
    if drop_address:
        i = flags.index("--server.address")
        del flags[i:i + 2]
    return flags


class StreamlitProcess:
    """Palaiž īstu Streamlit; `stop()` apturē un atgriež visu izvadi."""

    def __init__(self, drop_address=False):
        self.port = free_port()
        self.flags = bat_streamlit_flags(self.port, drop_address)
        env = {**os.environ, "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
        self.proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", *self.flags], cwd=ROOT, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.output = None
        self.ready = False
        deadline = time.time() + 60
        while time.time() < deadline and self.proc.poll() is None and not self.ready:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/_stcore/health", timeout=2) as r:
                    self.ready = r.read().strip() == b"ok"
            except OSError:
                time.sleep(0.3)

    def stop(self):
        if self.output is None:
            self.proc.terminate()
            try:
                self.output, _ = self.proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.output, _ = self.proc.communicate()
        return self.output


class TestRealStreamlitProcessWithTheBatParameters(unittest.TestCase):
    """Palaiž īstu Streamlit ar TIEŠI tiem pašiem parametriem, kas `start_mlk_windows.bat`."""

    def test_binds_only_to_loopback_and_prints_no_network_url(self):
        server = StreamlitProcess()
        self.addCleanup(server.stop)
        self.assertEqual(server.flags[server.flags.index("--server.address") + 1], "127.0.0.1")
        self.assertEqual(server.flags[server.flags.index("--browser.gatherUsageStats") + 1], "false")
        self.assertTrue(server.ready, "Streamlit neatbildēja uz 127.0.0.1")
        ip = non_loopback_ip()
        if ip is None:
            self.skipTest("šajā vidē nav ne-loopback IP adreses, ko pārbaudīt")        # skaidri paziņots, nevis kluss
        with self.assertRaises(OSError):                                               # no citas adreses nav pieejams
            socket.create_connection((ip, server.port), timeout=3).close()
        output = server.stop()
        self.assertIn(f"Uvicorn server started on 127.0.0.1:{server.port}", output)
        self.assertIn(f"URL: http://127.0.0.1:{server.port}", output)
        for forbidden in ("Network URL", "External URL", "0.0.0.0"):
            self.assertNotIn(forbidden, output)

    def test_negative_control_without_the_address_flag_is_detected(self):
        # Pārbauda, ka iepriekšējais tests spēj atšķirt: bez --server.address Streamlit klausās arī uz citām adresēm.
        server = StreamlitProcess(drop_address=True)
        self.addCleanup(server.stop)
        self.assertTrue(server.ready)
        output = server.stop()
        self.assertIn("Network URL", output)
        ip = non_loopback_ip()
        if ip is not None:
            second = StreamlitProcess(drop_address=True)
            self.addCleanup(second.stop)
            with socket.create_connection((ip, second.port), timeout=3):
                pass


class TestTelemetryIsOffByEnvironment(unittest.TestCase):
    def test_env_variable_disables_usage_stats(self):
        code = "from streamlit import config; print(config.get_option('browser.gatherUsageStats'))"
        env = {**os.environ, "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "False")


if __name__ == "__main__":
    unittest.main()
