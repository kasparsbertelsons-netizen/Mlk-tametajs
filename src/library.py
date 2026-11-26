"""Lokāla, atkārtoti lietojama materiālu recepšu, cenu un normstundu bibliotēka (Issue #20).

Bibliotēka ir ATSEVIŠĶS JSON fails (nav projekts un nav faktiskā kontroltāme). Imports: parsēšana + validācija → priekšskatījums → piemērošana
projektam. Piemērošana NEveido jaunu aprēķina ceļu: bibliotēkas ieraksti tiek pārvērsti par esošajām projekta rindām (`recipes`, `labour.operations`,
`catalog`), tāpēc `building_estimate.estimate()` aprēķina tos kā jebkuras citas receptes (draiveri, rezerve, cenas no kataloga, stundas).

Principi:
- NEIZDOMĀ: nezināma mērvienība → ieraksts noraidīts; trūkstoša/nederīga cena paliek tukša; trūkstoša norma paliek «nav ievadīta».
- Trīs atšķirīgi veidi: «ģeometriska formula» (draiveris × norma), «vēsturisks koeficients» (NEKAD netiek automātiski apstiprināts vai pārvērsts par
  validētu normu; pēc noklusējuma netiek piemērots) un «komplekta budžets» (AD komplekti ar standarta noklusējumu un izvēles līmeņiem).
- Nedublē: ieraksts ar to pašu `lib_code` tiek ATJAUNINĀTS (nevis pievienots otrreiz); jau esoša lietotāja recepte ar to pašu grupu/nosaukumu/artikulu un
  konstrukciju slāņi (vai tipu receptes) tiek AIZSARGĀTI no dubultošanas (ieraksts izlaists ar paskaidrojumu).
- Komplekti: viens aktīvs līmenis katram komplektam; pozīcijas var AIZSTĀT (cits līmenis/artikuls) vai IZSLĒGT, var PAPILDINĀT ar papildu pozīcijām; standarta
  un izvēlētais aprīkojums nekad netiek skaitīts abi. Option List nav obligāts; tā faila parsētājs netiek veidots (formāts nav zināms).
- Dokumentācija: `docs/LIBRARY.md`. Bibliotēkas fails nesatur reālus uzņēmuma datus (paraugs ir sintētisks).
"""
import copy
import datetime
import hashlib
import json
import math
from dataclasses import dataclass, field

from src.building_estimate import DRIVERS, GROUPS, LABOUR_UNITS, LAYER_GROUPS, MANUAL_GROUPS, COST_SCOPES, new_id, norm_name, num
from src.catalog_import import apply_catalog

LIB_APP_ID = "mlk-tametajs-biblioteka"
SCHEMA_VERSION = 1
MAX_BYTES = 5 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_TEXT = 200
KNOWN_UNITS = ("m²", "m³", "m", "gab.", "kompl.", "kg", "l", "iep.", "rit.", "pāri")

ST_APPROVED, ST_UNAPPROVED, ST_HISTORICAL = "apstiprināts", "neapstiprināts", "vēsturisks"
STATUSES = (ST_APPROVED, ST_UNAPPROVED, ST_HISTORICAL)
K_FORMULA, K_HISTORICAL, K_KIT = "ģeometriska formula", "vēsturisks koeficients", "komplekta budžets"
KINDS = (K_FORMULA, K_HISTORICAL, K_KIT)
ROW_KIND_KIT = "kit"
OPENING_TYPES = ("facade_win", "roof_win", "door")          # pozīcija, kuru tāmē jau dod ievadītas atveres (nedublē)


@dataclass
class LibraryImport:
    library: object = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class ApplyReport:
    added: list = field(default_factory=list)          # (kods, nosaukums)
    updated: list = field(default_factory=list)
    unchanged: list = field(default_factory=list)
    skipped: list = field(default_factory=list)        # (kods, nosaukums, iemesls)
    prices_applied: list = field(default_factory=list)
    prices_not_applied: list = field(default_factory=list)   # (artikuls, iemesls)
    warnings: list = field(default_factory=list)

    @property
    def n_changes(self):
        return len(self.added) + len(self.updated)


# --- palīgfunkcijas ----------------------------------------------------------------------------------------------
def empty_library(name="Jauna bibliotēka"):
    return {"meta": {"name": name, "version": "1", "description": "", "synthetic": False},
            "catalog": [], "recipes": [], "labour": [], "kits": []}


