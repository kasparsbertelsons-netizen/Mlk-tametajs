"""Sintētisku AD vektoru PDF ģenerators (Issue #6).

Veido PDF ar REĀLI ZĪMĒTĀM līnijām un kontūrām (PyMuPDF), izmēru līnijām ar izvilkuma
līnijām un izmēru tekstu; nevis tikai tekstu. Visi dati ir izdomāti: tie NAV reāli klientu
rasējumi un nesatur reālus projekta datus. Katrs PDF ir marķēts "SINTĒTISKS PARAUGS".

Ģenerēšana ir deterministiska (bez datumiem un nejaušiem ID), tāpēc repozitorijā
glabātie paraugi ir reproducējami:

    python -m tools.synthetic_ad_pdf --out samples/ad_vector

Mērogs: 1 pt = 25,4 / 72 mm uz papīra; reālais izmērs = pt · 25,4 / 72 · mērogs.
"""
import argparse
import pathlib

import pymupdf

PT_PER_MM = 72 / 25.4
PAGE_W, PAGE_H = 1191, 842          # A3 ainava, pt
MARK = "SINTĒTISKS PARAUGS / SYNTHETIC SAMPLE: nav reāls rasējums"
FONT = pymupdf.Font("helv")
METADATA = {"title": "SYNTHETIC AD vector sample", "author": "synthetic generator",
            "producer": "tools/synthetic_ad_pdf.py", "creator": "tools/synthetic_ad_pdf.py",
            "creationDate": "", "modDate": "", "subject": "SYNTHETIC: not a real drawing",
            "keywords": "synthetic"}


def mm(real_mm, scale):
    """Reālie mm → pt uz lapas, pie mēroga 1:scale."""
    return real_mm / scale * PT_PER_MM


class Sheet:
    """Viena rasējuma lapa ar zīmēšanas palīgfunkcijām."""

    GAP = 2.0       # sprauga starp kontūru un izvilkuma līniju

    def __init__(self, doc, *, kind="plan", title=None, scale_text=None, sheet_no="AD-07"):
        self.page = doc.new_page(width=PAGE_W, height=PAGE_H)
        self.writer = pymupdf.TextWriter(self.page.rect)
        if kind == "plan":
            self.page.draw_rect(pymupdf.Rect(20, 20, PAGE_W - 20, PAGE_H - 20), width=1.0)   # lapas rāmis
            block = pymupdf.Rect(880, 745, PAGE_W - 20, PAGE_H - 20)
            self.page.draw_rect(block, width=0.7)                                           # nosaukuma bloks
            self.text(890, 768, f"{sheet_no}  {title}", size=12)
            if scale_text:
                self.text(890, 788, scale_text, size=11)
            self.text(890, 810, MARK, size=6.5)
        else:
            self.text(60, 80, MARK, size=8)

    # --- pamatelementi -------------------------------------------------
    def text(self, x, y, string, size=9):
        self.writer.append((x, y), string, font=FONT, fontsize=size)

    def number_v(self, x, y_start, string, size=9):
        """Vertikāls (90°) cipars; y_start ir teksta sākums (apakšā)."""
        self.page.insert_text((x, y_start), string, fontsize=size, rotate=90)

    def line(self, p1, p2, width=0.5, dashes=None):
        self.page.draw_line(p1, p2, width=width, dashes=dashes)

    def rect(self, x0, y0, x1, y1, width=2.0):
        self.page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), width=width)

    def polygon(self, points, width=2.0, close_path=True):
        self.page.draw_polyline(points, width=width, closePath=close_path)

    # --- izmēru norādes ------------------------------------------------
    def dim_h(self, x0, x1, y_ref, offset, label, size=9):
        """Horizontāla izmēru norāde: izvilkuma līnijas, izmēru līnija ar kritumiem un teksts."""
        sign = 1 if offset > 0 else -1
        y = y_ref + offset
        for x in (x0, x1):
            self.line((x, y_ref + sign * self.GAP), (x, y + sign * 3))          # izvilkuma līnija
            self.line((x - 2.5, y + 2.5), (x + 2.5, y - 2.5), width=0.8)        # kritums
        self.line((x0, y), (x1, y))                                              # izmēru līnija
        width = pymupdf.get_text_length(label, fontname="helv", fontsize=size)
        self.page.insert_text(((x0 + x1) / 2 - width / 2, y - 2.5), label, fontsize=size)

    def dim_v(self, y0, y1, x_ref, offset, label, size=9):
        """Vertikāla izmēru norāde; teksts pagriezts par 90°."""
        sign = 1 if offset > 0 else -1
        x = x_ref + offset
        for y in (y0, y1):
            self.line((x_ref + sign * self.GAP, y), (x + sign * 3, y))
            self.line((x - 2.5, y + 2.5), (x + 2.5, y - 2.5), width=0.8)
        self.line((x, y0), (x, y1))
        width = pymupdf.get_text_length(label, fontname="helv", fontsize=size)
        self.number_v(x - 2.5, (y0 + y1) / 2 + width / 2, label, size)

    def finish(self):
        self.writer.write_text(self.page)
        return self.page


