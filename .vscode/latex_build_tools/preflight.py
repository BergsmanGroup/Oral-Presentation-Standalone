from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
#import tempfile
from pathlib import Path
from typing import Any

from .common import (
    CITE_COMMAND_PATTERN,
    DOI_FIELD_PATTERN,
    LABEL_COMMAND_PATTERN,
    ROOT_ARTIFACT_EXTENSIONS,
    SOURCE_ARTIFACT_EXTENSIONS,
    gather_bibliography_files,
    gather_source_files,
    is_skipped_source_path,
    line_number_for_offset,
    parse_bibliography_entries,
    read_text_safely,
    unique_preserving_order,
)

FIGURE_COMMAND_PATTERN = re.compile(
    r"""(?P<prefix>\\(?:halfwidthfigure|halfwrapfigure|fullfigure)\s*\{)
        (?P<path>[^{}]*)
        (?P<suffix>\})""",
    re.VERBOSE,
)


def clean_stale_artifacts(document: Path, output_directory: Path) -> None:
    """Wipe latexmk outputs and stale build files left outside the build directory."""
    subprocess.run(
        ["latexmk", "-CA", f"-outdir={output_directory}", str(document)],
        cwd=document.parent,
        check=False,
    )

    root = document.parent

    # Remove root-level artifacts matching the document stem (e.g. main.log, main.aux, main.pdf).
    for ext in ROOT_ARTIFACT_EXTENSIONS:
        candidate = root / (document.stem + ext)
        if candidate.is_file():
            candidate.unlink()

    root_pdf = root / f"{document.stem}.pdf"
    if root_pdf.is_file():
        root_pdf.unlink()

    figure_explorer_dir = root / ".figure-explorer"
    if figure_explorer_dir.is_dir():
        shutil.rmtree(figure_explorer_dir, ignore_errors=True)

    # Remove .aux/.bbl/.blg scattered in source subdirectories outside the build dir.
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in SOURCE_ARTIFACT_EXTENSIONS:
            rel = path.relative_to(root)
            if not is_skipped_source_path(rel):
                path.unlink()


def _find_rsvg_convert() -> Path | None:
    found = shutil.which("rsvg-convert")
    print(f"DEBUG rsvg-convert path: {found}")

    if found:
        return Path(found)

    print(
        "rsvg-convert not found in PATH; "
        "SVG to PDF conversion will be skipped."
    )
    return None





def _run_rsvg_convert(rsvg_convert: Path, svg: Path, pdf: Path) -> bool:
    command = [
        str(rsvg_convert),
        "--format=pdf",
        "--background-color=white",
        "--output",
        str(pdf),
        str(svg),
    ]

    print("DEBUG command:", command)

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    print("DEBUG return code:", result.returncode)
    print("DEBUG stdout:", result.stdout)
    print("DEBUG stderr:", result.stderr)

    return result.returncode == 0 and pdf.exists()


def convert_stale_svgs(document: Path) -> dict[str, Any]:
    """Convert SVG files that have no up-to-date PDF counterpart."""
    root = document.parent
    rsvg_convert = _find_rsvg_convert()

    if rsvg_convert is None:
        return {"rsvg_convert_available": False, "conversions": [], "failures": []}

    conversions: list[str] = []
    failures: list[str] = []

    for svg in sorted(root.rglob("*.svg")):
        rel = svg.relative_to(root)
        if is_skipped_source_path(rel):
            continue
        pdf = svg.with_suffix(".pdf")
        if pdf.exists() and pdf.stat().st_mtime >= svg.stat().st_mtime:
            continue
        if _run_rsvg_convert(rsvg_convert, svg, pdf):
            conversions.append(str(rel))
        else:
            failures.append(str(rel))

    return {
        "rsvg_convert_available": True,
        "conversions": conversions,
        "failures": failures,
    }

def normalize_bibliography_dois(bib_paths: list[Path], root: Path) -> list[str]:
    changes: list[str] = []

    for bib_path in bib_paths:
        text = read_text_safely(bib_path)
        if not text:
            continue

        updated_lines: list[str] = []
        modified = False

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            match = DOI_FIELD_PATTERN.match(raw_line)

            if match:
                value = match.group("value")
                normalized_value = re.sub(r"(?<!\\)_", r"\\_", value)

                if normalized_value != value:
                    raw_line = match.group("prefix") + normalized_value + "}" + match.group("suffix")
                    changes.append(
                        f"{bib_path.relative_to(root)}:{line_number}: escaped raw DOI underscore(s)"
                    )
                    modified = True

            updated_lines.append(raw_line)

        if modified:
            new_text = "\n".join(updated_lines)
            if text.endswith("\n"):
                new_text += "\n"
            bib_path.write_text(new_text, encoding="utf-8")

    return changes


