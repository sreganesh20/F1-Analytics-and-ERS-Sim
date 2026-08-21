"""
app/charts.py — Plotly interactive charts for ERS_v2 Streamlit app.
All return go.Figure ready for st.plotly_chart().
"""

import numpy as np
import plotly.graph_objects as go
from collections import defaultdict

from app.data_loader import (PU_COLOURS, TEAM_COLOURS, PU_ORDER,
                              FACTORY_TEAMS, SIG_COLOURS,
                              get_circuits_with_data)

# ── Dark layout base (NO xaxis/yaxis here — pass per chart to avoid duplicate kwarg crash)
DARK = dict(
    paper_bgcolor="#0F0F0F",
    plot_bgcolor="#1A1A1A",
    font=dict(color="#E0E0E0", family="monospace", size=11),
    legend=dict(bgcolor="#1A1A1A", bordercolor="#2A2A2A", borderwidth=1),
    margin=dict(l=60, r=60, t=70, b=60),
)

def _ax():
    """Shared dark axis style."""
    return dict(gridcolor="#2A2A2A", zerolinecolor="#444", linecolor="#333")

def _hex_rgba(hex_col, alpha=0.08):
    """Convert #RRGGBB to rgba(r,g,b,alpha) — Plotly doesn't support 8-digit hex."""
    h = hex_col.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Season evolution ──────────────────────────────────────

def season_evolution_chart(fps, sessions=None):
    sessions = sessions or ["Q", "R"]
    filtered = [fp for fp in fps if fp.session_type in sessions and fp.confidence >= 0.5]
    circuit_map = get_circuits_with_data()

    data_best = defaultdict(lambda: defaultdict(list))
    data_all  = defaultdict(lambda: defaultdict(list))
    for fp in filtered:
        data_all[fp.pu_name][fp.race_round].append(fp.lap_time_gap_pct)
        if fp.team in FACTORY_TEAMS.get(fp.pu_name, []):
            data_best[fp.pu_name][fp.race_round].append(fp.lap_time_gap_pct)

    all_rounds = sorted({r for d in data_best.values() for r in d})
    fig = go.Figure()

    for pu in PU_ORDER:
        if pu not in data_best:
            continue
        colour = PU_COLOURS[pu]
        rounds = sorted(data_best[pu].keys())
        bests  = [np.min(data_best[pu][r]) for r in rounds]
        worsts = [np.max(data_all[pu].get(r, [0])) for r in rounds]
        labels = [circuit_map.get(r, f"R{r}") for r in rounds]

        fig.add_trace(go.Scatter(
            x=rounds + rounds[::-1],
            y=worsts + bests[::-1],
            fill="toself",
            fillcolor=_hex_rgba(colour, 0.12),
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False, hoverinfo="skip",
        ))
        fig.add_trace(go.Scatter(
            x=rounds, y=bests,
            mode="lines+markers", name=pu,
            line=dict(color=colour, width=2.5),
            marker=dict(size=7, color=colour),
            customdata=list(zip(labels, [f"{b:.3f}%" for b in bests])),
            hovertemplate=f"<b>{pu}</b><br>R%{{x}} — %{{customdata[0]}}<br>Gap: %{{customdata[1]}}<extra></extra>",
        ))

    tick_labels = [circuit_map.get(r, f"R{r}")[:3].upper() for r in all_rounds]
    fig.update_layout(
        **DARK,
        title=dict(text="PU Performance Evolution — Best Car per PU<br>"
                        "<sup style='color:#888'>Baseline: fastest car of each session (0%). "
                        "Lower = closer to session-topping pace.</sup>",
                   font=dict(size=14)),
        xaxis=dict(**_ax(), title="Race Round",
                   tickmode="array", tickvals=all_rounds, ticktext=tick_labels),
        yaxis=dict(**_ax(), title="Lap Time Gap to Leader (%)", autorange="reversed"),
        hovermode="x unified", height=420,
    )
    return fig


# ── Harvest bars ──────────────────────────────────────────

