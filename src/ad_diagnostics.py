"""AD rasējumu LOKĀLĀ diagnostika (Issue #8).

Izmanto esošo analīzi (`src/ad_vector.py`) un NEveido jaunu atpazīšanu. Moduļa uzdevumi:
1. apskatīt PDF pa lapām (teksta klasifikācija, vektoru skaits) un analizēt arī ar roku norādītu lapu,
   ja automātiskais klasifikators to neatrod;
2. salīdzināt NOLASĪTOS kandidātus ar lietotāja KONTROLIZMĒRIEM (atsevišķi atzīmēti);
3. sagatavot brīvprātīgu SANITIZĒTU kopsavilkumu ar stingri definētu atļauto lauku sarakstu.

Drošība: modulis neizmanto tīklu un neko nesūta, neraksta failus un nesatur PDF saturu, ko varētu
paturēt. Sanitizētais kopsavilkums tiek būvēts TIKAI no strukturētiem skaitļiem un fiksētiem kodiem, nekad
no brīva teksta (faila nosaukuma, ceļa, PDF teksta, kļūdu ziņojumiem, koordinātām, izmēriem, hash,
metadatiem), un pirms atgriešanas tiek pārbaudīts ar `validate_summary`.
"""
import datetime
import json
import re

import pymupdf

from src.ad_plan import classify_page
from src.ad_vector import CONSISTENT, RECOGNISED, REFUSED, UNCLEAR, analyze_page, page_vector_summary

SCHEMA_VERSION = 1
MAX_PAGES = 300
MIN_CONTROL_MM, MAX_CONTROL_MM = 100, 100_000
COUNT_MAX = 1_000_000

INPUT_STATUSES = ("ok", "invalid_pdf", "encrypted", "too_many_pages", "unreadable")
SELECTION_MODES = ("manual", "auto", "all", "none")
TEXT_CLASSES = ("floor", "roof", "list", "other")
PAGE_STATUSES = ("ok", "no_vector_geometry", "error")
STATUS_KEYS = {CONSISTENT: "consistent", RECOGNISED: "recognised", UNCLEAR: "unclear", REFUSED: "refused"}
REASON_CODES = (
    "NO_VECTOR_GEOMETRY", "NO_CANDIDATES", "PAGE_ERROR", "SHAPE_NOT_RECTANGLE", "SCALE_CONFLICT",
    "SCALE_MULTIPLE", "SCALE_UNDETERMINED", "SCALE_NOT_DECLARED", "DIMENSION_MISSING",
    "DIMENSION_WEAK_LINK", "DIMENSION_CONFLICT", "NESTED_CONTOURS", "ROLE_CONFLICT",
    "ADJACENT_BOUNDARY_NOT_MARKED", "NO_MODULE_LABEL")
EXCLUDED_KINDS = ("room", "terrace", "nested", "unmeasured", "page_frame")
VECTOR_KINDS = ("contour_rectangle", "contour_polygon", "segment_horizontal", "segment_vertical",
                "segment_diagonal", "curve")
COMPARISON_CATEGORIES = ("match", "small", "medium", "large", "no_candidate")
# novirzes kategorijas (lielākā relatīvā novirze no L vai W): sakrīt ≤ 0,5 %, neliela ≤ 2 %, vidēja ≤ 10 %
DEVIATION_LIMITS = (("match", 0.005), ("small", 0.02), ("medium", 0.10))

