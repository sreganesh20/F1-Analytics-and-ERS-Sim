"""pages/4_Upgrades_and_News.py — LatentLap · Upgrades & Development."""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (
    TEAM_COLOURS,
    current_round,
    get_upgrade_timeline,
)
from app.ui import inject_global_css, page_header, section_header


st.set_page_config(
    page_title="Upgrades & Development — LatentLap",
    page_icon="🛠️",
    layout="wide",
)
inject_global_css()


CATEGORY_LABELS = {
    "persistent": "Persistent development",
    "circuit_specific": "Circuit-specific",
    "reliability": "Reliability",
    "power_unit": "PU / ADUO",
}

CATEGORY_HELP = {
    "persistent": (
        "A lasting chassis or aero change carried forward beyond one event."
    ),
    "circuit_specific": (
        "A track-range, cooling or aero configuration chosen for one circuit."
    ),
    "reliability": (
        "Cooling, structural or reliability work without a defensible persistent pace step."
    ),
    "power_unit": (
        "Power-unit homologation / ADUO context, kept separate from chassis-aero development."
    ),
}

SIGNIFICANCE_ORDER = {
    "power_unit": 4,
    "new_car": 4,
    "major": 3,
    "medium": 2,
    "moderate": 2,
    "minor": 1,
}

SIGNIFICANCE_LABELS = {
    "power_unit": "PU",
    "new_car": "New car",
    "major": "Major",
    "medium": "Moderate",
    "moderate": "Moderate",
    "minor": "Minor",
}


def _event_category(event: dict) -> str:
    if event.get("pu"):
        return "power_unit"
    return event.get("category", "persistent")


def _meaningful(event: dict) -> bool:
    category = _event_category(event)
    significance = event.get("significance", "minor")
    if category == "power_unit":
        return True
    if category != "persistent":
        return False
    return SIGNIFICANCE_ORDER.get(significance, 1) >= 2


def _source_label(event: dict) -> str:
    source = (event.get("source") or "").strip()
    if source:
        return source
    if event.get("pu"):
        return "LatentLap canonical PU / ADUO configuration"
    return "LatentLap canonical upgrade inventory"


def _team_order(events: list[dict]) -> list[str]:
    teams = sorted({event["team"] for event in events})
    return sorted(
        teams,
        key=lambda team: (
            -max(
                (
                    SIGNIFICANCE_ORDER.get(event.get("significance", "minor"), 1)
                    for event in events
                    if event["team"] == team
                ),
                default=0,
            ),
            team,
        ),
    )


def _timeline_figure(events: list[dict]):
    if not events:
        return None

    teams = _team_order(events)
    team_to_y = {team: idx for idx, team in enumerate(teams)}

    fig = go.Figure()

    for event in events:
        team = event["team"]
        category = _event_category(event)
        significance = event.get("significance", "minor")
        size = {
            4: 18,
            3: 15,
            2: 12,
            1: 9,
        }.get(SIGNIFICANCE_ORDER.get(significance, 1), 9)

        colour = TEAM_COLOURS.get(team, "#8d98a8")
        symbol = {
            "persistent": "circle",
            "circuit_specific": "diamond-open",
            "reliability": "square-open",
            "power_unit": "star",
        }.get(category, "circle")

        fig.add_trace(
            go.Scatter(
                x=[event["round"]],
                y=[team],
                mode="markers",
                marker=dict(
                    size=size,
                    color=colour,
                    symbol=symbol,
                    line=dict(
                        color="#d7dde6",
                        width=0.7,
                    ),
                    opacity=0.95 if not event.get("incoming") else 0.5,
                ),
                customdata=[[
                    CATEGORY_LABELS.get(category, category),
                    event.get("headline", ""),
                    event.get("detail", ""),
                    SIGNIFICANCE_LABELS.get(significance, significance.title()),
                    event.get("circuit", ""),
                ]],
                hovertemplate=(
                    "<b>%{y}</b> · R%{x} · %{customdata[4]}"
                    "<br>%{customdata[0]} · %{customdata[3]}"
                    "<br>%{customdata[1]}"
                    "<br>%{customdata[2]}"
                    "<extra></extra>"
                ),
                showlegend=False,
            )
        )

    fig.update_layout(
        height=max(480, 44 * len(teams) + 90),
        margin=dict(l=10, r=25, t=10, b=45),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d9b2b5", size=14),
        xaxis=dict(
            title="Round",
            dtick=1,
            gridcolor="rgba(255,255,255,0.06)",
            zeroline=False,
        ),
        yaxis=dict(
            title=None,
            categoryorder="array",
            categoryarray=list(reversed(teams)),
            gridcolor="rgba(255,255,255,0.035)",
        ),
    )
    return fig


