"""Lokālās palaišanas palīgs (Issue #8): atkarību pārbaude, instalēšana un Streamlit palaišana.

Izsauc `start_mlk_windows.bat` ar FIKSĒTU komandu:  python tools\\local_setup.py start [--update] [--no-browser]

- Atkarības tiek instalētas TIKAI pirmajā reizē, pēc izvēlēta `--update` vai ja `requirements.txt` prasības vairs
  neapmierina instalētās versijas. Parastai atkārtotai palaišanai internets NAV vajadzīgs.
- Streamlit klausās TIKAI `127.0.0.1`, telemetrija izslēgta; netiek izmantots ne ārējs API, ne tunelēšana.
- NEIZMANTO shell: visas ārējās komandas ir argumentu saraksti (`subprocess.run(list)`); lietotāja ievade nekad
  netiek ievietota komandrindā. Tikai standarta bibliotēka (jāstrādā pirms atkarību instalēšanas).
"""
import argparse
import importlib.metadata
import os
import pathlib
import signal
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
MIN_PYTHON = (3, 11)             # Streamlit 1.67: Requires-Python >=3.11
DEFAULT_PORT = 8501
PORT_ATTEMPTS = 20
MIN_PORT, MAX_PORT = 1024, 65535


def _safe_console():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")      # Windows konsole: nekrītam uz nekodējamām rakstzīmēm
            except Exception:
                pass


# --- atkarību pārbaude (bez interneta) ---------------------------------------------------------------
def unsatisfied(requirements_path=REQUIREMENTS):
    """Pakotņu nosaukumi, kuras trūkst vai neatbilst `requirements.txt` (tikai nosaukumi, nekādu ceļu)."""
    try:
        from packaging.requirements import Requirement
    except ImportError:
        return ["packaging"]                     # vide vēl nav sagatavota → jāinstalē
    missing = []
    for raw in pathlib.Path(requirements_path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        requirement = Requirement(line)
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(requirement.name)
            continue
        if not requirement.specifier.contains(installed, prereleases=True):
            missing.append(requirement.name)
    return missing


# --- komandas kā argumentu saraksti (nekad shell virkne) ----------------------------------------------
def build_install_command():
    return [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"]


def build_streamlit_command(port, headless=False):
    return [sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.address", "127.0.0.1", "--server.port", str(int(port)),
            "--server.headless", "true" if headless else "false",
            "--browser.gatherUsageStats", "false"]


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(preferred=None, environ=None):
    """(ports, brīdinājums). Vides mainīgais MLK_PORT tiek VALIDĒTS (tikai cipari, 1024–65535); aizņemtu portu
    nomaina uz nākamo brīvo."""
    environ = os.environ if environ is None else environ
    warning = None
    raw = str(preferred if preferred is not None else environ.get("MLK_PORT", "")).strip()
    port = DEFAULT_PORT
    if raw:
        if raw.isascii() and raw.isdigit() and MIN_PORT <= int(raw) <= MAX_PORT:
            port = int(raw)
        else:
            warning = f"MLK_PORT nav derīgs ports ({MIN_PORT}–{MAX_PORT}); izmantoju {DEFAULT_PORT}."
    for candidate in range(port, min(port + PORT_ATTEMPTS, MAX_PORT + 1)):
        if port_is_free(candidate):
            if candidate != port:
                warning = (warning + " " if warning else "") + f"Ports {port} ir aizņemts; izmantoju {candidate}."
            return candidate, warning
    raise RuntimeError("Nav atrasts brīvs ports.")


# --- palaišana ----------------------------------------------------------------------------------------------
def start(update=False, port=None, headless=False, say=print, run=subprocess.run, environ=None):
    """Pārbauda/instalē atkarības un palaiž lietotni. `run` ir injicējams testiem."""
    environ = os.environ if environ is None else environ
    if sys.version_info < MIN_PYTHON:
        say(f"KĻŪDA: nepieciešams Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} vai jaunāks.")
        return 1
    missing = [] if update else unsatisfied()
    if update or missing:
        say("Instalēju/atjauninu atkarības no requirements.txt." if update else
            "Atkarības nav instalētas vai neatbilst requirements.txt: instalēju (šim solim vajadzīgs internets).")
        say("Pēc instalēšanas parastai palaišanai internets nav vajadzīgs.")
        if run(build_install_command(), cwd=ROOT).returncode != 0:
            say("KĻŪDA: neizdevās instalēt atkarības. Pārbaudiet interneta savienojumu (vajadzīgs tikai instalēšanai) "
                "un mēģiniet vēlreiz.")
            return 1
        if unsatisfied():
            say("KĻŪDA: pēc instalēšanas atkarības joprojām neatbilst requirements.txt.")
            return 1
    else:
        say("Atkarības jau ir instalētas: internets nav vajadzīgs.")
    try:
        chosen, warning = choose_port(port, environ)
    except RuntimeError as error:
        say(f"KĻŪDA: {error}")
        return 1
    if warning:
        say(warning)
    say(f"Palaižu lietotni. Adrese datora pārlūkā: http://127.0.0.1:{chosen}")
    say("Lai apturētu, aizveriet šo logu vai nospiediet Ctrl+C.")
    child_env = {**environ, "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false"}
    try:
        return run(build_streamlit_command(chosen, headless), cwd=ROOT, env=child_env).returncode
    except KeyboardInterrupt:
        return 0


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt


@contextmanager
def _sigterm_as_interrupt():
    """SIGTERM (piem., aizverot logu/apturot procesu) kļūst par pārtraukumu: `subprocess.run` tad nogalina arī
    Streamlit bērnprocesu, nevis atstāj to dzīvu uz 127.0.0.1."""
    previous = None
    if threading.current_thread() is threading.main_thread():
        try:
            previous = signal.signal(signal.SIGTERM, _raise_interrupt)
        except (ValueError, OSError):
            previous = None
    try:
        yield
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def main(argv=None):
    _safe_console()
    parser = argparse.ArgumentParser(prog="tools/local_setup.py", description="Lokālās palaišanas palīgs.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="pārbaudīt, vai atkarības atbilst requirements.txt (bez interneta)")
    p = sub.add_parser("start", help="pārbaudīt/instalēt atkarības un palaist lietotni uz 127.0.0.1")
    p.add_argument("--update", action="store_true", help="skaidri izvēlēta atkarību instalēšana/atjaunināšana (vajadzīgs internets)")
    p.add_argument("--no-browser", action="store_true", help="neatvērt pārlūku (headless)")
    p.add_argument("--port", help="ports (pēc noklusējuma 8501 vai MLK_PORT)")
    args = parser.parse_args(argv)
    if args.command == "check":
        missing = unsatisfied()
        print("Atkarības atbilst requirements.txt." if not missing else
              "Atkarības nav sagatavotas vai neatbilst (" + ", ".join(missing) + ").")
        return 0 if not missing else 1
    with _sigterm_as_interrupt():
        return start(update=args.update, port=args.port, headless=args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
