"""pages/3_Teams_and_Drivers.py — driver, team and PU analysis.

Wave 1 keeps the existing page layout and fixes round-aware driver/team identity.
The larger LatentLap information-architecture redesign comes in a later wave.
"""

import os
import sys

import numpy as np
import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (
    FACTORY_TEAMS,
    PU_COLOURS,
    PU_ORDER,
    TEAM_COLOURS,
    current_round,
    driver_info,
    driver_name,
    driver_season_stats,
    get_circuits_with_data,
    get_fingerprints,
    get_pu_aduo_summary,
    get_teammate,
    qualifying_ranking,
    teammate_ranking,
    teammate_season_overall,
    teammate_stats,
)
from app.charts import (
    corner_class_ranking,
    corner_profile_ranking,
    fingerprint_radar_chart,
    harvest_bars_chart,
    pu_straight_speed_chart,
    qualifying_ranking_chart,
    straight_vs_corner_scatter,
)

from app.season_charts import (
    finish_history_chart,
    pace_trend_chart,
    teammate_gap_chart,
    teammate_hierarchy_chart,
)

st.set_page_config(page_title="Teams & Drivers — PitWall", page_icon="🏎️", layout="wide")
st.markdown(
    '<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
    'border-radius:2px;margin-bottom:1rem;"></div>',
    unsafe_allow_html=True,
)
st.title("🏎️ Teams & Drivers")

all_fps = get_fingerprints()
if not all_fps:
    st.warning("No fingerprint data in store.")
    st.stop()

circuit_map = get_circuits_with_data()
latest_round = current_round()
tab1, tab2, tab3 = st.tabs(["👤 Drivers", "🏗️ Teams", "⚡ Power Units"])

