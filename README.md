# Oral Presentation Resource Generator

A small starter project for building a citation-audited LaTeX companion to a
PowerPoint presentation. The repository includes a sample slide and bibliography
entry; replace them with your own content.

## Project files

- `Presentation.tex` - document setup, slide order, and bibliography.
- `slides/` - one LaTeX source file per slide.
- `references.bib` - BibTeX references used by the slides.
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
  `Oral Presentation with macro WORKING COPY.pptm` only when using `--reorder`
- `rsvg-convert` is optional and is used to convert SVG figures to PDF

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

## Regenerate the FTIR figure

Edit the `assignment` values in
`assets/figures/SID180c_TDICBAPMA_65nm_NoMeI_BaselineCorrected_FTIR_config.json`,
then run `python generate_ftir_plot.py` from the repository root. The script
regenerates the PNG and SVG in `assets/figures/`.

## Add your content

1. Copy `slides/Example slide.tex` and rename the copy to match a slide title.
2. Add the new slide's `\input{slides/...}` line to `Presentation.tex`.
3. Add bibliography records to `references.bib` and cite them with `\slideref{key}`.
4. Put any figures in `assets/figures/`; use PDF or a format supported by your TeX
   distribution. SVG figures are converted when `rsvg-convert` is available.
5. To export a standalone table, add a `.tex` wrapper under `assets/tables/`.

Generated files and local environments are excluded by `.gitignore`.