def normalize_figure_path_separators(document: Path) -> list[str]:
    """Convert Windows backslashes to forward slashes in figure file arguments."""
    changes: list[str] = []

    for tex_path in gather_source_files(document):
        text = read_text_safely(tex_path)

        if not text:
            continue

        relative_path = tex_path.relative_to(document.parent)

        def replace_path(match: re.Match[str]) -> str:
            path = match.group("path")
            normalized = path.replace("\\", "/")

            if normalized != path:
                line_number = line_number_for_offset(text, match.start())
                changes.append(
                    f"{relative_path}:{line_number}: "
                    f"normalized figure path '{path}' -> '{normalized}'"
                )

            return match.group("prefix") + normalized + match.group("suffix")

        updated = FIGURE_COMMAND_PATTERN.sub(replace_path, text)

        if updated != text:
            tex_path.write_text(updated, encoding="utf-8")

    return changes


def _is_first_letter_case_only_mismatch(source: str, target: str) -> bool:
    if not source or not target:
        return False

    if len(source) != len(target):
        return False

    if source[1:] != target[1:]:
        return False

    return source[0] != target[0] and source[0].casefold() == target[0].casefold()


def normalize_citation_key_capitalization(document: Path) -> list[str]:
    """
    Auto-fix cite keys in .tex files when they differ from a bibliography key
    only by first-letter capitalization (e.g., Butler2008 -> butler2008).

    Ambiguous casefold matches are skipped and handled by duplicate-key checks.
    """
    bib_paths = gather_bibliography_files(document)
    variants_by_casefold: dict[str, set[str]] = {}

    for bib_path in bib_paths:
        for key in parse_bibliography_entries(bib_path):
            variants_by_casefold.setdefault(key.casefold(), set()).add(key)

    changes: list[str] = []

    for tex_path in gather_source_files(document):
        tex_text = read_text_safely(tex_path)

        if not tex_text:
            continue

        relative_tex_path = tex_path.relative_to(document.parent)
        updated_chunks: list[str] = []
        cursor = 0
        modified = False

        for match in CITE_COMMAND_PATTERN.finditer(tex_text):
            updated_chunks.append(tex_text[cursor:match.start()])
            citation_command = match.group(0)
            raw_keys = match.group("keys")
            updated_parts: list[str] = []

            for raw_part in raw_keys.split(","):
                key = raw_part.strip()

                if not key:
                    updated_parts.append(raw_part)
                    continue

                casefold_key = key.casefold()
                variants = variants_by_casefold.get(casefold_key, set())

                if len(variants) != 1:
                    updated_parts.append(raw_part)
                    continue

                bib_key = next(iter(variants))

                if not _is_first_letter_case_only_mismatch(key, bib_key):
                    updated_parts.append(raw_part)
                    continue

                line_number = line_number_for_offset(tex_text, match.start())
                leading_ws_len = len(raw_part) - len(raw_part.lstrip())
                trailing_ws_len = len(raw_part) - len(raw_part.rstrip())
                leading_ws = raw_part[:leading_ws_len]
                trailing_ws = raw_part[len(raw_part) - trailing_ws_len :] if trailing_ws_len else ""
                updated_parts.append(f"{leading_ws}{bib_key}{trailing_ws}")
                changes.append(
                    f"{relative_tex_path}:{line_number}: normalized cite key '{key}' -> '{bib_key}'"
                )
                modified = True

            updated_raw_keys = ",".join(updated_parts)

            if updated_raw_keys != raw_keys:
                start_in_cmd = match.start("keys") - match.start()
                end_in_cmd = match.end("keys") - match.start()
                citation_command = (
                    citation_command[:start_in_cmd]
                    + updated_raw_keys
                    + citation_command[end_in_cmd:]
                )

            updated_chunks.append(citation_command)
            cursor = match.end()

        updated_chunks.append(tex_text[cursor:])

        if modified:
            tex_path.write_text("".join(updated_chunks), encoding="utf-8")

    return unique_preserving_order(changes)


