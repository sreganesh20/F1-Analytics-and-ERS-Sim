"""
viz/prediction_scatter.py

Scatter plot: predicted gap vs actual gap per driver per race.
Diagonal = perfect prediction. Error bars = predicted range.
Populated post-race via compare data.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

from viz.base import (
    apply_style, save_and_show,
    PU_COLOURS, PU_ORDER, DARK_BG, TEXT_COL, ACCENT_COL, GRID_COL
)


def _load_comparison_data() -> list[dict]:
    """
    Load all saved prediction vs actual comparisons.
    Returns list of {driver, pu, circuit, predicted, actual, low, high}
    """
    import json
    from analysis.prediction_store import PRED_DIR

    results = []
    if not os.path.exists(PRED_DIR):
        return results

    for fname in os.listdir(PRED_DIR):
        if not fname.endswith("_prediction.json"):
            continue

        pred_path = os.path.join(PRED_DIR, fname)
        circuit   = fname.replace("2026_", "").replace("_prediction.json", "").replace("_", " ")

        with open(pred_path) as f:
            pred_data = json.load(f)

        # Look for matching actual results file
        actual_path = pred_path.replace("_prediction.json", "_actual.json")
        if not os.path.exists(actual_path):
            continue

        with open(actual_path) as f:
            actual_data = json.load(f)

        actual_by_driver = {r["driver"]: r for r in actual_data}

        for p in pred_data["predictions"]:
            drv     = p["driver_code"]
            act_row = actual_by_driver.get(drv)
            if act_row is None:
                continue
            act_gap = act_row.get("gap_s")
            if act_gap is None:
                continue

            results.append({
                "driver":    drv,
                "pu":        p["pu_name"],
                "circuit":   circuit,
                "predicted": p["predicted_delta_s"],
                "actual":    float(act_gap),
                "low":       p["delta_range_low"],
                "high":      p["delta_range_high"],
            })

    return results


def plot_prediction_scatter(show: bool = True, save: bool = True):
    apply_style()

    data = _load_comparison_data()

    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_facecolor(DARK_BG)

    if not data:
        # No comparison data yet — show placeholder
        ax.text(0.5, 0.5,
                "No comparison data yet.\n\nRun after a race:\n"
                "  python run.py race <circuit>\n"
                "  python run.py compare <circuit>",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color=TEXT_COL, fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.8", facecolor=DARK_BG,
                          edgecolor=GRID_COL, alpha=0.8))

        ax.set_xlabel("Predicted Gap (s)", color=TEXT_COL)
        ax.set_ylabel("Actual Gap (s)",    color=TEXT_COL)
        ax.tick_params(colors=TEXT_COL)
        ax.spines[:].set_color(GRID_COL)

        fig.text(0.5, 0.97, "2026 F1 — Prediction vs Actual",
                 ha="center", va="top", fontsize=13,
                 color=ACCENT_COL, fontweight="bold", fontfamily="monospace")
        fig.text(0.5, 0.93, "Awaiting first race comparison",
                 ha="center", va="top", fontsize=8,
                 color=TEXT_COL, fontfamily="monospace")

        plt.tight_layout(rect=[0, 0, 1, 0.91])

        if save:
            save_and_show(fig, "prediction_scatter.png", show=show)
        elif show:
            plt.show()
        return fig

    # ── Plot data ─────────────────────────────────────────
    preds   = np.array([d["predicted"] for d in data])
    actuals = np.array([d["actual"]    for d in data])
    lows    = np.array([d["low"]       for d in data])
    highs   = np.array([d["high"]      for d in data])

    max_val = max(preds.max(), actuals.max()) * 1.05
    min_val = min(preds.min(), actuals.min()) - 0.1

    # Perfect prediction diagonal
    diag = np.linspace(min_val, max_val, 100)
    ax.plot(diag, diag, color=ACCENT_COL, linewidth=0.8,
            linestyle="--", alpha=0.4, zorder=1, label="Perfect prediction")

    # Plot per PU
    plotted_pus = set()
    for d in data:
        colour = PU_COLOURS.get(d["pu"], "#888888")
        err_lo = d["predicted"] - d["low"]
        err_hi = d["high"]      - d["predicted"]

        ax.errorbar(
            d["predicted"], d["actual"],
            xerr=[[err_lo], [err_hi]],
            fmt="o", color=colour, markersize=6,
            ecolor=colour, elinewidth=0.8, capsize=3, capthick=0.8,
            alpha=0.85, zorder=3,
        )

        # Driver label
        ax.annotate(
            d["driver"],
            xy=(d["predicted"], d["actual"]),
            xytext=(4, 3), textcoords="offset points",
            fontsize=6.5, color=colour, alpha=0.85,
        )
        plotted_pus.add(d["pu"])

    # Compute MAE
    mae = float(np.mean(np.abs(preds - actuals)))
    in_range = int(np.sum((actuals >= lows) & (actuals <= highs)))
    pct_in   = in_range / len(data) * 100

    # Stats box
    stats_txt = (f"MAE: {mae:.3f}s\n"
                 f"In range: {in_range}/{len(data)} ({pct_in:.0f}%)")
    ax.text(0.03, 0.97, stats_txt, transform=ax.transAxes,
            fontsize=8, color=TEXT_COL, va="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor=DARK_BG,
                      edgecolor=GRID_COL, alpha=0.8))

    # Legend
    legend_handles = [
        mlines.Line2D([0], [0], marker="o", color="w",
                      markerfacecolor=PU_COLOURS[pu], markersize=7, label=pu)
        for pu in PU_ORDER if pu in plotted_pus
    ]
    legend_handles.append(
        mlines.Line2D([0], [0], color=ACCENT_COL, linewidth=0.8,
                      linestyle="--", alpha=0.4, label="Perfect prediction")
    )
    ax.legend(handles=legend_handles, fontsize=8, framealpha=0.3)

    ax.set_xlabel("Predicted Gap to Leader (s)", color=TEXT_COL)
    ax.set_ylabel("Actual Gap to Leader (s)",    color=TEXT_COL)
    ax.set_xlim(min_val, max_val)
    ax.set_ylim(min_val, max_val)
    ax.set_aspect("equal")
    ax.tick_params(colors=TEXT_COL)
    ax.spines[:].set_color(GRID_COL)

    circuits = list({d["circuit"] for d in data})
    fig.text(0.5, 0.97, "2026 F1 — Prediction Accuracy",
             ha="center", va="top", fontsize=13,
             color=ACCENT_COL, fontweight="bold", fontfamily="monospace")
    fig.text(0.5, 0.93,
             f"Circuits: {', '.join(circuits)}  |  Error bars = predicted range  |  Diagonal = perfect",
             ha="center", va="top", fontsize=7.5,
             color=TEXT_COL, fontfamily="monospace")

    plt.tight_layout(rect=[0, 0, 1, 0.91])

    if save:
        save_and_show(fig, "prediction_scatter.png", show=show)
    elif show:
        plt.show()

    return fig


if __name__ == "__main__":
    plot_prediction_scatter()