def harvest_bars_chart(fps, sessions=None):
    sessions = sessions or ["R"]
    filtered = [fp for fp in fps if fp.session_type in sessions and fp.confidence >= 0.5]
    driver_data = defaultdict(lambda: {"ratios": [], "pu": "", "team": ""})
    for fp in filtered:
        driver_data[fp.driver_code]["ratios"].append(fp.braking_harvest_ratio)
        driver_data[fp.driver_code]["pu"]   = fp.pu_name
        driver_data[fp.driver_code]["team"] = fp.team

    sorted_d = sorted(
        driver_data.items(),
        key=lambda x: (PU_ORDER.index(x[1]["pu"]) if x[1]["pu"] in PU_ORDER else 99,
                       -np.mean(x[1]["ratios"]))
    )
    fig = go.Figure()
    for pu in PU_ORDER:
        items = [(d, v) for d, v in sorted_d if v["pu"] == pu]
        if not items:
            continue
        colour = PU_COLOURS[pu]
        drivers = [d for d, _ in items]
        means   = [np.mean(v["ratios"]) for _, v in items]
        stds    = [np.std(v["ratios"]) if len(v["ratios"]) > 1 else 0.0 for _, v in items]
        teams   = [v["team"] for _, v in items]
        ns      = [len(v["ratios"]) for _, v in items]
        fig.add_trace(go.Bar(
            y=drivers, x=means, orientation="h", name=pu,
            marker_color=colour, opacity=0.85,
            error_x=dict(type="data", array=stds,
                        color="rgba(255,255,255,0.35)", thickness=1.5, width=4),
            customdata=list(zip(teams, [f"{m:.3f}" for m in means], ns)),
            hovertemplate="<b>%{y}</b> — %{customdata[0]}<br>Ratio: %{customdata[1]}<br>Rounds: %{customdata[2]}<extra></extra>",
        ))

    fig.add_vline(x=1.0, line_dash="dash", line_color="rgba(255,255,255,0.3)",
                  annotation_text="Theoretical Max",
                  annotation_font_color="rgba(255,255,255,0.4)",
                  annotation_position="top right")
    all_means = [np.mean(v["ratios"]) for _, v in sorted_d if v["ratios"]]
    fig.update_layout(
        **DARK,
        title=dict(text="ERS Braking Harvest Efficiency", font=dict(size=14)),
        xaxis=dict(**_ax(), title="Braking Harvest Ratio",
                   range=[0.5, (max(all_means) + 0.12) if all_means else 1.1]),
        yaxis=dict(**_ax(), autorange="reversed"),
        barmode="overlay",
        height=max(420, len(sorted_d) * 30 + 120),
    )
    return fig


# ── Fingerprint radar ──────────────────────────────────────

def fingerprint_radar_chart(fps):
    filtered = [fp for fp in fps if fp.session_type == "R" and fp.confidence >= 0.5]
    pu_data = defaultdict(lambda: defaultdict(list))
    for fp in filtered:
        if fp.team in FACTORY_TEAMS.get(fp.pu_name, []):
            pu_data[fp.pu_name]["gap"].append(fp.lap_time_gap_pct)
            pu_data[fp.pu_name]["hrv"].append(fp.braking_harvest_ratio)
            pu_data[fp.pu_name]["str"].append(fp.straight_speed_delta_kph)
            pu_data[fp.pu_name]["brk"].append(fp.braking_speed_delta_kph)

    present = [pu for pu in PU_ORDER if pu in pu_data]
    if not present:
        return go.Figure()

    raw = {pu: [
        float(np.min(pu_data[pu]["gap"])) if pu_data[pu]["gap"] else 0,
        float(np.mean(pu_data[pu]["hrv"])) if pu_data[pu]["hrv"] else 0,
        float(np.mean(pu_data[pu]["str"])) if pu_data[pu]["str"] else 0,
        float(np.mean(pu_data[pu]["brk"])) if pu_data[pu]["brk"] else 0,
    ] for pu in present}

    arr = np.array([raw[pu] for pu in present])
    norm_axes = []
    for j, invert in enumerate([True, False, False, False]):
        col = -arr[:, j] if invert else arr[:, j]
        vmin, vmax = col.min(), col.max()
        if vmax - vmin < 1e-6:
            norm_axes.append(np.full(len(present), 0.5))
        else:
            norm_axes.append(0.1 + 0.9 * (col - vmin) / (vmax - vmin))
    norm_arr = np.stack(norm_axes, axis=1)

    categories = ["Pace (gap%)", "Harvest Ratio", "Straight Speed Δ", "Braking Speed Δ", "Pace (gap%)"]
    fig = go.Figure()
    for i, pu in enumerate(present):
        vals = norm_arr[i].tolist() + [norm_arr[i][0]]
        colour = PU_COLOURS[pu]
        r_raw = raw[pu]
        fig.add_trace(go.Scatterpolar(
            r=vals, theta=categories,
            fill="toself", name=pu,
            line=dict(color=colour, width=2.5),
            fillcolor=_hex_rgba(colour, 0.12),
            customdata=[[f"{r_raw[0]:.3f}%", f"{r_raw[1]:.3f}", f"{r_raw[2]:+.1f}kph", f"{r_raw[3]:+.1f}kph"] + [""]] * len(vals),
        ))
    fig.update_layout(
        paper_bgcolor="#0F0F0F",
        font=dict(color="#E0E0E0", family="monospace", size=11),
        polar=dict(
            bgcolor="#1A1A1A",
            radialaxis=dict(visible=True, range=[0, 1], gridcolor="#2A2A2A", showticklabels=False),
            angularaxis=dict(gridcolor="#2A2A2A", tickfont=dict(color="#E0E0E0", size=11)),
        ),
        legend=dict(bgcolor="#1A1A1A", bordercolor="#2A2A2A"),
        title=dict(text="ERS PU Fingerprint — Factory Teams Only", font=dict(size=14)),
        height=480,
    )
    return fig


