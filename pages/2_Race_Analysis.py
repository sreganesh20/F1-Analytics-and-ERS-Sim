"""pages/2_Race_Analysis.py — LatentLap · Round-by-round session analysis."""

import os
import sys

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (
    classification_threshold,
    driver_badge,
    driver_name,
    driver_number,
    fmt_laptime,
    get_circuits_with_data,
    get_fingerprints,
    get_session_results,
    get_sessions_for_round,
    is_classified,
    race_highlights,
    safe_delta,
)
from config import lineup_for_round

st.set_page_config(page_title="Race Analysis — LatentLap", page_icon="📊", layout="wide")
ACCENT = (
    '<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
    'border-radius:2px;margin-bottom:1rem;"></div>'
)
st.markdown(ACCENT, unsafe_allow_html=True)
st.title("📊 Race Analysis")

circuit_map = get_circuits_with_data()
if not circuit_map:
    st.warning("No session data in store. Run the pipeline locally first.")
    st.stop()

SESSION_LABELS = {
    "Q": "Qualifying",
    "SQ": "Sprint Qualifying",
    "R": "Race",
    "S": "Sprint",
}
SESSION_SORT = {"SQ": 0, "S": 1, "Q": 2, "R": 3}

round_options = {f"R{r} — {circuit_map[r]}": r for r in sorted(circuit_map.keys())}
sel_label = st.selectbox("Round", list(round_options.keys()), index=len(round_options) - 1)
sel_round = round_options[sel_label]

available = sorted(get_sessions_for_round(sel_round), key=lambda s: SESSION_SORT.get(s, 99))
if not available:
    st.info("No sessions loaded for this round.")
    st.stop()

all_fps = get_fingerprints()


def _status_finished(status: str) -> bool:
    if not status:
        return True
    s = str(status).strip().lower()
    if s in {"finished", "lapped", "classified"}:
        return True
    if s.startswith("finished") or s.startswith("+"):
        return True
    return False


def _ordered_result_codes(results: dict) -> list[str]:
    def key(item):
        code, row = item
        pos = row.get("finishing_position")
        return (pos is None, pos if pos is not None else 999, code)

    return [code for code, _ in sorted(results.items(), key=key)]


