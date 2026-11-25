"""AD PDF teksta analīze: grīdas plāna lapas un izmēru KANDIDĀTI (Issue #4).

Šis modulis NEnosaka moduļa L un W. Tas tikai parāda, kādi skaitļi ir redzami
grīdas plāna lapu tekstā, ar avota lapu. Teksta PDF nepierāda ģeometriju, tāpēc
lietotājs vienmēr apstiprina vai ievada L un W pirms aprēķina.

Netiek izmantots: jumta plāna skaitļi, titullapa / rasējumu saraksts, terases,
biežums kā izvēles pamatojums (skaitļi netiek ranžēti vai iepriekš izvēlēti).
Pilna vektoru ģeometrijas atpazīšana nav šī moduļa uzdevums.
"""
import re

FLOOR_RE = re.compile(r"\bFloor\s+plan\b", re.I)
ROOF_RE = re.compile(r"\bRoof\s+plan\b", re.I)
LIST_RE = re.compile(
    r"drawing\s+list|list\s+of\s+drawings|table\s+of\s+contents|sheet\s+index|cover\s+sheet|"
    r"title\s+page|zīmējumu\s+saraksts|rasējumu\s+saraksts|satura\s+rādītājs|titullapa",
    re.I)
TERRACE_RE = re.compile(r"\bteras\w*|\bterrace\w*|\bverand\w*", re.I)
# Atsevišķi 4–5 ciparu mm izmēri; bez decimāldaļām, reizinājumiem (1200x1500) un datumiem.
NUMBER_RE = re.compile(r"(?<![\d.,x×])\d{4,5}(?![\d.,x×])")
MIN_CANDIDATE_MM = 2000
MAX_CANDIDATE_MM = 20000
CONTEXT_CHARS = 80


def classify_page(text: str):
    """(kind, reason): 'floor' | 'roof' | 'list' | 'other'."""
    has_floor, has_roof = bool(FLOOR_RE.search(text)), bool(ROOF_RE.search(text))
    if not has_floor:
        if has_roof:
            return "roof", "Jumta plāns: skaitļi netiek izmantoti."
        return "other", ""
    if has_roof or LIST_RE.search(text):
        return "list", ("Titullapa vai rasējumu saraksts (grīdas plāns minēts kopā ar jumta plānu "
                        "vai saraksta atzīmi): skaitļi netiek izmantoti.")
    return "floor", ""


def extract_dimension_candidates(text: str):
    """(kandidāti, izslēgtie skaitļi) no vienas grīdas plāna lapas teksta."""
    found, excluded = {}, []
    for line in text.splitlines():
        numbers = [int(m.group()) for m in NUMBER_RE.finditer(line)]
        numbers = [n for n in numbers if MIN_CANDIDATE_MM <= n <= MAX_CANDIDATE_MM]
        if not numbers:
            continue
        context = " ".join(line.split())[:CONTEXT_CHARS]
        if TERRACE_RE.search(line):
            excluded.extend({"value_mm": n, "reason": "Terase", "context": context} for n in numbers)
            continue
        for n in numbers:
            entry = found.setdefault(n, {"value_mm": n, "count": 0, "context": context})
            entry["count"] += 1
    return sorted(found.values(), key=lambda item: item["value_mm"]), excluded


def scan_plan_pages(page_texts):
    """Klasificē lapas un izvelk kandidātus tikai no grīdas plāna lapām.

    Atgriež {"floor_pages": [...], "skipped_pages": [...]}; katra lapa ir dict ar
    "page", "kind", "reason", "candidates", "excluded_numbers".
    """
    floor_pages, skipped_pages = [], []
    for number, text in enumerate(page_texts, start=1):
        kind, reason = classify_page(text)
        page = {"page": number, "kind": kind, "reason": reason,
                "candidates": [], "excluded_numbers": []}
        if kind == "floor":
            page["candidates"], page["excluded_numbers"] = extract_dimension_candidates(text)
            floor_pages.append(page)
        elif kind in ("roof", "list"):
            skipped_pages.append(page)
    return {"floor_pages": floor_pages, "skipped_pages": skipped_pages}
