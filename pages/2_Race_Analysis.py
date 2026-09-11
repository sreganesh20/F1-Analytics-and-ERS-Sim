"""pages/2_Race_Analysis.py — LatentLap · session story with driver/team drill-down."""

from __future__ import annotations

import html
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (
    TEAM_COLOURS,
    driver_name,
    fmt_laptime,
    get_circuits_with_data,
    get_fingerprints,
    get_session_results,
    get_sessions_for_round,
    get_stint_data,
    race_highlights,
    safe_delta,
)
from app.ui import inject_global_css, page_header, section_header
from config import lineup_for_round
from data.race_knowledge import load_dossier


st.set_page_config(
    page_title="Race Analysis — LatentLap",
    page_icon="📊",
    layout="wide",
)
inject_global_css()


SESSION_LABELS = {
    "Q": "Qualifying",
    "SQ": "Sprint Qualifying",
    "R": "Race",
    "S": "Sprint",
}
SESSION_ORDER = {"SQ": 0, "S": 1, "Q": 2, "R": 3}


def _status_finished(status: str) -> bool:
    if not status:
        return True
    s = str(status).strip().lower()
    return (
        s in {"finished", "lapped", "classified"}
        or s.startswith("finished")
        or s.startswith("+")
    )


def _dossier(round_num: int) -> dict:
    return (
        load_dossier(
            round_num,
            approved_only=True,
            hydrate_snapshot=False,
        )
        or {}
    )


def _session_story(dossier: dict, session: str, ref) -> str:
    summary = dossier.get("sessions", {}).get(session, {}).get("summary")
    if summary:
        return summary

    if session in ("Q", "SQ"):
        return (
            f"{ref.driver_code} set the session reference at {fmt_laptime(ref.lap_time_s)}. "
            "Every valid pace gap on this page uses that same car as the reference."
        )

    return (
        f"{ref.driver_code} produced the fastest representative race-pace sample. "
        "That describes underlying pace only; it is not the race classification."
    )


def _team_for_code(code: str, fp_map: dict, lineup: dict) -> str:
    fp = fp_map.get(code)
    if fp is not None:
        return fp.team
    return lineup.get(code, {}).get("team", "Unknown")


def _driver_story(
    dossier: dict,
    code: str,
    session: str,
    fp,
    result: dict,
) -> str:
    insight = dossier.get("driver_insights", {}).get(code, {})
    summary = insight.get("summary")
    if summary:
        return summary

    if session in ("Q", "SQ"):
        if fp is None:
            return "No valid analytical qualifying fingerprint is stored for this driver."
        return (
            f"{code} ranked P{fp.lap_time_rank} on the stored pace view, "
            f"{fp.lap_time_gap_pct:.3f}% from the session-fastest reference."
        )

    status = result.get("result_status", "") or (
        getattr(fp, "result_status", "") if fp is not None else ""
    )
    finish = result.get("finishing_position")
    if finish is not None:
        result_text = f"finished P{finish}"
    elif status:
        result_text = status
    else:
        result_text = "has no classified result in the stored roster"

    if fp is None:
        return (
            f"{code} {result_text}. No valid representative pace sample was available, "
            "so LatentLap leaves underlying pace blank."
        )

    return (
        f"{code} {result_text} and ranked P{fp.lap_time_rank} on the stored "
        "representative race-pace view. Result and pace are deliberately kept separate."
    )


def _team_story(dossier: dict, team: str, rank: int | None, gap: float | None) -> str:
    summary = dossier.get("team_insights", {}).get(team, {}).get("summary")
    if summary:
        return summary

    if rank is None or gap is None:
        return "No team-level analytical pace summary is available for this session."

    return (
        f"{team} ranks P{rank} on the session team-pace view at "
        f"{gap:.3f}% from the session reference."
    )


