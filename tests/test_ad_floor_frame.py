"""AD režīma saskarnes testi (Issue #4): kandidāti → apstiprināti moduļi → pamatrāmis.

`app.py` tiek palaists caur Streamlit AppTest ar sintētiskiem PDF, kas satur
TIKAI TEKSTU. Tie NEPIERĀDA vektoru ģeometrijas atpazīšanu; tie pārbauda
apstiprināšanas plūsmu. Skaitļu pareizība kodolā: tests/test_floor_frame.py.

Importi ir tiešie: ja streamlit/PyMuPDF/AppTest nav pieejams, testi KRĪT, nevis
tiek klusi izlaisti (skat. TestEnvironment).
"""
import unittest
from pathlib import Path

import pymupdf
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import FileUploader

APP = str(Path(__file__).resolve().parent.parent / "app.py")
AD_MODE = "AD — prognozēt rāmi"
PD_MODE = "PD — nolasīt specifikāciju"

FLOOR = "Floor plan 1:50\n12000\n4000\nKitchen 12.5 m2\nWindow 1200x1500"
COVER = "Drawing list: Floor plan, Roof plan\nProject 15000"
ROOF = "Roof plan 1:100\n12600\n4600"
PD_TABLE = "Structural Frame - TOP\nTimber Element list\n 1 Glued beam / līmsija 200 240 9600 2"


def make_pdf(pages):
    """Sintētisks teksta PDF. TextWriter ar Unicode, lai saglabātos latviešu burti (ī u. c.)."""
    font = pymupdf.Font("helv")
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        writer = pymupdf.TextWriter(page.rect)
        for number, line in enumerate(text.split("\n")):
            writer.append((50, 72 + 14 * number), line, font=font, fontsize=10)
        writer.write_text(page)
    data = doc.tobytes()
    doc.close()
    return data


def start(pages=None, mode=AD_MODE):
    at = AppTest.from_file(APP, default_timeout=60).run()
    if mode != AD_MODE:
        at.radio[0].set_value(mode).run()
    if pages is not None:
        at.file_uploader[0].upload("synthetic.pdf", make_pdf(pages), "application/pdf").run()
    assert not at.exception, at.exception
    return at


def enter(at, index, length, width, confirm=True):
    at.number_input(key=f"ad_L_{index}").set_value(length)
    at.number_input(key=f"ad_W_{index}").set_value(width)
    if confirm:
        at.checkbox(key=f"ad_confirm_{index}").check()
    at.run()
    assert not at.exception, at.exception
    return at


def metrics(at):
    return [(m.label, m.value) for m in at.metric]


def metric(at, label, nth=0):
    return [value for lab, value in metrics(at) if lab == label][nth]


def beam_tables(at):
    """Siju tabulas (ar kolonnu 'Elements') kā [{Elements: rinda}, …]."""
    tables = []
    for frame in at.dataframe:
        if "Elements" in frame.value.columns:
            tables.append({row["Elements"]: row for row in frame.value.to_dict("records")})
    return tables


def warnings(at):
    return [w.value for w in at.warning]


def errors(at):
    return [e.value for e in at.error]


class TestEnvironment(unittest.TestCase):
    def test_apptest_supports_file_upload(self):
        # Ja šis krīt, vide nevar izpildīt UI testus; tie netiek klusi izlaisti.
        self.assertTrue(hasattr(FileUploader, "upload"),
                        "Streamlit AppTest nesatur FileUploader.upload; jāatjaunina streamlit")


class TestConfirmationFlow(unittest.TestCase):
    def test_nothing_is_calculated_before_confirmation(self):
        at = start([FLOOR])
        enter(at, 0, 12000, 4000, confirm=False)
        self.assertEqual(metrics(at), [])
        self.assertEqual(beam_tables(at), [])
        self.assertTrue(any("gaida apstiprinājumu" in i.value for i in at.info))

    def test_fields_are_not_prefilled_from_pdf(self):
        # PDF satur 12000 un 4000, bet L un W paliek tukši, līdz lietotājs tos ievada.
        at = start([FLOOR])
        self.assertEqual((at.number_input(key="ad_L_0").value, at.number_input(key="ad_W_0").value), (0, 0))
        self.assertFalse(at.checkbox(key="ad_confirm_0").value)
        self.assertEqual(metrics(at), [])

    def test_confirmed_without_dimensions_asks_for_them(self):
        at = start([FLOOR])
        at.checkbox(key="ad_confirm_0").check().run()
        self.assertEqual(metrics(at), [])
        self.assertTrue(any("ievadi L un W" in w for w in warnings(at)))

    def test_candidates_show_source_page(self):
        at = start([COVER, FLOOR, ROOF])
        candidates = at.dataframe[0].value.to_dict("records")
        self.assertEqual([(c["Lapa"], c["Izmērs (mm)"]) for c in candidates], [(2, 4000), (2, 12000)])
        self.assertIn("PDF 2. lapa", at.selectbox(key="ad_src_0").options)


