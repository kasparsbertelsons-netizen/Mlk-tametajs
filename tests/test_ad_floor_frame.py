"""AD režīma grīdas rāmja regresijas testi (Issue #2).

Testē `app.py` tādu, kāds tas ir: sintētisks PDF tiek "augšupielādēts" caur
Streamlit AppTest. Sagaidāmās vērtības ir aprēķinātas ar roku, neizmantojot
testējamo kodu (skat. docs/ISSUE2_FLOOR_FRAME_AUDIT.md).

Testi ar @expectedFailure fiksē konstatētās neatbilstības. Tie NEDRĪKST tikt
"salaboti", mainot testu; ja kods tiek labots pēc saskaņošanas, dekorators
jānoņem.
"""
import unittest
from pathlib import Path

APP = str(Path(__file__).resolve().parent.parent / "app.py")
AD_MODE = "AD — prognozēt rāmi"
PD_MODE = "PD — nolasīt specifikāciju"
NO_DIMENSIONS = "No plāna nav droši nosakāmi Rebel moduļa gabarīti"

try:
    import pymupdf
    from streamlit.testing.v1 import AppTest
    from streamlit.testing.v1.element_tree import FileUploader
    HAVE_APPTEST = hasattr(FileUploader, "upload")
except ImportError:  # pragma: no cover
    HAVE_APPTEST = False


