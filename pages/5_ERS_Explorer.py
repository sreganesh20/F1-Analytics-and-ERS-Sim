"""pages/5_ERS_Explorer.py — LatentLap · theoretical ERS strategy explorer."""

from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.charts import soc_flow_chart, strategy_chart
from app.ui import inject_global_css, page_header, section_header
from config import CIRCUITS


st.set_page_config(
    page_title="ERS Explorer — LatentLap",
    page_icon="⚡",
    layout="wide",
)
inject_global_css()


page_header(
    "Energy Recovery System",
    "ERS Explorer",
    "Explore the theoretical energy strategy produced by LatentLap's constrained optimiser. This is a model of what could work — not a reconstruction of a team's real battery state or secret deployment map.",
)

with st.container(border=True):
    a, b, c, d = st.columns(4, gap="medium")
    with a:
        st.markdown("**Measured**")
        st.write("Public timing and telemetry such as speed, throttle and braking.")
    with b:
        st.markdown("**Inferred**")
        st.write("Relative energy-behaviour proxies derived from observable telemetry.")
    with c:
        st.markdown("**Assumed**")
        st.write("Regulation limits, coefficients and model simplifications.")
    with d:
        st.markdown("**Optimised**")
        st.write("The theoretical harvest/deploy strategy returned by the model.")

explore_tab, method_tab = st.tabs(
    ["Explore strategy", "How the optimiser works"]
)

with explore_tab:
    controls, output = st.columns([1, 2.4], gap="large")

    with controls:
        with st.container(border=True):
            st.markdown("### Configure")

            circuit_names = sorted(
                CIRCUITS.keys(),
                key=lambda name: CIRCUITS[name].get("round", 999),
            )
            default_name = "Italy" if "Italy" in circuit_names else circuit_names[-1]
            circuit = st.selectbox(
                "Circuit",
                circuit_names,
                index=circuit_names.index(default_name),
            )

            cfg = CIRCUITS[circuit]

            session = st.radio(
                "Session",
                ["Q", "R"],
                horizontal=True,
                format_func=lambda value: (
                    "Qualifying" if value == "Q" else "Race"
                ),
            )

            default_limit = float(
                cfg.get(
                    f"harvest_limit_{'quali' if session == 'Q' else 'race'}_mj",
                    cfg.get("harvest_limit_mj", 8.5),
                )
            )

            harvest_limit = st.slider(
                "Harvest limit",
                min_value=5.0,
                max_value=9.5,
                value=default_limit,
                step=0.5,
                format="%.1f MJ/lap",
                help=(
                    f"Configured limit for {circuit} "
                    f"{'qualifying' if session == 'Q' else 'race'}."
                ),
            )

            soc_start = st.slider(
                "Starting battery state",
                min_value=0.0,
                max_value=4.0,
                value=4.0,
                step=0.1,
                format="%.1f MJ",
                help=(
                    "A model input, not an observed team battery state. "
                    "Qualifying commonly starts from a full model battery."
                ),
            )

            st.divider()

            st.markdown("**Circuit context**")
            st.write(
                f"{cfg.get('circuit_type', '—').replace('_', ' ').title()} · "
                f"{cfg.get('lap_length_km', '—')} km"
            )
            st.caption(
                f"Configured Q harvest limit {cfg.get('harvest_limit_quali_mj', '—')} MJ · "
                f"Race {cfg.get('harvest_limit_race_mj', '—')} MJ"
            )

            run = st.button(
                "Run theoretical optimiser",
                type="primary",
                use_container_width=True,
            )

    with output:
        if not run:
            with st.container(border=True):
                st.markdown("### Ready to explore")
                st.write(
                    "Choose a circuit and session, adjust the assumptions if you want, "
                    "then run the optimiser."
                )
                st.caption(
                    "LatentLap first looks for a committed telemetry extract, then a local "
                    "FastF1 cache. If neither exists it can demonstrate the method on a "
                    "synthetic circuit model, which is explicitly labelled."
                )

        if run:
            with st.spinner("Solving the constrained energy strategy…"):
                try:
                    from fetcher import (
                        fetch_real_telemetry,
                        generate_synthetic_telemetry,
                        load_telemetry_extract,
                    )
                    from models.optimizer import optimise
                    from models.track import segment_lap

                    df = None
                    data_source = None

                    df = load_telemetry_extract(circuit, session)
                    if df is not None:
                        data_source = "Real telemetry · committed extract"

                    if df is None:
                        try:
                            cfg_local = {
                                **cfg,
                                "fastf1_session": session,
                            }
                            cached = fetch_real_telemetry(cfg_local)
                            if (
                                cached is not None
                                and cached["Source"].iloc[0] == "FastF1"
                            ):
                                df = cached
                                data_source = "Real telemetry · local FastF1 cache"
                        except Exception:
                            pass

                    if df is None:
                        df = generate_synthetic_telemetry(circuit)
                        data_source = "Synthetic circuit model · not measured telemetry"

                    cfg_override = {
                        **cfg,
                        "fastf1_session": session,
                        "harvest_limit_race_mj": harvest_limit,
                        "harvest_limit_quali_mj": harvest_limit,
                    }

                    segments = segment_lap(df)
                    optimal = optimise(
                        segments,
                        cfg_override,
                        soc_start=soc_start,
                        session_type=session,
                    )

                except Exception as exc:
                    st.error(f"Optimizer failed: {exc}")
                    st.stop()

            with st.container(border=True):
                st.markdown(f"### {circuit} · {data_source}")
                if "Synthetic" in data_source:
                    st.warning(
                        "No real telemetry was available for this run. The lap below is "
                        "a synthetic circuit model built from configuration values, so the "
                        "output demonstrates the optimiser rather than reconstructing a real lap."
                    )
                else:
                    st.caption(
                        "The telemetry is observed input. The harvest/deploy strategy and "
                        "battery trajectory below are model outputs."
                    )

            m1, m2, m3, m4 = st.columns(4, gap="medium")
            m1.metric(
                "Harvested",
                f"{optimal.total_harvest_mj:.2f} MJ",
                f"{optimal.harvest_utilisation_pct:.0f}% of limit",
            )
            m2.metric(
                "Deployed",
                f"{optimal.total_deploy_mj:.2f} MJ",
            )
            m3.metric(
                "Model lap-time effect",
                f"{optimal.lap_time_delta_s:+.3f}s",
            )
            m4.metric(
                "Battery floor",
                f"{optimal.battery_floor_mj:.2f} MJ",
            )

            section_header(
                "Strategy",
                "Where the model harvests and deploys",
                "Harvest and deploy actions are chosen by the optimiser under the configured constraints and heuristic time-cost/time-benefit model.",
            )
            st.plotly_chart(
                strategy_chart(optimal),
                use_container_width=True,
                config={"displayModeBar": False},
            )

            section_header(
                "Battery state",
                "Model SoC through the lap",
                "This is the optimiser's internal battery state — not measured battery telemetry from the car.",
            )
            st.plotly_chart(
                soc_flow_chart(optimal),
                use_container_width=True,
                config={"displayModeBar": False},
            )

            with st.expander("Full segment breakdown"):
                rows = [
                    {
                        "Segment": segment.seg_index,
                        "Type": segment.seg_type,
                        "Start": f"{segment.d_start:.0f} m",
                        "End": f"{segment.d_end:.0f} m",
                        "Time": f"{segment.time_s:.2f}s",
                        "Harvest MJ": round(segment.optimal_harvest, 3),
                        "Max harvest": round(segment.max_harvest, 3),
                        "Deploy MJ": round(segment.optimal_deploy, 3),
                        "SoC in": round(segment.soc_entry, 3),
                        "SoC out": round(segment.soc_exit, 3),
                        "Δ time": f"{segment.time_delta_s:+.3f}s",
                    }
                    for segment in optimal.segments
                ]
                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True,
                )

