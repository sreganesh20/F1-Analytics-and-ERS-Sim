"""Session-aware season charts for Teams & Drivers.

GP season trends use Q and R only. Teammate H2H intentionally uses both Q and
SQ, but keeps those sessions distinct and exposes the sample size.
"""

import plotly.graph_objects as go

from app.charts import DARK, _ax
from app.data_loader import TEAM_COLOURS, get_circuits_with_data


def pace_trend_chart(fps, driver_code):
    circuit_map = get_circuits_with_data()
    d_fps = [fp for fp in fps if fp.driver_code == driver_code]
    q_fps = sorted([fp for fp in d_fps if fp.session_type == "Q"], key=lambda f: f.race_round)
    r_fps = sorted([fp for fp in d_fps if fp.session_type == "R"], key=lambda f: f.race_round)

    fig = go.Figure()
    for data, name, colour in (
        (q_fps, "GP Qualifying", "#00D2BE"),
        (r_fps, "Grand Prix Pace", "#FF8000"),
    ):
        if not data:
            continue
        labels = [circuit_map.get(f.race_round, f"R{f.race_round}") for f in data]
        fig.add_trace(
            go.Scatter(
                x=[f.race_round for f in data],
                y=[f.lap_time_gap_pct for f in data],
                mode="lines+markers",
                name=name,
                line=dict(color=colour, width=2.5),
                marker=dict(size=8, color=colour),
                customdata=list(zip(labels, [f"{f.lap_time_gap_pct:.3f}%" for f in data])),
                hovertemplate=f"<b>%{{customdata[0]}}</b><br>{name}: %{{customdata[1]}}<extra></extra>",
            )
        )

    rounds = sorted({f.race_round for f in q_fps + r_fps})
    fig.update_layout(
        **DARK,
        title=dict(text=f"{driver_code} — 2026 GP Pace Trend", font=dict(size=13)),
        xaxis=dict(
            **_ax(), title="Round", tickmode="array", tickvals=rounds,
            ticktext=[circuit_map.get(r, f"R{r}")[:3].upper() for r in rounds],
        ),
        yaxis=dict(**_ax(), title="Gap to session leader (%)", autorange="reversed"),
        height=320,
    )
    return fig


def finish_history_chart(history, driver_code, team_colour="#FF1E00"):
    """Grand Prix finishing position by round; Sprint results are excluded."""
    rounds = [r for r, _ in history]
    circuit_map = get_circuits_with_data()
    fin_r = [r for r, p in history if p is not None]
    fin_p = [p for _, p in history if p is not None]
    dnf_r = [r for r, p in history if p is None]

    fig = go.Figure()
    if fin_r:
        fig.add_trace(go.Scatter(
            x=fin_r, y=fin_p, mode="lines+markers", name="Grand Prix finish",
            line=dict(color=team_colour, width=2.5),
            marker=dict(size=9, color=team_colour),
            customdata=[circuit_map.get(r, f"R{r}") for r in fin_r],
            hovertemplate="<b>%{customdata}</b><br>Finished P%{y}<extra></extra>",
        ))
    if dnf_r:
        fig.add_trace(go.Scatter(
            x=dnf_r, y=[21] * len(dnf_r), mode="markers", name="DNF / NC",
            marker=dict(size=13, color="#FF4444", symbol="x", line=dict(width=2)),
            customdata=[circuit_map.get(r, f"R{r}") for r in dnf_r],
            hovertemplate="<b>%{customdata}</b><br>Did not finish<extra></extra>",
        ))
    fig.add_hrect(
        y0=0.5, y1=3.5, fillcolor="rgba(255,215,0,0.08)", line_width=0,
        annotation_text="Podium", annotation_font_color="#FFD700",
        annotation_position="top left",
    )
    ticks = sorted(set(rounds))
    fig.update_layout(
        **DARK,
        title=dict(text=f"{driver_code} — Grand Prix Finishing Position by Round", font=dict(size=13)),
        xaxis=dict(
            **_ax(), title="Round", tickmode="array", tickvals=ticks,
            ticktext=[circuit_map.get(r, f"R{r}")[:3].upper() for r in ticks],
        ),
        yaxis=dict(**_ax(), title="Finishing position", autorange="reversed", range=[22, 0], dtick=2),
        height=340,
    )
    return fig