# ── PU straight-line speed ────────────────────────────────

def pu_straight_speed_chart(fps):
    """Factory team straight-line speed per PU across rounds."""
    circuit_map = get_circuits_with_data()
    filtered = [fp for fp in fps
                if fp.session_type in ("Q", "SQ") and fp.confidence >= 0.5
                and fp.team in FACTORY_TEAMS.get(fp.pu_name, [])]

    data = defaultdict(lambda: defaultdict(list))
    for fp in filtered:
        data[fp.pu_name][fp.race_round].append(fp.straight_speed_delta_kph)

    all_rounds = sorted({fp.race_round for fp in filtered})
    fig = go.Figure()

    for pu in PU_ORDER:
        if pu not in data:
            continue
        colour = PU_COLOURS[pu]
        rounds = sorted(data[pu].keys())
        avgs   = [np.mean(data[pu][r]) for r in rounds]
        labels = [circuit_map.get(r, f"R{r}") for r in rounds]
        fig.add_trace(go.Scatter(
            x=rounds, y=avgs, mode="lines+markers", name=pu,
            line=dict(color=colour, width=2.5),
            marker=dict(size=7, color=colour),
            customdata=list(zip(labels, [f"{a:+.1f} kph" for a in avgs])),
            hovertemplate=f"<b>{pu}</b><br>R%{{x}} %{{customdata[0]}}<br>Str delta: %{{customdata[1]}}<extra></extra>",
        ))

    tick_labels = [circuit_map.get(r, f"R{r}")[:3].upper() for r in all_rounds]
    fig.update_layout(
        **DARK,
        title=dict(text="Straight-Line Speed Delta — Factory Teams (Qualifying)<br>"
                        "<sup style='color:#888'>Baseline: fastest car of each session = 0. "
                        "Positive = faster than that session's reference on the straights.</sup>",
                   font=dict(size=14)),
        xaxis=dict(**_ax(), title="Round",
                   tickmode="array", tickvals=all_rounds, ticktext=tick_labels),
        yaxis=dict(**_ax(), title="Speed delta vs session leader (kph)"),
        height=380,
        annotations=[dict(
            text="⚠ Signal = combined PU output + chassis drag — not ICE-only",
            xref="paper", yref="paper", x=0, y=-0.18,
            showarrow=False, font=dict(color="#666", size=9)
        )],
    )
    return fig


# ── Straight vs corner scatter ────────────────────────────

