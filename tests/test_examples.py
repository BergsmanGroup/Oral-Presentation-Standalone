import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from examples.build_table import build_table


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("pdflatex", "latex", "bibtex", "dvisvgm", "dvipdfmx", "rsvg-convert", "pdftotext")


class TableTests(unittest.TestCase):
    def test_table_contains_calculated_means_and_export_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            wrapper = build_table(output)
            table = (output / "example-table.tex").read_text(encoding="utf-8")
            self.assertIn(r"Control & 1.00 & 1.20 & 1.10 & 1.10 \\", table)
            self.assertIn(r"Treatment A & 1.60 & 1.80 & 1.70 & 1.70 \\", table)
            self.assertIn(r"Treatment B & 2.20 & 2.40 & 2.30 & 2.30 \\", table)
            self.assertIn(r"\input{build/examples/example-table.tex}", wrapper.read_text(encoding="utf-8"))


@unittest.skipUnless(all(shutil.which(tool) for tool in TOOLS), "TeX, rsvg-convert, and pdftotext required")
class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="presentation example tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("build_presentation.py", "Presentation.tex", "references.bib", "shared-table-preamble.tex"):
            shutil.copyfile(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "examples", self.root / "examples", ignore=shutil.ignore_patterns("__pycache__"))
        (self.root / "slides").mkdir()

    def build(self, *flags: str) -> None:
        command = (
            "import runpy, sys, webbrowser; "
            "webbrowser.open = lambda *args: True; "
            "sys.argv = ['build_presentation.py', *sys.argv[1:]]; "
            "runpy.run_path('build_presentation.py', run_name='__main__')"
        )
        result = subprocess.run(
            [sys.executable, "-c", command, *flags],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def pdf_text(self) -> str:
        result = subprocess.run(
            ["pdftotext", str(self.root / "build" / "Presentation.pdf"), "-"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout

    def test_examples_are_opt_in_and_do_not_leak_after_build(self) -> None:
        self.build("--html", "--export_tables")
        self.assertIn("No presentation slides yet", self.pdf_text())
        self.assertFalse((self.root / "build" / "examples").exists())
        self.assertFalse((self.root / "exported").exists())

        self.build("--examples", "--html", "--export_tables")
        text = self.pdf_text()
        self.assertIn("Slide 1: Example slide", text)
        self.assertIn("Source SVG", text)
        self.assertIn("Treatment B", text)
        self.assertIn("2.30", text)
        for name in ("example-figure.pdf", "example-figure.svg", "example-table.pdf", "example-table.svg"):
            self.assertTrue((self.root / "exported" / name).is_file(), name)
        html = (self.root / "build" / "citations.html").read_text(encoding="utf-8")
        self.assertIn("../exported/example-figure.svg", html)
        self.assertIn("../exported/example-table.svg", html)
        generated = {path: path.stat().st_mtime_ns for path in (self.root / "exported").iterdir()}
        generated.update({path: path.stat().st_mtime_ns for path in (self.root / "build" / "examples").rglob("*.tex")})

        self.build("--html", "--export_tables")
        self.assertNotIn("Example slide", self.pdf_text())
        self.assertNotIn("Example Journal", self.pdf_text())
        self.assertFalse((self.root / "build" / "presentation.bbl").exists())
        html = (self.root / "build" / "citations.html").read_text(encoding="utf-8")
        self.assertNotIn("Example slide", html)
        self.assertNotIn("example-figure", html)
        self.assertNotIn("example-table", html)
        self.assertNotIn("example2024", (self.root / "build" / "global-bib-labels.tex").read_text())
        for path, modified in generated.items():
            self.assertEqual(path.stat().st_mtime_ns, modified, str(path))

    def test_examples_build_without_table_exports(self) -> None:
        self.build("--examples")
        self.assertIn("Treatment A", self.pdf_text())
        self.assertTrue((self.root / "exported" / "example-figure.pdf").is_file())
        self.assertFalse((self.root / "exported" / "example-table.svg").exists())

    def test_user_slides_work_without_example_sources(self) -> None:
        shutil.rmtree(self.root / "examples")
        slide = self.root / "slides" / "User slide.tex"
        slide.write_text(r"\slidesection{User slide}User content \slideref{user2024}.", encoding="utf-8")
        master = self.root / "Presentation.tex"
        text = master.read_text(encoding="utf-8").replace(
            "% Updated by sync_slide_order.py",
            "\\input{slides/User slide.tex}\n% Updated by sync_slide_order.py",
        )
        master.write_text(text, encoding="utf-8")
        (self.root / "references.bib").write_text(
            "@article{user2024, author={Writer, Sam}, title={User Reference}, journal={User Journal}, year={2024}}",
            encoding="utf-8",
        )
        self.build("--html", "--export_tables")
        self.assertIn("User content", self.pdf_text())
        self.assertIn("User Journal", self.pdf_text())
        self.assertNotIn("Example slide", self.pdf_text())
        self.assertIn("User slide", (self.root / "build" / "citations.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