def _event_table(events: list[dict]) -> pd.DataFrame:
    rows = []
    for event in events:
        category = _event_category(event)
        significance = event.get("significance", "minor")
        rows.append(
            {
                "Round": f"R{event['round']}",
                "Circuit": event.get("circuit", "—"),
                "Team": event["team"],
                "Type": CATEGORY_LABELS.get(category, category),
                "Significance": SIGNIFICANCE_LABELS.get(
                    significance,
                    significance.replace("_", " ").title(),
                ),
                "Change": event.get("headline", ""),
                "Status": "Upcoming" if event.get("incoming") else "Confirmed",
            }
        )
    return pd.DataFrame(rows)


def _source_groups(events: list[dict]):
    groups = defaultdict(list)
    for event in events:
        source = _source_label(event)
        label = (
            f"R{event['round']} · {event['team']} · "
            f"{event.get('headline', '')}"
        )
        groups[source].append(label)
    return groups


page_header(
    "Car development",
    "Upgrades & Development",
    "Follow how the 2026 cars have changed, while keeping lasting development separate from circuit-specific, reliability and power-unit work.",
)

events = get_upgrade_timeline()
if not events:
    st.warning("No upgrade history is available.")
    st.stop()

now_round = current_round()
confirmed = [event for event in events if not event.get("incoming")]
incoming = [event for event in events if event.get("incoming")]
meaningful = [event for event in confirmed if _meaningful(event)]
persistent = [
    event
    for event in confirmed
    if _event_category(event) == "persistent"
]
power_unit = [
    event
    for event in confirmed
    if _event_category(event) == "power_unit"
]

m1, m2, m3, m4 = st.columns(4, gap="medium")
m1.metric("Analysed through", f"R{now_round}")
m2.metric("Confirmed changes", len(confirmed))
m3.metric("Persistent development", len(persistent))
m4.metric("PU / ADUO events", len(power_unit))

section_header(
    "How to read it",
    "Not every new part means the car permanently got faster",
    "LatentLap keeps four kinds of technical change separate so a one-race configuration is not mistaken for a lasting development step.",
)

c1, c2, c3, c4 = st.columns(4, gap="medium")
for column, category in zip(
    (c1, c2, c3, c4),
    ("persistent", "circuit_specific", "reliability", "power_unit"),
):
    with column:
        with st.container(border=True):
            st.markdown(f"**{CATEGORY_LABELS[category]}**")
            st.write(CATEGORY_HELP[category])

timeline_tab, team_tab, sources_tab = st.tabs(
    ["Season timeline", "Team drill-down", "Sources"]
)

# ============================================================
# SEASON TIMELINE
# ============================================================
with timeline_tab:
    section_header(
        "Season view",
        "What changed, and when?",
        "The default view shows meaningful persistent development plus power-unit steps. Open the full inventory to see every declared circuit-specific and reliability change.",
    )

    show_full = st.toggle(
        "Show full declared inventory",
        value=False,
        help=(
            "Off = moderate/major persistent development + PU/ADUO. "
            "On = every confirmed circuit-specific, reliability and minor change too."
        ),
    )

    timeline_events = confirmed if show_full else meaningful

    fig = _timeline_figure(timeline_events)
    if fig is not None:
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
        )

    st.caption(
        "Circle = persistent development · open diamond = circuit-specific · "
        "open square = reliability · star = PU / ADUO. Marker size reflects reviewed significance."
    )

    st.dataframe(
        _event_table(
            sorted(
                timeline_events,
                key=lambda event: (
                    -event["round"],
                    event["team"],
                ),
            )
        ),
        use_container_width=True,
        hide_index=True,
        height=min(660, 36 * len(timeline_events) + 40),
    )

    if incoming:
        with st.expander(
            f"Upcoming / planned items ({len(incoming)})"
        ):
            st.dataframe(
                _event_table(incoming),
                use_container_width=True,
                hide_index=True,
            )

