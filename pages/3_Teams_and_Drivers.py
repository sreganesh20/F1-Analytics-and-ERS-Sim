"""pages/3_Teams_and_Drivers.py — Driver stats, team comparison, PU analysis."""

import os, sys
import streamlit as st
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (get_fingerprints, get_circuits_with_data,
                             PU_COLOURS, TEAM_COLOURS, PU_ORDER, FACTORY_TEAMS,
                             get_teammate, teammate_stats)
from app.charts import (fingerprint_radar_chart, harvest_bars_chart,
                        pace_trend_chart, teammate_gap_chart,
                        straight_vs_corner_scatter, corner_profile_ranking,
                        pu_straight_speed_chart)
from config import CARS

st.set_page_config(page_title="Teams & Drivers — ERS_v2", page_icon="🏎️", layout="wide")
st.markdown('<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
            'border-radius:2px;margin-bottom:1rem;"></div>', unsafe_allow_html=True)
st.title("🏎️ Teams & Drivers")

all_fps = get_fingerprints()
if not all_fps:
    st.warning("No fingerprint data in store.")
    st.stop()

circuit_map = get_circuits_with_data()
tab1, tab2, tab3 = st.tabs(["👤 Drivers", "🏗️ Teams", "⚡ PU Analysis"])

# ─────────────────────────────────────────────────────────
# TAB 1: DRIVERS
# ─────────────────────────────────────────────────────────
with tab1:
    all_drivers = sorted({fp.driver_code for fp in all_fps})
    default_idx = all_drivers.index("ANT") if "ANT" in all_drivers else 0
    driver      = st.selectbox("Driver", all_drivers, index=default_idx)

    car_info = CARS.get(driver, {})
    team     = car_info.get("team", "—")
    pu       = car_info.get("pu", "—")
    team_col = TEAM_COLOURS.get(team, "#888")
    pu_col   = PU_COLOURS.get(pu, "#888")
    teammate = get_teammate(driver)

    # Driver card + stats
    col_left, col_right = st.columns([1, 3])
    with col_left:
        st.markdown(f"""
        <div style="padding:14px 16px;background:#1A1A1A;border-radius:10px;
                    border-left:4px solid {team_col};margin-bottom:12px;">
            <div style="font-size:1.5rem;font-weight:bold;color:{team_col};
                       font-family:monospace;">{driver}</div>
            <div style="color:{team_col};font-family:monospace;font-size:0.9rem;">{team}</div>
            <div style="color:{pu_col};font-family:monospace;font-size:0.8rem;">{pu} PU</div>
            {'<div style="color:#888;font-family:monospace;font-size:0.75rem;margin-top:4px;">Teammate: ' + teammate + '</div>' if teammate else ''}
        </div>
        """, unsafe_allow_html=True)

        d_fps_q = [fp for fp in all_fps if fp.driver_code == driver and fp.session_type in ("Q","SQ")]
        d_fps_r = [fp for fp in all_fps if fp.driver_code == driver and fp.session_type in ("R","S")]

        if d_fps_q:
            best = min(d_fps_q, key=lambda f: f.lap_time_gap_pct)
            st.metric("Avg Q Gap", f"{np.mean([f.lap_time_gap_pct for f in d_fps_q]):.3f}%")
            st.metric("Best Q", f"R{best.race_round} {circuit_map.get(best.race_round,'')}", f"{best.lap_time_gap_pct:.3f}%")
        if d_fps_r:
            st.metric("Avg Race Gap", f"{np.mean([f.lap_time_gap_pct for f in d_fps_r]):.3f}%")
            st.metric("Avg Harvest", f"{np.mean([f.braking_harvest_ratio for f in d_fps_r]):.3f}")
        st.metric("Rounds (Q)", len(d_fps_q))

    with col_right:
        fig = pace_trend_chart(all_fps, driver)
        st.plotly_chart(fig, use_container_width=True)

    # ── Teammate comparison ────────────────────────────────
    st.markdown("---")
    st.subheader(f"🤝 vs Teammate")

    if not teammate:
        st.info("No teammate found for this driver.")
    else:
        stats = teammate_stats(all_fps, driver, teammate)

        if stats["total"] == 0:
            st.info(f"No common qualifying rounds found between {driver} and {teammate}.")
        else:
            # Summary header
            wins_str    = f"{stats['d1_wins']}/{stats['total']} rounds faster"
            avg_gap_s   = stats['avg_gap_s']
            avg_gap_pct = stats['avg_gap_pct']
            faster_str  = f"avg {avg_gap_s:+.3f}s ({avg_gap_pct:+.3f}%)"
            indicator   = "✅ FASTER" if avg_gap_s < 0 else "❌ SLOWER"
            ind_colour  = "#00C851" if avg_gap_s < 0 else "#FF4444"

            st.markdown(f"""
            <div style="padding:14px 18px;background:#1A1A1A;border-radius:10px;
                        border-left:4px solid {team_col};margin-bottom:12px;">
                <div style="font-family:monospace;font-size:0.8rem;color:#888;">
                    {driver} vs {teammate} · Qualifying
                </div>
                <div style="font-family:monospace;font-size:1.2rem;font-weight:bold;
                            color:{team_col};margin:4px 0;">{wins_str}</div>
                <div style="font-family:monospace;font-size:0.9rem;">
                    <span style="color:{ind_colour};">{indicator}</span>
                    &nbsp;{faster_str} on average
                </div>
            </div>
            """, unsafe_allow_html=True)

            fig = teammate_gap_chart(all_fps, driver, teammate, circuit_map, team_col)
            st.plotly_chart(fig, use_container_width=True)

            st.caption(f"Negative bars = {driver} faster. Positive = {teammate} faster. "
                       "Bars show lap time difference in seconds; hover for % equivalent.")


