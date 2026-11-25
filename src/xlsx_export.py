"""Īsts XLSX eksports (openpyxl, Issue #14): Kopsavilkums, Klienta piedāvājums, Materiālu tāme, Iepirkumi, Darba operācijas, Pieņēmumi.

- Skaitļi ir skaitļu šūnas (nevis teksts); trūkstošs lielums ir teksts «nav ievadīts» (nav 0).
- Visas teksta šūnas tiek ierakstītas kā TEKSTS (data_type "s"), tāpēc importēts vai lietotāja teksts, kas sākas ar =, +, -, @, netiek
  izpildīts kā formula.
- «Klienta piedāvājums» NESATUR iekšējās pašizmaksas (darba stundas/likmes, materiālu cenas, pašizmaksu, uzcenojumu/maržu, peļņu).
- DEMO un nepilnība tiek skaidri norādīta; nepilns/provizorisks budžets netiek dēvēts par gala piedāvājumu.
- Rindas netiek apvienotas (nesavietojamas specifikācijas/vienības): katra BOM rinda ir atsevišķi, ar rindas ID izsekojamībai.
"""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.building_estimate import CONSTRUCTIONS, NOT_FINAL, STAGE_NOTE, ST_DUP, Estimate

NOT_ENTERED = "nav ievadīts"
HEAD_FILL = PatternFill("solid", fgColor="DDE6EE")
WARN_FILL = PatternFill("solid", fgColor="FFE9B3")
BOLD = Font(bold=True)
MONEY = '#,##0.00'
QTY = '#,##0.000'


def _put(ws, row, col, value, fmt=None, bold=False, fill=None, wrap=False):
    cell = ws.cell(row=row, column=col)
    if isinstance(value, bool):
        value = "jā" if value else "nē"
    if value is None:
        value = NOT_ENTERED
    if isinstance(value, str):
        cell.value = value
        cell.data_type = "s"                      # nekad formula (arī, ja teksts sākas ar =, +, -, @)
        cell.number_format = "@"
    else:
        cell.value = value
        if fmt:
            cell.number_format = fmt
    if bold:
        cell.font = BOLD
    if fill:
        cell.fill = fill
    if wrap:
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    return cell


def _row(ws, row, values, fmts=None, bold=False, fill=None):
    for i, value in enumerate(values, 1):
        _put(ws, row, i, value, (fmts or {}).get(i), bold, fill)


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _banner(project, est: Estimate, b):
    lines = [NOT_FINAL]
    if project.get("is_demo") or str(project.get("name", "")).upper().startswith("DEMO"):
        lines.append("DEMO — SINTĒTISKI DATI: nav MLK cenas, normas vai reāls projekts.")
    lines.append("NEPILNS: " + "; ".join(b["reasons"]) if b["incomplete"] else "Ievaddati ievadīti (budžets joprojām provizorisks).")
    return lines


