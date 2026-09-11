"""pages/1_Predictions.py — LatentLap · expected pace forecasts."""

from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analysis.llm import available as ai_available, explain_prediction
from app.data_loader import (
    TEAM_COLOURS,
    get_prediction_data,
    list_available_predictions,
)
from app.ui import inject_global_css, page_header, section_header
from config import CIRCUITS, DRIVER_SUBSTITUTIONS, GRID_PENALTIES


st.set_page_config(
    page_title="Predictions — LatentLap",
    page_icon="🔮",
    layout="wide",
)
inject_global_css()


SESSION_TABS = {
    "sprint_quali": ("Sprint Qualifying", "Friday · expected one-lap pace"),
    "sprint_race": ("Sprint", "Saturday · expected sprint pace"),
    "quali": ("Qualifying", "Expected one-lap pace"),
    "race": ("Race", "Expected grand prix pace"),
}
SPRINT_ORDER = ["sprint_quali", "sprint_race", "quali", "race"]
NORMAL_ORDER = ["quali", "race"]

SPRINT_PROVENANCE = (
    "Sprint forecasts pool sprint-session evidence with Grand Prix-session evidence, "
    "while weighting the matching sprint session type more heavily. This is deliberate "
    "rather than a fallback: sprint-only history is still sparse."
)


def _confidence_label(value: float) -> str:
    if value >= 0.70:
        return "High"
    if value >= 0.55:
        return "Medium"
    return "Low"


def _collect_footnotes(predictions):
    order_seen = []
    by_text = {}

    for row in predictions:
        for note in row.get("regulation_notes", []):
            warn = note.startswith("⚠")
            text = note.lstrip("⚠").strip()

            if text not in by_text:
                by_text[text] = {
                    "warn": warn,
                    "drivers": [],
                }
                order_seen.append(text)

            by_text[text]["drivers"].append(row["driver_code"])
            by_text[text]["warn"] = by_text[text]["warn"] or warn

    return [
        {
            "text": text,
            "warn": by_text[text]["warn"],
            "drivers": by_text[text]["drivers"],
        }
        for text in order_seen
    ]


def _weekend_note_summary(subs: dict, penalties: dict) -> str:
    parts = []
    if penalties:
        parts.append(
            f"{len(penalties)} grid/pit-lane "
            + ("penalty" if len(penalties) == 1 else "penalties")
        )
    if subs.get("banner"):
        parts.append("1 lineup change")
    return " · ".join(parts) if parts else "No special weekend notes"


def _display_team(code: str, row: dict, subs: dict) -> str:
    moved = subs.get("moved", {})
    return moved.get(code, row.get("team", "—"))


def _prediction_rows(pred: dict, subs: dict, pred_type: str):
    unavailable = subs.get("unavailable", {})
    rows = []
    pos = 0

    for row in pred.get("predictions", []):
        code = row["driver_code"]
        if code in unavailable:
            out_row = {
                "Pos": "OUT",
                "Driver": code,
                "Team": _display_team(code, row, subs),
                "Expected pace": unavailable[code],
                "Uncertainty": "—",
                "Confidence": "—",
                "History": row.get("n_races_used", "—"),
            }
            if pred_type in ("quali", "sprint_quali"):
                out_row["Harvest signal"] = "—"
            rows.append(out_row)
            continue

        pos += 1
        delta = float(row.get("predicted_delta_s", 0.0) or 0.0)
        low = float(row.get("delta_range_low", delta) or delta)
        high = float(row.get("delta_range_high", delta) or delta)
        uncertainty = max(abs(delta - low), abs(high - delta))
        conf = float(row.get("confidence", 0.0) or 0.0)

        out_row = {
            "Pos": f"P{pos}",
            "Driver": code,
            "Team": _display_team(code, row, subs),
            "Expected pace": (
                "0.000s"
                if pos == 1
                else f"+{delta:.3f}s"
            ),
            "Uncertainty": f"±{uncertainty:.3f}s",
            "Confidence": f"{_confidence_label(conf)} · {conf:.0%}",
            "History": row.get("n_races_used", "—"),
        }

        if pred_type in ("quali", "sprint_quali"):
            harvest = row.get("predicted_harvest_ratio")
            out_row["Harvest signal"] = (
                f"{float(harvest):.3f}"
                if harvest is not None and float(harvest) < 1.5
                else "—"
            )

        rows.append(out_row)

    predicted_codes = {
        row["driver_code"]
        for row in pred.get("predictions", [])
    }
    for extra in subs.get("added", []):
        if extra["code"] in predicted_codes:
            continue
        extra_row = {
            "Pos": "—",
            "Driver": extra["code"],
            "Team": extra["team"],
            "Expected pace": "No model history",
            "Uncertainty": "—",
            "Confidence": "—",
            "History": 0,
        }
        if pred_type in ("quali", "sprint_quali"):
            extra_row["Harvest signal"] = "—"
        rows.append(extra_row)

    return rows


def _render_weekend_notes(subs: dict, penalties: dict):
    summary = _weekend_note_summary(subs, penalties)

    with st.expander(f"Weekend notes · {summary}"):
        if subs.get("banner"):
            st.markdown(f"**Lineup:** {subs['banner']}")

        if penalties:
            for code, pen in penalties.items():
                timing = (
                    "Known when forecast was saved"
                    if pen.get("known_at_prediction_time")
                    else "Later weekend update"
                )
                st.markdown(
                    f"**{code} · {pen.get('penalty', 'Penalty')}**  \n"
                    f"{pen.get('note', '')}  \n"
                    f"*{timing}. Penalties affect the start, not the pace ranking.*"
                )

        if not subs.get("banner") and not penalties:
            st.write("No lineup or penalty notes are stored for this round.")