# ─────────────────────────────────────────────────────────
# TAB 2: TEAMS
# ─────────────────────────────────────────────────────────
with tab2:
    st.subheader("📍 Team Performance Map: Straight vs Corner")
    st.caption("All 11 teams. X = straight-line speed advantage, Y = corner speed advantage. "
               "Coloured by PU supplier. Dot size = rounds of data.")
    fps_q = [fp for fp in all_fps if fp.session_type in ("Q", "SQ")]
    fig = straight_vs_corner_scatter(fps_q)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏁 Corner Performance Ranking")
        fig = corner_profile_ranking(fps_q)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("📊 Overall Pace Ranking (Q — All Teams)")
        team_pace = {}
        for fp in fps_q:
            if fp.confidence < 0.5:
                continue
            if fp.team not in team_pace:
                team_pace[fp.team] = {"gaps": [], "pu": fp.pu_name}
            team_pace[fp.team]["gaps"].append(fp.lap_time_gap_pct)

        rows = []
        for i, (team, d) in enumerate(sorted(team_pace.items(),
                                              key=lambda x: np.mean(x[1]["gaps"])), 1):
            rows.append({
                "Pos": i,
                "Team": team,
                "PU": d["pu"],
                "Avg Gap %": round(np.mean(d["gaps"]), 3),
                "Best %": round(min(d["gaps"]), 3),
                "Worst %": round(max(d["gaps"]), 3),
                "Rounds": len(d["gaps"]),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # Intra-team comparison table
    st.subheader("🤝 Intra-Team Qualifying Battle")
    st.caption("Who's winning the teammate battle in qualifying across all rounds.")
    rows = []
    seen = set()
    for fp in fps_q:
        if fp.confidence < 0.5:
            continue
        drv = fp.driver_code
        tmt = get_teammate(drv)
        if not tmt or (drv, tmt) in seen or (tmt, drv) in seen:
            continue
        seen.add((drv, tmt))
        stats = teammate_stats(all_fps, drv, tmt)
        if stats["total"] == 0:
            continue
        rows.append({
            "Team": fp.team,
            "Driver 1": drv,
            "Driver 2": tmt,
            f"D1 faster": f"{stats['d1_wins']}/{stats['total']}",
            "Avg gap s": f"{stats['avg_gap_s']:+.3f}",
            "Avg gap %": f"{stats['avg_gap_pct']:+.3f}",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────
# TAB 3: PU ANALYSIS
# ─────────────────────────────────────────────────────────
with tab3:
    st.markdown("### ⚡ Power Unit Analysis")
    st.caption("Factory teams only. Signals = combined PU output + chassis effect — not ICE-only.")

    fps_r  = [fp for fp in all_fps if fp.session_type == "R"]
    fps_qh = [fp for fp in all_fps if fp.session_type in ("Q", "SQ")]  # qualifying only for harvest comparison
    fps_q = [fp for fp in all_fps if fp.session_type in ("Q", "SQ")]

    # PU straight-line speed
    st.markdown("**Straight-Line Speed Delta — Factory Teams (Qualifying)**")
    fig = pu_straight_speed_chart(fps_q)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**ERS Fingerprint Radar**")
        fig = fingerprint_radar_chart(fps_r)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.markdown("**Braking Harvest Efficiency (Qualifying)**")
        st.caption("Race session harvest ratios are unreliable — different fuel/tyre per driver. Qualifying = controlled conditions.")
        fig = harvest_bars_chart(fps_qh, sessions=["Q", "SQ"])
        st.plotly_chart(fig, use_container_width=True)

    # ADUO context table
    st.markdown("---")
    st.markdown("**ADUO ICE Performance Index (Confirmed Monaco R6)**")
    st.caption("ADUO measures ICE performance only — not ERS/electrical side. "
               "Straight-line chart above reflects combined PU+chassis.")
    aduo_rows = [
        {"Rank": 1, "PU": "RedBullFord", "ADUO Band": "Benchmark (0%)",
         "2026 Upgrades": "0 (no deficit)", "Note": "Best ICE on grid. Chassis limits results."},
        {"Rank": 2, "PU": "Mercedes",    "ADUO Band": ">2% deficit",
         "2026 Upgrades": "1",            "Note": "8 race wins from ERS/electrical advantage."},
        {"Rank": "3-5*", "PU": "Ferrari", "ADUO Band": ">4% deficit",
         "2026 Upgrades": "2",            "Note": "2 wins. Exact rank vs Honda/Audi unknown."},
        {"Rank": "3-5*", "PU": "Honda",   "ADUO Band": ">4% deficit",
         "2026 Upgrades": "2",            "Note": "Worst PU + weak chassis = large field gap."},
        {"Rank": "3-5*", "PU": "Audi",    "ADUO Band": ">4% deficit",
         "2026 Upgrades": "2",            "Note": "Debut season. Broadest dev runway."},
    ]
    st.dataframe(pd.DataFrame(aduo_rows), use_container_width=True, hide_index=True)
    st.caption("*FIA only confirmed 2% and 4% bands — exact rank within the >4% group is not public.")