def straight_vs_corner_scatter(fps):
    """11 teams: straight speed delta vs corner speed delta (qualifying)."""
    team_data = defaultdict(lambda: {"str": [], "cor": [], "pu": ""})
    filtered = [fp for fp in fps if fp.session_type in ("Q", "SQ") and fp.confidence >= 0.5]
    for fp in filtered:
        team_data[fp.team]["str"].append(fp.straight_speed_delta_kph)
        team_data[fp.team]["cor"].append(fp.corner_speed_delta_kph)
        team_data[fp.team]["pu"] = fp.pu_name

    if not team_data:
        return go.Figure()

    teams   = list(team_data.keys())
    # Median, not mean. On the current store, mean gives rho=+0.600 against
    # overall pace and puts Audi (7th-fastest car) top of the corner ranking;
    # median gives rho=+0.927 and a defensible order.
    str_avg = [np.median(team_data[t]["str"]) if team_data[t]["str"] else 0 for t in teams]
    cor_avg = [np.median(team_data[t]["cor"]) if team_data[t]["cor"] else 0 for t in teams]
    colours = [TEAM_COLOURS.get(t, PU_COLOURS.get(team_data[t]["pu"], "#888")) for t in teams]
    n_rdns  = [len(team_data[t]["str"]) for t in teams]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=str_avg, y=cor_avg,
        mode="markers+text",
        text=teams,
        textposition="top center",
        textfont=dict(size=9, color="#E0E0E0"),
        marker=dict(
            color=colours,
            size=[max(10, n * 1.5) for n in n_rdns],
            line=dict(color="rgba(255,255,255,0.5)", width=1),
        ),
        customdata=list(zip(teams, [team_data[t]["pu"] for t in teams],
                           [f"{v:+.1f}" for v in str_avg],
                           [f"{v:+.1f}" for v in cor_avg], n_rdns)),
        hovertemplate=(
            "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
            "Straight: %{customdata[2]} kph Δ<br>"
            "Corner: %{customdata[3]} kph Δ<br>"
            "Rounds: %{customdata[4]}<extra></extra>"
        ),
        showlegend=False,
    ))

    fig.add_hline(y=0, line_color="#333", line_width=1)
    fig.add_vline(x=0, line_color="#333", line_width=1)

    all_x = str_avg + [0]; all_y = cor_avg + [0]
    x_pad = (max(all_x) - min(all_x)) * 0.15 or 5
    y_pad = (max(all_y) - min(all_y)) * 0.15 or 2

    for label, x_frac, y_frac in [
        ("Closest to reference",     0.78, 0.88),
        ("Corner-biased",            0.15, 0.88),
        ("Straight-line biased",     0.78, 0.12),
        ("Furthest from reference",  0.15, 0.12),
    ]:
        x_pos = min(all_x) - x_pad + (max(all_x) - min(all_x) + 2*x_pad) * x_frac
        y_pos = min(all_y) - y_pad + (max(all_y) - min(all_y) + 2*y_pad) * y_frac
        fig.add_annotation(x=x_pos, y=y_pos, text=label,
                          font=dict(color="#333", size=9), showarrow=False)

    fig.update_layout(
        **DARK,
        title=dict(text="2026 — Team Performance Profile: Straight vs Corner<br>"
                        "<sup style='color:#888'>Baseline: session-fastest car = 0. All values are season "
                        "averages of per-session deltas — negative is normal (the reference is the fastest car).</sup>",
                   font=dict(size=14)),
        xaxis=dict(**_ax(), title="Straight-line speed vs session-fastest car (kph)"),
        yaxis=dict(**_ax(), title="Corner speed vs session-fastest car (kph)"),
        height=500,
    )
    return fig


# ── Corner profile ranking ────────────────────────────────

