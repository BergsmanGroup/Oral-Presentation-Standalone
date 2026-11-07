from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from .common import gather_bibliography_files, resolve_tex_document
from .diagnostics import build_diagnostics, write_text_report
from .preflight import (
    clean_stale_artifacts,
    convert_stale_svgs,
    normalize_bibliography_dois,
    normalize_citation_key_capitalization,
    normalize_figure_path_separators,
    scan_bibliography_preflight,
)


TRIGGER_CHOICES = ("save", "manual-standard", "manual-full", "unknown")
MAIN_BUILD_ARTIFACT_EXTENSIONS = {
    ".aux", ".bbl", ".blg", ".fdb_latexmk", ".fls", ".lof", ".log",
    ".lot", ".out", ".synctex.gz", ".toc",
}


def organize_main_build_artifacts(output_directory: Path) -> None:
    main_directory = output_directory / "chapters" / "main"
    main_directory.mkdir(parents=True, exist_ok=True)

    for path in output_directory.glob("main.*"):
        if path.is_file() and any(path.name.endswith(extension) for extension in MAIN_BUILD_ARTIFACT_EXTENSIONS):
            shutil.move(str(path), main_directory / path.name)

    for path in output_directory.glob("pdflatex*.fls"):
        if path.is_file():
            shutil.move(str(path), main_directory / path.name)


class ProgressTracker:
    def __init__(
        self,
        *,
        state_path: Path,
        events_path: Path,
        document: Path,
        trigger: str,
        clean_requested: bool,
    ) -> None:
        now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        self._state_path = state_path
        self._events_path = events_path
        self._state: dict[str, Any] = {
            "run_id": f"{now}-{uuid.uuid4().hex[:8]}",
            "timestamp": now,
            "document": str(document),
            "trigger": trigger,
            "status": "running",
            "phase": "preflight",
            "message": "Build started",
            "steps": [
                {
                    "id": "preflight.gather_bibliography",
                    "phase": "preflight",
                    "label": "Gather bibliography files",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "preflight.normalize_doi",
                    "phase": "preflight",
                    "label": "Normalize DOI underscores",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "preflight.normalize_citation_case",
                    "phase": "preflight",
                    "label": "Normalize citation key capitalization",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "preflight.normalize_figure_paths",
                    "phase": "preflight",
                    "label": "Normalize figure path separators",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "preflight.check_citation_mismatches",
                    "phase": "preflight",
                    "label": "Check citation key mismatches",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "preflight.check_raw_underscores",
                    "phase": "preflight",
                    "label": "Check raw bibliography underscores",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "preflight.check_duplicate_bibliography_keys",
                    "phase": "preflight",
                    "label": "Check duplicate bibliography keys",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "preflight.check_duplicate_labels",
                    "phase": "preflight",
                    "label": "Check duplicate labels",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "preflight.convert_svg",
                    "phase": "preflight",
                    "label": "Convert stale SVG figures",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "build.clean",
                    "phase": "build",
                    "label": "Clean stale artifacts",
                    "status": "pending" if clean_requested else "skipped",
                    "message": "" if clean_requested else "Not requested",
                },
                {
                    "id": "build.latexmk",
                    "phase": "build",
                    "label": "Run latexmk",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "build.parse_diagnostics",
                    "phase": "build",
                    "label": "Parse diagnostics",
                    "status": "pending",
                    "message": "",
                },
                {
                    "id": "build.write_reports",
                    "phase": "build",
                    "label": "Write reports",
                    "status": "pending",
                    "message": "",
                },
            ],
        }
        self.persist()
        self.emit("run_start", {
            "trigger": trigger,
            "document": str(document),
            "clean_requested": clean_requested,
        })

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        event = {
            "timestamp": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "run_id": self._state["run_id"],
            "event": event_type,
            "payload": payload or {},
        }
        with self._events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def persist(self) -> None:
        self._state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def set_phase(self, phase: str, message: str = "") -> None:
        self._state["phase"] = phase
        if message:
            self._state["message"] = message
        self.persist()

    def set_status(self, status: str, message: str = "") -> None:
        self._state["status"] = status
        if message:
            self._state["message"] = message
        self.persist()

    def _find_step(self, step_id: str) -> dict[str, Any]:
        for step in self._state["steps"]:
            if step["id"] == step_id:
                return step
        raise KeyError(f"Unknown step id: {step_id}")

    def start_step(self, step_id: str, message: str = "") -> None:
        step = self._find_step(step_id)
        step["status"] = "running"
        if message:
            step["message"] = message
        self.persist()
        self.emit("step_start", {"step_id": step_id, "message": message})

    def finish_step(self, step_id: str, status: str, message: str = "") -> None:
        step = self._find_step(step_id)
        step["status"] = status
        if message:
            step["message"] = message
        self.persist()
        self.emit("step_end", {"step_id": step_id, "status": status, "message": message})

    def snapshot_steps(self) -> list[dict[str, Any]]:
        return [dict(step) for step in self._state["steps"]]



