# Oral Presentation Resource Generator

This folder is a standalone package for generating citation-audited LaTeX
resources used by the oral presentation. It does not depend on the parent
dissertation repository and can be copied into its own Git repository.

PowerPoint remains the presentation editor. LaTeX provides the citation audit
PDF and table/figure resource exports, while Python orchestrates the build.

## Contents

- `Presentation.tex` - master citation-audit document and slide order.
- `slides/` - one LaTeX source file per slide with citations.
- `assets/tables/` - standalone table wrappers exported to SVG.
- `assets/figures/` - source figures used by the citation audit.
- `source/Figures/` - copied source fragments needed by presentation tables.
- `references.bib` - local bibliography used by the presentation.
- `shared-table-preamble.tex` - local table formatting support.
- `build_presentation.py` - reproducible build pipeline.
- `sync_slide_order.py` - optionally synchronizes slide order from the PowerPoint.
- `build/` - generated intermediate files and the citation audit PDF.
- `exported/` - generated or presentation-ready resource exports.

The PowerPoint files are included for slide-order synchronization and
presentation editing, but the LaTeX build does not modify them.

## Requirements

- Python 3.10 or newer
- `python-pptx` when using `--reorder`
- A TeX distribution providing `pdflatex`, `latex`, `bibtex`, `dvipdfmx`,
  and `dvisvgm` on `PATH`. The build script checks for all five tools when it
  starts, including for `--help` and PDF-only builds.
- `rsvg-convert` is optional and is only needed to convert SVG figures to PDF

The dependency manifest is `requirements.txt`. Create or update the local
virtual environment and install the dependencies with:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If the environment already exists, rerun only the activation and
`pip install` commands to update it. PowerShell execution-policy settings may
require activating the environment through
`.\.venv\Scripts\python.exe` instead of `Activate.ps1`.

Verify that the external tools are discoverable before building:

```powershell
Get-Command python, pdflatex, latex, bibtex, dvipdfmx, dvisvgm
python -m pip check
```

The scripts use the files relative to their own directory, so commands should
be run from this folder. Paths containing spaces are supported by the scripts,
but the PowerPoint filename used by `--reorder` is currently fixed to
`Oral Presentation with macro WORKING COPY.pptm`.

## Build

Run from this folder:

```powershell
python build_presentation.py
```

Useful options:

```powershell
python build_presentation.py --html
python build_presentation.py --export_tables
python build_presentation.py --reorder --html --export_tables
```

The normal workflow is:

1. Edit the PowerPoint deck and save it as
   `Oral Presentation with macro WORKING COPY.pptm`.
2. Run `python build_presentation.py --reorder` to synchronize the
   `\input{...}` order in `Presentation.tex` from the deck.
3. Review any unmatched-title warnings printed by the command and in
   `build/slide-matching.log`.
4. Run `python build_presentation.py` to generate the citation-audit PDF.
5. Add `--html` for the browser-based citation companion, or
   `--export_tables` to compile the standalone table assets to PDF and SVG.

`--reorder` edits `Presentation.tex`; do not use it as a read-only check.
Only slides whose PowerPoint title matches a `.tex` filename in `slides/` are
included. Missing or renamed titles are skipped and reported rather than
automatically repaired.

The build assigns citation numbers by first appearance across the slide order.
The audit PDF is written to `build/Presentation.pdf`; table SVGs are written
to `exported/` when `--export_tables` is supplied. Table assets are rebuilt
only when their source, included fragments, shared preamble, or citation-label
file is newer than the existing PDF/SVG outputs. SVG figures are converted to
PDFs when they are stale and `rsvg-convert` is available; otherwise the build
continues with a warning and LaTeX may use an existing PDF or fail if one is
absent. When refreshed table assets affect the master PDF, the master is
rebuilt once after those assets are updated.

To add a slide, create `slides/<slide-title>.tex` and add its input to
`Presentation.tex`, or use `--reorder` after saving the matching PowerPoint
file. To add a presentation-only table, create a wrapper in
`assets/tables/` and reference `shared-table-preamble.tex` plus any local
source fragments.

## Output and editing rules

The PowerPoint deck is the presentation source of truth. The LaTeX project is
the citation-audit and resource-export pipeline; it does not update the
PowerPoint file. Edit source files under `slides/`, `assets/`, `source/`,
`references.bib`, and `Presentation.tex`, then rebuild.

The build reuses unchanged files already in `build/` and `exported/`, but it
does not provide a destructive clean command. If an output is stale or a
citation/figure appears wrong, remove the specific generated output or the
relevant generated directory and rebuild. Do not edit generated files
directly.

## Generated files

Do not edit files generated by the build:

- `build/`
- generated PDFs and SVGs in `exported/` (the directory also contains
  presentation resources that may be maintained separately)

The source bibliography and table fragment are intentionally copied into this
package so it remains independent of the dissertation repository.

## Known limitations

- The build has no pinned Python or TeX versions and no automated test or CI
  configuration. Reproducibility therefore depends on the local installations
  and their versions.
- The five TeX executables are mandatory at script startup, even when a
  requested operation would not use every executable.
- `--reorder` relies on exact, normalized title-to-filename matching and can
  silently omit a slide from `Presentation.tex` except for its warning output.
- Generated artifacts are ignored by Git, but obsolete outputs are not
  automatically removed when a source asset is renamed or deleted. A fully
  clean rebuild still requires manual cleanup of the relevant generated files.
