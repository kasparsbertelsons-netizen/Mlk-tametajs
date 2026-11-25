"""AD režīma grīdas rāmja testi (Issue #2).

Trīs grupas:

1. TestApprovedRuleReferenceModel — tīrs aritmētikas modelis pēc ChatGPT
   precizētajiem noteikumiem (Issue #2 komentārs 2026-11-25). Sagaidāmās
   vērtības ir aprēķinātas ar roku un nav atkarīgas no app.py.
2. TestADCurrentBehavior — FIKSĒ ESOŠO app.py uzvedību (sintētisks PDF caur
   Streamlit AppTest). Tas NAV apstiprināts biznesa aprēķins; šie testi
   jāmaina nākamajā uzdevumā, kad aprēķins tiks labots.
3. TestADApprovedRules — pēc apstiprinātajiem noteikumiem sagaidāmā uzvedība.
   Esošais kods tos neizpilda, tāpēc @expectedFailure. Kad kods tiks labots,
   dekorators jānoņem; testa vērtības nemainīt.

Klientu dati netiek izmantoti: visi PDF tiek ģenerēti testā.
"""
import unittest
from pathlib import Path

APP = str(Path(__file__).resolve().parent.parent / "app.py")
AD_MODE = "AD — prognozēt rāmi"
PD_MODE = "PD — nolasīt specifikāciju"
NO_DIMENSIONS = "No plāna nav droši nosakāmi Rebel moduļa gabarīti"
NO_PLAN = "Nav atrasta atpazīstama grīdas plāna lapa."

try:
    import pymupdf
    from streamlit.testing.v1 import AppTest
    from streamlit.testing.v1.element_tree import FileUploader
    HAVE_APPTEST = hasattr(FileUploader, "upload")
except ImportError:  # pragma: no cover
    HAVE_APPTEST = False

needs_apptest = unittest.skipUnless(
    HAVE_APPTEST, "Nepieciešams streamlit ar AppTest failu augšupielādi un PyMuPDF")

# --- Apstiprinātie noteikumi (ChatGPT, Issue #2) ---------------------------
PERIMETER_MM = 200          # perimetra sijas platums
CLEAR_GAP_MM = 600          # tīrā atstarpe starp sijām
CROSS_JOIST_MM = 45         # šķērssijas platums
PITCH_MM = CLEAR_GAP_MM + CROSS_JOIST_MM   # 645 mm ass solis


def reference_cross_joists(length_mm):
    """Šķērssiju skaits un pēdējā atstarpe (atlikums), mm.

    Mērījums no gala sijas iekšējās plaknes: 600 mm brīvas atstarpes, sija 45,
    600, sija 45 … k-tā sija beidzas pie 645·k mm. Pēdējā atstarpe ir atlikums,
    bez pārdalīšanas.
    """
    clear = length_mm - 2 * PERIMETER_MM
    count = clear // PITCH_MM
    return count, clear - count * PITCH_MM


def make_pdf(pages):
    """Sintētisks PDF: katrs teksta bloks ir viena lapa."""
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
    return {row["Elements"]: row for row in at.dataframe[0].value.to_dict("records")}


def errors(at):
    return [e.value for e in at.error]


class TestApprovedRuleReferenceModel(unittest.TestCase):
    """Roku aprēķins pēc apstiprinātajiem noteikumiem (nav atkarīgs no app.py)."""

    def test_12000x4000(self):
        # brīvais garums 12000 − 400 = 11600; 11600 // 645 = 17 (17·645 = 10965);
        # 18. sija sāktos pie 600 + 17·645 = 11565 un beigtos pie 11610 > 11600.
        # Atlikums 11600 − 10965 = 635 mm (> 600 → jāatzīmē pārbaudei).
        self.assertEqual(reference_cross_joists(12000), (17, 635))
        self.assertGreater(635, CLEAR_GAP_MM)

    def test_12100x4000(self):
        # brīvais 11700; 11700 // 645 = 18 (18·645 = 11610); atlikums 90 mm.
        self.assertEqual(reference_cross_joists(12100), (18, 90))

    def test_totals_12000x4000(self):
        # garās 2·0,2·0,24·12,0 = 1,152; gala 2·0,2·0,24·3,6 = 0,3456;
        # šķērssijas 17·0,045·0,24·3,6 = 17·0,03888 = 0,66096
        # kopā 21 gab., 2,15856 m³
        total = 1.152 + 0.3456 + 17 * 0.03888
        self.assertAlmostEqual(total, 2.15856, places=6)
        self.assertEqual(2 + 2 + 17, 21)

    def test_totals_12100x4000(self):
        # 2·0,2·0,24·12,1 = 1,1616; 0,3456; 18·0,03888 = 0,69984 → 2,20704 m³, 22 gab.
        self.assertAlmostEqual(1.1616 + 0.3456 + 18 * 0.03888, 2.20704, places=6)


