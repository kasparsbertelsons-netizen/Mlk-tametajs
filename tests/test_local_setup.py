"""Lokālās palaišanas palīga testi (tools/local_setup.py, Issue #8): atkarību pārbaude BEZ interneta, instalēšana tikai
vajadzības gadījumā vai ar --update, komandas kā saraksti (bez shell), ports ar validāciju."""
import ast
import pathlib
import socket
import sys
import tempfile
import unittest
from unittest import mock

from tools import local_setup

ROOT = pathlib.Path(__file__).resolve().parent.parent
STDLIB_ONLY = {"argparse", "contextlib", "importlib", "os", "pathlib", "signal", "socket", "subprocess", "sys", "threading"}


class Result:
    def __init__(self, code=0):
        self.returncode = code


class FakeRun:
    """Aizstāj subprocess.run: ieraksta izsaukumus un neko neizpilda."""

    def __init__(self, codes=None):
        self.calls = []
        self.codes = list(codes or [])

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return Result(self.codes.pop(0) if self.codes else 0)

    @property
    def commands(self):
        return [c for c, _ in self.calls]


def requirements_file(text):
    tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write(text)
    tmp.close()
    return tmp.name


class TestUnsatisfied(unittest.TestCase):
    def test_current_environment_satisfies_the_repository_requirements(self):
        self.assertEqual(local_setup.unsatisfied(), [])

    def test_missing_package_is_reported_by_name_only(self):
        path = requirements_file("streamlit>=1.67.0,<2\nthis-package-does-not-exist-xyz>=1\n")
        self.assertEqual(local_setup.unsatisfied(path), ["this-package-does-not-exist-xyz"])

    def test_changed_requirement_triggers_reinstall(self):
        self.assertEqual(local_setup.unsatisfied(requirements_file("streamlit>=99\n")), ["streamlit"])
        self.assertEqual(local_setup.unsatisfied(requirements_file("PyMuPDF<1\n")), ["PyMuPDF"])

    def test_comments_and_blank_lines_are_ignored(self):
        path = requirements_file("# komentārs\n\nstreamlit>=1.67.0,<2   # inline\n   \n")
        self.assertEqual(local_setup.unsatisfied(path), [])

    def test_environment_without_packaging_is_treated_as_not_ready(self):
        with mock.patch.dict(sys.modules, {"packaging": None, "packaging.requirements": None}):
            self.assertEqual(local_setup.unsatisfied(), ["packaging"])

    def test_check_exit_codes(self):
        with mock.patch.object(local_setup, "unsatisfied", return_value=[]):
            self.assertEqual(local_setup.main(["check"]), 0)
        with mock.patch.object(local_setup, "unsatisfied", return_value=["streamlit"]):
            self.assertEqual(local_setup.main(["check"]), 1)


