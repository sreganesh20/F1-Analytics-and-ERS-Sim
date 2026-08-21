"""pages/2_Race_Analysis.py — PitWall · Round-by-round session analysis."""

import os, sys
import streamlit as st
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (get_fingerprints, get_circuits_with_data,
                             get_sessions_for_round, race_highlights,
                             driver_name, driver_badge, fmt_laptime,
                             classification_threshold, is_classified,
                             safe_delta)
from config import CARS

st.set_page_config(page_title="Race Analysis — PitWall", page_icon="📊", layout="wide")

ACCENT = ('<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
          'border-radius:2px;margin-bottom:1rem;"></div>')
st.markdown(ACCENT, unsafe_allow_html=True)
st.title("📊 Race Analysis")

circuit_map = get_circuits_with_data()
if not circuit_map:
    st.warning("No session data in store. Run the pipeline locally first.")
    st.stop()

SESSION_LABELS = {"Q": "Qualifying", "SQ": "Sprint Qualifying",
                  "R": "Race", "S": "Sprint"}

round_options = {f"R{r} — {circuit_map[r]}": r for r in sorted(circuit_map.keys())}
sel_label = st.selectbox("Round", list(round_options.keys()), index=len(round_options) - 1)
sel_round = round_options[sel_label]

available = get_sessions_for_round(sel_round)
if not available:
    st.info("No sessions loaded for this round.")
    st.stop()

all_fps = get_fingerprints()
tabs = st.tabs([SESSION_LABELS.get(s, s) for s in available])

