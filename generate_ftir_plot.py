"""Generate the annotated FTIR figure from the editable JSON configuration."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = (
    ROOT
    / "assets"
    / "figures"
    / "SID180c_TDICBAPMA_65nm_NoMeI_BaselineCorrected_FTIR_config.json"
)


def load_spectrum(data_path: Path, column: str) -> tuple[np.ndarray, np.ndarray]:
    with data_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    if not rows or "Wavenumbers [1/cm]" not in rows[0] or column not in rows[0]:
        raise ValueError(f"{data_path} is missing the expected FTIR data columns.")
    wavenumber = np.array([float(row["Wavenumbers [1/cm]"]) for row in rows])
    absorbance = np.array([float(row[column]) for row in rows])
    return wavenumber, absorbance


def local_peak(
    wavenumber: np.ndarray,
    absorbance: np.ndarray,
    target: float,
    window: float,
) -> tuple[float, float]:
    region = np.abs(wavenumber - target) <= window
    if not np.any(region):
        raise ValueError(f"No data points found near the configured {target:g} cm^-1 peak.")
    indices = np.flatnonzero(region)
    peak_index = indices[np.argmax(absorbance[region])]
    return float(wavenumber[peak_index]), float(absorbance[peak_index])


def render(config_path: Path) -> tuple[Path, Path]:
    config: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    data_path = (config_path.parent.parent.parent / config["data_file"]).resolve()
    wavenumber, absorbance = load_spectrum(data_path, config["data_column"])

    gap_min, gap_max = config["omitted_range_cm-1"]
    plotted_absorbance = absorbance.copy()
    plotted_absorbance[(wavenumber >= gap_min) & (wavenumber <= gap_max)] = np.nan

    peaks = config["peaks"]
    resolved_peaks = [
        (peak, *local_peak(wavenumber, absorbance, peak["wavenumber_cm-1"], config["peak_search_window_cm-1"]))
        for peak in peaks
    ]

    plt.rcParams.update(
        {
            "font.family": config["font_family"],
            "font.size": config["font_size"],
            "axes.titlesize": config["title_font_size"],
            "axes.labelsize": config["axis_label_font_size"],
            "xtick.labelsize": config["tick_font_size"],
        }
    )
    fig, ax = plt.subplots(figsize=config["figure_size_inches"], facecolor="white")
    ax.set_facecolor("white")
    ax.plot(
        wavenumber,
        plotted_absorbance,
        color="black",
        linewidth=config["trace_line_width"],
        zorder=2,
    )
    ax.scatter(
        [x for _, x, _ in resolved_peaks],
        [y for _, _, y in resolved_peaks],
        s=config["peak_marker_size"],
        color="black",
        zorder=3,
    )
    ax.set_xlim(*config["x_limits_cm-1"])
    ax.set_ylim(
        min(config["y_limits"][0], float(absorbance.min()) - 0.002),
        config["y_limits"][1],
    )
    ax.set_xlabel(config["x_axis_label"], labelpad=11)
    ax.set_ylabel(config["y_axis_label"], labelpad=12)
    ax.tick_params(axis="y", left=True, labelleft=False, length=0)
    ax.tick_params(axis="x", direction="out", length=5, width=1.1)
    ax.grid(True, color="#b8b8b8", linewidth=0.8, alpha=0.38)
    for spine in ax.spines.values():
        spine.set_color("#222222")
        spine.set_linewidth(1.1)
    ax.set_title(config["title"], pad=16)

    fig.tight_layout()
    number_targets: dict[str, tuple[float, float]] = {}
    for peak, x, y in resolved_peaks:
        number_y = y + config["peak_number_offset"]
        number_x = x + peak.get("number_wavenumber_offset_cm-1", 0)
        number_targets[peak["label"]] = (number_x, number_y)
        ax.plot(
            [x, number_x],
            [y + config["leader_start_offset"], number_y - config["leader_end_offset"]],
            color="#555555",
            linewidth=0.7,
            linestyle="--",
            zorder=3,
        )
        ax.text(
            number_x,
            number_y,
            peak["label"],
            ha="center",
            va="bottom",
            rotation=90,
            rotation_mode="anchor",
            fontsize=config["peak_number_font_size"],
            color="#111111",
            clip_on=False,
            zorder=4,
        )

    for peak in peaks:
        target_x, target_y = number_targets[peak["label"]]
        label_x, label_y = peak["assignment_position_axes"]
        ax.annotate(
            peak["assignment"],
            xy=(target_x, target_y),
            xycoords="data",
            xytext=(label_x, label_y),
            textcoords="axes fraction",
            ha="center",
            va="center",
            fontsize=config["assignment_font_size"],
            color="#111111",
            bbox={
                "boxstyle": "round,pad=0.22",
                "facecolor": "white",
                "edgecolor": "#777777",
                "linewidth": 0.65,
                "alpha": 0.97,
            },
            arrowprops={
                "arrowstyle": "->",
                "color": "#555555",
                "linewidth": 0.8,
                "shrinkA": 2,
                "shrinkB": 2,
                "connectionstyle": "angle,angleA=-90,angleB=0",
            },
            annotation_clip=False,
            zorder=5,
        )

    output_stem = config_path.parent / config["output_stem"]
    png_path = output_stem.with_suffix(".png")
    svg_path = output_stem.with_suffix(".svg")
    fig.savefig(png_path, dpi=config["png_dpi"], bbox_inches="tight", facecolor="white")
    fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return png_path, svg_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the FTIR plot JSON configuration.",
    )
    args = parser.parse_args()
    png_path, svg_path = render(args.config.resolve())
    print(f"Saved {png_path}")
    print(f"Saved {svg_path}")


if __name__ == "__main__":
    main()
