"""Sintētisko AD vektoru PDF paraugu testi (tools/synthetic_ad_pdf.py, samples/ad_vector, Issue #6).

Pārbauda: ģenerēšana ir reproducējama; repozitorijā glabātie paraugi ir TIEŠI ģeneratora izvade un satur
tikai sintētiskus failus (nav iespējams netīšām ielikt reālu klienta PDF); katra parauga rezultāts
analīzē sakrīt ar README tabulu.
"""
import contextlib
import io
import pathlib
import unittest

import pymupdf

from src.ad_plan import scan_plan_pages
from src.ad_vector import analyze_pdf
from src.pdf_reader import read_pdf
from tools import synthetic_ad_pdf as gen

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "samples" / "ad_vector"


def pipeline(data):
    """Kā lietotne: teksta klasifikācija izvēlas grīdas plāna lapas, tad vektoru analīze."""
    scan = scan_plan_pages([p["text"] for p in read_pdf(data)["pages"]])
    pages = [p["page"] for p in scan["floor_pages"]]
    return {p["page"]: p for p in analyze_pdf(data, pages)["pages"]}


class TestReproducibleGeneration(unittest.TestCase):
    def test_each_builder_is_deterministic(self):
        for name, builder in gen.SAMPLES.items():
            self.assertEqual(builder(), builder(), name)

    def test_variants_are_deterministic(self):
        self.assertEqual(gen.build_sample_03(separator=False), gen.build_sample_03(separator=False))
        self.assertNotEqual(gen.build_sample_03(), gen.build_sample_03(separator=False))
        self.assertNotEqual(gen.build_sample_09(), gen.build_sample_09(inner_label=True))

    def test_generator_cli_writes_the_same_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main(["--out", tmp])
            for name, builder in gen.SAMPLES.items():
                self.assertEqual((pathlib.Path(tmp) / name).read_bytes(), builder(), name)


class TestCommittedSamples(unittest.TestCase):
    def test_directory_contains_exactly_the_generated_samples(self):
        self.assertTrue(SAMPLES_DIR.is_dir())
        self.assertEqual(sorted(p.name for p in SAMPLES_DIR.glob("*.pdf")), sorted(gen.SAMPLES))

    def test_committed_files_are_byte_identical_to_generator_output(self):
        for name, builder in gen.SAMPLES.items():
            self.assertEqual((SAMPLES_DIR / name).read_bytes(), builder(),
                             f"{name} neatbilst ģeneratoram: palaid `python -m tools.synthetic_ad_pdf`")

    def test_every_pdf_under_samples_is_marked_synthetic(self):
        found = list((ROOT / "samples").rglob("*.pdf"))
        self.assertEqual(len(found), len(gen.SAMPLES))
        for path in found:
            with pymupdf.open(path) as doc:
                self.assertIn("SYNTHETIC", doc.metadata["title"], path.name)
                self.assertTrue(all("SINTĒTISKS PARAUGS" in page.get_text() for page in doc), path.name)

    def test_gitignore_exception_is_limited_to_the_samples_folder(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.pdf", text)                      # citi PDF joprojām ignorēti
        self.assertIn("!samples/ad_vector/*.pdf", text)
        self.assertNotIn("!*.pdf", text)

    def test_samples_contain_real_vector_drawings(self):
        for name in gen.SAMPLES:
            if "no_vector" in name:
                continue
            with pymupdf.open(SAMPLES_DIR / name) as doc:
                self.assertGreater(sum(len(page.get_drawings()) for page in doc), 10, name)


class TestExpectedResultsPerSample(unittest.TestCase):
    """Tabula no samples/ad_vector/README.md: faktiskā analīzes izvade katram paraugam."""

    def summary(self, name):
        data = (SAMPLES_DIR / name).read_bytes()
        return {page: [(c["status"], c["length_mm"], c["width_mm"]) for c in info["candidates"]] or info["status"]
                for page, info in pipeline(data).items()}

    def test_expected(self):
        self.assertEqual(self.summary("ad_vector_01_12000x4000_1to50.pdf"), {2: [("ģeometriski saskaņots", 12000, 4000)]})
        self.assertEqual(self.summary("ad_vector_02_12100x3600_1to100.pdf"), {1: [("ģeometriski saskaņots", 12100, 3600)]})
        self.assertEqual(self.summary("ad_vector_03_two_modules_with_boundary.pdf"),
                         {1: [("ģeometriski saskaņots", 12000, 4000), ("ģeometriski saskaņots", 12000, 3600)]})
        self.assertEqual(self.summary("ad_vector_04_L_shape_unclear.pdf"), {1: [("atteikums", None, None)]})
        self.assertEqual(self.summary("ad_vector_05_scale_missing.pdf"), {1: [("neskaidrs", 12000, 4000)]})
        self.assertEqual(self.summary("ad_vector_06_scale_conflict.pdf"), {1: [("atteikums", None, None)]})
        self.assertEqual(self.summary("ad_vector_07_rotated_and_vertical.pdf"),
                         {1: [("ģeometriski saskaņots", 12000, 4000)], 2: [("ģeometriski saskaņots", 12000, 4000)]})
        self.assertEqual(self.summary("ad_vector_08_no_vector_geometry.pdf"),
                         {1: "no_vector_geometry", 2: "no_vector_geometry"})
        self.assertEqual(self.summary("ad_vector_09_facade_and_inner_contour.pdf"),
                         {1: [("neskaidrs", 12400, 4400), ("neskaidrs", 12000, 4000)]})


if __name__ == "__main__":
    unittest.main()
