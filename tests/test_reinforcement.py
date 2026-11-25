"""Issue #10: pastiprinājuma sijas 150×240 (lietotāja norādītas) un grafiskā grīdas rāmja shēma.

Sintētiski dati. Gaidāmās vērtības ņemtas no Issue #10 kontrolvērtībām, nevis no koda izvades.
"""
import csv
import io
import re
import unittest
from fractions import Fraction
from pathlib import Path

from streamlit.testing.v1 import AppTest

import src.ad_ui  # noqa: F401
from src.ad_ui import parse_reinforcement_text
from src.floor_frame import (
    EXPORT_HEADER, ModuleSpec, calculate_module, calculate_modules, export_rows, summarize_modules,
)
from src.frame_diagram import build_frame_svg
from src.reinforcement import ReinforcementError, parse_axis

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def calc(axes=(), length=12000, width=4000, **kw):
    return calculate_module(length, width, name="T", reinforcements=axes, **kw)


class TestControlValues(unittest.TestCase):
    def test_base_unchanged(self):
        r = calc()
        self.assertEqual((r.total_pieces, r.total_volume_m3), (21, 2.15856))
        self.assertEqual((r.reinforcement_count, r.replaced_count, r.added_count), (0, 0, 0))
        self.assertEqual(r.regular_count, 17)

    def test_replace_first_regular(self):
        r = calc([822.5])
        self.assertEqual((r.total_pieces, r.total_volume_m3), (21, 2.24928))
        self.assertEqual((r.regular_count, r.replaced_count, r.added_count), (16, 1, 0))
        self.assertEqual(r.reinforcements[0].replaces, 1)

    def test_add_separate(self):
        # Issue #10: pamatrāmis + papildus ass 1150 → 22 gab., 2,28816 m³
        r = calc([1150])
        self.assertEqual((r.total_pieces, r.total_volume_m3), (22, 2.28816))
        self.assertEqual((r.regular_count, r.replaced_count, r.added_count), (17, 0, 1))

    def test_replace_and_add(self):
        r = calc([822.5, 1150])
        self.assertEqual((r.total_pieces, r.total_volume_m3), (22, 2.37888))
        self.assertEqual((r.regular_count, r.replaced_count, r.added_count), (16, 1, 1))

    def test_no_snapping_and_half_mm(self):
        for axis in (822.0, 823.0):
            with self.assertRaises(ReinforcementError) as cm:
                calc([axis])
            self.assertEqual(cm.exception.conflicts[0].code, "OVERLAP_REGULAR")
        self.assertEqual(calc(["822,5"]).replaced_count, 1)
        self.assertEqual(calc([Fraction(1645, 2)]).replaced_count, 1)
        with self.assertRaises(ValueError):
            parse_axis("822.555")        # netiek noapaļots


class TestConflicts(unittest.TestCase):
    def codes(self, axes, **kw):
        with self.assertRaises(ReinforcementError) as cm:
            calc(axes, **kw)
        return {c.code for c in cm.exception.conflicts}

    def test_duplicate(self):
        self.assertIn("DUPLICATE_AXIS", self.codes([1150, 1150]))
        self.assertIn("DUPLICATE_AXIS", self.codes([1150, "1150,0"]))

    def test_outside_and_end_beams(self):
        self.assertIn("OUTSIDE_FREE_FRAME", self.codes([100]))
        self.assertIn("OUTSIDE_FREE_FRAME", self.codes([11950]))
        self.assertIn("OUTSIDE_FREE_FRAME", self.codes([13000]))

    def test_overlap_reinforcements(self):
        self.assertIn("OVERLAP_REINFORCEMENT", self.codes([1150, 1250]))

    def test_unsupported_height_and_too_many(self):
        from src.floor_frame import FrameParams
        self.assertTrue(self.codes([1150], params=FrameParams(beam_height_mm=300), nonstandard_confirmed=True))
        self.assertIn("TOO_MANY", self.codes(list(range(300, 300 + 21 * 200, 200))))

    def test_touching_allowed_with_warning(self):
        r = calc([1150, 1300])             # attālums 150 = sijas platums → pieskaras
        self.assertEqual(r.added_count, 2)
        self.assertTrue(any("ZERO_GAP" in w.code for w in r.warnings))

    def test_blocked_error_in_batch_names_module(self):
        with self.assertRaises(ValueError) as cm:
            calculate_modules([ModuleSpec(12000, 4000, name="M1", reinforcements=(100,))])
        self.assertIn("M1", str(cm.exception))

    def test_invalid_parse(self):
        axes, errors = parse_reinforcement_text("822,5\nabc\n-5\n0\n1150")
        self.assertEqual(len(errors), 3)
        self.assertEqual(axes, [Fraction(1645, 2), Fraction(1150)])
        self.assertEqual(parse_reinforcement_text("")[0], [])