def make_pdf(pages):
    """Sintētisks PDF: katrs teksta bloks ir viena lapa. Nav klientu datu."""
    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((50, 72), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def run_app(pages, mode=AD_MODE):
    at = AppTest.from_file(APP, default_timeout=60).run()
    if mode != AD_MODE:
        at.radio[0].set_value(mode).run()
    at.file_uploader[0].upload("synthetic.pdf", make_pdf(pages), "application/pdf").run()
    assert not at.exception, at.exception
    return at


def ad_table(at):
    """AD siju tabula kā {Elements: rinda}."""
    frame = at.dataframe[0].value
    return {row["Elements"]: row for row in frame.to_dict("records")}


def errors(at):
    return [e.value for e in at.error]


@unittest.skipUnless(HAVE_APPTEST, "Nepieciešams streamlit ar AppTest failu augšupielādi un PyMuPDF")
class TestADFloorFrameSynthetic(unittest.TestCase):
    """Taisnstūra modulis 12000 × 4000 mm, sintētisks."""

    @classmethod
    def setUpClass(cls):
        cls.at = run_app([
            "Cover sheet",
            "Floor plan 1:50\n12000\n4000\nKitchen 12.5 m2\nWindow 1200x1500",
        ])
        cls.table = ad_table(cls.at)

    def test_dimensions_detected(self):
        metrics = [m.value for m in self.at.metric]
        self.assertEqual(metrics[:3], ["12000 mm", "4000 mm", "600 mm"])
        self.assertEqual(errors(self.at), [])

    def test_long_perimeter_beams(self):
        # 2 gab. 200×240 visā moduļa garumā: 0.2·0.24·12.0·2 = 1.152 m³
        row = self.table["Garās perimetra sijas"]
        self.assertEqual((row["b (mm)"], row["h (mm)"], row["L (mm)"], row["Gab."]), (200, 240, 12000, 2))
        self.assertAlmostEqual(row["m³"], 1.152, places=6)

    def test_end_beams_between_long_beams(self):
        # Gala sijas starp garajām sijām: 4000 − 2·200 = 3600 mm.
        # 0.2·0.24·3.6·2 = 0.3456 m³
        row = self.table["Gala sijas"]
        self.assertEqual((row["b (mm)"], row["h (mm)"], row["L (mm)"], row["Gab."]), (200, 240, 3600, 2))
        self.assertAlmostEqual(row["m³"], 0.3456, places=6)

    def test_cross_joists(self):
        # 600 mm ass solis no moduļa ārmalas: asis 600, 1200, … 11400 → 11400/600 = 19 gab.
        # (Pēdējā ass 11400; +22.5 = 11422.5 < gala sijas iekšmala 11800 → nepārklājas.)
        # Alternatīva interpretācija "600 mm tīrā atstarpe": tīrais garums 12000 − 2·200 = 11600,
        # n·45 + (n+1)·600 ≤ … ⇒ n ≥ 11000/645 = 17.05 ⇒ 18 gab. Kods lieto ass soli (19).
        # 0.045·0.24·3.6·19 = 0.73872 m³
        row = self.table["Regulārās šķērssijas"]
        self.assertEqual((row["b (mm)"], row["h (mm)"], row["L (mm)"], row["Gab."]), (45, 240, 3600, 19))
        self.assertAlmostEqual(row["m³"], 0.73872, places=6)

    def test_totals(self):
        # 2 + 2 + 19 = 23 gab.; 1.152 + 0.3456 + 0.73872 = 2.23632 m³
        self.assertEqual(sum(r["Gab."] for r in self.table.values()), 23)
        self.assertAlmostEqual(sum(r["m³"] for r in self.table.values()), 2.23632, places=6)
        self.assertIn("2.236 m³", [m.value for m in self.at.metric])


@unittest.skipUnless(HAVE_APPTEST, "Nepieciešams streamlit ar AppTest failu augšupielādi un PyMuPDF")
class TestADNoGuessing(unittest.TestCase):
    """Ja izmēri nav droši nolasāmi, aprēķins netiek veikts."""

    def assert_refused(self, pages):
        at = run_app(pages)
        self.assertTrue(any(NO_DIMENSIONS in e for e in errors(at)), errors(at))
        self.assertEqual(len(at.dataframe), 0)

    def test_thousands_separator_not_read(self):
        # Reproducējams ierobežojums: "12 000" (ar atstarpi) netiek atpazīts.
        self.assert_refused(["Floor plan\n12 000\n4 000"])

    def test_nonstandard_width_refused(self):
        # Tikai 3500 un 4000 mm tiek uzskatīti par Rebel platumiem.
        self.assert_refused(["Floor plan\n12000\n3600"])

    def test_no_floor_plan_page(self):
        at = run_app(["Elevation\n12000\n4000"])
        self.assertIn("Nav atrasta atpazīstama grīdas plāna lapa.", errors(at))


@unittest.skipUnless(HAVE_APPTEST, "Nepieciešams streamlit ar AppTest failu augšupielādi un PyMuPDF")
class TestADAndPDAreSeparate(unittest.TestCase):
    def test_pd_schedule_not_used_in_ad(self):
        at = run_app(["Structural Frame - TOP\nTimber Element list\n 1 Glued beam / līmsija 200 240 9600 2"])
        self.assertIn("Nav atrasta atpazīstama grīdas plāna lapa.", errors(at))

    def test_ad_plan_not_used_in_pd(self):
        at = run_app(["Floor plan\n12000\n4000"], mode=PD_MODE)
        self.assertIn("Šajā PDF netika atrasta atbalstīta līmsiju specifikācijas tabula.",
                      [i.value for i in at.info])
        self.assertEqual(errors(at), [])


@unittest.skipUnless(HAVE_APPTEST, "Nepieciešams streamlit ar AppTest failu augšupielādi un PyMuPDF")
class TestADKnownDiscrepancies(unittest.TestCase):
    """Konstatētās neatbilstības — jāsaskaņo ar ChatGPT/MLK pirms labošanas."""

    @unittest.expectedFailure
    def test_joists_do_not_overlap_end_beam_when_length_not_multiple_of_600(self):
        # L = 12100: kods dod ceil(12100/600) − 1 = 20 šķērssijas, pēdējā ass 12000 mm.
        # Gala sija aizņem 11900…12100 → šķērssija 11977.5…12022.5 pārklājas ar to.
        # Jebkurā interpretācijā (ass no ārmalas bez pārklāšanās, ass no gala sijas ass,
        # tīrā atstarpe) sanāk ≤ 19.
        table = ad_table(run_app(["Floor plan\n12100\n4000"]))
        self.assertLessEqual(table["Regulārās šķērssijas"]["Gab."], 19)

    @unittest.expectedFailure
    def test_roof_overhang_does_not_change_module_length(self):
        # Jumta plāns ar pārkarēm (12600) pārraksta grīdas plāna garumu 12000.
        at = run_app(["Floor plan\n12000\n4000", "Roof plan\n12600\n4600"])
        self.assertEqual(ad_table(at)["Garās perimetra sijas"]["L (mm)"], 12000)

    @unittest.expectedFailure
    def test_room_dimension_3500_does_not_override_width_4000(self):
        # Platumu izvēlas pēc biežuma; telpas izmērs 3500, kas atkārtojas, pārspēj 4000.
        at = run_app(["Floor plan\n12000\n4000\n3500\n3500"])
        self.assertEqual(ad_table(at)["Gala sijas"]["L (mm)"], 3600)

    @unittest.expectedFailure
    def test_cover_sheet_with_longer_text_is_not_chosen_as_floor_plan(self):
        # Ja titullapā ir vairāk teksta ar vārdiem "Floor plan", tiek izvēlēta titullapa.
        at = run_app(["Drawing list: Floor plan, Roof plan\nProject 15000",
                      "Floor plan\n12000\n4000"])
        self.assertEqual(errors(at), [])


if __name__ == "__main__":
    unittest.main()