def _default_preflight_payload() -> dict[str, Any]:
    return {
        "bibliography_files": [],
        "capitalization_mismatches": [],
        "raw_underscore_issues": [],
        "duplicate_bibliography_keys": [],
        "duplicate_labels_preflight": [],
        "doi_fixes": [],
        "citation_case_fixes": [],
        "figure_path_fixes": [],
        "svg_conversions": {
            "inkscape_available": False,
            "conversions": [],
            "failures": [],
        },
        "step_errors": [],
    }


def _mark_remaining_build_steps_as_skipped(progress: ProgressTracker) -> None:
    for step_id in ("build.latexmk", "build.parse_diagnostics", "build.write_reports"):
        progress.finish_step(step_id, "skipped", "Skipped because preflight blocked build")


def _finish_preflight_scan_steps(progress: ProgressTracker, preflight: dict[str, Any]) -> None:
    cap_mismatches = preflight["capitalization_mismatches"]
    raw_underscores = preflight["raw_underscore_issues"]
    duplicate_keys = preflight["duplicate_bibliography_keys"]
    duplicate_labels = preflight["duplicate_labels_preflight"]

    progress.finish_step(
        "preflight.check_citation_mismatches",
        "success" if not cap_mismatches else "failed",
        f"Found {len(cap_mismatches)} citation mismatch issue(s)",
    )
    progress.finish_step(
        "preflight.check_raw_underscores",
        "success" if not raw_underscores else "failed",
        f"Found {len(raw_underscores)} raw underscore issue(s)",
    )
    progress.finish_step(
        "preflight.check_duplicate_bibliography_keys",
        "success" if not duplicate_keys else "failed",
        f"Found {len(duplicate_keys)} duplicate bibliography key issue(s)",
    )
    progress.finish_step(
        "preflight.check_duplicate_labels",
        "success" if not duplicate_labels else "failed",
        f"Found {len(duplicate_labels)} duplicate label issue(s)",
    )


def _fail_preflight_scan_steps(progress: ProgressTracker, message: str) -> None:
    for step_id in (
        "preflight.check_citation_mismatches",
        "preflight.check_raw_underscores",
        "preflight.check_duplicate_bibliography_keys",
        "preflight.check_duplicate_labels",
    ):
        progress.finish_step(step_id, "failed", message)