def scan_bibliography_preflight(document: Path) -> dict[str, Any]:
    bib_paths = gather_bibliography_files(document)
    bib_keys: dict[str, str] = {}
    bibliography_definitions: dict[str, list[str]] = {}
    bibliography_definitions_casefold: dict[str, list[tuple[str, str]]] = {}

    citation_usages: dict[str, list[str]] = {}

    for bib_path in bib_paths:
        relative_bib_path = bib_path.relative_to(document.parent)

        for key, line_numbers in parse_bibliography_entries(bib_path).items():
            bibliography_definitions.setdefault(key, []).extend(
                f"{relative_bib_path}:{line_number}"
                for line_number in line_numbers
            )

            bibliography_definitions_casefold.setdefault(key.casefold(), []).extend(
                (key, f"{relative_bib_path}:{line_number}")
                for line_number in line_numbers
            )

            bib_keys.setdefault(key.casefold(), key)

    capitalization_mismatches: list[str] = []
    underscores: list[str] = []

    bibliography_texts = {
        bib_path: read_text_safely(bib_path)
        for bib_path in bib_paths
    }

    for tex_path in gather_source_files(document):
        tex_text = read_text_safely(tex_path)
        relative_tex_path = tex_path.relative_to(document.parent)

        for match in CITE_COMMAND_PATTERN.finditer(tex_text):
            raw_keys = match.group("keys")
            line_number = line_number_for_offset(tex_text, match.start())

            for key in (part.strip() for part in raw_keys.split(",")):
                if not key:
                    continue

                citation_usages.setdefault(key, []).append(
                    f"{relative_tex_path}:{line_number}"
                )

                bib_key = bib_keys.get(key.casefold())

                if bib_key and bib_key != key:
                    capitalization_mismatches.append(
                        f"{relative_tex_path}:{line_number}: cite key '{key}' should match bibliography key '{bib_key}'"
                    )

    for bib_path, bib_text in bibliography_texts.items():
        for line_number, raw_line in enumerate(bib_text.splitlines(), start=1):
            stripped = raw_line.strip()

            if not stripped or stripped.startswith("%"):
                continue

            if stripped.startswith("@"):
                continue

            if "_" in raw_line and not re.search(r"\\_", raw_line):
                underscores.append(
                    f"{bib_path.relative_to(document.parent)}:{line_number}: raw underscore found: {stripped}"
                )

    duplicate_bibliography_keys: list[dict[str, Any]] = []

    for normalized_key in sorted(bibliography_definitions_casefold):
        raw_entries = bibliography_definitions_casefold[normalized_key]
        variants = unique_preserving_order([entry_key for entry_key, _ in raw_entries])
        definitions = unique_preserving_order([location for _, location in raw_entries])
        citations: list[str] = []

        for citation_key, locations in citation_usages.items():
            if citation_key.casefold() == normalized_key:
                citations.extend(locations)

        if len(definitions) > 1:
            preferred_key = variants[0] if variants else normalized_key
            duplicate_bibliography_keys.append(
                {
                    "key": preferred_key,
                    "variants": variants,
                    "definitions": definitions,
                    "citations": unique_preserving_order(citations),
                }
            )

    label_definitions: dict[str, list[str]] = {}

    for tex_path in gather_source_files(document):
        tex_text = read_text_safely(tex_path)

        if not tex_text:
            continue

        relative_tex_path = tex_path.relative_to(document.parent)

        for match in LABEL_COMMAND_PATTERN.finditer(tex_text):
            label = match.group("label").strip()

            if not label:
                continue
            # Ignore labels inside parameterized command definitions,
            # e.g. \label{fig:#3}
            if re.search(r"#\d", label):
                continue
            line_number = line_number_for_offset(tex_text, match.start())
            label_definitions.setdefault(label, []).append(
                f"{relative_tex_path}:{line_number}"
            )

    duplicate_labels_preflight: list[dict[str, Any]] = []

    for label in sorted(label_definitions):
        definitions = unique_preserving_order(label_definitions[label])

        if len(definitions) > 1:
            duplicate_labels_preflight.append(
                {
                    "label": label,
                    "definitions": definitions,
                }
            )

    return {
        "bibliography_files": [str(path.relative_to(document.parent)) for path in bib_paths],
        "capitalization_mismatches": unique_preserving_order(capitalization_mismatches),
        "raw_underscore_issues": unique_preserving_order(underscores),
        "duplicate_bibliography_keys": duplicate_bibliography_keys,
        "duplicate_labels_preflight": duplicate_labels_preflight,
    }
