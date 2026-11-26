"""Lokāls Moneo budžeta/faktiskā patēriņa un stundu KONTROLTĀMES imports (Issue #16; sintētiski paraugi).

Fails (XLSX/CSV) tiek lasīts atmiņā; nekas netiek sūtīts. Importētie faktiskie dati NEAIZPILDA un NEPĀRRAKSTA AD prognozi: tie tiek glabāti
atsevišķi (`project["actuals"]`) un tiek izmantoti tikai salīdzināšanai (`src/forecast_compare.py`).

Rindu tipi (svarīgi, lai nesummētu divreiz): `item` — artikula rinda (ar artikula kodu); `group_total`, `stage_total`, `grand_total` — kopsummas;
`stage_header` — posma virsraksts (bez skaitļiem); `hours` — stundu rinda. Kopsummu rindas NETIEK ieskaitītas summās, bet tiek izmantotas
saskaņošanas pārbaudei (kopsumma pret artikulu rindu summu). Ja kolonna «Rindas tips» ir, tā ir noteicošā; citādi tips tiek izsecināts pēc artikula koda
un nosaukuma («Kopā», «Posma kopsumma» …). Mērvienība netiek izdomāta: ja eksportā nav, tā paliek `None`.
"""
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 20000
FIELDS = ["stage", "code", "name", "unit", "plan_qty", "actual_qty", "plan_price", "actual_price", "plan_sum", "actual_sum", "scope", "row_type"]
ALIASES = {
    "stage": ("posms", "ražošanas posms", "razosanas posms", "stage"),
    "code": ("artikuls", "artikula kods", "kods", "art", "code", "sku"),
    "name": ("nosaukums", "apraksts", "materials", "name"),
    "unit": ("mervieniba", "merv", "vieniba", "unit"),
    "plan_qty": ("planotais daudzums", "plana daudzums", "plan daudzums", "planots daudzums", "daudzums plans", "plan qty"),
    "actual_qty": ("faktiskais daudzums", "fakta daudzums", "fakts daudzums", "daudzums fakts", "actual qty"),
    "plan_price": ("planotā cena", "planota cena", "plana cena", "plan cena", "cena plans", "plan price"),
    "actual_price": ("faktiska cena", "faktiskā cena", "fakta cena", "fakts cena", "cena fakts", "actual price"),
    "plan_sum": ("planota summa", "plana summa", "plan summa", "summa plans", "plan sum"),
    "actual_sum": ("faktiska summa", "fakta summa", "fakts summa", "summa fakts", "actual sum"),
    "scope": ("veids", "izmaksu veids", "izmaksu segums", "segums", "tips", "kind"),
    "row_type": ("rindas tips", "rindas veids", "row type"),
}
TOTAL_RE = re.compile(r"^\s*(kopā|kopsumma|summa|kopā\s+posmam|posma\s+kopsumma|grupas\s+kopsumma|total|subtotal|kopā\s+grupai)\b", re.I)
STAGE_TOTAL_RE = re.compile(r"posm", re.I)
GROUP_TOTAL_RE = re.compile(r"grupas|grupai|group", re.I)
STAGE_HEADER_RE = re.compile(r"^\s*posms\s*[:\-–]\s*(.+)$", re.I)
HOURS_UNITS = ("h", "st.", "st", "stundas", "stunda")
SCOPE_MATERIAL, SCOPE_EXTERNAL, SCOPE_HOURS = "materiāli", "ārējās izmaksas", "stundas"


