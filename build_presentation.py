"""
build_presentation.py
-
Full build pipeline for the oral presentation citation system.

Usage:
    python build_presentation.py                          # PDF only (fast)
    python build_presentation.py --html                   # + citations.html
    python build_presentation.py --export_tables           # + table SVGs
    python build_presentation.py --reorder                # sync slide order first
    python build_presentation.py --reorder --html --export_tables  # full build

Or from inside the 'Oral Presentation' folder:
    python build_presentation.py [--reorder] [--html] [--export_tables]

Build order
-
1. (optional) sync_slide_order - reorder \\input lines in Presentation.tex from .pptx
2. rsvg-convert: assets/figures/*.svg → .pdf (skipped if rsvg-convert unavailable)
3. latex  (pass 1, draftmode) - citation discovery
4. bibtex           - assigns global citation numbers in first-appearance order
5. latex  (pass 2, draftmode) - processes the .bbl
6. latex  (pass 3) - resolves cross-references; produces final PDF
7. extract          - pulls \\bibcite lines from .aux - build/global-bib-labels.tex
8. (optional --html) generate - build/citations.html with per-slide copy buttons
9. (optional --export_tables) for each asset in assets/tables/:
       latex  (1 pass) - reads global-bib-labels.tex; correct numbers baked in
       dvisvgm         - exports SVG to exported/
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote as _url_quote


# - Paths -

PRES_DIR = Path(__file__).resolve().parent          # standalone package root
PROJECT_ROOT = PRES_DIR                             # all package dependencies are local
BUILD_DIR = PRES_DIR / "build"
EXPORT_DIR = PRES_DIR / "exported"
MASTER_TEX = PRES_DIR / "Presentation.tex"
MASTER_JOB = BUILD_DIR / "presentation"             # path stem for bibtex

ASSET_DIRS = [
    PRES_DIR / "assets" / "tables",
    PRES_DIR / "assets" / "figures",
]

GLOBAL_LABELS   = BUILD_DIR / "global-bib-labels.tex"
SLIDE_MATCH_LOG = BUILD_DIR / "slide-matching.log"


# - Tool discovery -

def _require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        sys.exit(
            f"ERROR: '{tool}' not found on PATH.\n"
            "Install a TeX distribution (TeX Live, MiKTeX) and ensure its bin\n"
            "directory is on your PATH."
        )
    return path


# Resolved once at import time so missing tools are caught before any work starts.
PDFLATEX = _require("pdflatex")   # master build - PDF
LATEX    = _require("latex")       # standalone assets - DVI - SVG
BIBTEX   = _require("bibtex")
DVISVGM  = _require("dvisvgm")
DVIPDFMX = _require("dvipdfmx")

LATEX_FLAGS = ["-interaction=nonstopmode", "-halt-on-error"]

# Matches \bibcite lines produced by natbib's unsrtnat style.
_BIBCITE_RE = re.compile(
    r'\\bibcite\{(?P<key>[^}]+)\}\{\{(?P<num>\d+)\}\{(?P<year>[^{}]*)(?:\{\})?\}\{\{(?P<author>[^}]+)\}'
)
_SLIDESECTION_RE = re.compile(r'\\slidesection\{(?P<title>[^}]+)\}')
_SLIDEREF_RE     = re.compile(r'\\slideref\{(?P<key>[^}]+)\}')
_SLIDE_INPUT_RE  = re.compile(r'\\input\{slides/(?P<path>[^}]+)\}')
_FIGURE_BLOCK_RE = re.compile(r'\\begin\{figure\}.*?\\end\{figure\}', re.DOTALL)
_INCL_PATH_RE    = re.compile(r'\\includegraphics\[[^\]]*\]\{([^}]+)\}')
_INPUT_PATH_RE   = re.compile(r'\\input\{([^}]+)\}')
_SUP_TRANS       = str.maketrans("0123456789", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079")

# Matches \cite{} family AND \slideref{} so both are checked in preflight.
_CITE_PATTERN = re.compile(
    r"\\(?:slideref|cite|Cite|citep|citet|citealt|citealp|citeauthor|citeyear)"
    r"(?:\[[^\]]*\]){0,2}"
    r"\{(?P<keys>[^{}]+)\}"
)
_LATEX_ACCENT_MAP: dict[str, dict[str, str]] = {
    "'":  {'a':'á','e':'é','i':'í','o':'ó','u':'ú','y':'ý','c':'ć','s':'ś','z':'ź','n':'ń',
           'A':'Á','E':'É','I':'Í','O':'Ó','U':'Ú','Y':'Ý','C':'Ć','S':'Ś','Z':'Ź','N':'Ń'},
    '`':  {'a':'à','e':'è','i':'ì','o':'ò','u':'ù','A':'À','E':'È','I':'Ì','O':'Ò','U':'Ù'},
    '"':  {'a':'ä','e':'ë','i':'ï','o':'ö','u':'ü','A':'Ä','E':'Ë','I':'Ï','O':'Ö','U':'Ü'},
    '^':  {'a':'â','e':'ê','i':'î','o':'ô','u':'û','A':'Â','E':'Ê','I':'Î','O':'Ô','U':'Û'},
    '~':  {'n':'ñ','N':'Ñ','a':'ã','o':'õ','A':'Ã','O':'Õ'},
    'c':  {'c':'ç','C':'Ç','s':'ş','S':'Ş'},
    'v':  {'c':'č','C':'Č','s':'š','S':'Š','z':'ž','Z':'Ž','e':'ě','E':'Ě','r':'ř','R':'Ř','n':'ň','N':'Ň'},
    'u':  {'a':'ă','A':'Ă','g':'ğ','G':'Ğ'},
    'H':  {'o':'ő','O':'Ő','u':'ű','U':'Ű'},
    'k':  {'a':'ą','A':'Ą','e':'ę','E':'Ę'},
    '.':  {'z':'ż','Z':'Ż'},
    'r':  {'a':'å','A':'Å'},
}
# Matches {\cmd x}, {\cmd {x}}, and \cmd{x} accent forms.
_ACCENT_RE = re.compile(
    r"""\{\\([`'\"^~cvuHk.r])\s*\{?([a-zA-Z])\}?\}|\\([`'\"^~cvuHk.r])\{([a-zA-Z])\}"""
)
_BBL_ITEM_RE = re.compile(
    r'\\bibitem\[[^\]]*\]\{([^}]+)\}\s*(.*?)(?=\\bibitem|\s*\\end\{thebibliography\})',
    re.DOTALL,
)

# - Subprocess helper -

def _run(cmd: list[str], cwd: Path, label: str, warn_codes: tuple[int, ...] = ()) -> None:
    print(f"  [{label}]  {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode in warn_codes:
        print(f"  WARNING: '{label}' exited {result.returncode} (non-fatal). Check {BUILD_DIR.relative_to(PRES_DIR)} for details.")
    elif result.returncode != 0:
        sys.exit(
            f"\nERROR: '{label}' failed (exit {result.returncode}).\n"
            f"Check the log in: {BUILD_DIR.relative_to(PRES_DIR)}"
        )


# - Master build -

def build_master() -> None:
    """Run latex - bibtex - latex - latex on presentation.tex."""
    BUILD_DIR.mkdir(exist_ok=True)

    master_rel = MASTER_TEX.relative_to(PRES_DIR).as_posix()
    outdir_flag = f"-output-directory={BUILD_DIR.relative_to(PRES_DIR).as_posix()}"

    print("\n- Pass 1: pdflatex (citation discovery) -")
    _run(
        [PDFLATEX, *LATEX_FLAGS, "-draftmode", outdir_flag, master_rel],
        cwd=PRES_DIR,
        label="pdflatex pass 1",
    )

    print("\n- BibTeX (global citation ordering) -")
    # bibtex argument is the job path relative to CWD, without extension.
    # Running from PRES_DIR so that the local references.bib resolves correctly.
    # warn_codes=(2,): exit 2 means recoverable errors (e.g. duplicate bib keys);
    # bibtex still produces a usable .bbl in that case.
    _run(
        [BIBTEX, MASTER_JOB.relative_to(PRES_DIR).as_posix()],
        cwd=PRES_DIR,
        label="bibtex",
        warn_codes=(2,),
    )

    print("\n- Pass 2: pdflatex (process .bbl) -")
    _run(
        [PDFLATEX, *LATEX_FLAGS, "-draftmode", outdir_flag, master_rel],
        cwd=PRES_DIR,
        label="pdflatex pass 2",
    )

    print("\n- Pass 3: pdflatex (resolve cross-references) -")
    _run(
        [PDFLATEX, *LATEX_FLAGS, outdir_flag, master_rel],
        cwd=PRES_DIR,
        label="pdflatex pass 3",
    )


# - Citation label extraction -

def extract_global_labels() -> int:
    """
    Pull every \\bibcite line from build/presentation.aux into
    build/global-bib-labels.tex.

    These lines carry the globally assigned citation numbers (e.g.
    \\bibcite{wanunu2007}{{4}{...}}).  Standalone asset builds read this file
    so that \\cite{} in table content displays the same number as in the master
    PDF rather than independently renumbering from 1.
    """
    aux_path = BUILD_DIR / "presentation.aux"
    if not aux_path.exists():
        sys.exit(f"ERROR: {aux_path} not found after master build.")

    lines = [
        line
        for line in aux_path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(r"\bibcite{")
    ]

    labels_text = "\n".join(lines) + "\n"
    if not GLOBAL_LABELS.exists() or GLOBAL_LABELS.read_text(encoding="utf-8") != labels_text:
        GLOBAL_LABELS.write_text(labels_text, encoding="utf-8")

    n = len(lines)
    print(f"\n- Extracted {n} citation label(s) - {GLOBAL_LABELS.relative_to(PRES_DIR)}")
    if n == 0:
        print(
            "  WARNING: no \\bibcite entries found.  Citation numbers in SVGs\n"
            "  will appear as [?] until the master build succeeds with BibTeX."
        )
    return n


# - Asset discovery -

def find_assets() -> list[Path]:
    """Return all .tex wrappers found under assets/ subdirectories."""
    assets: list[Path] = []
    for d in ASSET_DIRS:
        if d.exists():
            assets.extend(sorted(d.glob("*.tex")))
    return assets


def _asset_dependencies(tex_path: Path, seen: set[Path] | None = None) -> set[Path]:
    """Return source files that can affect a standalone asset."""
    seen = set() if seen is None else seen
    tex_path = tex_path.resolve()
    if tex_path in seen or not tex_path.exists():
        return seen
    seen.add(tex_path)

    text = tex_path.read_text(encoding="utf-8", errors="replace")
    for match in _INPUT_PATH_RE.finditer(text):
        raw = match.group(1)
        candidate = (PRES_DIR / raw).resolve()
        if not candidate.exists():
            candidate = candidate.with_suffix(".tex")
        _asset_dependencies(candidate, seen)

    if r"\cite" in text:
        bibliography = PRES_DIR / "references.bib"
        if bibliography.exists():
            seen.add(bibliography.resolve())
    if "global-bib-labels" in text and GLOBAL_LABELS.exists():
        seen.add(GLOBAL_LABELS.resolve())
    return seen


def _asset_uses_global_labels(tex_path: Path) -> bool:
    """Return whether an asset or one of its inputs consumes global labels."""
    return any(
        "global-bib-labels" in path.read_text(encoding="utf-8", errors="replace")
        for path in _asset_dependencies(tex_path)
        if path.suffix.lower() == ".tex"
    )


def asset_outputs_stale(tex_path: Path) -> bool:
    """Return whether a table asset needs compilation."""
    stem = tex_path.stem
    outputs = (EXPORT_DIR / f"{stem}.pdf", EXPORT_DIR / f"{stem}.svg")
    if any(not output.exists() for output in outputs):
        return True

    dependencies = _asset_dependencies(tex_path)
    if _asset_uses_global_labels(tex_path) and not GLOBAL_LABELS.exists():
        return True
    newest_dependency = max(path.stat().st_mtime_ns for path in dependencies)
    oldest_output = min(output.stat().st_mtime_ns for output in outputs)
    return newest_dependency > oldest_output


def _stale_assets(assets: list[Path]) -> list[Path]:
    """Return only standalone assets whose outputs are missing or out of date."""
    return [asset for asset in assets if asset_outputs_stale(asset)]


# - Standalone asset compilation -

def build_asset_svg(tex_path: Path) -> Path:
    """
    Compile one standalone asset wrapper and export it as an SVG.

    A per-asset build subdirectory is created under build/assets/<stem>/ so
    that DVI and auxiliary files from different assets do not collide.
    The final SVG is written to exported/<stem>.svg.
    """
    stem = tex_path.stem
    asset_build = BUILD_DIR / "assets" / stem
    asset_build.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(exist_ok=True)

    tex_rel = tex_path.relative_to(PRES_DIR).as_posix()
    outdir_flag = f"-output-directory={asset_build.relative_to(PRES_DIR).as_posix()}"

    print(f"\n  - {stem}: latex -")
    _run(
        [LATEX, *LATEX_FLAGS, outdir_flag, tex_rel],
        cwd=PRES_DIR,
        label=f"latex {stem}",
    )

    dvi_rel = (asset_build / f"{stem}.dvi").relative_to(PRES_DIR).as_posix()
    svg_path = EXPORT_DIR / f"{stem}.svg"
    svg_rel = svg_path.relative_to(PRES_DIR).as_posix()
    pdf_path = EXPORT_DIR / f"{stem}.pdf"
    pdf_rel = pdf_path.relative_to(PRES_DIR).as_posix()

    print(f"  - {stem}: dvipdfmx -")
    _run(
        [DVIPDFMX, "-o", pdf_rel, dvi_rel],
        cwd=PRES_DIR,
        label=f"dvipdfmx {stem}",
    )

    print(f"  - {stem}: dvisvgm -")
    _run(
        [DVISVGM, "--no-fonts", "--bbox=min", f"--output={svg_rel}", dvi_rel],
        cwd=PRES_DIR,
        label=f"dvisvgm {stem}",
    )

    return svg_path


# -- SVG figure conversion ---------------------------------------------------

def convert_svg_figures() -> None:
    """Convert stale SVGs in assets/figures/ to PDF using the shared rsvg-convert pipeline."""
    figures_dir = PRES_DIR / "assets" / "figures"
    if not figures_dir.exists() or not any(figures_dir.glob("*.svg")):
        return

    sys.path.insert(0, str(PROJECT_ROOT / ".vscode"))
    try:
        from latex_build_tools.preflight import convert_stale_svgs
    except ImportError as exc:
        print(f"  WARNING: shared preflight module not importable ({exc}); SVG\u2192PDF skipped.")
        return

    print("\n- Converting SVG figures to PDF -")
    # Pass a sentinel whose parent is figures_dir so only that subtree is searched.
    result = convert_stale_svgs(figures_dir / "_")

    if not result.get("rsvg_convert_available"):
        print("  WARNING: rsvg-convert not found; SVG\u2192PDF conversion skipped.")
        return
    for rel in result.get("conversions", []):
        print(f"  SVG\u2192PDF: {rel}")
    for rel in result.get("failures", []):
        print(f"  FAILED:   {rel}")


# -- Preflight ----------------------------------------------------------------

def run_preflight() -> None:
    """
    Run citation and bibliography checks before building.

    Delegates duplicate-key and capitalisation detection to the local
    .vscode/latex_build_tools/preflight module, which covers all package
    TeX files including presentation slides.

    Additionally validates \\slideref{} keys, which the shared CITE_COMMAND_PATTERN
    does not cover.

    Exits non-zero if any undefined citation keys are found.
    """
    sys.path.insert(0, str(PROJECT_ROOT / ".vscode"))

    try:
        from latex_build_tools.preflight import (
            normalize_citation_key_capitalization,
            scan_bibliography_preflight,
        )
        from latex_build_tools.common import (
            gather_bibliography_files,
            parse_bibliography_entries,
        )
    except ImportError as exc:
        print(f"  WARNING: preflight module not importable ({exc}); skipping.")
        return

    main_doc = PROJECT_ROOT / "Presentation.tex"
    if not main_doc.exists():
        print("  WARNING: Presentation.tex not found; skipping preflight.")
        return

    print("\n" + "-" * 60)
    print("Preflight")

    # Auto-fix unambiguous first-letter capitalisation mismatches in all .tex files.
    # Covers \cite{} family; \slideref{} mismatches are reported separately below.
    fixes = normalize_citation_key_capitalization(main_doc)
    for fix in fixes:
        print(f"  AUTO-FIXED: {fix}")

    result = scan_bibliography_preflight(main_doc)

    blockers: list[str] = []
    warnings: list[str] = []

    # Duplicate bib keys - warning only; bibtex step uses warn_codes to survive them
    for dup in result["duplicate_bibliography_keys"]:
        warnings.append(
            f"Duplicate bib key '{dup['key']}' "
            f"(variants: {', '.join(dup['variants'])})"
        )

    # Remaining capitalisation mismatches that couldn't be auto-fixed
    for mismatch in result["capitalization_mismatches"]:
        warnings.append(f"Cite key capitalisation: {mismatch}")

    # Build casefold map of all known bib keys for undefined-key detection
    bib_keys: dict[str, str] = {}  # casefold -> canonical
    for bib_path in gather_bibliography_files(main_doc):
        for key in parse_bibliography_entries(bib_path):
            bib_keys.setdefault(key.casefold(), key)

    # Scan all presentation .tex files for every \cite / \slideref key
    for tex_path in sorted(PRES_DIR.rglob("*.tex")):
        if "build" in tex_path.parts:
            continue
        text = tex_path.read_text(encoding="utf-8", errors="replace")
        rel = tex_path.relative_to(PRES_DIR)
        for match in _CITE_PATTERN.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            for raw_key in match.group("keys").split(","):
                key = raw_key.strip()
                if not key or "#" in key:  # skip LaTeX argument placeholders like #1
                    continue
                canonical = bib_keys.get(key.casefold())
                if canonical is None:
                    blockers.append(f"{rel}:{line}: '{key}' not found in bibliography")
                elif canonical != key:
                    warnings.append(
                        f"{rel}:{line}: '{key}' capitalisation differs from "
                        f"bib key '{canonical}'"
                    )

    for w in warnings:
        print(f"  WARN:  {w}")
    for b in blockers:
        print(f"  BLOCK: {b}")
    if not warnings and not blockers and not fixes:
        print("  OK")

    if blockers:
        sys.exit(
            f"\nERROR: {len(blockers)} undefined citation key(s). Fix before building."
        )


# - HTML citation companion -

def _parse_labels(labels_path: Path) -> dict[str, tuple[int, str, str]]:
    """Return {key: (number, author, year)} from global-bib-labels.tex."""
    out: dict[str, tuple[int, str, str]] = {}
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        m = _BIBCITE_RE.search(line)
        if m:
            author = m.group("author").replace("et~al.", "et al.").replace("~", "\u00a0")
            out[m.group("key")] = (int(m.group("num")), author, m.group("year"))
    return out


def _slide_inputs(master_tex: Path) -> list[Path]:
    """Return slide tex paths in document order, skipping commented lines."""
    slides_dir = master_tex.parent / "slides"
    paths: list[Path] = []
    for line in master_tex.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("%"):
            continue
        m = _SLIDE_INPUT_RE.search(line)
        if not m:
            continue
        raw = m.group("path")
        base = slides_dir / raw
        candidate = base if base.exists() else Path(str(base) + ".tex")
        if candidate.exists():
            paths.append(candidate)
    return paths


def _powerpoint_slide_numbers() -> dict[str, int]:
    """Return normalized PowerPoint slide titles mapped to their slide numbers."""
    try:
        from pptx import Presentation
    except ImportError:
        return {}
    pptx_path = PRES_DIR / "Oral Presentation with macro WORKING COPY.pptm"
    if not pptx_path.exists():
        return {}

    def normalize(value: str) -> str:
        return value.casefold().replace(" ", "_").replace("-", "_")

    numbers: dict[str, int] = {}
    for number, slide in enumerate(Presentation(str(pptx_path)).slides, 1):
        for placeholder in slide.placeholders:
            if placeholder.placeholder_format.idx == 0:
                title = placeholder.text_frame.text.strip()
                if title:
                    numbers.setdefault(normalize(title), number)
                break
    return numbers


def _js_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "") + "'"


def _delatex_accents(text: str) -> str:
    """Replace LaTeX accent commands with Unicode equivalents."""
    def _replace(m: re.Match) -> str:
        if m.group(1):
            return _LATEX_ACCENT_MAP.get(m.group(1), {}).get(m.group(2), m.group(0))
        return _LATEX_ACCENT_MAP.get(m.group(3), {}).get(m.group(4), m.group(0))
    text = _ACCENT_RE.sub(_replace, text)
    return (text
            .replace(r'{\i}', 'ı').replace(r'{\o}', 'ø')
            .replace(r'{\ae}', 'æ').replace(r'{\AE}', 'Æ')
            .replace(r'\l{}', 'ł').replace(r'\l ', 'ł '))


def _bbl_to_texts(raw: str) -> tuple[str, str]:
    """Convert a single .bbl entry body to (plain_text, html_text)."""
    text = re.sub(r'\\penalty0\s*', '', raw)
    text = text.replace(r'\protect', '')
    text = re.sub(r'\\natexlab\{([^}]*)\}', r'\1', text)
    text = text.replace(r'\newblock', ' ')
    text = _delatex_accents(text)
    text = re.sub(r'\\(?:bibinfo|textrm|textsf|textbf|textsc|textit)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\(?:url|texttt|hbox|mbox)\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\doi\{([^}]+)\}', r'doi: \1', text)
    text = text.replace('~', ' ')
    # Split on \emph before stripping remaining braces so italics can be preserved in HTML.
    plain = re.sub(r'\\emph\{([^}]*)\}', r'\1', text)
    html  = re.sub(r'\\emph\{([^}]*)\}', r'<em>\1</em>', text)
    def _finish(s: str) -> str:
        for _ in range(4):
            s = re.sub(r'\{([^{}]*)\}', r'\1', s)
        s = s.replace('---', '\u2014').replace('--', '\u2013')
        return re.sub(r'[ \t\n]+', ' ', s).strip()
    return _finish(plain), _finish(html)


def _parse_bbl(
    bbl_path: Path, labels: dict[str, tuple[int, str, str]]
) -> list[tuple[int, str, str]]:
    """Return [(num, plain, html), ...] sorted by citation number."""
    text = bbl_path.read_text(encoding='utf-8', errors='replace')
    entries: list[tuple[int, str, str]] = []
    for m in _BBL_ITEM_RE.finditer(text):
        key = m.group(1)
        if key not in labels:
            continue
        num = labels[key][0]
        plain, html = _bbl_to_texts(m.group(2))
        entries.append((num, plain, html))
    entries.sort(key=lambda e: e[0])
    return entries


def _render_bibliography_html(entries: list[tuple[int, str, str]]) -> str:
    """Build the bibliography section HTML with separate plain/rich copy buttons."""
    if not entries:
        return ""
    plain_all = "\n\n".join(f"[{num}] {plain}" for num, plain, _ in entries)
    rich_all  = "<html><body>" + "".join(
        f"<p><sup>{num}</sup> {html}</p>" for num, _, html in entries
    ) + "</body></html>"
    items = "\n".join(
        f'<li><sup class="bib-num">{num}</sup> <span class="bib-entry">{html}</span></li>'
        for num, _, html in entries
    )
    return (
        f'<script>\n'
        f'const _BIB_PLAIN = {_js_str(plain_all)};\n'
        f'const _BIB_RICH  = {_js_str(rich_all)};\n'
        f'</script>\n'
        f'<h2>Bibliography</h2>\n'
        f'<p>\n'
        f'  <button onclick="copyBibPlain(this)">Copy all (plain text)</button>'
        f'<span class="ok">&#10003; copied</span>\n'
        f'  <button onclick="copyBibRich(this)">Copy all (rich text)</button>'
        f'<span class="ok">&#10003; copied</span>\n'
        f'</p>\n'
        f'<ol class="bib-list">\n{items}\n</ol>\n'
    )


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Presentation Citations</title>
<style>
  body  {{ font-family: Georgia, serif; max-width: 860px; margin: 2rem auto; color: #222; }}
  h2    {{ border-bottom: 2px solid #444; padding-bottom: .3rem; margin-top: 2rem; }}
  ul    {{ list-style: none; padding: 0; }}
  li    {{ display: flex; align-items: center; gap: .75rem; margin: .6rem 0; }}
  .ref  {{ flex: 1; }}
  img.ref-img {{ height: 70px; width: auto; border: 1px solid #ddd; border-radius: 2px; flex-shrink: 0; }}
  button {{
    font-size: .75rem; padding: .15rem .5rem; cursor: pointer;
    border: 1px solid #888; border-radius: 3px; background: #f5f5f5;
    white-space: nowrap;
  }}
  button:active {{ background: #ddd; }}
  .ok {{ color: green; font-size: .75rem; display: none; }}
  .bib-list {{ list-style: none; padding: 0; }}
  .bib-list li {{ display: block; margin: .9rem 0; }}
  .bib-num {{ font-size: .8em; vertical-align: super; margin-right: .2rem; }}
</style>
</head>
<body>
<h1>Presentation Citation Reference</h1>
<p>Click <strong>Copy</strong> to place the formatted reference on your clipboard.
   Paste into PowerPoint with <kbd>Ctrl+V</kbd>; superscripts are preserved.</p>
{sections}
<script>
function showOk(btn) {{
  const ok = btn.nextElementSibling;
  ok.style.display = "inline";
  setTimeout(() => {{ ok.style.display = "none"; }}, 1500);
}}
async function copyRef(btn, plain, html) {{
  try {{
    await navigator.clipboard.write([new ClipboardItem({{
      "text/plain": new Blob([plain], {{type: "text/plain"}}),
      "text/html":  new Blob([html],  {{type: "text/html"}})
    }})]);
    showOk(btn);
  }} catch (e) {{ alert("Copy failed: " + e); }}
}}
async function copyBibPlain(btn) {{
  try {{
    await navigator.clipboard.writeText(_BIB_PLAIN);
    showOk(btn);
  }} catch (e) {{ alert("Copy failed: " + e); }}
}}
async function copyBibRich(btn) {{
  try {{
    await navigator.clipboard.write([new ClipboardItem({{
      "text/plain": new Blob([_BIB_PLAIN], {{type: "text/plain"}}),
      "text/html":  new Blob([_BIB_RICH],  {{type: "text/html"}})
    }})]);
    showOk(btn);
  }} catch (e) {{ alert("Copy failed: " + e); }}
}}
</script>
</body>
</html>
"""

_SECTION_HTML = "<h2>{title}</h2>\n<ul>\n{items}\n</ul>"

_ITEM_HTML = (
    '<li>'
    '{img}'
    '<span class="ref">({author}, {year})<sup>{num}</sup></span>'
    '<button onclick="copyRef(this, {p}, {h})">Copy</button>'
    '<span class="ok">&#10003; copied</span>'
    '</li>'
)

_OBJECT_HTML = (
    '<li><img class="ref-img" src="{src}" alt="{alt}">'
    '<span class="ref">{label}</span></li>'
)


def _slide_figure_images(text: str) -> dict[str, str]:
    """Map each \\slideref key inside a figure block to its image filename."""
    result: dict[str, str] = {}
    for block in _FIGURE_BLOCK_RE.finditer(text):
        path_m = _INCL_PATH_RE.search(block.group())
        if not path_m:
            continue
        filename = Path(path_m.group(1)).name
        for ref_m in _SLIDEREF_RE.finditer(block.group()):
            result[ref_m.group("key")] = filename
    return result


def _browser_image_path(filename: str) -> tuple[str, str]:
    """Return an HTML asset path and alt text, preferring SVG over PDF."""
    path = Path(filename)
    if path.suffix.lower() == ".pdf":
        svg_name = path.with_suffix(".svg").name
        for directory in (PRES_DIR / "assets" / "figures", PRES_DIR / "exported"):
            if (directory / svg_name).exists():
                return svg_name, filename
    return filename, filename


def _html_asset(filename: str) -> tuple[str, str]:
    """Return a relative HTML path and alt text for a generated presentation asset."""
    image_name, alt_text = _browser_image_path(filename)
    image_dir = "../exported/" if (EXPORT_DIR / image_name).exists() else "../assets/figures/"
    return image_dir + _url_quote(image_name, safe=""), alt_text


def generate_citations_html() -> Path:
    """Generate build/citations.html with per-slide copy buttons for each \\slideref."""
    out_path = BUILD_DIR / "citations.html"
    if not GLOBAL_LABELS.exists():
        print("  WARNING: global-bib-labels.tex not found; skipping HTML generation.")
        return out_path

    labels = _parse_labels(GLOBAL_LABELS)
    slides = _slide_inputs(MASTER_TEX)
    powerpoint_numbers = _powerpoint_slide_numbers()

    sections: list[str] = []

    bbl_path = BUILD_DIR / "presentation.bbl"
    if bbl_path.exists():
        bib_section = _render_bibliography_html(_parse_bbl(bbl_path, labels))
        if bib_section:
            sections.append(bib_section)

    slide_num = 0

    for path in slides:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        slide_num += 1
        m = _SLIDESECTION_RE.search(text)
        title = m.group("title") if m else path.stem
        normalized_title = title.casefold().replace(" ", "_").replace("-", "_")
        display_number = powerpoint_numbers.get(normalized_title, slide_num)

        images = _slide_figure_images(text)
        items: list[str] = []
        referenced_images = set(images.values())

        # Include rendered table inputs even when the table contains no citation.
        for input_m in _INPUT_PATH_RE.finditer(text):
            input_path = Path(input_m.group(1))
            stem = input_path.stem
            for suffix in (".svg", ".pdf"):
                asset = EXPORT_DIR / f"{stem}{suffix}"
                if asset.exists():
                    src, alt_text = _html_asset(asset.name)
                    items.append(_OBJECT_HTML.format(
                        src=src, alt=alt_text, label=f"Rendered table: {stem}"
                    ))
                    break

        for ref_m in _SLIDEREF_RE.finditer(text):
            key = ref_m.group("key")
            if key not in labels:
                continue
            num, author, year = labels[key]
            citation = f"{author}, {year}" if year else author
            plain     = f"({citation}){str(num).translate(_SUP_TRANS)}"
            html_span = f"<span>({citation})<sup>{num}</sup></span>"
            if key in images:
                src, alt_text = _html_asset(images[key])
                img = f'<img class="ref-img" src="{src}" alt="{alt_text}">'
            else:
                img = ""
            items.append(_ITEM_HTML.format(
                img=img, author=author, year=year, num=num,
                p=_js_str(plain), h=_js_str(html_span),
            ))

        sections.append(_SECTION_HTML.format(
            title=f"Slide {display_number}: {title}",
            items="\n".join(items) if items else "<li>No citations or rendered objects.</li>",
        ))

    out_path.write_text(
        _HTML_TEMPLATE.format(sections="\n".join(sections)),
        encoding="utf-8",
    )
    return out_path


# - Entry point -

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the oral presentation PDF and optional outputs."
    )
    parser.add_argument(
        "--html", action="store_true",
        help="Generate build/citations.html with per-slide copy buttons.",
    )
    parser.add_argument(
        "--reorder", action="store_true",
        help="Sync \\input order in Presentation.tex from the PowerPoint before building.",
    )
    parser.add_argument(
        "--export_tables", action="store_true",
        help="Build stale table assets and export PDFs/SVGs to exported/.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Oral Presentation Build")
    print(f"  Presentation dir : {PRES_DIR}")
    print(f"  Build dir        : {BUILD_DIR}")
    print(f"  Export dir       : {EXPORT_DIR}")
    print("=" * 60)

    run_preflight()

    # Warn about .tex files that had no matching PowerPoint slide on last sync.
    if SLIDE_MATCH_LOG.exists():
        warnings = [
            ln for ln in SLIDE_MATCH_LOG.read_text(encoding="utf-8").splitlines()
            if ln and not ln.startswith("#")
        ]
        if warnings:
            print("\n" + "!" * 60)
            print("SLIDE MATCHING WARNINGS (run sync_slide_order.py to fix):")
            for w in warnings:
                print(f"  {w}")
            print("!" * 60)

    if args.reorder:
        print("\n- Syncing slide order from PowerPoint -")
        subprocess.run(
            [sys.executable, str(PRES_DIR / "sync_slide_order.py")],
            check=True,
        )

    # Convert any SVG figures to PDF before LaTeX runs
    convert_svg_figures()

    assets = find_assets()

    # Step 1-4: master PDF + global citation ordering
    if args.export_tables:
        stale = _stale_assets(assets)
        if stale:
            print(f"\n- Prebuilding {len(stale)} stale standalone asset(s) for master PDF -")
            for tex in stale:
                build_asset_svg(tex)
        elif assets:
            print("\n- Standalone assets are up to date; reusing existing exports -")
    build_master()

    # Step 5: make citation numbers available to standalone asset builds
    previous_labels = (
        GLOBAL_LABELS.read_text(encoding="utf-8")
        if GLOBAL_LABELS.exists()
        else None
    )
    n_labels = extract_global_labels()
    labels_changed = (
        previous_labels != GLOBAL_LABELS.read_text(encoding="utf-8")
    )

    # Step 6: optionally generate HTML citation companion
    html_out: Path | None = None
    if args.html:
        html_out = generate_citations_html()
        print(f"  HTML : {html_out.relative_to(PRES_DIR)}")

    # Step 7: compile table assets and export SVGs (opt-in; slowest step)
    exported: list[Path] = []
    if args.export_tables:
        stale = _stale_assets(assets)
        if stale:
            print(f"\n- Building {len(stale)} stale standalone asset(s) -")
            for tex in stale:
                exported.append(build_asset_svg(tex))
            print("\n- Rebuilding master PDF with refreshed table assets -")
            build_master()
        else:
            if assets:
                print("\n- Standalone assets remain up to date -")
            else:
                print("\nNo standalone assets found in assets/.")
    else:
        stale = _stale_assets(assets)
        if stale or labels_changed:
            print(
                "\nWARNING: standalone table exports may be stale. "
                "Run with --export_tables to refresh them."
            )

    # Summary
    print("\n" + "=" * 60)
    print("Build complete.")
    # pdflatex mirrors the source filename capitalisation on Windows
    pdf = next(BUILD_DIR.glob("[Pp]resentation.pdf"), BUILD_DIR / "presentation.pdf")
    print(f"  PDF  : {pdf.relative_to(PRES_DIR)}")
    print(f"  {n_labels} citation label(s) extracted.")
    if html_out:
        print(f"  HTML : {html_out.relative_to(PRES_DIR)}")
        import webbrowser
        webbrowser.open(html_out.as_uri())
    for svg in exported:
        print(f"  SVG  : {svg.relative_to(PRES_DIR)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
