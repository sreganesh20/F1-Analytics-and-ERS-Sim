"""pages/3_Teams_and_Drivers.py — LatentLap · full-season team, driver and PU analysis."""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (
    PU_COLOURS,
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
from app.ui import inject_global_css, page_header, section_header


st.set_page_config(
    page_title="Teams & Drivers — LatentLap",
    page_icon="🏎️",
    layout="wide",
)
inject_global_css()


all_fps = get_fingerprints()
if not all_fps:
    st.warning("No fingerprint data in store.")
    st.stop()

circuit_map = get_circuits_with_data()
latest_round = current_round()

page_header(
    "Season performance",
    "Teams & Drivers",
    "Full-season pace, teammate battles, driver form and power-unit signals. The redesign changes how the analysis is organised — not how much of it you can see.",
)

teams_tab, teammates_tab, drivers_tab, pu_tab = st.tabs(
    ["Teams", "Teammates", "Drivers", "Power Units"]
)

# ============================================================
# TEAMS
# ============================================================
with teams_tab:
    fps_q = [
        fp
        for fp in all_fps
        if fp.session_type == "Q"
    ]

    section_header(
        "Performance profile",
        "Straight-line vs corner performance",
        "All teams across the full season. Dot size reflects available rounds and each team keeps its own colour.",
    )
    st.plotly_chart(
        straight_vs_corner_scatter(fps_q),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    section_header(
        "Corner profile",
        "Corner performance by speed class",
        "Season aggregate from Grand Prix qualifying. The corner metric remains approximate because flat-out corners can be under-detected.",
    )
    fig_cc, suppressed = corner_class_ranking(all_fps)

    if suppressed:
        names = {
            "slow": "slow (<130 kph)",
            "medium": "medium (130–210 kph)",
            "fast": "fast (>210 kph)",
        }
        st.warning(
            f"{', '.join(names[s] for s in suppressed)} not shown due to insufficient "
            "detected samples. Flat-out corners remain systematically under-sampled."
        )

    if fig_cc.data:
        st.plotly_chart(
            fig_cc,
            use_container_width=True,
            config={"displayModeBar": False},
        )

    section_header(
        "Season ranking",
        "Corner pace + overall qualifying pace",
        "These views use the complete stored season, not only the last few rounds.",
    )

    left, right = st.columns(2, gap="large")

    with left:
        st.markdown("### Overall corner ranking")
        st.plotly_chart(
            corner_profile_ranking(fps_q),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    with right:
        st.markdown("### Overall qualifying pace")
        pace = {}
        for fp in fps_q:
            if fp.confidence < 0.5:
                continue
            pace.setdefault(
                fp.team,
                {"gaps": [], "pu": fp.pu_name},
            )["gaps"].append(fp.lap_time_gap_pct)

        rows = [
            {
                "Pos": pos,
                "Team": team,
                "PU": data["pu"],
                "Median gap %": round(
                    float(np.median(data["gaps"])),
                    3,
                ),
                "Best %": round(min(data["gaps"]), 3),
                "Sessions": len(data["gaps"]),
            }
            for pos, (team, data) in enumerate(
                sorted(
                    pace.items(),
                    key=lambda item: np.median(item[1]["gaps"]),
                ),
                1,
            )
        ]

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )

    st.caption(
        "Team colours are preserved in the comparative plots. Overall pace remains a "
        "Grand Prix qualifying benchmark; standings are deliberately not used to rank car pace."
    )


# ============================================================
# TEAMMATES
# ============================================================
with teammates_tab:
    section_header(
        "Season H2H",
        "Teammate battles across every lineup era",
        "Q + SQ sessions only. If a team changed drivers, each actual pairing remains separate instead of overwriting earlier evidence.",
    )

    overall_changes = teammate_season_overall(all_fps)

    if overall_changes:
        st.markdown("### Overall record across lineup changes")
        st.caption(
            "This preserves a driver's complete H2H across all teammates faced. "
            "Median gaps stay pairing-specific because mixing different opponents would be misleading."
        )

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Team": row["team"],
                        "Driver": f"{row['driver']} · {driver_name(row['driver'])}",
                        "Teammates faced": ", ".join(row["opponents"]),
                        "Overall H2H": f"{row['wins']}–{row['losses']}",
                        "Sessions": row["sessions"],
                        "Weekends": row["weekends"],
                        "Rounds": row["round_label"],
                    }
                    for row in overall_changes
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    ranking = teammate_ranking(all_fps)

    if ranking:
        st.markdown("### Pairing hierarchy")
        st.plotly_chart(
            teammate_hierarchy_chart(ranking),
            use_container_width=True,
            config={"displayModeBar": False},
        )

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Team": row["team"],
                        "Pairing": f"{row['driver1']} vs {row['driver2']}",
                        "Faster": (
                            f"{row['faster']} · "
                            f"{driver_name(row['faster'])}"
                        ),
                        "Median margin": f"{row['gap_s']:.3f}s",
                        "Margin %": f"{row['gap_pct']:.3f}%",
                        "H2H": (
                            f"{row['faster_wins']}–"
                            f"{row['slower_wins']}"
                        ),
                        "Sessions": row["sessions"],
                        "Weekends": row["weekends"],
                        "Rounds": row["round_label"],
                        "Era": (
                            "Current"
                            if row["current_pairing"]
                            else "Earlier"
                        ),
                        "Sample": (
                            "Limited"
                            if row["limited_sample"]
                            else "Established"
                        ),
                    }
                    for row in ranking
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No same-team qualifying comparisons are available.")

    st.markdown(
        """
<div class="ll-ai-hook">
    <div>
        <strong>Ask about a teammate battle</strong>
        <span>Ask the Engineer can explain the evidence behind a current or earlier pairing without collapsing different lineup eras together.</span>
    </div>
    <a class="ll-cta ll-cta-primary" href="/Ask_the_Engineer" target="_self">Ask the Engineer</a>
</div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# DRIVERS
# ============================================================
with drivers_tab:
    drivers = sorted(
        {fp.driver_code for fp in all_fps},
        key=lambda code: driver_name(code, latest_round),
    )
    default_idx = drivers.index("ANT") if "ANT" in drivers else 0

    driver = st.selectbox(
        "Driver",
        drivers,
        index=default_idx,
        format_func=lambda code: (
            f"{code} · {driver_name(code, latest_round)}"
        ),
    )

    info = driver_info(driver, latest_round)
    team = info.get("team", "—")
    team_colour = TEAM_COLOURS.get(team, "#888888")
    pu_colour = PU_COLOURS.get(info.get("pu", ""), "#888888")
    teammate = get_teammate(driver, latest_round)
    stats = driver_season_stats(all_fps, driver)

    st.markdown(
        f"""
<div style="
    border:1px solid rgba(255,255,255,0.10);
    border-left:5px solid {team_colour};
    border-radius:14px;
    padding:18px 20px;
    margin:10px 0 18px;
    background:rgba(15,21,29,0.78);
">
    <div style="font-size:0.78rem;letter-spacing:0.12em;text-transform:uppercase;color:{team_colour};font-weight:800;">
        #{info.get('number', '')} · {driver}
    </div>
    <div style="font-size:1.65rem;font-weight:800;margin-top:4px;">
        {driver_name(driver, latest_round)}
    </div>
    <div style="margin-top:5px;color:{team_colour};font-weight:700;">
        {team}
    </div>
    <div style="font-size:0.92rem;margin-top:2px;color:{pu_colour};">
        {info.get('pu', '—')} power unit
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    s1, s2, s3, s4, s5 = st.columns(5, gap="medium")
    s1.metric("Wins", stats["wins"])
    s2.metric("Podiums", stats["podiums"])
    s3.metric("Poles", stats["poles"])
    s4.metric("DNFs", stats["dnfs"])
    s5.metric(
        "Avg Q gap",
        (
            f"{stats['avg_q_gap']:.3f}%"
            if stats["avg_q_gap"] is not None
            else "—"
        ),
    )

    section_header(
        "Full season",
        "2026 pace trend",
        "Grand Prix qualifying and representative Grand Prix pace are shown separately across every stored round. This is the complete season view.",
    )

    st.plotly_chart(
        pace_trend_chart(all_fps, driver),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    if stats["finish_history"]:
        st.plotly_chart(
            finish_history_chart(
                stats["finish_history"],
                driver,
                team_colour,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    if teammate:
        section_header(
            "Teammate",
            f"{driver} vs {teammate}",
            "All shared same-team Q + SQ sessions for the active pairing.",
        )

        ts = teammate_stats(
            all_fps,
            driver,
            teammate,
        )

        if ts["total"] > 0:
            h1, h2, h3 = st.columns(3, gap="medium")
            h1.metric(
                "H2H",
                f"{ts['d1_wins']}–{ts['d2_wins']}",
                f"{ts['sessions']} sessions",
            )
            h2.metric(
                "Median gap",
                f"{abs(ts['med_gap_s']):.3f}s",
                (
                    f"{driver} faster"
                    if ts["med_gap_s"] < 0
                    else f"{driver} slower"
                ),
            )
            h3.metric(
                "Weekends",
                ts["weekends"],
                (
                    "Limited sample"
                    if ts["weekends"] < 3
                    else None
                ),
            )

            st.plotly_chart(
                teammate_gap_chart(
                    all_fps,
                    driver,
                    teammate,
                    circuit_map,
                    team_colour,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        else:
            st.info(
                f"No common same-team Q/SQ sessions with "
                f"{driver_name(teammate, latest_round)}."
            )

    section_header(
        "Field context",
        "Season qualifying ranking",
        "Every driver ranked by average gap to the session reference in Grand Prix qualifying only.",
    )

    st.plotly_chart(
        qualifying_ranking_chart(
            qualifying_ranking(all_fps)
        ),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    st.caption(
        f"{stats['classified']} classified GP finishes · "
        f"{stats['dnfs']} DNF"
        + (f" · {stats['ncs']} NC" if stats["ncs"] else "")
    )


# ============================================================
# POWER UNITS
# ============================================================
with pu_tab:
    section_header(
        "Power units",
        "Power Unit Analysis",
        "Factory-team telemetry signals only. These combine PU output with chassis and aero effects, so they are not ICE-only measurements.",
    )

    fps_r = [
        fp
        for fp in all_fps
        if fp.session_type == "R"
    ]
    fps_qh = [
        fp
        for fp in all_fps
        if fp.session_type in ("Q", "SQ")
    ]

    st.markdown("### Straight-line speed signal")
    st.plotly_chart(
        pu_straight_speed_chart(fps_qh),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    section_header(
        "ERS / harvesting",
        "Fingerprint + braking-harvest proxy",
        "These are model-derived signals. They do not expose true electrical efficiency, battery state or exact deployment.",
    )

    left, right = st.columns(2, gap="large")

    with left:
        st.markdown("### ERS fingerprint")
        st.plotly_chart(
            fingerprint_radar_chart(fps_r),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    with right:
        st.markdown("### Braking harvest behaviour")
        st.caption(
            "Qualifying only. Race harvest ratios are not used because representative race laps occur under different conditions."
        )
        st.plotly_chart(
            harvest_bars_chart(
                fps_qh,
                sessions=["Q", "SQ"],
            ),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    section_header(
        "ADUO",
        "ICE performance bands",
        "ADUO applies to the internal-combustion engine only. It does not measure battery state, energy recovery or deployment.",
    )

    st.dataframe(
        pd.DataFrame(get_pu_aduo_summary()),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Published bands do not establish an exact order inside the >4% group, so LatentLap does not claim one."
    )

    st.markdown(
        """
<div class="ll-ai-hook">
    <div>
        <strong>Ask about the PU or ERS evidence</strong>
        <span>Ask the Engineer can explain what these signals mean, what is inferred and what LatentLap cannot observe directly.</span>
    </div>
    <a class="ll-cta ll-cta-primary" href="/Ask_the_Engineer" target="_self">Ask the Engineer</a>
</div>
        """,
        unsafe_allow_html=True,
    )
