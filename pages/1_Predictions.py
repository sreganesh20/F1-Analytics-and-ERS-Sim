"""pages/1_Predictions.py — PitWall · Weekend Predictions.

Shows every predicted session for a weekend. Standard weekends have two
(qualifying, race); sprint weekends have four, presented in the order they
actually run: sprint qualifying Friday, sprint Saturday morning, qualifying
Saturday afternoon, grand prix Sunday.
"""

import math
import os, sys
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (list_available_predictions, get_prediction_data,
                             conf_badge, TEAM_COLOURS)
from config import CIRCUITS

st.set_page_config(page_title="Weekend Predictions — PitWall",
                   page_icon="🔮", layout="wide")

ACCENT = ('<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
          'border-radius:2px;margin-bottom:1rem;"></div>')

# Grand prix and sprint distances, used to turn a per-lap pace delta into a
# gap a reader can picture. A sprint is 100 km, not 305 — using the grand prix
# figure for a sprint overstated the gap roughly threefold.
#
# Lap count uses ceil, not round: both distances are defined as the smallest
# number of laps EXCEEDING the target. round() gave Zandvoort a 23-lap sprint,
# which is 97.96 km and therefore not a sprint.
#
# Monaco is the known exception — its grand prix is shortened by regulation, so
# the estimate runs long there. The caption shows the arithmetic so the reader
# can see it is an estimate.
GP_DISTANCE_KM     = 305.0
SPRINT_DISTANCE_KM = 100.0

# Session order = the order the weekend runs, not the order files were written.
SESSION_TABS = {
    "sprint_quali": ("Sprint Qualifying", "Friday · sets the sprint grid"),
    "sprint_race":  ("Sprint",            "Saturday morning · 100 km, no mandatory stop"),
    "quali":        ("Qualifying",        "Saturday afternoon · sets the grand prix grid"),
    "race":         ("Race",              "Sunday · grand prix pace"),
}
SPRINT_ORDER = ["sprint_quali", "sprint_race", "quali", "race"]
NORMAL_ORDER = ["quali", "race"]

# A pooled-session prediction should say so on the page, not only inside the
# methodology expander.
SPRINT_PROVENANCE = (
    "Built from sprint sessions **and** grand prix sessions, with the sprint "
    "type weighted higher. Across the four 2026 sprint weekends so far, grand "
    "prix qualifying predicted sprint qualifying at the same event more closely "
    "than one grand prix qualifying predicts the next — so the wider sample is "
    "the stronger signal, not a fallback."
)

st.markdown(ACCENT, unsafe_allow_html=True)
st.title("🔮 Weekend Predictions")

circuits = list_available_predictions()
if not circuits:
    st.warning("No predictions stored yet. Run `python run.py predict <circuit>` "
               "locally, then push the files in `store/predictions/`.")
    st.stop()

circuit = st.selectbox("Circuit", circuits, index=len(circuits) - 1)

cfg       = CIRCUITS.get(circuit, {})
lap_km    = cfg.get("lap_length_km")
is_sprint = bool(cfg.get("has_sprint"))
order     = SPRINT_ORDER if is_sprint else NORMAL_ORDER

preds = {pt: get_prediction_data(circuit, pred_type=pt) for pt in order}
preds = {pt: p for pt, p in preds.items() if p}

if not preds:
    st.error(f"No prediction data found for {circuit}. "
             f"Run `python run.py predict {circuit.lower()}` and push the result.")
    st.stop()

if is_sprint and len(preds) < 4:
    missing = [SESSION_TABS[pt][0] for pt in order if pt not in preds]
    st.info(f"{circuit} is a sprint weekend, but these sessions have no stored "
            f"prediction: {', '.join(missing)}. "
            f"Re-run `python run.py predict {circuit.lower()}`.")


# ── Header ────────────────────────────────────────────────

ref = next(iter(preds.values()))
m1, m2, m3 = st.columns(3)
m1.metric("Round", ref.get("race_round", "—"))
m2.metric("Circuit type", str(ref.get("circuit_type", "—")).replace("_", " ").title())
m3.metric("Format", "Sprint weekend" if is_sprint else "Standard weekend")

st.divider()


# ── Footnotes ─────────────────────────────────────────────

def collect_footnotes(predictions):
    """
    Turn per-driver regulation notes into one numbered list.

    Notes are shared — every Honda driver carries the same ADUO paragraph — so
    per-driver expanders repeated the same text up to 22 times per grid. Here
    each distinct note appears once, numbered, listing the drivers it covers.

    Returns (footnotes, marker_map):
      footnotes  [(number, text, is_upgrade_warning, [driver codes])]
      marker_map {driver_code: [numbers]}
    """
    order_seen, by_text = [], {}
    for p in predictions:
        for note in p.get("regulation_notes", []):
            warn = note.startswith("⚠")
            text = note.lstrip("⚠").strip()
            if text not in by_text:
                by_text[text] = {"warn": warn, "drivers": []}
                order_seen.append(text)
            by_text[text]["drivers"].append(p["driver_code"])
            by_text[text]["warn"] = by_text[text]["warn"] or warn

    footnotes, marker_map = [], {}
    for i, text in enumerate(order_seen, 1):
        entry = by_text[text]
        footnotes.append((i, text, entry["warn"], entry["drivers"]))
        for d in entry["drivers"]:
            marker_map.setdefault(d, []).append(i)
    return footnotes, marker_map