def build_workbook(project: dict, est: Estimate) -> bytes:
    b = est.budget()
    wb = Workbook()
    summary_sheet(wb.active, project, est, b)
    client_sheet(wb.create_sheet("Klienta piedāvājums"), project, est, b)
    materials_sheet(wb.create_sheet("Materiālu tāme"), est)
    procurement_sheet(wb.create_sheet("Iepirkumi"), est)
    labour_sheet(wb.create_sheet("Darba operācijas"), est, b)
    assumptions_sheet(wb.create_sheet("Pieņēmumi un neiekļautais"), project, est, b)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def summary_sheet(ws, project, est, b):
    ws.title = "Kopsavilkums"
    r = 1
    _put(ws, r, 1, f"Projekts: {project.get('name') or 'Projekts'}", bold=True)
    for line in _banner(project, est, b):
        r += 1
        _put(ws, r, 1, line, bold=True, fill=WARN_FILL)
    r += 1
    _put(ws, r, 1, "Konstrukcija: " + CONSTRUCTIONS.get(est.construction, est.construction))
    r += 1
    _put(ws, r, 1, STAGE_NOTE)
    r += 1
    _put(ws, r, 1, "Iepirkuma gatavība: " + est.procurement_status)
    r += 2
    _row(ws, r, ["BUDŽETS (EUR bez PVN)", "Summa", "Piezīme"], bold=True, fill=HEAD_FILL)
    pr = est.pricing or {}
    items = [
        ("Materiāli (pasūtāmais × cena)", b["materials"] if b["priced_rows"] else None, f"rindas ar cenu {b['priced_rows']}, bez cenas {b['unpriced_rows']}"),
        ("Ražošanas darbs (stundas × likme)", b["labour_cost"] if b["labour_rows"] else None, f"{b['labour_hours']:.2f} h; operācijas {b['labour_rows']}"),
        ("Ārpakalpojumi", b["by_category"]["Ārpakalpojumi"], "manuāli"),
        ("Transports", b["by_category"]["Transports"], "manuāli"),
        ("Montāža", b["by_category"]["Montāža"], "manuāli"),
        ("Citas izmaksas", b["by_category"]["Cits"], "manuāli"),
        ("TIEŠĀS IZMAKSAS", b["direct"], "tikai ievadītās"),
        (f"Pieskaitāmās izmaksas ({pr.get('overhead_pct') if pr.get('overhead_pct') is not None else NOT_ENTERED} % no tiešajām)", b["overhead"], ""),
        ("PAŠIZMAKSA", b["cost_total"], "tiešās + pieskaitāmās"),
    ]
    for name, value, note in items:
        r += 1
        _row(ws, r, [name, value, note], {2: MONEY}, bold=name.isupper() or name.startswith("PAŠ") or name.startswith("TIE"))
    method = b["method"]
    if method == "markup":
        formula = f"UZCENOJUMS {pr.get('markup_pct')} %: cena = pašizmaksa × (1 + uzcenojums)"
    elif method == "margin":
        formula = f"PEĻŅAS MARŽA {pr.get('margin_pct')} % no cenas: cena = pašizmaksa / (1 − marža)"
    else:
        formula = "uzcenojums/marža nav izvēlēta"
    r += 1
    _row(ws, r, ["Cenojuma metode", formula, ""])
    for name, value in (("PĀRDOŠANAS CENA bez PVN", b["sell"]), ("Peļņa (cena − pašizmaksa)", b["profit"]),
                        (f"PVN ({pr.get('vat_pct')} %)" if pr.get("vat_enabled") else "PVN (nav iespējots)", b["vat"] if pr.get("vat_enabled") else None),
                        ("Summa ar PVN", b["total_incl"])):
        r += 1
        _row(ws, r, [name, value, "" if value is not None else "nav aprēķināts"], {2: MONEY}, bold=name.startswith("PĀRD") or name.startswith("Summa"))
    r += 2
    _row(ws, r, ["Grupa", "Statuss", "Rindas", "Nav ievadīts", "Koksne neto m³", "Koksne pasūt. m³", "Darba stundas"], bold=True, fill=HEAD_FILL)
    for s in est.summary():
        r += 1
        _row(ws, r, [s["group"], s["status"], s["rows"], s["not_entered"], round(s["timber_net"], 3), round(s["timber_order"], 3), s["hours"]],
             {5: QTY, 6: QTY, 7: '0.00'})
    _widths(ws, [44, 34, 34, 14, 16, 16, 14])