class TestAcceptanceInUI(unittest.TestCase):
    def test_12000x4000(self):
        at = enter(start([FLOOR]), 0, 12000, 4000)
        self.assertEqual(errors(at), [])
        self.assertEqual(metric(at, "Šķērssijas (gab.)"), "17")
        self.assertEqual(metric(at, "Sijas moduļā (gab.)"), "21")
        self.assertEqual(metric(at, "Kokmateriāli moduļā"), "2.15856 m³")
        self.assertEqual(metric(at, "Atlikums (mm)"), "635")
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "21")
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")
        self.assertTrue(any("635" in w and "jāpārbauda" in w for w in warnings(at)))
        table = beam_tables(at)[0]
        self.assertEqual(table["Regulārās šķērssijas"]["Gab."], 17)
        self.assertEqual(table["Gala sijas"]["L (mm)"], 3600)

    def test_12100x4000(self):
        at = enter(start([FLOOR]), 0, 12100, 4000)
        self.assertEqual(metric(at, "Šķērssijas (gab.)"), "18")
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "22")
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.20704 m³")
        self.assertEqual(metric(at, "Atlikums (mm)"), "90")
        self.assertFalse(any("jāpārbauda" in w and "Atlikums" in w for w in warnings(at)))

    def test_width_3600(self):
        at = enter(start([FLOOR]), 0, 12000, 3600)
        table = beam_tables(at)[0]
        self.assertEqual(table["Gala sijas"]["L (mm)"], 3200)
        self.assertEqual(table["Regulārās šķērssijas"]["L (mm)"], 3200)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.04672 m³")

    def test_two_modules_are_confirmed_and_summed_separately(self):
        at = start([FLOOR])
        at.number_input(key="ad_module_count").set_value(2).run()
        enter(at, 0, 12000, 4000)
        enter(at, 1, 12100, 3600)
        self.assertEqual(errors(at), [])
        self.assertEqual(metric(at, "Sijas moduļā (gab.)", 0), "21")
        self.assertEqual(metric(at, "Sijas moduļā (gab.)", 1), "22")
        self.assertEqual(metric(at, "Kokmateriāli moduļā", 0), "2.15856 m³")
        self.assertEqual(metric(at, "Kokmateriāli moduļā", 1), "2.09088 m³")
        self.assertEqual(metric(at, "Aprēķinātie moduļi"), "2")
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "43")
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "4.24944 m³")

    def test_unconfirmed_second_module_is_not_counted(self):
        at = start([FLOOR])
        at.number_input(key="ad_module_count").set_value(2).run()
        enter(at, 0, 12000, 4000)
        enter(at, 1, 12100, 3600, confirm=False)
        self.assertEqual(metric(at, "Aprēķinātie moduļi"), "1")
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_scope_note_says_only_base_frame(self):
        at = enter(start([FLOOR]), 0, 12000, 4000)
        self.assertTrue(any("tikai pamatrāmi" in w and "150×240" in w for w in warnings(at)))
        self.assertTrue(any("tikai pamatrāmi" in i.value for i in at.info))


