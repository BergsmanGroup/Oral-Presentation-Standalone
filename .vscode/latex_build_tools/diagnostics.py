from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .common import (
    INCLUDE_BOX_WARNINGS,
    SUPPRESS_SECONDARY_UNDEFINEDS_ON_PRIMARY_ERROR,
    quote_command,
    read_text_safely,
    unique_preserving_order,
)


SOURCE_LOCATION_PATTERN = re.compile(r"^(?P<path>(?:[A-Za-z]:)?[^:]+?):(?P<line>\d+):\s*(?P<message>.*)$")


def extract_stdout_errors(output: str) -> list[str]:
    """
    Extract high-level execution failures from latexmk console output.

    Detailed LaTeX and BibTeX diagnostics are obtained separately from
    .log and .blg files.
    """
    patterns = [
        re.compile(r"^latexmk:.*errors", re.IGNORECASE),
        re.compile(r"^latexmk:.*failed", re.IGNORECASE),
        re.compile(r"^latexmk:.*did not complete", re.IGNORECASE),
        re.compile(r"command failed with exit code", re.IGNORECASE),
        re.compile(r"fatal error", re.IGNORECASE),
        re.compile(r"emergency stop", re.IGNORECASE),
        re.compile(r"could not be found", re.IGNORECASE),
    ]

    errors: list[str] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if any(pattern.search(line) for pattern in patterns):
            errors.append(line)

    return unique_preserving_order(errors)


def parse_latex_log(log_path: Path) -> dict[str, Any]:
    """
    Parse the root LaTeX .log file.

    Returns unique citation/reference names plus LaTeX errors and optional
    box warnings.
    """
    text = read_text_safely(log_path)

    citation_pattern = re.compile(
        r"(?:Package\s+natbib\s+Warning:\s+)?"
        r"Citation\s+[`']([^`']+)[`']"
        r".*?\bundefined\b",
        re.IGNORECASE,
    )

    reference_pattern = re.compile(
        r"(?:LaTeX\s+Warning:\s+)?"
        r"Reference\s+[`']([^`']+)[`']"
        r".*?\bundefined\b",
        re.IGNORECASE,
    )

    duplicate_label_pattern = re.compile(
        r"Label\s+[`']([^`']+)[`']\s+multiply defined",
        re.IGNORECASE,
    )

    citations = citation_pattern.findall(text)
    references = reference_pattern.findall(text)
    duplicate_labels = duplicate_label_pattern.findall(text)

    citation_counts = Counter(citations)
    reference_counts = Counter(references)
    duplicate_label_counts = Counter(duplicate_labels)

    latex_errors: list[str] = []
    box_warnings: list[str] = []

    lines = text.splitlines()

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()

        if not line:
            continue

        is_error = (
            line.startswith("!")
            or "LaTeX Error:" in line
            or re.search(r"Package\s+\S+\s+Error:", line)
            or re.search(r"Class\s+\S+\s+Error:", line)
            or "Undefined control sequence" in line
            or "Runaway argument" in line
            or "Emergency stop" in line
            or "Fatal error occurred" in line
        )

        if is_error:
            context = [line]

            # Capture nearby source-line context such as:
            # ./path/to/file.tex:42: Paragraph ended before ...
            # l.42 \badcommand
            for following in lines[index + 1 : index + 6]:
                following = following.strip()

                if not following:
                    break

                if (
                    following.startswith("l.")
                    or following.startswith("<")
                    or SOURCE_LOCATION_PATTERN.match(following)
                ):
                    context.append(f"    {following}")

            latex_errors.append("\n".join(context))

        if INCLUDE_BOX_WARNINGS and re.search(
            r"(?:Overfull|Underfull) \\[hv]box",
            line,
            re.IGNORECASE,
        ):
            # Capture the text excerpt on the next line - it names the offending words
            context = [line]
            if index + 1 < len(lines):
                excerpt = lines[index + 1].strip()
                if excerpt and not excerpt.startswith(("[", "(")):
                    context.append(f"    {excerpt}")
            box_warnings.append("\n".join(context))

    empty_bibliographies = len(
        re.findall(
            r"Empty [`']thebibliography['`] environment",
            text,
            re.IGNORECASE,
        )
    )

    return {
        "path": str(log_path),
        "latex_errors": unique_preserving_order(latex_errors),
        "undefined_citations": dict(sorted(citation_counts.items())),
        "undefined_references": dict(sorted(reference_counts.items())),
        "duplicate_labels": dict(sorted(duplicate_label_counts.items())),
        "empty_bibliographies": empty_bibliographies,
        "box_warnings": unique_preserving_order(box_warnings),
    }