# --- sanitizētā kopsavilkuma ATĻAUTO LAUKU SARAKSTS (vienīgā patiesība) -------------------------------
SUMMARY_FIELDS = {
    "schema_version": ("const", SCHEMA_VERSION, "kopsavilkuma formāta versija"),
    "input_status": ("enum", INPUT_STATUSES, "ievades statusa kods (ok / invalid_pdf / encrypted / too_many_pages / unreadable)"),
    "pages_selection": ("enum", SELECTION_MODES, "lapu izvēles veids: manual / auto / all / none"),
    "pages_total": ("count", None, "PDF lapu skaits"),
    "pages_analyzed": ("count", None, "analizēto lapu skaits"),
    "page_text_class_counts": ("counts", TEXT_CLASSES, "lapu skaits pēc teksta klasifikācijas: floor / roof / list / other"),
    "page_status_counts": ("counts", PAGE_STATUSES, "analizēto lapu statusu kodu skaits: ok / no_vector_geometry / error"),
    "vector_kind_counts": ("counts", VECTOR_KINDS, "vektoru veidu skaits analizētajās lapās (tikai skaitļi, bez koordinātām)"),
    "dimension_annotations_total": ("count", None, "atrasto izmēru norāžu skaits (bez vērtībām)"),
    "candidates_total": ("count", None, "kontūru kandidātu skaits"),
    "status_counts": ("counts", tuple(STATUS_KEYS.values()), "kandidātu statusu kodu skaits: consistent / recognised / unclear / refused"),
    "reason_code_counts": ("counts", REASON_CODES, "neveiksmes/neskaidrības iemeslu kodu skaits (fiksēts kodu saraksts)"),
    "excluded_counts": ("counts", EXCLUDED_KINDS, "izslēgto kontūru skaits pēc veida (telpa, terase, ligzdota, bez izmēriem, lapas rāmis)"),
    "recognised_modules": ("count", None, "atpazīto moduļu skaits (kandidāti ar L un W)"),
    "controlled_modules": ("count", None, "lietotāja kontrolēto moduļu skaits"),
    "control_comparison": ("counts", COMPARISON_CATEGORIES,
                           "kontrolizmēru noviržu kategoriju skaits: match / small / medium / large / no_candidate (bez faktiskajiem izmēriem)"),
}
NEVER_INCLUDED = (
    "faila nosaukums un ceļš", "klientu un projektu nosaukumi, identifikatori", "PDF teksts un marķējumu teksti",
    "attēli un priekšskatījumi", "koordinātas un lapu izmēri", "faktiskie izmēri (L, W, norāžu vērtības, kontrolizmēri)",
    "PDF hash un metadati", "kļūdu ziņojumu teksts")


class DiagnosticsError(ValueError):
    """Lietotāja ievades kļūda (ziņojums ir drošs rādīšanai lokāli)."""


# --- ievades parsēšana ---------------------------------------------------------------------------------
def parse_page_list(text):
    """"3", "3,5" vai "3-6,9" → kārtots lapu numuru saraksts (1-based)."""
    pages = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d{1,4})(?:\s*-\s*(\d{1,4}))?", part)
        if not match:
            raise DiagnosticsError(f"Nederīgs lapu numurs: '{part}'. Piemērs: 3 vai 3,5 vai 3-6.")
        first, last = int(match.group(1)), int(match.group(2) or match.group(1))
        if first < 1 or last < first or last - first > MAX_PAGES:
            raise DiagnosticsError(f"Nederīgs lapu diapazons: '{part}'.")
        pages.update(range(first, last + 1))
    if not pages:
        raise DiagnosticsError("Nav norādīts neviens lapas numurs.")
    return sorted(pages)


def parse_control(text):
    """"12000x4000" → (L, W) milimetros, L ≥ W. Lietotāja KONTROLIZMĒRS, nevis nolasīts no PDF."""
    match = re.fullmatch(r"\s*(\d{3,6})\s*[x×*]\s*(\d{3,6})\s*", str(text), flags=re.I)
    if not match:
        raise DiagnosticsError(f"Nederīgs kontrolizmērs: '{text}'. Piemērs: 12000x4000 (mm).")
    a, b = int(match.group(1)), int(match.group(2))
    if not (MIN_CONTROL_MM <= min(a, b) and max(a, b) <= MAX_CONTROL_MM):
        raise DiagnosticsError(f"Kontrolizmērs ārpus {MIN_CONTROL_MM}–{MAX_CONTROL_MM} mm: '{text}'.")
    return max(a, b), min(a, b)


# --- PDF apskats un analīze -----------------------------------------------------------------------------
def _open_pdf(data: bytes):
    if not data.startswith(b"%PDF"):
        return None, "invalid_pdf"
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return None, "unreadable"
    if doc.needs_pass:
        doc.close()
        return None, "encrypted"
    if len(doc) > MAX_PAGES:
        doc.close()
        return None, "too_many_pages"
    return doc, "ok"


def _describe_page(doc, number):
    page = doc[number - 1]
    entry = {"page": number, "text_class": "other", "text_class_reason": "", "text_chars": 0,
             "size_pt": [round(page.mediabox.width, 1), round(page.mediabox.height, 1)],
             "rotation": page.rotation, "vectors": None, "describe_error": None}
    try:
        text = page.get_text("text", sort=True)
        kind, reason = classify_page(text)
        entry.update(text_class=kind, text_class_reason=reason, text_chars=len(text))
        entry["vectors"] = page_vector_summary(page)
    except Exception as error:      # vietēji parādāms; sanitizētajā kopsavilkumā nonāk tikai kods
        entry["describe_error"] = f"{type(error).__name__}: {error}"
    return entry


def _failed_analysis(number, error, summary=None):
    return {"page": number, "status": "error", "candidates": [], "excluded": [], "dimensions": [],
            "scale": None, "vector_summary": summary, "rotation": None, "mediabox_pt": None,
            "notes": [f"Analīzes kļūda lapā {number}: {type(error).__name__}: {error}"]}


