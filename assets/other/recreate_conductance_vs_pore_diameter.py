import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams["font.family"] = "Arial"
plt.rcParams["font.size"] = 11
plt.rcParams["axes.labelsize"] = 12
plt.rcParams["xtick.labelsize"] = 11
plt.rcParams["ytick.labelsize"] = 11
plt.rcParams["svg.fonttype"] = "none"

# Approximate reconstruction of the supplied figure.
# Black-square data were visually digitized from the image.

sigma = 120.0

def G_access(d_nm, l_nm, sigma_scale=sigma):
    d_m = d_nm * 1e-9
    l_m = l_nm * 1e-9
    resistance_term = (4 * l_m / (np.pi * d_m**2)) + (1 / d_m)
    scale = 1.0e-11 * sigma_scale
    return scale / resistance_term * 1e9

def G_cyl(d_nm, l_nm=8.6, sigma_scale=sigma):
    d_m = d_nm * 1e-9
    l_m = l_nm * 1e-9
    scale = 1.0e-11 * sigma_scale
    return scale * (np.pi * d_m**2 / (4 * l_m)) * 1e9

d = np.linspace(4, 101, 500)

x_data = np.array([
    6, 8, 10, 13, 16, 20, 22, 25, 30, 33, 36, 38, 40, 42,
    45, 48, 52, 57, 60, 61, 65, 70, 75, 78, 81, 86, 96, 100
], dtype=float)

y_data = np.array([
    8, 18, 28, 45, 92, 142, 149, 185, 260, 230, 305, 325, 345, 360,
    405, 355, 445, 385, 455, 490, 550, 595, 675, 650, 720, 760, 815, 860
], dtype=float)

fig, ax = plt.subplots(figsize=(4.35, 4.05), dpi=330)

ax.plot(d, G_access(d, 0.0), color="red", lw=1.6)
ax.plot(d, G_access(d, 8.6), color="blue", lw=1.6)
ax.plot(d, G_access(d, 20.0), color="#00DD22", lw=1.6)

d_gray = np.linspace(4, 55, 300)
ax.plot(d_gray, G_cyl(d_gray), color="0.35", lw=1.7)

ax.scatter(
    x_data, y_data,
    marker="s",
    s=15,
    facecolor="black",
    edgecolor="black",
    linewidth=0.3,
    zorder=5
)

ax.set_xlim(0, 105)
ax.set_ylim(0, 1000)
ax.set_xticks(np.arange(0, 101, 20))
ax.set_yticks(np.arange(0, 1001, 200))

ax.set_xlabel("Pore diameter d (nm)")
ax.set_ylabel("Conductance G (nS)")

ax.tick_params(axis="both", which="major", direction="in",
               top=True, right=True, length=6, width=1.2)
ax.tick_params(axis="both", which="minor", direction="in",
               top=True, right=True, length=3, width=1.0)
ax.minorticks_on()

for spine in ax.spines.values():
    spine.set_linewidth(1.2)

ax.text(
    16, 835,
    r"$G=\sigma\,\dfrac{\pi d^2}{4l}$",
    fontsize=13,
    color="0.35"
)

ax.text(
    54, 260,
    r"$G=\sigma\left[\dfrac{4l}{\pi d^2}+\dfrac{1}{d}\right]^{-1}$",
    fontsize=13,
    color="blue"
)

ax.text(72, 760, "l=0nm", color="red", fontsize=12, rotation=48)
ax.text(78, 700, "l=8.6nm", color="blue", fontsize=12, rotation=48)
ax.text(83, 610, "l=20nm", color="#00DD22", fontsize=12, rotation=48)

fig.tight_layout(pad=0.6)

svg_path = Path(__file__).resolve().parents[1] / "figures" / "conductance_vs_pore_diameter.svg"

fig.savefig(svg_path, format="svg", bbox_inches="tight")

plt.show()