def _team_pace_rows(fps: list) -> list[dict]:
    grouped = defaultdict(list)
    for fp in fps:
        if fp.lap_time_gap_pct is not None:
            grouped[fp.team].append(float(fp.lap_time_gap_pct))

    rows = [
        {
            "team": team,
            "gap": float(np.median(gaps)),
            "cars": len(gaps),
        }
        for team, gaps in grouped.items()
    ]
    return sorted(rows, key=lambda row: row["gap"])


def _team_rank(team: str, rows: list[dict]):
    for idx, row in enumerate(rows, start=1):
        if row["team"] == team:
            return idx, row
    return None, None


def _team_dot_plot(rows: list[dict], selected_team: str, is_race: bool):
    if not rows:
        return None

    ordered = list(reversed(rows))
    teams = [row["team"] for row in ordered]
    gaps = [row["gap"] for row in ordered]

    colours = [
        TEAM_COLOURS.get(team, "#E10600")
        if team == selected_team
        else "#596474"
        for team in teams
    ]
    sizes = [15 if team == selected_team else 9 for team in teams]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=gaps,
            y=teams,
            mode="markers",
            marker=dict(
                color=colours,
                size=sizes,
                line=dict(width=0),
            ),
            text=[f"{gap:.3f}%" for gap in gaps],
            hovertemplate="%{y}<br>%{x:.3f}% off reference<extra></extra>",
        )
    )

    fig.update_layout(
        height=340,
        margin=dict(l=10, r=40, t=10, b=45),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d7dde6", size=14),
        xaxis=dict(
            title=(
                "Median representative race-pace gap (%)"
                if is_race
                else "Median qualifying gap to session-fastest (%)"
            ),
            gridcolor="rgba(255,255,255,0.07)",
            zerolinecolor="rgba(225,6,0,0.55)",
            rangemode="tozero",
        ),
        yaxis=dict(title=None),
        showlegend=False,
    )
    return fig


def _teammate_codes(
    selected_code: str,
    selected_team: str,
    fp_map: dict,
    results: dict,
    lineup: dict,
) -> list[str]:
    codes = set(fp_map) | set(results)
    return sorted(
        code
        for code in codes
        if code != selected_code
        and _team_for_code(code, fp_map, lineup) == selected_team
    )


def _teammate_delta(selected_fp, teammate_fp) -> str:
    if selected_fp is None or teammate_fp is None:
        return "No comparable pace sample"
    delta = float(selected_fp.lap_time_s) - float(teammate_fp.lap_time_s)
    if abs(delta) < 0.0005:
        return "Level on stored pace"
    if delta < 0:
        return f"{abs(delta):.3f}s quicker"
    return f"{abs(delta):.3f}s slower"


def _fmt_speed_delta(value) -> str:
    value = safe_delta(value)
    if value is None:
        return "—"
    return f"{float(value):+.1f} km/h"


def _driver_stint_df(code: str, stints: dict) -> pd.DataFrame:
    rows = []
    for stint in stints.get(code, []):
        trend = stint.get("degradation_rate")
        rows.append(
            {
                "Stint": stint.get("stint"),
                "Compound": stint.get("compound"),
                "Retained laps": stint.get("stint_length"),
                "Average pace": fmt_laptime(stint.get("avg_pace")),
                "Pace trend s/lap": (
                    round(float(trend), 4)
                    if trend is not None
                    else None
                ),
            }
        )
    return pd.DataFrame(rows)