def _checksum(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def export_library(library: dict) -> bytes:
    doc = {"schema_version": SCHEMA_VERSION, "app": LIB_APP_ID, "data": library, "checksum": _checksum(library)}
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")


def _text(value, limit=MAX_TEXT):
    return " ".join(str(value or "").split())[:limit]


def _date(value, where, errors):
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        errors.append(f"{where}: nederīgs datums «{text}» (formāts GGGG-MM-DD)")
        return None


def _number(value, where, errors, positive=False):
    try:
        out = num(value)
    except ValueError as error:
        errors.append(f"{where}: {error}")
        return None
    if out is not None and positive and out <= 0:
        errors.append(f"{where}: vērtībai jābūt > 0")
        return None
    return out


def _status_kind(entry, where, out):
    status = _text(entry.get("status")) or ST_UNAPPROVED
    kind = _text(entry.get("kind")) or K_FORMULA
    if status not in STATUSES:
        out.errors.append(f"{where}: nezināms statuss «{status}» (atļauts: {', '.join(STATUSES)})")
        status = ST_UNAPPROVED
    if kind not in KINDS:
        out.errors.append(f"{where}: nezināms veids «{kind}» (atļauts: {', '.join(KINDS)})")
        kind = K_FORMULA
    if kind == K_HISTORICAL and status == ST_APPROVED:
        out.warnings.append(f"{where}: vēsturisks koeficients nevar būt «apstiprināts» (netiek pārvērsts par validētu normu) — saglabāts kā «vēsturisks».")
        status = ST_HISTORICAL
    if kind == K_HISTORICAL:
        status = ST_HISTORICAL
    return status, kind


def parse_library(raw: bytes) -> LibraryImport:
    """Validē bibliotēkas JSON. Kļūdainie ieraksti tiek noraidīti ar paskaidrojumu (nekas netiek izdomāts); pārējie tiek saglabāti."""
    out = LibraryImport()
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
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        out.errors.append("trūkst vai nederīga shēmas versija")
        return out
    if version > SCHEMA_VERSION:
        out.errors.append(f"fails ir jaunākas shēmas versijas ({version}) nekā šī programma atbalsta ({SCHEMA_VERSION})")
        return out
    if doc.get("app") != LIB_APP_ID:
        out.errors.append("fails nav šīs programmas bibliotēkas fails")
        return out
    data = doc["data"]
    trusted = doc.get("checksum") == _checksum(data)
    if not trusted:
        out.warnings.append("Kontrolsumma neatbilst (fails mainīts ārpus programmas): visi ieraksti tiek ielasīti kā «neapstiprināts».")
    meta_in = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    lib = empty_library(_text(meta_in.get("name"), 80) or "Bibliotēka")
    lib["meta"].update({"version": _text(meta_in.get("version"), 20) or "1", "description": _text(meta_in.get("description"), 400),
                        "synthetic": bool(meta_in.get("synthetic"))})
    for key in ("catalog", "recipes", "labour", "kits"):
        if not isinstance(data.get(key, []), list) or not all(isinstance(x, dict) for x in data.get(key, [])):
            out.errors.append(f"«{key}»: jābūt objektu sarakstam")
            return out
        if len(data.get(key, [])) > MAX_ENTRIES:
            out.errors.append(f"«{key}»: pārāk daudz ierakstu (maks. {MAX_ENTRIES})")
            return out
    _parse_catalog(data.get("catalog", []), lib, out)
    _parse_recipes(data.get("recipes", []), lib, out)
    _parse_labour(data.get("labour", []), lib, out)
    _parse_kits(data.get("kits", []), lib, out)
    if not trusted:
        for lst in (lib["recipes"], lib["labour"]):
            for e in lst:
                if e["status"] == ST_APPROVED:
                    e["status"] = ST_UNAPPROVED
    out.library = lib
    return out


def _parse_catalog(entries, lib, out):
    seen = set()
    for i, e in enumerate(entries, 1):
        where = f"katalogs, rinda {i}"
        errors_before = len(out.errors)
        article = _text(e.get("article"), 60)
        if not article:
            out.errors.append(f"{where}: trūkst artikula")
            continue
        where = f"katalogs «{article}»"
        if article in seen:
            out.errors.append(f"{where}: dublikāts artikuls — rinda izlaista")
            continue
        unit = _text(e.get("unit"), 12)
        if unit not in KNOWN_UNITS:
            out.errors.append(f"{where}: nezināma mērvienība «{unit}» (atļauts: {', '.join(KNOWN_UNITS)}) — mērvienība netiek minēta")
        price = _number(e.get("unit_price"), f"{where}: cena", out.errors)
        pack = _number(e.get("pack_size"), f"{where}: iepakojums", out.errors, positive=True)
        vf = _date(e.get("price_valid_from"), f"{where}: cena spēkā no", out.errors)
        vt = _date(e.get("price_valid_to"), f"{where}: cena spēkā līdz", out.errors)
        if vf and vt and vt < vf:
            out.errors.append(f"{where}: cenas derīguma beigu datums ir pirms sākuma")
        if len(out.errors) > errors_before:
            continue
        psource = _text(e.get("price_source"), 120)
        if price is not None and not psource:
            out.warnings.append(f"{where}: cenai nav norādīts avots (cenas avots ieteicams).")
        seen.add(article)
        lib["catalog"].append({"article": article, "name": _text(e.get("name")), "spec": _text(e.get("spec")), "unit": unit, "unit_price": price,
                               "pack_size": pack, "supplier": _text(e.get("supplier"), 80), "price_valid_from": vf, "price_valid_to": vt,
                               "price_source": psource})


def _parse_recipes(entries, lib, out):
    seen = set()
    articles = {c["article"] for c in lib["catalog"]}
    for i, e in enumerate(entries, 1):
        code = _text(e.get("code"), 60)
        where = f"receptes «{code or i}»"
        n0 = len(out.errors)
        if not code:
            out.errors.append(f"receptes rinda {i}: trūkst koda")
            continue
        if code in seen:
            out.errors.append(f"{where}: dublikāts kods — rinda izlaista")
            continue
        group = e.get("group")
        if group not in MANUAL_GROUPS:
            out.errors.append(f"{where}: nezināma grupa «{_text(group, 40)}»")
        name, article = _text(e.get("name")), _text(e.get("article"), 60)
        if not name and not article:
            out.errors.append(f"{where}: jānorāda nosaukums vai artikuls")
        unit = _text(e.get("unit"), 12)
        if unit.lower() in LABOUR_UNITS:
            out.errors.append(f"{where}: mērvienība ir darba stundas — norma jāliek sadaļā «labour» (citādi darbs tiktu ieskaitīts divreiz)")
        elif unit not in KNOWN_UNITS:
            out.errors.append(f"{where}: nezināma mērvienība «{unit}» (atļauts: {', '.join(KNOWN_UNITS)}) — mērvienība netiek minēta")
        driver = _text(e.get("driver")) or "direct"
        if driver not in DRIVERS:
            out.errors.append(f"{where}: nezināms draiveris «{driver}»")
        norm = _number(e.get("norm"), f"{where}: norma", out.errors)
        qty = _number(e.get("qty"), f"{where}: daudzums", out.errors)
        waste = _number(e.get("waste_pct"), f"{where}: rezerve", out.errors)
        pack = _number(e.get("pack_size"), f"{where}: iepakojums", out.errors, positive=True)
        scope = e.get("cost_scope") if e.get("cost_scope") in COST_SCOPES else "materiāli"
        status, kind = _status_kind(e, where, out)
        if len(out.errors) > n0:
            continue
        if article and article not in articles:
            out.warnings.append(f"{where}: artikuls «{article}» nav bibliotēkas katalogā (cena jāievada projektā).")
        if driver != "direct" and norm is None:
            out.warnings.append(f"{where}: patēriņa norma nav norādīta — rinda paliks «nav ievadīta» (norma netiek izdomāta).")
        if not _text(e.get("source")):
            out.warnings.append(f"{where}: avots nav norādīts.")
        seen.add(code)
        lib["recipes"].append({"code": code, "group": group, "name": name, "article": article or None, "spec": _text(e.get("spec")), "unit": unit,
                               "driver": driver, "norm": norm, "qty": qty, "waste_pct": waste, "pack_size": pack, "status": status, "kind": kind,
                               "source": _text(e.get("source"), 120), "assumption": _text(e.get("assumption"), 200),
                               "detail": e.get("detail") if e.get("detail") in ("detalizēts", "norma", "komplekts") else "norma" if driver != "direct" else "",
                               "cost_scope": scope})


def _parse_labour(entries, lib, out):
    seen = set()
    for i, e in enumerate(entries, 1):
        code = _text(e.get("code"), 60)
        where = f"normstundas «{code or i}»"
        n0 = len(out.errors)
        if not code:
            out.errors.append(f"normstundu rinda {i}: trūkst koda")
            continue
        if code in seen:
            out.errors.append(f"{where}: dublikāts kods — rinda izlaista")
            continue
        group = e.get("group")
        if group not in GROUPS:
            out.errors.append(f"{where}: nezināma grupa «{_text(group, 40)}»")
        name = _text(e.get("name"))
        if not name:
            out.errors.append(f"{where}: trūkst operācijas nosaukuma")
        driver = _text(e.get("driver")) or "direct"
        if driver not in DRIVERS:
            out.errors.append(f"{where}: nezināms draiveris «{driver}»")
        unit = _text(e.get("unit"), 12)
        if unit and unit not in KNOWN_UNITS:
            out.errors.append(f"{where}: nezināma mērvienība «{unit}»")
        norm_h = _number(e.get("norm_h"), f"{where}: normstundas uz vienību", out.errors)
        status, kind = _status_kind(e, where, out)
        if len(out.errors) > n0:
            continue
        if norm_h is None:
            out.warnings.append(f"{where}: normstundas nav norādītas — operācija paliks «nav ievadīta».")
        seen.add(code)
        lib["labour"].append({"code": code, "group": group, "name": name, "stage": _text(e.get("stage"), 60), "driver": driver, "unit": unit,
                              "norm_h": norm_h, "status": status, "kind": kind, "source": _text(e.get("source"), 120)})


def _parse_kits(entries, lib, out):
    seen = set()
    articles = {c["article"] for c in lib["catalog"]}
    for i, e in enumerate(entries, 1):
        code = _text(e.get("code"), 60)
        where = f"komplekts «{code or i}»"
        n0 = len(out.errors)
        if not code:
            out.errors.append(f"komplekta rinda {i}: trūkst koda")
            continue
        if code in seen:
            out.errors.append(f"{where}: dublikāts kods — komplekts izlaists")
            continue
        group = e.get("group")
        if group not in MANUAL_GROUPS:
            out.errors.append(f"{where}: nezināma grupa «{_text(group, 40)}»")
        name = _text(e.get("name"))
        if not name:
            out.errors.append(f"{where}: trūkst nosaukuma")
        levels = e.get("levels")
        if not (isinstance(levels, list) and levels and all(isinstance(x, str) and x.strip() for x in levels) and len(set(levels)) == len(levels)):
            out.errors.append(f"{where}: «levels» jābūt neatkārtojamu līmeņu sarakstam")
            levels = []
        default = _text(e.get("default_level"))
        if levels and default not in levels:
            out.errors.append(f"{where}: noklusējuma līmenis «{default}» nav līmeņu sarakstā")
        positions_in = e.get("positions")
        if not (isinstance(positions_in, list) and positions_in and all(isinstance(x, dict) for x in positions_in)):
            out.errors.append(f"{where}: jānorāda vismaz viena pozīcija («positions»)")
            positions_in = []
        positions, pseen = [], set()
        for j, p in enumerate(positions_in, 1):
            pcode, pwhere = _text(p.get("code"), 40), f"{where}, pozīcija {j}"
            if not pcode or pcode in pseen or "/" in pcode:
                out.errors.append(f"{pwhere}: kods trūkst, atkārtojas vai satur «/»")
                continue
            pseen.add(pcode)
            unit = _text(p.get("unit"), 12)
            if unit not in KNOWN_UNITS:
                out.errors.append(f"{pwhere}: nezināma mērvienība «{unit}»")
                continue
            driver = _text(p.get("driver")) or "direct"
            if driver not in DRIVERS:
                out.errors.append(f"{pwhere}: nezināms draiveris «{driver}»")
                continue
            qty = _number(p.get("qty"), f"{pwhere}: daudzums", out.errors, positive=True)
            norm = _number(p.get("norm"), f"{pwhere}: norma", out.errors)
            if driver == "direct" and qty is None:
                out.errors.append(f"{pwhere}: tiešai pozīcijai jānorāda daudzums")
                continue
            options = p.get("options") if isinstance(p.get("options"), dict) else {}
            clean = {}
            for lvl, art in options.items():
                art = _text(art, 60)
                if lvl not in levels:
                    out.errors.append(f"{pwhere}: līmenis «{lvl}» nav komplekta līmeņu sarakstā")
                elif art:
                    clean[lvl] = art
                    if art not in articles:
                        out.warnings.append(f"{pwhere}: artikuls «{art}» nav bibliotēkas katalogā (cena jāievada projektā).")
            opening = _text(p.get("opening"), 20) or None
            if opening and opening not in OPENING_TYPES:
                out.errors.append(f"{pwhere}: nezināms «opening» tips «{opening}» (atļauts: {', '.join(OPENING_TYPES)})")
                continue
            positions.append({"code": pcode, "name": _text(p.get("name")), "unit": unit, "qty": qty, "driver": driver, "norm": norm, "options": clean,
                              "opening": opening})
        scope = e.get("cost_scope") if e.get("cost_scope") in COST_SCOPES else "materiāli"
        covers = [norm_name(t) for t in (e.get("covers") or []) if isinstance(t, str) and t.strip()]
        if len(out.errors) > n0:
            continue
        assumption = _text(e.get("assumption"), 200)
        if not assumption:
            out.warnings.append(f"{where}: AD komplektam jānorāda pieņēmums («assumption»).")
        seen.add(code)
        lib["kits"].append({"code": code, "group": group, "name": name, "levels": levels, "default_level": default, "positions": positions,
                            "assumption": assumption, "cost_scope": scope, "covers": covers})


# --- piemērošana projektam -------------------------------------------------------------------------------------------
def _effective(entry, today):
    """(cena vai None, iemesls kāpēc nav piemērota). Cena bez derīguma datuma uzskatāma par spēkā esošu."""
    price = entry.get("unit_price")
    if price is None:
        return None, "cena nav norādīta (nav izdomāta)"
    vf, vt = entry.get("price_valid_from"), entry.get("price_valid_to")
    if vf and vf > today:
        return None, f"cena spēkā tikai no {vf}"
    if vt and vt < today:
        return None, f"cena beigusies {vt}"
    return price, ""


def _label(library):
    meta = library["meta"]
    return f"{meta['name']} v{meta['version']}"


def _lines(project, key):
    if key == "ops":
        return project.setdefault("labour", {}).setdefault("operations", [])
    return project.setdefault(key, [])


def _structural_conflict(project, group, name, article):
    """Vai grupā jau ir konstrukcijas slānis / tipa recepte ar šo nosaukumu vai artikulu (slāņi/tipi tiek skaitīti atsevišķi)."""
    if group not in LAYER_GROUPS:
        return None
    for key, label in (("layers", "konstrukcijas slānis"), ("type_recipes", "konstrukciju tipa recepte")):
        for ln in project.get(key) or []:
            if ln.get("enabled") is False or ln.get("group", group if key == "type_recipes" else None) not in (group, None):
                continue
            if (article and str(ln.get("article") or "").strip() == article) or (name and norm_name(ln.get("name")) == norm_name(name)):
                return f"jau ir {label} «{ln.get('name')}»"
    return None


def _recipe_line(entry, library, lib_kit=None):
    status = entry["status"]
    hist = status == ST_HISTORICAL
    source = f"Bibliotēka {_label(library)}"
    if hist:
        source += " — VĒSTURISKS koeficients (nav validēts)"
    elif entry.get("source"):
        source += f": {entry['source']}"
    return {"group": entry["group"], "article": entry.get("article"), "name": entry["name"], "spec": entry.get("spec") or "", "unit": entry["unit"],
            "driver": entry.get("driver") or "direct", "norm": entry.get("norm"), "qty": entry.get("qty"), "waste_pct": entry.get("waste_pct"),
            "pack_size": entry.get("pack_size"), "module": "", "stage": "", "approved": status == ST_APPROVED, "source": source[:120], "enabled": True,
            "detail": entry.get("detail") or "", "assumption": entry.get("assumption") or "", "cost_scope": entry.get("cost_scope") or "materiāli",
            "lib_code": entry["code"], "lib_status": status, "lib_kind": entry.get("kind") or K_FORMULA, **({"lib_kit": lib_kit} if lib_kit else {})}


_MANAGED = ("group", "article", "name", "spec", "unit", "driver", "norm", "qty", "waste_pct", "pack_size", "approved", "source", "detail", "assumption",
            "cost_scope", "lib_status", "lib_kind", "lib_kit")


def _upsert(lines, new, report, label):
    """Ieraksts ar to pašu lib_code tiek atjaunināts vietā (id saglabāts → cenas un izvēles nesabojājas); citādi pievienots."""
    for ln in lines:
        if ln.get("lib_code") == new["lib_code"]:
            if all(ln.get(k) == new.get(k) for k in _MANAGED):
                report.unchanged.append((new["lib_code"], label))
            else:
                for k in _MANAGED:
                    if k in new:
                        ln[k] = new[k]
                    else:
                        ln.pop(k, None)
                ln["enabled"] = True
                report.updated.append((new["lib_code"], label))
            return ln
    new["id"] = new.get("id") or new_id()
    lines.append(new)
    report.added.append((new["lib_code"], label))
    return new


def _has_user_twin(lines, group, name, article):
    for ln in lines:
        if ln.get("lib_code") or ln.get("enabled") is False or ln.get("group") != group:
            continue
        if (article and str(ln.get("article") or "").strip() == article) or (name and norm_name(ln.get("name")) == norm_name(name)):
            return ln
    return None


def apply_library(project, library, *, as_of=None, include_historical=False, include_kits=True, kit_choices=None, include_labour=True):
    """Piemēro bibliotēku projektam (maina `project`!). Priekšskatījumam izmanto `preview_library`. Atgriež ApplyReport."""
    report = ApplyReport()
    today = as_of if isinstance(as_of, str) else (as_of or datetime.date.today()).isoformat()
    label = _label(library)
    # 1) katalogs (cenas tikai ar derīgu periodu un avotu; tukša/nederīga cena neizdzēš esošu)
    used_units = {}
    for ln in list(project.get("recipes") or []) + list(project.get("manual") or []):
        if ln.get("article") and ln.get("unit") and not ln.get("lib_code"):
            used_units.setdefault(str(ln["article"]).strip(), set()).add(str(ln["unit"]).strip())
    rows = []
    for c in library["catalog"]:
        price, why = _effective(c, today)
        if price is None:
            report.prices_not_applied.append((c["article"], why))
        rows.append({"article": c["article"], "name": c["name"], "spec": c["spec"], "unit": c["unit"], "unit_price": price,
                     "pack_size": c["pack_size"], "supplier": c["supplier"]})
    skipped = apply_catalog(project, rows, used_units)
    for art, unit, units in skipped:
        report.skipped.append((art, art, f"katalogs: mērvienība «{unit}» neatbilst projekta rindām ({', '.join(units)}) — nav piemērots"))
    by_art = {str(c.get("article")).strip(): c for c in project.get("catalog") or []}
    skipped_arts = {a for a, _u, _x in skipped}
    for c in library["catalog"]:
        target = by_art.get(c["article"])
        if target is None or c["article"] in skipped_arts:
            continue
        price, _why = _effective(c, today)
        target["source"] = f"Bibliotēka {label}"
        if price is not None:
            target.update({"price_valid_from": c["price_valid_from"], "price_valid_to": c["price_valid_to"], "price_source": c["price_source"]})
            report.prices_applied.append(c["article"])
    # 2) receptes
    recipes = _lines(project, "recipes")
    for e in library["recipes"]:
        name = e["name"] or e["article"]
        if e["status"] == ST_HISTORICAL and not include_historical:
            report.skipped.append((e["code"], name, "vēsturisks koeficients — netiek piemērots automātiski (atsevišķi nav validēts)"))
            continue
        existing = next((ln for ln in recipes if ln.get("lib_code") == e["code"]), None)
        if existing is None:
            twin = _has_user_twin(recipes, e["group"], e["name"], e["article"])
            if twin is not None:
                report.skipped.append((e["code"], name, f"projektā jau ir šāda recepte «{twin.get('name')}» — nedublē"))
                continue
        conflict = _structural_conflict(project, e["group"], e["name"], e["article"])
        if conflict:
            report.skipped.append((e["code"], name, f"dubultošana: {conflict}"))
            continue
        _upsert(recipes, _recipe_line(e, library), report, name)
    # 3) normstundas
    if include_labour:
        ops = _lines(project, "ops")
        for e in library["labour"]:
            if e["status"] == ST_HISTORICAL and not include_historical:
                report.skipped.append((e["code"], e["name"], "vēsturisks koeficients — netiek piemērots automātiski"))
                continue
            existing = next((o for o in ops if o.get("lib_code") == e["code"]), None)
            if existing is None and any(not o.get("lib_code") and o.get("enabled") is not False and o.get("group") == e["group"]
                                        and norm_name(o.get("name")) == norm_name(e["name"]) and norm_name(o.get("stage")) == norm_name(e["stage"])
                                        for o in ops):
                report.skipped.append((e["code"], e["name"], "projektā jau ir šāda darba operācija — nedublē"))
                continue
            src = f"Bibliotēka {label}" + (" — VĒSTURISKS (nav validēts)" if e["status"] == ST_HISTORICAL else (f": {e['source']}" if e["source"] else ""))
            new = {"group": e["group"], "name": e["name"], "stage": e["stage"], "module": "", "driver": e["driver"], "qty": None, "unit": e["unit"],
                   "norm_h": e["norm_h"], "hours": None, "rate_eur_h": None, "approved": e["status"] == ST_APPROVED, "source": src[:120], "enabled": True,
                   "lib_code": e["code"], "lib_status": e["status"], "lib_kind": e["kind"]}
            if existing is not None:
                keep_id = existing.get("id")
                if all(existing.get(k) == new[k] for k in ("group", "name", "stage", "driver", "unit", "norm_h", "approved", "source", "lib_status")):
                    report.unchanged.append((e["code"], e["name"]))
                else:
                    existing.update(new)
                    existing["id"] = keep_id
                    report.updated.append((e["code"], e["name"]))
            else:
                new["id"] = new_id()
                ops.append(new)
                report.added.append((e["code"], e["name"]))
    # 4) komplekti
    project["lib"] = {"name": library["meta"]["name"], "version": library["meta"]["version"], "kits": dict((project.get("lib") or {}).get("kits") or {})}
    if kit_choices is not None:
        project["lib"]["kits"] = copy.deepcopy(kit_choices)
    if include_kits:
        apply_kits(project, library, report=report)
    return report


def _has_openings(project, kind):
    for o in project.get("openings") or []:
        if o.get("enabled") is False:
            continue
        wall, is_window = o.get("wall") or "Ārsiena", (o.get("kind") or "Logs") == "Logs"
        if (kind == "facade_win" and is_window and wall == "Ārsiena") or (kind == "roof_win" and is_window and wall == "Jumts") or (kind == "door" and not is_window):
            return True
    return False


def kit_selection(project, code):
    sel = ((project.get("lib") or {}).get("kits") or {}).get(code) or {}
    return {"enabled": sel.get("enabled", True) is not False, "level": sel.get("level"),
            "pos_levels": dict(sel.get("pos_levels") or {}), "pos_articles": dict(sel.get("pos_articles") or {}),
            "skip": list(sel.get("skip") or []), "add": [a for a in sel.get("add") or [] if isinstance(a, dict)]}


def kit_total(project, library, code):
    """Komplekta cena (EUR bez PVN) pie pašreizējās izvēles, aprēķināta ar parasto tāmes aprēķinu; None, ja kādai pozīcijai nav daudzuma vai cenas."""
    from src.building_estimate import estimate
    if not any(k["code"] == code for k in library["kits"]):
        return None
    tmp = copy.deepcopy(project)
    apply_kits(tmp, library, only=code)
    ids = {f"recipe:{ln['id']}" for ln in tmp.get("recipes") or [] if ln.get("lib_kit") == code}
    rows = [r for r in estimate(tmp).rows if r.row_id in ids]
    if not rows or len(rows) < len(ids) or any(r.cost is None for r in rows):
        return None
    return sum(r.cost for r in rows)


def apply_kits(project, library, *, report=None, only=None):
    """(Pār)veido komplektu rindas projektā pēc `project['lib']['kits']` izvēlēm. Katram komplektam — viens aktīvs līmenis; rindas ar to pašu
    `lib_code` tiek atjauninātas vietā, vairs nevajadzīgas (aizstātas/izslēgtas/noņemtas) tiek dzēstas — standarta un izvēlētais netiek dubultoti."""
    report = report or ApplyReport()
    recipes = _lines(project, "recipes")
    label = _label(library)
    catalog_arts = {str(c.get("article")).strip(): c for c in project.get("catalog") or []}
    for kit in library["kits"]:
        if only and kit["code"] != only:
            continue
        sel = kit_selection(project, kit["code"])
        wanted = {}
        reason = None
        if not sel["enabled"]:
            reason = "komplekts izslēgts"
        else:
            level = sel["level"] if sel["level"] in kit["levels"] else kit["default_level"]
            if sel["level"] and sel["level"] not in kit["levels"]:
                report.warnings.append(f"Komplekts «{kit['name']}»: līmenis «{sel['level']}» nav zināms — izmantots noklusējuma «{level}».")
            twin = next((ln for ln in recipes if not ln.get("lib_code") and ln.get("enabled") is not False and ln.get("group") == kit["group"]
                         and any(tok and tok in norm_name(ln.get("name")) for tok in kit["covers"])), None)
            for ln in project.get("manual") or []:
                if twin is None and ln.get("group") == kit["group"] and any(tok and tok in norm_name(ln.get("material")) for tok in kit["covers"]):
                    twin = {"name": ln.get("material")}
            if twin is not None:
                reason = f"dubultošana: grupā jau ir lietotāja rinda «{twin.get('name')}», kas sedz šo komplektu — noņem to vai izslēdz komplektu"
            else:
                used_articles = {}
                for pos in kit["positions"]:
                    if pos["code"] in sel["skip"]:
                        continue
                    if pos.get("opening") and _has_openings(project, pos["opening"]):
                        report.skipped.append((f"{kit['code']}/{pos['code']}", pos["name"],
                                               "dubultošana: šīs atveres jau ir tāmē kā rindas grupā «Logi un durvis» — komplekta pozīcija netiek skaitīta otrreiz"))
                        continue
                    plevel = sel["pos_levels"].get(pos["code"], level)
                    if plevel not in kit["levels"]:
                        report.warnings.append(f"Komplekts «{kit['name']}», {pos['name']}: līmenis «{plevel}» nav zināms — izmantots «{level}».")
                        plevel = level
                    article = sel["pos_articles"].get(pos["code"]) or pos["options"].get(plevel)
                    if article is None and plevel != kit["default_level"]:
                        article = pos["options"].get(kit["default_level"])
                        report.warnings.append(f"Komplekts «{kit['name']}», {pos['name']}: līmenim «{plevel}» nav artikula — izmantots noklusējuma līmeņa artikuls.")
                    if article and article in catalog_arts and catalog_arts[article].get("unit") not in (None, "", pos["unit"]):
                        report.warnings.append(f"Komplekts «{kit['name']}», {pos['name']}: artikula «{article}» mērvienība neatbilst pozīcijai ({pos['unit']}) — cena netiks piemērota.")
                    if article and article in used_articles:
                        report.skipped.append((f"{kit['code']}/{pos['code']}", pos["name"], f"dubultošana: artikuls «{article}» jau komplektā ({used_articles[article]})"))
                        continue
                    if article:
                        used_articles[article] = pos["name"]
                    wanted[f"{kit['code']}/{pos['code']}"] = {
                        "group": kit["group"], "article": article, "name": f"{kit['name']}: {pos['name']}", "spec": f"līmenis: {plevel}", "unit": pos["unit"],
                        "driver": pos["driver"], "norm": pos["norm"], "qty": pos["qty"], "waste_pct": 0.0, "pack_size": None, "approved": False,
                        "source": f"Bibliotēka {label}: komplekts {kit['name']} ({level})"[:120], "detail": "komplekts",
                        "assumption": f"{kit['assumption']} [komplektācija: {level}]".strip(), "cost_scope": kit["cost_scope"],
                        "lib_status": ST_UNAPPROVED, "lib_kind": K_KIT, "lib_kit": kit["code"]}
                for n, add in enumerate(sel["add"], 1):
                    aname, aunit, aqty = _text(add.get("name")), _text(add.get("unit"), 12), None
                    try:
                        aqty = num(add.get("qty"))
                    except ValueError:
                        aqty = None
                    aart = _text(add.get("article"), 60) or None
                    code = f"{kit['code']}/+{n}"
                    if not aname or aunit not in KNOWN_UNITS or not aqty or aqty <= 0:
                        report.skipped.append((code, aname or code, "papildu pozīcijai jānorāda nosaukums, zināma mērvienība un daudzums > 0"))
                        continue
                    if aart and aart in used_articles:
                        report.skipped.append((code, aname, f"dubultošana: artikuls «{aart}» jau ir komplektā ({used_articles[aart]}) — izmanto aizstāšanu"))
                        continue
                    if aart:
                        used_articles[aart] = aname
                    wanted[code] = {"group": kit["group"], "article": aart, "name": f"{kit['name']}: {aname} (papildu)", "spec": "papildu pozīcija", "unit": aunit,
                                    "driver": "direct", "norm": None, "qty": aqty, "waste_pct": 0.0, "pack_size": None, "approved": False,
                                    "source": f"Bibliotēka {label}: papildinājums", "detail": "komplekts", "assumption": f"{kit['assumption']} [papildinājums]".strip(),
                                    "cost_scope": kit["cost_scope"], "lib_status": ST_UNAPPROVED, "lib_kind": K_KIT, "lib_kit": kit["code"]}
        if reason:
            report.skipped.append((kit["code"], kit["name"], reason))
        # noņem šī komplekta rindas, kuras vairs nav vajadzīgas
        recipes[:] = [ln for ln in recipes if ln.get("lib_kit") != kit["code"] or ln.get("lib_code") in wanted]
        for code, data in wanted.items():
            base = {"enabled": True, "module": "", "stage": "", "lib_code": code, **data}
            _upsert(recipes, base, report, data["name"])
    return report


def preview_library(project, library, **kw):
    """Priekšskatījums BEZ projekta izmaiņām: piemēro kopijai un atgriež to pašu pārskatu, ko dotu īstā piemērošana."""
    return apply_library(copy.deepcopy(project), library, **kw)


def library_summary(library):
    counts = {"katalogs": len(library["catalog"]), "receptes": len(library["recipes"]), "normstundas": len(library["labour"]), "komplekti": len(library["kits"])}
    by_status = {s: sum(1 for e in library["recipes"] + library["labour"] if e["status"] == s) for s in STATUSES}
    return counts, by_status


def library_fingerprint(library):
    return _checksum(library)[:12]


def new_library_from_dict(data):
    """Palīgs testiem/rīkiem: ģenerē derīgu bibliotēkas dokumentu no vārdnīcas (kontrolsummu uzliek export)."""
    return parse_library(export_library(data))
