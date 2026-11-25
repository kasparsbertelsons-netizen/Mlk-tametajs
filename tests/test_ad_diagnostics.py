"""AD lokālās diagnostikas bibliotēkas testi (src/ad_diagnostics.py, Issue #8). Tikai sintētiski dati.

Sanitizācija tiek testēta ar sintētiskiem SENSITĪVIEM MARĶIERIEM (KLIENTS-SECRET-…), neparastiem izmēriem un
izņēmumiem: kopsavilkumā nedrīkst parādīties neviens marķieris, izmērs, ceļš, hash vai kļūdas teksts.
"""
import hashlib
import json
import re
import unittest
from unittest import mock

import pymupdf

from src import ad_diagnostics as diag
from tests.synthetic_pdfs import SECRET, custom_pdf, plan_view_pdf, sensitive_pdf
from tools import synthetic_ad_pdf as gen


def run(data, **kwargs):
    return diag.run_diagnostics(data, **kwargs)


def summary_of(data, **kwargs):
    return diag.build_sanitized_summary(run(data, **kwargs))


class TestParsing(unittest.TestCase):
    def test_page_lists(self):
        self.assertEqual(diag.parse_page_list("3"), [3])
        self.assertEqual(diag.parse_page_list("5, 3,3"), [3, 5])
        self.assertEqual(diag.parse_page_list("3-6,9"), [3, 4, 5, 6, 9])

    def test_invalid_page_lists(self):
        for bad in ("", "0", "a", "5-3", "1-99999", "3;5", "-2"):
            with self.assertRaises(diag.DiagnosticsError, msg=bad):
                diag.parse_page_list(bad)

    def test_controls_are_normalised_and_validated(self):
        self.assertEqual(diag.parse_control("12000x4000"), (12000, 4000))
        self.assertEqual(diag.parse_control(" 4000 × 12000 "), (12000, 4000))
        self.assertEqual(diag.parse_control("12000*4000"), (12000, 4000))
        for bad in ("12000", "axb", "12000x", "50x50", "12000x999999", "12000,4000", "-12000x4000"):
            with self.assertRaises(diag.DiagnosticsError, msg=bad):
                diag.parse_control(bad)


class TestPageSelection(unittest.TestCase):
    def test_auto_selects_floor_plan_pages_only(self):
        report = run(gen.build_sample_01())
        self.assertEqual((report["selection"]["mode"], report["selection"]["pages"]), ("auto", [2]))
        self.assertEqual([p["text_class"] for p in report["pages"]], ["list", "floor", "roof"])
        self.assertEqual(list(report["analyses"]), [2])

    def test_every_page_gets_vector_counts_even_when_not_analysed(self):
        pages = {p["page"]: p["vectors"] for p in run(gen.build_sample_01())["pages"]}
        self.assertEqual(pages[1]["drawing_paths"], 0)                       # titullapa: tikai teksts
        self.assertEqual((pages[2]["contour_rectangle"], pages[2]["segment_horizontal"], pages[2]["segment_vertical"]), (5, 5, 7))
        self.assertGreater(pages[3]["drawing_paths"], 0)                      # jumta lapa arī skaitīta, bet netiek analizēta

    def test_manual_page_is_analysed_even_if_the_classifier_misses_it(self):
        data = plan_view_pdf()
        auto = run(data)
        self.assertEqual((auto["selection"]["mode"], auto["selection"]["pages"], auto["analyses"]), ("none", [], {}))
        self.assertTrue(any("--page N" in note for note in auto["selection"]["notes"]))
        self.assertEqual(auto["pages"][0]["text_class"], "other")
        manual = run(data, pages=[1])
        self.assertEqual((manual["selection"]["mode"], manual["selection"]["pages"]), ("manual", [1]))
        candidate = manual["analyses"][1]["candidates"][0]
        self.assertEqual((candidate["length_mm"], candidate["width_mm"]), (12000, 4000))

    def test_manual_page_overrides_roof_and_list_classification_with_a_note(self):
        report = run(gen.build_sample_01(), pages=[1, 3])
        self.assertEqual(sorted(report["analyses"]), [1, 3])
        self.assertEqual(report["analyses"][1]["status"], "no_vector_geometry")
        self.assertEqual(len(report["selection"]["notes"]), 2)
        self.assertTrue(any("'roof'" in n and "pēc jūsu norādes" in n for n in report["selection"]["notes"]))
        roof = report["analyses"][3]["candidates"][0]
        self.assertEqual((roof["length_mm"], roof["width_mm"]), (12600, 4600))     # redzams, ka tā ir jumta pārkare

    def test_out_of_range_pages_are_reported_not_analysed(self):
        report = run(gen.build_sample_01(), pages=[2, 9])
        self.assertEqual((report["selection"]["pages"], report["selection"]["invalid_pages"]), ([2], [9]))

    def test_all_pages(self):
        report = run(gen.build_sample_01(), all_pages=True)
        self.assertEqual((report["selection"]["mode"], sorted(report["analyses"])), ("all", [1, 2, 3]))


