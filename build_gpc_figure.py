"""Generate stacked GPC growth-characterization plots from an Excel workbook."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from collections import defaultdict
from typing import Iterable

import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
from openpyxl import load_workbook


DEFAULT_INPUT = Path("assets") / "other" / "TDIC_BAPMA_GrowChar.xlsx"
DEFAULT_OUTPUT = Path("assets") / "figures" / "GPC_Growth_Characterization.svg"
PANEL_CONFIG = (
    ("TDIC_SatCurve", "TDIC Dose", "GPC vs TDIC Dose", (-10, 800), 180, 30, "a)"),
    ("BAPMA_SatCurve", "BAPMA Dose", "GPC vs BAPMA Dose", (-10, 560), 180, 30, "b)"),
    ("GPC_vs_Temp", "Chamber Temp (°C)", "GPC vs Temperature", (49, 101), 10, 5, "c)"),
)


def _numeric_rows(
    rows: Iterable[tuple[object, ...]],
) -> list[tuple[float, float, float]]:
    """Return temperature, average GPC, and standard-deviation values."""
    values: list[tuple[float, float, float]] = []
    for row_number, row in enumerate(rows, start=1):
        if len(row) < 3:
            continue
        try:
            temperature = float(row[0])
            average_gpc = float(row[1])
            stdev = float(row[2])
        except (TypeError, ValueError):
            if row_number == 1:
                continue
            raise ValueError(
                f"Row {row_number} must contain numeric temperature, average GPC, and stdev values."
            ) from None
        if stdev < 0:
            raise ValueError(f"Row {row_number} has a negative stdev value.")
        values.append((temperature, average_gpc, stdev))
    if not values:
        raise ValueError(
            "The workbook contains no numeric temperature/GPC/stdev rows in its first three columns."
        )
    return values


def read_data(
    workbook_path: Path,
    sheet_name: str,
) -> list[tuple[float, float, float]]:
    """Read independent, average GPC, and stdev values from one worksheet."""
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Workbook does not contain the required sheet {sheet_name!r}.")
        worksheet = workbook[sheet_name]
        return _numeric_rows(worksheet.iter_rows(values_only=True))
    finally:
        workbook.close()


def _combine_duplicate_x_values(
    values: list[tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    """Average duplicate y-values and combine their stdev values in quadrature."""
    grouped: defaultdict[float, list[tuple[float, float]]] = defaultdict(list)
    for independent, average_gpc, stdev in values:
        grouped[independent].append((average_gpc, stdev))

    combined = []
    for independent, measurements in grouped.items():
        average_gpc = sum(value for value, _ in measurements) / len(measurements)
        combined_stdev = math.sqrt(sum(stdev**2 for _, stdev in measurements))
        combined.append((independent, average_gpc, combined_stdev))
    return sorted(combined)


def build_figure(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
) -> None:
    """Create the requested 3.25-inch-wide stacked SVG figure."""
    plt.rcParams["font.family"] = "Times New Roman"
    plt.rcParams["font.size"] = 12
    figure, axes = plt.subplots(
        nrows=1,
        ncols=3,
        figsize=(9.75, 3.25),
        sharey=True,
    )
    try:
        for axis, (sheet_name, x_label, title, x_limits, x_major, x_minor, label) in zip(
            axes, PANEL_CONFIG
        ):
            values = _combine_duplicate_x_values(read_data(input_path, sheet_name))
            independent, average_gpc, stdev = zip(*values)
            axis.errorbar(
                independent,
                average_gpc,
                yerr=stdev,
                fmt="o-",
                color="black",
                ecolor="black",
                markerfacecolor="black",
                markeredgecolor="black",
                markersize=4,
                capsize=2,
                capthick=0.6,
                elinewidth=0.6,
            )
            axis.set_xlim(*x_limits)
            axis.set_ylim(0, 4.5)
            axis.xaxis.set_major_locator(MultipleLocator(x_major))
            axis.xaxis.set_minor_locator(MultipleLocator(x_minor))
            axis.yaxis.set_major_locator(MultipleLocator(1.0))
            axis.yaxis.set_minor_locator(MultipleLocator(0.5))
            axis.tick_params(
                axis="both",
                which="major",
                direction="in",
                top=True,
                right=True,
                length=4,
                width=0.8,
            )
            axis.tick_params(
                axis="both",
                which="minor",
                direction="in",
                top=True,
                right=True,
                length=2.5,
                width=0.6,
                label1On=False,
                label2On=False,
            )
            if x_major == 180:
                figure.canvas.draw()
                for tick in axis.xaxis.get_minor_ticks():
                    if tick.get_loc() % 90 == 0:
                        tick.tick1line.set_markersize(3.2)
                        tick.tick2line.set_markersize(3.2)
            axis.set_xlabel(x_label)
            axis.set_ylabel("GPC (Å/cycle)")
            axis.set_title(title)
            axis.text(
                -0.18,
                1.08,
                label,
                transform=axis.transAxes,
                va="top",
                ha="right",
            )
        figure.subplots_adjust(left=0.08, right=0.98, bottom=0.17, top=0.86, wspace=0.45)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(output_path, format="svg", metadata={"Date": None})
    finally:
        plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build_figure(args.input, args.output)


if __name__ == "__main__":
    main()