def run_diagnostics(data: bytes, *, pages=None, all_pages=False, controls=(), file_name=None):
    """Pilns LOKĀLAIS pārskats (satur PDF saturu: nekopīgot). `pages` = ar roku norādītas lapas (1-based)."""
    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "input": {"status": "ok", "file_name": file_name, "size_bytes": len(data), "pages_total": 0},
        "pages": [], "selection": {"mode": "none", "pages": [], "invalid_pages": [], "notes": []},
        "analyses": {}, "controls": [{"length_mm": l, "width_mm": w} for l, w in controls],
    }
    doc, status = _open_pdf(data)
    report["input"]["status"] = status
    if doc is None:
        report["comparison"] = compare_controls([], controls)
        return report
    with doc:
        total = len(doc)
        report["input"]["pages_total"] = total
        report["pages"] = [_describe_page(doc, n) for n in range(1, total + 1)]
        by_number = {p["page"]: p for p in report["pages"]}
        selection = report["selection"]
        if pages:
            selection["mode"] = "manual"
            selection["pages"] = [n for n in pages if 1 <= n <= total]
            selection["invalid_pages"] = [n for n in pages if not 1 <= n <= total]
            for n in selection["pages"]:
                if by_number[n]["text_class"] in ("roof", "list"):
                    selection["notes"].append(
                        f"Lapa {n} automātiski klasificēta kā '{by_number[n]['text_class']}' "
                        f"({by_number[n]['text_class_reason']}); analīze tiek veikta pēc jūsu norādes.")
        elif all_pages:
            selection["mode"] = "all"
            selection["pages"] = list(range(1, total + 1))
        else:
            floor = [p["page"] for p in report["pages"] if p["text_class"] == "floor"]
            selection["mode"] = "auto" if floor else "none"
            selection["pages"] = floor
            if not floor:
                selection["notes"].append(
                    "Automātiskais klasifikators neatrada grīdas plāna lapu. Norādiet lapu pats: "
                    "--page N (lapas numuru redzat PDF skatītājā un šī pārskata lapu tabulā).")
        for n in selection["pages"]:
            try:
                report["analyses"][n] = analyze_page(doc[n - 1], n)
            except Exception as error:
                report["analyses"][n] = _failed_analysis(n, error, by_number[n]["vectors"])
    candidates = [(n, c) for n, a in sorted(report["analyses"].items()) for c in a["candidates"] if c["transferable"]]
    report["comparison"] = compare_controls(candidates, controls)
    return report


# --- kontrolizmēru salīdzinājums -----------------------------------------------------------------------
def _category(deviation):
    for name, limit in DEVIATION_LIMITS:
        if deviation <= limit:
            return name
    return "large"


def compare_controls(candidates, controls):
    """Katram kontrolizmēram (lietotāja ievadīts) atrod tuvāko NOLASĪTO kandidātu (1:1, neizdomājot).

    `candidates`: [(lapa, kandidāts)]; `controls`: [(L, W)] mm. Neatbilstību nemaina un neslēpj.
    """
    pairs = []
    for ci, (l, w) in enumerate(controls):
        for ki, (page, cand) in enumerate(candidates):
            dl, dw = abs(cand["length_mm"] - l) / l, abs(cand["width_mm"] - w) / w
            pairs.append((max(dl, dw), ci, ki))
    pairs.sort()
    used_controls, used_candidates, assigned = set(), set(), {}
    for deviation, ci, ki in pairs:
        if ci in used_controls or ki in used_candidates:
            continue
        used_controls.add(ci)
        used_candidates.add(ki)
        assigned[ci] = (ki, deviation)
    entries, counts = [], {name: 0 for name in COMPARISON_CATEGORIES}
    for ci, (l, w) in enumerate(controls):
        entry = {"control_index": ci + 1, "control": {"length_mm": l, "width_mm": w}, "candidate_id": None,
                 "page": None, "candidate": None, "deviation_mm": None, "deviation_pct": None,
                 "category": "no_candidate"}
        if ci in assigned:
            ki, deviation = assigned[ci]
            page, cand = candidates[ki]
            entry.update(
                candidate_id=cand["id"], page=page,
                candidate={"length_mm": cand["length_mm"], "width_mm": cand["width_mm"], "status": cand["status"]},
                deviation_mm={"length": cand["length_mm"] - l, "width": cand["width_mm"] - w},
                deviation_pct=round(deviation * 100, 2), category=_category(deviation))
        counts[entry["category"]] += 1
        entries.append(entry)
    unmatched = [cand["id"] for ki, (page, cand) in enumerate(candidates) if ki not in used_candidates]
    return {"entries": entries, "counts": counts, "candidates_without_control": unmatched}