class TestReportDistinguishesReadFromControl(unittest.TestCase):
    def test_controls_are_stored_separately_from_read_candidates(self):
        report = run(gen.build_sample_01(), controls=[(9999, 3333)])
        self.assertEqual(report["controls"], [{"length_mm": 9999, "width_mm": 3333}])
        read_values = json.dumps(report["analyses"])
        self.assertNotIn("9999", read_values)               # kontrolizmērs nekad nenonāk "nolasītajā" daļā
        self.assertNotIn("3333", read_values)

    def test_comparison_entries_keep_both_values(self):
        report = run(gen.build_sample_01(), controls=[(12100, 4000)])
        entry = report["comparison"]["entries"][0]
        self.assertEqual(entry["control"], {"length_mm": 12100, "width_mm": 4000})
        self.assertEqual(entry["candidate"]["length_mm"], 12000)
        self.assertEqual(entry["deviation_mm"], {"length": -100, "width": 0})
        self.assertEqual((entry["category"], entry["deviation_pct"]), ("small", 0.83))


class TestControlComparison(unittest.TestCase):
    @staticmethod
    def cand(cid, length, width):
        return (1, {"id": cid, "length_mm": length, "width_mm": width, "status": "neskaidrs"})

    def category(self, control, candidate=(12000, 4000)):
        result = diag.compare_controls([self.cand("K1", *candidate)], [control])
        return result["entries"][0]["category"]

    def test_category_boundaries(self):
        self.assertEqual(self.category((12000, 4000)), "match")
        self.assertEqual(self.category((12060, 4000)), "match")       # 60/12060 = 0,50 %
        self.assertEqual(self.category((12100, 4000)), "small")       # 0,83 %
        self.assertEqual(self.category((12240, 4000)), "small")       # 240/12240 = 1,96 %
        self.assertEqual(self.category((12300, 4000)), "medium")      # 2,44 %
        self.assertEqual(self.category((13300, 4000)), "medium")      # 9,77 %
        self.assertEqual(self.category((13500, 4000)), "large")       # 11,1 %
        self.assertEqual(self.category((12000, 4600)), "large")       # novirze pa W

    def test_each_candidate_is_used_once(self):
        result = diag.compare_controls([self.cand("K1", 12000, 4000)], [(12000, 4000), (12000, 4000)])
        self.assertEqual([e["category"] for e in result["entries"]], ["match", "no_candidate"])
        self.assertEqual(result["counts"]["no_candidate"], 1)

    def test_best_pairing_and_leftover_candidates(self):
        result = diag.compare_controls([self.cand("A", 12000, 4000), self.cand("B", 9000, 3000), self.cand("C", 7000, 2500)],
                                       [(9010, 3000), (12000, 4000)])
        self.assertEqual([(e["candidate_id"], e["category"]) for e in result["entries"]], [("B", "match"), ("A", "match")])
        self.assertEqual(result["candidates_without_control"], ["C"])

    def test_no_candidates_means_no_candidate_never_invented(self):
        result = diag.compare_controls([], [(12000, 4000)])
        self.assertEqual(result["entries"][0]["candidate"], None)
        self.assertEqual(result["counts"], {"match": 0, "small": 0, "medium": 0, "large": 0, "no_candidate": 1})

    def test_untransferable_candidates_are_not_compared(self):
        report = run(gen.build_sample_04(), controls=[(12000, 7000)])        # L-forma: atteikums, L/W nav
        self.assertEqual(report["comparison"]["entries"][0]["category"], "no_candidate")