# ══════════════════════════════════════════════════════════
# DRIVERS
# ══════════════════════════════════════════════════════════
with tab1:
    drivers = sorted({fp.driver_code for fp in all_fps})
    idx = drivers.index("ANT") if "ANT" in drivers else 0
    driver = st.selectbox(
        "Driver",
        drivers,
        index=idx,
        format_func=lambda d: f"{driver_name(d)}  ({d})",
    )

    # Round-aware identity is essential during substitutions. Stored R12/R13
    # fingerprints can legitimately say LAW=Red Bull / TSU=VCARB even though
    # the base season roster in CARS differs.
    info = driver_info(driver, latest_round)
    team = info.get("team", "—")
    team_col = TEAM_COLOURS.get(team, "#888")
    pu_col = PU_COLOURS.get(info.get("pu", ""), "#888")
    teammate = get_teammate(driver, latest_round)
    stats = driver_season_stats(all_fps, driver)

    left, right = st.columns([1, 2.4])
    with left:
        st.markdown(
            f"""
        <div style="padding:16px 18px;background:#1A1A1A;border-radius:10px;
                    border-left:5px solid {team_col};margin-bottom:14px;">
            <div style="font-family:monospace;font-size:2rem;font-weight:bold;
                        color:{team_col};line-height:1;">#{info.get('number','')}</div>
            <div style="font-family:monospace;font-size:1.05rem;color:#E0E0E0;
                        margin-top:6px;">{driver_name(driver)}</div>
            <div style="color:{team_col};font-family:monospace;font-size:0.85rem;">{team}</div>
            <div style="color:{pu_col};font-family:monospace;font-size:0.75rem;">
                {info.get('pu','—')} PU</div>
            {'<div style="color:#777;font-family:monospace;font-size:0.72rem;margin-top:6px;">vs ' + driver_name(teammate) + '</div>' if teammate else ''}
        </div>""",
            unsafe_allow_html=True,
        )
        a, b = st.columns(2)
        a.metric("Wins", stats["wins"])
        b.metric("Podiums", stats["podiums"])
        a.metric("Poles", stats["poles"])
        b.metric("DNFs", stats["dnfs"])
        avg = stats["avg_finish"]
        st.metric(
            "Avg Finish",
            f"P{avg:.1f}" if avg else "—",
            help=(
                "Classified finishes only — DNF and NC excluded, since a "
                "retirement says nothing about finishing pace."
            ),
        )
        st.metric(
            "Best Finish",
            f"P{stats['best_finish']}" if stats["best_finish"] else "—",
        )
        if stats["avg_q_gap"] is not None:
            st.metric(
                "Avg Q Gap",
                f"{stats['avg_q_gap']:.3f}%",
                help="Average gap to pole across Grand Prix Qualifying sessions only.",
            )
        st.caption(
            f"{stats['classified']} classified · {stats['dnfs']} DNF"
            + (f" · {stats['ncs']} NC" if stats["ncs"] else "")
        )

    with right:
        st.plotly_chart(pace_trend_chart(all_fps, driver), use_container_width=True)
        if stats["finish_history"]:
            st.plotly_chart(
                finish_history_chart(stats["finish_history"], driver, team_col),
                use_container_width=True,
            )

    st.markdown("---")
    st.subheader("🤝 Teammate Comparison")
    if not teammate:
        st.info("No active teammate on record for the latest stored round.")
    else:
        ts = teammate_stats(all_fps, driver, teammate)
        if ts["total"] == 0:
            st.info(f"No common same-team qualifying sessions with {driver_name(teammate)}.")
        else:
            faster = ts["med_gap_s"] < 0
            col_ind = "#00C851" if faster else "#FF4444"
            st.markdown(
                f"""
            <div style="padding:14px 18px;background:#1A1A1A;border-radius:10px;
                        border-left:5px solid {team_col};margin-bottom:12px;">
              <div style="font-family:monospace;font-size:0.78rem;color:#888;">
                {driver_name(driver)} vs {driver_name(teammate)} · Qualifying</div>
              <div style="font-family:monospace;font-size:1.35rem;font-weight:bold;
                          color:{team_col};margin:5px 0;">
                {ts['d1_wins']}/{ts['total']} sessions faster</div>
              <div style="font-family:monospace;font-size:0.92rem;">
                <span style="color:{col_ind};font-weight:bold;">
                  {'FASTER' if faster else 'SLOWER'}</span>
                &nbsp;by {abs(ts['med_gap_s']):.3f}s ({abs(ts['med_gap_pct']):.3f}%) median
              </div>
            </div>""",
                unsafe_allow_html=True,
            )
            st.caption(
                f"Overall Q + SQ H2H: {ts['sessions']} shared qualifying session(s) "
                f"across {ts['weekends']} weekend(s)."
                + (" Limited sample." if ts["weekends"] < 3 else "")
            )
            st.plotly_chart(
                teammate_gap_chart(all_fps, driver, teammate, circuit_map, team_col),
                use_container_width=True,
            )

    st.markdown("---")
    st.subheader("⏱️ Season Qualifying Ranking")
    st.caption("Every driver ranked by average gap to pole in Grand Prix Qualifying (Q) only.")
    st.plotly_chart(
        qualifying_ranking_chart(qualifying_ranking(all_fps)),
        use_container_width=True,
    )