def teammate_gap_chart(fps, driver1, driver2, circuit_map, team_colour="#FF1E00"):
    """Overall same-team Q+SQ gap, with Q/SQ shown as separate observations."""
    d1 = {
        (fp.race_round, fp.session_type): fp
        for fp in fps
        if fp.driver_code == driver1 and fp.session_type in ("Q", "SQ")
    }
    d2 = {
        (fp.race_round, fp.session_type): fp
        for fp in fps
        if fp.driver_code == driver2 and fp.session_type in ("Q", "SQ")
    }
    order = {"SQ": 0, "Q": 1}
    common = sorted(
        (key for key in set(d1) & set(d2) if d1[key].team == d2[key].team),
        key=lambda key: (key[0], order.get(key[1], 99)),
    )
    if not common:
        return go.Figure()

    gaps_s = [d1[key].lap_time_s - d2[key].lap_time_s for key in common]
    gaps_pct = [d1[key].lap_time_gap_pct - d2[key].lap_time_gap_pct for key in common]
    labels = [
        f"{circuit_map.get(r, f'R{r}')[:3].upper()} {session}"
        for r, session in common
    ]
    colours = [team_colour if gap < 0 else "#3A3A3A" for gap in gaps_s]

    fig = go.Figure(go.Bar(
        x=labels, y=gaps_s, marker_color=colours,
        customdata=[
            (f"{gap:+.3f}s", f"{pct:+.3f}%", driver1 if gap < 0 else driver2)
            for gap, pct in zip(gaps_s, gaps_pct)
        ],
        hovertemplate=(
            "<b>%{x}</b><br>%{customdata[0]} (%{customdata[1]})<br>"
            "%{customdata[2]} faster<extra></extra>"
        ),
        name="Gap",
    ))
    fig.add_hline(y=0, line_color="#888", line_width=1)
    fig.update_layout(
        **DARK,
        title=dict(text=f"Qualifying H2H: {driver1} vs {driver2}", font=dict(size=14)),
        xaxis=dict(**_ax()),
        yaxis=dict(**_ax(), title=f"Lap time gap: {driver1} − {driver2} (s)"),
        height=320,
        annotations=[dict(
            text=f"Negative = {driver1} faster | Positive = {driver2} faster · Q and SQ shown separately",
            xref="paper", yref="paper", x=0, y=-0.20, showarrow=False,
            font=dict(color="#888", size=9),
        )],
    )
    return fig


def teammate_hierarchy_chart(ranking):
    """Overall Q+SQ median gaps for every teammate era seen this season."""
    labels = [f"{r['faster']} vs {r['slower']} · {r.get('round_label', '')}" for r in ranking]
    gaps = [r["gap_s"] for r in ranking]
    cols = [TEAM_COLOURS.get(r["team"], "#888") for r in ranking]
    fig = go.Figure(go.Bar(
        y=labels, x=gaps, orientation="h", marker_color=cols,
        text=[f"{gap:.3f}s" for gap in gaps], textposition="outside",
        textfont=dict(color="#E0E0E0", size=11),
        customdata=[
            (
                r["team"], r["faster"], r["faster_wins"], r["slower_wins"],
                r["sessions"], r["weekends"], f"{r['gap_pct']:.3f}%",
                "Limited sample" if r.get("limited_sample") else "Established sample",
                r.get("round_label", ""),
                "Current pairing" if r.get("current_pairing") else "Earlier pairing",
            )
            for r in ranking
        ],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "%{customdata[1]} faster by %{x:.3f}s (%{customdata[6]})<br>"
            "H2H: %{customdata[2]}–%{customdata[3]} · "
            "%{customdata[4]} sessions / %{customdata[5]} weekends<br>"
            "%{customdata[8]} · %{customdata[9]} · %{customdata[7]}<extra></extra>"
        ),
    ))
    fig.update_layout(
        **DARK,
        title=dict(
            text=(
                "Intra-Team Qualifying Battle — Overall Q + SQ Median Gap<br>"
                "<sup style='color:#888'>Every teammate era is retained after lineup changes; "
                "session and weekend counts show the evidence behind each H2H.</sup>"
            ),
            font=dict(size=14),
        ),
        xaxis=dict(**_ax(), title="Median qualifying gap between teammates (s)"),
        yaxis=dict(**_ax(), autorange="reversed"),
        height=max(400, len(labels) * 42 + 130),
    )
    return fig
