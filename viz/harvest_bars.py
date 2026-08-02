"""
viz/harvest_bars.py

Horizontal bar chart: braking_harvest_ratio per driver,
averaged across all race sessions. Coloured by PU.
Reference line at 1.0 = achieving theoretical maximum.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict

from viz.base import (
    apply_style, save_and_show, load_race_fingerprints,
    PU_COLOURS, PU_ORDER, DARK_BG, TEXT_COL, ACCENT_COL, GRID_COL
)


def plot_harvest_bars(show: bool = True, save: bool = True):
    apply_style()

    fps, _ = load_race_fingerprints(sessions=["R"])
    if not fps:
        print("  No race fingerprint data found.")
        return

    # ── Aggregate harvest ratio per driver ────────────────
    driver_data = defaultdict(lambda: {"ratios": [], "pu": "", "team": ""})

    for fp in fps:
        if fp.confidence < 0.5:
            continue
        driver_data[fp.driver_code]["ratios"].append(fp.braking_harvest_ratio)
        driver_data[fp.driver_code]["pu"]   = fp.pu_name
        driver_data[fp.driver_code]["team"] = fp.team

    if not driver_data:
        print("  No valid data.")
        return

    # Compute means
    drivers  = []
    means    = []
    stds     = []
    colours  = []
    pus      = []

    # Sort by PU group first, then by mean ratio descending within group
    sorted_drivers = sorted(
        driver_data.items(),
        key=lambda x: (PU_ORDER.index(x[1]["pu"]) if x[1]["pu"] in PU_ORDER else 99,
                       -np.mean(x[1]["ratios"]))
    )

    for drv, info in sorted_drivers:
        ratios = info["ratios"]
        drivers.append(drv)
        means.append(float(np.mean(ratios)))
        stds.append(float(np.std(ratios)) if len(ratios) > 1 else 0.0)
        colours.append(PU_COLOURS.get(info["pu"], "#888888"))
        pus.append(info["pu"])

    # ── Build figure ──────────────────────────────────────
    n   = len(drivers)
    fig, ax = plt.subplots(figsize=(10, max(6, n * 0.35)))
    fig.patch.set_facecolor(DARK_BG)

    y_pos = np.arange(n)

    bars = ax.barh(y_pos, means, xerr=stds,
                   color=colours, alpha=0.85,
                   error_kw={"ecolor": ACCENT_COL, "capsize": 3,
                             "elinewidth": 0.8, "capthick": 0.8},
                   height=0.65, zorder=3)

    # Value labels on bars
    for i, (mean, std) in enumerate(zip(means, stds)):
        ax.text(mean + 0.005, i, f"{mean:.2f}",
                va="center", ha="left", fontsize=7.5,
                color=TEXT_COL)

    # Reference line at 1.0
    ax.axvline(1.0, color=ACCENT_COL, linewidth=1.0,
               linestyle="--", alpha=0.7, zorder=4)
    ax.text(1.002, n - 0.5, "Theoretical\nMaximum",
            color=ACCENT_COL, fontsize=7, va="top", alpha=0.7)

    # PU group separators
    current_pu  = None
    group_start = 0
    for i, pu in enumerate(pus):
        if pu != current_pu:
            if current_pu is not None:
                ax.axhline(i - 0.5, color=GRID_COL, linewidth=0.8,
                           linestyle="-", alpha=0.6)
            current_pu  = pu
            group_start = i

    # Y axis
    ax.set_yticks(y_pos)
    ax.set_yticklabels(drivers, fontsize=8.5, fontfamily="monospace")
    ax.invert_yaxis()

    # PU colour legend
    legend_patches = [
        plt.Rectangle((0, 0), 1, 1,
                       facecolor=PU_COLOURS[pu], alpha=0.85, label=pu)
        for pu in PU_ORDER if pu in set(pus)
    ]
    ax.legend(handles=legend_patches, loc="lower right",
              fontsize=8, framealpha=0.3)

    ax.set_xlabel("Braking Harvest Ratio  (observed KE / theoretical maximum)", color=TEXT_COL)
    ax.set_xlim(0.5, max(means) + 0.12)
    ax.tick_params(colors=TEXT_COL)
    ax.spines[:].set_color(GRID_COL)

    fig.text(0.5, 0.97, "2026 F1 — ERS Braking Harvest Efficiency",
             ha="center", va="top", fontsize=13,
             color=ACCENT_COL, fontweight="bold", fontfamily="monospace")
    fig.text(0.5, 0.93, "Average across all race sessions  |  Error bars = circuit-to-circuit variation  |  >1.0 = above reference car",
             ha="center", va="top", fontsize=7.5, color=TEXT_COL, fontfamily="monospace")

    plt.tight_layout(rect=[0, 0, 1, 0.92])

    if save:
        save_and_show(fig, "harvest_bars.png", show=show)
    elif show:
        plt.show()

    return fig


if __name__ == "__main__":
    plot_harvest_bars()
