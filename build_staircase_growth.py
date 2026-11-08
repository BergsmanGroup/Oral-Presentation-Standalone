"""Generate half-cycle comparison and staircase-growth figures."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from openpyxl import load_workbook


DEFAULT_INPUT = Path("assets") / "other" / "staircase_growth.xlsx"
DEFAULT_OUTPUT_DIR = Path("assets") / "figures"
HALF_CYCLE_OUTPUT = DEFAULT_OUTPUT_DIR / "staircase_half_cycle_comparison.svg"
COLORS = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9", "#F0E442")


def _read_rows(
    workbook_path: Path,
    sheet_name: str,
) -> list[tuple[float, ...]]:
    """Read numeric data rows from a named worksheet."""
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Workbook does not contain the required sheet {sheet_name!r}.")
        rows: list[tuple[float, ...]] = []
        for row_number, row in enumerate(
            workbook[sheet_name].iter_rows(min_row=2, values_only=True),
            start=2,
        ):
            if all(value is None for value in row):
                continue
            try:
                rows.append(tuple(float(value) if value is not None else float("nan") for value in row))
            except (TypeError, ValueError):
                raise ValueError(f"Row {row_number} in {sheet_name!r} contains non-numeric data.") from None
        if not rows:
            raise ValueError(f"Worksheet {sheet_name!r} contains no numeric data.")
        return rows
    finally:
        workbook.close()


def _group_by_dose(rows: Iterable[tuple[float, ...]]) -> dict[float, list[tuple[float, ...]]]:
    grouped: defaultdict[float, list[tuple[float, ...]]] = defaultdict(list)
    for row in rows:
        grouped[row[0]].append(row)
    return dict(sorted(grouped.items()))


def _style_axis(axis: plt.Axes) -> None:
    axis.minorticks_off()
    axis.tick_params(
        axis="both",
        which="major",
        direction="in",
        top=True,
        right=True,
        length=4,
        width=0.8,
    )


def _style_staircase_axis(axis: plt.Axes, thicknesses: list[float]) -> None:
    """Use a 24-unit y-range with 6-unit major and 1-unit minor spacing."""
    lower = thicknesses[0] - 1
    axis.set_ylim(lower, lower + 24)
    axis.yaxis.set_major_locator(MultipleLocator(6))
    axis.yaxis.set_minor_locator(MultipleLocator(1))
    axis.xaxis.set_major_locator(MultipleLocator(5))
    axis.xaxis.set_minor_locator(MultipleLocator(0.5))
    axis.tick_params(
        axis="y",
        which="minor",
        direction="in",
        left=True,
        right=True,
        length=2.5,
        width=0.6,
        label1On=False,
        label2On=False,
    )
    axis.tick_params(
        axis="x",
        which="minor",
        direction="in",
        top=True,
        bottom=True,
        length=2.5,
        width=0.6,
        label1On=False,
        label2On=False,
    )


def build_figures(
    input_path: Path = DEFAULT_INPUT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> None:
    """Generate the combined half-cycle plot and one staircase plot per dose."""
    half_cycle = _group_by_dose(_read_rows(input_path, "half_cycle_comparison"))
    staircase = _group_by_dose(_read_rows(input_path, "staircase_growth"))
    if set(half_cycle) != set(staircase):
        raise ValueError("The two worksheets do not contain the same BAPMA dose times.")
    dose_colors = dict(zip(sorted(half_cycle), COLORS))

    plt.rcParams["font.family"] = "Times New Roman"
    plt.rcParams["font.size"] = 12
    output_dir.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(7, 3.25))
    try:
        for dose, rows in half_cycle.items():
            if dose == 0:
                continue
            color = dose_colors[dose]
            segments = (
                (rows[:20], rows[20:])
                if dose == 120 and len(rows) == 40
                else (rows,)
            )
            for segment_index, segment in enumerate(segments):
                tdic = [(row[1], row[2]) for row in segment if row[2] == row[2]]
                bapma = [(row[1], row[3]) for row in segment if row[3] == row[3]]
                axis.plot(
                    [point[0] for point in tdic],
                    [point[1] for point in tdic],
                    color=color,
                    marker="o",
                    markersize=3.5,
                    linewidth=0.8,
                    label=f"{dose:g} s" if segment_index == 0 else None,
                )
                axis.plot(
                    [point[0] for point in bapma],
                    [point[1] for point in bapma],
                    color=color,
                    marker="^",
                    markersize=3.5,
                    linewidth=0.8,
                    linestyle="--",
                )
        axis.set_xlabel("Cycle")
        axis.set_ylabel("Half-cycle thickness (Å)")
        axis.set_title("TDIC and BAPMA half-cycle growth")
        axis.set_xlim(30, 100)
        axis.legend(frameon=False, fontsize=8, title="BAPMA dose time")
        _style_axis(axis)
        figure.tight_layout()
        figure.savefig(HALF_CYCLE_OUTPUT, format="svg", metadata={"Date": None})
    finally:
        plt.close(figure)

    for dose, rows in staircase.items():
        color = dose_colors[dose]
        segments = (
            (rows[:20], rows[20:])
            if dose == 120 and len(rows) == 40
            else (rows,)
        )
        for segment_index, segment in enumerate(segments, start=1):
            figure, axis = plt.subplots(figsize=(3.25, 3.25))
            try:
                axis.plot(
                    [row[1] for row in segment],
                    [row[2] for row in segment],
                    color=color,
                    marker="o",
                    markersize=3.5,
                    linewidth=1.0,
                )
                axis.set_xlabel("Cycle")
                axis.set_ylabel("Overall thickness (Å)")
                title = f"Staircase growth: {dose:g} s BAPMA"
                axis.set_title(title)
                _style_axis(axis)
                _style_staircase_axis(axis, [row[2] for row in segment])
                axis.set_xlim(segment[0][1] - 0.5, segment[-1][1] + 0.5)
                figure.tight_layout()
                figure.canvas.draw()
                for tick in axis.yaxis.get_minor_ticks():
                    if tick.get_loc() % 6 == 3:
                        tick.tick1line.set_markersize(4)
                        tick.tick2line.set_markersize(4)
                for tick in axis.xaxis.get_minor_ticks():
                    location = tick.get_loc()
                    if abs(location - round(location)) < 1e-9 and int(round(location)) % 5 != 0:
                        tick.tick1line.set_markersize(3.2)
                        tick.tick2line.set_markersize(3.2)
                suffix = f"_{dose:g}s"
                if len(segments) > 1:
                    suffix += f"_part{segment_index}"
                output_path = output_dir / f"staircase_growth{suffix}.svg"
                figure.savefig(output_path, format="svg", metadata={"Date": None})
            finally:
                plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    build_figures(args.input, args.output_dir)


if __name__ == "__main__":
    main()
