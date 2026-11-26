"""AD režīma saskarnes testi (Issue #4): kandidāti → apstiprināti moduļi → pamatrāmis.

`app.py` tiek palaists caur Streamlit AppTest ar sintētiskiem PDF, kas satur
TIKAI TEKSTU. Tie NEPIERĀDA vektoru ģeometrijas atpazīšanu; tie pārbauda
apstiprināšanas plūsmu. Skaitļu pareizība kodolā: tests/test_floor_frame.py.

Importi ir tiešie: ja streamlit/PyMuPDF/AppTest nav pieejams, testi KRĪT, nevis
tiek klusi izlaisti (skat. TestEnvironment).
"""
import hashlib
import re
import unittest
from unittest import mock
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import pymupdf
from packaging.requirements import Requirement

import src.ad_ui  # noqa: F401  (patch("src.ad_ui.MAX_PDF_BYTES") testiem)
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import FileUploader

APP = str(Path(__file__).resolve().parent.parent / "app.py")
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples" / "ad_vector"
AD_MODE = "Vecais AD: tikai grīdas rāmis"
PD_MODE = "PD: līmsiju specifikācija"

FLOOR = "Floor plan 1:50\n12000\n4000\nKitchen 12.5 m2\nWindow 1200x1500"
COVER = "Drawing list: Floor plan, Roof plan\nProject 15000"
ROOF = "Roof plan 1:100\n12600\n4600"
PD_TABLE = "Structural Frame - TOP\nTimber Element list\n 1 Glued beam / līmsija 200 240 9600 2"



def legacy_app(timeout=60):
    """Vecais AD grīdas rāmja režīms (Issue #18: noklusējums tagad ir pilnas ēkas AD tāme)."""
    at = AppTest.from_file(APP, default_timeout=timeout).run()
    at.radio[0].set_value("Vecais AD: tikai grīdas rāmis").run()
    return at


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
    at = legacy_app(60)
    if mode != AD_MODE:
        at.radio[0].set_value(mode).run()
    if pages is not None:
        at.file_uploader[0].upload("synthetic.pdf", make_pdf(pages), "application/pdf").run()
    assert not at.exception, at.exception
    return at


def sample(name):
    return (SAMPLES_DIR / name).read_bytes()


def start_bytes(data):
    """Palaiž lietotni un augšupielādē gatavu PDF (piem., paraugu no samples/ad_vector)."""
    at = legacy_app(90)
    at.file_uploader[0].upload("sample.pdf", data, "application/pdf").run()
    assert not at.exception, at.exception
    return at


def pick_candidate(at, prefix):
    box = at.selectbox(key="ad_vec_pick")
    label = next(option for option in box.options if option.startswith(prefix))
    box.set_value(label).run()
    assert not at.exception, at.exception
    return at


def transfer(at, target=1):
    at.selectbox(key="ad_vec_target").set_value(target).run()
    at.button(key="ad_vec_transfer").click().run()
    assert not at.exception, at.exception
    return at


def vector_table(at):
    for frame in at.dataframe:
        if "Statuss" in frame.value.columns:
            return frame.value.to_dict("records")
    return []


def confirm(at, index):
    at.button(key=f"ad_confirm_{index}").click().run()
    assert not at.exception, at.exception
    return at


def enter(at, index, length, width, confirmed=True):
    """Ievada L un W un (pēc noklusējuma) nospiež "Apstiprināt šo ievadi"."""
    at.number_input(key=f"ad_L_{index}").set_value(length)
    at.number_input(key=f"ad_W_{index}").set_value(width)
    at.run()
    assert not at.exception, at.exception
    return confirm(at, index) if confirmed else at


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

    def test_installed_versions_satisfy_requirements_txt(self):
        # requirements.txt zemākās versijas ir faktiski testētās (README: Testēšanas vide).
        text = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text(encoding="utf-8")
        requirements = [Requirement(line) for line in text.splitlines() if line.strip()]
        self.assertGreaterEqual(len(requirements), 2)
        for requirement in requirements:
            installed = version(requirement.name)
            self.assertTrue(requirement.specifier.contains(installed),
                            f"{requirement.name} {installed} neatbilst {requirement.specifier}")


