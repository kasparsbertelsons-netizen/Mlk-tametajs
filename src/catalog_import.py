"""Cenu/artikulu kataloga imports no XLSX/CSV (Issue #14). Tikai lokāli: fails tiek lasīts atmiņā, nekas netiek sūtīts un saglabāts.

Noteikumi:
- Artikuls vienmēr ir TEKSTS (sākuma nulles saglabājas, ja tās ir faila teksta šūnā/CSV; skaitliska XLSX šūna tiek atzīmēta ar brīdinājumu).
- Trūkstoša cena nav nulle (None). Cena ir EUR BEZ PVN par norādīto mērvienību; mērvienības netiek konvertētas.
- Šūnas ar formulām netiek izpildītas un netiek importētas (kļūda). Teksts nekad netiek interpretēts kā formula.
- Rindas ar kļūdām netiek importētas; priekšskatījums rāda kļūdas, un piemērošanai vajadzīgs lietotāja apstiprinājums (UI).
"""
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_TEXT = 200
FIELDS = ["article", "name", "spec", "unit", "unit_price", "pack_size", "supplier"]
HEADERS_LV = {"article": "Artikuls", "name": "Nosaukums", "spec": "Specifikācija", "unit": "Mērvienība",
              "unit_price": "Vienības cena EUR bez PVN", "pack_size": "Iepakojums", "supplier": "Piegādātājs"}
ALIASES = {
    "article": ("artikuls", "art", "artikula kods", "kods", "sku", "article"),
    "name": ("nosaukums", "materials", "materiala nosaukums", "apraksts", "name"),
    "spec": ("specifikacija", "spec", "specification"),
    "unit": ("mervieniba", "vieniba", "unit", "mervienibas"),
    "unit_price": ("vienibas cena eur bez pvn", "vienibas cena", "cena", "cena eur", "cena eur bez pvn", "cena bez pvn", "price", "unit price"),
    "pack_size": ("iepakojums", "iepakojuma izmers", "pack", "pack size"),
    "supplier": ("piegadatajs", "supplier"),
}
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _norm_header(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


@dataclass
class CatalogImport:
    rows: list = field(default_factory=list)          # derīgās rindas (dict ar FIELDS atslēgām)
    errors: list = field(default_factory=list)        # (faila rindas Nr. vai None, ziņojums) — šīs rindas NAV importētas
    warnings: list = field(default_factory=list)
    columns: dict = field(default_factory=dict)       # lauks → faila kolonnas nosaukums
    read_rows: int = 0
    fatal: bool = False                               # faila līmeņa kļūda (nederīgs fails/trūkst obligāto kolonnu)


def _clean_text(value, what, row_no, result, limit=MAX_TEXT):
    text = _CONTROL.sub("", str(value)).strip()
    if len(text) > limit:
        result.errors.append((row_no, f"{what}: teksts garāks par {limit} rakstzīmēm"))
        return None
    if text[:1] in ("=", "+", "-", "@"):
        result.warnings.append((row_no, f"{what}: teksts sākas ar formulas simbolu — tiks glabāts un eksportēts kā TEKSTS, nevis formula"))
    return text


def _parse_price(raw, row_no, result):
    if raw in (None, ""):
        return None, True
    if isinstance(raw, bool):
        result.errors.append((row_no, "cena: nederīga vērtība"))
        return None, False
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = str(raw).replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "")
        if not text:
            return None, True
        if "," in text and "." in text:
            text = text.replace(",", "")                 # 1,234.50
        else:
            text = text.replace(",", ".")
        try:
            value = float(text)
        except ValueError:
            result.errors.append((row_no, f"cena: nederīga vērtība «{str(raw)[:20]}»"))
            return None, False
    if value != value or value in (float("inf"), float("-inf")):
        result.errors.append((row_no, "cena: nav galīgs skaitlis"))
        return None, False
    if value < 0:
        result.errors.append((row_no, "cena: nedrīkst būt negatīva"))
        return None, False
    if value == 0:
        result.warnings.append((row_no, "cena ir 0 — pārbaudi; trūkstoša cena jāatstāj TUKŠA (tā nav nulle)"))
    return round(value, 6), True


def _read_csv(data):
    for enc in ("utf-8-sig", "cp1257", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = text.splitlines()[0] if text.strip() else ""
    delim = max((";", ",", "\t"), key=first.count)
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)], {}


def _read_xlsx(data):
    import openpyxl                                               # atkarība: requirements.txt
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=False, data_only=False)
    ws = wb["Katalogs"] if "Katalogs" in wb.sheetnames else wb.worksheets[0]
    if ws.max_row and ws.max_row > MAX_ROWS + 1:
        raise ValueError(f"fails satur vairāk nekā {MAX_ROWS} rindas")
    rows, kinds = [], {}
    for r_index, row in enumerate(ws.iter_rows(), 1):
        vals = []
        for c_index, cell in enumerate(row, 1):
            if cell.data_type == "f":
                kinds[(r_index, c_index)] = "formula"
                vals.append(None)
            else:
                vals.append(cell.value)
        rows.append(vals)
    return rows, kinds