def corner_profile_ranking(fps):
    """All 11 teams ranked by corner speed delta (qualifying)."""
    team_data = defaultdict(lambda: {"cor": [], "pu": ""})
    filtered = [fp for fp in fps if fp.session_type in ("Q", "SQ") and fp.confidence >= 0.5]
    for fp in filtered:
        team_data[fp.team]["cor"].append(fp.corner_speed_delta_kph)
        team_data[fp.team]["pu"] = fp.pu_name

    # Median across sessions — see straight_vs_corner_scatter for why.
    sorted_t = sorted(team_data.items(),
                      key=lambda x: -np.median(x[1]["cor"]) if x[1]["cor"] else 0)
    teams   = [t for t, _ in sorted_t]
    cors    = [np.median(v["cor"]) if v["cor"] else 0 for _, v in sorted_t]
    colours = [PU_COLOURS.get(v["pu"], "#888") for _, v in sorted_t]
    ns      = [len(v["cor"]) for _, v in sorted_t]

    fig = go.Figure(go.Bar(
        y=teams, x=cors, orientation="h",
        marker_color=colours,
        customdata=[(f"{c:+.1f} kph", v["pu"], n) for (_, v), c, n in zip(sorted_t, cors, ns)],
        hovertemplate="<b>%{y}</b><br>Corner delta: %{customdata[0]}<br>PU: %{customdata[1]}<br>Rounds: %{customdata[2]}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#555", line_width=1)
    fig.update_layout(
        **DARK,
        title=dict(text="Corner Performance Ranking — All Teams (Qualifying)<br>"
                        "<sup style='color:#888'>Baseline: session-fastest car = 0. "
                        "Less negative = closer to reference pace in corners. "
                        "Median across sessions.<br>"
                        "Corners are fixed distance windows taken from the session's "
                        "fastest lap, so cars braking at materially different points "
                        "are compared imperfectly.</sup>",
                   font=dict(size=14)),
        xaxis=dict(**_ax(), title="Corner speed vs session-fastest car (kph, median)"),
        yaxis=dict(**_ax(), autorange="reversed"),
        height=420,
    )
    return fig


# ── Teammate comparison ───────────────────────────────────

def teammate_gap_chart(fps, driver1, driver2, circuit_map, team_colour="#FF1E00"):
    """Per-round qualifying gap: driver1 vs driver2. Shows seconds and %."""
    d1 = {fp.race_round: fp for fp in fps
          if fp.driver_code == driver1 and fp.session_type in ("Q", "SQ")}
    d2 = {fp.race_round: fp for fp in fps
          if fp.driver_code == driver2 and fp.session_type in ("Q", "SQ")}
    common = sorted(set(d1) & set(d2))
    if not common:
        return go.Figure()

    gaps_s   = [d1[r].lap_time_s - d2[r].lap_time_s for r in common]
    gaps_pct = [d1[r].lap_time_gap_pct - d2[r].lap_time_gap_pct for r in common]
    labels   = [circuit_map.get(r, f"R{r}") for r in common]
    colours  = [team_colour if g < 0 else "#3A3A3A" for g in gaps_s]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=gaps_s,
        marker_color=colours,
        customdata=[(f"{g:+.3f}s", f"{p:+.3f}%", driver1 if g < 0 else driver2)
                    for g, p in zip(gaps_s, gaps_pct)],
        hovertemplate=(
            "<b>%{x}</b><br>"
            "%{customdata[0]} (%{customdata[1]})<br>"
            "%{customdata[2]} faster<extra></extra>"
        ),
        name="Gap",
    ))
    fig.add_hline(y=0, line_color="#888", line_width=1)
    fig.update_layout(
        **DARK,
        title=dict(
            text=f"Qualifying H2H: {driver1} vs {driver2}",
            font=dict(size=14),
        ),
        xaxis=dict(**_ax()),
        yaxis=dict(**_ax(), title=f"Lap time gap: {driver1} − {driver2} (s)"),
        height=320,
        annotations=[dict(
            text=f"Negative = {driver1} faster  |  Positive = {driver2} faster",
            xref="paper", yref="paper", x=0, y=-0.18,
            showarrow=False, font=dict(color="#888", size=9)
        )],
    )
    return fig


# ── Pace trend ────────────────────────────────────────────

def pace_trend_chart(fps, driver_code):
    circuit_map = get_circuits_with_data()
    d_fps = [fp for fp in fps if fp.driver_code == driver_code]
    q_fps = sorted([fp for fp in d_fps if fp.session_type in ("Q", "SQ")], key=lambda f: f.race_round)
    r_fps = sorted([fp for fp in d_fps if fp.session_type in ("R", "S")],  key=lambda f: f.race_round)

    fig = go.Figure()
    for data, name, colour in [(q_fps, "Qualifying", "#00D2BE"), (r_fps, "Race Pace", "#FF8000")]:
        if data:
            labels = [circuit_map.get(f.race_round, f"R{f.race_round}") for f in data]
            fig.add_trace(go.Scatter(
                x=[f.race_round for f in data],
                y=[f.lap_time_gap_pct for f in data],
                mode="lines+markers", name=name,
                line=dict(color=colour, width=2.5), marker=dict(size=8, color=colour),
                customdata=list(zip(labels, [f"{f.lap_time_gap_pct:.3f}%" for f in data])),
                hovertemplate=f"<b>%{{customdata[0]}}</b><br>{name}: %{{customdata[1]}}<extra></extra>",
            ))
    fig.update_layout(
        **DARK,
        title=dict(text=f"{driver_code} — 2026 Pace Trend", font=dict(size=13)),
        xaxis=dict(**_ax(), title="Round"),
        yaxis=dict(**_ax(), title="Gap to Leader (%)", autorange="reversed"),
        height=320,
    )
    return fig


# ── ERS Strategy charts ───────────────────────────────────