class TestConfirmationFlow(unittest.TestCase):
    def test_nothing_is_calculated_before_confirmation(self):
        at = start([FLOOR])
        enter(at, 0, 12000, 4000, confirmed=False)
        self.assertEqual(metrics(at), [])
        self.assertEqual(beam_tables(at), [])
        self.assertTrue(any("gaida apstiprinājumu" in i.value.lower() for i in at.info))

    def test_fields_are_not_prefilled_from_pdf(self):
        # PDF satur 12000 un 4000, bet L un W paliek tukši, līdz lietotājs tos ievada.
        at = start([FLOOR])
        self.assertEqual((at.number_input(key="ad_L_0").value, at.number_input(key="ad_W_0").value), (0, 0))
        self.assertTrue(any("gaida apstiprinājumu" in i.value.lower() for i in at.info))
        self.assertEqual(metrics(at), [])

    def test_confirmed_without_dimensions_asks_for_them(self):
        at = confirm(start([FLOOR]), 0)
        self.assertEqual(metrics(at), [])
        self.assertTrue(any("Ievadi L un W" in w for w in warnings(at)))

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
        at = legacy_app(60)
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
        enter(at, 0, 12000, 4000)                       # spiež "Apstiprināt" bez atzīmes
        self.assertTrue(any("nestandarta perimetra" in e for e in errors(at)))
        self.assertEqual(metrics(at), [])
        at.checkbox(key="ad_nonstd_0_150").check().run()
        self.assertEqual(metrics(at), [])               # atzīme viena pati neapstiprina ievadi
        confirm(at, 0)
        self.assertEqual(errors(at), [])
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "1.84968 m³")
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "22")

    def test_default_perimeter_is_labelled_as_default(self):
        at = enter(start(), 0, 12000, 4000)
        self.assertIn("NOKLUSĒJUMS", " ".join(c.value for c in at.caption))
        self.assertIn("noklusējums 200", at.number_input(key="ad_perim_0").label)

    def test_width_over_4500_needs_extra_confirmation(self):
        at = enter(start(), 0, 12000, 4600)             # spiež "Apstiprināt" bez atzīmes
        self.assertEqual(metrics(at), [])
        self.assertTrue(any("platuma virs 4500" in e for e in errors(at)))
        at.checkbox(key="ad_wide_0_4600").check().run()
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.32632 m³")
        self.assertTrue(any("pārsniedz orientējošo 4500" in w for w in warnings(at)))

    def test_width_4500_does_not_need_extra_confirmation(self):
        at = enter(start(), 0, 12000, 4500)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.29836 m³")


class TestConfirmationBoundToInput(unittest.TestCase):
    """Apstiprinājums attiecas uz konkrētu ievades versiju (L, W, perimetrs, avots, PDF)."""

    @staticmethod
    def confirmed():
        at = enter(start([FLOOR]), 0, 12000, 4000)
        assert metric(at, "Kokmateriāli kopā") == "2.15856 m³"
        return at

    def assert_cancelled(self, at):
        self.assertEqual(metrics(at), [])
        self.assertEqual(beam_tables(at), [])
        self.assertTrue(any("apstiprinājums atcelts" in w for w in warnings(at)), warnings(at))

    def test_changing_L_cancels_confirmation(self):
        at = self.confirmed()
        at.number_input(key="ad_L_0").set_value(12100).run()
        self.assert_cancelled(at)
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.20704 m³")

    def test_changing_W_cancels_confirmation(self):
        at = self.confirmed()
        at.number_input(key="ad_W_0").set_value(3600).run()
        self.assert_cancelled(at)
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.04672 m³")

    def test_changing_source_cancels_confirmation(self):
        at = self.confirmed()
        at.selectbox(key="ad_src_0").set_value("PDF 1. lapa").run()
        self.assert_cancelled(at)
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_changing_perimeter_cancels_confirmation(self):
        at = self.confirmed()
        at.number_input(key="ad_perim_0").set_value(150).run()
        self.assert_cancelled(at)

    def test_replacing_pdf_cancels_confirmation(self):
        at = self.confirmed()
        other = make_pdf([FLOOR + "\nRevision B"])
        at.file_uploader[0].upload("other.pdf", other, "application/pdf").run()
        self.assertFalse(at.exception)
        self.assert_cancelled(at)
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_removing_pdf_cancels_confirmation(self):
        at = self.confirmed()
        at.file_uploader[0].set_value(None).run()
        self.assertFalse(at.exception)
        self.assert_cancelled(at)

    def test_removed_and_readded_module_does_not_restore_confirmation(self):
        at = start([FLOOR])
        at.number_input(key="ad_module_count").set_value(2).run()
        enter(at, 0, 12000, 4000)
        enter(at, 1, 12100, 3600)
        self.assertEqual(metric(at, "Aprēķinātie moduļi"), "2")
        at.number_input(key="ad_module_count").set_value(1).run()
        self.assertEqual(list(at.session_state["ad_confirmations"]), [0])
        at.number_input(key="ad_module_count").set_value(2).run()
        enter(at, 1, 12100, 3600, confirmed=False)       # tās pašas vērtības, bet bez apstiprināšanas
        self.assertEqual(metric(at, "Sijas moduļā (gab.)", 0), "21")
        self.assertEqual([lab for lab, _ in metrics(at)].count("Sijas moduļā (gab.)"), 1)
        self.assertTrue(any("NEPILNS APRĒĶINS (1 no 2" in w for w in warnings(at)))
        confirm(at, 1)
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "43")

    def test_nonstandard_confirmation_is_reset_when_perimeter_changes(self):
        at = start()
        at.number_input(key="ad_perim_0").set_value(150).run()
        enter(at, 0, 12000, 4000, confirmed=False)
        at.checkbox(key="ad_nonstd_0_150").check().run()
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "1.84968 m³")
        at.number_input(key="ad_perim_0").set_value(160).run()
        self.assertFalse(at.checkbox(key="ad_nonstd_0_160").value)     # vecā atzīme netiek pārnesta
        self.assertEqual(metrics(at), [])
        confirm(at, 0)                                                   # bez jaunas atzīmes
        self.assertTrue(any("nestandarta perimetra" in e for e in errors(at)))
        self.assertEqual(metrics(at), [])
        at.checkbox(key="ad_nonstd_0_160").check().run()
        confirm(at, 0)
        # perimetrs 160: brīvais 11680, n = 18, atlikums 70, gala/šķērs. 3680 → 1,919616 m³
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "22")
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "1.91962 m³")

    def test_wide_confirmation_is_reset_when_width_changes(self):
        at = enter(start(), 0, 12000, 4600, confirmed=False)
        at.checkbox(key="ad_wide_0_4600").check().run()
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.32632 m³")
        at.number_input(key="ad_W_0").set_value(4700).run()
        self.assertFalse(at.checkbox(key="ad_wide_0_4700").value)
        self.assertEqual(metrics(at), [])
        confirm(at, 0)
        self.assertTrue(any("platuma virs 4500" in e for e in errors(at)))
        self.assertEqual(metrics(at), [])