for tab, session in zip(tabs, available):
    with tab:
        fps = [fp for fp in all_fps
               if fp.race_round == sel_round and fp.session_type == session]
        if not fps:
            st.info(f"No data for {SESSION_LABELS.get(session, session)}.")
            continue

        is_race = session in ("R", "S")
        ranked  = sorted(fps, key=lambda f: f.lap_time_s)
        ref     = ranked[0]
        lap_label = "Representative Race Pace" if is_race else "Best Lap"
        # FIA 90% rule — who was officially classified
        clf_threshold = classification_threshold(fps) if is_race else 0

        # ── Session summary strip ─────────────────────────
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            st.markdown(
                f"**Reference car** &nbsp; {driver_badge(ref.driver_code, 'md')} "
                f"&nbsp;`{fmt_laptime(ref.lap_time_s)}`",
                unsafe_allow_html=True)
            st.caption(f"{lap_label} · all deltas below are measured against this car")
        c2.metric("Circuit type", ref.circuit_type.title())
        c3.metric("Cars", len(fps))

        st.divider()

        # ── RACE HIGHLIGHTS (race/sprint only) ────────────
        if is_race:
            hl = race_highlights(fps)
            st.markdown("#### 🏁 Race Highlights")

            h1, h2, h3, h4 = st.columns(4)
            with h1:
                st.markdown("**Fastest Lap**")
                if hl["fastest_lap"]:
                    f = hl["fastest_lap"]
                    st.markdown(driver_badge(f["driver"], "md"), unsafe_allow_html=True)
                    lap_txt = f" · lap {f['lap']}" if f["lap"] else ""
                    st.markdown(f"`{fmt_laptime(f['time_s'])}`{lap_txt}")
                else:
                    st.markdown("—")
            with h2:
                st.markdown("**Fastest Sectors**")
                if hl["sectors"]:
                    stale = any(d.get("source") == "rep_lap"
                                for d in hl["sectors"].values())
                    for sec, d in hl["sectors"].items():
                        st.markdown(
                            f"{sec} &nbsp;{driver_badge(d['driver'], 'sm')}"
                            f" &nbsp;`{d['time_s']:.3f}s`", unsafe_allow_html=True)
                    if stale:
                        st.caption("⚠ From reference lap splits — re-run the race "
                                   "pipeline for true per-driver best sectors.")
                else:
                    st.markdown("—")
            with h3:
                st.markdown("**Most Places Gained**")
                if hl["most_gained"]:
                    g = hl["most_gained"]
                    st.markdown(driver_badge(g["driver"], "md"), unsafe_allow_html=True)
                    st.markdown(f"**+{g['gained']}** &nbsp;P{g['grid']} → P{g['finish']}")
                else:
                    st.markdown("—")
            with h4:
                st.markdown("**Attrition**")
                st.markdown(f"**{hl['dnf_count']}** DNF"
                            + (f" · **{hl['nc_count']}** NC" if hl["nc_count"] else ""))
                if hl["pit_range"]:
                    lo, hi = hl["pit_range"]
                    st.caption(f"Pit stops: {lo}–{hi}")

            if hl["best_pit_lane"]:
                p = hl["best_pit_lane"]
                st.caption(
                    f"Quickest pit lane transit — {p['driver']} ({p['team']}) "
                    f"{p['time_s']:.2f}s. This is pit entry to pit exit including the "
                    "speed-limited drive-through, **not** stationary stop time. "
                    "Stationary times (the ~2s figures) come from DHL and are entered manually."
                )
            st.divider()

        # ── Detail table ──────────────────────────────────
        st.markdown(f"#### {SESSION_LABELS.get(session, session)} — Detail")

        rows = []
        for fp in ranked:
            row = {
                "Pace Rank": fp.lap_time_rank,
                "No":        CARS.get(fp.driver_code, {}).get("number", ""),
                "Code":      fp.driver_code,
                "Driver":    driver_name(fp.driver_code),
                "Team":      fp.team,
                lap_label:   fmt_laptime(fp.lap_time_s),
                "Gap %":     round(fp.lap_time_gap_pct, 3),
            }
            if is_race:
                classified = is_classified(fp, clf_threshold)
                # Numeric columns kept as real numbers so table sorting works.
                # (Storing "NC"/"—" as text made the whole column string-typed,
                #  which sorts 1,10,11,2,3 instead of 1,2,3,10,11.)
                row["Grid"]   = fp.grid_position if fp.grid_position else None
                row["Finish"] = (fp.finishing_position
                                 if classified and fp.finishing_position else None)
                row["+/-"]    = ((fp.grid_position - fp.finishing_position)
                                 if classified and fp.grid_position
                                 and fp.finishing_position else None)
                row["Laps"]   = getattr(fp, "laps_completed", None) or None
                row["Pits"]   = fp.pit_stops if fp.pit_stops is not None else None
                row["Status"] = ("DNF" if not fp.completed_race
                                 else ("NC" if not classified else ""))
                row["Reason"] = fp.result_status if not fp.completed_race else ""
            else:
                # safe_delta blanks values the fixed-distance-window method
                # can't support, rather than printing "+318 kph" at a reader.
                row["Straight Δ"] = safe_delta(fp.straight_speed_delta_kph)
                row["Corner Δ"]   = safe_delta(fp.corner_speed_delta_kph)
                row["Harvest"]    = round(fp.braking_harvest_ratio, 3)
            rows.append(row)

        df = pd.DataFrame(rows)
        # Nullable integer dtype: sorts numerically, renders blanks for NC/DNF
        for col in ("Grid", "Finish", "+/-", "Laps", "Pits", "Pace Rank", "No"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        # Default order for races = actual result: P1..Pn first, DNF/NC last.
        # (na_position="last" keeps unclassified runners at the bottom rather
        #  than floating to the top as NaN normally would.)
        if is_race and "Finish" in df.columns:
            df = df.sort_values("Finish", na_position="last").reset_index(drop=True)

        st.dataframe(df, use_container_width=True, hide_index=True,
                     height=min(780, 38 * len(rows) + 40))

        if is_race:
            st.caption(
                f"**Pace Rank** = ranking by race pace, *not* the race result — a fast car "
                f"that retired ranks high here but finishes low. **Finish** = official "
                f"classification. **Representative Race Pace** = IQR-filtered average of clean "
                f"green-flag laps (excludes out-laps, in-laps, safety car and outliers), not a "
                f"single fastest lap. **Pits** = tyre stops (stint changes). "
                f"**DNF** = retired. **NC** = not classified — under {clf_threshold} laps "
                f"(90% of the winner's {max((getattr(f,'laps_completed',0) or 0) for f in fps)})."
            )
            st.info(
                "Speed deltas and harvest ratios are **not shown for race sessions**. Each "
                "driver's representative lap comes from a different point in the race "
                "(different fuel load, tyre compound, track state), so comparing telemetry "
                "against one reference car isn't valid. Those signals live in **Qualifying**, "
                "where conditions are controlled."
            )
        else:
            st.caption(
                f"Deltas are **kph versus {ref.driver_code}**, the fastest car of this session — "
                "so most values are negative by construction. **Harvest** = braking energy "
                "actually recovered ÷ theoretical maximum recoverable (1.0 = physics ceiling)."
            )