class TestCommandsAreListsWithoutShell(unittest.TestCase):
    def test_install_command(self):
        self.assertEqual(local_setup.build_install_command(),
                         [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"])

    def test_streamlit_command(self):
        command = local_setup.build_streamlit_command(8512)
        self.assertEqual(command, [sys.executable, "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1",
                                   "--server.port", "8512", "--server.headless", "false", "--browser.gatherUsageStats", "false"])
        self.assertEqual(local_setup.build_streamlit_command(8512, headless=True)[command.index("--server.headless") + 1], "true")
        self.assertTrue(all(isinstance(part, str) for part in command))
        self.assertNotIn("0.0.0.0", command)

    def test_port_must_be_an_integer(self):
        with self.assertRaises(ValueError):
            local_setup.build_streamlit_command("8501 & calc")

    def test_source_never_uses_a_shell_or_third_party_imports(self):
        source = (ROOT / "tools" / "local_setup.py").read_text(encoding="utf-8")
        for banned in ("shell=True", "os.system", "os.popen", "Popen("):
            self.assertNotIn(banned, source)
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        # `packaging` tiek importēts slinki funkcijā: pirms atkarību instalēšanas jāstrādā bez tā
        self.assertEqual(imported - STDLIB_ONLY - {"packaging"}, set())
        top_level = {n.names[0].name.split(".")[0] for n in ast.parse(source).body if isinstance(n, ast.Import)}
        self.assertNotIn("packaging", top_level)


class TestPort(unittest.TestCase):
    def test_default_and_valid_values(self):
        port, warning = local_setup.choose_port(environ={})
        self.assertGreaterEqual(port, local_setup.DEFAULT_PORT)
        self.assertEqual(local_setup.choose_port(preferred=free_port_above_1024(), environ={})[1], None)

    def test_hostile_or_invalid_values_fall_back_to_the_default_with_a_warning(self):
        for raw in ("8600 & calc", "abc", "80", "99999", "-5", "８６００", "8600;rm", "８", "1e3", " "):
            port, warning = local_setup.choose_port(environ={"MLK_PORT": raw})
            self.assertGreaterEqual(port, local_setup.DEFAULT_PORT, raw)
            if raw.strip():
                self.assertIn("nav derīgs ports", warning, raw)

    def test_a_busy_port_is_replaced_with_the_next_free_one(self):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            busy = blocker.getsockname()[1]
            if busy < local_setup.MIN_PORT:
                self.skipTest("sistēma piešķīra privileģētu portu")
            port, warning = local_setup.choose_port(preferred=busy, environ={})
            self.assertNotEqual(port, busy)
            self.assertIn(f"Ports {busy} ir aizņemts", warning)


def free_port_above_1024():
    for _ in range(50):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port >= local_setup.MIN_PORT:
            return port
    raise RuntimeError("nav piemērota porta testam")


class TestStartDoesNotNeedTheInternetForRepeatedLaunches(unittest.TestCase):
    def start(self, run, **kwargs):
        said = []
        code = local_setup.start(say=said.append, run=run, port=free_port_above_1024(), headless=True, **kwargs)
        return code, said

    def test_repeated_launch_installs_nothing_and_touches_no_network(self):
        run = FakeRun([7])                                       # Streamlit atgriež 7
        with mock.patch.object(local_setup, "unsatisfied", return_value=[]), \
             mock.patch.object(socket.socket, "connect", side_effect=AssertionError("tīkla savienojums")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("tīkla savienojums")):
            code, said = self.start(run)
        self.assertEqual(code, 7)
        self.assertEqual(len(run.calls), 1)                      # TIKAI Streamlit; pip netiek izsaukts
        self.assertEqual(run.commands[0][:5], [sys.executable, "-m", "streamlit", "run", "app.py"])
        self.assertFalse(any("pip" in part for command in run.commands for part in command))
        self.assertIn("Atkarības jau ir instalētas: internets nav vajadzīgs.", said)
        self.assertFalse(any("instalēju" in line.lower() and "internets" in line and "nav" not in line for line in said))

    def test_streamlit_is_launched_with_a_list_loopback_and_no_telemetry(self):
        run = FakeRun()
        with mock.patch.object(local_setup, "unsatisfied", return_value=[]):
            self.start(run)
        command, kwargs = run.calls[0]
        self.assertIsInstance(command, list)
        self.assertEqual(command[command.index("--server.address") + 1], "127.0.0.1")
        self.assertEqual(command[command.index("--browser.gatherUsageStats") + 1], "false")
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["cwd"], local_setup.ROOT)
        self.assertEqual(kwargs["env"]["STREAMLIT_BROWSER_GATHER_USAGE_STATS"], "false")

    def test_missing_dependencies_are_installed_once_and_then_the_app_starts(self):
        run = FakeRun()
        with mock.patch.object(local_setup, "unsatisfied", side_effect=[["streamlit"], []]):
            code, said = self.start(run)
        self.assertEqual(code, 0)
        self.assertEqual(run.commands[0], local_setup.build_install_command())
        self.assertEqual(run.commands[1][:5], [sys.executable, "-m", "streamlit", "run", "app.py"])
        self.assertEqual(len(run.calls), 2)
        self.assertTrue(any("vajadzīgs internets" in line for line in said))

    def test_explicit_update_installs_even_when_everything_is_satisfied(self):
        run = FakeRun()
        with mock.patch.object(local_setup, "unsatisfied", return_value=[]):
            code, said = self.start(run, update=True)
        self.assertEqual(code, 0)
        self.assertEqual(run.commands[0], local_setup.build_install_command())
        self.assertEqual(len(run.calls), 2)
        self.assertTrue(any("atjauninu" in line for line in said))

    def test_failed_install_stops_with_an_internet_hint_and_does_not_launch(self):
        run = FakeRun([1])
        with mock.patch.object(local_setup, "unsatisfied", return_value=["streamlit"]):
            code, said = self.start(run)
        self.assertEqual(code, 1)
        self.assertEqual(len(run.calls), 1)
        self.assertEqual(run.commands[0], local_setup.build_install_command())
        self.assertTrue(any("interneta savienojumu" in line for line in said))

    def test_install_that_does_not_fix_the_requirements_stops(self):
        run = FakeRun()
        with mock.patch.object(local_setup, "unsatisfied", return_value=["streamlit"]):
            code, said = self.start(run)
        self.assertEqual(code, 1)
        self.assertEqual(len(run.calls), 1)

    def test_old_python_is_refused_before_anything_runs(self):
        run = FakeRun()
        with mock.patch.object(local_setup.sys, "version_info", (3, 10, 0, "final", 0)):
            code, said = self.start(run)
        self.assertEqual((code, run.calls), (1, []))
        self.assertTrue(any("3.11" in line for line in said))

    def test_ctrl_c_is_a_normal_stop(self):
        def interrupted(command, **kwargs):
            raise KeyboardInterrupt
        with mock.patch.object(local_setup, "unsatisfied", return_value=[]):
            code, _ = self.start(interrupted)
        self.assertEqual(code, 0)

    def test_hostile_port_variable_never_reaches_the_command(self):
        run = FakeRun()
        said = []
        with mock.patch.object(local_setup, "unsatisfied", return_value=[]):
            local_setup.start(say=said.append, run=run, headless=True, environ={"MLK_PORT": "8600 & calc"})
        command = run.commands[0]
        self.assertTrue(command[command.index("--server.port") + 1].isdigit())
        self.assertNotIn("calc", " ".join(command))
        self.assertTrue(any("nav derīgs ports" in line for line in said))


if __name__ == "__main__":
    unittest.main()