def _norm(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _num(value):
    """None, ja tukšs; float; ValueError, ja nederīgs. Pieņem decimālkomatu un atstarpes."""
    if value is None or isinstance(value, bool):
        if isinstance(value, bool):
            raise ValueError("nederīga vērtība")
        return None
    if isinstance(value, (int, float)):
        out = float(value)
    else:
        text = str(value).replace(" ", "").replace(" ", "").replace("€", "").replace("EUR", "")
        if not text:
            return None
        if "," in text and "." in text:
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
        try:
            out = float(text)
        except ValueError:
            raise ValueError(f"nederīga vērtība «{str(value)[:20]}»") from None
    if out != out or out in (float("inf"), float("-inf")):
        raise ValueError("nav galīgs skaitlis")
    return out


@dataclass
class ControlLine:
    row_no: int
    row_type: str                  # item | group_total | stage_total | grand_total | stage_header | hours | ignored
    stage: str = ""
    code: str = ""
    name: str = ""
    unit: object = None
    plan_qty: object = None
    actual_qty: object = None
    plan_price: object = None
    actual_price: object = None
    plan_sum: object = None
    actual_sum: object = None
    scope: object = None           # materiāli | ārējās izmaksas | stundas | None (nav norādīts)


@dataclass
class ControlSheet:
    lines: list = field(default_factory=list)
    errors: list = field(default_factory=list)       # (rinda, ziņojums): rindas ar kļūdām netiek importētas
    warnings: list = field(default_factory=list)
    reconciliation: list = field(default_factory=list)   # kopsummu pārbaude: {row_no, label, total_plan, sum_plan, total_actual, sum_actual, ok}
    columns: dict = field(default_factory=dict)
    fatal: bool = False

    @property
    def items(self):
        return [l for l in self.lines if l.row_type == "item"]

    @property
    def hours(self):
        return [l for l in self.lines if l.row_type == "hours"]

    @property
    def totals(self):
        return [l for l in self.lines if l.row_type in ("group_total", "stage_total", "grand_total")]


def _read_table(filename, data):
    name = str(filename or "").lower()
    if name.endswith(".xlsx") or data[:2] == b"PK":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
        ws = wb["Kontroltāme"] if "Kontroltāme" in wb.sheetnames else wb.worksheets[0]
        if ws.max_row and ws.max_row > MAX_ROWS + 1:
            raise ValueError(f"fails satur vairāk nekā {MAX_ROWS} rindas")
        rows = []
        for row in ws.iter_rows():
            rows.append([("=FORMULA" if c.data_type == "f" else c.value) for c in row])
        return rows
    if name.endswith(".csv") or name.endswith(".txt"):
        for enc in ("utf-8-sig", "cp1257", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        first = text.splitlines()[0] if text.strip() else ""
        delim = max((";", ",", "\t"), key=first.count)
        return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delim)]
    raise ValueError("neatbalstīts faila tips (jāpiegādā .xlsx vai .csv)")


def _scope_of(raw, unit):
    text = _norm(raw)
    if text:
        if any(w in text for w in ("stund", "darb", "hours", "labour")):
            return SCOPE_HOURS
        if any(w in text for w in ("arpak", "arej", "apaksuznem", "external", "transport", "montaz")):
            return SCOPE_EXTERNAL
        if "material" in text:
            return SCOPE_MATERIAL
    if str(unit or "").strip().lower() in HOURS_UNITS:
        return SCOPE_HOURS
    return None