def _full_field_df(
    fps: list,
    results: dict,
    lineup: dict,
    round_num: int,
    is_race: bool,
) -> pd.DataFrame:
    fp_map = {fp.driver_code: fp for fp in fps}

    if is_race:
        codes = list(results) if results else list(fp_map)

        def result_key(code):
            pos = results.get(code, {}).get("finishing_position")
            return (pos is None, pos if pos is not None else 999, code)

        codes = sorted(codes, key=result_key)
        codes.extend(code for code in fp_map if code not in codes)

        rows = []
        for code in codes:
            fp = fp_map.get(code)
            result = results.get(code, {})
            status = result.get("result_status", "") or (
                getattr(fp, "result_status", "") if fp else ""
            )
            grid = result.get("grid_position")
            finish = result.get("finishing_position")

            rows.append(
                {
                    "Finish": finish,
                    "Driver": f"{code} · {driver_name(code, round_num)}",
                    "Team": _team_for_code(code, fp_map, lineup),
                    "Grid": grid,
                    "+/-": (
                        grid - finish
                        if grid is not None and finish is not None
                        else None
                    ),
                    "Pace rank": fp.lap_time_rank if fp else None,
                    "Representative pace": (
                        fmt_laptime(fp.lap_time_s) if fp else "—"
                    ),
                    "Gap %": (
                        round(float(fp.lap_time_gap_pct), 3)
                        if fp is not None and fp.lap_time_gap_pct is not None
                        else None
                    ),
                    "Status": "Finished" if _status_finished(status) else (status or "DNF"),
                }
            )
        return pd.DataFrame(rows)

    rows = []
    for fp in sorted(fps, key=lambda f: f.lap_time_s):
        rows.append(
            {
                "Pace": fp.lap_time_rank,
                "Driver": f"{fp.driver_code} · {driver_name(fp.driver_code, round_num)}",
                "Team": fp.team,
                "Best lap": fmt_laptime(fp.lap_time_s),
                "Gap %": round(float(fp.lap_time_gap_pct), 3),
                "Straight Δ": safe_delta(fp.straight_speed_delta_kph),
                "Corner Δ": safe_delta(fp.corner_speed_delta_kph),
                "Harvest": (
                    round(float(fp.braking_harvest_ratio), 3)
                    if fp.braking_harvest_ratio is not None
                    else None
                ),
            }
        )
    return pd.DataFrame(rows)


page_header(
    "Weekend analysis",
    "Race Analysis",
    "Start with the session story, then inspect a driver or team. The full field stays available without dominating the page.",
)

circuit_map = get_circuits_with_data()
if not circuit_map:
    st.warning("No session data in store. Run the pipeline locally first.")
    st.stop()

round_options = {
    f"R{round_num} — {circuit_map[round_num]}": round_num
    for round_num in sorted(circuit_map)
}

select_a, select_b = st.columns([1.2, 1], gap="large")
with select_a:
    round_label = st.selectbox(
        "Round",
        list(round_options.keys()),
        index=len(round_options) - 1,
    )
selected_round = round_options[round_label]

available = sorted(
    get_sessions_for_round(selected_round),
    key=lambda session: SESSION_ORDER.get(session, 99),
)
if not available:
    st.info("No sessions loaded for this round.")
    st.stop()

default_session = "R" if "R" in available else available[-1]
with select_b:
    session = st.selectbox(
        "Session",
        available,
        index=available.index(default_session),
        format_func=lambda code: SESSION_LABELS.get(code, code),
    )

all_fps = get_fingerprints()
fps = [
    fp
    for fp in all_fps
    if fp.race_round == selected_round and fp.session_type == session
]
if not fps:
    st.info(f"No analytical data for {SESSION_LABELS.get(session, session)}.")
    st.stop()

is_race = session in ("R", "S")
ranked = sorted(fps, key=lambda fp: fp.lap_time_s)
ref = ranked[0]
fp_map = {fp.driver_code: fp for fp in fps}
results = get_session_results(selected_round, session) if is_race else {}
stints = get_stint_data(selected_round, session) if is_race else {}
lineup = lineup_for_round(selected_round)
dossier = _dossier(selected_round)
field_count = len(results) if results else len(fps)

st.caption(
    f"R{selected_round} · {circuit_map[selected_round]} · "
    f"{SESSION_LABELS.get(session, session)} · "
    f"{ref.circuit_type.replace('_', ' ').title()} circuit"
)

