"""Aplikācijas čaula (Issue #18): režīmu nosaukumi, noklusējuma sākumskats un izvietotās versijas identifikators.

- Noklusējuma (pirmais) režīms ir **Pilnas ēkas AD tāme**; vecais AD grīdas rāmja režīms un PD režīms ir saglabāti ar skaidriem nosaukumiem.
- Versijas identifikators: kodā definēta **izlaiduma versija** (`RELEASE_VERSION`, jāatjaunina katram izlaidumam) + **īsais commit SHA**, ja tas ir pieejams
  (vides mainīgais vai `git`). Streamlit izvietojumā commit var nebūt pieejams — tad redzama tikai izlaiduma versija un tas tiek skaidri norādīts.
  Ekrānuzņēmumā tas ļauj atšķirt vecu izvietojumu no jaunā. Nekas sensitīvs (ceļi, lietotāji) netiek rādīts.
"""
import os
import pathlib
import re
import subprocess

RELEASE_VERSION = "2026.11.26-biblioteka-1"       # JĀATJAUNINA katram izlaidumam (Issue #18, #20)
ROOT = pathlib.Path(__file__).resolve().parent.parent

MODE_BUILDING = "Pilnas ēkas AD tāme"
MODE_OLD_AD = "Vecais AD: tikai grīdas rāmis"
MODE_PD = "PD: līmsiju specifikācija"
MODES = [MODE_BUILDING, MODE_OLD_AD, MODE_PD]            # pirmais = noklusējums

COMMIT_ENV_VARS = ("MLK_COMMIT", "GIT_COMMIT", "COMMIT_SHA", "SOURCE_VERSION", "RENDER_GIT_COMMIT", "GITHUB_SHA")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_cache = {}


def _valid(value):
    value = str(value or "").strip().lower()
    return value[:7] if _SHA_RE.match(value) else None


def commit_sha(environ=None, runner=None, use_cache=True):
    """Īsais (7 simboli) commit SHA vai None. Secība: vides mainīgie → `git rev-parse` (bez shell, ar taimautu) → None."""
    if use_cache and environ is None and runner is None and "sha" in _cache:
        return _cache["sha"]
    env = os.environ if environ is None else environ
    sha = next((s for s in (_valid(env.get(name)) for name in COMMIT_ENV_VARS) if s), None)
    if sha is None:
        run = runner or subprocess.run
        try:
            result = run(["git", "-C", str(ROOT), "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, timeout=3)
            if getattr(result, "returncode", 1) == 0:
                sha = _valid(result.stdout)
        except Exception:                                   # git nav pieejams / nav repozitorijs (piem., ZIP izvietojums)
            sha = None
    if use_cache and environ is None and runner is None:
        _cache["sha"] = sha
    return sha


def version_label(environ=None, runner=None):
    sha = commit_sha(environ, runner, use_cache=environ is None and runner is None)
    return f"Versija {RELEASE_VERSION} · commit {sha}" if sha else f"Versija {RELEASE_VERSION} · commit nav pieejams"
