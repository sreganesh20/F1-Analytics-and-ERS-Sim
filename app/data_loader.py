"""
app/data_loader.py
Shared data loading and caching for the Streamlit app.

Wave 1 correctness notes:
- the latest analytical round is derived from store/index.json;
- driver/team identity is round-aware;
- teammate statistics only compare fingerprints produced for the same team;
- the upgrade timeline reads the canonical upgrade history;
- stored stint data is exposed without changing the fingerprint schema.
"""

import json
import os
import sys
from collections import defaultdict

import numpy as np
import requests
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from data.race_store import (  # noqa: E402
    load_all_fingerprints as _load_all,
    load_index,
    load_stint_data as _load_stint_data,
    load_session_results as _load_session_results,
)
from data.upgrade_history import UPGRADE_HISTORY  # noqa: E402
from config import (  # noqa: E402
    CARS,
    CIRCUITS,
    DRIVER_SUBSTITUTIONS,
    PU_ADUO_UPGRADES,
    lineup_for_round,
)


def _latest_round_from_index(index: dict | None = None) -> int:
    index = load_index() if index is None else index
    rounds = [int(meta.get("race_round", 0)) for meta in index.values()]
    return max(rounds, default=0)


# Compatibility constant for pages that import it. New logic below uses the
# current cached index where practical rather than relying on this snapshot.
CURRENT_ROUND = _latest_round_from_index()

# ── Colour palettes ──────────────────────────────────────
PU_COLOURS = {
    "Mercedes": "#00D2BE",
    "Ferrari": "#E8002D",
    "RedBullFord": "#3671C6",
    "Honda": "#CC1E4A",
    "Audi": "#B0B0B0",
}
TEAM_COLOURS = {
    "Mercedes": "#00D2BE",
    "McLaren": "#FF8000",
    "Ferrari": "#E8002D",
    "Red Bull": "#3671C6",
    "VCARB": "#6692FF",
    "Aston Martin": "#229971",
    "Alpine": "#FF87BC",
    "Williams": "#64C4FF",
    "Haas": "#B6BABD",
    "Audi": "#B0B0B0",
    "Cadillac": "#C9B037",
}
PU_ORDER = ["Mercedes", "Ferrari", "RedBullFord", "Audi", "Honda"]
SIG_COLOURS = {
    "power_unit": "#00B7FF",
    "new_car": "#FF1E00",
    "major": "#FF8000",
    "medium": "#FFD700",
    "moderate": "#FFD700",
    "minor": "#00C851",
}
FACTORY_TEAMS = {
    "Mercedes": ["Mercedes"],
    "Ferrari": ["Ferrari"],
    "RedBullFord": ["Red Bull"],
    "Honda": ["Aston Martin"],
    "Audi": ["Audi"],
}


# ── Fingerprint / stored-session loading ─────────────────
@st.cache_data(ttl=60)
def get_fingerprints(sessions=None):
    sessions = sessions or ["Q", "R", "S", "SQ"]
    if isinstance(sessions, str):
        sessions = [sessions]
    return [
        fp
        for rf in _load_all(year=2026, sessions=sessions)
        for fp in rf.fingerprints
    ]


@st.cache_data(ttl=60)
def get_store_index():
    return load_index()


def current_round() -> int:
    """Latest round represented in the committed analytical store."""
    return _latest_round_from_index(get_store_index())


@st.cache_data(ttl=60)
def get_circuits_with_data():
    idx = get_store_index()
    result = {}
    for meta in idx.values():
        r = meta["race_round"]
        if r not in result:
            result[r] = meta["circuit_name"]
    return result


@st.cache_data(ttl=60)
def get_sessions_for_round(race_round):
    idx = get_store_index()
    return sorted(
        {
            meta["session_type"]
            for meta in idx.values()
            if meta["race_round"] == race_round
        }
    )


@st.cache_data(ttl=60)
def get_session_results(race_round: int, session: str = "R", year: int = 2026) -> dict:
    """Return the stored official session result roster.

    Unlike fingerprints, this can include an early retirement that never had a
    usable representative pace lap.
    """
    return _load_session_results(year, race_round, session)


@st.cache_data(ttl=60)
def get_stint_data(race_round: int, session: str = "R", year: int = 2026) -> dict:
    """Return stored stint context for one session.

    ``degradation_rate`` is a fitted lap-time trend from the pipeline; it must
    not be presented as directly measured tyre degradation because fuel burn,
    traffic, track evolution and management can contribute to the slope.
    """
    return _load_stint_data(year, race_round, session)