class TestReasonCodesAndCounts(unittest.TestCase):
    def codes(self, data, **kw):
        counts = summary_of(data, **kw)["reason_code_counts"]
        return {k: v for k, v in counts.items() if v}

    def test_no_vectors(self):
        summary = summary_of(gen.build_sample_08())
        self.assertEqual(summary["reason_code_counts"]["NO_VECTOR_GEOMETRY"], 2)
        self.assertEqual(summary["page_status_counts"], {"ok": 0, "no_vector_geometry": 2, "error": 0})
        self.assertEqual(sum(summary["vector_kind_counts"].values()), 0)
        self.assertEqual((summary["candidates_total"], summary["recognised_modules"]), (0, 0))

    def test_l_shape(self):
        summary = summary_of(gen.build_sample_04())
        self.assertEqual(summary["status_counts"]["refused"], 1)
        self.assertEqual(self.codes(gen.build_sample_04()), {"SHAPE_NOT_RECTANGLE": 1})
        self.assertEqual(summary["vector_kind_counts"]["contour_polygon"], 1)
        self.assertEqual(summary["recognised_modules"], 0)

    def test_scale_conflict_and_missing_scale(self):
        self.assertEqual(self.codes(gen.build_sample_06()), {"SCALE_CONFLICT": 1})
        self.assertEqual(self.codes(gen.build_sample_05()), {"SCALE_NOT_DECLARED": 1})
        self.assertEqual(summary_of(gen.build_sample_05())["recognised_modules"], 1)

    def test_other_reason_codes(self):
        self.assertEqual(self.codes(gen.build_sample_09()), {"NESTED_CONTOURS": 2})
        self.assertEqual(self.codes(gen.build_sample_03(separator=False)), {"ADJACENT_BOUNDARY_NOT_MARKED": 2})
        self.assertEqual(self.codes(gen.build_sample_01(module_label=False)), {"NO_MODULE_LABEL": 1})

    def test_clean_sample_has_no_reason_codes(self):
        summary = summary_of(gen.build_sample_01())
        self.assertEqual(self.codes(gen.build_sample_01()), {})
        self.assertEqual(summary["status_counts"]["consistent"], 1)
        self.assertEqual(summary["excluded_counts"], {"room": 1, "terrace": 1, "nested": 0, "unmeasured": 1, "page_frame": 1})
        self.assertEqual((summary["pages_total"], summary["pages_analyzed"], summary["dimension_annotations_total"]), (3, 1, 4))

    def test_no_candidates_on_a_page_with_vectors(self):
        def draw(sheet):
            sheet.rect(150, 260, 800, 480)                                   # kontūra bez izmēru norādēm
        self.assertEqual(self.codes(custom_pdf(draw)), {"NO_CANDIDATES": 1})

    def test_comparison_and_module_counts(self):
        summary = summary_of(gen.build_sample_03(), controls=[(12000, 4000), (12000, 3650), (5000, 2000)])
        self.assertEqual((summary["recognised_modules"], summary["controlled_modules"]), (2, 3))
        self.assertEqual(summary["control_comparison"], {"match": 1, "small": 1, "medium": 0, "large": 0, "no_candidate": 1})