story = _session_story(dossier, session, ref)
with st.container(border=True):
    st.markdown("### Session story")
    st.write(story)

if is_race:
    highlights = race_highlights(fps)

    dnf_count = (
        sum(
            1
            for row in results.values()
            if not _status_finished(row.get("result_status", ""))
        )
        if results
        else highlights.get("dnf_count", 0)
    )

    fastest = highlights.get("fastest_lap")
    sectors = highlights.get("sectors") or {}

    gained_rows = [
        (row.get("positions_gained"), code, row)
        for code, row in results.items()
        if row.get("positions_gained") is not None
    ]
    if gained_rows:
        gained, gained_code, gained_row = max(
            gained_rows,
            key=lambda item: item[0],
        )
    else:
        gained, gained_code, gained_row = None, None, {}

    st.markdown("### Race highlights")
    h1, h2, h3, h4 = st.columns(4, gap="medium")

    with h1:
        with st.container(border=True):
            st.caption("FASTEST LAP")
            if fastest:
                st.markdown(f"### {fastest['driver']}")
                lap_note = f" · Lap {fastest['lap']}" if fastest.get("lap") else ""
                st.write(f"{fmt_laptime(fastest['time_s'])}{lap_note}")
            else:
                st.markdown("### —")
                st.write("No stored fastest lap")

    with h2:
        with st.container(border=True):
            st.caption("FASTEST SECTORS")
            for sector in ("S1", "S2", "S3"):
                info = sectors.get(sector)
                if info:
                    st.markdown(
                        f"**{sector}** &nbsp; {info['driver']} &nbsp; "
                        f"`{float(info['time_s']):.3f}s`"
                    )
                else:
                    st.markdown(f"**{sector}** &nbsp; —")

    with h3:
        with st.container(border=True):
            st.caption("MOST PLACES GAINED")
            if gained is not None and gained > 0:
                st.markdown(f"### {gained_code}")
                st.write(
                    f"+{gained} · P{gained_row.get('grid_position')} → "
                    f"P{gained_row.get('finishing_position')}"
                )
            else:
                st.markdown("### —")
                st.write("No positive mover stored")

    with h4:
        with st.container(border=True):
            st.caption("ATTRITION")
            st.markdown(f"### {dnf_count} DNF")
            st.write(f"{field_count} starters · {len(fps)} pace samples")


driver_tab, team_tab, field_tab = st.tabs(
    ["Driver analysis", "Team analysis", "Full field"]
)