@needs_apptest
class TestADCurrentBehavior(unittest.TestCase):
    """ESOŠĀ app.py uzvedība, 12000 × 4000 mm sintētisks modulis.

    Šķērssiju skaits un kopsummas NAV apstiprinātas: skat. TestADApprovedRules.
    """

    @classmethod
    def setUpClass(cls):
        cls.at = run_app([
            "Cover sheet",
            "Floor plan 1:50\n12000\n4000\nKitchen 12.5 m2\nWindow 1200x1500",
        ])
        cls.table = ad_table(cls.at)

    def test_dimensions_detected(self):
        self.assertEqual([m.value for m in self.at.metric][:3], ["12000 mm", "4000 mm", "600 mm"])
        self.assertEqual(errors(self.at), [])

    def test_long_perimeter_beams_match_rule(self):
        # 2 × 0,2·0,24·12,0 = 1,152 m³ (sakrīt ar apstiprināto noteikumu)
        row = self.table["Garās perimetra sijas"]
        self.assertEqual((row["b (mm)"], row["h (mm)"], row["L (mm)"], row["Gab."]), (200, 240, 12000, 2))
        self.assertAlmostEqual(row["m³"], 1.152, places=6)

    def test_end_beams_match_rule(self):
        # L = W − 400 = 3600; 2 × 0,2·0,24·3,6 = 0,3456 m³ (sakrīt ar noteikumu)
        row = self.table["Gala sijas"]
        self.assertEqual((row["b (mm)"], row["h (mm)"], row["L (mm)"], row["Gab."]), (200, 240, 3600, 2))
        self.assertAlmostEqual(row["m³"], 0.3456, places=6)

    def test_current_cross_joists_19_not_approved(self):
        # Kods: ceil(12000/600) − 1 = 19 (600 kā ass solis no ārmalas).
        # Apstiprinātais noteikums dod 17 → kods pārvērtē par 2 gab., 0,07776 m³.
        row = self.table["Regulārās šķērssijas"]
        self.assertEqual((row["b (mm)"], row["h (mm)"], row["L (mm)"], row["Gab."]), (45, 240, 3600, 19))
        self.assertAlmostEqual(row["m³"], 0.73872, places=6)

    def test_current_totals_not_approved(self):
        # Esošais: 23 gab., 2,23632 m³. Apstiprinātais: 21 gab., 2,15856 m³.
        self.assertEqual(sum(r["Gab."] for r in self.table.values()), 23)
        self.assertAlmostEqual(sum(r["m³"] for r in self.table.values()), 2.23632, places=6)
        self.assertIn("2.236 m³", [m.value for m in self.at.metric])


@needs_apptest
class TestADNoGuessing(unittest.TestCase):
    """Ja izmēri nav droši nolasāmi, aprēķins netiek veikts (droša uzvedība)."""

    def assert_refused(self, pages):
        at = run_app(pages)
        self.assertTrue(any(NO_DIMENSIONS in e for e in errors(at)), errors(at))
        self.assertEqual(len(at.dataframe), 0)

    def test_thousands_separator_not_read(self):
        # Reproducējams ierobežojums: "12 000" (ar atstarpi) netiek atpazīts.
        self.assert_refused(["Floor plan\n12 000\n4 000"])

    def test_current_width_3600_refused(self):
        # ESOŠĀ uzvedība: tikai 3500/4000. Apstiprinātais noteikums platumu
        # neierobežo (līdz ~4500 mm) → skat. TestADApprovedRules.
        self.assert_refused(["Floor plan\n12000\n3600"])

    def test_no_floor_plan_page(self):
        self.assertIn(NO_PLAN, errors(run_app(["Elevation\n12000\n4000"])))