class TestInputProblems(unittest.TestCase):
    def test_not_a_pdf(self):
        report = run(b"KLIENTS-SECRET this is not a pdf")
        self.assertEqual(report["input"]["status"], "invalid_pdf")
        summary = diag.build_sanitized_summary(report)
        self.assertEqual((summary["input_status"], summary["pages_total"], summary["pages_selection"]), ("invalid_pdf", 0, "none"))
        self.assertNotIn(SECRET, diag.summary_json(summary))

    def test_corrupt_pdf(self):
        report = run(b"%PDF-1.7\n" + b"\x00\xff garbage " * 20)
        self.assertIn(report["input"]["status"], ("unreadable", "ok"))   # PyMuPDF var atjaunot; nedrīkst izmest kļūdu
        diag.build_sanitized_summary(report)

    def test_encrypted_pdf(self):
        doc = pymupdf.open()
        doc.new_page()
        data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-secret", user_pw="user-secret")
        report = run(data)
        self.assertEqual(report["input"]["status"], "encrypted")
        self.assertEqual(diag.build_sanitized_summary(report)["input_status"], "encrypted")

    def test_too_many_pages(self):
        with mock.patch.object(diag, "MAX_PAGES", 2):
            self.assertEqual(run(gen.build_sample_01())["input"]["status"], "too_many_pages")

    def test_page_description_failure_is_contained(self):
        with mock.patch.object(diag, "page_vector_summary", side_effect=RuntimeError(f"{SECRET}-DESCRIBE C:\\Klients\\x.pdf")):
            report = run(gen.build_sample_01())
        self.assertTrue(all(p["describe_error"] for p in report["pages"]))
        self.assertIn(SECRET, report["pages"][0]["describe_error"])        # vietējā pārskatā redzams (lokāli)
        self.assertNotIn(SECRET, diag.summary_json(diag.build_sanitized_summary(report)))

    def test_analysis_exception_gives_only_a_code_in_the_summary(self):
        message = f"{SECRET}-ERROR-TEXT C:\\Klients\\Projekts\\fails.pdf 12345"
        with mock.patch.object(diag, "analyze_page", side_effect=RuntimeError(message)):
            report = run(gen.build_sample_01())
        self.assertEqual(report["analyses"][2]["status"], "error")
        self.assertIn(SECRET, report["analyses"][2]["notes"][0])           # lokāli redzams
        summary = diag.build_sanitized_summary(report)
        self.assertEqual(summary["page_status_counts"]["error"], 1)
        self.assertEqual(summary["reason_code_counts"]["PAGE_ERROR"], 1)
        dumped = diag.summary_json(summary)
        for leaked in (SECRET, "Klients", "fails.pdf", "12345", "ERROR-TEXT"):
            self.assertNotIn(leaked, dumped)


