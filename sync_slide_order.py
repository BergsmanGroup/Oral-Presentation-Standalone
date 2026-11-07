"""
sync_slide_order.py
---
One-shot utility: read slide titles from the PowerPoint deck and rewrite the
\\input block in Presentation.tex to match that order.

Usage (from this package folder):
    python sync_slide_order.py

Only slides whose title matches an existing file in slides/ are included.
Titles with no matching .tex file are reported and skipped.
.tex files in slides/ that have no matching PowerPoint title are also reported.
"""

from __future__ import annotations

import difflib
import sys
from datetime import datetime
from pathlib import Path

try:
    from pptx import Presentation as PptxPresentation
except ImportError:
    sys.exit(
        "ERROR: python-pptx is required.\n"
        "Install it with: pip install python-pptx"
    )

# ── Paths ─────────────────────────────────────────────────────────────────────

PRES_DIR   = Path(__file__).resolve().parent
SLIDES_DIR = PRES_DIR / "slides"
BUILD_DIR  = PRES_DIR / "build"
MASTER_TEX = PRES_DIR / "Presentation.tex"
PPTX_FILE  = PRES_DIR / "Oral Presentation with macro WORKING COPY.pptm"
SLIDE_MATCH_LOG = BUILD_DIR / "slide-matching.log"

# Delimit the \\input block inside Presentation.tex.
_SLIDES_START = "% ── Slides (in presentation order)"
_SLIDES_END   = "% ── Bibliography"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Casefold + collapse spaces/hyphens to underscores for fuzzy matching."""
    return s.casefold().replace(" ", "_").replace("-", "_")


def _suggest_rename(stem: str, all_titles: list[str]) -> str | None:
    """Return the closest PowerPoint title if similarity >= 0.5, else None."""
    best_title, best_ratio = None, 0.0
    norm = _normalize(stem)
    for title in all_titles:
        ratio = difflib.SequenceMatcher(None, norm, _normalize(title)).ratio()
        if ratio > best_ratio:
            best_ratio, best_title = ratio, title
    return best_title if best_ratio >= 0.5 else None


def _slide_title(slide) -> str | None:
    """Return title placeholder text, or None if the slide has no title."""
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 0:
            text = ph.text_frame.text.strip()
            return text or None
    return None


def _available_tex_files() -> dict[str, Path]:
    """Return {normalized_stem: path} for every file in slides/."""
    result: dict[str, Path] = {}
    for p in sorted(SLIDES_DIR.iterdir()):
        if not p.is_file():
            continue
        stem = p.stem if p.suffix.lower() == ".tex" else p.name
        result[_normalize(stem)] = p
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    for path, label in ((PPTX_FILE, "PowerPoint file"), (MASTER_TEX, "Presentation.tex")):
        if not path.exists():
            sys.exit(f"ERROR: {label} not found: {path}")

    prs      = PptxPresentation(str(PPTX_FILE))
    tex_files = _available_tex_files()
    used: set[str] = set()

    matched: list[tuple[int, Path]] = []
    unmatched_titles: list[str] = []
    all_titles: list[str] = []

    for slide_number, slide in enumerate(prs.slides, 1):
        title = _slide_title(slide)
        if not title:
            continue
        all_titles.append(title)
        key = _normalize(title)
        if key in tex_files:
            if key not in used:          # deduplicate if title repeats
                matched.append((slide_number, tex_files[key]))
                used.add(key)
        else:
            unmatched_titles.append(title)

    unused_files = [p for k, p in tex_files.items() if k not in used]

    # Write (or clear) the build log so build_presentation.py can warn about it.
    BUILD_DIR.mkdir(exist_ok=True)
    if unused_files:
        lines = [
            f"# Slide matching warnings — generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "# Re-run sync_slide_order.py after saving the PowerPoint to refresh.",
            "",
        ]
        for p in unused_files:
            stem = p.stem if p.suffix.lower() == ".tex" else p.name
            suggestion = _suggest_rename(stem, all_titles)
            if suggestion:
                hint = f'Should this be "{suggestion}.tex"?'
            else:
                hint = "No similar slide title found."
            lines.append(f'"{p.name}": match not found. {hint}')
        SLIDE_MATCH_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        SLIDE_MATCH_LOG.write_text("", encoding="utf-8")

    print(f"PowerPoint : {len(prs.slides)} slides")
    print(f"Matched    : {len(matched)} .tex file(s)")

    if unmatched_titles:
        print("\nTitles with no matching .tex file (skipped):")
        for t in unmatched_titles:
            print(f"  (no file)  {t}")

    if unused_files:
        print("\n.tex files not matched to any slide title (not included):")
        for p in unused_files:
            print(f"  (no slide) {p.name}")

    if not matched:
        sys.exit("\nNo matches found. Presentation.tex not modified.")

    print("\nNew \\input order:")
    input_lines: list[str] = []
    for slide_number, p in matched:
        rel = p.relative_to(PRES_DIR).as_posix()
        print(f"  {rel}")
        input_lines.append(f"\\setcounter{{slide}}{{{slide_number - 1}}}")
        input_lines.append(f"\\input{{{rel}}}")

    # Locate and replace the \\input block in Presentation.tex.
    original    = MASTER_TEX.read_text(encoding="utf-8")
    start_idx   = original.find(_SLIDES_START)
    end_idx     = original.find(_SLIDES_END)

    if start_idx == -1 or end_idx == -1:
        sys.exit(
            "ERROR: Could not locate input-block markers in Presentation.tex.\n"
            f"  Expected: {_SLIDES_START!r}\n"
            f"  Expected: {_SLIDES_END!r}"
        )

    start_line_end = original.index("\n", start_idx) + 1
    new_tex = (
        original[:start_line_end]
        + "% Updated by sync_slide_order.py — do not edit this block manually.\n"
        + "\n".join(input_lines)
        + "\n"
        + original[end_idx:]
    )

    MASTER_TEX.write_text(new_tex, encoding="utf-8")
    print(f"\nPresentation.tex updated. Run build_presentation.py to rebuild.")


if __name__ == "__main__":
    main()