def _append_preflight_checklist(lines: list[str], steps: list[dict[str, Any]]) -> None:
    lines.extend([
        "PRE-FLIGHT CHECKLIST",
        "-" * 72,
    ])

    for step in steps:
        if step.get("phase") != "preflight":
            continue

        label = step.get("label", "Step")
        status = str(step.get("status", "pending")).upper()
        message = step.get("message", "")
        suffix = f": {message}" if message else ""
        lines.append(f"- [{status}] {label}{suffix}")

    lines.append("")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run latexmk and create concise, deduplicated diagnostics."
        )
    )

    parser.add_argument(
        "--doc",
        default="C-main.tex",
        help="Path to the root TeX document, with or without .tex (default: C-main.tex).",
    )

    parser.add_argument(
        "--outdir",
        default="build",
        help="LaTeX output directory (default: build).",
    )

    parser.add_argument(
        "--clean",
        action="store_true",
        help="Wipe all latexmk-generated files before building (full rebuild).",
    )

    parser.add_argument(
        "--trigger",
        choices=TRIGGER_CHOICES,
        default="unknown",
        help="Build trigger source used by UI integration.",
    )

    args = parser.parse_args()

    try:
        document = resolve_tex_document(args.doc)
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 2

    output_directory = Path(args.outdir).expanduser()

    if not output_directory.is_absolute():
        output_directory = document.parent / output_directory

    output_directory = output_directory.resolve()
    latex_output_directory = output_directory
    diagnostics_directory = output_directory / "diagnostics"
    latex_output_directory.mkdir(parents=True, exist_ok=True)
    diagnostics_directory.mkdir(parents=True, exist_ok=True)

    raw_output_path = diagnostics_directory / "latexmk-output.txt"
    report_path = diagnostics_directory / "last-build-errors.txt"
    diagnostics_path = diagnostics_directory / "diagnostics.json"
    progress_state_path = diagnostics_directory / "progress-state.json"
    progress_events_path = diagnostics_directory / "progress-events.jsonl"

    progress = ProgressTracker(
        state_path=progress_state_path,
        events_path=progress_events_path,
        document=document,
        trigger=args.trigger,
        clean_requested=args.clean,
    )

    preflight: dict[str, Any] = _default_preflight_payload()
    step_errors: list[str] = preflight["step_errors"]

    progress.start_step("preflight.gather_bibliography")
    try:
        bibliography_files = gather_bibliography_files(document)
        preflight["bibliography_files"] = [
            str(path.relative_to(document.parent))
            for path in bibliography_files
        ]
        progress.finish_step(
            "preflight.gather_bibliography",
            "success",
            f"Found {len(bibliography_files)} bibliography file(s)",
        )
    except Exception as error:
        step_errors.append(
            f"gather_bibliography_files failed: {error.__class__.__name__}: {error}"
        )
        bibliography_files = []
        progress.finish_step("preflight.gather_bibliography", "failed", step_errors[-1])

    progress.start_step("preflight.normalize_doi")
    try:
        preflight["doi_fixes"] = normalize_bibliography_dois(
            bibliography_files,
            document.parent,
        )
        progress.finish_step(
            "preflight.normalize_doi",
            "success",
            f"Applied {len(preflight['doi_fixes'])} DOI fix(es)",
        )
    except Exception as error:
        step_errors.append(
            f"normalize_bibliography_dois failed: {error.__class__.__name__}: {error}"
        )
        progress.finish_step("preflight.normalize_doi", "failed", step_errors[-1])

    progress.start_step("preflight.normalize_citation_case")
    try:
        preflight["citation_case_fixes"] = normalize_citation_key_capitalization(document)
        progress.finish_step(
            "preflight.normalize_citation_case",
            "success",
            f"Applied {len(preflight['citation_case_fixes'])} citation capitalization fix(es)",
        )
    except Exception as error:
        step_errors.append(
            f"normalize_citation_key_capitalization failed: {error.__class__.__name__}: {error}"
        )
        progress.finish_step("preflight.normalize_citation_case", "failed", step_errors[-1])

    progress.start_step("preflight.normalize_figure_paths")
    try:
        preflight["figure_path_fixes"] = normalize_figure_path_separators(document)
        progress.finish_step(
            "preflight.normalize_figure_paths",
            "success",
            f"Applied {len(preflight['figure_path_fixes'])} figure path fix(es)",
        )
    except Exception as error:
        step_errors.append(
            f"normalize_figure_path_separators failed: {error.__class__.__name__}: {error}"
        )
        progress.finish_step("preflight.normalize_figure_paths", "failed", step_errors[-1])

    for step_id in (
        "preflight.check_citation_mismatches",
        "preflight.check_raw_underscores",
        "preflight.check_duplicate_bibliography_keys",
        "preflight.check_duplicate_labels",
    ):
        progress.start_step(step_id)

    try:
        scan_result = scan_bibliography_preflight(document)
        preflight.update(scan_result)
        _finish_preflight_scan_steps(progress, preflight)
    except Exception as error:
        message = (
            "scan_bibliography_preflight failed: "
            f"{error.__class__.__name__}: {error}"
        )
        step_errors.append(message)
        _fail_preflight_scan_steps(progress, message)

    progress.start_step("preflight.convert_svg")
    try:
        preflight["svg_conversions"] = convert_stale_svgs(document)
        conversions = preflight["svg_conversions"]["conversions"]
        failures = preflight["svg_conversions"]["failures"]
        progress.finish_step(
            "preflight.convert_svg",
            "success" if not failures else "failed",
            f"Converted {len(conversions)} SVG(s), failed {len(failures)}",
        )
    except Exception as error:
        step_errors.append(
            f"convert_stale_svgs failed: {error.__class__.__name__}: {error}"
        )
        progress.finish_step("preflight.convert_svg", "failed", step_errors[-1])

    # Build should stop on duplicate keys, cap mismatches, and unfixed underscores.
    duplicate_key_issues = [
        (
            f"duplicate bibliography key '{dup['key']}' defined at "
            f"{', '.join(dup['definitions'])}"
            + (
                f" (variants: {', '.join(dup['variants'])})"
                if dup.get("variants") else ""
            )
        )
        for dup in preflight["duplicate_bibliography_keys"]
    ]

    duplicate_label_issues = [
        (
            f"duplicate label '{dup['label']}' defined at "
            f"{', '.join(dup['definitions'])}"
        )
        for dup in preflight["duplicate_labels_preflight"]
    ]

    # Duplicate keys/labels, cap mismatches, and unfixed underscores block the build.
    blocking_issues = (
        duplicate_key_issues
        + duplicate_label_issues
        + preflight["capitalization_mismatches"]
        + preflight["raw_underscore_issues"]
        + step_errors
    )

    progress.set_phase("preflight", "Preflight completed")
    preflight["step_statuses"] = progress.snapshot_steps()

    if blocking_issues:
        progress.set_status("blocked", f"Preflight blocked build with {len(blocking_issues)} issue(s)")
        _mark_remaining_build_steps_as_skipped(progress)
        progress.emit("run_blocked", {"blocking_issue_count": len(blocking_issues)})

        timestamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        report_lines = [
            "=" * 72,
            "LaTeX BUILD BLOCKED",
            "=" * 72,
            f"Time:      {timestamp}",
            f"Document:  {document}",
            f"Trigger:   {args.trigger}",
            "",
        ]
        _append_preflight_checklist(report_lines, preflight["step_statuses"])
        doi_fixes = preflight["doi_fixes"]
        if doi_fixes:
            report_lines.append(f"DOI underscores auto-fixed ({len(doi_fixes)}):")
            report_lines.extend(f"  {fix}" for fix in doi_fixes)
            report_lines.append("")
        citation_case_fixes = preflight["citation_case_fixes"]
        if citation_case_fixes:
            report_lines.append(
                f"Citation key capitalization auto-fixed ({len(citation_case_fixes)}):"
            )
            report_lines.extend(f"  {fix}" for fix in citation_case_fixes)
            report_lines.append("")
        figure_path_fixes = preflight["figure_path_fixes"]
        if figure_path_fixes:
            report_lines.append(
                f"Figure path separators auto-fixed ({len(figure_path_fixes)}):"
            )
            report_lines.extend(f"  {fix}" for fix in figure_path_fixes)
            report_lines.append("")
        if step_errors:
            report_lines.append(f"Preflight step failures ({len(step_errors)}):")
            report_lines.extend(f"  {issue}" for issue in step_errors)
            report_lines.append("")
        cap_mismatches = preflight["capitalization_mismatches"]
        if cap_mismatches:
            report_lines.append(f"Capitalization mismatches ({len(cap_mismatches)}):")
            report_lines.extend(f"  {issue}" for issue in cap_mismatches)
            report_lines.append("")
        raw_underscores = preflight["raw_underscore_issues"]
        if raw_underscores:
            report_lines.append(f"Remaining raw underscores ({len(raw_underscores)}):")
            report_lines.extend(f"  {issue}" for issue in raw_underscores)
            report_lines.append("")
        duplicate_keys = preflight["duplicate_bibliography_keys"]
        if duplicate_keys:
            report_lines.append(f"Duplicate bibliography keys ({len(duplicate_keys)}):")
            for dup in duplicate_keys:
                report_lines.append(f"  {dup['key']}")
                if dup.get("variants"):
                    report_lines.append(f"    Variants: {', '.join(dup['variants'])}")
                report_lines.append(f"    Definitions: {', '.join(dup['definitions'])}")
                if dup.get("citations"):
                    report_lines.append(f"    Citations: {', '.join(dup['citations'])}")
            report_lines.append("")
        duplicate_labels = preflight["duplicate_labels_preflight"]
        if duplicate_labels:
            report_lines.append(f"Duplicate labels in source ({len(duplicate_labels)}):")
            for dup in duplicate_labels:
                report_lines.append(f"  {dup['label']}")
                report_lines.append(f"    Definitions: {', '.join(dup['definitions'])}")
            report_lines.append("")
        report_lines.extend([
            f"BLOCKING PREFLIGHT ISSUES ({len(blocking_issues)})",
            "-" * 72,
        ])
        report_lines.extend(f"- {issue}" for issue in blocking_issues)
        report_lines.extend([
            "",
            "BUILD STATUS",
            "-" * 72,
            "Build cancelled before latexmk because preflight checks failed.",
            "",
        ])
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        raw_output_path.write_text(
            "Build cancelled: preflight checks failed.\n",
            encoding="utf-8",
        )
        diagnostics_path.write_text(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "document": str(document),
                    "output_directory": str(output_directory),
                    "trigger": args.trigger,
                    "status": "blocked",
                    "exit_code": 1,
                    "preflight": preflight,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        first_issue = blocking_issues[0]
        summary = (
            "Preflight checks failed "
            f"({len(blocking_issues)} issue(s)). "
            f"First issue: {first_issue}. "
            f"See {report_path}"
        )
        print(summary, file=sys.stderr)
        return 1

    progress.set_phase("build", "Build in progress")

    if args.clean:
        progress.start_step("build.clean")
        try:
            clean_stale_artifacts(document, latex_output_directory)
            progress.finish_step("build.clean", "success", "Clean completed")
        except Exception as error:
            progress.finish_step(
                "build.clean",
                "failed",
                f"clean_stale_artifacts failed: {error.__class__.__name__}: {error}",
            )

    command = [
        "latexmk",
        "-synctex=1",
        "-interaction=nonstopmode",
        "-file-line-error",
        "-pdf",
        f"-outdir={latex_output_directory}",
        str(document),
    ]

    progress.start_step("build.latexmk")
    try:
        completed = subprocess.run(
            command,
            cwd=document.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        output = completed.stdout or ""
        return_code = completed.returncode
        progress.finish_step("build.latexmk", "success" if return_code == 0 else "failed", f"latexmk exit code {return_code}")

    except FileNotFoundError:
        output = (
            "Fatal error: latexmk could not be found.\n"
            "Confirm that the TeX Live binary directory is on PATH.\n"
        )
        return_code = 127
        progress.finish_step("build.latexmk", "failed", "latexmk not found")

    except Exception as error:
        output = f"Fatal error while running latexmk: {error}\n"
        return_code = 1
        progress.finish_step(
            "build.latexmk",
            "failed",
            f"latexmk invocation failed: {error.__class__.__name__}: {error}",
        )

    raw_output_path.write_text(output, encoding="utf-8")

    # Preserve normal LaTeX Workshop output.
    print(output, end="")

    progress.start_step("build.parse_diagnostics")
    diagnostics = build_diagnostics(
        document=document,
        output_directory=latex_output_directory,
        command=command,
        return_code=return_code,
        stdout=output,
    )
    diagnostics["preflight"] = preflight
    diagnostics["trigger"] = args.trigger
    progress.finish_step("build.parse_diagnostics", "success", "Diagnostics parsed")

    diagnostics_path.write_text(
        json.dumps(diagnostics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    progress.start_step("build.write_reports")
    write_text_report(
        report_path=report_path,
        raw_output_path=raw_output_path,
        diagnostics_path=diagnostics_path,
        diagnostics=diagnostics,
    )
    progress.finish_step("build.write_reports", "success", "Reports written")

    organize_main_build_artifacts(output_directory)

    final_status = "success" if return_code == 0 else "failed"
    progress.set_status(final_status, f"Build {final_status} (exit code {return_code})")
    progress.emit("run_end", {"status": final_status, "exit_code": return_code})

    print(f"\nConcise diagnostics: {report_path}")
    print(f"Structured diagnostics: {diagnostics_path}")
    print(f"Complete build output: {raw_output_path}")
    print(f"Progress state: {progress_state_path}")

    return return_code