class TestNoSilentWrongResults(unittest.TestCase):
    def test_roof_cover_and_room_numbers_do_not_become_results(self):
        at = start([COVER, FLOOR + "\nTerase 4500\n3500", ROOF])
        self.assertEqual(metrics(at), [])                       # nekas netiek aprēķināts pats
        shown = {c["Izmērs (mm)"] for c in at.dataframe[0].value.to_dict("records")}
        self.assertEqual(shown, {3500, 4000, 12000})
        self.assertFalse(shown & {12600, 4600, 15000, 4500})    # jumts, titullapa, terase
        enter(at, 0, 12000, 4000)
        self.assertEqual(beam_tables(at)[0]["Garās perimetra sijas"]["L (mm)"], 12000)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_excluded_sources_are_listed(self):
        at = start([COVER, FLOOR + "\nTerase 4500", ROOF])
        excluded = at.dataframe[1].value.to_dict("records")
        self.assertEqual(sorted(row["Lapa"] for row in excluded), [1, 2, 3])
        self.assertTrue(any(row["Skaitļi"] == "4500" for row in excluded))

    def test_ambiguous_dimensions_need_user_input(self):
        # 3500 atkārtojas biežāk par 4000; programma neizvēlas pati.
        at = start(["Floor plan\n12000\n4000\n3500\n3500\n3500"])
        self.assertEqual(metrics(at), [])
        self.assertEqual((at.number_input(key="ad_L_0").value, at.number_input(key="ad_W_0").value), (0, 0))

    def test_thousands_separator_gives_no_candidates_but_manual_entry_works(self):
        at = start(["Floor plan\n12 000\n4 000"])
        self.assertTrue(any("neviens izmēra kandidāts" in w for w in warnings(at)))
        enter(at, 0, 12000, 4000)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_no_floor_plan_page_warns_and_allows_manual_entry(self):
        at = start(["Elevation\n12000\n4000"])
        self.assertTrue(any("Nav atrasta atpazīstama grīdas plāna lapa" in w for w in warnings(at)))
        self.assertEqual(metrics(at), [])
        enter(at, 0, 12000, 4000)
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "21")

    def test_manual_entry_without_any_pdf(self):
        at = enter(start(), 0, 12100, 4000)
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "22")

    def test_non_pdf_file_is_rejected(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        at.file_uploader[0].upload("fake.pdf", b"this is not a pdf", "application/pdf").run()
        self.assertTrue(any("PDF neizdevās nolasīt" in e for e in errors(at)))
        self.assertEqual(metrics(at), [])


class TestInvalidAndNonstandardInput(unittest.TestCase):
    def test_width_too_small(self):
        at = enter(start(), 0, 12000, 400)
        self.assertTrue(any("Platums W" in e for e in errors(at)))
        self.assertEqual(metrics(at), [])

    def test_length_too_small(self):
        at = enter(start(), 0, 400, 4000)
        self.assertTrue(any("Garums L" in e for e in errors(at)))
        self.assertEqual(metrics(at), [])

    def test_nonstandard_perimeter_needs_confirmation(self):
        at = start()
        at.number_input(key="ad_perim_0").set_value(150).run()
        enter(at, 0, 12000, 4000)
        self.assertTrue(any("Nestandarta" in e for e in errors(at)))
        self.assertEqual(metrics(at), [])
        at.checkbox(key="ad_nonstd_0").check().run()
        self.assertEqual(errors(at), [])
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "1.84968 m³")
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "22")

    def test_default_perimeter_is_labelled_as_default(self):
        at = enter(start(), 0, 12000, 4000)
        self.assertIn("NOKLUSĒJUMS", " ".join(c.value for c in at.caption))
        self.assertIn("noklusējums 200", at.number_input(key="ad_perim_0").label)

    def test_width_over_4500_needs_extra_confirmation(self):
        at = enter(start(), 0, 12000, 4600)
        self.assertEqual(metrics(at), [])
        self.assertTrue(any("nav apstiprināts" in w and "4500" in w for w in warnings(at)))
        at.checkbox(key="ad_wide_0").check().run()
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.32632 m³")
        self.assertTrue(any("pārsniedz orientējošo 4500" in w for w in warnings(at)))

    def test_width_4500_does_not_need_extra_confirmation(self):
        at = enter(start(), 0, 12000, 4500)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.29836 m³")


class TestPDPathUnchanged(unittest.TestCase):
    def test_pd_schedule_still_read(self):
        at = start([PD_TABLE], mode=PD_MODE)
        self.assertEqual(errors(at), [])
        self.assertEqual(metric(at, "Pozīcijas"), "1")
        self.assertEqual(metric(at, "Līmsijas"), "2")
        self.assertEqual(metric(at, "Kokmateriāli"), "0.922 m³")      # 200·240·9600·2 = 0,9216
        self.assertEqual(at.dataframe[0].value.to_dict("records")[0]["volume_m3"], 0.9216)

    def test_pd_mode_has_no_ad_widgets(self):
        at = start([PD_TABLE], mode=PD_MODE)
        keys = {w.key for w in list(at.number_input) + list(at.checkbox)}
        self.assertFalse({k for k in keys if k and k.startswith("ad_")})

    def test_ad_plan_in_pd_mode_finds_no_schedule(self):
        at = start([FLOOR], mode=PD_MODE)
        self.assertIn("Šajā PDF netika atrasta atbalstīta līmsiju specifikācijas tabula.",
                      [i.value for i in at.info])
        self.assertEqual(errors(at), [])

    def test_pd_schedule_is_not_used_in_ad_mode(self):
        at = start([PD_TABLE])
        self.assertTrue(any("Nav atrasta atpazīstama grīdas plāna lapa" in w for w in warnings(at)))
        self.assertEqual(metrics(at), [])


if __name__ == "__main__":
    unittest.main()