# ── Standings ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_driver_standings():
    try:
        r = requests.get(
            "https://api.jolpi.ca/ergast/f1/2026/driverStandings.json", timeout=10
        )
        r.raise_for_status()
        sl = r.json()["MRData"]["StandingsTable"]["StandingsLists"]
        if not sl:
            return []
        return [
            {
                "pos": int(s["position"]),
                "code": s["Driver"]["code"],
                "name": f"{s['Driver']['givenName']} {s['Driver']['familyName']}",
                "team": s["Constructors"][0]["name"],
                "points": float(s["points"]),
                "wins": int(s["wins"]),
            }
            for s in sl[0]["DriverStandings"]
        ]
    except Exception:
        return []


@st.cache_data(ttl=3600)
def get_constructor_standings():
    try:
        r = requests.get(
            "https://api.jolpi.ca/ergast/f1/2026/constructorStandings.json",
            timeout=10,
        )
        r.raise_for_status()
        sl = r.json()["MRData"]["StandingsTable"]["StandingsLists"]
        if not sl:
            return []
        return [
            {
                "pos": int(s["position"]),
                "team": s["Constructor"]["name"],
                "points": float(s["points"]),
                "wins": int(s["wins"]),
            }
            for s in sl[0]["ConstructorStandings"]
        ]
    except Exception:
        return []


