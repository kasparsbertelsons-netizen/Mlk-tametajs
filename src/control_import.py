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
    stage_code: str = ""           # (Moneo pārskats) posma kods
    group: str = ""                # (Moneo pārskats) artikulu grupa


@dataclass
class ControlSheet:
    lines: list = field(default_factory=list)
    errors: list = field(default_factory=list)       # (rinda, ziņojums): rindas ar kļūdām netiek importētas
    warnings: list = field(default_factory=list)
    reconciliation: list = field(default_factory=list)   # kopsummu pārbaude: {row_no, label, total_plan, sum_plan, total_actual, sum_actual, ok}
    columns: dict = field(default_factory=dict)
    fatal: bool = False
    kind: str = "generic"                            # generic | moneo
    project_heading: str = ""
    layout_checks: list = field(default_factory=list)   # virsrakstu bloka atbilstības pārbaudes

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


# --- Moneo vispārīgā budžeta/faktiskā pārskata izkārtojums (kolonnu BURTI; Issue #16 korekcija) ---------------------------------------------
# Struktūra (bez vērtībām): virsraksta rindas B=Kods, F=Apraksts (projekts/posms, posmi atkārtojas); virsrakstu bloks J/M/P/S/W/Z; artikulu rindas
# E=kods, H=apraksts, I/K/N = budžeta daudzums/cena/summa, Q/T/V = faktiskais daudzums/cena/summa; grupu rindas D/G (kods/nosaukums) ar O/X summām;
# posma kontrolsumma: F=<bez koda>, P/Z; atkārtota posma kopsumma: J=Kopā, P/Z. Tukšās rindas ignorē. Mērvienību nav (saglabā nezināmu).
MONEO_LAYOUT = {"stage_code": "B", "stage_desc": "F", "group_code": "D", "group_name": "G", "code": "E", "desc": "H",
                "plan_qty": "I", "plan_price": "K", "plan_sum": "N", "actual_qty": "Q", "actual_price": "T", "actual_sum": "V",
                "group_plan_sum": "O", "group_actual_sum": "X", "stage_plan_sum": "P", "stage_actual_sum": "Z", "total_label": "J"}
MONEO_LAYOUT_LABELS = {"stage_code": "Posma/projekta kods", "stage_desc": "Posma/projekta apraksts (un «<bez koda>»)", "group_code": "Grupas kods",
                       "group_name": "Grupas nosaukums", "code": "Artikula kods", "desc": "Artikula apraksts", "plan_qty": "Budžeta daudzums",
                       "plan_price": "Budžeta cena", "plan_sum": "Budžeta summa", "actual_qty": "Faktiskais daudzums", "actual_price": "Faktiskā cena",
                       "actual_sum": "Faktiskā summa", "group_plan_sum": "Grupas budžeta summa", "group_actual_sum": "Grupas faktiskā summa",
                       "stage_plan_sum": "Posma kontrolsumma (budžets)", "stage_actual_sum": "Posma kontrolsumma (fakts)", "total_label": "«Kopā» etiķete"}
HEADER_BLOCK = {"J": ("budzets", "daudzums"), "M": ("cena",), "P": ("budzets", "summa"), "S": ("faktisk", "daudzums"), "W": ("cena",), "Z": ("faktisk", "summa")}
NUMERIC_FIELDS = ("plan_qty", "plan_price", "plan_sum", "actual_qty", "actual_price", "actual_sum")


def _col(letter):
    from openpyxl.utils import column_index_from_string
    return column_index_from_string(str(letter).strip().upper()) - 1


def _cell(row, letter):
    i = _col(letter)
    return row[i] if i < len(row) else None


def _text(value):
    return "" if value is None else str(value).strip()


def _is_num(value):
    """Vai šūna izskatās pēc skaitļa (nederīgs teksts → False; to apstrādā virsrakstu bloka/rindu tipu noteikšana)."""
    try:
        return _num(value) is not None
    except ValueError:
        return False


