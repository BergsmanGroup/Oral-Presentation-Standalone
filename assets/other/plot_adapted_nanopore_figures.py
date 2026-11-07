import csv
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


# ============================================================
# Configuration
# ============================================================

HERE = Path(__file__).resolve().parent
INPUT_CSV = HERE / "combined_ICR_hafnia_data.csv"
OUTPUT_DIR = HERE.parent / "figures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CB = {
    "black":          "#000000",
    "orange":         "#E69F00",
    "sky_blue":       "#56B4E9",
    "bluish_green":   "#009E73",
    "yellow":         "#F0E442",
    "blue":           "#0072B2",
    "vermillion":     "#D55E00",
    "reddish_purple": "#CC79A7",
    "grey":           "#4D4D4D",
}

plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "axes.linewidth": 1.2,
    "svg.fonttype": "none",
})


# ============================================================
# Helpers
# ============================================================

def style_axes(ax):
    """Simple publication/presentation style with no grid."""
    ax.grid(False)
    ax.tick_params(
        axis="both",
        which="both",
        direction="in",
        top=True,
        right=True,
        width=1.1,
    )
    for spine in ax.spines.values():
        spine.set_linewidth(1.2)


def save_figure(fig, filename):
    path = OUTPUT_DIR / filename
    fig.savefig(path, format="svg", bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    print(f"Saved: {path}")


def linear_regression_line(x, y, n=200):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m, b = np.polyfit(x, y, 1)
    xfit = np.linspace(x.min(), x.max(), n)
    yfit = m * xfit + b
    return xfit, yfit, m, b


# ============================================================
# 1. Literature I-V: ka = 3 only
#    Approximate values visually digitized from supplied figure.
# ============================================================

lit_iv_v = np.array([
    -10, -9, -8, -7, -6, -5, -4, -3, -2, -1,
      0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10
], dtype=float)

lit_iv_i = np.array([
    -4.6, -4.2, -3.9, -3.6, -3.3, -3.0, -2.7, -2.4, -2.1, -1.7,
    -1.2, -0.5,  0.2,  1.0,  1.8,  2.8,  3.9,  5.1,  6.5,  8.1, 10.0
], dtype=float)

fig, ax = plt.subplots(figsize=(3.25, 3.0), dpi=300)
ax.plot(
    lit_iv_v,
    lit_iv_i,
    color=CB["black"],
    marker="o",
    markersize=4,
    linewidth=1.2,
)
ax.set_xlabel("Voltage (V)")
ax.set_ylabel("Current (nA)")
ax.set_xlim(-15, 15)
ax.set_ylim(-10, 15)
style_axes(ax)
save_figure(fig, "01_literature_IV_ka3.svg")


# ============================================================
# 2A. Conductance vs pH A
#     Top panel only from supplied two-panel figure.
#     Black circular markers only.
# ============================================================

ph_a = np.array([2.75, 3.20, 4.35, 5.65, 6.90, 8.40])
g_a = np.array([11.1, 10.35, 9.45, 17.8, 22.0,24.0])
g_a_err = np.array([0.25, 0.30, 1.65, 0.25, 0.35, 0.65])

fig, ax = plt.subplots(figsize=(3.25, 3.0), dpi=300)
ax.plot(ph_a, g_a, color=CB["black"], linewidth=1.2, zorder=1)
ax.errorbar(
    ph_a,
    g_a,
    fmt="o",
    color=CB["black"],
    ecolor=CB["black"],
    markersize=4,
    elinewidth=1.0,
    capsize=3,
    linestyle="none",
)
ax.set_xlabel("pH")
ax.set_ylabel("Conductance (nS)")
ax.set_xlim(1, 11)
ax.set_ylim(8, 25)
ax.set_xticks([1, 3, 5, 7, 9, 11])
style_axes(ax)
save_figure(fig, "02_conductance_vs_pH_A.svg")


# ============================================================
# 2B. Conductance vs pH B
#     Single-frame figure, stripped of background/insets/fit.
#     Black circular markers only.
# ============================================================

ph_b = np.array([1.1, 2.0, 3.0, 3.6, 4.2, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0])
g_b = np.array([4.85, 2.10, 1.65, 1.55, 1.2, 1.50, 1.85, 2.80, 3.20, 3.70, 4.20, 4.65, 4.95])
g_b_err = np.array([0.15, 0.80, 0.45, 0.10, 0.35, 0.15, 0.12, 0.25, 0.40, 0.65, 0.35, 0.25, 0.12])

fig, ax = plt.subplots(figsize=(3.25, 3.0), dpi=300)
ax.plot(ph_b, g_b, color=CB["black"], linewidth=1.2, zorder=1)
ax.errorbar(
    ph_b,
    g_b,
    fmt="o",
    color=CB["black"],
    ecolor=CB["black"],
    markersize=4,
    elinewidth=1.0,
    capsize=3,
    linestyle="none",
)
ax.set_xlabel("pH")
ax.set_ylabel("Conductance (nS)")
ax.set_xlim(1, 11)
# Same conductance scale as plot A, as requested.
ax.set_ylim(0, 7)
ax.set_xticks([1, 3, 5, 7, 9, 11])
style_axes(ax)
save_figure(fig, "03_conductance_vs_pH_B.svg")


# ============================================================
# 3A. Current vs pressure
#     Approximate points visually digitized from supplied figure.
#     Colored circles + independent linear regression for each pH.
# ============================================================

pressure_sets = {
    "pH 3": {
        "x": np.array([0.00, 0.06, 0.11, 0.16, 0.21, 0.26, 0.31]),
        "y": np.array([0.00, 0.30, 0.43, 0.66, 0.84, 1.05, 1.15]),
        "color": CB["sky_blue"],
    },
    "pH 4.6": {
        "x": np.array([0.00, 0.06, 0.11, 0.16, 0.20, 0.26, 0.31]),
        "y": np.array([0.00, -0.35, -0.72, -1.05, -1.42, -1.70, -2.05]),
        "color": CB["vermillion"],
    },
    "pH 8": {
        "x": np.array([0.00, 0.06, 0.11, 0.16, 0.20, 0.26, 0.31]),
        "y": np.array([0.00, -0.55, -1.05, -1.55, -2.15, -2.75, -3.55]),
        "color": CB["bluish_green"],
    },
    "pH 12": {
        "x": np.array([0.00, 0.06, 0.10, 0.16, 0.20, 0.26, 0.31]),
        "y": np.array([0.00, -1.55, -1.85, -3.95, -4.85, -7.25, -8.15]),
        "color": CB["orange"],
    },
}

fig, ax = plt.subplots(figsize=(3.6, 3.0), dpi=300)

for label, d in pressure_sets.items():
    ax.scatter(
        d["x"],
        d["y"],
        s=22,
        marker="o",
        color=d["color"],
        label=label,
        zorder=3,
    )

    xfit, yfit, _, _ = linear_regression_line(d["x"], d["y"])
    ax.plot(xfit, yfit, color=d["color"], linewidth=1.2)

ax.set_xlabel("Pressure (MPa)")
ax.set_ylabel("Current (pA)")
ax.set_xlim(0, 0.32)
ax.set_ylim(-10, 2)
ax.legend(frameon=False, fontsize=9)
style_axes(ax)
save_figure(fig, "04_current_vs_pressure.svg")


# ============================================================
# 3B. Zeta potential vs pH
#
# Re-checked against supplied image.
# Multiple points at each repeated pH are averaged before plotting.
# A quadratic fit is applied to the pH-level means.
# ============================================================

zeta_raw = {
    3.0:  [2.0],
    4.5:  [-1.7, -0.8],
    8.0:  [-5.4, -6.5, -7.0, -8.5],
    12.0: [-17.0, -20.5, -22.5],
}

zeta_ph = np.array(sorted(zeta_raw.keys()), dtype=float)
zeta_mean = np.array([np.mean(zeta_raw[p]) for p in zeta_ph], dtype=float)

# Smooth black quadratic fit through the averaged pH-level values.
coef = np.polyfit(zeta_ph, zeta_mean, 2)
xfit = np.linspace(1.0, 13.0, 300)
yfit = np.polyval(coef, xfit)

fig, ax = plt.subplots(figsize=(3.25, 3.0), dpi=300)
ax.scatter(
    zeta_ph,
    zeta_mean,
    s=24,
    marker="o",
    color=CB["black"],
    zorder=3,
)
ax.plot(
    xfit,
    yfit,
    color=CB["black"],
    linewidth=1.6,
)
ax.set_xlabel("pH")
ax.set_ylabel("Zeta potential (mV)")
ax.set_xlim(1, 13)
ax.set_ylim(-25, 5)
ax.axhline(0, color="black", linewidth=1.2)
style_axes(ax)
save_figure(fig, "05_zeta_potential_vs_pH.svg")


# ============================================================
# 4. Hafnia I-V
#
# Read the supplied CSV:
#   X     = voltage
#   Y4p5  = pH 4.5 current
#   Y7p0  = pH 7.0 current
#   Y9p5  = pH 9.5 current
#
# Requested normalization:
#   each retained current curve / max(abs(current))
#
# Y7p0 is intentionally DROPPED.
#
# Colored circular markers + straight lines connecting adjacent data points.
# ============================================================

if not INPUT_CSV.exists():
    raise FileNotFoundError(
        f"Could not find {INPUT_CSV.name} next to this script.\n"
        f"Place the CSV in:\n{HERE}"
    )

required_columns = {"X", "Y4p5", "Y7p0", "Y9p5"}
with INPUT_CSV.open(newline="", encoding="utf-8-sig") as csv_file:
    reader = csv.DictReader(csv_file)
    columns = set(reader.fieldnames or [])
    missing = required_columns - columns
    if missing:
        raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
    hafnia_rows = list(reader)

if not hafnia_rows:
    raise ValueError(f"CSV contains no data rows: {INPUT_CSV}")

voltage = np.array([float(row["X"]) for row in hafnia_rows], dtype=float)
current_by_column = {
    column: np.array([float(row[column]) for row in hafnia_rows], dtype=float)
    for column in required_columns - {"X"}
}

hafnia_series = {
    "pH 7.0": {
        "column": "Y7p0",
        "color": CB["blue"],
    },
    "pH 9.5": {
        "column": "Y9p5",
        "color": CB["vermillion"],
    },
}

fig, ax = plt.subplots(figsize=(3.6, 3.0), dpi=300)

for label, info in hafnia_series.items():
    current = current_by_column[info["column"]]

    # Normalization option 3: normalize to maximum absolute current.
    current_norm = current / np.max(np.abs(current))

    ax.scatter(
        voltage,
        current_norm,
        s=22,
        marker="o",
        color=info["color"],
        label=label,
        zorder=3,
    )

    ax.plot(
        voltage,
        current_norm,
        color=info["color"],
        linewidth=1.4,
    )

ax.axhline(0, color=CB["grey"], linewidth=0.7)
ax.axvline(0, color=CB["grey"], linewidth=0.7)
ax.set_xlabel("Voltage (mV)")
ax.set_ylabel(r"Normalized current, $I/\max(|I|)$")
ax.legend(frameon=False)
style_axes(ax)
save_figure(fig, "06_hafnia_IV_normalized_maxI_no_pH7.svg")


print("\nAll figures created successfully.")
print(f"Output directory: {OUTPUT_DIR}")
