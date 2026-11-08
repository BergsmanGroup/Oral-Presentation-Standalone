"""Generate the solvent-stability two-panel figure from an Excel workbook."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator
from openpyxl import load_workbook


DEFAULT_INPUT = Path("assets") / "other" / "solvent_stability.xlsx"
DEFAULT_OUTPUT = Path("assets") / "figures" / "solvent_stability.svg"
COLORS = ("#0072B2", "#E69F00", "#009E73")


def _read_rows(workbook_path: Path, sheet_name: str) -> list[tuple[float, ...]]:
    workbook = load_workbook(workbook_path, data_only=True, read_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Workbook does not contain the required sheet {sheet_name!r}.")
        rows: list[tuple[float, ...]] = []
        for row_number, row in enumerate(workbook[sheet_name].iter_rows(values_only=True), start=1):
            if not row or all(value is None for value in row):
                continue
            if row_number == 1:
                continue
            try:
                rows.append(tuple(float(value) for value in row if value is not None))
            except (TypeError, ValueError):
                raise ValueError(f"Row {row_number} in {sheet_name!r} contains non-numeric data.") from None
        if not rows:
            raise ValueError(f"Worksheet {sheet_name!r} contains no numeric data.")
        return rows
    finally:
        workbook.close()


def _style_axis(axis: plt.Axes) -> None:
    axis.set_ylim(-60, 30)
    axis.yaxis.set_major_locator(MultipleLocator(30))
    axis.yaxis.set_minor_locator(MultipleLocator(5))
    axis.set_yticks([-60, -30, 0, 30])
    axis.set_yticklabels(["-60%", "-30%", "0%", "30%"])
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


def build_figure(
    input_path: Path = DEFAULT_INPUT,
    output_path: Path = DEFAULT_OUTPUT,
) -> None:
    """Create the 3.25-inch-tall, side-by-side SVG figure."""
    solvent_rows = _read_rows(input_path, "20min_SolventStability")
    no_mei_rows = _read_rows(input_path, "100C_H2OStability_NoMeI")
    yes_mei_rows = _read_rows(input_path, "100C_H2OStability_YesMeI")

    plt.rcParams["font.family"] = "Times New Roman"
    plt.rcParams["font.size"] = 12
    figure, axes = plt.subplots(1, 2, figsize=(6.5, 3.25))
    try:
        left, right = axes

        solvent_names = ("H₂O", "EtOH", "ACN")
        temperatures = [int(row[0]) for row in solvent_rows]
        solvent_values_by_temperature = {
            temperature: {
                solvent: value * 100
                for solvent, value in zip(solvent_names, row[1:4])
            }
            for temperature, row in zip(temperatures, solvent_rows)
        }
        x_positions = np.arange(len(solvent_names))
        bar_width = 0.22
        for index, (temperature, color) in enumerate(zip(temperatures, COLORS)):
            left.bar(
                x_positions + (index - 1) * bar_width,
                [
                    solvent_values_by_temperature[temperature][solvent]
                    for solvent in solvent_names
                ],
                width=bar_width,
                color=color,
                label=str(temperature),
                linewidth=0,
            )
        left.axhline(0, color="black", linewidth=0.8)
        left.set_xticks(x_positions, solvent_names)
        left.set_xlabel("Solvent")
        left.set_ylabel("% Change in film thickness")
        left.set_title(
            "Solvent stability vs\ndeposition temperature",
            pad=8,
        )
        left.legend(
            title=None,
            frameon=False,
            fontsize=9,
            loc="lower right",
            bbox_to_anchor=(0.98, 0.02),
        )
        _style_axis(left)

        no_mei = np.asarray(no_mei_rows, dtype=float)
        yes_mei = np.asarray(yes_mei_rows, dtype=float)
        right.plot(
            no_mei[:, 0],
            no_mei[:, 2] * 100,
            color=COLORS[2],
            marker="o",
            markersize=4,
            linewidth=1.2,
            label="No MeI",
        )
        right.plot(
            yes_mei[:, 0],
            yes_mei[:, 2] * 100,
            color=COLORS[2],
            marker="^",
            markersize=4,
            linewidth=1.2,
            linestyle="--",
            label="Yes MeI",
        )
        right.set_xscale("log")
        right.set_xlim(0.8, 1200)
        right.set_xticks([1, 10, 100, 1000])
        right.set_xticklabels(["1", "10", "100", "1000"])
        right.set_xlabel("Length of H₂O exposure (s)")
        right.set_ylabel("% Change in film thickness")
        right.set_title("100°C deposition\nH₂O stability", pad=8)
        right.legend(
            frameon=False,
            fontsize=9,
            loc="lower right",
            bbox_to_anchor=(0.98, 0.02),
        )
        _style_axis(right)

        left.text(-0.20, 1.08, "a)", transform=left.transAxes, ha="right", va="top")
        right.text(-0.20, 1.08, "b)", transform=right.transAxes, ha="right", va="top")
        figure.subplots_adjust(left=0.1, right=0.98, bottom=0.17, top=0.86, wspace=0.5)
        figure.canvas.draw()
        for axis in axes:
            for tick in axis.yaxis.get_minor_ticks():
                if tick.get_loc() % 30 == 15:
                    tick.tick1line.set_markersize(4)
                    tick.tick2line.set_markersize(4)

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
