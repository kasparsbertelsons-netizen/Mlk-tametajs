"""Grīdas pamatrāmja aprēķina kodola testi (src/floor_frame.py, Issue #4).

Tikai sintētiski dati. Sagaidāmās vērtības ir aprēķinātas ar roku un ierakstītas
kā konstantes; tās netiek iegūtas no testējamā koda. Noteikumi: skat.
docs/FLOOR_FRAME_CORE.md.
"""
import dataclasses
import unittest

from src.floor_frame import (
    DEFAULT_PARAMS, FrameParams, ModuleSpec, calculate_module, calculate_modules,
    export_rows, layout_problems, summarize_modules,
)


def codes(result):
    return {w.code for w in result.warnings}


def rows_by_name(result):
    return {row.element: row for row in result.rows}


class TestAcceptanceExamples(unittest.TestCase):
    """Issue #4 pieņemšanas piemēri."""

    def test_12000x4000(self):
        # brīvais 11600; ⌊11600/645⌋ = 17; atlikums 11600 − 10965 = 635 (> 600 → jāpārbauda)
        # 1,152 + 0,3456 + 17·0,03888 (=0,66096) = 2,15856 m³
        r = calculate_module(12000, 4000)
        self.assertEqual(r.cross_count, 17)
        self.assertEqual(r.remainder_mm, 635)
        self.assertEqual(r.total_pieces, 21)
        self.assertEqual(r.total_volume_m3, 2.15856)
        self.assertEqual(codes(r), {"REMAINDER_OVER_GAP"})
        self.assertTrue(r.needs_review)
        rows = rows_by_name(r)
        self.assertEqual((rows["Garās perimetra sijas"].width_mm, rows["Garās perimetra sijas"].height_mm,
                          rows["Garās perimetra sijas"].length_mm, rows["Garās perimetra sijas"].count),
                         (200, 240, 12000, 2))
        self.assertEqual((rows["Gala sijas"].length_mm, rows["Gala sijas"].count), (3600, 2))
        cross = rows["Regulārās šķērssijas"]
        self.assertEqual((cross.width_mm, cross.height_mm, cross.length_mm, cross.count), (45, 240, 3600, 17))
        self.assertEqual(cross.volume_m3, 0.66096)
        self.assertEqual(rows["Garās perimetra sijas"].volume_m3, 1.152)
        self.assertEqual(rows["Gala sijas"].volume_m3, 0.3456)

    def test_12100x4000(self):
        # brīvais 11700; ⌊11700/645⌋ = 18 (11610); atlikums 90; 2,20704 m³; 22 gab.
        r = calculate_module(12100, 4000)
        self.assertEqual((r.cross_count, r.remainder_mm, r.total_pieces), (18, 90, 22))
        self.assertEqual(r.total_volume_m3, 2.20704)
        self.assertEqual(codes(r), set())
        self.assertFalse(r.needs_review)

    def test_width_3600(self):
        # W − 400 = 3200 gala un šķērssijām; 1,152 + 2·0,2·0,24·3,2 (=0,3072) + 17·0,045·0,24·3,2 (=0,58752)
        r = calculate_module(12000, 3600)
        rows = rows_by_name(r)
        self.assertEqual(rows["Gala sijas"].length_mm, 3200)
        self.assertEqual(rows["Regulārās šķērssijas"].length_mm, 3200)
        self.assertEqual(r.cross_count, 17)
        self.assertEqual(r.total_volume_m3, 2.04672)

    def test_two_modules_are_summed_separately(self):
        # A 12000×4000: 21 gab., 2,15856 m³; B 12100×3600: 22 gab., 2,09088 m³ → 43 gab., 4,24944 m³
        results = calculate_modules([ModuleSpec(12000, 4000, "A"), ModuleSpec(12100, 3600, "B")])
        self.assertEqual([r.total_pieces for r in results], [21, 22])
        self.assertEqual([r.total_volume_m3 for r in results], [2.15856, 2.09088])
        self.assertEqual([r.remainder_mm for r in results], [635, 90])
        total = summarize_modules(results)
        self.assertEqual((total["modules"], total["pieces"], total["volume_m3"], total["needs_review"]),
                         (2, 43, 4.24944, 1))

    def test_integer_valued_floats_are_accepted(self):
        self.assertEqual(calculate_module(12000.0, 4000.0).total_volume_m3, 2.15856)

    def test_default_perimeter_is_labelled(self):
        r = calculate_module(12000, 4000)
        self.assertTrue(r.params_default)
        self.assertTrue(any("NOKLUSĒJUMS" in note for note in r.notes))
        self.assertIn("Noklusējums", r.rows[0].basis)


