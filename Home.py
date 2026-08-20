"""Home.py — PitWall · F1 2026 Season Overview"""

import os, sys
import streamlit as st

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (get_fingerprints, get_driver_standings,
                             get_constructor_standings, get_circuits_with_data,
                             list_available_predictions, get_prediction_data,
                             driver_badge, driver_name, TEAM_COLOURS)
from app.charts import season_evolution_chart

st.set_page_config(page_title="PitWall — F1 2026 Analytics",
                   page_icon="🏁", layout="wide",
                   initial_sidebar_state="expanded")

# ── Header ────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:1.2rem 0 0.3rem 0;">
    <div style="font-family:monospace;font-size:3rem;font-weight:bold;
                color:#FF1E00;letter-spacing:6px;line-height:1;">PITWALL</div>
    <div style="font-family:monospace;font-size:0.85rem;color:#888;
                margin-top:8px;letter-spacing:1px;">
        F1 2026 · Telemetry Analytics &amp; Race Strategy
    </div>
</div>
""", unsafe_allow_html=True)
st.markdown('<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
            'border-radius:2px;margin:1rem 0 1.5rem 0;"></div>', unsafe_allow_html=True)

circuit_map = get_circuits_with_data()
ds = get_driver_standings()
cs = get_constructor_standings()

# ── Top metrics ───────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Rounds Complete", f"{max(circuit_map.keys()) if circuit_map else 0} / 23")
with m2:
    st.markdown("**Championship Leader**")
    if ds:
        st.markdown(driver_badge(ds[0]["code"], "lg"), unsafe_allow_html=True)
        st.markdown(f"**{ds[0]['points']:.0f}** pts · {ds[0]['wins']} wins")
    else:
        st.markdown("—")
with m3:
    st.markdown("**Constructors Leader**")
    if cs:
        col = TEAM_COLOURS.get(cs[0]["team"], "#888")
        st.markdown(
            f'<div style="border-left:4px solid {col};padding:4px 10px;'
            f'background:{col}18;border-radius:4px;font-family:monospace;">'
            f'<b style="color:{col};">{cs[0]["team"]}</b></div>',
            unsafe_allow_html=True)
        st.markdown(f"**{cs[0]['points']:.0f}** pts")
    else:
        st.markdown("—")
m4.metric("Sessions Analysed", len(get_fingerprints()) and len(circuit_map) * 2 or 0)

st.divider()

# ── Standings ─────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Drivers' Championship")
    if ds:
        leader_pts = ds[0]["points"]
        show_all = st.toggle("Show all 22 drivers", value=False, key="all_drivers")
        rows = ds if show_all else ds[:10]
        for s in rows:
            gap = "leader" if s["pos"] == 1 else f"–{leader_pts - s['points']:.0f}"
            c = st.columns([0.6, 1.6, 2.6, 1.1, 0.9])
            c[0].markdown(f"**P{s['pos']}**")
            c[1].markdown(driver_badge(s["code"], "sm"), unsafe_allow_html=True)
            c[2].markdown(f"{driver_name(s['code'])}"
                          if driver_name(s["code"]) != s["code"] else s["name"])
            c[3].markdown(f"**{s['points']:.0f}**")
            c[4].markdown(f"<span style='color:#888;font-size:0.8rem;'>{gap}</span>",
                          unsafe_allow_html=True)
        if not show_all and len(ds) > 10:
            st.caption(f"Showing top 10 of {len(ds)}")
    else:
        st.info("Standings unavailable — check connection.")

with col2:
    st.subheader("🏗️ Constructors' Championship")
    if cs:
        leader_pts = cs[0]["points"]
        for s in cs:                      # ALL 11 teams
            gap = "leader" if s["pos"] == 1 else f"–{leader_pts - s['points']:.0f}"
            col = TEAM_COLOURS.get(s["team"], "#888")
            c = st.columns([0.6, 3.4, 1.1, 0.9])
            c[0].markdown(f"**P{s['pos']}**")
            c[1].markdown(
                f'<span style="border-left:3px solid {col};padding-left:8px;'
                f'color:{col};font-weight:bold;font-family:monospace;">'
                f'{s["team"]}</span>', unsafe_allow_html=True)
            c[2].markdown(f"**{s['points']:.0f}**")
            c[3].markdown(f"<span style='color:#888;font-size:0.8rem;'>{gap}</span>",
                          unsafe_allow_html=True)
        st.caption(f"All {len(cs)} constructors")
    else:
        st.info("Standings unavailable.")

st.divider()

# ── PU Performance Evolution ──────────────────────────────
hdr, btn = st.columns([5, 1])
hdr.subheader("📈 Power Unit Performance Evolution")
with btn:
    with st.popover("ℹ️ How to read"):
        st.markdown("""
**What this shows**

For each power unit manufacturer, the line tracks their **fastest factory-team car**
in each round, measured as a percentage gap to that session's fastest car overall.

**Why factory teams only?**
Ferrari power Ferrari, Haas and Cadillac. Averaging all three would blend
Cadillac's chassis deficit into Ferrari's PU line. Using the works team isolates
what the manufacturer achieves with their own car.

**Why gap to session-fastest, not a lap-time record?**
Lap records aren't comparable across the season — different regulations, fuel
loads, tyre compounds and track conditions. Gap to the fastest car on the day is
the only stable reference.

**Reading the chart**
`0%` at the top = level with the session's fastest car. Lower on the chart = further
behind. The shaded band spans the whole PU group, from factory team down to the
slowest customer — a wide band means the PU is in cars of very different quality.

**Caveat:** the leading PU sits near 0% partly by construction, since its own car is
often the reference.
        """)

fps = get_fingerprints(sessions=["Q", "R"])
if fps:
    st.plotly_chart(season_evolution_chart(fps), use_container_width=True)
else:
    st.info("No fingerprint data yet.")

st.divider()

# ── Latest prediction preview ─────────────────────────────
st.subheader("🔮 Latest Prediction")
preds = list_available_predictions()
if preds:
    circuit = preds[-1]
    pred = get_prediction_data(circuit, pred_type="quali")
    if pred:
        st.markdown(f"**{circuit}** · {pred.get('circuit_type','').replace('_',' ').title()} "
                    f"circuit · confidence {pred.get('overall_confidence',0):.0%}")
        for i, p in enumerate(pred.get("predictions", [])[:5]):
            gap = f"+{p['predicted_delta_s']:.3f}s" if p["predicted_delta_s"] > 0 else "POLE"
            col = TEAM_COLOURS.get(p["team"], "#888")
            c = st.columns([0.6, 1.6, 2.6, 1.4])
            c[0].markdown(f"**P{i+1}**")
            c[1].markdown(driver_badge(p["driver_code"], "sm"), unsafe_allow_html=True)
            c[2].markdown(f'<span style="color:{col};">{p["team"]}</span>',
                          unsafe_allow_html=True)
            c[3].markdown(f"`{gap}`")
        st.caption("Full qualifying and race-pace predictions → **Weekend Predictions**")
else:
    st.info("No predictions stored. Run `python run.py predict <circuit>` locally.")

st.divider()
st.caption(
    "PitWall · Built on FastF1 · Telemetry fingerprinting + dynamic-programming ERS optimizer · "
    f"Data through Round {max(circuit_map.keys()) if circuit_map else 0}."
)