def strategy_chart(optimal):
    segs = optimal.segments
    fig = go.Figure()

    h_segs = [s for s in segs if s.optimal_harvest > 0.001]
    d_segs = [s for s in segs if s.optimal_deploy  > 0.001]

    if h_segs:
        fig.add_trace(go.Bar(
            name="Harvest (MJ)",
            x=[f"{s.d_start:.0f}m" for s in h_segs],
            y=[s.optimal_harvest for s in h_segs],
            marker_color="#00C851", opacity=0.85,
            customdata=[(s.seg_type, s.max_harvest) for s in h_segs],
            hovertemplate="<b>%{x}</b> (%{customdata[0]})<br>Harvest: %{y:.3f} MJ (max: %{customdata[1]:.3f})<extra></extra>",
        ))
    if d_segs:
        fig.add_trace(go.Bar(
            name="Deploy (MJ)",
            x=[f"{s.d_start:.0f}m" for s in d_segs],
            y=[-s.optimal_deploy for s in d_segs],
            marker_color="#FF4444", opacity=0.85,
            customdata=[(s.seg_type, s.max_deploy) for s in d_segs],
            hovertemplate="<b>%{x}</b> (%{customdata[0]})<br>Deploy: %{y:.3f} MJ (max: %{customdata[1]:.3f})<extra></extra>",
        ))

    soc_x = [f"{s.d_start:.0f}m" for s in segs]
    soc_y = [s.soc_entry for s in segs]
    if segs:
        soc_x.append(f"{segs[-1].d_end:.0f}m")
        soc_y.append(segs[-1].soc_exit)
    fig.add_trace(go.Scatter(
        x=soc_x, y=soc_y, name="Battery SoC",
        line=dict(color="#FFD700", width=2, dash="dot"),
        yaxis="y2",
        hovertemplate="SoC: %{y:.3f} MJ<extra></extra>",
    ))

    fig.update_layout(
        **DARK,
        title=dict(
            text=f"ERS Strategy — {optimal.circuit_name} [{optimal.session_type}]  "
                 f"· Harvest limit: {optimal.harvest_limit_mj:.1f} MJ",
            font=dict(size=13)
        ),
        xaxis=dict(**_ax(), title="Lap distance"),
        yaxis=dict(**_ax(), title="Energy (MJ)", zeroline=True, zerolinecolor="#555"),
        yaxis2=dict(title="Battery SoC (MJ)", overlaying="y", side="right",
                    range=[-0.1, 4.3], gridcolor="#2A2A2A", color="#FFD700"),
        barmode="overlay", height=400,
    )
    return fig


def soc_flow_chart(optimal):
    segs = optimal.segments
    x, y = [], []
    for s in segs:
        x += [s.d_start, s.d_end]
        y += [s.soc_entry, s.soc_exit]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines",
        name="Battery SoC",
        fill="tozeroy",
        fillcolor=_hex_rgba("#FFD700", 0.10),
        line=dict(color="#FFD700", width=2.5),
        hovertemplate="Distance: %{x:.0f}m<br>SoC: %{y:.3f} MJ<extra></extra>",
    ))
    fig.add_hrect(y0=0, y1=0.2, fillcolor=_hex_rgba("#FF4444", 0.15), line_width=0,
                  annotation_text="Critical", annotation_position="right",
                  annotation_font_color="#FF4444")
    fig.update_layout(
        **DARK,
        title=dict(text="Battery SoC — Lap Profile", font=dict(size=13)),
        xaxis=dict(**_ax(), title="Distance (m)"),
        yaxis=dict(**_ax(), title="Battery SoC (MJ)", range=[-0.1, 4.3]),
        height=280,
    )
    return fig


# ── Upgrade timeline ──────────────────────────────────────

def upgrade_timeline_chart(events, all_teams=None):
    """Show all teams on Y axis even if they have no upgrades."""
    if all_teams is None:
        all_teams = sorted({"Mercedes", "Ferrari", "McLaren", "Red Bull", "Aston Martin",
                            "VCARB", "Haas", "Alpine", "Williams", "Audi", "Cadillac"})

    team_y = {t: i for i, t in enumerate(all_teams)}
    fig = go.Figure()

    # Legend entries
    for sig, colour in SIG_COLOURS.items():
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(color=colour, size=10, symbol="circle"),
            name=sig.replace("_", " ").title(), showlegend=True,
        ))

    for u in events:
        if u["team"] not in team_y:
            continue
        colour = SIG_COLOURS.get(u["significance"], "#888")
        symbol = "diamond-open" if u["incoming"] else "circle"
        size   = 18 if u["significance"] == "new_car" else 14 if u["significance"] == "major" else 10
        note   = u["note"][:90] + "..." if len(u["note"]) > 90 else u["note"]
        fig.add_trace(go.Scatter(
            x=[u["round"]], y=[team_y[u["team"]]],
            mode="markers", showlegend=False,
            marker=dict(color=colour, size=size, symbol=symbol,
                       line=dict(color=colour, width=2)),
            customdata=[(u["circuit"], u["significance"].replace("_", " ").upper(), note)],
            hovertemplate=(
                f"<b>{u['team']}</b> — R{u['round']} %{{customdata[0]}}<br>"
                "<b>%{customdata[1]}</b><br>%{customdata[2]}<extra></extra>"
            ),
        ))

    fig.update_layout(
        paper_bgcolor="#0F0F0F", plot_bgcolor="#1A1A1A",
        font=dict(color="#E0E0E0", family="monospace"),
        title=dict(text="2026 — Team Upgrade Timeline (All 11 Teams)", font=dict(size=14)),
        xaxis=dict(title="Race Round", gridcolor="#2A2A2A", dtick=1, range=[0.5, 24]),
        yaxis=dict(tickmode="array", tickvals=list(team_y.values()),
                   ticktext=list(team_y.keys()), gridcolor="#2A2A2A"),
        legend=dict(bgcolor="#1A1A1A", bordercolor="#2A2A2A"),
        height=max(450, len(all_teams) * 55 + 100),
        margin=dict(l=130, r=40, t=70, b=60),
        hovermode="closest",
    )
    return fig