class TestBoundaries(unittest.TestCase):
    """Atlikuma robežas; n = 10 → L = 400 + 6450 + atlikums."""

    def test_remainder_exactly_600_has_no_warning(self):
        r = calculate_module(7450, 4000)
        self.assertEqual((r.cross_count, r.remainder_mm), (10, 600))
        self.assertEqual(codes(r), set())

    def test_remainder_601_warns(self):
        r = calculate_module(7451, 4000)
        self.assertEqual((r.cross_count, r.remainder_mm), (10, 601))
        self.assertEqual(codes(r), {"REMAINDER_OVER_GAP"})

    def test_remainder_zero_warns_and_is_not_called_approved(self):
        r = calculate_module(6850, 4000)
        self.assertEqual((r.cross_count, r.remainder_mm), (10, 0))
        self.assertEqual(codes(r), {"REMAINDER_ZERO"})
        message = next(w.message for w in r.warnings if w.code == "REMAINDER_ZERO")
        self.assertIn("jāpārbauda", message)
        self.assertIn("nav apstiprināts", message)

    def test_remainder_one_has_no_warning(self):
        r = calculate_module(6851, 4000)
        self.assertEqual((r.cross_count, r.remainder_mm), (10, 1))
        self.assertEqual(codes(r), set())

    def test_one_below_pitch_gives_no_joist(self):
        # brīvais 644 < 645: n = 0, atlikums 644 (> 600); sija netiek pievienota
        r = calculate_module(1044, 4000)
        self.assertEqual((r.cross_count, r.remainder_mm, r.total_pieces), (0, 644, 4))
        self.assertEqual(codes(r), {"NO_CROSS_JOISTS", "REMAINDER_OVER_GAP"})
        self.assertEqual(r.cross_positions, ())

    def test_exactly_one_pitch_gives_one_joist_and_zero_remainder(self):
        r = calculate_module(1045, 4000)
        self.assertEqual((r.cross_count, r.remainder_mm, r.total_pieces), (1, 0, 5))
        self.assertEqual(r.cross_positions, ((800, 845),))
        self.assertEqual(codes(r), {"REMAINDER_ZERO"})

    def test_width_4500_is_not_flagged_4501_is(self):
        self.assertNotIn("WIDTH_OVER_LIMIT", codes(calculate_module(12000, 4500)))
        flagged = calculate_module(12000, 4501)
        self.assertIn("WIDTH_OVER_LIMIT", codes(flagged))
        self.assertIn("nav absolūta", next(w.message for w in flagged.warnings
                                          if w.code == "WIDTH_OVER_LIMIT"))

    def test_width_above_limit_is_still_calculated(self):
        # Robeža ir orientējoša: kodols aprēķina un brīdina; apstiprināšana ir UI līmenī.
        r = calculate_module(12000, 4600)
        self.assertEqual(rows_by_name(r)["Gala sijas"].length_mm, 4200)
        self.assertEqual(r.total_volume_m3, 2.32632)


class TestInvalidInput(unittest.TestCase):
    def assert_rejected(self, *args, **kwargs):
        with self.assertRaises(ValueError):
            calculate_module(*args, **kwargs)

    def test_non_positive(self):
        for bad in (0, -1, -12000):
            self.assert_rejected(bad, 4000)
            self.assert_rejected(12000, bad)

    def test_non_integer_millimetres(self):
        self.assert_rejected(12000.5, 4000)
        self.assert_rejected(12000, 4000.25)

    def test_not_a_number(self):
        for bad in (float("nan"), float("inf"), "12000", None, True, [12000]):
            self.assert_rejected(bad, 4000)
            self.assert_rejected(12000, bad)

    def test_absurdly_large(self):
        self.assert_rejected(10_000_000_000, 4000)

    def test_width_too_small_for_end_beams(self):
        self.assert_rejected(12000, 400)   # W − 400 = 0
        self.assert_rejected(12000, 399)
        self.assertEqual(rows_by_name(calculate_module(12000, 401))["Gala sijas"].length_mm, 1)

    def test_length_too_small_for_end_beams(self):
        self.assert_rejected(400, 4000)    # L − 400 = 0
        self.assert_rejected(399, 4000)

    def test_error_message_names_the_problem(self):
        with self.assertRaisesRegex(ValueError, "Platums W"):
            calculate_module(12000, 400)
        with self.assertRaisesRegex(ValueError, "Garums L"):
            calculate_module(0, 4000)

    def test_calculate_modules_names_the_failing_module(self):
        with self.assertRaisesRegex(ValueError, "Slikts modulis"):
            calculate_modules([ModuleSpec(12000, 4000, "Labs"), ModuleSpec(0, 4000, "Slikts modulis")])

    def test_nonstandard_params_need_confirmation(self):
        params = FrameParams(perimeter_width_mm=150)
        self.assert_rejected(12000, 4000, params=params)
        self.assert_rejected(12000, 4000, params=params, nonstandard_confirmed=False)

    def test_nonstandard_params_when_confirmed(self):
        # perimetrs 150: brīvais 11700; ⌊11700/645⌋ = 18; atlikums 90; gala/šķērs. 3700
        # (2·150·240·12000 + 2·150·240·3700 + 18·45·240·3700)/1e9 = 1,84968 m³
        r = calculate_module(12000, 4000, params=FrameParams(perimeter_width_mm=150),
                             nonstandard_confirmed=True)
        self.assertFalse(r.params_default)
        self.assertEqual((r.cross_count, r.remainder_mm, r.total_pieces), (18, 90, 22))
        self.assertEqual(r.total_volume_m3, 1.84968)
        self.assertIn("NONSTANDARD_PARAMS", codes(r))
        self.assertEqual(layout_problems(r), [])

    def test_invalid_params_rejected_even_if_confirmed(self):
        for params in (FrameParams(perimeter_width_mm=0), FrameParams(clear_gap_mm=-5),
                       FrameParams(cross_width_mm=0)):
            self.assert_rejected(12000, 4000, params=params, nonstandard_confirmed=True)
        self.assert_rejected(12000, 4000, params="200", nonstandard_confirmed=True)