def detect_layout(filename, data: bytes) -> str:
    """«moneo» — ja failā ir Moneo pārskata pazīmes (F=<bez koda> vai J=Kopā), citādi «generic»."""
    try:
        rows = _read_table(filename, data)
    except Exception:
        return "generic"
    for row in rows[:5000]:
        if _text(_cell(row, "F")).lower().startswith("<bez") or (_text(_cell(row, "J")).lower().startswith("kopā") and _is_num(_cell(row, "P"))):
            return "moneo"
    return "generic"


def parse_moneo_report(filename, data: bytes, layout=None) -> ControlSheet:
    """Moneo vispārīgā pārskata imports pēc kolonnu burtiem (`layout` — lietotāja kartējums, ja struktūra atšķiras). Artikulu rindas netiek jauktas ar grupu,
    posma kontrolsummu un atkārtotām kopsummām; kopsummas NETIEK summētas, tikai saskaņotas."""
    lay = {**MONEO_LAYOUT, **(layout or {})}
    out = ControlSheet(kind="moneo")
    out.columns = dict(lay)
    if len(data) > MAX_BYTES:
        out.errors.append((None, "fails ir lielāks par 8 MB"))
        out.fatal = True
        return out
    try:
        table = _read_table(filename, data)
        for letter in lay.values():
            _col(letter)
    except Exception as error:
        out.errors.append((None, f"faila nolasīšana vai kartējums neizdevās ({type(error).__name__}): {str(error)[:120]}"))
        out.fatal = True
        return out
    if len(table) > MAX_ROWS + 1:
        out.errors.append((None, f"fails satur vairāk nekā {MAX_ROWS} rindas"))
        out.fatal = True
        return out
    headers, seen_header_texts = [], {}
    stage_code = stage_desc = group = ""
    items_seen = False
    for offset, row in enumerate(table, 1):
        if not any(v not in (None, "") and str(v).strip() for v in row):
            continue                                                            # tukšās rindas ignorē
        if any(str(v) == "=FORMULA" for v in row):
            out.errors.append((offset, "rinda satur formulu: formulas netiek izpildītas — ievadi vērtību"))
            continue
        # virsrakstu bloks: teksts kolonnās J/M/P/S/W/Z bez skaitļiem
        header_cells = {l: _text(_cell(row, l)) for l in HEADER_BLOCK}
        nums = {f: _cell(row, lay[f]) for f in NUMERIC_FIELDS}
        no_numbers = not any(_is_num(_cell(row, lay[f])) for f in NUMERIC_FIELDS + ("group_plan_sum", "group_actual_sum", "stage_plan_sum", "stage_actual_sum"))
        if no_numbers and any(header_cells.values()) and not _text(_cell(row, lay["code"])) and not _text(_cell(row, lay["stage_code"])):
            for l, t in header_cells.items():
                if t:
                    seen_header_texts[l] = (seen_header_texts.get(l, "") + " " + _norm(t)).strip()
            continue
        try:
            vals = {f: _num(_cell(row, lay[f])) for f in NUMERIC_FIELDS}
            g_plan, g_act = _num(_cell(row, lay["group_plan_sum"])), _num(_cell(row, lay["group_actual_sum"]))
            s_plan, s_act = _num(_cell(row, lay["stage_plan_sum"])), _num(_cell(row, lay["stage_actual_sum"]))
        except ValueError as error:
            out.errors.append((offset, str(error)))
            continue
        total_label = _text(_cell(row, lay["total_label"])).lower()
        f_text = _text(_cell(row, lay["stage_desc"]))
        code = _text(_cell(row, lay["code"]))
        desc = _text(_cell(row, lay["desc"]))
        if total_label.startswith("kopā") and (s_plan is not None or s_act is not None):
            out.lines.append(ControlLine(offset, "stage_total_repeat", stage=f"{stage_code} {stage_desc}".strip(), name="Kopā (atkārtots)", plan_sum=s_plan,
                                         actual_sum=s_act, stage_code=stage_code))
            continue
        if f_text.lower().startswith("<bez") and (s_plan is not None or s_act is not None):
            out.lines.append(ControlLine(offset, "stage_total", stage=f"{stage_code} {stage_desc}".strip(), name="Posma kontrolsumma", plan_sum=s_plan,
                                         actual_sum=s_act, stage_code=stage_code))
            continue
        if code and any(v is not None for v in vals.values()):
            if isinstance(_cell(row, lay["code"]), (int, float)) and not isinstance(_cell(row, lay["code"]), bool):
                out.warnings.append((offset, f"artikula kods {code} ir skaitlis: sākuma nulles varēja zust — formatē kolonnu kā TEKSTU"))
            out.lines.append(ControlLine(offset, "item", stage=f"{stage_code} {stage_desc}".strip(), code=code, name=desc, unit=None, plan_qty=vals["plan_qty"],
                                         actual_qty=vals["actual_qty"], plan_price=vals["plan_price"], actual_price=vals["actual_price"], plan_sum=vals["plan_sum"],
                                         actual_sum=vals["actual_sum"], scope=None, stage_code=stage_code, group=group))
            items_seen = True
            continue
        if code:
            out.warnings.append((offset, f"artikula rinda «{code[:24]}» bez skaitļiem ignorēta"))
            continue
        g_code, g_name = _text(_cell(row, lay["group_code"])), _text(_cell(row, lay["group_name"]))
        if g_code or g_name:
            group = f"{g_code} {g_name}".strip()
            if g_plan is not None or g_act is not None:
                out.lines.append(ControlLine(offset, "group_total", stage=f"{stage_code} {stage_desc}".strip(), name=group, plan_sum=g_plan, actual_sum=g_act,
                                             stage_code=stage_code, group=group))
            continue
        b_text = _text(_cell(row, lay["stage_code"]))
        if b_text and f_text and no_numbers:
            headings_so_far = [l for l in out.lines if l.row_type == "stage_header"]
            stage_code, stage_desc = b_text, f_text
            out.lines.append(ControlLine(offset, "stage_header", stage=f"{b_text} {f_text}".strip(), code=b_text, name=f_text, stage_code=b_text))
            group = ""
            if not headings_so_far and not items_seen:
                out.project_heading = f"{b_text} {f_text}".strip()            # pirmais virsraksts pirms pirmās artikulu rindas (vēlāk var izrādīties projekts)
            continue
        out.warnings.append((offset, "rinda neatbilst izkārtojumam (kartējums?) un ir ignorēta"))
    # ja pirmais virsraksts ir PROJEKTS: otrs virsraksts seko bez artikuliem pa vidu
    heads = [l for l in out.lines if l.row_type == "stage_header"]
    if len(heads) >= 2:
        first_idx, second_idx = out.lines.index(heads[0]), out.lines.index(heads[1])
        if not any(l.row_type == "item" for l in out.lines[first_idx:second_idx]):
            out.project_heading = heads[0].stage
            out.lines[first_idx].row_type = "project_header"
        else:
            out.project_heading = ""
    for letter, words in HEADER_BLOCK.items():
        text = seen_header_texts.get(letter, "")
        if not text:
            out.layout_checks.append((letter, "virsrakstu bloka teksts nav atrasts"))
        elif not all(w in text for w in words):
            out.layout_checks.append((letter, f"virsraksts «{text[:40]}» neatbilst gaidītajam ({' + '.join(words)})"))
    if out.layout_checks:
        out.warnings.append((None, "virsrakstu bloks neatbilst gaidītajam kolonnu izkārtojumam: " + "; ".join(f"{l}: {m}" for l, m in out.layout_checks[:4])
                             + " — pārbaudi kartējumu"))
    if not out.items:
        out.errors.append((None, "nav atrasta neviena artikula rinda: struktūra neatbilst izkārtojumam — pielāgo kolonnu kartējumu"))
        out.fatal = True
    _reconcile_moneo(out)
    return out