class TestConfirmationDoesNotComeBack(unittest.TestCase):
    """A → B → A: atgriežoties pie sākotnējiem datiem bez pogas apstiprinājums NEATJAUNOJAS.

    Piezīme: make_pdf nav deterministisks (katrs izsaukums dod citus baitus), tāpēc testos, kur
    jāatgriežas pie "tā paša" PDF, tiek lietots viens un tas pats baitu objekts.
    """

    def assert_needs_new_confirmation(self, at):
        self.assertEqual(metrics(at), [])
        self.assertEqual(beam_tables(at), [])
        self.assertTrue(any("gaida apstiprinājumu" in i.value.lower() for i in at.info))
        self.assertNotIn(0, at.session_state["ad_confirmations"])      # vecais nospiedums dzēsts

    def test_length_A_B_A(self):
        at = enter(start([FLOOR]), 0, 12000, 4000)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")
        at.number_input(key="ad_L_0").set_value(12100).run()
        self.assertTrue(any("apstiprinājums atcelts" in w for w in warnings(at)))
        self.assertEqual(metrics(at), [])
        at.number_input(key="ad_L_0").set_value(12000).run()           # atpakaļ uz A, bez pogas
        self.assert_needs_new_confirmation(at)
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_width_A_B_A(self):
        at = enter(start([FLOOR]), 0, 12000, 4000)
        at.number_input(key="ad_W_0").set_value(3600).run()
        at.number_input(key="ad_W_0").set_value(4000).run()
        self.assert_needs_new_confirmation(at)

    def test_source_A_B_A(self):
        at = enter(start([FLOOR]), 0, 12000, 4000)
        at.selectbox(key="ad_src_0").set_value("PDF 1. lapa").run()
        self.assertEqual(metrics(at), [])
        at.selectbox(key="ad_src_0").set_value("Ievadīts manuāli").run()
        self.assert_needs_new_confirmation(at)

    def test_perimeter_A_B_A(self):
        at = enter(start([FLOOR]), 0, 12000, 4000)
        at.number_input(key="ad_perim_0").set_value(150).run()
        at.number_input(key="ad_perim_0").set_value(200).run()
        self.assert_needs_new_confirmation(at)

    def test_pdf_removed_and_same_bytes_restored(self):
        data = make_pdf([FLOOR])
        at = legacy_app(60)
        at.file_uploader[0].upload("a.pdf", data, "application/pdf").run()
        enter(at, 0, 12000, 4000)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")
        at.file_uploader[0].set_value(None).run()
        self.assertEqual(metrics(at), [])
        at.file_uploader[0].upload("a.pdf", data, "application/pdf").run()   # tie paši baiti
        self.assert_needs_new_confirmation(at)
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_pdf_replaced_by_other_and_back(self):
        a, b = make_pdf([FLOOR]), make_pdf([FLOOR + "\nRevision B"])
        at = legacy_app(60)
        at.file_uploader[0].upload("a.pdf", a, "application/pdf").run()
        enter(at, 0, 12000, 4000)
        at.file_uploader[0].upload("b.pdf", b, "application/pdf").run()
        self.assertEqual(metrics(at), [])
        at.file_uploader[0].upload("a.pdf", a, "application/pdf").run()
        self.assert_needs_new_confirmation(at)

    def test_wide_A_B_A(self):
        at = enter(start(), 0, 12000, 4600, confirmed=False)
        at.checkbox(key="ad_wide_0_4600").check().run()
        confirm(at, 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.32632 m³")
        at.number_input(key="ad_W_0").set_value(4700).run()
        at.number_input(key="ad_W_0").set_value(4600).run()
        self.assertFalse(at.checkbox(key="ad_wide_0_4600").value)      # atzīme neatjaunojas
        self.assert_needs_new_confirmation(at)

    def test_identical_content_direct_replacement_keeps_confirmation(self):
        # ChatGPT: identiska PDF satura tieša nomaiņa drīkst saglabāt apstiprinājumu,
        # ja avots un pārējā ievade nemainās.
        data = make_pdf([FLOOR])
        at = legacy_app(60)
        at.file_uploader[0].upload("a.pdf", data, "application/pdf").run()
        enter(at, 0, 12000, 4000)
        at.file_uploader[0].upload("copy.pdf", data, "application/pdf").run()
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_other_modules_confirmation_is_untouched(self):
        at = start([FLOOR])
        at.number_input(key="ad_module_count").set_value(2).run()
        enter(at, 0, 12000, 4000)
        enter(at, 1, 12100, 3600)
        at.number_input(key="ad_L_1").set_value(12000).run()           # maina tikai 2. moduli
        self.assertEqual(sorted(at.session_state["ad_confirmations"]), [0])
        self.assertEqual(metric(at, "Sijas moduļā (gab.)"), "21")


class TestPdfIdentity(unittest.TestCase):
    """PDF identitāte ir pilns SHA-256 no satura, arī nederīgam vai par lielam failam."""

    @staticmethod
    def upload(at, name, content):
        at.file_uploader[0].upload(name, content, "application/pdf").run()
        assert not at.exception, at.exception
        return at.session_state["ad_scan"]["pdf_id"]

    def test_valid_pdf_uses_full_sha256(self):
        data = make_pdf([FLOOR])
        at = legacy_app(60)
        pdf_id = self.upload(at, "a.pdf", data)
        self.assertEqual(len(pdf_id), 64)
        self.assertEqual(pdf_id, hashlib.sha256(data).hexdigest())

    def test_invalid_files_with_same_name_and_size_have_different_identity(self):
        at = legacy_app(60)
        first = self.upload(at, "same.pdf", b"not a pdf: AAAA")
        self.assertTrue(any("PDF neizdevās nolasīt" in e for e in errors(at)))
        second = self.upload(at, "same.pdf", b"not a pdf: BBBB")       # tas pats nosaukums un izmērs
        self.assertNotEqual(first, second)
        self.assertEqual(first, hashlib.sha256(b"not a pdf: AAAA").hexdigest())
        self.assertEqual(len(second), 64)

    def test_confirmation_is_cancelled_when_invalid_file_is_replaced_by_same_size_file(self):
        at = legacy_app(60)
        self.upload(at, "same.pdf", b"not a pdf: AAAA")
        enter(at, 0, 12000, 4000)                                     # izmēri ievadīti manuāli
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")
        self.upload(at, "same.pdf", b"not a pdf: BBBB")
        self.assertEqual(metrics(at), [])
        self.assertTrue(any("apstiprinājums atcelts" in w for w in warnings(at)))

    def test_oversized_files_with_same_name_and_size_have_different_identity(self):
        with mock.patch("src.ad_ui.MAX_PDF_BYTES", 100):
            at = legacy_app(60)
            first = self.upload(at, "big.pdf", b"A" * 200)
            self.assertTrue(any("Maksimālais PDF izmērs" in e for e in errors(at)))
            second = self.upload(at, "big.pdf", b"B" * 200)
            self.assertNotEqual(first, second)
            self.assertEqual(first, hashlib.sha256(b"A" * 200).hexdigest())
            self.assertEqual(len(second), 64)


class TestIncompleteCalculation(unittest.TestCase):
    """Ja derīgu apstiprinātu moduļu ir mazāk nekā pieprasīts: NEPILNS APRĒĶINS, bez kopsummas un CSV."""

    TOTAL_LABELS = ("Aprēķinātie moduļi", "Sijas kopā (gab.)", "Kokmateriāli kopā")

    def assert_incomplete(self, at, done, requested):
        self.assertTrue(any(f"NEPILNS APRĒĶINS ({done} no {requested} moduļiem)" in w
                            for w in warnings(at)), warnings(at))
        labels = [lab for lab, _ in metrics(at)]
        for label in self.TOTAL_LABELS:
            self.assertNotIn(label, labels)
        self.assertEqual(len(at.get("download_button")), 0)

    def two_modules(self):
        at = start([FLOOR])
        at.number_input(key="ad_module_count").set_value(2).run()
        enter(at, 0, 12000, 4000)
        return at

    def test_second_module_not_confirmed(self):
        at = self.two_modules()
        enter(at, 1, 12100, 3600, confirmed=False)
        self.assert_incomplete(at, 1, 2)
        self.assertEqual(metric(at, "Sijas moduļā (gab.)"), "21")      # atsevišķs rezultāts paliek redzams

    def test_second_module_invalid(self):
        at = self.two_modules()
        enter(at, 1, 12000, 400)
        self.assertTrue(any("Platums W" in e for e in errors(at)))
        self.assert_incomplete(at, 1, 2)

    def test_second_module_wide_but_not_confirmed(self):
        at = self.two_modules()
        enter(at, 1, 12000, 4600)
        self.assert_incomplete(at, 1, 2)

    def test_nothing_confirmed_yet(self):
        self.assert_incomplete(start([FLOOR]), 0, 1)

    def test_complete_calculation_shows_totals_and_export(self):
        at = self.two_modules()
        enter(at, 1, 12100, 3600)
        self.assertFalse(any("NEPILNS" in w for w in warnings(at)))
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "43")
        self.assertEqual(len(at.get("download_button")), 1)

    def test_incomplete_again_after_input_changes(self):
        at = self.two_modules()
        enter(at, 1, 12100, 3600)
        at.number_input(key="ad_L_1").set_value(12000).run()
        self.assert_incomplete(at, 1, 2)


