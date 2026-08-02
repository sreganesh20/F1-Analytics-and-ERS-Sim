"""
viz/base.py
Shared constants, palette, and helpers for all charts.
"""

import os
import matplotlib.pyplot as plt
import matplotlib as mpl

# ─────────────────────────────────────────────────────────
#  Output directory
# ─────────────────────────────────────────────────────────

VIZ_DIR = os.path.join(os.path.dirname(__file__), "..", "viz", "outputs")


def ensure_output_dir():
    os.makedirs(VIZ_DIR, exist_ok=True)


def output_path(filename: str) -> str:
    ensure_output_dir()
    return os.path.join(VIZ_DIR, filename)


# ─────────────────────────────────────────────────────────
#  PU colour palette — consistent across all charts
# ─────────────────────────────────────────────────────────

PU_COLOURS = {
    "Mercedes":    "#00D2BE",
    "Ferrari":     "#DC143C",
    "RedBullFord": "#1E41FF",
    "Honda":       "#CC1E4A",
    "Audi":        "#C0C0C0",
}

PU_ORDER = ["Mercedes", "Ferrari", "RedBullFord", "Audi", "Honda"]

# Team → PU mapping for convenience
TEAM_TO_PU = {
    "Mercedes":     "Mercedes",
    "McLaren":      "Mercedes",
    "Williams":     "Mercedes",
    "Alpine":       "Mercedes",
    "Ferrari":      "Ferrari",
    "Haas":         "Ferrari",
    "Cadillac":     "Ferrari",
    "Red Bull":     "RedBullFord",
    "VCARB":        "RedBullFord",
    "Aston Martin": "Honda",
    "Audi":         "Audi",
}


def pu_colour(pu_name: str) -> str:
    return PU_COLOURS.get(pu_name, "#888888")


# ─────────────────────────────────────────────────────────
#  Global matplotlib style — dark, F1-appropriate
# ─────────────────────────────────────────────────────────

DARK_BG    = "#0F0F0F"
PANEL_BG   = "#1A1A1A"
GRID_COL   = "#2A2A2A"
TEXT_COL   = "#E0E0E0"
ACCENT_COL = "#FFFFFF"


def apply_style():
    """Apply consistent dark style to all charts."""
    mpl.rcParams.update({
        "figure.facecolor":    DARK_BG,
        "axes.facecolor":      PANEL_BG,
        "axes.edgecolor":      GRID_COL,
        "axes.labelcolor":     TEXT_COL,
        "axes.titlecolor":     ACCENT_COL,
        "axes.grid":           True,
        "grid.color":          GRID_COL,
        "grid.linewidth":      0.5,
        "xtick.color":         TEXT_COL,
        "ytick.color":         TEXT_COL,
        "text.color":          TEXT_COL,
        "legend.facecolor":    PANEL_BG,
        "legend.edgecolor":    GRID_COL,
        "legend.labelcolor":   TEXT_COL,
        "font.family":         "monospace",
        "font.size":           9,
        "axes.titlesize":      11,
        "axes.labelsize":      9,
        "figure.dpi":          120,
    })


# ─────────────────────────────────────────────────────────
#  Save + show helper
# ─────────────────────────────────────────────────────────

def save_and_show(fig: plt.Figure, filename: str, show: bool = True):
    """Save figure to outputs/ and optionally display."""
    path = output_path(filename)
    fig.savefig(path, bbox_inches="tight", facecolor=DARK_BG, dpi=120)
    print(f"  Saved → {path}")
    if show:
        plt.show()
    plt.close(fig)


# ─────────────────────────────────────────────────────────
#  Data helpers
# ─────────────────────────────────────────────────────────

def load_race_fingerprints(sessions=None):
    """Load fingerprints from store. Returns flat list of CarFingerprint."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data.race_store import load_all_fingerprints

    if sessions is None:
        sessions = ["Q", "R"]

    all_rfs = load_all_fingerprints(year=2026, sessions=sessions)
    fps = [fp for rf in all_rfs for fp in rf.fingerprints]
    return fps, all_rfs


def circuit_label(circuit_name: str, race_round: int) -> str:
    return f"Rd{race_round}\n{circuit_name[:3].upper()}"
