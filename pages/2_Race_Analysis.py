"""pages/2_Race_Analysis.py — Round-by-round fingerprint viewer with DNF display."""

import os, sys
import streamlit as st
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import get_fingerprints, get_circuits_with_data, get_sessions_for_round
from app.charts import harvest_bars_chart
from config import CARS

st.set_page_config(page_title="Race Analysis — ERS_v2", page_icon="📊", layout="wide")
st.markdown('<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
            'border-radius:2px;margin-bottom:1rem;"></div>', unsafe_allow_html=True)
st.title("📊 Race Analysis")

circuit_map = get_circuits_with_data()
if not circuit_map:
    st.warning("No race data in store.")
    st.stop()

round_options = {f"R{r} — {circuit_map[r]}": r for r in sorted(circuit_map.keys())}
selected_label = st.selectbox("Round", list(round_options.keys()), index=len(round_options)-1)
selected_round = round_options[selected_label]
circuit_name   = circuit_map[selected_round]

st.markdown(f"**{circuit_name}** · Round {selected_round}")
available_sessions = get_sessions_for_round(selected_round)

if not available_sessions:
    st.info("No sessions loaded for this round.")
    st.stop()

tabs = st.tabs([f"Session {s}" for s in available_sessions])
all_fps = get_fingerprints()

for tab, session in zip(tabs, available_sessions):
    with tab:
        round_fps = [fp for fp in all_fps
                     if fp.race_round == selected_round and fp.session_type == session]

        if not round_fps:
            st.info(f"No {session} fingerprints for R{selected_round}.")
            continue

        sorted_fps = sorted(round_fps, key=lambda f: f.lap_time_s)
        ref_time   = sorted_fps[0].lap_time_s

        # Summary strip
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Fastest", sorted_fps[0].driver_code,
                  f"{int(ref_time//60)}:{ref_time%60:06.3f}")
        m2.metric("Circuit type", sorted_fps[0].circuit_type.title())
        m3.metric("Epoch", sorted_fps[0].regulation_epoch.replace("_", " "))
        m4.metric("Cars with data", len(round_fps))

        st.markdown("")

        # Fingerprint table
        rows = []
        in_store = {fp.driver_code for fp in round_fps}

        for fp in sorted_fps:
            rows.append({
                "Pos":      fp.lap_time_rank,
                "Driver":   fp.driver_code,
                "Team":     fp.team,
                "PU":       fp.pu_name,
                "Lap Time": f"{int(fp.lap_time_s//60)}:{fp.lap_time_s%60:06.3f}",
                "Gap %":    round(fp.lap_time_gap_pct, 3),
                "Str Δ":    round(fp.straight_speed_delta_kph, 1),
                "Brk Δ":    round(fp.braking_speed_delta_kph, 1),
                "Hrv":      round(fp.braking_harvest_ratio, 3),
                "Conf":     round(fp.confidence, 2),
                "Epoch":    fp.regulation_epoch,
                "Status":   "DNF" if not fp.completed_race else "OK",
            })

        # Show missing drivers as DNF
        for drv, info in CARS.items():
            if drv not in in_store:
                rows.append({
                    "Pos":      "—",
                    "Driver":   drv,
                    "Team":     info["team"],
                    "PU":       info["pu"],
                    "Lap Time": "—",
                    "Gap %":    "—",
                    "Str Δ":    "—",
                    "Brk Δ":    "—",
                    "Hrv":      "—",
                    "Conf":     "—",
                    "Epoch":    "—",
                    "Status":   "DNF / No data",
                })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # ERS harvest note for race sessions
        if session in ("R", "S"):
            st.markdown("---")
            st.info(
                "**Race session harvest ratios are not shown here.**  \n"
                "Each driver's representative lap comes from a different race moment "
                "(different fuel load, tyre compound, track position). "
                "Speed-based harvest comparison vs a single reference car is "
                "meaningless in these conditions.  \n"
                "→ See **Teams & Drivers → PU Analysis** for harvest efficiency "
                "computed from qualifying sessions where conditions are controlled."
            )