def classify_bibtex_warning(message: str) -> dict[str, str]:
    """
    Convert a BibTeX warning into a structured warning record.
    """
    missing_entry = re.search(
        r"I didn't find a database entry for [\"'](.+?)[\"']$",
        message,
        re.IGNORECASE,
    )

    if missing_entry:
        return {
            "type": "missing_database_entry",
            "key": missing_entry.group(1).strip(),
            "message": message,
        }

    entry_match = re.search(
        r"\bin\s+([^\s]+)$",
        message,
        re.IGNORECASE,
    )

    entry = entry_match.group(1).strip() if entry_match else ""

    if "can't use both author and editor fields" in message.lower():
        warning_type = "author_and_editor"
    elif re.search(r"\bempty\s+\w+", message, re.IGNORECASE):
        warning_type = "empty_field"
    elif "can't use both volume and number fields" in message.lower():
        warning_type = "volume_and_number"
    elif "too many commas in name" in message.lower():
        warning_type = "malformed_name"
    else:
        warning_type = "other"

    return {
        "type": warning_type,
        "entry": entry,
        "message": message,
    }


def parse_blg_file(blg_path: Path) -> dict[str, Any]:
    """
    Parse one BibTeX .blg file.
    """
    text = read_text_safely(blg_path)
    lines = text.splitlines()

    warnings: list[dict[str, str]] = []
    errors: list[str] = []

    for index, raw_line in enumerate(lines):
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("Warning--"):
            message = line.removeprefix("Warning--").strip()
            warnings.append(classify_bibtex_warning(message))
            continue

        if line.startswith("Repeated entry---line"):
            context = [line]

            for following in lines[index + 1 : index + 4]:
                following = following.strip()

                if not following:
                    break

                if following.startswith(":") or following.startswith("I'm skipping"):
                    context.append(f"    {following}")

            errors.append("\n".join(context))
            continue

        if (
            line.startswith("I couldn't open")
            or line.startswith("I found no")
            or "Too many commas in name" in line
            or "Illegal, another \\bibstyle command" in line
            or "Illegal, another \\bibdata command" in line
        ):
            context = [line]

            for following in lines[index + 1 : index + 3]:
                following = following.strip()

                if following.startswith("while executing"):
                    context.append(f"    {following}")

            errors.append("\n".join(context))

    return {
        "path": str(blg_path),
        "name": blg_path.stem,
        "warnings": warnings,
        "errors": unique_preserving_order(errors),
    }


def collect_bibtex_results(output_directory: Path) -> list[dict[str, Any]]:
    """
    Find every BibTeX log recursively below the build directory.
    """
    return [
        parse_blg_file(path)
        for path in sorted(output_directory.rglob("*.blg"))
    ]


def build_diagnostics(
    document: Path,
    output_directory: Path,
    command: list[str],
    return_code: int,
    stdout: str,
) -> dict[str, Any]:
    root_log = output_directory / f"{document.stem}.log"
    latex = parse_latex_log(root_log)

    bibtex_files = collect_bibtex_results(output_directory)
    stdout_errors = extract_stdout_errors(stdout)

    missing_entries: dict[str, list[str]] = {}
    bibliography_warnings: list[dict[str, str]] = []
    bibtex_errors: list[dict[str, str]] = []

    for bibtex_file in bibtex_files:
        source_name = bibtex_file["name"]

        for warning in bibtex_file["warnings"]:
            if warning["type"] == "missing_database_entry":
                key = warning["key"]
                missing_entries.setdefault(key, []).append(source_name)
            else:
                bibliography_warnings.append(
                    {
                        "bibliography": source_name,
                        **warning,
                    }
                )

        for error in bibtex_file["errors"]:
            bibtex_errors.append(
                {
                    "bibliography": source_name,
                    "message": error,
                }
            )

    # Deduplicate metadata warnings from repeated BibTeX invocations.
    unique_bibliography_warnings: list[dict[str, str]] = []
    seen_bibliography_warnings: set[tuple[str, str, str]] = set()

    for warning in bibliography_warnings:
        identity = (
            warning.get("bibliography", ""),
            warning.get("entry", ""),
            warning.get("message", ""),
        )

        if identity not in seen_bibliography_warnings:
            seen_bibliography_warnings.add(identity)
            unique_bibliography_warnings.append(warning)

    timestamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    return {
        "timestamp": timestamp,
        "document": str(document),
        "output_directory": str(output_directory),
        "status": "success" if return_code == 0 else "failed",
        "exit_code": return_code,
        "command": command,
        "latex_log": latex,
        "execution_errors": stdout_errors,
        "bibtex_errors": bibtex_errors,
        "missing_bibliography_entries": {
            key: sorted(set(sources))
            for key, sources in sorted(missing_entries.items())
        },
        "bibliography_warnings": unique_bibliography_warnings,
        "bibtex_logs": [item["path"] for item in bibtex_files],
    }