@needs_apptest
class TestADAndPDAreSeparate(unittest.TestCase):
    def test_pd_schedule_not_used_in_ad(self):
        at = run_app(["Structural Frame - TOP\nTimber Element list\n 1 Glued beam / līmsija 200 240 9600 2"])
        self.assertIn(NO_PLAN, errors(at))

    def test_ad_plan_not_used_in_pd(self):
        at = run_app(["Floor plan\n12000\n4000"], mode=PD_MODE)
        self.assertIn("Šajā PDF netika atrasta atbalstīta līmsiju specifikācijas tabula.",
                      [i.value for i in at.info])
        self.assertEqual(errors(at), [])


@needs_apptest
class TestADApprovedRules(unittest.TestCase):
    """Pēc ChatGPT apstiprinātajiem noteikumiem sagaidāmā uzvedība.

    Esošais kods tos neizpilda → @expectedFailure. Nemainīt vērtības; kad kods
    tiks labots (atsevišķs uzdevums), noņemt dekoratoru.
    """

    @unittest.expectedFailure
    def test_cross_joists_12000x4000(self):
        table = ad_table(run_app(["Floor plan\n12000\n4000"]))
        row = table["Regulārās šķērssijas"]
        self.assertEqual(row["Gab."], 17)
        self.assertAlmostEqual(row["m³"], 0.66096, places=6)
        self.assertEqual(sum(r["Gab."] for r in table.values()), 21)
        self.assertAlmostEqual(sum(r["m³"] for r in table.values()), 2.15856, places=6)

    @unittest.expectedFailure
    def test_cross_joists_12100x4000(self):
        # Esošais kods dod 20 (pārklājas ar gala siju); noteikums dod 18, atlikums 90 mm.
        table = ad_table(run_app(["Floor plan\n12100\n4000"]))
        self.assertEqual(table["Regulārās šķērssijas"]["Gab."], 18)
        self.assertAlmostEqual(sum(r["m³"] for r in table.values()), 2.20704, places=6)

    @unittest.expectedFailure
    def test_width_3600_is_not_rejected(self):
        # Platumi nav ierobežoti ar 3500/4000; faktiskais izmērs no rasējuma.
        # W = 3600 → gala/šķērssiju garums 3200 mm.
        at = run_app(["Floor plan\n12000\n3600"])
        self.assertEqual(errors(at), [], "platums 3600 tiek noraidīts")
        self.assertEqual(ad_table(at)["Gala sijas"]["L (mm)"], 3200)

    @unittest.expectedFailure
    def test_roof_overhang_does_not_change_module_length(self):
        # Garums no grīdas moduļa kontūras, ne no jumta plāna (12600 ar pārkari).
        at = run_app(["Floor plan\n12000\n4000", "Roof plan\n12600\n4600"])
        self.assertEqual(ad_table(at)["Garās perimetra sijas"]["L (mm)"], 12000)

    @unittest.expectedFailure
    def test_ambiguous_width_is_not_silently_chosen(self):
        # 3500 (telpas izmērs, atkārtots) un 4000 plānā. Neskaidra ģeometrija:
        # jāizvēlas pareizi (3600) vai jāatsakās/jāprasa apstiprinājums,
        # bet nedrīkst klusi pieņemt 3500 platu moduli (L = 3100).
        at = run_app(["Floor plan\n12000\n4000\n3500\n3500"])
        if len(at.dataframe):
            self.assertEqual(ad_table(at)["Gala sijas"]["L (mm)"], 3600)
        else:
            self.assertTrue(errors(at))

    @unittest.expectedFailure
    def test_cover_sheet_is_not_chosen_as_floor_plan(self):
        # Titullapa ar vairāk teksta un vārdiem "Floor plan" nedrīkst aizstāt plānu.
        at = run_app(["Drawing list: Floor plan, Roof plan\nProject 15000",
                      "Floor plan\n12000\n4000"])
        self.assertEqual(errors(at), [])


if __name__ == "__main__":
    unittest.main()
