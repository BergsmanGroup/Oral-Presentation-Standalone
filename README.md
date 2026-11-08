# Oral Presentation Resource Generator

A small starter project for building a citation-audited LaTeX companion to a
PowerPoint presentation. Example content is opt-in and kept separate from your
own slides.

## Project files

- `Presentation.tex` - document setup, slide order, and bibliography.
- `slides/` - one LaTeX source file per slide.
- `examples/` - sample slide, original SVG, synthetic Python table, and bibliography.
- `references.bib` - BibTeX references used by the slides.
- `unsrtnat-firstauthor.bst` - local bibliography style that prints only the
  first author for each reference.
- `shared-table-preamble.tex` - packages and helpers for standalone table assets.
- `build_presentation.py` - builds the citation-audit PDF and optional exports.
- `sync_slide_order.py` - optionally orders slides from a PowerPoint deck.
- `build/` and `exported/` - generated files; do not edit these directly.

## Requirements

- Python 3.10 or newer
- Python dependencies from `requirements.txt`
- A TeX distribution providing `pdflatex`, `latex`, `bibtex`, `dvipdfmx`, and
  `dvisvgm`
- `python-pptx` and a PowerPoint file named
  `AVS 72 2026 WORKING COPY.pptm` only when using `--reorder`
- `rsvg-convert` is required for `--examples` or when an SVG figure needs conversion

Create a virtual environment and install the Python dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Build

Run from the repository root:

```powershell
python build_presentation.py
```

This builds only your content. With no user slides, it produces a one-page
placeholder PDF. Example sources and assets are not built or included unless
you supply `--examples`, even if their generated files already exist.

Build the demonstration slide, including its SVG graphic and a table calculated
and written as LaTeX by Python:

```powershell
python build_presentation.py --examples
python build_presentation.py --examples --html --export_tables
```

The example uses only Python's standard library; no additional Python packages
are needed. The SVG is converted to `exported/example-figure.pdf`. The table
fragment is generated in `build/examples/example-table.tex`; `--export_tables`
also exports the table to PDF and SVG. The HTML companion displays the example
figure and, when exported, the table.

Optional outputs:

```powershell
python build_presentation.py --html
python build_presentation.py --export_tables
```

To synchronize slide order, put a PowerPoint deck at the filename above, ensure
its slide titles match the corresponding `.tex` filenames in `slides/`, then run:

```powershell
python build_presentation.py --reorder
```

The script updates the slide-input block in `Presentation.tex`; unmatched titles
are reported and skipped. The default build creates a PDF in `build/`. Optional
table exports go in `exported/`.

## Add your content

1. Copy `examples/Example slide.tex` into `slides/` and rename it to match a slide title.
2. Add the new slide's `\input{slides/...}` line to `Presentation.tex`.
3. Add bibliography records to `references.bib` and cite them with `\slideref{key}`.
   In VS Code with LaTeX Workshop, type `\cite{` and press `Ctrl+Space` to search
   citation entries by key, title, or author; insert the resulting key inside
   `\slideref{...}`. The completion inserts a citation key, not the full BibTeX
   record, and custom commands such as `\slideref` may not trigger citation
   completion directly.
4. Put any figures in `assets/figures/`; use PDF or a format supported by your TeX
   distribution. SVG figures are converted when `rsvg-convert` is available.
5. To export a standalone table, add a `.tex` wrapper under `assets/tables/`.
   `examples/build_table.py` shows how to calculate rows and generate LaTeX.

When copying the example, replace its citation and generated asset paths with
your own sources and generation workflow. Do not depend on `--examples` for
production slides. Slide-order synchronization only scans `slides/` and leaves
the opt-in example block intact.

Generated files and local environments are excluded by `.gitignore`.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The integration tests use temporary copies of the project and require the TeX
tools, `rsvg-convert`, and `pdftotext`. They check both example and normal builds,
including switching back to a normal build after generating the examples.