def _new_doc():
    doc = pymupdf.open()
    doc.set_metadata(METADATA)
    return doc


def _to_bytes(doc):
    data = doc.tobytes(no_new_id=True, deflate=False, garbage=0)
    doc.close()
    return data


def _cover(doc):
    sheet = Sheet(doc, kind="cover")
    sheet.text(60, 120, "Drawing list", size=14)
    sheet.text(60, 150, "1  Floor plan", size=11)
    sheet.text(60, 170, "2  Roof plan", size=11)
    sheet.text(60, 200, "Project number 15000", size=10)
    sheet.finish()


def _module(sheet, x0, y0, length_mm, width_mm, scale, *, label="MODULIS M1", vertical=False,
            as_polyline=False, dim_h_offset=45, dim_v_offset=-45, dims=True, label_at=None):
    """Taisnstūra moduļa kontūra ar abām izmēru norādēm. Atgriež (x0, y0, x1, y1) pt."""
    w_pt = mm(width_mm if vertical else length_mm, scale)
    h_pt = mm(length_mm if vertical else width_mm, scale)
    x1, y1 = x0 + w_pt, y0 + h_pt
    if as_polyline:
        sheet.polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], width=2.0)
    else:
        sheet.rect(x0, y0, x1, y1, width=2.0)
    if dims:
        horizontal_mm = width_mm if vertical else length_mm
        vertical_mm = length_mm if vertical else width_mm
        sheet.dim_h(x0, x1, y1 if dim_h_offset > 0 else y0, dim_h_offset, str(horizontal_mm))
        sheet.dim_v(y0, y1, x0, dim_v_offset, str(vertical_mm))
    if label:
        lx, ly = label_at or (x0 + w_pt * 0.62, y0 + h_pt * 0.22)
        sheet.text(lx, ly, label, size=12)
    return x0, y0, x1, y1


def build_sample_01(module_label=True):
    """12000 × 4000, 1:50; telpa 3500 (maldinošs kandidāts), terase; titullapa un jumta lapa ar pārkari."""
    doc = _new_doc()
    _cover(doc)

    sheet = Sheet(doc, title="Floor plan", scale_text="Mērogs 1:50")
    x0, y0, x1, y1 = _module(sheet, 150, 260, 12000, 4000, 50,
                             label="MODULIS M1" if module_label else None)
    # telpa moduļa iekšpusē: 3500 × 2500 mm, ar savu izmēru norādi (maldinošs kandidāts)
    rx0, ry0 = x0 + 25, y0 + 30
    rx1, ry1 = rx0 + mm(3500, 50), ry0 + mm(2500, 50)
    sheet.rect(rx0, ry0, rx1, ry1, width=1.0)
    sheet.text(rx0 + 12, ry0 + 40, "Virtuve", size=10)
    sheet.text(rx0 + 12, ry0 + 55, "8.75 m2", size=10)
    sheet.dim_h(rx0, rx1, ry1, 18, "3500")
    # terase: atsevišķa kontūra ārpus moduļa, ar savu izmēru norādi
    tx0, ty0 = x1 + 40, 290
    tx1, ty1 = tx0 + mm(4500, 50), ty0 + mm(2000, 50)
    sheet.rect(tx0, ty0, tx1, ty1, width=1.0)
    sheet.text(tx0 + 14, ty0 + 40, "Terase", size=10)
    sheet.dim_h(tx0, tx1, ty0, -22, "4500")
    sheet.finish()

    roof = Sheet(doc, title="Roof plan", scale_text="Mērogs 1:50", sheet_no="AD-08")
    _module(roof, 130, 240, 12600, 4600, 50, label=None)     # jumts ar pārkari: 12600 × 4600
    roof.finish()
    return _to_bytes(doc)