tabs = st.tabs([SESSION_LABELS.get(s, s) for s in available])
for tab, session in zip(tabs, available):
    with tab:
        fps = [
            fp for fp in all_fps
            if fp.race_round == sel_round and fp.session_type == session
        ]
        if not fps:
            st.info(f"No analytical pace data for {SESSION_LABELS.get(session, session)}.")
            continue

        is_race = session in ("R", "S")
        ranked = sorted(fps, key=lambda f: f.lap_time_s)
        ref = ranked[0]
        lap_label = "Representative Race Pace" if is_race else "Best Lap"
        results = get_session_results(sel_round, session) if is_race else {}
        lineup = lineup_for_round(sel_round)

        # FIA 90% rule remains useful for old fingerprint-only sessions. New
        # result rosters expose the official status directly, including early DNFs.
        clf_threshold = classification_threshold(fps) if is_race else 0

        # ── Session summary strip ─────────────────────────
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            st.markdown(
                f"**Reference car** &nbsp; {driver_badge(ref.driver_code, 'md', sel_round)} "
                f"&nbsp;`{fmt_laptime(ref.lap_time_s)}`",
                unsafe_allow_html=True,
            )
            if is_race:
                st.caption(
                    f"{lap_label} · aggregate pace only. Race-session speed/ERS deltas are "
                    "not treated as cross-driver evidence because representative laps occur "
                    "under different tyres, fuel loads and track states."
                )
            else:
                st.caption(f"{lap_label} · deltas below are measured against this car")
        c2.metric("Circuit type", ref.circuit_type.title())
        field_count = len(results) if results else len(fps)
        c3.metric("Cars", field_count)
        if is_race and results and len(results) != len(fps):
            st.caption(f"{len(fps)} cars have a valid representative pace sample")
        st.divider()

        # ── Race highlights ───────────────────────────────
        if is_race:
            hl = race_highlights(fps)

            # Use the full official result roster for attrition so a driver who
            # retired before a representative lap (e.g. lap-one accident) is not
            # erased from the session story.
            if results:
                hl["dnf_count"] = sum(
                    1 for row in results.values()
                    if not _status_finished(row.get("result_status", ""))
                )
                hl["nc_count"] = sum(
                    1 for row in results.values()
                    if _status_finished(row.get("result_status", ""))
                    and row.get("finishing_position") is None
                    and row.get("result_status")
                )

                gained_rows = []
                for code, row in results.items():
                    gained = row.get("positions_gained")
                    if gained is not None:
                        gained_rows.append((gained, code, row))
                if gained_rows:
                    gained, code, row = max(gained_rows, key=lambda x: x[0])
                    if gained > 0:
                        hl["most_gained"] = {
                            "driver": code,
                            "team": lineup.get(code, {}).get("team", "Unknown"),
                            "gained": gained,
                            "grid": row.get("grid_position"),
                            "finish": row.get("finishing_position"),
                        }

            st.markdown("#### 🏁 Race Highlights")
            h1, h2, h3, h4 = st.columns(4)
            with h1:
                st.markdown("**Fastest Lap**")
                if hl["fastest_lap"]:
                    f = hl["fastest_lap"]
                    st.markdown(
                        driver_badge(f["driver"], "md", sel_round),
                        unsafe_allow_html=True,
                    )
                    lap_txt = f" · lap {f['lap']}" if f["lap"] else ""
                    st.markdown(f"`{fmt_laptime(f['time_s'])}`{lap_txt}")
                else:
                    st.markdown("—")
            with h2:
                st.markdown("**Fastest Sectors**")
                if hl["sectors"]:
                    stale = any(d.get("source") == "rep_lap" for d in hl["sectors"].values())
                    for sec, d in hl["sectors"].items():
                        st.markdown(
                            f"{sec} &nbsp;{driver_badge(d['driver'], 'sm', sel_round)} "
                            f"&nbsp;`{d['time_s']:.3f}s`",
                            unsafe_allow_html=True,
                        )
                    if stale:
                        st.caption(
                            "⚠ From representative-lap splits — re-run the race pipeline "
                            "for true per-driver best sectors."
                        )
                else:
                    st.markdown("—")
            with h3:
                st.markdown("**Most Places Gained**")
                if hl["most_gained"]:
                    g = hl["most_gained"]
                    st.markdown(
                        driver_badge(g["driver"], "md", sel_round),
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"**+{g['gained']}** &nbsp;P{g['grid']} → P{g['finish']}")
                else:
                    st.markdown("—")
            with h4:
                st.markdown("**Attrition**")
                st.markdown(
                    f"**{hl['dnf_count']}** DNF"
                    + (f" · **{hl['nc_count']}** NC" if hl["nc_count"] else "")
                )
                if hl["pit_range"]:
                    lo, hi = hl["pit_range"]
                    st.caption(f"Pit stops: {lo}–{hi}")

            if hl["best_pit_lane"]:
                p = hl["best_pit_lane"]
                st.caption(
                    f"Quickest pit lane transit — {p['driver']} ({p['team']}) "
                    f"{p['time_s']:.2f}s. This is pit entry to pit exit including the "
                    "speed-limited drive-through, **not** stationary stop time."
                )
            st.divider()

        # ── Detail table ──────────────────────────────────
        st.markdown(f"#### {SESSION_LABELS.get(session, session)} — Detail")
        rows = []

        if is_race and results:
            fp_map = {fp.driver_code: fp for fp in ranked}
            codes = _ordered_result_codes(results)
            # Preserve any analytical row absent from the official result map.
            codes.extend(code for code in fp_map if code not in results)

            for code in codes:
                fp = fp_map.get(code)
                result = results.get(code, {})
                team = fp.team if fp else lineup.get(code, {}).get("team", "Unknown")
                status = result.get("result_status", "") or (getattr(fp, "result_status", "") if fp else "")
                completed = _status_finished(status)
                grid = result.get("grid_position")
                finish = result.get("finishing_position")
                laps = result.get("laps_completed")
                if laps is None and fp is not None:
                    laps = getattr(fp, "laps_completed", None)

                row = {
                    "Pace Rank": fp.lap_time_rank if fp else None,
                    "No": driver_number(code, sel_round),
                    "Code": code,
                    "Driver": driver_name(code, sel_round),
                    "Team": team,
                    lap_label: fmt_laptime(fp.lap_time_s) if fp else "—",
                    "Gap %": round(fp.lap_time_gap_pct, 3) if fp else None,
                    "Grid": grid,
                    "Finish": finish,
                    "+/-": ((grid - finish) if grid is not None and finish is not None else None),
                    "Laps": laps,
                    "Pits": (fp.pit_stops if fp is not None and fp.pit_stops is not None else None),
                    "Status": ("" if completed else "DNF"),
                    "Reason": status if not completed else "",
                }
                rows.append(row)
        else:
            for fp in ranked:
                row = {
                    "Pace Rank": fp.lap_time_rank,
                    "No": driver_number(fp.driver_code, sel_round),
                    "Code": fp.driver_code,
                    "Driver": driver_name(fp.driver_code, sel_round),
                    "Team": fp.team,
                    lap_label: fmt_laptime(fp.lap_time_s),
                    "Gap %": round(fp.lap_time_gap_pct, 3),
                    "Straight Δ": safe_delta(fp.straight_speed_delta_kph),
                    "Corner Δ": safe_delta(fp.corner_speed_delta_kph),
                    "Harvest": round(fp.braking_harvest_ratio, 3),
                }
                rows.append(row)

        df = pd.DataFrame(rows)
        for col in ("Grid", "Finish", "+/-", "Laps", "Pits", "Pace Rank", "No"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        if is_race and "Finish" in df.columns:
            df = df.sort_values("Finish", na_position="last").reset_index(drop=True)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=min(780, 38 * len(rows) + 40),
        )

        if is_race:
            st.caption(
                "**Pace Rank** ranks only drivers with a valid representative race-pace sample; "
                "it is not the race result. A driver who retires before enough clean laps exist "
                "still appears in the official result rows with Representative Race Pace = N/A. "
                "**Representative Race Pace** uses filtered green-flag laps and is aggregate pace, "
                "not one-lap telemetry equivalence."
            )
            st.info(
                "Straight/braking/corner speed deltas and ERS harvest/deploy ratios are **not "
                "shown for race sessions**. Representative laps occur under different fuel loads, "
                "tyres and track states, so those cross-driver telemetry deltas are not valid race "
                "evidence. Use Qualifying/Sprint Qualifying for controlled telemetry comparisons."
            )
        else:
            st.caption(
                f"Deltas are **kph versus {ref.driver_code}**, the fastest car of this session — "
                "so most values are negative by construction. **Harvest** is an inferred braking "
                "energy-behaviour ratio, not measured battery data."
            )
