"""LatentLap — F1 2026 analytics home."""

from __future__ import annotations

import html
import os
import sys

import streamlit as st

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (
    TEAM_COLOURS,
    driver_name,
    get_circuits_with_data,
    get_constructor_standings,
    get_driver_standings,
    get_prediction_data,
    list_available_predictions,
)
from app.ui import inject_global_css, intent_grid, methodology_strip, section_header
from config import CIRCUITS


st.set_page_config(
    page_title="LatentLap — F1 2026 Analytics",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_global_css()


# ── Current deterministic state ────────────────────────────────────────────
circuit_map = get_circuits_with_data()
driver_standings = get_driver_standings()
constructor_standings = get_constructor_standings()
latest_completed_round = max(circuit_map.keys()) if circuit_map else 0

predicted_circuits = list_available_predictions()
latest_prediction_circuit = (
    max(predicted_circuits, key=lambda c: CIRCUITS.get(c, {}).get("round", -1))
    if predicted_circuits
    else None
)
latest_prediction = (
    get_prediction_data(latest_prediction_circuit, pred_type="quali")
    if latest_prediction_circuit
    else None
)


# ── Hero ───────────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="ll-hero">
    <div class="ll-wordmark">LATENT<span>LAP</span></div>
    <div class="ll-kicker">F1 2026 analytics</div>
    <h1>What the timing screen doesn’t tell you.</h1>
    <div class="ll-hero-copy">
        LatentLap looks beyond finishing positions to explore who was really quick,
        how teams and drivers performed, what changed, and how F1 cars manage energy —
        using real race data.
    </div>
    <div class="ll-hero-note">
        Some of the most interesting information in Formula 1 is not public. LatentLap
        works backwards from timing and telemetry we can observe, while keeping measured,
        inferred, assumed, optimised and predicted information clearly separated.
    </div>
    <div class="ll-pill-row">
        <span class="ll-pill">Observed</span>
        <span class="ll-pill">Inferred</span>
        <span class="ll-pill">Assumed</span>
        <span class="ll-pill">Optimised</span>
        <span class="ll-pill">Predicted</span>
    </div>
    <div class="ll-hero-actions">
        <a class="ll-cta ll-cta-primary" href="/Race_Analysis" target="_self">Explore the latest race</a>
        <a class="ll-cta ll-cta-secondary" href="/Ask_the_Engineer" target="_self">Ask the Engineer</a>
    </div>
</div>
    """,
    unsafe_allow_html=True,
)


# ── Intent cards ───────────────────────────────────────────────────────────
section_header(
    "Start with a question",
    "Choose what you want to understand",
    "You do not need to know the model names first. Start with the F1 question, then go deeper if you want the methodology.",
)

intent_grid(
    [
        (
            "01 / WEEKEND",
            "What happened this weekend?",
            "See who was actually quick, how teams compared, where teammates gained or lost time, and what the results really showed.",
            [
                ("Race Analysis", "/Race_Analysis", "primary"),
                ("Teams & Drivers", "/Teams_and_Drivers", "secondary"),
            ],
        ),
        (
            "02 / DEVELOPMENT",
            "What’s happening with the cars?",
            "Follow upgrades across the season and separate persistent development from circuit-specific, reliability and power-unit changes.",
            [("Upgrades & Development", "/Upgrades_and_News", "primary")],
        ),
        (
            "03 / ENERGY",
            "How does the energy side work?",
            "Explore ERS — the Energy Recovery System — and see what public telemetry can and cannot tell us about harvesting and deployment.",
            [("Explore ERS", "/ERS_Explorer", "primary")],
        ),
        (
            "04 / EXPLAIN",
            "Ask the Engineer",
            "Ask about drivers, teams, races, upgrades, predictions, ERS or methodology. Answers are grounded in LatentLap’s committed data and analysis.",
            [("Ask a question", "/Ask_the_Engineer", "primary")],
        ),
    ]
)


# ── ERS spotlight — one CSS grid keeps both cards the same height ─────────
section_header(
    "A core LatentLap idea",
    "Working backwards from the telemetry we can see",
    "F1 does not publish the real battery state or exact ERS deployment map. LatentLap therefore treats energy behaviour as an inference problem, not hidden telemetry magically recovered from the car.",
)

st.markdown(
    """
<div class="ll-two-card-grid">
    <div class="ll-spotlight ll-spotlight-flex">
        <div>
            <div class="ll-kicker">ERS · Energy Recovery System</div>
            <h3>Observe what is public. Infer carefully. Optimise separately.</h3>
            <p>
                LatentLap compares braking and speed behaviour with a session reference,
                then uses a constrained theoretical optimiser to explore what an energy
                strategy could look like under the model’s assumptions.
            </p>
            <p>
                The optimiser is <strong>not</strong> a reconstruction of a team’s real battery
                state or secret deployment strategy. It is the theoretical strategy produced
                by the model.
            </p>
        </div>
        <div class="ll-card-footer">
            <a class="ll-cta ll-cta-primary" href="/ERS_Explorer" target="_self">Open ERS Explorer</a>
        </div>
    </div>
    <div class="ll-spotlight ll-spotlight-flex">
        <div class="ll-signal-grid">
            <div class="ll-signal">
                <strong>Measured</strong>
                <span>Timing, speed, throttle, braking behaviour and race results available through public data.</span>
            </div>
            <div class="ll-signal">
                <strong>Inferred</strong>
                <span>Relative performance and energy-behaviour proxies derived from the observable telemetry.</span>
            </div>
            <div class="ll-signal">
                <strong>Assumed</strong>
                <span>Model coefficients, regulation constants and simplifications that are stated rather than hidden.</span>
            </div>
            <div class="ll-signal">
                <strong>Optimised</strong>
                <span>A theoretical ERS strategy produced by the model under those constraints and assumptions.</span>
            </div>
        </div>
        <div class="ll-card-footer">
            <a class="ll-cta ll-cta-secondary" href="/Ask_the_Engineer" target="_self">Ask about the method</a>
        </div>
    </div>
</div>
    """,
    unsafe_allow_html=True,
)


# ── Methodology strip ──────────────────────────────────────────────────────
section_header(
    "Method in one line",
    "How LatentLap works",
    "The deeper methodology remains visible throughout the project, but this is the basic path from public F1 data to an explanation.",
)
methodology_strip(
    [
        ("Observe", "Use real F1 telemetry, timing and race results."),
        ("Infer", "Estimate performance and energy behaviour that is not directly published."),
        ("Predict & Optimise", "Build pace forecasts and theoretical ERS strategies from deterministic models."),
        ("Explain", "Use AI to answer from LatentLap’s own committed data, analysis and reviewed context."),
    ]
)


# ── Season state + prediction preview — same-height grid ──────────────────
section_header(
    "Current state",
    "The 2026 season in LatentLap",
    "A compact checkpoint of what has been analysed and what the model currently expects next.",
)

driver_leader = driver_standings[0] if driver_standings else None
constructor_leader = constructor_standings[0] if constructor_standings else None

driver_value = (
    f"{html.escape(driver_name(driver_leader['code']))} · {driver_leader['points']:.0f} pts"
    if driver_leader
    else "Unavailable"
)
constructor_value = (
    f"{html.escape(constructor_leader['team'])} · {constructor_leader['points']:.0f} pts"
    if constructor_leader
    else "Unavailable"
)

state_html = f"""
<div class="ll-state-card">
    <div>
        <div class="ll-kicker">Season state</div>
        <h3>Round {latest_completed_round} analysed</h3>
        <p class="ll-card-copy">
            Latest completed timing and race data currently committed to the analytical store.
        </p>
        <div class="ll-state-grid">
            <div class="ll-stat">
                <div class="label">Rounds</div>
                <div class="value">{latest_completed_round} / 23</div>
            </div>
            <div class="ll-stat">
                <div class="label">Drivers' leader</div>
                <div class="value">{driver_value}</div>
            </div>
            <div class="ll-stat">
                <div class="label">Constructors' leader</div>
                <div class="value">{constructor_value}</div>
            </div>
        </div>
    </div>
    <div class="ll-card-footer">
        <a class="ll-cta ll-cta-primary" href="/Teams_and_Drivers" target="_self">Explore season performance</a>
    </div>
</div>
"""

if latest_prediction and latest_prediction_circuit:
    confidence = latest_prediction.get("overall_confidence", 0.0)
    rows = latest_prediction.get("predictions", [])[:3]
    row_html = []
    for i, p in enumerate(rows, start=1):
        team = str(p.get("team", ""))
        code = str(p.get("driver_code", ""))
        colour = TEAM_COLOURS.get(team, "#8d98a8")
        gap_s = float(p.get("predicted_delta_s", 0.0) or 0.0)
        gap = "0.000s" if i == 1 else f"+{gap_s:.3f}s"
        row_html.append(
            f'<div class="ll-pred-row">'
            f'<span class="ll-pred-pos">P{i}</span>'
            f'<span class="ll-pred-code">{html.escape(code)}</span>'
            f'<span style="color:{html.escape(colour)};">{html.escape(team)}</span>'
            f'<span class="ll-pred-gap">{gap}</span>'
            f'</div>'
        )

    pred_html = (
        '<div class="ll-pred-card">'
        '<div>'
        '<div class="ll-kicker">Latest forecast</div>'
        f'<h3>{html.escape(latest_prediction_circuit)} · Expected qualifying pace</h3>'
        f'<p class="ll-card-copy">Overall model confidence {confidence:.0%}</p>'
        + ''.join(row_html)
        + '<div class="ll-disclaimer">Pace forecast only. Incidents, safety cars, reliability and strategy calls are not predicted here.</div>'
        + '</div>'
        + '<div class="ll-card-footer">'
        + '<a class="ll-cta ll-cta-primary" href="/Predictions" target="_self">Open full prediction</a>'
        + '</div>'
        + '</div>'
    )
else:
    pred_html = """
<div class="ll-pred-card">
    <div>
        <div class="ll-kicker">Latest forecast</div>
        <h3>No prediction stored yet</h3>
        <p class="ll-card-copy">The next forecast will appear here once it has been generated and committed.</p>
    </div>
</div>
"""

st.markdown(
    '<div class="ll-two-card-grid">' + state_html + pred_html + '</div>',
    unsafe_allow_html=True,
)


st.markdown(
    f"""
<div class="ll-footer">
    LatentLap · F1 2026 telemetry analytics · Data through Round {latest_completed_round} · Built on FastF1<br>
    Public telemetry and results are observed inputs. Derived, inferred, assumed, optimised and predicted outputs are labelled by role.
</div>
    """,
    unsafe_allow_html=True,
)