# ── DRIVER TAB ────────────────────────────────────────────────────────────
with driver_tab:
    driver_codes = set(fp_map) | set(results)

    if is_race and results:
        def driver_sort(code):
            pos = results.get(code, {}).get("finishing_position")
            return (pos is None, pos if pos is not None else 999, code)
        driver_options = sorted(driver_codes, key=driver_sort)
    else:
        driver_options = [
            fp.driver_code
            for fp in sorted(fps, key=lambda fp: fp.lap_time_s)
        ]

    selected_code = st.selectbox(
        "Driver",
        driver_options,
        key="race_analysis_driver",
        format_func=lambda code: (
            f"{code} · {driver_name(code, selected_round)} · "
            f"{_team_for_code(code, fp_map, lineup)}"
        ),
    )

    selected_fp = fp_map.get(selected_code)
    selected_result = results.get(selected_code, {})
    selected_team = _team_for_code(selected_code, fp_map, lineup)

    st.markdown(
        f"## {selected_code} · {driver_name(selected_code, selected_round)}"
    )
    st.caption(selected_team)

    driver_story = _driver_story(
        dossier,
        selected_code,
        session,
        selected_fp,
        selected_result,
    )
    st.write(driver_story)

    teammates = _teammate_codes(
        selected_code,
        selected_team,
        fp_map,
        results,
        lineup,
    )
    teammate_code = teammates[0] if teammates else None
    teammate_fp = fp_map.get(teammate_code) if teammate_code else None
    teammate_text = _teammate_delta(selected_fp, teammate_fp)

    m1, m2, m3, m4 = st.columns(4, gap="medium")

    if is_race:
        finish = selected_result.get("finishing_position")
        grid = selected_result.get("grid_position")
        status = selected_result.get("result_status", "") or (
            getattr(selected_fp, "result_status", "") if selected_fp else ""
        )
        move = (
            grid - finish
            if grid is not None and finish is not None
            else None
        )

        with m1:
            st.metric(
                "Result",
                f"P{finish}" if finish is not None else (status or "—"),
            )
        with m2:
            st.metric(
                "Grid",
                f"P{grid}" if grid is not None else "—",
                f"{move:+d} positions" if move is not None else None,
            )
        with m3:
            st.metric(
                "Underlying pace",
                f"P{selected_fp.lap_time_rank}" if selected_fp else "No sample",
                (
                    f"{selected_fp.lap_time_gap_pct:.3f}% off reference"
                    if selected_fp
                    else None
                ),
            )
        with m4:
            st.metric(
                "Teammate",
                teammate_code or "—",
                teammate_text,
            )

        st.markdown("#### Stint context")
        driver_stints = _driver_stint_df(selected_code, stints)
        if not driver_stints.empty:
            st.dataframe(
                driver_stints,
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "Pace trend is a fitted lap-time slope, not pure tyre degradation. "
                "Fuel burn, traffic, track evolution and management can contribute."
            )
        else:
            st.info(
                "No valid filtered stint sample is stored for this driver. "
                "LatentLap leaves it blank rather than fabricating stint pace."
            )

    else:
        with m1:
            st.metric(
                "Pace rank",
                f"P{selected_fp.lap_time_rank}" if selected_fp else "—",
            )
        with m2:
            st.metric(
                "Gap to reference",
                (
                    f"{selected_fp.lap_time_gap_pct:.3f}%"
                    if selected_fp
                    else "—"
                ),
            )
        with m3:
            st.metric(
                "Best lap",
                fmt_laptime(selected_fp.lap_time_s) if selected_fp else "—",
            )
        with m4:
            st.metric(
                "Teammate",
                teammate_code or "—",
                teammate_text,
            )

        st.markdown("#### Telemetry fingerprint")
        q1, q2, q3 = st.columns(3, gap="medium")
        with q1:
            st.metric(
                "Straight Δ",
                _fmt_speed_delta(
                    selected_fp.straight_speed_delta_kph
                    if selected_fp
                    else None
                ),
            )
        with q2:
            st.metric(
                "Corner Δ",
                _fmt_speed_delta(
                    selected_fp.corner_speed_delta_kph
                    if selected_fp
                    else None
                ),
            )
        with q3:
            harvest = (
                f"{float(selected_fp.braking_harvest_ratio):.3f}"
                if selected_fp
                and selected_fp.braking_harvest_ratio is not None
                else "—"
            )
            st.metric("Harvest proxy", harvest)

        with st.expander("Corner class breakdown"):
            corner_rows = [
                {
                    "Corner class": "Slow",
                    "Δ km/h": (
                        safe_delta(
                            getattr(selected_fp, "corner_slow_delta_kph", None)
                        )
                        if selected_fp
                        else None
                    ),
                },
                {
                    "Corner class": "Medium",
                    "Δ km/h": (
                        safe_delta(
                            getattr(selected_fp, "corner_medium_delta_kph", None)
                        )
                        if selected_fp
                        else None
                    ),
                },
                {
                    "Corner class": "Fast",
                    "Δ km/h": (
                        safe_delta(
                            getattr(selected_fp, "corner_fast_delta_kph", None)
                        )
                        if selected_fp
                        else None
                    ),
                },
            ]
            st.dataframe(
                pd.DataFrame(corner_rows),
                use_container_width=True,
                hide_index=True,
            )

        st.caption(
            "Speed deltas are relative to the session-fastest reference car. "
            "Corner deltas remain an approximate derived metric; harvest is an "
            "inferred behaviour proxy, not measured battery data."
        )