with method_tab:
    section_header(
        "Method",
        "Bellman dynamic programming, not a hidden team strategy",
        "The optimiser searches segment-by-segment harvest/deploy actions while respecting battery and per-lap constraints.",
    )

    with st.container(border=True):
        st.markdown(
            """
### State

The dynamic-programming state tracks:

- **battery state-of-charge**, discretised in 0.1 MJ steps;
- **cumulative harvest budget**, discretised in 0.5 MJ steps.

### Actions

At each track segment the model chooses a harvest/deploy pair within the
segment's allowed energy limits.

### Objective

The reward is the modelled **time saved by deployment minus time lost by harvesting**.

Those benefit/cost coefficients are engineering heuristics inside LatentLap.
They are not measurements of a real team's electrical efficiency or control software.

### What this page cannot claim

It cannot recover a team's true SoC, exact recovered energy, exact MGU-K deployment,
or private strategy. The optimiser is a constrained theoretical benchmark that can be
compared with the public telemetry-derived behaviour proxies elsewhere in LatentLap.
            """
        )

    st.markdown(
        """
<div class="ll-ai-hook">
    <div>
        <strong>Want the implementation explained?</strong>
        <span>Ask the Engineer can walk through telemetry segmentation, ERS inference, the Bellman state/action model and its assumptions.</span>
    </div>
    <a class="ll-cta ll-cta-primary" href="/Ask_the_Engineer" target="_self">Ask about the method</a>
</div>
        """,
        unsafe_allow_html=True,
    )