def _reconcile_moneo(sheet):
    """Saskaņo: posma kontrolsumma (F=<bez koda>) pret artikulu rindām kopš iepriekšējās kontrolsummas; atkārtotā kopsumma pret kontrolsummu; grupu summas pret
    artikuliem pēc grupas rindas. Nekas netiek summēts kopsummu dēļ."""
    tol = 0.02 + 1e-6
    since, last_stage_total, group_row, group_items = [], None, None, []

    def close_group():
        if group_row is not None:
            sp = round(sum(x.plan_sum for x in group_items if x.plan_sum is not None), 2)
            sa = round(sum(x.actual_sum for x in group_items if x.actual_sum is not None), 2)
            ok = (group_row.plan_sum is None or abs(sp - group_row.plan_sum) <= tol) and (group_row.actual_sum is None or abs(sa - group_row.actual_sum) <= tol)
            sheet.reconciliation.append({"row_no": group_row.row_no, "label": group_row.name, "type": "group_total", "total_plan": group_row.plan_sum, "sum_plan": sp,
                                         "total_actual": group_row.actual_sum, "sum_actual": sa, "ok": ok})
            if not ok:
                sheet.warnings.append((group_row.row_no, f"grupas «{group_row.name[:30]}» summa neatbilst artikulu rindām (plāns {sp} / fakts {sa}): pārbaudi"))
    for l in sheet.lines:
        if l.row_type == "item":
            since.append(l)
            group_items.append(l)
        elif l.row_type == "group_total":
            close_group()
            group_row, group_items = l, []
        elif l.row_type == "stage_header":
            close_group()
            group_row, group_items = None, []
        elif l.row_type == "stage_total":
            close_group()
            group_row, group_items = None, []
            sp = round(sum(x.plan_sum for x in since if x.plan_sum is not None), 2)
            sa = round(sum(x.actual_sum for x in since if x.actual_sum is not None), 2)
            ok = (l.plan_sum is None or abs(sp - l.plan_sum) <= tol) and (l.actual_sum is None or abs(sa - l.actual_sum) <= tol)
            sheet.reconciliation.append({"row_no": l.row_no, "label": l.stage, "type": "stage_total", "total_plan": l.plan_sum, "sum_plan": sp,
                                         "total_actual": l.actual_sum, "sum_actual": sa, "ok": ok})
            if not ok:
                sheet.warnings.append((l.row_no, f"posma «{l.stage[:30]}» kontrolsumma neatbilst artikulu rindu summai (plāns {sp} / fakts {sa}): pārbaudi eksportu; "
                                                 "kontrolsumma NETIEK izmantota summēšanā"))
            last_stage_total, since = l, []
        elif l.row_type == "stage_total_repeat":
            ok = last_stage_total is not None and (l.plan_sum is None or last_stage_total.plan_sum is None or abs(l.plan_sum - last_stage_total.plan_sum) <= tol) \
                and (l.actual_sum is None or last_stage_total.actual_sum is None or abs(l.actual_sum - last_stage_total.actual_sum) <= tol)
            sheet.reconciliation.append({"row_no": l.row_no, "label": l.stage + " (atkārtota kopsumma)", "type": "stage_total_repeat", "total_plan": l.plan_sum,
                                         "sum_plan": last_stage_total.plan_sum if last_stage_total else None, "total_actual": l.actual_sum,
                                         "sum_actual": last_stage_total.actual_sum if last_stage_total else None, "ok": ok})
            if not ok:
                sheet.warnings.append((l.row_no, "atkārtotā posma kopsumma («Kopā») neatbilst posma kontrolsummai"))
    close_group()
    if since:
        sheet.warnings.append((None, f"{len(since)} artikulu rindas nav aptvertas ar posma kontrolsummu (nav F=<bez koda> rindas)"))