class TestMultiModuleAndCsv(unittest.TestCase):
    def test_sums_and_csv(self):
        a, b = calc([822.5, 1150]), calc()
        total = summarize_modules([a, b])
        self.assertEqual((total["pieces"], total["volume_m3"]), (22 + 21, round(2.37888 + 2.15856, 6)))
        self.assertEqual((total["replaced"], total["added"], total["modules_with_reinforcements"]), (1, 1, 1))
        rows = export_rows([a, b])
        self.assertEqual(rows[0], EXPORT_HEADER)
        text = "\n".join(";".join(map(str, r)) for r in rows)
        self.assertEqual(text.count("Pastiprinājums 150×240 (aizvieto regulāro)"), 1)
        self.assertEqual(text.count("Pastiprinājums 150×240 (papildus)"), 1)
        self.assertIn("Lietotāja manuāli norādīts", text)
        self.assertIn("pamatrāmis + lietotāja pastiprinājumi", text)
        self.assertIn("822.5", text)

    def test_base_export_header_prefix_unchanged(self):
        self.assertEqual(EXPORT_HEADER[:11], ["Modulis", "Elements", "b_mm", "h_mm", "L_mm", "Gab", "Apjoms_m3",
                                              "Pamatojums", "Atlikums_mm", "Japarbauda", "Avots"])
        self.assertTrue(any("tikai pamatrāmis" in str(r[0]).lower() for r in export_rows([calc()])))


class TestDiagramMatchesCalc(unittest.TestCase):
    def rects(self, svg, kind):
        return re.findall(r'<rect[^>]*data-kind="%s"[^>]*>' % kind, svg)

    def test_svg_geometry(self):
        r = calc([822.5, 1150, 11500])
        svg = build_frame_svg(r)
        k = float(re.search(r'data-scale-px-per-mm="([\d.]+)"', svg).group(1))
        y0 = float(re.search(r'data-origin-y="([\d.]+)"', svg).group(1))
        self.assertIn('viewBox', svg)
        self.assertNotIn("http://", svg.replace("http://www.w3.org/2000/svg", ""))
        for m in r.members:
            tag = re.search(r'<rect[^>]*data-label="%s"[^>]*>' % m.label, svg)
            self.assertIsNotNone(tag, m.label)
            y = float(re.search(r' y="([\d.]+)"', tag.group(0)).group(1))
            self.assertAlmostEqual((y - y0) / k, float(m.start), delta=0.6)
        for pl in r.reinforcements:
            self.assertIn(f'data-label="{pl.label}"', svg)
        self.assertEqual(svg.count('data-kind="legend"'), 5)
        for word in ("AIZVIETO", "PAPILDUS", "nav realizētas"):
            self.assertIn(word, svg)

    def test_base_has_no_reinforcement_legend(self):
        svg = build_frame_svg(calc())
        self.assertNotIn("PAPILDUS", svg)
        self.assertIn("Pastiprinājumi nav norādīti", svg)


# ---- UI (AppTest) ---------------------------------------------------------------------------
def app(L=12000, W=4000, axes=None, confirm_rf=True):
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.number_input(key="ad_L_0").set_value(L).run()
    at.number_input(key="ad_W_0").set_value(W).run()
    at.button(key="ad_confirm_0").click().run()
    if axes is not None:
        at.text_area(key="ad_rf_0").set_value(axes).run()
        if confirm_rf and any(c.key and c.key.startswith("ad_rfok_0_") for c in at.checkbox):
            rf_check(at).check().run()
    return at


def rf_check(at):
    return next(c for c in at.checkbox if c.key and c.key.startswith("ad_rfok_0_"))


def metric_values(at):
    return {m.label: m.value for m in at.metric}


class TestUi(unittest.TestCase):
    def test_base_without_reinforcements(self):
        at = app()
        self.assertEqual(metric_values(at)["Sijas kopā (gab.)"], "21")
        self.assertEqual([m.value for m in at.metric][2], "2.15856 m³")
        self.assertTrue(any("NEpierāda" in c.value or "nav vajadzīgi" in c.value for c in at.caption))

    def test_reinforcement_needs_confirmation(self):
        at = app(axes="822,5\n1150", confirm_rf=False)
        self.assertEqual(list(at.metric), [])
        self.assertTrue(any("NEPILNS" in w.value for w in at.warning))
        rf_check(at).check().run()
        self.assertEqual(metric_values(at)["Sijas kopā (gab.)"], "22")
        self.assertIn("2.37888", [m.value for m in at.metric][2])

    def test_changing_position_cancels_confirmation(self):
        at = app(axes="822,5\n1150")
        self.assertEqual(len(at.metric) > 0, True)
        at.text_area(key="ad_rf_0").set_value("822,5\n1200").run()
        self.assertFalse(rf_check(at).value)
        self.assertEqual(list(at.metric), [])
        at.text_area(key="ad_rf_0").set_value("822,5\n1150").run()      # A→B→A: nav atjaunots
        self.assertFalse(rf_check(at).value)

    def test_invalid_and_conflicting_block_export(self):
        at = app(axes="abc")
        self.assertTrue(at.error)
        self.assertEqual(list(at.metric), [])
        self.assertEqual(list(at.get("download_button")), [])
        at = app(axes="822\n")
        self.assertTrue(any("pārklājas" in e.value for e in at.error))
        self.assertEqual(list(at.metric), [])
        self.assertEqual(list(at.get("download_button")), [])

    def test_changing_dimensions_cancels_rf_confirmation(self):
        at = app(axes="1150")
        at.number_input(key="ad_L_0").set_value(12100).run()
        self.assertFalse(rf_check(at).value)

    def test_svg_rendered_and_download_present(self):
        at = app(axes="822,5\n1150")
        self.assertTrue(any("<svg" in m.value for m in at.markdown))
        self.assertEqual(len(at.get("download_button")), 1)


if __name__ == "__main__":
    unittest.main()