class TestSessionDataHandling(unittest.TestCase):
    """PDF teksts: tikai sesijā, bez globāla keša; dzēšams, mainot/noņemot PDF."""

    def test_no_global_cache_in_code(self):
        root = Path(__file__).resolve().parent.parent
        offenders = []
        for path in [root / "app.py", *sorted((root / "src").glob("*.py"))]:
            if re.search(r"cache_data|cache_resource|lru_cache|functools\.cache", path.read_text(encoding="utf-8")):
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_scan_is_session_scoped_and_removed_with_pdf(self):
        at = start([FLOOR])
        self.assertIn("ad_scan", at.session_state)
        first_id = at.session_state["ad_scan"]["pdf_id"]
        at.file_uploader[0].upload("other.pdf", make_pdf([FLOOR + "\nRevision B"]), "application/pdf").run()
        self.assertEqual(len(first_id), 64)
        self.assertNotEqual(at.session_state["ad_scan"]["pdf_id"], first_id)
        at.file_uploader[0].set_value(None).run()
        self.assertNotIn("ad_scan", at.session_state)
        self.assertEqual(len(at.dataframe), 0)                       # kandidātu tabula pazūd

    def test_upload_help_does_not_promise_privacy(self):
        at = start()
        help_text = at.file_uploader[0].proto.help
        self.assertIn("nav individuālas autentifikācijas", help_text)
        self.assertNotIn("privāt", help_text.lower().replace("konfidenciāl", ""))

    def test_terrace_caveat_is_shown(self):
        at = start([FLOOR + "\nTerase 4500"])
        self.assertTrue(any("negarantē" in c.value and "terase" in c.value for c in at.caption))
        self.assertTrue(any("pagaidu kandidātu saraksts" in c.value for c in at.caption))