# ============================================================
# TEAM DRILL-DOWN
# ============================================================
with team_tab:
    teams = sorted({event["team"] for event in events})
    selected_team = st.selectbox(
        "Team",
        teams,
        key="upgrade_team",
    )

    team_events = [
        event
        for event in events
        if event["team"] == selected_team
    ]
    team_confirmed = [
        event
        for event in team_events
        if not event.get("incoming")
    ]

    st.markdown(f"## {selected_team}")

    counts = defaultdict(int)
    for event in team_confirmed:
        counts[_event_category(event)] += 1

    t1, t2, t3, t4 = st.columns(4, gap="medium")
    t1.metric("Persistent", counts["persistent"])
    t2.metric("Circuit-specific", counts["circuit_specific"])
    t3.metric("Reliability", counts["reliability"])
    t4.metric("PU / ADUO", counts["power_unit"])

    important = sorted(
        [
            event
            for event in team_confirmed
            if _meaningful(event)
        ],
        key=lambda event: (
            -event["round"],
            -SIGNIFICANCE_ORDER.get(
                event.get("significance", "minor"),
                1,
            ),
        ),
    )

    section_header(
        "Key development",
        "Meaningful changes first",
        "These are the persistent chassis/aero steps rated moderate or major, plus PU / ADUO events. This ordering is for readability, not a claim of measured lap-time gain.",
    )

    if important:
        for event in important:
            category = _event_category(event)
            significance = event.get("significance", "minor")
            with st.container(border=True):
                head_a, head_b = st.columns([4, 1])
                with head_a:
                    st.markdown(
                        f"### R{event['round']} · {event.get('circuit', '')}"
                    )
                    st.markdown(f"**{event.get('headline', '')}**")
                with head_b:
                    st.markdown(
                        f"**{SIGNIFICANCE_LABELS.get(significance, significance.title())}**"
                    )
                    st.caption(
                        CATEGORY_LABELS.get(category, category)
                    )

                detail = event.get("detail", "")
                if detail:
                    st.write(detail)

                st.caption(
                    f"Source · {_source_label(event)}"
                )
    else:
        st.info(
            "No moderate/major persistent or PU development event is stored for this team yet."
        )

    with st.expander("Full team inventory"):
        st.dataframe(
            _event_table(
                sorted(
                    team_events,
                    key=lambda event: -event["round"],
                )
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown(
        """
<div class="ll-ai-hook">
    <div>
        <strong>Ask what an upgrade actually changed</strong>
        <span>Ask the Engineer can explain the declared package, the timing and the performance context without inventing a lap-time gain.</span>
    </div>
    <a class="ll-cta ll-cta-primary" href="/Ask_the_Engineer" target="_self">Ask the Engineer</a>
</div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# SOURCES
# ============================================================
with sources_tab:
    section_header(
        "Provenance",
        "Where the upgrade inventory comes from",
        "Official F1/FIA-style weekend declarations are the inventory backbone. Technical reporting adds context and significance where useful.",
    )

    source_groups = _source_groups(confirmed)

    st.metric(
        "Distinct source labels",
        len(source_groups),
    )

    for source, labels in sorted(
        source_groups.items(),
        key=lambda item: item[0].lower(),
    ):
        with st.expander(
            f"{source} · {len(labels)} item{'s' if len(labels) != 1 else ''}"
        ):
            for label in labels:
                st.markdown(f"- {label}")

    st.caption(
        "Power-unit / ADUO events are sourced from LatentLap's canonical PU configuration and are kept separate from chassis/aero declarations."
    )
