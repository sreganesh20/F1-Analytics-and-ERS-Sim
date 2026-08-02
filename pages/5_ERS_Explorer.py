"""
pages/5_ERS_Explorer.py — Interactive ERS strategy optimizer
"""

import os, sys
import streamlit as st
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import CIRCUITS
from app.charts import strategy_chart, soc_flow_chart

st.set_page_config(page_title="ERS Explorer — ERS_v2", page_icon="⚡", layout="wide")
st.title("⚡ ERS Strategy Explorer")
st.caption(
    "Run the dynamic-programming ERS optimizer on any circuit. "
    "Adjust the harvest limit, SoC, and session type, then hit Run."
)

# ── Controls ──────────────────────────────────────────────
col_ctrl, col_result = st.columns([1, 3])

with col_ctrl:
    circuit_names = sorted(CIRCUITS.keys())
    default_idx   = circuit_names.index("Netherlands") if "Netherlands" in circuit_names else 0
    circuit       = st.selectbox("Circuit", circuit_names, index=default_idx)

    cfg     = CIRCUITS[circuit]
    session = st.radio("Session", ["Q", "R"], horizontal=True)

    default_limit = float(cfg.get(
        f"harvest_limit_{'quali' if session == 'Q' else 'race'}_mj",
        cfg.get("harvest_limit_mj", 8.5)
    ))

    harvest_limit = st.slider(
        "Harvest Limit (MJ/lap)",
        min_value=5.0, max_value=9.5, value=default_limit, step=0.5,
        help=f"FIA-mandated limit for {circuit} {session}. Default: {default_limit} MJ"
    )

    soc_start = st.slider(
        "Starting SoC (MJ)",
        min_value=0.0, max_value=4.0, value=4.0, step=0.1,
        help="Battery charge at lap start. Q = 4.0 (full). Race varies."
    )

    st.markdown("---")

    # Circuit info card
    st.markdown(f"""
    <div style="background:#1A1A1A;border-radius:8px;padding:12px 14px;
                font-family:monospace;font-size:0.8rem;line-height:1.8;">
        <div style="color:#888;">Circuit info</div>
        <div><b>Type:</b> {cfg.get('circuit_type','—').title()}</div>
        <div><b>Length:</b> {cfg.get('lap_length_km','—')} km</div>
        <div><b>Altitude:</b> {cfg.get('altitude_m',0)} m</div>
        <div><b>Harvest Q:</b> {cfg.get('harvest_limit_quali_mj','—')} MJ</div>
        <div><b>Harvest R:</b> {cfg.get('harvest_limit_race_mj','—')} MJ</div>
        <div><b>Sprint:</b> {'✓' if cfg.get('has_sprint') else '✗'}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("")
    run = st.button("🚀 Run Optimizer", use_container_width=True, type="primary")

# ── Results ───────────────────────────────────────────────
with col_result:
    if not run:
        st.markdown("""
        <div style="display:flex;align-items:center;justify-content:center;
                    height:400px;color:#444;font-family:monospace;font-size:1rem;">
            ← Configure and press Run Optimizer
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    with st.spinner("Running DP optimizer..."):
        try:
            from models.track import segment_lap
            from models.optimizer import optimise

            # Try FastF1 cache first, fall back to synthetic
            data_source = "Synthetic (no local cache)"
            try:
                from fetcher import fetch_real_telemetry
                cfg_local = {**cfg, "fastf1_session": session}
                df = fetch_real_telemetry(cfg_local)
                if df is not None and df["Source"].iloc[0] == "FastF1":
                    data_source = "FastF1 (local cache)"
                else:
                    raise ValueError("No real telemetry")
            except Exception:
                from fetcher import generate_synthetic_telemetry
                df = generate_synthetic_telemetry(circuit)

            cfg_override = {
                **cfg,
                "fastf1_session":      session,
                "harvest_limit_race_mj":  harvest_limit,
                "harvest_limit_quali_mj": harvest_limit,
            }

            segments = segment_lap(df)
            optimal  = optimise(segments, cfg_override,
                               soc_start=soc_start,
                               session_type=session)

        except Exception as e:
            st.error(f"Optimizer failed: {e}")
            import traceback
            st.code(traceback.format_exc())
            st.stop()

    # Source badge
    badge_col = "#00C851" if "FastF1" in data_source else "#FFD700"
    st.markdown(
        f'<span style="background:{badge_col}22;color:{badge_col};border:1px solid {badge_col};'
        f'border-radius:4px;padding:2px 8px;font-family:monospace;font-size:0.75rem;">'
        f'Data: {data_source}</span>',
        unsafe_allow_html=True
    )
    if "Synthetic" in data_source:
        st.caption(
            "⚠️ Using synthetic telemetry — results are indicative. "
            "Run `python run.py pipeline` locally to cache real FastF1 data."
        )

    st.markdown("")

    # Metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Harvest Limit", f"{optimal.harvest_limit_mj:.1f} MJ")
    m2.metric("Harvested", f"{optimal.total_harvest_mj:.3f} MJ",
              f"{optimal.harvest_utilisation_pct:.1f}% used")
    m3.metric("Deployed", f"{optimal.total_deploy_mj:.3f} MJ")
    m4.metric("Lap Time Δ", f"{optimal.lap_time_delta_s:+.3f}s")
    m5.metric("Battery Floor", f"{optimal.battery_floor_mj:.3f} MJ")

    st.markdown("")

    # Strategy chart
    fig1 = strategy_chart(optimal)
    st.plotly_chart(fig1, use_container_width=True)

    # SoC flow
    fig2 = soc_flow_chart(optimal)
    st.plotly_chart(fig2, use_container_width=True)

    # Segment table
    with st.expander("📋 Full Segment Breakdown"):
        rows = [{
            "Seg":     s.seg_index,
            "Type":    s.seg_type,
            "Start":   f"{s.d_start:.0f}m",
            "End":     f"{s.d_end:.0f}m",
            "Time":    f"{s.time_s:.2f}s",
            "Harvest": round(s.optimal_harvest, 3),
            "Max Hrv": round(s.max_harvest, 3),
            "Deploy":  round(s.optimal_deploy, 3),
            "SoC In":  round(s.soc_entry, 3),
            "SoC Out": round(s.soc_exit, 3),
            "Δ Time":  f"{s.time_delta_s:+.3f}s",
        } for s in optimal.segments]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
