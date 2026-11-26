"""Sintētisks AD ĒKAS PDF (visas ģeometrijas kategorijas) un sintētiska Moneo kontroltāme (Issue #16).

Visi dati ir IZDOMĀTI; tas NAV reāls projekts, rasējums vai uzņēmuma dati. Ģenerēšana ir deterministiska:

    python -m tools.synthetic_ad_building --out samples/ad_building

PDF lapas: 1 titullapa; 2 «Floor plan» (divi moduļi ar izmēru norādēm, telpu eksplikācija, atveru marķējumi, fasādes kontūras teksts);
3 logu/durvju specifikācija (ar dublikātu un rindu bez atrašanās vietas); 4 sienu eksplikācija (posmi, CLT biezumi, zelmiņi, telpas augstums);
5 «Roof plan» (divas slīpnes, jumta logi); 6 konstrukciju tipi (slāņu saraksti, vairākas latojuma kārtas).
"""
import argparse
import io
import pathlib

import pymupdf

from tools import synthetic_ad_pdf as base

MM = base.mm

FLOOR_TEXT = [
    "Telpu eksplikācija:",
    "Dzīvojamā istaba 30.0 m2",
    "Virtuve 14.0 m2",
    "Guļamistaba 12.0 m2",
    "Vannasistaba 8.0 m2",
    "Gaitenis 8.0 m2",
    "Terase 12.0 m2",
    "Fasādes kontūra 20240 x 4240",
]
OPENING_ROWS = [
    "L1 1200 x 1500 3 gab. ārējais posms N",
    "L1 1200 x 1500 3 gab. ārējais posms S",
    "L1 1200 x 1500 3 gab. ārējais posms N",            # dublikāts: nedrīkst atskaitīt divreiz
    "D1 1000 x 2100 1 gab. ārējais posms S",
    "D2 800 x 2100 1 gab. iekšējais posms I1",
    "D2 800 x 2100 1 gab. iekšējais posms I2",
    "D2 800 x 2100 1 gab. iekšējais posms I3",
    "JL1 780 x 1400 2 gab. jumta posms Slīpne A",
    "D3 900 x 2100 1 gab.",                            # atrašanās vieta nav norādīta: netiek pārnesta
]
WALL_ROWS = [
    "Telpas augstums 2700 mm",
    "Siena N: ārējā, tips ĀS1, L=20.0 m, H=2700 mm, CLT 100 mm",
    "Siena S: ārējā, tips ĀS1, L=20.0 m, H=2700 mm, CLT 100 mm",
    "Siena A: ārējā, tips ĀS2, L=4.0 m, H=2700 mm, CLT 140 mm",
    "Siena B: ārējā, tips ĀS2, L=4.0 m, H=2700 mm, CLT 140 mm",
    "Siena I1: iekšējā, tips IS1, L=4.0 m, H=2700 mm",
    "Siena I2: iekšējā, tips IS1, L=3.0 m, H=2700 mm",
    "Siena I3: iekšējā, tips IS1, L=2.5 m, H=2700 mm",
    "Zelmiņš A: tips ĀS2, pamats=4.0 m, augstums=1.5 m, CLT 140 mm",
    "Zelmiņš B: tips ĀS2, pamats=4.0 m, augstums=1.5 m, CLT 140 mm",
    "Siena X: tips ĀS1, H=2700 mm",                    # nepilna: garums un veids nav nolasāmi
]
ROOF_ROWS = [
    "Jumta slīpums 20°",
    "Jumta slīpne A: garums = 24.0 m, horizontālā projekcija = 2.5 m, leņķis = 20°, tips JK1, CLT 120 mm",
    "Jumta slīpne B: garums = 24.0 m, horizontālā projekcija = 2.5 m, leņķis = 20°, tips JK2",
]
TYPE_ROWS = [
    "Konstrukciju tipi:",
    "ĀS1 Ārsiena: fasādes dēlis 20 mm; latojums 50 mm c/c 600; latojums 50 mm c/c 400; vēja plēve; siltinājums 150 mm; CLT 100 mm; "
    "instalāciju latojums 50 mm c/c 600; ģipškartons 12.5 mm; skrūves",
    "ĀS2 Ārsiena: fasādes dēlis 20 mm; latojums 50 mm c/c 600; vēja plēve; siltinājums 150 mm; CLT 140 mm; ģipškartons 12.5 mm",
    "IS1 Iekšsiena: ģipškartons 12.5 mm abās pusēs; CLT 80 mm",
    "JK1 Jumts: jumta segums; latojums 50 mm c/c 350; membrāna; siltinājums 200 mm; CLT 120 mm",
    "JK2 Jumts: jumta segums; latojums 50 mm c/c 350; membrāna; siltinājums 200 mm; CLT 100 mm",
    "GR1 Grīda: grīdas segums; PIR 200 mm",
]