class TestLayoutPlacement(unittest.TestCase):
    def test_positions_12000(self):
        # 1. šķērssija: 200 + 600 = 800…845; tālāk +645; 17. beidzas pie 200 + 17·645 = 11165
        r = calculate_module(12000, 4000)
        self.assertEqual(r.cross_positions[0], (800, 845))
        self.assertEqual(r.cross_positions[1], (1445, 1490))
        self.assertEqual(r.cross_positions[-1], (11120, 11165))
        self.assertEqual(len(r.cross_positions), 17)
        # pēdējā atstarpe līdz gala sijas iekšmalai (11800): 11800 − 11165 = 635
        self.assertEqual(11800 - r.cross_positions[-1][1], 635)

    def test_no_redistribution_and_no_extra_joist(self):
        r = calculate_module(12000, 4000)
        gaps = [b[0] - a[1] for a, b in zip(r.cross_positions, r.cross_positions[1:])]
        self.assertEqual(set(gaps), {600})
        # 18. sija sāktos pie 11165 + 600 = 11765 un beigtos pie 11810 > 11800
        self.assertGreater(r.cross_positions[-1][1] + 600 + 45, 12000 - 200)

    def test_layout_valid_over_many_sizes(self):
        for length in range(1000, 30001, 37):
            for width in (3000, 3600, 4000, 4500, 5000):
                r = calculate_module(length, width)
                self.assertEqual(layout_problems(r), [], (length, width))
                self.assertEqual(r.total_pieces, 4 + r.cross_count)
                # nākamā sija neietilpst: tad atlikums < solis (645)
                if r.cross_positions:
                    last_end = r.cross_positions[-1][1]
                    self.assertGreater(last_end + 600 + 45, length - 200, (length, width))
                else:
                    self.assertGreater(645, length - 400)

    def test_checker_detects_overlap_with_end_beam(self):
        good = calculate_module(12000, 4000)
        moved = good.cross_positions[:-1] + ((11800, 11845),)   # ieiet gala sijā
        broken = dataclasses.replace(good, cross_positions=moved)
        self.assertTrue(layout_problems(broken))

    def test_checker_detects_wrong_gap_and_count(self):
        good = calculate_module(12000, 4000)
        shifted = dataclasses.replace(
            good, cross_positions=((810, 855),) + good.cross_positions[1:])
        self.assertTrue(layout_problems(shifted))
        short = dataclasses.replace(good, cross_positions=good.cross_positions[:-1])
        self.assertTrue(layout_problems(short))

    def test_default_params_constant(self):
        self.assertEqual(DEFAULT_PARAMS, FrameParams(200, 240, 45, 600))
        self.assertEqual(DEFAULT_PARAMS.pitch_mm, 645)


class TestExport(unittest.TestCase):
    def test_rows_and_total(self):
        results = calculate_modules([ModuleSpec(12000, 4000, "A"), ModuleSpec(12100, 3600, "B")])
        rows = export_rows(results)
        self.assertEqual(rows[0][0], "Modulis")
        self.assertEqual(len(rows), 1 + 6 + 1)             # galvene + 2×3 rindas + KOPĀ
        self.assertEqual(rows[-1][0], "KOPĀ (tikai pamatrāmis)")
        self.assertEqual(rows[-1][5], 43)
        self.assertEqual(rows[-1][6], "4.249440")
        self.assertEqual({row[8] for row in rows[1:4]}, {635})
        self.assertEqual({row[9] for row in rows[1:4]}, {"JĀ"})
        self.assertEqual({row[9] for row in rows[4:7]}, {""})

    def test_formula_injection_is_neutralised(self):
        result = calculate_module(12000, 4000, name="=HYPERLINK(\"x\")", source="@cmd")
        rows = export_rows([result])
        self.assertTrue(rows[1][0].startswith("'="))
        self.assertTrue(rows[1][10].startswith("'@"))


if __name__ == "__main__":
    unittest.main()