def client_sheet(ws, project, est, b):
    """Klienta budžeta piedāvājums: BEZ iekšējām pašizmaksām, stundām, likmēm, uzcenojuma/maržas un materiālu cenām."""
    r = 1
    _put(ws, r, 1, "PROVIZORISKS BUDŽETA PIEDĀVĀJUMS", bold=True)
    r += 1
    _put(ws, r, 1, "Nav gala piedāvājums. Provizorisks aprēķins, nav konstruktora specifikācija.", bold=True, fill=WARN_FILL)
    if project.get("is_demo") or str(project.get("name", "")).upper().startswith("DEMO"):
        r += 1
        _put(ws, r, 1, "DEMO — sintētiski dati, nav MLK piedāvājums.", bold=True, fill=WARN_FILL)
    if b["incomplete"]:
        r += 1
        _put(ws, r, 1, "NEPILNS: daļa ievaddatu vēl nav ievadīta; summa var mainīties.", bold=True, fill=WARN_FILL)
    r += 2
    _put(ws, r, 1, f"Projekts: {project.get('name') or 'Projekts'}", bold=True)
    r += 1
    _put(ws, r, 1, "Konstrukcija: " + CONSTRUCTIONS.get(est.construction, est.construction))
    r += 2
    _row(ws, r, ["Darbu apjoms (pa grupām)", "Statuss"], bold=True, fill=HEAD_FILL)
    for s in est.summary():
        if s["rows"] or s["status"] != "NAV IEVADĪTS":
            r += 1
            _row(ws, r, [s["group"], "ietverts" if s["status"] in ("ievadīta", "tikai manuāla") else "nepilns / nav ievadīts"])
    a = est.areas
    r += 2
    _row(ws, r, ["Galvenie lielumi", "Vērtība"], bold=True, fill=HEAD_FILL)
    for label, key in (("Moduļu grīdas laukums, m²", "floor_frame_m2"), ("Ārsienu neto laukums, m²", "ext_walls_net_m2"),
                       ("Jumta platība, m²", "roof_m2")):
        r += 1
        _row(ws, r, [label, a.get(key)], {2: '0.00'})
    r += 2
    _row(ws, r, ["CENA (EUR)", "Summa"], bold=True, fill=HEAD_FILL)
    pr = est.pricing or {}
    r += 1
    _row(ws, r, ["Provizoriskā cena bez PVN", b["sell"]], {2: MONEY}, bold=True)
    if pr.get("vat_enabled"):
        r += 1
        _row(ws, r, [f"PVN {pr.get('vat_pct')} %", b["vat"]], {2: MONEY})
        r += 1
        _row(ws, r, ["Summa ar PVN", b["total_incl"]], {2: MONEY}, bold=True)
    r += 2
    _put(ws, r, 1, "Šajā piedāvājumā NAV iekļauts:", bold=True)
    for work in est.excluded:
        r += 1
        _put(ws, r, 1, "• " + work)
    _widths(ws, [60, 28])


MAT_HEADER = ["Rindas ID", "Konstrukciju grupa", "Artikuls", "Materiāls", "Specifikācija", "Mērvienība", "Neto", "Rezerve %", "Pasūtāmais",
              "Iepakojums", "Cena EUR/vienība", "Izmaksas EUR", "Modulis/telpa/sistēma", "Ražošanas posms", "Avots/pieņēmums",
              "Apstiprinājums", "Statuss", "Aprēķina pamats", "Alternatīvā vienība (nav cenota)"]


def _mat_row(r):
    alt = None if r.alt_qty is None else f"{r.alt_qty:.3f} {r.alt_unit}"
    return [r.row_id, r.group, r.article or "", r.material, r.spec, r.unit, r.qty, r.waste_pct, r.order_qty, r.pack_size, r.unit_price,
            r.cost, r.module, r.stage, r.source, r.approval, r.status, r.basis, alt or ""]


MAT_FMT = {7: QTY, 9: QTY, 10: '0.##', 11: MONEY, 12: MONEY}


def materials_sheet(ws, est):
    _row(ws, 1, MAT_HEADER, bold=True, fill=HEAD_FILL)
    r = 1
    for row in est.rows:
        r += 1
        _row(ws, r, _mat_row(row), MAT_FMT)
    r += 2
    cost = sum(x.cost for x in est.rows if x.cost is not None)
    _row(ws, r, ["", "", "", "Materiāli kopā (tikai rindas ar cenu)", "", "", "", "", "", "", "", cost], {12: MONEY}, bold=True)
    _widths(ws, [28, 26, 14, 44, 30, 10, 12, 10, 12, 10, 12, 14, 18, 18, 30, 16, 26, 44, 22])
    ws.freeze_panes = "E2"


