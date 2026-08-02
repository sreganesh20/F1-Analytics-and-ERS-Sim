"""
Home.py — ERS_v2 Season Overview
Main entry point for the Streamlit app.
"""

import os
import sys
import streamlit as st

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (get_fingerprints, get_driver_standings,
                              get_constructor_standings, get_circuits_with_data,
                              list_available_predictions, get_prediction_data,
                              TEAM_COLOURS)
from app.charts import season_evolution_chart

st.set_page_config(
    page_title="ERS_v2 — F1 2026 Analytics",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Header ───────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:1.5rem 0 0.5rem 0;">
    <div style="font-family:monospace;font-size:2.5rem;font-weight:bold;
                color:#FF1E00;letter-spacing:4px;">ERS_v2</div>
    <div style="font-family:monospace;font-size:0.9rem;color:#888;margin-top:4px;">
        F1 2026 · ERS Strategy Analysis & Race Prediction
    </div>
</div>
""", unsafe_allow_html=True)
st.divider()

# ── Top metrics ──────────────────────────────────────────
circuit_map = get_circuits_with_data()
ds = get_driver_standings()
cs = get_constructor_standings()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Rounds Complete", f"{max(circuit_map.keys()) if circuit_map else 0} / 23")
m2.metric("Championship Leader",
          ds[0]["code"] if ds else "—",
          f"{ds[0]['points']:.0f} pts" if ds else "")
m3.metric("Constructors Leader",
          cs[0]["team"][:12] if cs else "—",
          f"{cs[0]['points']:.0f} pts" if cs else "")
m4.metric("Sessions in Store", len(get_circuits_with_data()))

st.divider()

# ── Championship standings ────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Driver Standings")
    if ds:
        leader_pts = ds[0]["points"]
        for s in ds[:10]:
            gap = f"–{leader_pts - s['points']:.0f}" if s["pos"] > 1 else "leader"
            c1, c2, c3, c4, c5 = st.columns([0.7, 1.2, 2.5, 1.5, 1])
            c1.markdown(f"**P{s['pos']}**")
            c2.markdown(f"`{s['code']}`")
            c3.markdown(s["name"][:22])
            c4.markdown(f"**{s['points']:.0f}** pts")
            c5.markdown(f"_{gap}_")
    else:
        st.info("Standings unavailable — check internet connection.")

with col2:
    st.subheader("🏗️ Constructor Standings")
    if cs:
        leader_pts = cs[0]["points"]
        for s in cs[:10]:
            gap = f"–{leader_pts - s['points']:.0f}" if s["pos"] > 1 else "leader"
            col = TEAM_COLOURS.get(s["team"], "#888")
            c1, c2, c3, c4 = st.columns([0.7, 3, 1.5, 1])
            c1.markdown(f"**P{s['pos']}**")
            c2.markdown(
                f'<span style="color:{col};font-weight:bold;">{s["team"][:22]}</span>',
                unsafe_allow_html=True
            )
            c3.markdown(f"**{s['points']:.0f}** pts")
            c4.markdown(f"_{gap}_")
    else:
        st.info("Standings unavailable.")

st.divider()

# ── PU Performance Evolution ─────────────────────────────
st.subheader("📈 PU Performance Evolution")
fps = get_fingerprints(sessions=["Q", "R"])
if fps:
    fig = season_evolution_chart(fps)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Line = best car per PU per round (factory team only). "
        "Shaded band = full PU group spread (factory → customer teams)."
    )
else:
    st.info("No fingerprint data in store yet.")

st.divider()

# ── Next race prediction preview ─────────────────────────
st.subheader("🔮 Latest Prediction")
preds = list_available_predictions()
if preds:
    circuit = preds[-1]
    pred = get_prediction_data(circuit)
    if pred:
        st.markdown(f"**{circuit}** — {pred.get('circuit_type','').title()} circuit  "
                    f"· {pred.get('n_historical_races',0)} sessions · "
                    f"confidence {pred.get('overall_confidence',0):.0%}")
        top5 = pred.get("predictions", [])[:5]
        if top5:
            c1, c2, c3, c4 = st.columns([0.7, 1.5, 2.5, 2])
            for h in ["Pos", "Driver", "Team", "Predicted Gap"]:
                [c1, c2, c3, c4][["Pos","Driver","Team","Predicted Gap"].index(h)]\
                    .markdown(f"**{h}**")
            for i, p in enumerate(top5):
                gap = f"+{p['predicted_delta_s']:.3f}s" if p['predicted_delta_s'] > 0 else "POLE"
                c1, c2, c3, c4 = st.columns([0.7, 1.5, 2.5, 2])
                c1.markdown(f"P{i+1}")
                c2.markdown(f"`{p['driver_code']}`")
                c3.markdown(p["team"])
                c4.markdown(f"`{gap}`")
        st.caption("Full prediction → **🔮 Predictions** page")
else:
    st.info("No predictions stored. Run `python run.py predict <circuit>` locally.")

# ── Footer ────────────────────────────────────────────────
st.divider()
st.caption(
    "ERS_v2 · Built on FastF1 · Telemetry-derived fingerprinting + DP optimizer · "
    "Data updated after each race weekend. "
    f"Rounds with data: {sorted(circuit_map.keys())}"
)