# ── Grid ──────────────────────────────────────────────────

def render_grid(pred, pred_type):
    predictions = pred.get("predictions", [])
    if not predictions:
        st.info("This session has no prediction rows.")
        return

    is_race_type = pred_type in ("race", "sprint_race")
    distance_km  = SPRINT_DISTANCE_KM if pred_type == "sprint_race" else GP_DISTANCE_KM
    est_laps     = math.ceil(distance_km / lap_km) if lap_km else None

    footnotes, markers = collect_footnotes(predictions)

    n_sess = pred.get("n_historical_races", 0)
    conf   = pred.get("overall_confidence", 0)
    st.markdown(f"**{n_sess} sessions of history** · overall confidence {conf:.0%}")

    if pred_type.startswith("sprint_"):
        st.caption(SPRINT_PROVENANCE)

    if is_race_type and est_laps:
        st.caption(f"Gap shown as total time lost over ~{est_laps} laps "
                   f"({distance_km:.0f} km ÷ {lap_km:.3f} km lap).")

    st.markdown(
        '<div style="display:flex;align-items:center;padding:2px 10px;'
        'font-family:monospace;font-size:0.68rem;color:#666;'
        'letter-spacing:0.05em;text-transform:uppercase;">'
        '<div style="width:32px;">Pos</div>'
        '<div style="width:56px;">Driver</div>'
        '<div style="flex:1;">Team</div>'
        '<div style="width:110px;text-align:right;">Gap</div>'
        '<div style="width:120px;text-align:right;">Range</div>'
        '<div style="width:56px;text-align:right;">Harvest</div>'
        '<div style="width:86px;text-align:right;">Confidence</div>'
        '<div style="width:54px;text-align:right;">Notes</div>'
        '</div>', unsafe_allow_html=True)

    for i, p in enumerate(predictions, 1):
        delta = p["predicted_delta_s"]

        if i == 1:
            gap_str = "FASTEST" if is_race_type else "POLE"
        elif is_race_type and est_laps:
            gap_str = f"+{delta * est_laps:.1f}s"
        else:
            gap_str = f"+{delta:.3f}s"

        rng       = f"{p['delta_range_low']:+.2f} / {p['delta_range_high']:+.2f}"
        hrv       = p.get("predicted_harvest_ratio", 0)
        hrv_str   = f"{hrv:.3f}" if hrv and hrv < 1.5 else "—"
        team_col  = TEAM_COLOURS.get(p["team"], "#888")
        gap_style = "font-weight:bold;color:#FFD700;" if i == 1 else "color:#E0E0E0;"

        nums  = markers.get(p["driver_code"], [])
        marks = (f'<span style="color:#FF6B35;font-size:0.68rem;">'
                 f'{",".join(str(n) for n in nums)}</span>' if nums else "")

        st.markdown(f"""
        <div style="display:flex;align-items:center;padding:6px 10px;margin:3px 0;
                    background:#1A1A1A;border-radius:6px;border-left:3px solid {team_col};
                    font-family:monospace;">
            <div style="width:32px;font-size:1rem;font-weight:bold;color:#555;">P{i}</div>
            <div style="width:56px;font-size:1rem;font-weight:bold;color:{team_col};">{p['driver_code']}</div>
            <div style="flex:1;font-size:0.82rem;color:#aaa;">{p['team']}</div>
            <div style="width:110px;text-align:right;{gap_style}font-size:0.92rem;">{gap_str}</div>
            <div style="width:120px;text-align:right;font-size:0.72rem;color:#666;">[{rng}]</div>
            <div style="width:56px;text-align:right;font-size:0.75rem;color:#888;">{hrv_str}</div>
            <div style="width:86px;text-align:right;">{conf_badge(p['confidence'])}</div>
            <div style="width:54px;text-align:right;">{marks}</div>
        </div>
        """, unsafe_allow_html=True)

    if footnotes:
        st.markdown("")
        st.markdown("**Notes**")
        for num, text, warn, drivers in footnotes:
            who = ", ".join(sorted(set(drivers)))
            if warn:
                st.warning(f"**{num}. Incoming upgrade — prediction may understate.** "
                           f"{text}  \n*Applies to: {who}*")
            else:
                st.info(f"**{num}.** {text}  \n*Applies to: {who}*")

    with st.expander("How this prediction was built"):
        for note in pred.get("methodology_notes", []):
            st.markdown(f"• {note}")
        st.markdown(
            "• Gap is measured against the fastest predicted car, which sits at 0.  \n"
            "• Range is the uncertainty band, not a best or worst case.  \n"
            "• Harvest is observed braking energy recovery divided by the "
            "theoretical maximum, taken from qualifying laps only."
        )


# ── Tabs, in the order the weekend runs ───────────────────

available = [pt for pt in order if pt in preds]
tabs = st.tabs([SESSION_TABS[pt][0] for pt in available])

for tab, pt in zip(tabs, available):
    with tab:
        st.caption(SESSION_TABS[pt][1])
        render_grid(preds[pt], pt)