def procurement_sheet(ws, est):
    """Iepirkumi: katra rinda atsevišķi (specifikācijas un vienības netiek apvienotas); trūkstošs daudzums = «nav ievadīts»."""
    header = ["Artikuls", "Specifikācija", "Materiāls", "Mērvienība", "Neto", "Rezerve %", "Pasūtāmais", "Iepakojums", "Cena EUR/vienība",
              "Izmaksas EUR", "Modulis", "Ražošanas posms", "Statuss", "Konstrukciju grupa", "Rindas ID"]
    _row(ws, 1, header, bold=True, fill=HEAD_FILL)
    r = 1
    rows = [x for x in est.rows if x.status != ST_DUP and x.group != "Terases (ārpus iekštelpu platības)"]
    for x in sorted(rows, key=lambda x: (x.group, x.article or "~", x.material)):
        r += 1
        _row(ws, r, [x.article or "", x.spec, x.material, x.unit, x.qty, x.waste_pct, x.order_qty, x.pack_size, x.unit_price, x.cost,
                     x.module, x.stage, x.status if x.qty is not None else "NAV IEVADĪTS", x.group, x.row_id],
             {5: QTY, 7: QTY, 8: '0.##', 9: MONEY, 10: MONEY})
    r += 2
    _put(ws, r, 1, "Saraksts ir AD budžeta stadijas provizorisks; " + est.procurement_status, bold=True)
    _widths(ws, [14, 30, 44, 10, 12, 10, 12, 10, 14, 14, 18, 18, 24, 26, 28])
    ws.freeze_panes = "D2"


def labour_sheet(ws, est, b):
    header = ["Rindas ID", "Konstrukciju grupa", "Darba operācija", "Ražošanas posms", "Modulis", "Apjoms", "Vienība", "Normstundas uz vienību",
              "Stundas", "Likme EUR/h (pilna pašizmaksa)", "Izmaksas EUR", "Statuss", "Pamats", "Avots"]
    _row(ws, 1, header, bold=True, fill=HEAD_FILL)
    r = 1
    for x in est.labour:
        r += 1
        _row(ws, r, [x.row_id, x.group, x.name, x.stage, x.module, x.qty, x.unit, x.norm_h, x.hours, x.rate, x.cost, x.status, x.basis, x.source],
             {6: QTY, 8: '0.000', 9: '0.00', 10: MONEY, 11: MONEY})
    r += 2
    _row(ws, r, ["", "", "Kopā", "", "", "", "", "", b["labour_hours"], "", b["labour_cost"]], {9: '0.00', 11: MONEY}, bold=True)
    _widths(ws, [28, 26, 40, 18, 16, 12, 10, 14, 10, 16, 14, 18, 40, 28])


def assumptions_sheet(ws, project, est, b):
    r = 1
    _put(ws, r, 1, "PIEŅĒMUMI UN NEIEKĻAUTAIS", bold=True)

    def block(title, lines):
        nonlocal r
        r += 2
        _put(ws, r, 1, title, bold=True, fill=HEAD_FILL)
        for line in lines or ["—"]:
            r += 1
            _put(ws, r, 1, str(line), wrap=True)
    block("Stadija", [STAGE_NOTE, NOT_FINAL])
    block("Rezerve", ["Rezerve % ir lietotāja regulējams provizorisks pieņēmums (materiāliem 10%; iekārtām, logiem/durvīm, sanitārtehnikai 0%). "
                      "CLT neto ģeometrija atšķiras no iepirkuma bruto/izgriezumiem; paneļu optimizācija nav realizēta."])
    block("Nepilnība (kāpēc budžets ir nepilns)", b["reasons"])
    block("Neiekļautie darbi", est.excluded)
    block("Brīdinājumi", est.warnings)
    block("Kļūdas", est.errors)
    block("Nepilnās sadaļas", [f"{g}: {m}" for g, items in est.missing.items() for m in items])
    block("Obligātās grupas bez datiem", est.uncovered)
    block("Nav apstiprinātas rindas", [f"{x.group}: {x.material}" for x in est.rows if x.approved is False and x.qty is not None][:80])
    ws.column_dimensions["A"].width = 140
