"""Projekta saglabāšana/atjaunošana JSON failā (Issue #14): lokāla lejupielāde/augšupielāde, bez servera persistences.

- Fails satur shēmas versiju, projekta datus (ievaddati, katalogs, receptes, darbaspēks, cenas) un datu kontrolsummu.
  PDF saturs netiek iekļauts; nekas netiek sūtīts automātiski.
- Imports VALIDĒ struktūru un tipus un NEuzticas faila gatavības/apstiprinājuma statusam: atbildīgās personas pārbaude vienmēr tiek
  atcelta; ja kontrolsumma neatbilst (fails mainīts ārpus programmas), tiek atceltas arī visas lietotāja apstiprinājuma atzīmes.
- Izmanto tikai `json` (nekad pickle/eval).
"""
import hashlib
import json
import math
from dataclasses import dataclass, field

from src.building_estimate import LINE_LISTS, MAX_MODULES, empty_project, ensure_ids

SCHEMA_VERSION = 1
APP_ID = "mlk-tametajs-pilna-eka"
MAX_BYTES = 5 * 1024 * 1024
MAX_LIST = 2000
MAX_TEXT = 2000
MAX_DEPTH = 8
LOCAL_DATA_REMINDER = ("Reālus MLK datus (cenas, normas, projektus) izmanto TIKAI lokālajā versijā (127.0.0.1 savā datorā). Publiskajā "
                       "Streamlit lietotnē drīkst izmantot tikai sintētiskus DEMO datus.")


@dataclass
class ImportedProject:
    project: object = None
    notices: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def _checksum(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def export_project(project: dict) -> bytes:
    doc = {"schema_version": SCHEMA_VERSION, "app": APP_ID, "data": project, "checksum": _checksum(project)}
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")


def _walk(value, path, errors, depth=0):
    if depth > MAX_DEPTH:
        errors.append(f"{path}: pārāk dziļa struktūra")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str) or len(k) > 120:
                errors.append(f"{path}: nederīga atslēga")
                return
            _walk(v, f"{path}.{k}", errors, depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_LIST:
            errors.append(f"{path}: pārāk daudz ierakstu (maks. {MAX_LIST})")
            return
        for i, v in enumerate(value):
            _walk(v, f"{path}[{i}]", errors, depth + 1)
    elif isinstance(value, str):
        if len(value) > MAX_TEXT:
            errors.append(f"{path}: teksts pārāk garš")
    elif isinstance(value, bool) or value is None or isinstance(value, int):
        pass
    elif isinstance(value, float):
        if not math.isfinite(value):
            errors.append(f"{path}: nav galīgs skaitlis")
    else:
        errors.append(f"{path}: neatbalstīts tips {type(value).__name__}")


def _type_ok(default, value):
    if default is None:
        return value is None or isinstance(value, (int, float, str)) and not isinstance(value, bool)
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, type(default))


def import_project(raw: bytes) -> ImportedProject:
    out = ImportedProject()
    if len(raw) > MAX_BYTES:
        out.errors.append("fails ir lielāks par 5 MB")
        return out
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        out.errors.append(f"nav derīgs JSON: {str(error)[:80]}")
        return out
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), dict):
        out.errors.append("nepareiza faila struktūra (trūkst «data»)")
        return out
    version = doc.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        out.errors.append("trūkst shēmas versijas")
        return out
    if version > SCHEMA_VERSION:
        out.errors.append(f"fails ir jaunākas shēmas versijas ({version}) nekā šī programma atbalsta ({SCHEMA_VERSION})")
        return out
    if version < 1:
        out.errors.append("nederīga shēmas versija")
        return out
    if doc.get("app") != APP_ID:
        out.errors.append("fails nav šīs programmas projekta fails")
        return out
    data = doc["data"]
    _walk(data, "data", out.errors)
    if out.errors:
        return out
    base = empty_project(str(data.get("name") or "Importēts projekts")[:80], data.get("construction") if isinstance(data.get("construction"), str) else "clt")
    project = {}
    dropped = []
    for key, value in data.items():
        if key not in base:
            dropped.append(key)
            continue
        if not _type_ok(base[key], value) and not (key in ("floor_net_m2", "ceiling_m2") and value is None):
            out.errors.append(f"«{key}»: nepareizs tips")
            continue
        project[key] = value
    for key, default in base.items():
        project.setdefault(key, default)
        if isinstance(default, dict):
            if not isinstance(project[key], dict):
                out.errors.append(f"«{key}»: nepareizs tips")
                continue
            for k2, v2 in default.items():
                project[key].setdefault(k2, v2)
    for key in LINE_LISTS + ("modules", "catalog", "excluded"):
        if not isinstance(project.get(key), list):
            out.errors.append(f"«{key}»: jābūt sarakstam")
        elif key != "excluded" and not all(isinstance(x, dict) for x in project[key]):
            out.errors.append(f"«{key}»: katram ierakstam jābūt objektam")
    if not isinstance(project["labour"].get("operations"), list) or not all(isinstance(x, dict) for x in project["labour"]["operations"]):
        out.errors.append("«labour.operations»: jābūt objektu sarakstam")
    if len(project.get("modules", [])) > MAX_MODULES:
        out.errors.append(f"pārāk daudz moduļu (maks. {MAX_MODULES})")
    if out.errors:
        return out
    if dropped:
        out.notices.append("Ignorēti nezināmi lauki: " + ", ".join(sorted(map(str, dropped)))[:200])
    trusted = doc.get("checksum") == _checksum(data)
    ensure_ids(project)
    if not trusted:
        out.notices.append("Kontrolsumma neatbilst (fails mainīts ārpus programmas): VISAS apstiprinājuma atzīmes (moduļi, CLT biezums, "
                           "slīpums, rindas) ir atceltas — apstiprini no jauna.")
        _drop_approvals(project)
    # atbildīgās personas pārbaude NETIEK pārņemta nekad
    if (project.get("review") or {}).get("confirmed"):
        out.notices.append("Atbildīgās personas pārbaude netiek pārņemta no faila: apstiprini vēlreiz pēc importa.")
    project["review"] = {"reviewer": str((project.get("review") or {}).get("reviewer") or "")[:60], "confirmed": False, "fp": None}
    out.project = project
    return out


def _drop_approvals(project):
    for m in project.get("modules", []):
        m["confirmed"] = False
    project["module_fp"] = {}
    for key in ("layers", "recipes", "manual"):
        for line in project.get(key, []):
            line["approved"] = False
    for op in project["labour"].get("operations", []):
        op["approved"] = False
    for panel in (project.get("clt") or {}).values():
        if isinstance(panel, dict):
            panel["thickness_confirmed"] = False
    if isinstance(project.get("roof"), dict):
        project["roof"]["slope_confirmed"] = False
