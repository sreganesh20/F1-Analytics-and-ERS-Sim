"""
viz/fingerprint_radar.py

Radar/spider chart: ERS fingerprint per PU group.
Axes: lap_time_gap_pct, braking_harvest_ratio,
      straight_speed_delta, braking_speed_delta.
One polygon per PU, averaged across all drivers and race sessions.
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


# Axes definition: (field_name, display_label, invert, scale_factor)
# invert=True means higher raw value = worse = should plot smaller
AXES = [
    ("lap_time_gap_pct",       "Pace\n(gap%)",        True,  1.0),
    ("braking_harvest_ratio",  "Harvest\nRatio",       False, 1.0),
    ("straight_speed_delta",   "Straight\nSpeed Δ",   False, 0.1),   # kph → scaled
    ("braking_speed_delta",    "Braking\nSpeed Δ",    False, 0.1),
]

N_AXES = len(AXES)


def _normalise(values: np.ndarray) -> np.ndarray:
    """Normalise to [0.1, 1.0] range across all PUs for radar display."""
    vmin, vmax = values.min(), values.max()
    if vmax - vmin < 1e-6:
        return np.full_like(values, 0.5)
    return 0.1 + 0.9 * (values - vmin) / (vmax - vmin)


def plot_fingerprint_radar(show: bool = True, save: bool = True):
    apply_style()

    fps, _ = load_race_fingerprints(sessions=["R"])
    if not fps:
        print("  No race fingerprint data found.")
        return

    # Works/factory team per PU — excludes customer chassis noise.
    # Ferrari PU radar reflects Ferrari factory car, not Haas or Cadillac.
    FACTORY_TEAMS = {
        "Mercedes":    ["Mercedes"],
        "Ferrari":     ["Ferrari"],
        "RedBullFord": ["Red Bull"],
        "Honda":       ["Aston Martin"],   # sole team
        "Audi":        ["Audi"],           # sole team
    }

    # ── Aggregate per PU — factory cars only ─────────────
    pu_data = defaultdict(lambda: defaultdict(list))

    for fp in fps:
        if fp.confidence < 0.5:
            continue
        allowed_teams = FACTORY_TEAMS.get(fp.pu_name, [])
        if fp.team not in allowed_teams:
            continue   # skip customer teams
        pu_data[fp.pu_name]["lap_time_gap_pct"].append(fp.lap_time_gap_pct)
        pu_data[fp.pu_name]["braking_harvest_ratio"].append(fp.braking_harvest_ratio)
        pu_data[fp.pu_name]["straight_speed_delta"].append(fp.straight_speed_delta_kph)
        pu_data[fp.pu_name]["braking_speed_delta"].append(fp.braking_speed_delta_kph)

    present_pus = [pu for pu in PU_ORDER if pu in pu_data]
    if not present_pus:
        print("  No PU data available.")
        return

    # ── Compute raw values per PU per axis ────────────────
    # Pace: use min (best lap — most competitive result)
    # ERS signals: use mean (average behaviour across races)
    raw = np.zeros((len(present_pus), N_AXES))
    for i, pu in enumerate(present_pus):
        for j, (field, _, invert, scale) in enumerate(AXES):
            vals = pu_data[pu][field]
            if not vals:
                raw[i, j] = 0.0
                continue
            if field == "lap_time_gap_pct":
                raw[i, j] = float(np.min(vals)) * scale   # best car
            else:
                raw[i, j] = float(np.mean(vals)) * scale  # avg ERS behaviour

    # ── Normalise column-wise for display ─────────────────
    # For inverted axes (gap%), lower is better so we invert before normalising
    display = raw.copy()
    for j, (_, _, invert, _) in enumerate(AXES):
        col = display[:, j]
        if invert:
            col = -col   # flip: lower gap = higher display value
        display[:, j] = _normalise(col)

    # ── Build radar ───────────────────────────────────────
    angles = np.linspace(0, 2 * np.pi, N_AXES, endpoint=False).tolist()
    angles += angles[:1]   # close the polygon

    fig, ax = plt.subplots(figsize=(8, 8),
                           subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_BG)

    # Grid rings
    for r in [0.2, 0.4, 0.6, 0.8, 1.0]:
        ax.plot(np.linspace(0, 2 * np.pi, 100), [r] * 100,
                color=GRID_COL, linewidth=0.5, zorder=1)

    # Spoke lines
    for angle in angles[:-1]:
        ax.plot([angle, angle], [0, 1],
                color=GRID_COL, linewidth=0.5, zorder=1)

    # Plot each PU
    for i, pu in enumerate(present_pus):
        colour  = PU_COLOURS[pu]
        vals    = display[i].tolist()
        vals   += vals[:1]

        ax.plot(angles, vals, color=colour, linewidth=2.0,
                marker="o", markersize=5, zorder=3, label=pu)
        ax.fill(angles, vals, color=colour, alpha=0.10, zorder=2)

    # Axis labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(
        [label for _, label, _, _ in AXES],
        fontsize=9, color=TEXT_COL, fontfamily="monospace"
    )
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"],
                        fontsize=6, color=TEXT_COL)
    ax.set_ylim(0, 1)
    ax.tick_params(colors=TEXT_COL)

    # Raw value annotations around outer ring
    for i, pu in enumerate(present_pus):
        for j, (field, _, invert, scale) in enumerate(AXES):
            angle  = angles[j]
            radius = display[i, j] + 0.07
            raw_v  = raw[i, j] / scale   # back to original units
            label  = f"{raw_v:+.2f}" if "delta" in field else f"{raw_v:.3f}"
            ax.text(angle, radius, label,
                    ha="center", va="center",
                    fontsize=6, color=PU_COLOURS[pu], alpha=0.75)

    # Legend
    legend_patches = [
        mpatches.Patch(facecolor=PU_COLOURS[pu], alpha=0.7, label=pu)
        for pu in present_pus
    ]
    ax.legend(handles=legend_patches,
              loc="upper right", bbox_to_anchor=(1.35, 1.15),
              fontsize=9, framealpha=0.3)

    # Disclaimer
    ax.text(0, -0.18,
            "Normalised display — higher = better on all axes\n"
            "Raw values annotated. Based on race sessions only.",
            transform=ax.transAxes,
            ha="left", va="top", fontsize=7, color=TEXT_COL, alpha=0.6,
            fontfamily="monospace")

    fig.text(0.5, 0.97, "2026 F1 — ERS Power Unit Fingerprint",
             ha="center", va="top", fontsize=13,
             color=ACCENT_COL, fontweight="bold", fontfamily="monospace")
    fig.text(0.5, 0.93,
             "Factory/works team only  |  Pace = best lap, ERS = mean  |  Axes normalised",
             ha="center", va="top", fontsize=7.5,
             color=TEXT_COL, fontfamily="monospace")

    plt.tight_layout(rect=[0, 0, 1, 0.91])

    if save:
        save_and_show(fig, "fingerprint_radar.png", show=show)
    elif show:
        plt.show()

    return fig


if __name__ == "__main__":
    plot_fingerprint_radar()