def parse_catalog_file(filename, data: bytes) -> CatalogImport:
    result = CatalogImport()
    name = str(filename or "").lower()
    if len(data) > MAX_BYTES:
        result.errors.append((None, f"fails ir lielāks par {MAX_BYTES // (1024 * 1024)} MB"))
        result.fatal = True
        return result
    try:
        if name.endswith(".xlsx") or data[:2] == b"PK":
            table, kinds = _read_xlsx(data)
        elif name.endswith(".csv") or name.endswith(".txt"):
            table, kinds = _read_csv(data)
        else:
            result.errors.append((None, "neatbalstīts faila tips (jāpiegādā .xlsx vai .csv)"))
            result.fatal = True
            return result
    except Exception as error:                                     # bojāts/neatbalstīts fails
        result.errors.append((None, f"faila nolasīšana neizdevās ({type(error).__name__}): " + str(error)[:120]))
        result.fatal = True
        return result
    table = [r for r in table if any(str(v).strip() for v in r if v is not None)] if not kinds else table
    if not table:
        result.errors.append((None, "fails ir tukšs"))
        result.fatal = True
        return result
    header = table[0]
    mapping = {}
    for index, cell in enumerate(header):
        key = _norm_header(cell)
        for fld, names in ALIASES.items():
            if key in names and fld not in mapping:
                mapping[fld] = index
                result.columns[fld] = str(cell)
    if "article" not in mapping or "unit_price" not in mapping or "unit" not in mapping:
        missing = [HEADERS_LV[f] for f in ("article", "unit", "unit_price") if f not in mapping]
        result.errors.append((None, "trūkst obligāto kolonnu: " + ", ".join(missing)))
        result.fatal = True
        return result
    if len(table) - 1 > MAX_ROWS:
        result.errors.append((None, f"fails satur vairāk nekā {MAX_ROWS} rindas"))
        result.fatal = True
        return result
    seen = {}
    for offset, row in enumerate(table[1:], 2):
        if not any(v not in (None, "") and str(v).strip() for v in row):
            continue
        result.read_rows += 1

        def cell(fld):
            i = mapping.get(fld)
            return row[i] if i is not None and i < len(row) else None
        formula_cols = [f for f, i in mapping.items() if kinds.get((offset, i + 1)) == "formula"]
        if formula_cols:
            result.errors.append((offset, "šūna satur formulu (" + ", ".join(HEADERS_LV[f] for f in formula_cols)
                                  + "): formulas netiek izpildītas — ievadi vērtību"))
            continue
        errors_before = len(result.errors)
        raw_art = cell("article")
        if isinstance(raw_art, bool) or raw_art is None or str(raw_art).strip() == "":
            result.errors.append((offset, "artikuls nav norādīts"))
            continue
        if isinstance(raw_art, float) and raw_art == int(raw_art):
            raw_art = int(raw_art)
        if isinstance(raw_art, int):
            result.warnings.append((offset, f"artikuls {raw_art} ir skaitliska šūna: sākuma nulles varēja zust — formatē kolonnu kā TEKSTU"))
        article = _clean_text(raw_art, "artikuls", offset, result)
        rec = {"article": article}
        for fld in ("name", "spec", "unit", "supplier"):
            value = cell(fld)
            rec[fld] = _clean_text(value, HEADERS_LV[fld].lower(), offset, result) if value not in (None, "") else ""
        price, ok = _parse_price(cell("unit_price"), offset, result)
        rec["unit_price"] = price
        pack_raw = cell("pack_size")
        pack = None
        if pack_raw not in (None, ""):
            try:
                pack = float(str(pack_raw).replace(",", ".")) if not isinstance(pack_raw, (int, float)) else float(pack_raw)
                if pack <= 0 or pack != pack:
                    raise ValueError
            except ValueError:
                result.errors.append((offset, f"iepakojums: nederīga vērtība «{str(pack_raw)[:20]}»"))
        rec["pack_size"] = pack
        if price is not None and not rec["unit"]:
            result.errors.append((offset, "norādīta cena, bet nav mērvienības — cenu nevar piemērot"))
        if len(result.errors) > errors_before:
            continue
        if article in seen:
            result.errors.append((offset, f"dublikāts artikuls «{article}» (pirmā rinda {seen[article]}) — rinda izlaista"))
            continue
        seen[article] = offset
        result.rows.append(rec)
    return result