def build_sample_02():
    """12100 × 3600 citā mērogā (1:100)."""
    doc = _new_doc()
    sheet = Sheet(doc, title="Floor plan", scale_text="Mērogs 1:100")
    _module(sheet, 200, 300, 12100, 3600, 100, dim_h_offset=40, dim_v_offset=-40)
    sheet.finish()
    return _to_bytes(doc)


def build_sample_03(separator=True, labels=True):
    """Divi blakus esoši moduļi (12000 × 4000 un 12000 × 3600) ar vai bez skaidri marķētas robežas."""
    doc = _new_doc()
    sheet = Sheet(doc, title="Floor plan", scale_text="Mērogs 1:50")
    ax0, ay0, ax1, ay1 = _module(sheet, 150, 230, 12000, 4000, 50, dim_h_offset=-30,
                                 label="MODULIS M1" if labels else None)
    # B modulis zīmēts kā slēgta polilīnija; tā augšmala sakrīt ar A apakšmalu
    _module(sheet, 150, ay1, 12000, 3600, 50, label="MODULIS M2" if labels else None,
            as_polyline=True, dim_h_offset=30, label_at=(150 + mm(12000, 50) * 0.62, ay1 + 50))
    if separator:
        sheet.line((ax0, ay1), (ax1, ay1), width=1.2, dashes="[6 3] 0")
        sheet.text(ax0 + 60, ay1 - 6, "MODEĻU ROBEŽA", size=8)
    sheet.finish()
    return _to_bytes(doc)


def build_sample_04():
    """L-veida kontūra (neskaidra): viens slēgts ortogonāls poligons ar 6 virsotnēm."""
    doc = _new_doc()
    sheet = Sheet(doc, title="Floor plan", scale_text="Mērogs 1:50")
    x0, y0 = 150, 200
    pts = [(x0, y0), (x0 + mm(12000, 50), y0), (x0 + mm(12000, 50), y0 + mm(4000, 50)),
           (x0 + mm(4000, 50), y0 + mm(4000, 50)), (x0 + mm(4000, 50), y0 + mm(7000, 50)),
           (x0, y0 + mm(7000, 50))]
    sheet.polygon(pts, width=2.0)
    sheet.dim_h(x0, x0 + mm(12000, 50), y0, -30, "12000")
    sheet.dim_v(y0, y0 + mm(7000, 50), x0, -45, "7000")
    sheet.text(x0 + 300, y0 + 40, "MODULIS M1", size=12)
    sheet.finish()
    return _to_bytes(doc)


def build_sample_05():
    """Trūkstošs mērogs: virsrakstā nav "1:xx"; ģeometrija ir 1:50."""
    doc = _new_doc()
    sheet = Sheet(doc, title="Floor plan", scale_text=None)
    _module(sheet, 150, 260, 12000, 4000, 50)
    sheet.finish()
    return _to_bytes(doc)


def build_sample_06():
    """Pretrunīgs mērogs: virsrakstā 1:100, bet ģeometrija un izmēri atbilst 1:50."""
    doc = _new_doc()
    sheet = Sheet(doc, title="Floor plan", scale_text="Mērogs 1:100")
    _module(sheet, 150, 260, 12000, 4000, 50)
    sheet.finish()
    return _to_bytes(doc)