# --- Stundu pārskats: 2 rindu virsraksts (A=Darbība, B=Stundas; nākamajā rindā B=Reāli, C=Plānots), A=operācija, A=Kopā: kontrolsumma -------------
HOURS_LAYOUT = {"name": "A", "actual": "B", "plan": "C"}


@dataclass
class HoursOp:
    row_no: int
    name: str
    actual: object
    plan: object


@dataclass
class HoursReport:
    operations: list = field(default_factory=list)
    total_actual: object = None                      # «Kopā:» rinda: KONTROLSUMMA, nevis operācija
    total_plan: object = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    reconciliation: dict = field(default_factory=dict)
    layout: dict = field(default_factory=dict)
    fatal: bool = False


def parse_hours_report(filename, data: bytes, layout=None) -> HoursReport:
    out = HoursReport()
    lay = {**HOURS_LAYOUT, **(layout or {})}
    out.layout = dict(lay)
    if len(data) > MAX_BYTES:
        out.errors.append((None, "fails ir lielāks par 8 MB"))
        out.fatal = True
        return out
    try:
        table = _read_table(filename, data)
        cols = {k: _col(v) for k, v in lay.items()}
    except Exception as error:
        out.errors.append((None, f"faila nolasīšana vai kartējums neizdevās ({type(error).__name__}): {str(error)[:120]}"))
        out.fatal = True
        return out
    non_empty = [(i, r) for i, r in enumerate(table, 1) if any(v not in (None, "") and str(v).strip() for v in r)]
    start = next((k for k, (_i, r) in enumerate(non_empty) if _norm(r[cols["name"]] if cols["name"] < len(r) else "").startswith("darbiba")), None)
    if start is None:
        out.errors.append((None, "nav atrasts virsraksts «Darbība» (A kolonnā): pārbaudi kartējumu"))
        out.fatal = True
        return out
    actual_col, plan_col = cols["actual"], cols["plan"]
    body_from = start + 1
    if start + 1 < len(non_empty):
        r2 = non_empty[start + 1][1]
        labels = {j: _norm(v) for j, v in enumerate(r2) if v not in (None, "")}
        a = next((j for j, t in labels.items() if t.startswith(("reali", "fakt"))), None)
        p = next((j for j, t in labels.items() if t.startswith("planot")), None)
        if a is not None and p is not None:
            actual_col, plan_col, body_from = a, p, start + 2                  # kolonnu lomas nosaka 2. virsraksta rinda (Reāli/Plānots)
        else:
            out.warnings.append((non_empty[start + 1][0], "otrajā virsraksta rindā nav «Reāli»/«Plānots»: izmantots kartējums (faktiskās=B, plānotās=C)"))
    for rno, row in non_empty[body_from:]:
        name = _text(row[cols["name"]]) if cols["name"] < len(row) else ""
        if any(str(v) == "=FORMULA" for v in row):
            out.errors.append((rno, "rinda satur formulu: formulas netiek izpildītas — ievadi vērtību"))
            continue
        try:
            actual = _num(row[actual_col]) if actual_col < len(row) else None
            plan = _num(row[plan_col]) if plan_col < len(row) else None
        except ValueError as error:
            out.errors.append((rno, str(error)))
            continue
        if _norm(name).startswith("kopa"):
            out.total_actual, out.total_plan = actual, plan                       # kontrolsumma, NE operācija
            continue
        if not name:
            out.warnings.append((rno, "rinda bez operācijas nosaukuma ignorēta"))
            continue
        if actual is None and plan is None:
            out.warnings.append((rno, f"operācija «{name[:30]}» bez stundām ignorēta"))
            continue
        out.operations.append(HoursOp(rno, name, actual, plan))
    names = [_norm(o.name) for o in out.operations]
    dups = sorted({n for n in names if names.count(n) > 1})
    if dups:
        out.warnings.append((None, "atkārtotas operācijas (tiks agregētas salīdzināšanā, avota rindas saglabātas): " + ", ".join(dups[:5])))
    sa = round(sum(o.actual for o in out.operations if o.actual is not None), 4)
    sp = round(sum(o.plan for o in out.operations if o.plan is not None), 4)
    ok_a = out.total_actual is None or abs(sa - out.total_actual) <= 0.01 + 1e-6
    ok_p = out.total_plan is None or abs(sp - out.total_plan) <= 0.01 + 1e-6
    out.reconciliation = {"sum_actual": sa, "sum_plan": sp, "total_actual": out.total_actual, "total_plan": out.total_plan, "ok": ok_a and ok_p,
                          "has_total": out.total_actual is not None or out.total_plan is not None}
    if not out.reconciliation["ok"]:
        out.warnings.append((None, f"«Kopā:» kontrolsumma neatbilst operāciju summai (fakts {sa} / plāns {sp}): pārbaudi; kontrolsumma netiek izmantota summēšanā"))
    if not out.operations:
        out.errors.append((None, "nav atrasta neviena operācija"))
        out.fatal = True
    return out