# ══════════════════════════════════════════════════════════
# TEAMS
# ══════════════════════════════════════════════════════════
with tab2:
    fps_q = [fp for fp in all_fps if fp.session_type == "Q"]

    st.subheader("📍 Performance Profile: Straight vs Corner")
    st.caption("All 11 teams · dot size = rounds of data · colour = team")
    st.plotly_chart(straight_vs_corner_scatter(fps_q), use_container_width=True)

    st.markdown("---")
    st.subheader("🔄 Corner Performance by Speed Class")
    fig_cc, suppressed = corner_class_ranking(all_fps)
    if suppressed:
        names = {
            "slow": "slow (<130 kph)",
            "medium": "medium (130–210)",
            "fast": "fast (>210)",
        }
        st.warning(
            f"**{', '.join(names[s] for s in suppressed)}** corners are not shown — "
            "too few detected across the season for a reliable ranking. Corner detection "
            "is throttle/brake based, so flat-out corners are invisible to it and fast "
            "corners are systematically under-sampled."
        )
    if fig_cc.data:
        st.plotly_chart(fig_cc, use_container_width=True)
        st.caption(
            "Season aggregate across all qualifying sessions — not per-circuit "
            "counts, which would be unreliable for the reason above."
        )

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🏁 Corner Ranking (Overall)")
        st.plotly_chart(corner_profile_ranking(fps_q), use_container_width=True)
    with c2:
        st.subheader("📊 Overall Pace Ranking")
        pace = {}
        for fp in fps_q:
            if fp.confidence < 0.5:
                continue
            pace.setdefault(fp.team, {"gaps": [], "pu": fp.pu_name})["gaps"].append(
                fp.lap_time_gap_pct
            )
        rows = [
            {
                "Pos": i,
                "Team": team,
                "PU": data["pu"],
                "Median Gap %": round(float(np.median(data["gaps"])), 3),
                "Best %": round(min(data["gaps"]), 3),
                "Sessions": len(data["gaps"]),
            }
            for i, (team, data) in enumerate(
                sorted(pace.items(), key=lambda item: np.median(item[1]["gaps"])), 1
            )
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🤝 Intra-Team Qualifying Battle")
    st.caption(
        "Overall Q + SQ battle across every teammate pairing used this season. "
        "Lineup changes create a new row rather than erasing the earlier H2H; "
        "session and weekend counts show the sample behind each comparison."
    )
    overall_changes = teammate_season_overall(all_fps)
    if overall_changes:
        st.markdown("**Season H2H across lineup changes**")
        st.caption(
            "For teams that changed one seat, this keeps the long-term driver's full "
            "Q + SQ head-to-head across every teammate they faced. Median gaps stay in "
            "the pairing breakdown below because mixing different opponents would be misleading."
        )
        st.dataframe(
            pd.DataFrame([
                {
                    "Team": r["team"],
                    "Driver": f"{r['driver']} ({driver_name(r['driver'])})",
                    "Teammates faced": ", ".join(r["opponents"]),
                    "Overall H2H": f"{r['wins']}–{r['losses']}",
                    "Sessions": r["sessions"],
                    "Weekends": r["weekends"],
                    "Rounds": r["round_label"],
                }
                for r in overall_changes
            ]),
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("")

    tr = teammate_ranking(all_fps)
    if tr:
        st.plotly_chart(teammate_hierarchy_chart(tr), use_container_width=True)
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Team": r["team"],
                        "Pairing": f"{r['driver1']} vs {r['driver2']}",
                        "Faster": f"{r['faster']} ({driver_name(r['faster'])})",
                        "Margin": f"{r['gap_s']:.3f}s",
                        "Margin %": f"{r['gap_pct']:.3f}%",
                        "H2H": f"{r['faster_wins']}–{r['slower_wins']}",
                        "Sessions": r["sessions"],
                        "Weekends": r["weekends"],
                        "Rounds": r["round_label"],
                        "Era": "Current" if r["current_pairing"] else "Earlier",
                        "Sample": "Limited" if r["limited_sample"] else "Established",
                    }
                    for r in tr
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

# ══════════════════════════════════════════════════════════
# POWER UNITS
# ══════════════════════════════════════════════════════════
with tab3:
    st.markdown("### ⚡ Power Unit Analysis")
    st.caption(
        "Factory teams only. These signals combine PU output with chassis "
        "effects — they are **not** ICE-only measurements."
    )

    fps_r = [fp for fp in all_fps if fp.session_type == "R"]
    fps_qh = [fp for fp in all_fps if fp.session_type in ("Q", "SQ")]
    st.plotly_chart(pu_straight_speed_chart(fps_qh), use_container_width=True)

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**ERS Fingerprint**")
        st.plotly_chart(fingerprint_radar_chart(fps_r), use_container_width=True)
    with c2:
        st.markdown("**Braking Harvest Efficiency**")
        st.caption(
            "Qualifying only — race harvest ratios are unreliable because "
            "each driver's reference lap comes from different conditions."
        )
        st.plotly_chart(
            harvest_bars_chart(fps_qh, sessions=["Q", "SQ"]),
            use_container_width=True,
        )

    st.markdown("---")
    st.markdown("**ADUO ICE Performance Bands**")
    st.caption(
        "ADUO applies to the internal combustion engine only. It does not measure "
        "battery state, energy recovery or deployment. Deployment counts below "
        "come directly from the canonical PU configuration."
    )
    st.dataframe(
        pd.DataFrame(get_pu_aduo_summary()),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "*The published bands do not establish an exact order inside the >4% group, "
        "so LatentLap does not claim one."
    )