# ── TEAM TAB ──────────────────────────────────────────────────────────────
with team_tab:
    team_rows = _team_pace_rows(fps)
    team_options = [row["team"] for row in team_rows]

    selected_team = st.selectbox(
        "Team",
        team_options,
        key="race_analysis_team",
    )

    team_position, team_row = _team_rank(selected_team, team_rows)
    team_gap = team_row["gap"] if team_row else None

    st.markdown(f"## {selected_team}")
    st.write(
        _team_story(
            dossier,
            selected_team,
            team_position,
            team_gap,
        )
    )

    t1, t2, t3 = st.columns(3, gap="medium")
    with t1:
        st.metric(
            "Team pace rank",
            f"P{team_position}" if team_position is not None else "—",
        )
    with t2:
        st.metric(
            "Median pace gap",
            f"{team_gap:.3f}%" if team_gap is not None else "—",
        )
    with t3:
        cars = team_row["cars"] if team_row else 0
        st.metric("Cars with pace sample", cars)

    team_codes = sorted(
        code
        for code in (set(fp_map) | set(results))
        if _team_for_code(code, fp_map, lineup) == selected_team
    )

    comparison_rows = []
    for code in team_codes:
        fp = fp_map.get(code)
        result = results.get(code, {})
        row = {
            "Driver": f"{code} · {driver_name(code, selected_round)}",
            "Pace rank": fp.lap_time_rank if fp else None,
            "Pace gap %": (
                round(float(fp.lap_time_gap_pct), 3)
                if fp is not None and fp.lap_time_gap_pct is not None
                else None
            ),
        }
        if is_race:
            row["Finish"] = result.get("finishing_position")
            row["Grid"] = result.get("grid_position")
            row["Status"] = result.get("result_status", "") or (
                getattr(fp, "result_status", "") if fp else ""
            )
        comparison_rows.append(row)

    st.dataframe(
        pd.DataFrame(comparison_rows),
        use_container_width=True,
        hide_index=True,
    )

    fig = _team_dot_plot(team_rows, selected_team, is_race)
    if fig is not None:
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
        )
        st.caption(
            "The selected team is highlighted. Lower gap is quicker. "
            + (
                "Race values use representative pace and are not the finishing order."
                if is_race
                else "Qualifying values use the common session-fastest reference."
            )
        )

# ── FULL FIELD TAB ────────────────────────────────────────────────────────
with field_tab:
    section_header(
        "Full session",
        "Every car in one place",
        (
            "Official result and representative pace remain separate."
            if is_race
            else f"All qualifying gaps use {ref.driver_code} as the session reference."
        ),
    )

    full_df = _full_field_df(
        fps,
        results,
        lineup,
        selected_round,
        is_race,
    )
    st.dataframe(
        full_df,
        use_container_width=True,
        hide_index=True,
        height=min(760, 36 * len(full_df) + 40),
    )

    if is_race:
        st.caption(
            "Drivers without enough clean laps remain in the official result table "
            "with no fabricated representative pace value."
        )
        st.info(
            "Race-session straight/braking/corner speed deltas and ERS ratios are not "
            "used as cross-driver evidence because representative laps occur under "
            "different tyres, fuel loads and track states."
        )

st.markdown(
    """
<div class="ll-ai-hook">
    <div>
        <strong>Want the engineering explanation?</strong>
        <span>Ask about a driver, team, strategy context, pace comparison or how LatentLap built the metric.</span>
    </div>
    <a class="ll-cta ll-cta-primary" href="/Ask_the_Engineer" target="_self">Ask the Engineer</a>
</div>
    """,
    unsafe_allow_html=True,
)