def parse_control_sheet(filename, data: bytes) -> ControlSheet:
    out = ControlSheet()
    if len(data) > MAX_BYTES:
        out.errors.append((None, "fails ir lielāks par 8 MB"))
        out.fatal = True
        return out
    try:
        table = _read_table(filename, data)
    except Exception as error:
        out.errors.append((None, f"faila nolasīšana neizdevās ({type(error).__name__}): {str(error)[:120]}"))
        out.fatal = True
        return out
    if len(table) > MAX_ROWS + 1:
        out.errors.append((None, f"fails satur vairāk nekā {MAX_ROWS} rindas"))
        out.fatal = True
        return out
    header_index = next((i for i, r in enumerate(table) if any(_norm(c) in ALIASES["code"] + ALIASES["name"] for c in r if c is not None)), None)
    if header_index is None:
        out.errors.append((None, "nav atrasta virsraksta rinda (jābūt kolonnām «Artikuls»/«Nosaukums»)"))
        out.fatal = True
        return out
    mapping = {}
    for idx, cell in enumerate(table[header_index]):
        key = _norm(cell)
        for fld, names in ALIASES.items():
            if key in [_norm(n) for n in names] and fld not in mapping:
                mapping[fld] = idx
                out.columns[fld] = str(cell)
    if "name" not in mapping or "code" not in mapping:
        out.errors.append((None, "trūkst obligāto kolonnu: Artikuls, Nosaukums"))
        out.fatal = True
        return out
    stage, last_item_block = "", []
    block = {"stage": [], "group": []}
    for offset, row in enumerate(table[header_index + 1:], header_index + 2):
        if not any(v not in (None, "") and str(v).strip() for v in row):
            continue

        def cell(fld):
            i = mapping.get(fld)
            return row[i] if i is not None and i < len(row) else None
        if any(str(v) == "=FORMULA" for v in row):
            out.errors.append((offset, "rinda satur formulu: formulas netiek izpildītas — ievadi vērtību"))
            continue
        code = str(cell("code") or "").strip()
        name = str(cell("name") or "").strip()
        unit = str(cell("unit") or "").strip() or None
        try:
            vals = {f: _num(cell(f)) for f in ("plan_qty", "actual_qty", "plan_price", "actual_price", "plan_sum", "actual_sum")}
        except ValueError as error:
            out.errors.append((offset, str(error)))
            continue
        declared = _norm(cell("row_type"))
        has_numbers = any(v is not None for v in vals.values())
        stage_cell = str(cell("stage") or "").strip()
        header = None
        if not code and not has_numbers:
            header = STAGE_HEADER_RE.match(name) or STAGE_HEADER_RE.match(stage_cell)
        if header:
            stage = header.group(1).strip()
            out.lines.append(ControlLine(offset, "stage_header", stage=stage, name=name))
            continue
        if stage_cell:
            stage = stage_cell
        # rindas tips: deklarētais ir noteicošs; citādi izsecināts
        if declared:
            if declared.startswith(("artikul", "item", "rinda")):
                rtype = "item"
            elif declared.startswith(("posm", "stage")):
                rtype = "stage_total"
            elif declared.startswith(("grupa", "group")):
                rtype = "group_total"
            elif declared.startswith(("kopa", "total", "kopsumma", "gala")):
                rtype = "grand_total"
            elif declared.startswith(("stund", "hours")):
                rtype = "hours"
            else:
                out.warnings.append((offset, f"nezināms rindas tips «{cell('row_type')}»: rinda ignorēta"))
                continue
        elif not code and has_numbers and _scope_of(cell("scope"), unit) == SCOPE_HOURS and not TOTAL_RE.match(name):
            rtype = "hours"
        elif not code and (TOTAL_RE.match(name) or has_numbers):
            low = name.lower()
            rtype = "stage_total" if STAGE_TOTAL_RE.search(low) else ("group_total" if GROUP_TOTAL_RE.search(low) else "grand_total")
            if not TOTAL_RE.match(name):
                out.warnings.append((offset, f"rinda bez artikula koda ar summām («{name[:30]}») atzīta par kopsummu — netiek summēta"))
        elif code:
            rtype = "item"
        else:
            out.warnings.append((offset, "rinda bez artikula koda un bez skaitļiem ignorēta"))
            continue
        scope = _scope_of(cell("scope"), unit)
        if rtype == "item" and scope == SCOPE_HOURS:
            rtype = "hours"
        if rtype == "hours":
            scope = SCOPE_HOURS
        if rtype == "item" and not code:
            out.errors.append((offset, "artikula rindai nav artikula koda"))
            continue
        line = ControlLine(offset, rtype, stage, code, name, unit, vals["plan_qty"], vals["actual_qty"], vals["plan_price"], vals["actual_price"],
                           vals["plan_sum"], vals["actual_sum"], scope)
        out.lines.append(line)
    _reconcile(out)
    return out


def _reconcile(sheet):
    """Kopsummu rindu pārbaude pret artikulu rindām (neietekmē summas; tikai atklāj dubultu summēšanu/neatbilstību)."""
    since = []                                       # artikulu rindas kopš iepriekšējās kopsummas
    stage_items = []
    for l in sheet.lines:
        if l.row_type in ("item", "hours"):
            since.append(l)
            stage_items.append(l)
        elif l.row_type in ("group_total", "stage_total", "grand_total"):
            pool = since if l.row_type == "group_total" else (stage_items if l.row_type == "stage_total" else [x for x in sheet.lines if x.row_type in ("item", "hours")])
            money = [x for x in pool if x.row_type == "item"]
            sp = round(sum(x.plan_sum for x in money if x.plan_sum is not None), 2)
            sa = round(sum(x.actual_sum for x in money if x.actual_sum is not None), 2)
            ok_p = l.plan_sum is None or abs(sp - l.plan_sum) <= 0.02 + 1e-6
            ok_a = l.actual_sum is None or abs(sa - l.actual_sum) <= 0.02 + 1e-6
            sheet.reconciliation.append({"row_no": l.row_no, "label": l.name, "type": l.row_type, "total_plan": l.plan_sum, "sum_plan": sp,
                                         "total_actual": l.actual_sum, "sum_actual": sa, "ok": ok_p and ok_a})
            if not (ok_p and ok_a):
                sheet.warnings.append((l.row_no, f"kopsumma «{l.name[:30]}» neatbilst artikulu rindu summai (plāns {sp} / fakts {sa}): pārbaudi "
                                                 "eksportu; kopsumma NETIEK izmantota summēšanā"))
            if l.row_type == "group_total":
                since = []
            if l.row_type == "stage_total":
                since, stage_items = [], []