class TestVectorCandidatesUI(unittest.TestCase):
    """Vektoru kandidāti → pārnešana → OBLIGĀTS apstiprinājums → aprēķins (repozitorija paraugi)."""

    S01 = "ad_vector_01_12000x4000_1to50.pdf"
    S02 = "ad_vector_02_12100x3600_1to100.pdf"
    S03 = "ad_vector_03_two_modules_with_boundary.pdf"

    def test_candidate_preview_and_evidence_are_shown(self):
        at = start_bytes(sample(self.S01))
        rows = vector_table(at)
        self.assertEqual([(r["Kandidāts"], r["Lapa"], r["Statuss"], r["L (mm)"], r["W (mm)"]) for r in rows],
                         [("P2-K1", 2, "ģeometriski saskaņots", 12000, 4000)])
        self.assertIn("1:50", rows[0]["Mērogs"])
        self.assertEqual(len(at.get("image")), 1)                       # priekšskatījums ar iezīmētu kontūru
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("Horizontālā izmēru norāde '12000'", text)
        self.assertIn("Vertikālā izmēru norāde '4000'", text)
        self.assertIn("MODULIS M1", text)
        self.assertTrue(any("NAV pierādījums" in c.value for c in at.caption))     # prototipa atruna

    def test_room_terrace_roof_and_cover_are_not_candidates(self):
        at = start_bytes(sample(self.S01))
        self.assertEqual({r["Kandidāts"] for r in vector_table(at)}, {"P2-K1"})
        excluded = next(f.value.to_dict("records") for f in at.dataframe if "Veids" in f.value.columns)
        self.assertEqual({(e["Veids"], e["Izmēri (mm)"]) for e in excluded}, {("room", "3500"), ("terrace", "4500")})
        self.assertEqual(metrics(at), [])

    def test_transfer_does_not_confirm_then_confirmation_gives_acceptance_numbers(self):
        at = transfer(start_bytes(sample(self.S01)))
        self.assertEqual((at.number_input(key="ad_L_0").value, at.number_input(key="ad_W_0").value), (12000, 4000))
        self.assertEqual(at.selectbox(key="ad_src_0").value, "PDF 2. lapa, vektoru kandidāts P2-K1")
        self.assertEqual(metrics(at), [])                                  # pārnešana neapstiprina
        self.assertTrue(any("NAV izdarīts" in i.value for i in at.info))
        self.assertTrue(any("gaida apstiprinājumu" in i.value.lower() for i in at.info))
        confirm(at, 0)
        self.assertEqual(metric(at, "Šķērssijas (gab.)"), "17")
        self.assertEqual(metric(at, "Sijas moduļā (gab.)"), "21")
        self.assertEqual(metric(at, "Kokmateriāli moduļā"), "2.15856 m³")
        self.assertEqual(metric(at, "Atlikums (mm)"), "635")
        self.assertTrue(any("635" in w and "jāpārbauda" in w for w in warnings(at)))
        source = next(f.value.to_dict("records")[0]["Avots"] for f in at.dataframe if "Avots" in f.value.columns)
        self.assertEqual(source, "PDF 2. lapa, vektoru kandidāts P2-K1")

    def test_12100x3600_after_confirmation(self):
        at = confirm(transfer(start_bytes(sample(self.S02))), 0)
        self.assertEqual(metric(at, "Sijas moduļā (gab.)"), "22")
        self.assertEqual(metric(at, "Kokmateriāli moduļā"), "2.09088 m³")
        self.assertEqual(metric(at, "Atlikums (mm)"), "90")
        self.assertFalse(any("jāpārbauda" in w and "Atlikums" in w for w in warnings(at)))

    def test_two_modules_are_transferred_and_confirmed_separately(self):
        at = start_bytes(sample(self.S03))
        self.assertEqual([r["Statuss"] for r in vector_table(at)], ["ģeometriski saskaņots", "ģeometriski saskaņots"])
        at.number_input(key="ad_module_count").set_value(2).run()
        transfer(pick_candidate(at, "P1-K1"), 1)
        transfer(pick_candidate(at, "P1-K2"), 2)
        self.assertEqual([(at.number_input(key=f"ad_L_{i}").value, at.number_input(key=f"ad_W_{i}").value) for i in (0, 1)],
                         [(12000, 4000), (12000, 3600)])
        self.assertEqual(metrics(at), [])
        confirm(at, 0)
        self.assertTrue(any("NEPILNS APRĒĶINS (1 no 2" in w for w in warnings(at)))
        confirm(at, 1)
        self.assertEqual(metric(at, "Aprēķinātie moduļi"), "2")
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "42")           # 21 + 21
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "4.20528 m³")     # 2,15856 + 2,04672

    def test_transferring_another_candidate_cancels_the_confirmation(self):
        at = confirm(transfer(start_bytes(sample(self.S03))), 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")
        transfer(pick_candidate(at, "P1-K2"), 1)                          # tas pats modulis, citi L/W
        self.assertEqual(metrics(at), [])
        self.assertNotIn(0, at.session_state["ad_confirmations"])         # pārnešana dzēš apstiprinājumu
        self.assertTrue(any("gaida apstiprinājumu" in i.value.lower() for i in at.info))

    def test_retransferring_the_same_confirmed_candidate_clears_the_confirmation(self):
        # Fingerprint pēc atkārtotas pārnešanas būtu identisks: apstiprinājums tomēr jādzēš katrā pārnešanā.
        at = confirm(transfer(start_bytes(sample(self.S01))), 0)
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")
        transfer(at)                                                      # tā pati vērtība, tas pats kandidāts
        self.assertEqual((at.number_input(key="ad_L_0").value, at.number_input(key="ad_W_0").value), (12000, 4000))
        self.assertEqual(metrics(at), [])
        self.assertNotIn(0, at.session_state["ad_confirmations"])
        self.assertTrue(any("gaida apstiprinājumu" in i.value.lower() for i in at.info))
        confirm(at, 0)                                                    # jauns apstiprinājums atjauno aprēķinu
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³")

    def test_retransfer_clears_only_the_target_module_confirmation(self):
        at = start_bytes(sample(self.S03))
        at.number_input(key="ad_module_count").set_value(2).run()
        transfer(pick_candidate(at, "P1-K1"), 1)
        transfer(pick_candidate(at, "P1-K2"), 2)
        confirm(at, 0)
        confirm(at, 1)
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "42")
        transfer(pick_candidate(at, "P1-K2"), 2)                          # atkārtoti tas pats uz 2. moduli
        self.assertEqual(sorted(at.session_state["ad_confirmations"]), [0])
        self.assertTrue(any("NEPILNS APRĒĶINS (1 no 2" in w for w in warnings(at)))

    def test_one_candidate_cannot_be_counted_in_two_modules(self):
        at = start_bytes(sample(self.S03))
        at.number_input(key="ad_module_count").set_value(2).run()
        transfer(pick_candidate(at, "P1-K1"), 1)
        transfer(at, 2)                                                   # tas pats P1-K1 uz 2. moduli
        self.assertTrue(any("BRĪDINĀJUMS" in w and "jau ir izvēlēts 1" in w for w in warnings(at)))
        confirm(at, 0)
        confirm(at, 1)
        self.assertTrue(any("jau ir izmantots 1. modulī" in e and "bloķēta" in e for e in errors(at)))
        self.assertEqual(metric(at, "Sijas moduļā (gab.)"), "21")          # tikai pirmais modulis
        self.assertEqual([lab for lab, _ in metrics(at)].count("Sijas moduļā (gab.)"), 1)
        self.assertTrue(any("NEPILNS APRĒĶINS (1 no 2" in w for w in warnings(at)))
        labels = [lab for lab, _ in metrics(at)]
        self.assertNotIn("Sijas kopā (gab.)", labels)                     # nav kopsummas
        self.assertEqual(len(at.get("download_button")), 0)               # nav CSV

    def test_duplicate_is_resolved_by_choosing_a_different_candidate_or_manual_source(self):
        at = start_bytes(sample(self.S03))
        at.number_input(key="ad_module_count").set_value(2).run()
        transfer(pick_candidate(at, "P1-K1"), 1)
        transfer(at, 2)
        at.selectbox(key="ad_src_1").set_value("Ievadīts manuāli").run()   # apzināti manuāls modulis
        enter(at, 1, 12000, 3600)
        self.assertEqual(errors(at), [])
        confirm(at, 0)
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "42")
        self.assertFalse(any("NEPILNS" in w for w in warnings(at)))

    def test_manually_corrected_values_mark_the_source_as_corrected(self):
        at = transfer(start_bytes(sample(self.S01)))
        at.number_input(key="ad_L_0").set_value(12100).run()
        self.assertTrue(any("manuāli koriģēts" in w and "P2-K1" in w for w in warnings(at)))
        confirm(at, 0)
        source = next(f.value.to_dict("records")[0]["Avots"] for f in at.dataframe if "Avots" in f.value.columns)
        self.assertIn("vektoru kandidāts P2-K1", source)
        self.assertIn("MANUĀLI KORIĢĒTS", source)
        self.assertIn("12100×4000", source)
        self.assertIn("12000×4000", source)                                # kandidāta oriģinālā vērtība
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.20704 m³")    # aprēķins no ievadītā, ne no kandidāta

    def test_unchanged_transferred_values_are_not_marked_as_corrected(self):
        at = confirm(transfer(start_bytes(sample(self.S01))), 0)
        source = next(f.value.to_dict("records")[0]["Avots"] for f in at.dataframe if "Avots" in f.value.columns)
        self.assertEqual(source, "PDF 2. lapa, vektoru kandidāts P2-K1")
        self.assertFalse(any("manuāli koriģēts" in w for w in warnings(at)))

    def test_transfer_warnings_do_not_call_the_status_proven(self):
        at = start_bytes(sample(self.S01))
        self.assertTrue(any("nenozīmē konstruktīvi pierādītu" in w for w in warnings(at)))      # arī saskaņotam
        self.assertEqual({r["Statuss"] for r in vector_table(at)}, {"ģeometriski saskaņots"})
        self.assertNotIn("pierādīts", {r["Statuss"] for r in vector_table(at)})
        self.assertTrue(any("ģeometriski saskaņots" in c.value and "NEPIERĀDA" in c.value for c in at.caption))
        unclear = start_bytes(sample("ad_vector_05_scale_missing.pdf"))
        self.assertTrue(any("pierādījumu nepietiek" in w for w in warnings(unclear)))
        self.assertFalse(any("nenozīmē konstruktīvi" in w for w in warnings(unclear)))

    def test_changing_transferred_values_cancels_the_confirmation(self):
        at = confirm(transfer(start_bytes(sample(self.S01))), 0)
        at.number_input(key="ad_L_0").set_value(12100).run()
        self.assertEqual(metrics(at), [])
        self.assertTrue(any("apstiprinājums atcelts" in w for w in warnings(at)))

    def test_refused_candidates_cannot_be_transferred(self):
        for name, issue in (("ad_vector_04_L_shape_unclear.pdf", "nav taisnstūris"),
                            ("ad_vector_06_scale_conflict.pdf", "Mēroga pretruna")):
            at = start_bytes(sample(name))
            self.assertEqual(vector_table(at)[0]["Statuss"], "atteikums", name)
            row = vector_table(at)[0]
            self.assertTrue(pd.isna(row["L (mm)"]) and pd.isna(row["W (mm)"]), name)    # atteikums: L/W nav
            self.assertTrue(at.button(key="ad_vec_transfer").disabled, name)
            self.assertIn("L/W netiek piedāvāti", at.selectbox(key="ad_vec_pick").value)
            self.assertIn(issue, " ".join(m.value for m in at.markdown), name)
            self.assertEqual((at.number_input(key="ad_L_0").value, at.number_input(key="ad_W_0").value), (0, 0))
            enter(at, 0, 12000, 4000)                                      # manuālā ievade paliek pieejama
            self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.15856 m³", name)

    def test_unclear_candidates_are_transferable_with_a_warning(self):
        for name in ("ad_vector_05_scale_missing.pdf", "ad_vector_09_facade_and_inner_contour.pdf"):
            at = start_bytes(sample(name))
            self.assertEqual({r["Statuss"] for r in vector_table(at)}, {"neskaidrs"}, name)
            self.assertTrue(any("pierādījumu nepietiek" in w for w in warnings(at)), name)
            transfer(at)
            self.assertNotEqual(at.number_input(key="ad_L_0").value, 0, name)
            self.assertEqual(metrics(at), [], name)                        # joprojām jāapstiprina

    def test_pages_without_vectors_warn_and_manual_entry_works(self):
        at = start_bytes(sample("ad_vector_08_no_vector_geometry.pdf"))
        self.assertTrue(any("nav vektoru ģeometrijas" in w for w in warnings(at)))
        self.assertEqual(vector_table(at), [])
        self.assertEqual(len(at.get("image")), 0)
        enter(at, 0, 12100, 4000)
        self.assertEqual(metric(at, "Sijas kopā (gab.)"), "22")

    def test_manual_entry_is_independent_of_candidates(self):
        at = enter(start_bytes(sample(self.S01)), 0, 12100, 4000)         # nepiekrīt kandidātam 12000 × 4000
        self.assertEqual(metric(at, "Kokmateriāli kopā"), "2.20704 m³")
        source = next(f.value.to_dict("records")[0]["Avots"] for f in at.dataframe if "Avots" in f.value.columns)
        self.assertEqual(source, "Ievadīts manuāli")

    def test_removing_the_pdf_clears_vector_data_and_cancels_confirmation(self):
        at = confirm(transfer(start_bytes(sample(self.S01))), 0)
        self.assertIn("vector", at.session_state["ad_scan"]["scan"])
        at.file_uploader[0].set_value(None).run()
        self.assertNotIn("ad_scan", at.session_state)
        self.assertEqual(vector_table(at), [])
        self.assertEqual(len(at.get("image")), 0)
        self.assertEqual(metrics(at), [])                                  # PDF identitāte mainījusies

    def test_replacing_the_pdf_replaces_the_candidates(self):
        at = start_bytes(sample(self.S01))
        at.file_uploader[0].upload("other.pdf", sample(self.S02), "application/pdf").run()
        self.assertEqual([(r["Kandidāts"], r["L (mm)"], r["W (mm)"]) for r in vector_table(at)], [("P1-K1", 12100, 3600)])

    def test_pd_mode_is_unaffected_by_vector_samples(self):
        at = legacy_app(90)
        at.radio[0].set_value(PD_MODE).run()
        at.file_uploader[0].upload("sample.pdf", sample(self.S01), "application/pdf").run()
        self.assertFalse(at.exception)
        self.assertEqual(vector_table(at), [])
        self.assertFalse({w.key for w in at.number_input if w.key and w.key.startswith("ad_")})


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