# ── WAVE 3: Corner performance by speed class (season aggregate) ──

MIN_CLASS_SAMPLES = 8   # minimum fingerprint datapoints season-wide for a class to be shown


def corner_class_ranking(fps):
    """
    Team ranking within each corner speed class (slow / medium / fast),
    aggregated across ALL qualifying sessions of the season.

    Honesty rules (user decision 13 Aug):
    - Season-aggregate ONLY — never per-circuit corner counts (detection is
      throttle/brake-based; flat-out corners are invisible, so per-circuit
      counts are not publishable facts).
    - A class with < MIN_CLASS_SAMPLES datapoints is suppressed (fast corners
      are systematically under-detected — a ranking built on 3 points is noise).
    Returns (figure, suppressed_classes) so the page can explain gaps.
    """
    field_map = {
        "slow":   "corner_slow_delta_kph",
        "medium": "corner_medium_delta_kph",
        "fast":   "corner_fast_delta_kph",
    }
    quali = [fp for fp in fps if fp.session_type in ("Q", "SQ") and fp.confidence >= 0.5]

    class_team_vals = {c: defaultdict(list) for c in field_map}
    team_pu = {}
    for fp in quali:
        team_pu[fp.team] = fp.pu_name
        for cls, field in field_map.items():
            val = getattr(fp, field, None)
            if val is not None:
                class_team_vals[cls][fp.team].append(val)

    shown, suppressed = [], []
    for cls in ("slow", "medium", "fast"):
        n_total = sum(len(v) for v in class_team_vals[cls].values())
        (shown if n_total >= MIN_CLASS_SAMPLES else suppressed).append(cls)

    if not shown:
        return go.Figure(), suppressed

    fig = go.Figure()
    class_offsets = {c: i for i, c in enumerate(shown)}
    class_labels  = {"slow": "Slow (<130 kph)", "medium": "Medium (130–210)", "fast": "Fast (>210)"}
    class_colours = {"slow": "#FF4444", "medium": "#FFD700", "fast": "#00C851"}

    # Order teams by slow-corner performance (or first shown class).
    # Median across sessions: class buckets hold fewer corners per lap than
    # the aggregate, so a single mis-segmented corner distorts a mean badly
    # (slow-corner deltas reach +318 kph on individual laps).
    order_cls = shown[0]
    team_order = sorted(class_team_vals[order_cls].keys(),
                        key=lambda t: -np.median(class_team_vals[order_cls][t]))

    for cls in shown:
        vals   = class_team_vals[cls]
        teams  = [t for t in team_order if t in vals]
        means  = [np.median(vals[t]) for t in teams]
        ns     = [len(vals[t]) for t in teams]
        fig.add_trace(go.Bar(
            y=teams, x=means, orientation="h",
            name=class_labels[cls],
            marker_color=class_colours[cls], opacity=0.85,
            customdata=list(zip([f"{m:+.1f} kph" for m in means], ns)),
            hovertemplate="<b>%{y}</b> — " + class_labels[cls] +
                          "<br>Median delta: %{customdata[0]}<br>"
                          "Corners sampled: %{customdata[1]}<extra></extra>",
        ))

    fig.update_layout(
        **DARK,
        title=dict(
            text="Corner Performance by Speed Class — Season Aggregate<br>"
                 "<sup style='color:#888'>Baseline: session-fastest car = 0 · Qualifying only · "
                 "Median across sessions<br>"
                 "Detection is throttle/brake-based — flat-out corners not captured, so the "
                 "fast bucket skews negative for the whole field.<br>"
                 "Corners are fixed distance windows from the session's fastest lap; cars "
                 "braking at different points are compared imperfectly.</sup>",
            font=dict(size=14)),
        xaxis=dict(**_ax(), title="Corner speed vs session-fastest car (kph, median)"),
        yaxis=dict(**_ax(), autorange="reversed"),
        barmode="group",
        height=max(450, len(team_order) * 38 + 140),
    )
    return fig, suppressed


