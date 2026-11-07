from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

# Include overfull and underfull box warnings in the report.
INCLUDE_BOX_WARNINGS = True

# When a primary compile error exists, undefined citations/references are usually
# follow-on noise from the aborted run.
SUPPRESS_SECONDARY_UNDEFINEDS_ON_PRIMARY_ERROR = True

SOURCE_SKIP_DIRS = {"build", ".git", ".venv", "venv", "node_modules", ".figure-explorer"}

# Extensions purged from source subdirectories during a full clean.
SOURCE_ARTIFACT_EXTENSIONS = {".aux", ".bbl", ".blg"}
# Extensions purged from the project root (matched against the document stem only).
ROOT_ARTIFACT_EXTENSIONS = {
    ".aux", ".bbl", ".blg", ".log", ".toc", ".lof", ".lot",
    ".fls", ".fdb_latexmk", ".out", ".synctex.gz",
}
# Only files actually used by the LaTeX build; avoids false-positive duplicates from old exports.
DEFAULT_BIB_FILES = ("chapters/references.bib", "references.bib")

# Update when Inkscape is upgraded - only the version number changes.
INKSCAPE_WINDOWSAPPS = Path(
    r"C:\Program Files\WindowsApps"
    r"\25415Inkscape.Inkscape_1.4.40.0_x64__9waqn51p1ttv2"
    r"\VFS\ProgramFilesX64\Inkscape\bin\inkscape.exe"
)

CITE_COMMAND_PATTERN = re.compile(
    r"\\(?:cite|Cite|citep|citet|citealt|citealp|citeauthor|citeyear|Cref|cref|autocite|textcite)"
    r"(?:\[[^\]]*\])?"
    r"(?:\[[^\]]*\])?"
    r"\{(?P<keys>[^{}]+)\}"
)

LABEL_COMMAND_PATTERN = re.compile(
    r"\\label\{(?P<label>[^{}]+)\}"
)

BIB_ENTRY_PATTERN = re.compile(
    r"^@[^\{]+\{\s*(?P<key>[^,\s]+)\s*,"
)

DOI_FIELD_PATTERN = re.compile(
    r"^(?P<prefix>\s*doi\s*=\s*\{)(?P<value>[^}]*)\}(?P<suffix>\s*,?\s*)$",
    re.IGNORECASE,
)


def unique_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        normalized = item.strip()

        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        result.append(normalized)

    return result


def read_text_safely(path: Path) -> str:
    """
    Read a compiler-generated text file while tolerating unusual encodings.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def line_number_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def quote_command(command: list[str]) -> str:
    """
    Format a command for a human-readable report.
    """
    if sys.platform == "win32":
        return subprocess.list2cmdline(command)

    return shlex.join(command)


def resolve_tex_document(raw_path: str) -> Path:
    """
    Resolve a LaTeX Workshop document argument.

    LaTeX Workshop may pass %DOC% either with or without the .tex suffix.
    """
    document = Path(raw_path).expanduser()

    if not document.is_absolute():
        document = Path.cwd() / document

    document = document.resolve()

    if document.is_file():
        return document

    if document.suffix.lower() != ".tex":
        tex_candidate = document.with_suffix(".tex")

        if tex_candidate.is_file():
            return tex_candidate

    raise FileNotFoundError(f"Root document does not exist: {document}")


def is_skipped_source_path(path: Path) -> bool:
    return any(part in SOURCE_SKIP_DIRS for part in path.parts)


def gather_source_files(document: Path) -> list[Path]:
    root = document.parent
    candidates: list[Path] = []

    for path in root.rglob("*.tex"):
        if not is_skipped_source_path(path):
            candidates.append(path)

    return sorted(candidates)


def gather_bibliography_files(document: Path) -> list[Path]:
    root = document.parent
    return [
        root / relative
        for relative in DEFAULT_BIB_FILES
        if (root / relative).is_file()
    ]


def parse_bibliography_entries(bib_path: Path) -> dict[str, list[int]]:
    entries: dict[str, list[int]] = {}

    for line_number, raw_line in enumerate(
        read_text_safely(bib_path).splitlines(),
        start=1,
    ):
        match = BIB_ENTRY_PATTERN.match(raw_line.strip())

        if match:
            key = match.group("key").strip()
            entries.setdefault(key, []).append(line_number)

    return entries