# --- sanitizētais kopsavilkums -------------------------------------------------------------------------
def _zero(keys):
    return {key: 0 for key in keys}


def build_sanitized_summary(report):
    """Kopsavilkums TIKAI no strukturētiem skaitļiem un fiksētiem kodiem; pirms atgriešanas pārbaudīts."""
    analyses = list(report["analyses"].values())
    summary = {
        "schema_version": SCHEMA_VERSION,
        "input_status": report["input"]["status"],
        "pages_selection": report["selection"]["mode"],
        "pages_total": report["input"]["pages_total"],
        "pages_analyzed": len(analyses),
        "page_text_class_counts": _zero(TEXT_CLASSES),
        "page_status_counts": _zero(PAGE_STATUSES),
        "vector_kind_counts": _zero(VECTOR_KINDS),
        "dimension_annotations_total": 0,
        "candidates_total": 0,
        "status_counts": _zero(STATUS_KEYS.values()),
        "reason_code_counts": _zero(REASON_CODES),
        "excluded_counts": _zero(EXCLUDED_KINDS),
        "recognised_modules": 0,
        "controlled_modules": len(report["controls"]),
        "control_comparison": dict(report["comparison"]["counts"]),
    }
    for page in report["pages"]:
        if page["text_class"] in summary["page_text_class_counts"]:
            summary["page_text_class_counts"][page["text_class"]] += 1
    for analysis in analyses:
        status = analysis.get("status")
        if status in summary["page_status_counts"]:
            summary["page_status_counts"][status] += 1
        for kind in VECTOR_KINDS:
            summary["vector_kind_counts"][kind] += int((analysis.get("vector_summary") or {}).get(kind, 0))
        summary["dimension_annotations_total"] += len(analysis.get("dimensions", []))
        for item in analysis.get("excluded", []):
            if item.get("kind") in summary["excluded_counts"]:
                summary["excluded_counts"][item["kind"]] += 1
        page_code = {"no_vector_geometry": "NO_VECTOR_GEOMETRY", "error": "PAGE_ERROR"}.get(status)
        if status == "ok" and not analysis["candidates"]:
            page_code = "NO_CANDIDATES"
        if page_code:
            summary["reason_code_counts"][page_code] += 1
        for cand in analysis.get("candidates", []):
            summary["candidates_total"] += 1
            key = STATUS_KEYS.get(cand.get("status"))
            if key:
                summary["status_counts"][key] += 1
            if cand.get("transferable"):
                summary["recognised_modules"] += 1
            for code in cand.get("reason_codes", []):
                if code in summary["reason_code_counts"]:
                    summary["reason_code_counts"][code] += 1
    validate_summary(summary)
    return summary


def _is_count(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= COUNT_MAX


def validate_summary(summary):
    """Pārbauda, ka kopsavilkumā ir TIEŠI atļautie lauki ar atļautām vērtībām. Citādi ValueError.

    Kļūdas ziņojums nekad neietver vērtības, tikai lauku nosaukumus.
    """
    if not isinstance(summary, dict):
        raise ValueError("Kopsavilkumam jābūt vārdnīcai.")
    extra, missing = set(summary) - set(SUMMARY_FIELDS), set(SUMMARY_FIELDS) - set(summary)
    if extra or missing:
        # liekos lauku nosaukumus NEatkārtojam (tie varētu saturēt sensitīvu tekstu); trūkstošie nāk no atļautā saraksta
        raise ValueError(f"Kopsavilkuma lauki neatbilst atļautajam sarakstam (liekie lauki: {len(extra)}, "
                         f"trūkstošie: {sorted(missing)}).")
    for name, (kind, arg, _description) in SUMMARY_FIELDS.items():
        value = summary[name]
        if kind == "const":
            ok = isinstance(value, int) and not isinstance(value, bool) and value == arg
        elif kind == "enum":
            ok = isinstance(value, str) and value in arg
        elif kind == "count":
            ok = _is_count(value)
        else:   # counts
            ok = isinstance(value, dict) and set(value) == set(arg) and all(_is_count(v) for v in value.values())
        if not ok:
            raise ValueError(f"Lauka '{name}' vērtība nav atļautā formātā.")
    return True


def summary_json(summary):
    validate_summary(summary)
    return json.dumps(summary, ensure_ascii=True, indent=2)


def describe_allowed_fields():
    lines = ["ATĻAUTIE sanitizētā kopsavilkuma lauki (nekas cits netiek iekļauts):"]
    for name, (_kind, _arg, description) in SUMMARY_FIELDS.items():
        lines.append(f"  - {name}: {description}")
    lines.append("")
    lines.append("NEKAD netiek iekļauts:")
    lines.extend(f"  - {item}" for item in NEVER_INCLUDED)
    return "\n".join(lines)
