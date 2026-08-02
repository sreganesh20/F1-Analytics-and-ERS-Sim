"""pages/1_Predictions.py — Qualifying & Race pace predictions side by side."""

import os, sys
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import list_available_predictions, get_prediction_data, conf_badge, TEAM_COLOURS
from config import CIRCUITS

st.set_page_config(page_title="Predictions — ERS_v2", page_icon="🔮", layout="wide")

st.markdown('<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
            'border-radius:2px;margin-bottom:1rem;"></div>', unsafe_allow_html=True)
st.title("🔮 Race Predictions")
st.caption("Q+SQ sessions → Qualifying prediction · R+S sessions → Race pace prediction")

circuits = list_available_predictions()
if not circuits:
    st.warning("No predictions stored. Run `python run.py predict <circuit>` locally, then push.")
    st.stop()

circuit = st.selectbox("Circuit", circuits, index=len(circuits) - 1)

qual_pred = get_prediction_data(circuit, pred_type="quali")
race_pred = get_prediction_data(circuit, pred_type="race")

if not qual_pred and not race_pred:
    st.error(f"No prediction data found for {circuit}.")
    st.stop()


def render_grid(predictions, session_label, pred_type="quali", lap_length_km=None):
    """Render a prediction as a styled starting grid."""
    if not predictions:
        st.info(f"No {session_label} prediction data.")
        return

    # Estimate race laps for cumulative gap calculation
    est_laps = round(305 / lap_length_km) if lap_length_km else None

    st.markdown(f"#### {session_label}")
    if pred_type == "race" and est_laps:
        st.caption(f"Gap shown as cumulative over ~{est_laps} laps "
                   f"(305km ÷ {lap_length_km:.3f}km lap)")

    for i, p in enumerate(predictions):
        pos = i + 1
        delta = p['predicted_delta_s']

        if pred_type == "race":
            if pos == 1:
                gap_str = "FASTEST"
            elif est_laps:
                total_s = delta * est_laps
                gap_str = f"+{total_s:.2f}s total"
            else:
                gap_str = f"+{delta:.3f}s/lap"
        else:
            gap_str = f"+{delta:.3f}s" if delta > 0 else "POLE"

        rng_str = f"{p['delta_range_low']:+.2f} / {p['delta_range_high']:+.2f}"
        hrv     = p.get("predicted_harvest_ratio", 0)
        hrv_str = f"{hrv:.3f}" if hrv < 1.5 else "—"
        team_col = TEAM_COLOURS.get(p["team"], "#888")

        gap_colour = "#FFD700" if pos == 1 else "#E0E0E0"
        gap_style  = "font-weight:bold;color:#FFD700;" if pos == 1 else "color:#E0E0E0;"

        notes = p.get("regulation_notes", [])
        has_warning = any(n.startswith("⚠") for n in notes)

        st.markdown(f"""
        <div style="display:flex;align-items:center;padding:6px 10px;margin:3px 0;
                    background:#1A1A1A;border-radius:6px;border-left:3px solid {team_col};
                    font-family:monospace;">
            <div style="width:32px;font-size:1rem;font-weight:bold;color:#555;">P{pos}</div>
            <div style="width:52px;font-size:1rem;font-weight:bold;color:{team_col};">{p['driver_code']}</div>
            <div style="flex:1;font-size:0.82rem;color:#aaa;">{p['team'][:18]}</div>
            <div style="width:60px;font-size:0.75rem;color:#666;">{p['pu_name'][:10]}</div>
            <div style="width:90px;text-align:right;{gap_style}font-size:0.92rem;">{gap_str}</div>
            <div style="width:130px;text-align:right;font-size:0.72rem;color:#666;">[{rng_str}]</div>
            <div style="width:50px;text-align:right;font-size:0.75rem;color:#888;">{hrv_str}</div>
            <div style="width:80px;text-align:right;">{conf_badge(p["confidence"])}</div>
            {'<div style="width:16px;text-align:right;font-size:0.8rem;">⚠</div>' if has_warning else '<div style="width:16px;"></div>'}
        </div>
        """, unsafe_allow_html=True)

        if notes:
            with st.expander(f"Notes — {p['driver_code']}", expanded=False):
                for note in notes:
                    if note.startswith("⚠"):
                        st.warning(note[2:].strip())
                    else:
                        st.info(note)

    st.markdown("")


# Header metrics
ref_pred = qual_pred or race_pred
m1, m2, m3 = st.columns(3)
m1.metric("Circuit type", ref_pred.get("circuit_type","—").title())
m2.metric("Round", ref_pred.get("race_round", "—"))
m3.metric("Sessions used", ref_pred.get("n_historical_races", 0))

st.divider()

col1, col2 = st.columns(2)
with col1:
    if qual_pred:
        c_str = f"{qual_pred.get('overall_confidence',0):.0%}"
        st.markdown(f"**🏎️ Qualifying** · {qual_pred.get('n_historical_races',0)} sessions · confidence {c_str}")
        lap_km = CIRCUITS.get(circuit, {}).get('lap_length_km', None)
        render_grid(qual_pred.get('predictions', []), 'Qualifying Prediction', pred_type='quali', lap_length_km=lap_km)
    else:
        st.info("No qualifying prediction. Run `python run.py predict` locally.")

with col2:
    if race_pred:
        c_str = f"{race_pred.get('overall_confidence',0):.0%}"
        st.markdown(f"**🏁 Race Pace** · {race_pred.get('n_historical_races',0)} sessions · confidence {c_str}")
        lap_km = CIRCUITS.get(circuit, {}).get('lap_length_km', None)
        render_grid(race_pred.get('predictions', []), 'Race Pace Prediction', pred_type='race', lap_length_km=lap_km)
    else:
        st.info("No race pace prediction stored.")

# Methodology
with st.expander("📐 Methodology"):
    for note in (qual_pred or race_pred).get("methodology_notes", []):
        st.markdown(f"• {note}")