def build_sample_07():
    """1. lapa: rotēta lapa (90°); 2. lapa: modulis zīmēts vertikāli (garā mala augšup)."""
    doc = _new_doc()
    first = Sheet(doc, title="Floor plan", scale_text="Mērogs 1:50")
    _module(first, 150, 260, 12000, 4000, 50)
    page = first.finish()
    page.set_rotation(90)
    second = Sheet(doc, title="Floor plan", scale_text="Mērogs 1:50", sheet_no="AD-07b")
    _module(second, 320, 100, 12000, 4000, 50, vertical=True, dim_h_offset=30, dim_v_offset=-45)
    second.finish()
    return _to_bytes(doc)


def build_sample_08():
    """Lapas bez vektoru ģeometrijas: tikai teksts un rastra attēls."""
    doc = _new_doc()
    text_only = doc.new_page(width=PAGE_W, height=PAGE_H)
    writer = pymupdf.TextWriter(text_only.rect)
    for number, line in enumerate(["AD-07  Floor plan  Mērogs 1:50", "12000", "4000", MARK]):
        writer.append((60, 80 + 20 * number), line, font=FONT, fontsize=11)
    writer.write_text(text_only)
    raster = doc.new_page(width=PAGE_W, height=PAGE_H)
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 120), False)
    pixmap.clear_with(235)
    raster.insert_image(pymupdf.Rect(150, 260, 830, 487), pixmap=pixmap)
    writer = pymupdf.TextWriter(raster.rect)
    writer.append((890, 768), "AD-07  Floor plan", font=FONT, fontsize=12)
    writer.append((890, 788), "Mērogs 1:50", font=FONT, fontsize=11)
    writer.append((890, 810), MARK, font=FONT, fontsize=6.5)
    writer.write_text(raster)
    return _to_bytes(doc)


def build_sample_09(inner_label=False):
    """Fasādes kontūra (12400 × 4400) ar iekšēju kontūru (12000 × 4000); pēc noklusējuma bez moduļa marķējuma."""
    doc = _new_doc()
    sheet = Sheet(doc, title="Floor plan", scale_text="Mērogs 1:50")
    ox0, oy0 = 130, 240
    ow, oh = mm(12400, 50), mm(4400, 50)
    sheet.rect(ox0, oy0, ox0 + ow, oy0 + oh, width=2.0)
    ix0, iy0 = ox0 + mm(200, 50), oy0 + mm(200, 50)
    iw, ih = mm(12000, 50), mm(4000, 50)
    sheet.rect(ix0, iy0, ix0 + iw, iy0 + ih, width=1.4)
    sheet.dim_h(ox0, ox0 + ow, oy0 + oh, 40, "12400")
    sheet.dim_v(oy0, oy0 + oh, ox0, -62, "4400")
    sheet.dim_h(ix0, ix0 + iw, iy0, -38, "12000")
    sheet.dim_v(iy0, iy0 + ih, ix0, -30, "4000")
    if inner_label:
        sheet.text(ix0 + 400, iy0 + 60, "MODULIS M1", size=12)
    sheet.finish()
    return _to_bytes(doc)


# Repozitorijā glabātie paraugi: faila nosaukums → ģenerators
SAMPLES = {
    "ad_vector_01_12000x4000_1to50.pdf": build_sample_01,
    "ad_vector_02_12100x3600_1to100.pdf": build_sample_02,
    "ad_vector_03_two_modules_with_boundary.pdf": build_sample_03,
    "ad_vector_04_L_shape_unclear.pdf": build_sample_04,
    "ad_vector_05_scale_missing.pdf": build_sample_05,
    "ad_vector_06_scale_conflict.pdf": build_sample_06,
    "ad_vector_07_rotated_and_vertical.pdf": build_sample_07,
    "ad_vector_08_no_vector_geometry.pdf": build_sample_08,
    "ad_vector_09_facade_and_inner_contour.pdf": build_sample_09,
}


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
    parser = argparse.ArgumentParser(description="Ģenerē sintētiskus AD vektoru PDF paraugus.")
    parser.add_argument("--out", default="samples/ad_vector", help="izvades mape")
    args = parser.parse_args(argv)
    for path in write_samples(args.out):
        print(f"{path}  ({path.stat().st_size} B)")


if __name__ == "__main__":
    main()
