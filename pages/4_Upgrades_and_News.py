"""
pages/4_Upgrades_and_News.py — Team upgrade timeline + race commentary
"""

import os, sys
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.data_loader import (get_upgrade_timeline, get_commentary,
                              upgrade_card, SIG_COLOURS)
from app.charts import upgrade_timeline_chart
from app.data_loader import TEAM_COLOURS

st.set_page_config(page_title="Upgrades & News — ERS_v2", page_icon="📰", layout="wide")
ACCENT = '<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);border-radius:2px;margin-bottom:1rem;"></div>'
st.markdown(ACCENT, unsafe_allow_html=True)
st.title("📰 Upgrades & News")

# ── Filters ───────────────────────────────────────────────
all_teams = sorted({"Mercedes", "Ferrari", "McLaren", "Red Bull", "Aston Martin",
                    "VCARB", "Haas", "Alpine", "Williams", "Audi", "Cadillac",
                    "Honda"})

col1, col2 = st.columns([2, 3])
with col1:
    show_incoming = st.checkbox("Show upcoming upgrades ⚠️", value=True)
with col2:
    team_filter = st.multiselect("Filter teams", all_teams, default=all_teams)

upgrades = get_upgrade_timeline()
filtered = [u for u in upgrades
            if u["team"] in team_filter
            and (show_incoming or not u["incoming"])]

# ── Timeline chart ────────────────────────────────────────
st.subheader("📅 Upgrade Timeline")
ALL_TEAMS = sorted({"Mercedes","Ferrari","McLaren","Red Bull","Aston Martin",
                    "VCARB","Haas","Alpine","Williams","Audi","Cadillac"})
fig = upgrade_timeline_chart(filtered, all_teams=ALL_TEAMS)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "● Confirmed upgrade  ◆ Upcoming upgrade  |  "
    + "  ".join(
        f'<span style="color:{c};">■ {s.replace("_"," ").title()}</span>'
        for s, c in SIG_COLOURS.items()
    ),
    unsafe_allow_html=True,
)

st.divider()

# ── Upgrade details ───────────────────────────────────────
st.subheader("🔧 Upgrade Details")

# Upcoming first
upcoming = [u for u in reversed(filtered) if u["incoming"]]
confirmed = [u for u in reversed(filtered) if not u["incoming"]]

if upcoming:
    st.markdown("**Upcoming**")
    for u in upcoming:
        st.markdown(upgrade_card(u), unsafe_allow_html=True)
    st.markdown("")

if confirmed:
    st.markdown("**Confirmed (latest first)**")
    for u in confirmed:
        st.markdown(upgrade_card(u), unsafe_allow_html=True)

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