class TestSanitisedSummaryContainsNoSensitiveData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = sensitive_pdf()
        cls.report = run(cls.data, controls=[(12399, 4300)], file_name=f"{SECRET}-PROJEKTS/PROJ-9981_AD.pdf")
        cls.summary = diag.build_sanitized_summary(cls.report)
        cls.dumped = diag.summary_json(cls.summary)

    def test_the_local_report_does_contain_the_data(self):
        # Pārliecināmies, ka tests ir jēgpilns: marķieri un izmēri lokālajā pārskatā TIEŠĀM ir.
        local = json.dumps(self.report, ensure_ascii=False)
        for present in (SECRET, "12345", "4321", "PROJ-9981"):
            self.assertIn(present, local)
        self.assertEqual(self.report["analyses"][1]["candidates"][0]["length_mm"], 12345)

    def test_no_marker_name_text_dimension_or_control_leaks(self):
        for leaked in (SECRET, "PROJ-9981", "PROJEKTS", ".pdf", "AUTHOR", "META", "SUBJECT", "Virtuve", "MODULIS", "Floor plan",
                       "12345", "4321", "12399", "4300", "12000", "4000"):
            self.assertNotIn(leaked, self.dumped, leaked)

    def test_no_hash_coordinates_or_free_text(self):
        self.assertNotIn(hashlib.sha256(self.data).hexdigest()[:16], self.dumped)
        self.assertIsNone(re.search(r"[0-9a-f]{16,}", self.dumped))        # nekāda hash
        self.assertIsNone(re.search(r"\d+\.\d+", self.dumped))             # nekādu koordināšu/decimāldaļu
        for word in ("bbox", "coord", "vertices", "path", "name", "title", "hash", "meta", "evidence", "issue"):
            self.assertNotIn(word, self.dumped.lower(), word)

    def test_only_allowed_fields_with_allowed_value_types(self):
        data = json.loads(self.dumped)
        self.assertEqual(list(data), list(diag.SUMMARY_FIELDS))
        for name, (kind, arg, _) in diag.SUMMARY_FIELDS.items():
            value = data[name]
            if kind == "counts":
                self.assertEqual(list(value), list(arg), name)
                self.assertTrue(all(type(v) is int for v in value.values()), name)
            elif kind == "enum":
                self.assertIn(value, arg)
            else:
                self.assertIs(type(value), int, name)
        # visas ne-fiksētās virknes ir tikai atslēgas un enum vērtības
        strings = re.findall(r'"([^"]*)"', self.dumped)
        allowed = set(diag.SUMMARY_FIELDS) | set(diag.INPUT_STATUSES) | set(diag.SELECTION_MODES)
        for _, (kind, arg, _) in diag.SUMMARY_FIELDS.items():
            if kind == "counts":
                allowed |= set(arg)
        self.assertEqual(set(strings) - allowed, set())

    def test_values_describe_the_run_correctly_without_revealing_it(self):
        s = self.summary
        self.assertEqual((s["pages_total"], s["pages_analyzed"], s["candidates_total"], s["recognised_modules"]), (1, 1, 1, 1))
        self.assertEqual(s["status_counts"]["consistent"], 1)
        self.assertEqual(s["controlled_modules"], 1)
        # kontrole 12399×4300 pret 12345×4321: lielākā novirze 0,49 % → "match"; faktiskie skaitļi kopsavilkumā nav
        self.assertEqual(s["control_comparison"], {"match": 1, "small": 0, "medium": 0, "large": 0, "no_candidate": 0})

    def test_allowed_fields_text_lists_everything_and_the_exclusions(self):
        text = diag.describe_allowed_fields()
        for name in diag.SUMMARY_FIELDS:
            self.assertIn(name, text)
        for never in diag.NEVER_INCLUDED:
            self.assertIn(never, text)


class TestValidationRejectsAnythingElse(unittest.TestCase):
    def good(self):
        return summary_of(gen.build_sample_01())

    def assert_rejected(self, summary, leaked="SECRET-VALUE"):
        with self.assertRaises(ValueError) as ctx:
            diag.validate_summary(summary)
        self.assertNotIn(leaked, str(ctx.exception))                       # kļūda neatklāj ne vērtības, ne liekos lauku nosaukumus

    def test_good_summary_passes(self):
        self.assertTrue(diag.validate_summary(self.good()))

    def test_extra_or_missing_fields(self):
        s = self.good()
        s["file_name"] = "SECRET-VALUE.pdf"
        self.assert_rejected(s)
        s = self.good()
        del s["pages_total"]
        self.assert_rejected(s)
        self.assert_rejected({**self.good(), "SECRET-VALUE": 1})

    def test_wrong_value_types(self):
        for field, bad in (("pages_total", "12"), ("pages_total", 1.5), ("pages_total", True), ("pages_total", -1),
                           ("pages_total", 10 ** 9), ("input_status", "SECRET-VALUE"), ("pages_selection", "x"),
                           ("schema_version", 2), ("candidates_total", None)):
            s = self.good()
            s[field] = bad
            self.assert_rejected(s)

    def test_nested_dicts_must_have_exactly_the_allowed_keys_and_int_values(self):
        for field in ("status_counts", "reason_code_counts", "vector_kind_counts", "control_comparison", "excluded_counts"):
            s = self.good()
            s[field] = {**s[field], "SECRET-VALUE": 1}
            self.assert_rejected(s)
            s = self.good()
            key = next(iter(s[field]))
            s[field][key] = "SECRET-VALUE"
            self.assert_rejected(s)
            s = self.good()
            s[field].pop(next(iter(s[field])))
            self.assert_rejected(s)

    def test_builder_never_returns_an_invalid_summary(self):
        with mock.patch.object(diag, "validate_summary", side_effect=ValueError("x")):
            with self.assertRaises(ValueError):
                diag.build_sanitized_summary(run(gen.build_sample_01()))


if __name__ == "__main__":
    unittest.main()