# ── Commentary ────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_commentary():
    path = os.path.join(ROOT, "data", "commentary.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Predictions ───────────────────────────────────────────
@st.cache_data(ttl=60)
def get_prediction_data(circuit_name, pred_type="quali"):
    """Load stored prediction.

    pred_type: ``quali`` | ``race`` | ``sprint_quali`` | ``sprint_race``.
    """
    pred_dir = os.path.join(ROOT, "store", "predictions")
    path = os.path.join(
        pred_dir,
        f"2026_{circuit_name.replace(' ', '_')}_{pred_type}_prediction.json",
    )
    if not os.path.exists(path) and pred_type == "quali":
        path = os.path.join(
            pred_dir, f"2026_{circuit_name.replace(' ', '_')}_prediction.json"
        )
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_available_predictions():
    """Return unique circuit names that have any prediction file."""
    pred_dir = os.path.join(ROOT, "store", "predictions")
    if not os.path.exists(pred_dir):
        return []
    circuits = set()
    for filename in os.listdir(pred_dir):
        if "_prediction.json" not in filename or not filename.startswith("2026_"):
            continue
        name = filename.removeprefix("2026_")
        # Longest first; remove exactly one suffix.
        for suffix in (
            "_sprint_quali_prediction.json",
            "_sprint_race_prediction.json",
            "_quali_prediction.json",
            "_race_prediction.json",
            "_prediction.json",
        ):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        circuits.add(name.replace("_", " "))
    return sorted(circuits)


# ── Upgrade timeline ──────────────────────────────────────
def _round_to_circuit() -> dict[int, str]:
    return {
        cfg["round"]: cfg.get("fastf1_name", "").replace(" Grand Prix", "")
        for cfg in CIRCUITS.values()
    }


def _pu_customer_teams() -> dict[str, set[str]]:
    customers: dict[str, set[str]] = {}
    for car in CARS.values():
        pu = car.get("pu") or car.get("pu_name")
        if pu:
            customers.setdefault(pu, set()).add(car["team"])
    return customers


def _pu_timeline_event(team: str, pu: str, rnd: int, note: str, now_round: int) -> dict:
    parts = note.split(". ")
    return {
        "team": team,
        "round": rnd,
        "circuit": _round_to_circuit().get(rnd, f"R{rnd}"),
        "significance": "power_unit",
        "category": "power_unit",
        "headline": parts[0],
        "detail": " ".join(parts[1:]),
        "source": "",
        "note": note,
        "incoming": rnd > now_round,
        "pu": pu,
        "affects_prediction": True,
    }


def get_upgrade_timeline():
    """Return the canonical chassis/aero + PU development timeline.

    ``incoming`` is derived from the latest round in the analytical store; it
    is not manually maintained in a second upcoming-upgrades dictionary.
    """
    events = []
    round_to_circuit = _round_to_circuit()
    now_round = current_round()

    for upg in UPGRADE_HISTORY:
        rnd = upg["round"]
        headline = upg["headline"]
        detail = upg.get("detail", "")
        events.append(
            {
                "team": upg["team"],
                "round": rnd,
                "circuit": round_to_circuit.get(rnd, f"R{rnd}"),
                "significance": upg["significance"],
                "category": upg.get("category", "persistent"),
                "headline": headline,
                "detail": detail,
                "source": upg.get("source", ""),
                "note": " ".join(x for x in (headline, detail) if x),
                "incoming": upg.get("status") == "planned" or rnd > now_round,
                "pu": None,
                "affects_prediction": upg.get("affects_prediction", False),
                **({"drivers": list(upg["drivers"])} if upg.get("drivers") else {}),
            }
        )

    customers = _pu_customer_teams()
    for pu, upg in PU_ADUO_UPGRADES.items():
        first_round = upg.get("round")
        if first_round is not None:
            for team in sorted(customers.get(pu, [])):
                events.append(
                    _pu_timeline_event(team, pu, first_round, upg["note"], now_round)
                )
        second_round = upg.get("second_round")
        if second_round is not None:
            second_note = upg.get("second_note") or (
                f"{pu} ADUO upgrade 2 deployed at round {second_round}."
            )
            for team in sorted(customers.get(pu, [])):
                events.append(
                    _pu_timeline_event(
                        team, pu, second_round, second_note, now_round
                    )
                )

    return sorted(events, key=lambda x: (x["round"], x["team"], x["headline"]))


# ── HTML helpers ─────────────────────────────────────────
def conf_badge(conf):
    if conf >= 0.70:
        c, t = "#00C851", f"HIGH {conf:.0%}"
    elif conf >= 0.55:
        c, t = "#FFD700", f"MED {conf:.0%}"
    else:
        c, t = "#FF4444", f"LOW {conf:.0%}"
    return (
        f'<span style="background:{c}22;color:{c};border:1px solid {c};'
        f'border-radius:4px;padding:1px 6px;font-family:monospace;font-size:0.75rem;">'
        f"{t}</span>"
    )


def sig_badge(sig):
    c = SIG_COLOURS.get(sig, "#888")
    t = sig.replace("_", " ").upper()
    return (
        f'<span style="background:{c}22;color:{c};border:1px solid {c};'
        f'border-radius:3px;padding:1px 5px;font-family:monospace;font-size:0.7rem;">'
        f"{t}</span>"
    )


def upgrade_card(upg):
    c = SIG_COLOURS.get(upg["significance"], "#888")
    prefix = "⚠️ UPCOMING" if upg["incoming"] else f"R{upg['round']} · {upg['circuit']}"
    pu_tag = (
        f' <span style="font-weight:normal;font-size:0.75rem;color:#00B7FF;">'
        f'· {upg["pu"]} power unit</span>'
        if upg.get("pu")
        else ""
    )
    return f"""
    <div style="border-left:3px solid {c};padding:8px 14px;margin:8px 0;
                background:{c}11;border-radius:0 6px 6px 0;">
        <div style="font-family:monospace;font-size:0.7rem;color:{c};margin-bottom:3px;">
            {prefix} · {upg['significance'].replace('_',' ').upper()}
        </div>
        <div style="font-weight:bold;margin-bottom:4px;">{upg['team']}{pu_tag}</div>
        <div style="font-size:0.83rem;color:#C0C0C0;">{upg['note']}</div>
    </div>"""


def team_display_order(teams):
    """Championship order, falling back to qualifying pace, then alphabetical."""
    teams = list(teams)
    try:
        standings = get_constructor_standings()
    except Exception:
        standings = []
    if standings:
        rank = {row["team"]: row["pos"] for row in standings}

        def pos(team):
            if team in rank:
                return rank[team]
            for name, p in rank.items():
                if name.lower().startswith(team.lower()[:4]) or team.lower().startswith(
                    name.lower()[:4]
                ):
                    return p
            return 99

        if sum(1 for team in teams if pos(team) < 99) >= len(teams) // 2:
            return sorted(teams, key=lambda team: (pos(team), team))

    try:
        fps = get_fingerprints()
        gaps = {}
        for fp in fps:
            if fp.session_type == "Q" and fp.lap_time_gap_pct is not None:
                gaps.setdefault(fp.team, []).append(fp.lap_time_gap_pct)
        if gaps:
            med = {team: float(np.median(values)) for team, values in gaps.items()}
            return sorted(teams, key=lambda team: (med.get(team, 99), team))
    except Exception:
        pass
    return sorted(teams)


def upgrade_group_card(team, chassis, power, colour="#888"):
    """One team's confirmed upgrades as a single box, newest first."""

    def entry(event, mono_width="66px"):
        sig = event["significance"]
        c = SIG_COLOURS.get(sig, "#888")
        pill = (
            ""
            if sig == "power_unit"
            else (
                f'<span style="background:{c}22;color:{c};border:1px solid {c}55;'
                f'font-size:0.62rem;padding:0 5px;border-radius:3px;'
                f'font-family:monospace;">{sig.replace("_", " ")}</span>'
            )
        )
        detail = (
            f'<div style="font-size:0.76rem;color:#8A8A8A;line-height:1.45;">'
            f'{event["detail"]}</div>'
            if event.get("detail")
            else ""
        )
        source = (
            f'<div style="font-size:0.68rem;color:#5E5E5E;margin-top:2px;">'
            f'{event["source"]}</div>'
            if event.get("source")
            else ""
        )
        return (
            f'<div style="margin-bottom:11px;">'
            f'<div style="display:flex;align-items:baseline;gap:7px;margin-bottom:1px;">'
            f'<span style="font-family:monospace;font-size:0.66rem;color:#6E6E6E;'
            f'min-width:{mono_width};">R{event["round"]} {event["circuit"][:9]}</span>{pill}</div>'
            f'<div style="font-size:0.82rem;color:#DADADA;line-height:1.45;">{event["headline"]}</div>'
            f"{detail}{source}</div>"
        )

    last = max([e["round"] for e in chassis + power], default=0)
    n = len(chassis) + len(power)
    head = (
        f'<div style="display:flex;align-items:baseline;justify-content:space-between;'
        f'border-bottom:1px solid #2A2A2A;padding-bottom:6px;margin-bottom:9px;">'
        f'<span style="font-weight:bold;font-size:0.95rem;color:{colour};">{team}</span>'
        f'<span style="font-size:0.7rem;color:#6E6E6E;">{n} upgrade{"s" if n != 1 else ""}'
        f" · last R{last}</span></div>"
    )

    def _held_token():
        pu = next(
            (
                c.get("pu") or c.get("pu_name")
                for c in CARS.values()
                if c["team"] == team
            ),
            None,
        )
        upg = PU_ADUO_UPGRADES.get(pu) if pu else None
        if upg and upg.get("round") is None:
            return pu, upg["note"]
        return None, None

    pu_block = ""
    if power:
        pu_name = power[0].get("pu") or ""
        pu_block = (
            '<div style="border-top:1px solid #2A2A2A;padding-top:9px;margin-top:2px;">'
            f'<div style="font-size:0.68rem;color:#00B7FF;margin-bottom:5px;'
            f'font-family:monospace;">POWER UNIT · {pu_name}</div>'
            + "".join(entry(e) for e in power)
            + "</div>"
        )
    else:
        held_pu, _ = _held_token()
        if held_pu:
            pu_block = (
                '<div style="border-top:1px solid #2A2A2A;padding-top:9px;margin-top:2px;">'
                f'<div style="font-size:0.68rem;color:#6E6E6E;margin-bottom:4px;'
                f'font-family:monospace;">POWER UNIT · {held_pu}</div>'
                '<div style="font-size:0.76rem;color:#8A8A8A;line-height:1.45;">'
                "ADUO allocated, not yet used.</div></div>"
            )

    body = "".join(entry(e) for e in chassis) or (
        '<div style="font-size:0.78rem;color:#6E6E6E;margin-bottom:11px;">'
        "No chassis upgrades recorded.</div>"
    )
    return (
        '<div style="background:#141414;border:1px solid #262626;'
        f'border-left:3px solid {colour};border-radius:0 8px 8px 0;'
        f'padding:12px 16px;margin-bottom:12px;">{head}{body}{pu_block}</div>'
    )


# ── Display guard for per-driver speed deltas ─────────────
DELTA_DISPLAY_LIMIT_KPH = 40.0


def safe_delta(value, limit: float = DELTA_DISPLAY_LIMIT_KPH):
    """Round a display delta, blanking only clearly unsupported per-driver values.

    Deliberately not used for chart aggregation; the median aggregation policy
    remains unchanged.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v) or abs(v) > limit:
        return None
    return round(v, 1)


# ── Round-aware driver identity / teammates ───────────────
def _effective_round(race_round: int | None = None) -> int:
    return current_round() if race_round is None else int(race_round)


def driver_info(code: str, race_round: int | None = None) -> dict:
    """Driver metadata for a round, including temporary stand-ins/team moves."""
    rnd = _effective_round(race_round)
    info = lineup_for_round(rnd).get(code)
    if info:
        return dict(info)
    return dict(CARS.get(code, {}))


def _unavailable_for_round(race_round: int) -> set[str]:
    sub = DRIVER_SUBSTITUTIONS.get(race_round, {})
    return set((sub.get("unavailable") or {}).keys())


def get_teammate(driver_code: str, race_round: int | None = None) -> str | None:
    """Return the active teammate for a driver at the requested round."""
    rnd = _effective_round(race_round)
    lineup = lineup_for_round(rnd)
    unavailable = _unavailable_for_round(rnd)
    if driver_code in unavailable:
        return None
    team = lineup.get(driver_code, {}).get("team", "")
    if not team:
        return None
    teammates = [
        code
        for code, info in lineup.items()
        if code != driver_code
        and code not in unavailable
        and info.get("team") == team
    ]
    # A valid F1 lineup has one active teammate. Deterministic ordering prevents
    # surprises if a malformed round temporarily contains >2 active entries.
    return sorted(teammates)[0] if teammates else None


def teammate_stats(fps, driver1: str, driver2: str, team: str | None = None) -> dict:
    """Head-to-head qualifying stats between two drivers while actual teammates.

    Keys are ``(round, session_type)``, preserving the sprint-weekend fix. A
    common key is retained only if both fingerprints carry the same team label.
    When ``team`` is provided, only sessions for that constructor are counted;
    this lets season history preserve multiple teammate eras cleanly.
    """
    d1_fps = {
        (fp.race_round, fp.session_type): fp
        for fp in fps
        if fp.driver_code == driver1 and fp.session_type in ("Q", "SQ")
    }
    d2_fps = {
        (fp.race_round, fp.session_type): fp
        for fp in fps
        if fp.driver_code == driver2 and fp.session_type in ("Q", "SQ")
    }
    common = sorted(
        key
        for key in set(d1_fps) & set(d2_fps)
        if d1_fps[key].team == d2_fps[key].team
        and (team is None or d1_fps[key].team == team)
    )
    if not common:
        return {
            "d1_wins": 0,
            "d2_wins": 0,
            "total": 0,
            "sessions": 0,
            "weekends": 0,
            "session_keys": [],
            "first_round": None,
            "last_round": None,
            "med_gap_s": 0.0,
            "med_gap_pct": 0.0,
        }

    gaps_s = [d1_fps[key].lap_time_s - d2_fps[key].lap_time_s for key in common]
    gaps_pct = [
        d1_fps[key].lap_time_gap_pct - d2_fps[key].lap_time_gap_pct for key in common
    ]
    rounds = sorted({round_num for round_num, _ in common})
    return {
        "d1_wins": sum(1 for gap in gaps_s if gap < 0),
        "d2_wins": sum(1 for gap in gaps_s if gap > 0),
        "total": len(common),
        "sessions": len(common),
        "weekends": len(rounds),
        "session_keys": common,
        "first_round": rounds[0],
        "last_round": rounds[-1],
        "med_gap_s": float(np.median(gaps_s)),
        "med_gap_pct": float(np.median(gaps_pct)),
    }


def driver_name(code: str, race_round: int | None = None) -> str:
    return driver_info(code, race_round).get("name", code)


def driver_number(code: str, race_round: int | None = None) -> int | None:
    return driver_info(code, race_round).get("number")


def driver_badge(code: str, size: str = "md", race_round: int | None = None) -> str:
    """Coloured driver badge: number + code in round-aware team colour."""
    info = driver_info(code, race_round)
    col = TEAM_COLOURS.get(info.get("team", ""), "#888")
    num = info.get("number", "")
    fs, pad = (
        ("1.0rem", "3px 9px")
        if size == "lg"
        else (("0.8rem", "2px 7px") if size == "md" else ("0.7rem", "1px 5px"))
    )
    return (
        '<span style="display:inline-flex;align-items:center;gap:6px;'
        f'background:{col}22;border-left:3px solid {col};border-radius:4px;'
        f'padding:{pad};font-family:monospace;font-size:{fs};">'
        f'<b style="color:{col};">{num}</b>'
        f'<span style="color:#E0E0E0;font-weight:bold;">{code}</span></span>'
    )


def team_badge(team: str, size: str = "md") -> str:
    col = TEAM_COLOURS.get(team, "#888")
    fs = "0.95rem" if size == "lg" else "0.82rem"
    return (
        f'<span style="color:{col};font-weight:bold;font-family:monospace;'
        f'font-size:{fs};">{team}</span>'
    )


def status_chip(fp) -> str:
    """DNF / NC / blank chip for a fingerprint."""
    status = (getattr(fp, "result_status", "") or "").strip()
    finished = getattr(fp, "completed_race", True)
    pos = getattr(fp, "finishing_position", None)
    if not finished:
        return (
            f'<span title="{status or "Retired"}" style="background:#FF444422;'
            'color:#FF4444;border:1px solid #FF4444;border-radius:3px;'
            'padding:1px 6px;font-size:0.7rem;font-family:monospace;">DNF</span>'
        )
    if pos is None and status:
        return (
            '<span title="Not classified — under 90% of winner\'s distance" '
            'style="background:#FFD70022;color:#FFD700;border:1px solid #FFD700;'
            'border-radius:3px;padding:1px 6px;font-size:0.7rem;'
            'font-family:monospace;">NC</span>'
        )
    return ""


# ── Race highlights ───────────────────────────────────────
def race_highlights(fps) -> dict:
    out = {
        "fastest_lap": None,
        "sectors": {},
        "most_gained": None,
        "best_pit_lane": None,
        "pit_range": None,
        "dnf_count": 0,
        "nc_count": 0,
    }
    if not fps:
        return out

    fastest = [f for f in fps if getattr(f, "fastest_lap_s", None)]
    if fastest:
        best = min(fastest, key=lambda f: f.fastest_lap_s)
        out["fastest_lap"] = {
            "driver": best.driver_code,
            "team": best.team,
            "time_s": best.fastest_lap_s,
            "lap": getattr(best, "fastest_lap_number", None),
        }

    for i in (1, 2, 3):
        best_field = f"best_sector_{i}_s"
        rep_field = f"sector_{i}_s"
        vals = [f for f in fps if getattr(f, best_field, None)]
        source = "best"
        if not vals:
            vals = [f for f in fps if getattr(f, rep_field, None)]
            source = "rep_lap"
        if vals:
            field = best_field if source == "best" else rep_field
            best = min(vals, key=lambda f: getattr(f, field))
            out["sectors"][f"S{i}"] = {
                "driver": best.driver_code,
                "team": best.team,
                "time_s": getattr(best, field),
                "source": source,
            }

    gained = [f for f in fps if getattr(f, "positions_gained", None) is not None]
    if gained:
        best = max(gained, key=lambda f: f.positions_gained)
        if best.positions_gained > 0:
            out["most_gained"] = {
                "driver": best.driver_code,
                "team": best.team,
                "gained": best.positions_gained,
                "grid": best.grid_position,
                "finish": best.finishing_position,
            }

    pits = [f for f in fps if getattr(f, "pit_lane_time_s", None)]
    if pits:
        best = min(pits, key=lambda f: f.pit_lane_time_s)
        out["best_pit_lane"] = {
            "driver": best.driver_code,
            "team": best.team,
            "time_s": best.pit_lane_time_s,
        }

    stops = [getattr(f, "pit_stops", 0) for f in fps if getattr(f, "pit_stops", 0) > 0]
    if stops:
        out["pit_range"] = (min(stops), max(stops))

    out["dnf_count"] = sum(
        1 for f in fps if not getattr(f, "completed_race", True)
    )
    out["nc_count"] = sum(
        1
        for f in fps
        if getattr(f, "completed_race", True)
        and getattr(f, "finishing_position", None) is None
        and getattr(f, "result_status", "")
    )
    return out


def fmt_laptime(seconds) -> str:
    if seconds is None:
        return "—"
    return f"{int(seconds // 60)}:{seconds % 60:06.3f}"


# ── FIA classification (90% rule) ─────────────────────────
def classification_threshold(fps) -> int:
    laps = [getattr(f, "laps_completed", 0) or 0 for f in fps]
    winner_laps = max(laps) if laps else 0
    return int(winner_laps * 0.9)


def is_classified(fp, threshold: int) -> bool:
    return (getattr(fp, "laps_completed", 0) or 0) >= threshold


def result_label(fp, threshold: int) -> str:
    if not is_classified(fp, threshold):
        return "NC"
    pos = getattr(fp, "finishing_position", None)
    return str(pos) if pos else "—"


# ── Driver season aggregates ──────────────────────────────
def driver_season_stats(fps, driver_code: str) -> dict:
    """Grand Prix season stats for one driver.

    GP summary statistics deliberately use only main Qualifying (Q) and the
    Grand Prix (R). Sprint sessions remain available elsewhere, but never create
    duplicate round markers or inflate poles/wins/podiums/average finish.
    """
    race_fps = [
        f for f in fps
        if f.driver_code == driver_code and f.session_type == "R"
    ]
    qual_fps = [
        f for f in fps
        if f.driver_code == driver_code and f.session_type == "Q"
    ]

    finishes, dnfs, ncs = [], 0, 0
    for f in race_fps:
        peers = [
            x for x in fps
            if x.race_round == f.race_round and x.session_type == "R"
        ]
        threshold = classification_threshold(peers)
        if not getattr(f, "completed_race", True):
            dnfs += 1
        elif not is_classified(f, threshold):
            ncs += 1
        elif getattr(f, "finishing_position", None):
            finishes.append(f.finishing_position)

    q_gaps = [f.lap_time_gap_pct for f in qual_fps if f.lap_time_gap_pct is not None]
    poles = sum(1 for f in qual_fps if f.lap_time_rank == 1)
    wins = sum(1 for p in finishes if p == 1)
    podiums = sum(1 for p in finishes if p <= 3)

    return {
        "races": len(race_fps),
        "classified": len(finishes),
        "dnfs": dnfs,
        "ncs": ncs,
        "avg_finish": (sum(finishes) / len(finishes)) if finishes else None,
        "best_finish": min(finishes) if finishes else None,
        "wins": wins,
        "podiums": podiums,
        "poles": poles,
        "avg_q_gap": (sum(q_gaps) / len(q_gaps)) if q_gaps else None,
        "best_q_gap": min(q_gaps) if q_gaps else None,
        "finish_history": [
            (
                f.race_round,
                f.finishing_position if getattr(f, "completed_race", True) else None,
            )
            for f in sorted(race_fps, key=lambda x: x.race_round)
        ],
    }


def qualifying_ranking(fps, sessions=("Q",)) -> list[dict]:
    """Drivers ranked by qualifying gap; GP Q only by default."""
    session_set = set(sessions)
    per = defaultdict(list)
    latest = {}
    for f in fps:
        if f.session_type in session_set and f.confidence >= 0.5:
            per[f.driver_code].append(f.lap_time_gap_pct)
            current = latest.get(f.driver_code)
            key = (f.race_round, 1 if f.session_type == "Q" else 0)
            if current is None or key > current[0]:
                latest[f.driver_code] = (key, f)

    out = []
    for driver, values in per.items():
        if not values:
            continue
        team_fp = latest.get(driver, (None, None))[1]
        out.append(
            {
                "driver": driver,
                "team": team_fp.team if team_fp is not None else "?",
                "avg_gap": sum(values) / len(values),
                "best_gap": min(values),
                "sessions": len(values),
            }
        )
    return sorted(out, key=lambda x: x["avg_gap"])


def teammate_ranking(fps) -> list[dict]:
    """Return every real teammate pairing seen in Q/SQ during the season.

    A team can therefore have more than one row after a lineup change. This is
    intentionally different from using only the latest active pairing: Verstappen
    and Lindblad keep their earlier season H2H records as well as the temporary
    R12+ pairings. Q and SQ remain separate observations, while ``weekends``
    reports the distinct round count so sprint weekends do not masquerade as two
    weekends.
    """
    # Discover pairings from what was actually stored, not from the current flat
    # roster. Each same-team Q/SQ session contributes an unordered driver pair.
    session_drivers = defaultdict(set)
    for fp in fps:
        if fp.session_type in ("Q", "SQ"):
            session_drivers[(fp.team, fp.race_round, fp.session_type)].add(fp.driver_code)

    pairings = set()
    for (team, _round, _session), drivers in session_drivers.items():
        if len(drivers) == 2:
            d1, d2 = sorted(drivers)
            pairings.add((team, d1, d2))

    rnd = current_round()
    active_by_team = defaultdict(set)
    unavailable = _unavailable_for_round(rnd)
    for driver, info in lineup_for_round(rnd).items():
        if driver not in unavailable:
            active_by_team[info.get("team", "?")].add(driver)

    out = []
    for team, d1, d2 in sorted(pairings):
        stats = teammate_stats(fps, d1, d2, team=team)
        if stats["total"] == 0:
            continue
        if stats["med_gap_s"] <= 0:
            faster, slower = d1, d2
            gap_s, gap_pct = abs(stats["med_gap_s"]), abs(stats["med_gap_pct"])
            f_wins, s_wins = stats["d1_wins"], stats["d2_wins"]
        else:
            faster, slower = d2, d1
            gap_s, gap_pct = stats["med_gap_s"], stats["med_gap_pct"]
            f_wins, s_wins = stats["d2_wins"], stats["d1_wins"]

        current_pair = {d1, d2} == active_by_team.get(team, set())
        first_round = stats["first_round"]
        last_round = stats["last_round"]
        round_label = (
            f"R{first_round}"
            if first_round == last_round
            else f"R{first_round}–R{last_round}"
        )
        out.append(
            {
                "team": team,
                "driver1": d1,
                "driver2": d2,
                "pairing": f"{d1} vs {d2}",
                "faster": faster,
                "slower": slower,
                "gap_s": gap_s,
                "gap_pct": gap_pct,
                "faster_wins": f_wins,
                "slower_wins": s_wins,
                "sessions": stats["sessions"],
                "weekends": stats["weekends"],
                "first_round": first_round,
                "last_round": last_round,
                "round_label": round_label,
                "current_pairing": current_pair,
                "limited_sample": stats["weekends"] < 3,
                "rounds": stats["sessions"],  # legacy display compatibility
            }
        )

    # Group teammate eras by team; within a team, show the current/latest pairing
    # first. This makes lineup changes readable without hiding earlier evidence.
    return sorted(
        out,
        key=lambda x: (
            x["team"],
            0 if x["current_pairing"] else 1,
            -(x["last_round"] or 0),
        ),
    )


def teammate_season_overall(fps) -> list[dict]:
    """Season H2H for the anchor driver of teams that changed lineups.

    The anchor is the driver with the most same-team Q/SQ appearances for that
    constructor. Their H2H is then accumulated against whoever occupied the
    other seat in each qualifying session. This is deliberately a H2H summary
    only: a single median gap across different opponents would be misleading.
    """
    session_rows = defaultdict(list)
    for fp in fps:
        if fp.session_type in ("Q", "SQ"):
            session_rows[(fp.team, fp.race_round, fp.session_type)].append(fp)

    by_team = defaultdict(list)
    for (team, race_round, session_type), rows in session_rows.items():
        if len(rows) == 2:
            by_team[team].append((race_round, session_type, rows))

    out = []
    for team, sessions in by_team.items():
        appearances = defaultdict(int)
        opponents_by_driver = defaultdict(set)
        for _round, _session, rows in sessions:
            a, b = rows
            appearances[a.driver_code] += 1
            appearances[b.driver_code] += 1
            opponents_by_driver[a.driver_code].add(b.driver_code)
            opponents_by_driver[b.driver_code].add(a.driver_code)

        # Only add an overall row where there was actually a teammate change.
        candidates = [d for d, opps in opponents_by_driver.items() if len(opps) > 1]
        if not candidates:
            continue
        anchor = max(candidates, key=lambda d: (appearances[d], d))

        wins = losses = 0
        session_count = 0
        weekend_set = set()
        opponents = set()
        first_round = None
        last_round = None
        for race_round, _session, rows in sessions:
            me = next((fp for fp in rows if fp.driver_code == anchor), None)
            other = next((fp for fp in rows if fp.driver_code != anchor), None)
            if me is None or other is None:
                continue
            session_count += 1
            weekend_set.add(race_round)
            opponents.add(other.driver_code)
            first_round = race_round if first_round is None else min(first_round, race_round)
            last_round = race_round if last_round is None else max(last_round, race_round)
            if me.lap_time_s < other.lap_time_s:
                wins += 1
            elif me.lap_time_s > other.lap_time_s:
                losses += 1

        if session_count:
            out.append({
                "team": team,
                "driver": anchor,
                "opponents": sorted(opponents),
                "wins": wins,
                "losses": losses,
                "sessions": session_count,
                "weekends": len(weekend_set),
                "first_round": first_round,
                "last_round": last_round,
                "round_label": (
                    f"R{first_round}" if first_round == last_round
                    else f"R{first_round}–R{last_round}"
                ),
            })
    return sorted(out, key=lambda x: x["team"])


def get_pu_aduo_summary() -> list[dict]:
    """Return the PU/ADUO table from canonical configuration."""
    rows = []
    for pu in PU_ORDER:
        meta = PU_ADUO_UPGRADES.get(pu, {})
        deployed = int(meta.get("round") is not None) + int(
            meta.get("second_round") is not None
        )
        allocated = int(meta.get("tokens_allocated", 0))
        if pu == "RedBullFord":
            rank = "1"
            band = "Benchmark (0%)"
            note = "Published benchmark ICE; no ADUO allocation."
        elif pu == "Mercedes":
            rank = "2"
            note = "ADUO allocated but not yet deployed."
        else:
            rank = "3–5*"
            if deployed == 0:
                note = "No performance homologation deployed yet."
            elif deployed == 1:
                note = f"ADUO 1 deployed at R{meta.get('round')}."
            else:
                note = (
                    f"ADUO 1 deployed at R{meta.get('round')}; "
                    f"ADUO 2 at R{meta.get('second_round')}."
                )
        rows.append(
            {
                "Rank": rank,
                "PU": pu,
                "ADUO Band": band if pu == "RedBullFord" else meta.get("aduo_band", "Not published"),
                "Allocated": allocated,
                "Deployed": deployed,
                "Note": note,
            }
        )
    return rows