# ── WAVE 3: Driver finishing position across season ───────

def finish_history_chart(history, driver_code, team_colour="#FF1E00"):
    """Finishing position per round. DNF/NC plotted as a red X at the bottom."""
    rounds  = [r for r, _ in history]
    circuit_map = get_circuits_with_data()
    fin_r   = [r for r, p in history if p is not None]
    fin_p   = [p for _, p in history if p is not None]
    dnf_r   = [r for r, p in history if p is None]

    fig = go.Figure()
    if fin_r:
        fig.add_trace(go.Scatter(
            x=fin_r, y=fin_p, mode="lines+markers", name="Finish",
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
    fig.add_hrect(y0=0.5, y1=3.5, fillcolor=_hex_rgba("#FFD700", 0.08),
                  line_width=0, annotation_text="Podium",
                  annotation_font_color="#FFD700", annotation_position="top left")

    ticks = sorted(set(rounds))
    fig.update_layout(
        **DARK,
        title=dict(text=f"{driver_code} — Finishing Position by Round", font=dict(size=13)),
        xaxis=dict(**_ax(), title="Round", tickmode="array", tickvals=ticks,
                   ticktext=[circuit_map.get(r, f"R{r}")[:3].upper() for r in ticks]),
        yaxis=dict(**_ax(), title="Finishing position", autorange="reversed",
                   range=[22, 0], dtick=2),
        height=340,
    )
    return fig


def qualifying_ranking_chart(ranking):
    """All drivers ranked by average qualifying gap to pole."""
    drivers = [r["driver"] for r in ranking]
    gaps    = [r["avg_gap"] for r in ranking]
    colours = [TEAM_COLOURS.get(r["team"], "#888") for r in ranking]

    fig = go.Figure(go.Bar(
        y=drivers, x=gaps, orientation="h", marker_color=colours,
        customdata=[(r["team"], f"{r['avg_gap']:.3f}%", f"{r['best_gap']:.3f}%",
                     r["sessions"]) for r in ranking],
        hovertemplate=("<b>%{y}</b> — %{customdata[0]}<br>"
                       "Avg gap: %{customdata[1]}<br>Best: %{customdata[2]}<br>"
                       "Sessions: %{customdata[3]}<extra></extra>"),
    ))
    fig.update_layout(
        **DARK,
        title=dict(text="Qualifying Pace Ranking — Average Gap to Pole<br>"
                        "<sup style='color:#888'>Lower is better · all Q and SQ sessions</sup>",
                   font=dict(size=14)),
        xaxis=dict(**_ax(), title="Average gap to session pole (%)"),
        yaxis=dict(**_ax(), autorange="reversed"),
        height=max(460, len(drivers) * 26 + 130),
    )
    return fig


def teammate_hierarchy_chart(ranking):
    """Intra-team qualifying gaps, biggest margin first. Colour = team."""
    labels = [f"{r['faster']} vs {r['slower']}" for r in ranking]
    gaps   = [r["gap_s"] for r in ranking]
    cols   = [TEAM_COLOURS.get(r["team"], "#888") for r in ranking]

    fig = go.Figure(go.Bar(
        y=labels, x=gaps, orientation="h", marker_color=cols,
        text=[f"{g:.3f}s" for g in gaps], textposition="outside",
        textfont=dict(color="#E0E0E0", size=11),
        customdata=[(r["team"], r["faster"], r["faster_wins"], r["rounds"],
                     f"{r['gap_pct']:.3f}%") for r in ranking],
        hovertemplate=("<b>%{customdata[0]}</b><br>"
                       "%{customdata[1]} faster by %{x:.3f}s (%{customdata[4]})<br>"
                       "H2H: %{customdata[2]}/%{customdata[3]} rounds<extra></extra>"),
    ))
    fig.update_layout(
        **DARK,
        title=dict(text="Intra-Team Qualifying Battle — Margin of Dominance<br>"
                        "<sup style='color:#888'>Widest gap at top · faster driver named first</sup>",
                   font=dict(size=14)),
        xaxis=dict(**_ax(), title="Median qualifying gap between teammates (s)"),
        yaxis=dict(**_ax(), autorange="reversed"),
        height=max(400, len(labels) * 42 + 130),
    )
    return fig
