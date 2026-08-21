"""
pages/4_Upgrades_and_News.py — Team upgrade timeline + race commentary
"""

import os, sys
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (get_upgrade_timeline, get_commentary,
                              upgrade_card, upgrade_group_card,
                              team_display_order, SIG_COLOURS, TEAM_COLOURS)
from app.charts import upgrade_timeline_chart
from config import CARS

st.set_page_config(page_title="Upgrades & News — PitWall", page_icon="📰", layout="wide")
ACCENT = '<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);border-radius:2px;margin-bottom:1rem;"></div>'
st.markdown(ACCENT, unsafe_allow_html=True)
st.title("📰 Upgrades & News")
st.caption("Chassis and power unit developments across the 2026 season, with sources. Upcoming entries are announced but not yet raced.")

# ── Filters ───────────────────────────────────────────────
#
# Team list comes from CARS, not a hardcoded set. The old list included
# "Honda", which is a power unit manufacturer rather than a team — it put a
# twelfth row on a chart of eleven and made a PU upgrade look like a team's
# own development.
ALL_TEAMS = sorted({c["team"] for c in CARS.values()})

upgrades = get_upgrade_timeline()

col1, col2 = st.columns([3, 2])
with col1:
    # Single dropdown rather than a multiselect pre-filled with every team,
    # which rendered eleven chips and pushed the chart below the fold.
    team_choice = st.selectbox("Team", ["All teams"] + ALL_TEAMS, index=0)
with col2:
    show_incoming = st.checkbox("Include upcoming upgrades", value=True)

filtered = [u for u in upgrades
            if (team_choice == "All teams" or u["team"] == team_choice)
            and (show_incoming or not u["incoming"])]

# ── Timeline chart ────────────────────────────────────────
st.subheader("📅 Upgrade Timeline")
chart_teams = ALL_TEAMS if team_choice == "All teams" else [team_choice]
fig = upgrade_timeline_chart(filtered, all_teams=chart_teams)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "● Confirmed  ◆ Upcoming  |  "
    + "  ".join(
        f'<span style="color:{c};">■ {sig.replace("_"," ").title()}</span>'
        for sig, c in SIG_COLOURS.items()
    )
    + "  |  Power unit upgrades appear on every customer team, so one "
      "manufacturer homologation can show on three rows.",
    unsafe_allow_html=True,
)

st.divider()

# ── Upgrade details ───────────────────────────────────────
st.subheader("🔧 Upgrade Details")

upcoming  = [u for u in reversed(filtered) if u["incoming"]]
confirmed = [u for u in filtered if not u["incoming"]]

# Upcoming stays a flat list — there are only a handful and they are the
# thing people came to read.
if upcoming:
    st.markdown("**Upcoming**")
    for u in upcoming:
        st.markdown(upgrade_card(u), unsafe_allow_html=True)
    st.markdown("")

# Confirmed is grouped per team in two columns. As one flat list it was 27
# stacked cards — several screens of scrolling with no way to see what any
# one team had done across the season.
if confirmed:
    st.markdown("**Confirmed** — newest first within each team")

    by_team = {}
    for u in confirmed:
        by_team.setdefault(u["team"], []).append(u)

    ordered = team_display_order(by_team.keys())
    cols    = st.columns(2)

    for i, team in enumerate(ordered):
        rows    = by_team[team]
        chassis = sorted([r for r in rows if not r.get("pu")],
                         key=lambda r: -r["round"])
        power   = sorted([r for r in rows if r.get("pu")],
                         key=lambda r: -r["round"])
        with cols[i % 2]:
            st.markdown(
                upgrade_group_card(team, chassis, power,
                                   colour=TEAM_COLOURS.get(team, "#888")),
                unsafe_allow_html=True)

st.divider()

# ── Commentary ─────────────────────────────────────────────
st.subheader("📖 Race Commentary")
commentary = get_commentary()

if not commentary:
    st.info("No commentary yet. Edit `data/commentary.json` to add race summaries.")
else:
    tag_options = sorted({tag for entry in commentary for tag in entry.get("tags", [])})
    tag_filter  = st.multiselect("Filter by tag", tag_options, default=[])

    for entry in reversed(commentary):
        tags = entry.get("tags", [])
        if tag_filter and not any(t in tags for t in tag_filter):
            continue

        tag_html = " ".join(
            f'<code style="font-size:0.7rem;color:#888;background:#1A1A1A;'
            f'padding:1px 5px;border-radius:3px;">{t}</code>'
            for t in tags
        )
        with st.expander(
            f"R{entry['round']} {entry['circuit']} · {entry['headline']}",
            expanded=False
        ):
            st.markdown(entry.get("body", ""))
            if tag_html:
                st.markdown(tag_html, unsafe_allow_html=True)
            st.caption(entry.get("date", ""))