def _render_prediction(pred: dict, pred_type: str, subs: dict):
    predictions = pred.get("predictions", [])
    if not predictions:
        st.info("This session has no stored prediction rows.")
        return

    label, subtitle = SESSION_TABS[pred_type]
    overall = float(pred.get("overall_confidence", 0.0) or 0.0)
    history = pred.get("n_historical_races", 0)

    st.markdown(f"## {label}")
    st.caption(subtitle)

    if pred_type.startswith("sprint_"):
        st.caption(SPRINT_PROVENANCE)

    c1, c2, c3 = st.columns(3, gap="medium")
    c1.metric(
        "Model confidence",
        f"{_confidence_label(overall)} · {overall:.0%}",
    )
    c2.metric(
        "Historical sessions",
        history,
        "after weighting/filtering",
    )
    c3.metric(
        "Prediction type",
        "Expected pace",
        "not finishing order",
    )

    rows = _prediction_rows(pred, subs, pred_type)
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        height=min(760, 36 * len(rows) + 40),
    )

    st.caption(
        "Position is the model's expected pace order. Uncertainty is shown in seconds around the expected delta. "
        "Incidents, safety cars, strategy calls and reliability are not part of the pace forecast."
    )

    if pred_type in ("quali", "sprint_quali"):
        st.caption(
            "Harvest signal is an inferred qualifying braking-energy behaviour input used by the model. "
            "It is not measured recovered energy, battery state or electrical efficiency."
        )

    if ai_available():
        section_header(
            "Explain",
            "Why does LatentLap think this?",
            "Pick one driver. The explanation uses this saved forecast and its own model evidence; it does not change the ranking.",
        )

        codes = [
            row["driver_code"]
            for row in predictions
            if row["driver_code"] not in subs.get("unavailable", {})
        ]
        if codes:
            a, b = st.columns([1.2, 1], gap="large")
            with a:
                target = st.selectbox(
                    "Driver",
                    codes,
                    key=f"pred_explain_driver_{pred_type}",
                )
            with b:
                st.write("")
                st.write("")
                clicked = st.button(
                    "Explain this prediction",
                    key=f"pred_explain_button_{pred_type}",
                    type="primary",
                    use_container_width=True,
                )

            if clicked:
                with st.spinner("Reading the saved model evidence…"):
                    text, err = explain_prediction(pred, target)
                if err:
                    st.info(err)
                else:
                    with st.container(border=True):
                        st.markdown(f"**Why {target} is here**")
                        st.markdown(text)
                        st.caption(
                            "The saved prediction grid remains the source of truth."
                        )

    methodology = pred.get("methodology_notes", [])
    if methodology:
        with st.expander("How this forecast was built"):
            st.markdown(
                "\n".join(
                    f"- {note}"
                    for note in methodology
                )
            )

            circuit_cfg = CIRCUITS.get(pred.get("circuit_name"), {})
            if circuit_cfg.get("note"):
                st.markdown(
                    f"**Circuit note:** {circuit_cfg['note']}"
                )

    footnotes = _collect_footnotes(predictions)
    if footnotes:
        with st.expander("Model and regulation notes"):
            for note in footnotes:
                drivers = ", ".join(note["drivers"])
                prefix = "⚠ " if note["warn"] else ""
                st.markdown(
                    f"**{prefix}{drivers}** — {note['text']}"
                )


page_header(
    "Forecasts",
    "Predictions",
    "Expected pace, not crystal-ball finishing order. LatentLap ranks the likely relative pace and shows the uncertainty around it.",
)

circuits = list_available_predictions()
if not circuits:
    st.warning("No stored predictions are available yet.")
    st.stop()

circuit = st.selectbox(
    "Weekend",
    circuits,
    index=len(circuits) - 1,
)

cfg = CIRCUITS.get(circuit, {})
is_sprint = bool(cfg.get("has_sprint"))
order = SPRINT_ORDER if is_sprint else NORMAL_ORDER

preds = {
    pred_type: get_prediction_data(
        circuit,
        pred_type=pred_type,
    )
    for pred_type in order
}
preds = {
    pred_type: pred
    for pred_type, pred in preds.items()
    if pred
}

if not preds:
    st.error(f"No stored prediction data found for {circuit}.")
    st.stop()

ref = next(iter(preds.values()))
round_num = ref.get("race_round")
subs = DRIVER_SUBSTITUTIONS.get(round_num, {})
penalties = GRID_PENALTIES.get(round_num, {})

m1, m2, m3 = st.columns(3, gap="medium")
m1.metric("Round", f"R{round_num}")
m2.metric(
    "Circuit type",
    str(ref.get("circuit_type", "—")).replace("_", " ").title(),
)
m3.metric(
    "Weekend format",
    "Sprint weekend" if is_sprint else "Standard weekend",
)

_render_weekend_notes(subs, penalties)

tab_labels = [
    SESSION_TABS[pred_type][0]
    for pred_type in preds
]
tabs = st.tabs(tab_labels)

for tab, pred_type in zip(tabs, preds):
    with tab:
        _render_prediction(
            preds[pred_type],
            pred_type,
            subs,
        )