def format_counted_items(items: dict[str, int]) -> list[str]:
    lines: list[str] = []

    for name, count in items.items():
        if count == 1:
            lines.append(f"- {name}")
        else:
            lines.append(f"- {name}  ({count} occurrences)")

    return lines


def write_text_report(
    report_path: Path,
    raw_output_path: Path,
    diagnostics_path: Path,
    diagnostics: dict[str, Any],
) -> None:
    status = diagnostics["status"].upper()
    timestamp = diagnostics["timestamp"]
    latex = diagnostics["latex_log"]

    lines = [
        "=" * 72,
        f"LaTeX BUILD {status}",
        "=" * 72,
        f"Time:      {timestamp}",
        f"Document:  {diagnostics['document']}",
        f"Trigger:   {diagnostics.get('trigger', 'unknown')}",
        f"Exit code: {diagnostics['exit_code']}",
        "",
        "Command:",
        quote_command(diagnostics["command"]),
        "",
    ]

    preflight = diagnostics.get("preflight", {})
    if preflight:
        doi_fixes = preflight.get("doi_fixes", [])
        citation_case_fixes = preflight.get("citation_case_fixes", [])
        step_errors = preflight.get("step_errors", [])
        step_statuses = preflight.get("step_statuses", [])
        cap_mismatches = preflight.get("capitalization_mismatches", [])
        raw_underscores = preflight.get("raw_underscore_issues", [])
        dup_keys = preflight.get("duplicate_bibliography_keys", [])
        dup_labels_preflight = preflight.get("duplicate_labels_preflight", [])

        lines.extend(["PRE-FLIGHT", "-" * 72])

        if step_statuses:
            lines.append("Checklist:")
            for step in step_statuses:
                if step.get("phase") != "preflight":
                    continue

                label = step.get("label", "Step")
                status = str(step.get("status", "pending")).upper()
                message = step.get("message", "")
                suffix = f": {message}" if message else ""
                lines.append(f"  [{status}] {label}{suffix}")

        svg_result = preflight.get("svg_conversions", {})
        svg_conversions = svg_result.get("conversions", [])
        svg_failures = svg_result.get("failures", [])
        if svg_conversions:
            lines.append(f"SVG->PDF converted ({len(svg_conversions)}):")
            lines.extend(f"  {c}" for c in svg_conversions)
        if svg_failures:
            lines.append(f"SVG->PDF failed ({len(svg_failures)}):")
            lines.extend(f"  {f}" for f in svg_failures)

        if doi_fixes:
            lines.append(f"DOI underscores auto-fixed ({len(doi_fixes)}):")
            lines.extend(f"  {fix}" for fix in doi_fixes)
        else:
            lines.append("No DOI underscore fixes were needed.")

        if citation_case_fixes:
            lines.append(
                f"Citation key capitalization auto-fixed ({len(citation_case_fixes)}):"
            )
            lines.extend(f"  {fix}" for fix in citation_case_fixes)

        if step_errors:
            lines.append(f"Preflight step failures ({len(step_errors)}):")
            lines.extend(f"  {issue}" for issue in step_errors)

        if cap_mismatches:
            lines.append(f"Capitalization mismatches ({len(cap_mismatches)}):")
            lines.extend(f"  {m}" for m in cap_mismatches)

        if raw_underscores:
            lines.append(f"Remaining raw underscores ({len(raw_underscores)}):")
            lines.extend(f"  {u}" for u in raw_underscores)

        if dup_keys:
            lines.append(f"Duplicate bibliography keys ({len(dup_keys)}):")
            for dup in dup_keys:
                lines.append(f"  {dup['key']}")
                if dup.get("variants"):
                    lines.append(f"    Variants: {', '.join(dup['variants'])}")
                lines.append(f"    Definitions: {', '.join(dup['definitions'])}")
                if dup["citations"]:
                    lines.append(f"    Citations: {', '.join(dup['citations'])}")

        if dup_labels_preflight:
            lines.append(f"Duplicate labels in source ({len(dup_labels_preflight)}):")
            for dup in dup_labels_preflight:
                lines.append(f"  {dup['label']}")
                lines.append(f"    Definitions: {', '.join(dup['definitions'])}")

        lines.append("")

    execution_errors = diagnostics["execution_errors"]
    latex_errors = latex["latex_errors"]
    bibtex_errors = diagnostics["bibtex_errors"]

    total_errors = (
        len(execution_errors)
        + len(latex_errors)
        + len(bibtex_errors)
    )

    lines.extend(
        [
            f"ERRORS ({total_errors})",
            "-" * 72,
        ]
    )

    if total_errors == 0:
        lines.append("No compiler errors were found.")
    else:
        for message in latex_errors:
            lines.append(f"- {message}")

        for error in bibtex_errors:
            lines.append(
                f"- [{error['bibliography']}] {error['message']}"
            )

        for message in execution_errors:
            lines.append(f"- {message}")

    missing_entries = diagnostics["missing_bibliography_entries"]

    lines.extend(
        [
            "",
            f"MISSING BIBLIOGRAPHY ENTRIES ({len(missing_entries)})",
            "-" * 72,
        ]
    )

    if missing_entries:
        for key, sources in missing_entries.items():
            lines.append(f"- {key}")
            lines.append(f"    Bibliography: {', '.join(sources)}")
    else:
        lines.append("No missing bibliography database entries were found.")

    undefined_citations = latex["undefined_citations"]
    has_primary_errors = (len(latex_errors) + len(bibtex_errors)) > 0

    lines.extend(
        [
            "",
            f"UNDEFINED CITATIONS ({len(undefined_citations)} unique)",
            "-" * 72,
        ]
    )

    if (
        undefined_citations
        and SUPPRESS_SECONDARY_UNDEFINEDS_ON_PRIMARY_ERROR
        and has_primary_errors
    ):
        lines.append(
            "Suppressed detailed citation list because upstream LaTeX/BibTeX errors were found."
        )
        lines.append(
            "Fix the ERRORS section first, then rebuild to see remaining unresolved citations."
        )
    elif undefined_citations:
        lines.extend(format_counted_items(undefined_citations))
    else:
        lines.append("No undefined citations were found.")

    undefined_references = latex["undefined_references"]

    lines.extend(
        [
            "",
            f"UNDEFINED REFERENCES ({len(undefined_references)} unique)",
            "-" * 72,
        ]
    )

    if (
        undefined_references
        and SUPPRESS_SECONDARY_UNDEFINEDS_ON_PRIMARY_ERROR
        and has_primary_errors
    ):
        lines.append(
            "Suppressed detailed reference list because upstream LaTeX/BibTeX errors were found."
        )
        lines.append(
            "Fix the ERRORS section first, then rebuild to see remaining unresolved references."
        )
    elif undefined_references:
        lines.extend(format_counted_items(undefined_references))
    else:
        lines.append("No undefined references were found.")

    duplicate_labels = latex["duplicate_labels"]

    lines.extend(
        [
            "",
            f"DUPLICATE LABELS ({len(duplicate_labels)} unique)",
            "-" * 72,
        ]
    )

    if duplicate_labels:
        lines.extend(format_counted_items(duplicate_labels))
    else:
        lines.append("No duplicate labels were found.")

    bibliography_warnings = diagnostics["bibliography_warnings"]

    lines.extend(
        [
            "",
            f"BIBLIOGRAPHY METADATA WARNINGS ({len(bibliography_warnings)})",
            "-" * 72,
        ]
    )

    if bibliography_warnings:
        for warning in bibliography_warnings:
            bibliography = warning.get("bibliography", "")
            entry = warning.get("entry", "")
            message = warning.get("message", "")

            heading_parts = [part for part in [bibliography, entry] if part]
            heading = " | ".join(heading_parts)

            if heading:
                lines.append(f"- [{heading}] {message}")
            else:
                lines.append(f"- {message}")
    else:
        lines.append("No bibliography metadata warnings were found.")

    if latex["empty_bibliographies"]:
        lines.extend(
            [
                "",
                "EMPTY BIBLIOGRAPHIES",
                "-" * 72,
                (
                    f"LaTeX reported {latex['empty_bibliographies']} empty "
                    "thebibliography environment(s)."
                ),
                (
                    "This can be harmless for chapters with no citations, but it "
                    "should be checked if a cited chapter has an empty bibliography."
                ),
            ]
        )

    if INCLUDE_BOX_WARNINGS:
        box_warnings = latex["box_warnings"]

        lines.extend(
            [
                "",
                f"BOX WARNINGS ({len(box_warnings)})",
                "-" * 72,
            ]
        )

        if box_warnings:
            lines.extend(f"- {warning}" for warning in box_warnings)
        else:
            lines.append("No overfull or underfull box warnings were found.")

    lines.extend(
        [
            "",
            "OUTPUT FILES",
            "-" * 72,
            f"Complete console output: {raw_output_path}",
            f"Structured diagnostics:  {diagnostics_path}",
            f"Root LaTeX log:          {latex['path']}",
            "",
        ]
    )

    report_path.write_text("\n".join(lines), encoding="utf-8")
