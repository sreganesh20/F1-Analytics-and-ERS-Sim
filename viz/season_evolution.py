"""
viz/season_evolution.py

Line chart: PU group average lap_time_gap_pct per race round.
Shows season performance trajectory per power unit.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from collections import defaultdict

from viz.base import (
    apply_style, save_and_show, load_race_fingerprints,
    PU_COLOURS, PU_ORDER, DARK_BG, TEXT_COL, ACCENT_COL, GRID_COL
)


def plot_season_evolution(show: bool = True, save: bool = True):
    apply_style()

    fps, all_rfs = load_race_fingerprints(sessions=["Q", "R"])
    if not fps:
        print("  No fingerprint data found.")
        return

    # ── Aggregate per PU per round ─────────────────────────
    # Structure: {pu: {round: [gap_pct values]}}
    data = defaultdict(lambda: defaultdict(list))

    for fp in fps:
        if fp.confidence < 0.5:
            continue
        data[fp.pu_name][fp.race_round].append(fp.lap_time_gap_pct)

    # Get sorted rounds
    all_rounds = sorted({fp.race_round for fp in fps})

    # Get circuit name per round for x-axis labels
    round_to_circuit = {}
    for rf in all_rfs:
        round_to_circuit[rf.race_round] = rf.circuit_name

    # ── Build figure ──────────────────────────────────────
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor(DARK_BG)

    for pu in PU_ORDER:
        if pu not in data:
            continue

        colour  = PU_COLOURS[pu]
        rounds  = sorted(data[pu].keys())

        # Best car per PU per round (min gap = fastest car using this PU).
        # Avoids customer team chassis dragging the PU line down.
        # e.g. Ferrari PU line reflects Ferrari factory car, not Cadillac.
        bests = [np.min(data[pu][r]) for r in rounds]
        worsts = [np.max(data[pu][r]) for r in rounds]

        # Line: best car per PU
        ax.plot(rounds, bests, color=colour, linewidth=2.0,
                marker="o", markersize=5, label=pu, zorder=3)

        # Shaded band: best-to-worst shows customer team spread
        ax.fill_between(rounds, bests, worsts,
                         color=colour, alpha=0.10, zorder=2)

        # Annotate final point with PU name
        ax.annotate(
            pu,
            xy=(rounds[-1], bests[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            color=colour,
            fontsize=8,
            va="center",
            fontweight="bold",
        )

    # ── X-axis labels ─────────────────────────────────────
    ax.set_xticks(all_rounds)
    ax.set_xticklabels([
        f"Rd{r}\n{round_to_circuit.get(r, '')[:3].upper()}"
        for r in all_rounds
    ], fontsize=8)

    # ── Invert Y — smaller gap = better = top of chart ────
    ax.invert_yaxis()
    ax.set_ylabel("Lap Time Gap to Session Leader (%)", color=TEXT_COL)
    ax.set_xlabel("Race Round", color=TEXT_COL)

    # ── Title + subtitle ──────────────────────────────────
    fig.text(0.5, 0.97, "2026 F1 — PU Performance Evolution",
             ha="center", va="top", fontsize=13,
             color=ACCENT_COL, fontweight="bold", fontfamily="monospace")
    fig.text(0.5, 0.92, "Best car per PU per round  |  Shaded = best-to-worst within PU group (customer team spread)",
             ha="center", va="top", fontsize=8, color=TEXT_COL, fontfamily="monospace")

    # ── Formatting ────────────────────────────────────────
    ax.set_xlim(min(all_rounds) - 0.3, max(all_rounds) + 1.2)
    ax.tick_params(colors=TEXT_COL)
    ax.spines[:].set_color(GRID_COL)

    # Reference line at 0 (pole/leader pace)
    ax.axhline(0, color=ACCENT_COL, linewidth=0.5, linestyle="--", alpha=0.4)
    ax.text(min(all_rounds) - 0.25, 0, "Leader", color=ACCENT_COL,
            fontsize=7, va="center", alpha=0.6)

    plt.tight_layout(rect=[0, 0, 1, 0.91])

    if save:
        save_and_show(fig, "season_evolution.png", show=show)
    elif show:
        plt.show()

    return fig


if __name__ == "__main__":
    plot_season_evolution()
