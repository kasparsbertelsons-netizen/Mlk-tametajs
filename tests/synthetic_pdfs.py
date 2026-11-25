"""Kopīgi palīgi sintētisku PDF veidošanai diagnostikas testos (nav tests; discover to neaiztiek)."""
from tools import synthetic_ad_pdf as gen

SECRET = "KLIENTS-SECRET"


def custom_pdf(draw, *, title="Floor plan", scale_text="Mērogs 1:50", metadata=None):
    """Vienas lapas PDF ar patvaļīgu zīmējumu `draw(sheet)`; `metadata` papildina PDF metadatus."""
    doc = gen._new_doc()
    if metadata:
        doc.set_metadata({**gen.METADATA, **metadata})
    sheet = gen.Sheet(doc, title=title, scale_text=scale_text)
    draw(sheet)
    sheet.finish()
    return gen._to_bytes(doc)


def sensitive_pdf():
    """12345 × 4321 modulis ar sensitīviem marķieriem visur, kur tie var nonākt: metadati, virsraksts, marķējumi."""
    def draw(sheet):
        x0, y0, x1, y1 = gen._module(sheet, 150, 260, 12345, 4321, 50, label=f"MODULIS {SECRET}-LABEL")
        sheet.text(150, 700, f"Virtuve {SECRET}-ROOM", size=10)                  # ārpus kontūras: statuss paliek tīrs
        sheet.text(60, 60, f"{SECRET}-FREE-TEXT PROJ-9981", size=9)
    return custom_pdf(draw, title=f"Floor plan {SECRET}-TITLE",
                      metadata={"title": f"SYNTHETIC {SECRET}-META-TITLE", "author": f"{SECRET}-AUTHOR",
                                "subject": f"SYNTHETIC {SECRET}-SUBJECT", "keywords": f"synthetic {SECRET}-KW"})


def plan_view_pdf(length_mm=12000, width_mm=4000):
    """Grīdas plāns, kura virsrakstā NAV vārdu "Floor plan": automātiskais klasifikators to neatradīs."""
    def draw(sheet):
        gen._module(sheet, 150, 260, length_mm, width_mm, 50)
    return custom_pdf(draw, title="Plan view")