def diff_catalog(existing, imported_rows, used_units):
    """Salīdzina ar esošo katalogu un projekta rindām. `used_units`: artikuls → {vienību kopa, kas tiek lietota BOM rindās}.
    Atgriež dict: new, updated, unchanged (artikulu saraksti), unmatched (importētie artikuli, kurus nelieto neviena rinda),
    unit_conflicts (artikuls, kataloga vienība, rindu vienības), unknown_in_file (projekta artikuli, kuru nav importā)."""
    current = {str(c.get("article")).strip(): c for c in existing if str(c.get("article") or "").strip()}
    new, updated, unchanged = [], [], []
    for rec in imported_rows:
        old = current.get(rec["article"])
        if old is None:
            new.append(rec["article"])
        elif any((old.get(f) or None) != (rec.get(f) or None) for f in ("name", "spec", "unit", "unit_price", "pack_size", "supplier")
                 if rec.get(f) not in (None, "")):
            updated.append(rec["article"])
        else:
            unchanged.append(rec["article"])
    imported = {r["article"]: r for r in imported_rows}
    return {"new": new, "updated": updated, "unchanged": unchanged,
            "unmatched": [a for a in imported if a not in used_units],
            "unit_conflicts": [(a, imported[a]["unit"], sorted(u)) for a, u in used_units.items()
                               if a in imported and imported[a]["unit"] and set(u) != {imported[a]["unit"]}],
            "unknown_in_file": sorted(a for a in used_units if a not in imported and a not in current)}


def apply_catalog(project, imported_rows, used_units=None):
    """Apvieno ar projekta katalogu: tā paša artikula ieraksts tiek atjaunināts, citi saglabāti. TUKŠS importētais lauks neizdzēš
    esošo vērtību (trūkstoša cena nav nulle un nenoņem iepriekš ievadītu cenu).
    `used_units` (artikuls → vienību kopa BOM rindās): rinda, kuras mērvienība NEATBILST tāmes rindām ar šo artikulu, netiek piemērota
    (ne cena, ne vienība; konversijas netiek izdomātas). Atgriež izlaisto artikulu sarakstu (artikuls, importa vienība, rindu vienības)."""
    catalog = project.setdefault("catalog", [])
    by_art = {str(c.get("article")).strip(): c for c in catalog if str(c.get("article") or "").strip()}
    skipped = []
    for rec in imported_rows:
        units = (used_units or {}).get(rec["article"])
        if units and rec.get("unit") and set(units) != {rec["unit"]}:
            skipped.append((rec["article"], rec["unit"], sorted(units)))
            continue
        target = by_art.get(rec["article"])
        if target is None:
            target = {"article": rec["article"]}
            catalog.append(target)
            by_art[rec["article"]] = target
        for fld in FIELDS[1:]:
            if rec.get(fld) not in (None, ""):
                target[fld] = rec[fld]
            else:
                target.setdefault(fld, None if fld in ("unit_price", "pack_size") else "")
        target["source"] = "Imports no faila (lietotāja)"
    return skipped


# --- parauga šabloni (sintētiski) ----------------------------------------------------------------------------------
TEMPLATE_ROWS = [("00123", "CLT panelis 100 mm (DEMO)", "DEMO specifikācija", "m³", 480.0, "", "DEMO piegādātājs"),
                 ("SKR-6x80", "Skrūve 6×80 (DEMO)", "DEMO", "gab.", 0.12, 200, "DEMO piegādātājs"),
                 ("LENTE-01", "Hermetizācijas lente (DEMO)", "DEMO", "m", None, "", "")]


def catalog_template_xlsx() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Katalogs"
    ws.append([HEADERS_LV[f] for f in FIELDS])
    for rec in TEMPLATE_ROWS:
        ws.append(list(rec))
    for row in ws.iter_rows(min_row=2, max_col=1):
        for cell in row:
            cell.number_format = "@"                                   # artikuls kā teksts (sākuma nulles)
            cell.data_type = "s"
    for col, width in zip("ABCDEFG", (14, 34, 26, 12, 24, 12, 22)):
        ws.column_dimensions[col].width = width
    info = wb.create_sheet("Instrukcija")
    for line in ("SINTĒTISKS PARAUGS — visi dati ir DEMO, nav MLK cenas.",
                 "Obligātās kolonnas: Artikuls, Mērvienība, Vienības cena EUR bez PVN.",
                 "Artikulu glabā kā TEKSTU (arī sākuma nulles). Cena: EUR bez PVN par norādīto mērvienību; konversijas netiek veiktas.",
                 "Trūkstoša cena = atstāj šūnu TUKŠU (tā nav nulle). Formulas netiek izpildītas.",
                 "Mērvienībai jāsakrīt ar tāmes rindas mērvienību (m², m³, m, gab., kompl. …), citādi cena netiek piemērota."):
        info.append([line])
    info.column_dimensions["A"].width = 110
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def catalog_template_csv() -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow([HEADERS_LV[f] for f in FIELDS])
    for rec in TEMPLATE_ROWS:
        writer.writerow(["" if v is None else v for v in rec])
    return "﻿" + out.getvalue()