def _text_page(doc, title, lines, size=9, start=90, step=18):
    page = doc.new_page(width=base.PAGE_W, height=base.PAGE_H)
    writer = pymupdf.TextWriter(page.rect)
    writer.append((60, 60), title, font=base.FONT, fontsize=14)
    for i, line in enumerate(lines):
        writer.append((60, start + i * step), line, font=base.FONT, fontsize=size)
    writer.append((60, base.PAGE_H - 40), base.MARK, font=base.FONT, fontsize=7)
    writer.write_text(page)
    return page


def build_ad_building_pdf(include_unclear=True) -> bytes:
    doc = base._new_doc()
    _text_page(doc, "SINTĒTISKS AD PARAUGS — pilna ēka", ["Titullapa (nav reāls projekts).", "Arhitektūras daļa, sintētisks piemērs."], start=100)
    # 2. grīdas plāns
    sheet = base.Sheet(doc, title="Floor plan", scale_text="Mērogs 1:100")
    _x0, y0, x1, _y1 = base._module(sheet, 150, 250, 12000, 4000, 100, label="MODULIS M1", dim_h_offset=-30, dim_v_offset=-45)
    base._module(sheet, x1 + 30, 250, 8000, 4000, 100, label="MODULIS M2", dim_h_offset=-30, dim_v_offset=45, label_at=(x1 + 60, 330))
    for i, line in enumerate(FLOOR_TEXT):
        sheet.text(150, 480 + i * 15, line, size=9)
    tags = ["L1"] * 6 + ["D1"] + ["D2"] * 3
    for i, tag in enumerate(tags):
        sheet.text(200 + (i // 5) * 70, 268 + (i % 5) * 16, tag, size=7)                      # katrs marķējums savā rindā (nesaplūst)
    sheet.finish()
    _text_page(doc, "Logu un durvju specifikācija", OPENING_ROWS if include_unclear else OPENING_ROWS[:-1])
    _text_page(doc, "Sienu eksplikācija", WALL_ROWS if include_unclear else WALL_ROWS[:-1])
    roof = base.Sheet(doc, title="Roof plan", scale_text="Mērogs 1:100")
    for i, line in enumerate(ROOF_ROWS):
        roof.text(60, 120 + i * 18, line, size=9)
    roof.finish()
    _text_page(doc, "Konstrukciju tipi", TYPE_ROWS, size=8)
    return base._to_bytes(doc)


def build_identical_modules_pdf() -> bytes:
    """Divi FIZISKI atšķirīgi moduļi ar VIENĀDIEM izmēriem (12000 × 4000), novietoti viens virs otra ar skaidri marķētu robežu (Issue #16 korekcija)."""
    doc = base._new_doc()
    sheet = base.Sheet(doc, title="Floor plan", scale_text="Mērogs 1:50")
    ax0, ay0, ax1, ay1 = base._module(sheet, 150, 230, 12000, 4000, 50, dim_h_offset=-30, label="MODULIS M1")
    base._module(sheet, 150, ay1, 12000, 4000, 50, label="MODULIS M2", as_polyline=True, dim_h_offset=30, label_at=(150 + MM(12000, 50) * 0.62, ay1 + 50))
    sheet.line((ax0, ay1), (ax1, ay1), width=1.2, dashes="[6 3] 0")
    sheet.text(ax0 + 60, ay1 - 6, "MODEĻU ROBEŽA", size=8)
    sheet.finish()
    return base._to_bytes(doc)


def build_revit_style_pdf() -> bytes:
    """SINTĒTISKS fragments, tuvs Revit lapu notācijai: telpu tabula Nr./Name/Area/Notes, «Total Building Area on Ground», logu marķējumi W-n/RW-n ar
    izmēriem «platums x augstums mm» (skaits — no plāna marķējumiem), jumta leņķis grādos. Nav reāls rasējums."""
    doc = base._new_doc()
    sheet = base.Sheet(doc, title="Floor plan", scale_text="Scale 1:100")
    rows = ["Nr. Name Area Notes", "1 Kitchen 14.0 m2", "2 Living room 30.0 m2 open plan", "3 Bedroom 12.0 m2", "4 Terrace 12.0 m2",
            "Total Building Area on Ground 80.0 m2"]
    for i, line in enumerate(rows):
        sheet.text(150, 300 + i * 16, line, size=9)
    for i, tag in enumerate(["W-1", "W-1", "W-1", "RW-1"]):
        sheet.text(520, 430 + i * 20, tag, size=7)
    sheet.finish()
    _text_page(doc, "Window schedule", ["W-1 1200 x 1500 mm", "RW-1 780 x 1400 mm", "W-2 900 x 1200 mm", "Roof angle 20°"])
    return base._to_bytes(doc)


# --- sintētiska Moneo kontroltāme ---------------------------------------------------------------------------------------
HEADER = ["Posms", "Artikuls", "Nosaukums", "Mērv.", "Plānotais daudzums", "Faktiskais daudzums", "Plānotā cena", "Faktiskā cena",
          "Plānotā summa", "Faktiskā summa", "Veids", "Rindas tips"]
# (posms, artikuls, nosaukums, mērv., plāna daudz., fakta daudz., plāna cena, fakta cena, veids)
CONTROL_ITEMS = [
    ("Karkasa ražošana", "DEMO-CLT-100", "CLT panelis 100 mm", "m³", 17.5, 18.1, 520.0, 535.0, "Materiāls"),
    ("Karkasa ražošana", "DEMO-CLT-140", "CLT panelis 140 mm", "m³", 4.2, 4.2, 560.0, 560.0, "Materiāls"),
    ("Karkasa ražošana", "DEMO-LATA-50", "Latas 50×50", "m", 1050.0, 1180.0, 1.4, 1.45, "Materiāls"),
    ("Apdare un montāža", "DEMO-GKL-12", "Ģipškartons 12.5 mm", "m²", 180.0, 170.0, 6.0, 6.3, "Materiāls"),
    ("Apdare un montāža", "DEMO-SKR-6x80", "Skrūve 6×80", "gab.", 800.0, 1000.0, 0.12, 0.12, "Materiāls"),
    ("Apdare un montāža", "DEMO-MEP-AP", "MEP apakšuzņēmējs (darbs)", "kompl.", 1.0, 1.0, 4000.0, 4350.0, "Ārpakalpojums"),
    ("Apdare un montāža", "DEMO-NAV-PROGNOZE", "Papildu palīgmateriāls", "gab.", 10.0, 12.0, 5.0, 5.0, "Materiāls"),
    ("Apdare un montāža", "DEMO-VEJA", "Vēja membrāna (eksportā nav mērvienības)", None, 128.0, 128.0, 2.1, 2.2, "Materiāls"),
]
CONTROL_HOURS = [("Karkasa ražošana", "Stundas — karkasa ražošana", 120.0, 130.0), ("Apdare un montāža", "Stundas — apdare un montāža", 280.0, 270.0),
                 ("Loģistika", "Stundas — loģistika (nav prognozē)", 10.0, 14.0)]


def control_rows(*, with_totals=True, double_count_trap=True):
    """Kontroltāmes rindas: posma virsraksti, artikulu rindas, grupas/posma kopsummas un gala kopsumma, stundu rindas."""
    rows = [HEADER]
    grand = {"ps": 0.0, "as": 0.0}
    stages = []
    for item in CONTROL_ITEMS:
        if item[0] not in stages:
            stages.append(item[0])
    for stage in stages:
        rows.append([f"Posms: {stage}", None, None, None, None, None, None, None, None, None, None, None])
        ps = as_ = 0.0
        for st, code, name, unit, pq, aq, pp, ap, kind in [i for i in CONTROL_ITEMS if i[0] == stage]:
            psum, asum = round(pq * pp, 2), round(aq * ap, 2)
            ps, as_ = ps + psum, as_ + asum
            rows.append([stage, code, name, unit, pq, aq, pp, ap, psum, asum, kind, "Artikuls"])
        if with_totals:
            rows.append([stage, None, "Grupas kopsumma materiāli un ārpakalpojumi", None, None, None, None, None, round(ps, 2), round(as_, 2), None, "Grupa"])
            rows.append([stage, None, "Posma kopsumma", None, None, None, None, None, round(ps, 2), round(as_, 2), None, "Posms"])
        grand["ps"] += ps
        grand["as"] += as_
    for stage, name, plan_h, act_h in CONTROL_HOURS:
        rows.append([stage, None, name, "h", plan_h, act_h, None, None, None, None, "Stundas", "Stundas"])
    if with_totals:
        rows.append([None, None, "Kopā", None, None, None, None, None, round(grand["ps"], 2), round(grand["as"], 2), None, "Kopā"])
    return rows


def build_control_xlsx(**kw) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Kontroltāme"
    for row in control_rows(**kw):
        ws.append(row)
    ws["A1"].comment = None
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_control_csv(**kw) -> bytes:
    import csv
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    for row in control_rows(**kw):
        writer.writerow(["" if v is None else str(v).replace(".", ",") if isinstance(v, float) else v for v in row])
    return ("﻿" + out.getvalue()).encode("utf-8")


# --- sintētiska Moneo vispārīgā pārskata STRUKTŪRA (kolonnu burti kā reālajā izkārtojumā; visas vērtības izdomātas) ---------------------------------
# (posma kods, posma apraksts, [(grupas kods, grupas nosaukums, [(artikuls, apraksts, plāna daudz., plāna cena, fakta daudz., fakta cena), ...]), ...])
MONEO_STAGES = [
    ("S01", "Karkasa ražošana", [("G10", "CLT paneļi", [("DEMO-CLT-100", "CLT panelis 100 mm", 9.0, 520.0, 9.6, 535.0),
                                                      ("DEMO-CLT-140", "CLT panelis 140 mm", 3.0, 560.0, 3.0, 560.0)]),
                                ("G20", "Latas", [("DEMO-LATA-50", "Latas 50×50", 600.0, 1.4, 700.0, 1.45)])]),
    ("S02", "Apdare un montāža", [("G10", "CLT paneļi", [("DEMO-CLT-100", "CLT panelis 100 mm", 8.5, 520.0, 8.5, 535.0)]),       # tas pats artikuls 2. posmā
                                   ("G30", "Plāksnes un palīgmateriāli", [("DEMO-GKL-12", "Ģipškartons 12.5 mm", 180.0, 6.0, 170.0, 6.3),
                                                                         ("DEMO-SKR-6x80", "Skrūve 6×80", 800.0, 0.12, 1000.0, 0.12),
                                                                         ("00123", "Palīgmateriāls (nav prognozē)", 10.0, 5.0, 12.0, 5.0)])]),
    ("S01", "Karkasa ražošana", [("G20", "Latas", [("DEMO-LATA-50", "Latas 50×50", 450.0, 1.4, 480.0, 1.45)])]),                     # posms atkārtojas
]
MONEO_HEADER_ROWS = [{"J": "Budžets", "P": "Budžets", "S": "Faktiskais", "Z": "Faktiskā"},
                     {"J": "Daudzums", "M": "Cena", "P": "Summa", "S": "daudzums", "W": "Cena", "Z": "summa"}]
HOURS_OPS = [("CLT ārsienu montāža un apstrāde", 70.0, 61.0), ("Grīdas rāmja izgatavošana", 50.0, 48.0), ("CLT iekšsienu montāža", 9.0, 8.0),
             ("Elektroinstalācija", 62.0, 60.0), ("Loģistika", 14.0, 10.0), ("Elektroinstalācija", 4.0, 0.0)]       # atkārtota operācija; Loģistika nav prognozē


def moneo_rows():
    """Rindas kā {kolonnas burts: vērtība}. Tukšās rindas ir ievietotas tīši (jāignorē)."""
    rows = [{"B": "PRJ-SINT", "F": "Sintētisks projekts (DEMO)"}, *MONEO_HEADER_ROWS, {}]
    for code, desc, groups in MONEO_STAGES:
        rows.append({"B": code, "F": desc})
        stage_plan = stage_act = 0.0
        for gcode, gname, items in groups:
            gp = round(sum(round(pq * pp, 2) for _c, _d, pq, pp, _aq, _ap in items), 2)
            ga = round(sum(round(aq * ap, 2) for _c, _d, _pq, _pp, aq, ap in items), 2)
            rows.append({"D": gcode, "G": gname, "O": gp, "X": ga})
            for art, adesc, pq, pp, aq, ap in items:
                rows.append({"E": art, "H": adesc, "I": pq, "K": pp, "N": round(pq * pp, 2), "Q": aq, "T": ap, "V": round(aq * ap, 2)})
            stage_plan += gp
            stage_act += ga
            rows.append({})
        rows.append({"F": "<bez koda>", "P": round(stage_plan, 2), "Z": round(stage_act, 2)})
        rows.append({"J": "Kopā", "P": round(stage_plan, 2), "Z": round(stage_act, 2)})
        rows.append({})
    return rows


def build_moneo_report_xlsx(tamper_stage_total=False) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pārskats"
    for i, row in enumerate(moneo_rows(), 1):
        for letter, value in row.items():
            cell = ws[f"{letter}{i}"]
            cell.value = value
            if isinstance(value, str):
                cell.data_type = "s"
        if tamper_stage_total and row.get("F") == "<bez koda>" and "Z" in row:
            ws[f"Z{i}"].value = row["Z"] + 100.0
            tamper_stage_total = False
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_hours_xlsx(tamper_total=False) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Stundas"
    ws["A1"], ws["B1"] = "Darbība", "Stundas"
    ws["B2"], ws["C2"] = "Reāli", "Plānots"
    r = 4                                                  # 3. rinda tukša
    for name, actual, plan in HOURS_OPS:
        ws[f"A{r}"], ws[f"B{r}"], ws[f"C{r}"] = name, actual, plan
        r += 1
        if name == "Grīdas rāmja izgatavošana":
            r += 1                                         # tukša rinda starp operācijām
    ws[f"A{r}"] = "Kopā:"
    ws[f"B{r}"] = sum(a for _n, a, _p in HOURS_OPS) + (50.0 if tamper_total else 0.0)
    ws[f"C{r}"] = sum(p for _n, _a, p in HOURS_OPS)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


SAMPLES = {"AD_sintetiska_eka.pdf": build_ad_building_pdf, "kontroltame_sintetiska.xlsx": build_control_xlsx,
           "kontroltame_sintetiska.csv": build_control_csv, "moneo_parskats_sintetisks.xlsx": build_moneo_report_xlsx,
           "stundas_sintetiskas.xlsx": build_hours_xlsx}


def write_samples(out_dir):
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, builder in SAMPLES.items():
        path = out / name
        path.write_bytes(builder())
        written.append(path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ģenerē sintētisku AD ēkas PDF un kontroltāmi.")
    parser.add_argument("--out", default="samples/ad_building")
    args = parser.parse_args(argv)
    for path in write_samples(args.out):
        print(f"{path}  ({path.stat().st_size} B)")


if __name__ == "__main__":
    main()
