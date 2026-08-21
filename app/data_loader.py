"""
app/data_loader.py
Shared data loading and caching for the Streamlit app.
All heavy operations are cached with st.cache_data.
"""

import os
import sys
import json
import requests
import numpy as np
import streamlit as st
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from data.race_store import load_all_fingerprints as _load_all, load_index
from config import CARS, CIRCUITS, TEAM_UPGRADES, KNOWN_UPCOMING_UPGRADES

# ── Colour palettes ──────────────────────────────────────

PU_COLOURS = {
    "Mercedes":    "#00D2BE",
    "Ferrari":     "#E8002D",
    "RedBullFord": "#3671C6",
    "Honda":       "#CC1E4A",
    "Audi":        "#B0B0B0",
}

TEAM_COLOURS = {
    "Mercedes":     "#00D2BE",
    "McLaren":      "#FF8000",
    "Ferrari":      "#E8002D",
    "Red Bull":     "#3671C6",
    "VCARB":        "#6692FF",
    "Aston Martin": "#229971",
    "Alpine":       "#FF87BC",
    "Williams":     "#64C4FF",
    "Haas":         "#B6BABD",
    "Audi":         "#B0B0B0",
    "Cadillac":     "#C9B037",
}

PU_ORDER = ["Mercedes", "Ferrari", "RedBullFord", "Audi", "Honda"]

SIG_COLOURS = {
    "new_car": "#FF1E00",
    "major":   "#FF8000",
    "medium":  "#FFD700",
    "minor":   "#00C851",
}

FACTORY_TEAMS = {
    "Mercedes":    ["Mercedes"],
    "Ferrari":     ["Ferrari"],
    "RedBullFord": ["Red Bull"],
    "Honda":       ["Aston Martin"],
    "Audi":        ["Audi"],
}

# ── Fingerprint loading ──────────────────────────────────

@st.cache_data(ttl=60)
def get_fingerprints(sessions=None):
    sessions = sessions or ["Q", "R", "S", "SQ"]
    if isinstance(sessions, str):
        sessions = [sessions]
    return [fp for rf in _load_all(year=2026, sessions=sessions)
            for fp in rf.fingerprints]

@st.cache_data(ttl=60)
def get_store_index():
    return load_index()

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
    return sorted({meta["session_type"] for meta in idx.values()
                   if meta["race_round"] == race_round})

# ── Standings ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_driver_standings():
    try:
        r = requests.get("https://api.jolpi.ca/ergast/f1/2026/driverStandings.json",
                        timeout=10)
        r.raise_for_status()
        sl = r.json()["MRData"]["StandingsTable"]["StandingsLists"]
        if not sl:
            return []
        return [{
            "pos":    int(s["position"]),
            "code":   s["Driver"]["code"],
            "name":   f"{s['Driver']['givenName']} {s['Driver']['familyName']}",
            "team":   s["Constructors"][0]["name"],
            "points": float(s["points"]),
            "wins":   int(s["wins"]),
        } for s in sl[0]["DriverStandings"]]
    except Exception:
        return []

@st.cache_data(ttl=3600)
def get_constructor_standings():
    try:
        r = requests.get("https://api.jolpi.ca/ergast/f1/2026/constructorStandings.json",
                        timeout=10)
        r.raise_for_status()
        sl = r.json()["MRData"]["StandingsTable"]["StandingsLists"]
        if not sl:
            return []
        return [{
            "pos":    int(s["position"]),
            "team":   s["Constructor"]["name"],
            "points": float(s["points"]),
            "wins":   int(s["wins"]),
        } for s in sl[0]["ConstructorStandings"]]
    except Exception:
        return []

# ── Commentary ─────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_commentary():
    path = os.path.join(ROOT, "data", "commentary.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# ── Predictions ─────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_prediction_data(circuit_name, pred_type="quali"):
    """Load stored prediction. pred_type: 'quali' | 'race'"""
    pred_dir = os.path.join(ROOT, "store", "predictions")
    # New format: 2026_Netherlands_quali_prediction.json
    path = os.path.join(pred_dir,
                        f"2026_{circuit_name.replace(' ', '_')}_{pred_type}_prediction.json")
    if not os.path.exists(path) and pred_type == "quali":
        # Legacy fallback: 2026_Netherlands_prediction.json
        path = os.path.join(pred_dir,
                            f"2026_{circuit_name.replace(' ', '_')}_prediction.json")
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
    for f in os.listdir(pred_dir):
        if "_prediction.json" not in f or not f.startswith("2026_"):
            continue
        name = f.replace("2026_", "")
        for suffix in ("_quali_prediction.json", "_race_prediction.json", "_prediction.json"):
            name = name.replace(suffix, "")
        circuits.add(name.replace("_", " "))
    return sorted(circuits)

# ── Upgrade timeline ─────────────────────────────────────

def get_upgrade_timeline():
    events = []
    round_to_circuit = {cfg["round"]: cfg.get("fastf1_name", "").replace(" Grand Prix", "")
                        for cfg in CIRCUITS.values()}
    for team, upgrades in TEAM_UPGRADES.items():
        for upg in upgrades:
            events.append({
                "team":         team,
                "round":        upg["from_round"],
                "circuit":      round_to_circuit.get(upg["from_round"], f"R{upg['from_round']}"),
                "significance": upg["significance"],
                "note":         upg["note"],
                "incoming":     False,
            })
    for entity, upgrades in KNOWN_UPCOMING_UPGRADES.items():
        for upg in upgrades:
            events.append({
                "team":         entity,
                "round":        upg["at_round"],
                "circuit":      round_to_circuit.get(upg["at_round"], f"R{upg['at_round']}"),
                "significance": upg["significance"],
                "note":         upg["note"],
                "incoming":     True,
            })
    return sorted(events, key=lambda x: (x["round"], x["team"]))

# ── HTML helpers ─────────────────────────────────────────

def conf_badge(conf):
    if conf >= 0.70:   c, t = "#00C851", f"HIGH {conf:.0%}"
    elif conf >= 0.55: c, t = "#FFD700", f"MED {conf:.0%}"
    else:              c, t = "#FF4444", f"LOW {conf:.0%}"
    return (f'<span style="background:{c}22;color:{c};border:1px solid {c};'
            f'border-radius:4px;padding:1px 6px;font-family:monospace;font-size:0.75rem;">'
            f'{t}</span>')

def sig_badge(sig):
    c = SIG_COLOURS.get(sig, "#888")
    t = sig.replace("_", " ").upper()
    return (f'<span style="background:{c}22;color:{c};border:1px solid {c};'
            f'border-radius:3px;padding:1px 5px;font-family:monospace;font-size:0.7rem;">'
            f'{t}</span>')

def upgrade_card(upg):
    c = SIG_COLOURS.get(upg["significance"], "#888")
    prefix = "⚠️ UPCOMING" if upg["incoming"] else f"R{upg['round']} · {upg['circuit']}"
    return f"""
    <div style="border-left:3px solid {c};padding:8px 14px;margin:8px 0;
                background:{c}11;border-radius:0 6px 6px 0;">
        <div style="font-family:monospace;font-size:0.7rem;color:{c};margin-bottom:3px;">
            {prefix} · {upg['significance'].replace('_',' ').upper()}
        </div>
        <div style="font-weight:bold;margin-bottom:4px;">{upg['team']}</div>
        <div style="font-size:0.83rem;color:#C0C0C0;">{upg['note']}</div>
    </div>"""

# ── Display guard for per-driver speed deltas ─────────────

DELTA_DISPLAY_LIMIT_KPH = 40.0


def safe_delta(value, limit: float = DELTA_DISPLAY_LIMIT_KPH):
    """
    Round a per-driver speed delta for display, or return None if it is
    outside the range the measurement can support.

    WHY: segments are fixed distance windows detected on the session's
    fastest lap. A car that brakes 20 m earlier is therefore measured in
    the wrong window, and short slow-corner windows are the most sensitive
    to that. 16 of 323 quali driver-sessions land beyond +/-25 kph, topping
    out at +114 kph overall and +318 kph in the slow-corner bucket, which
    are artefacts rather than measurements.

    Team-level charts survive this because they aggregate ~30 sessions with
    a median. A single cell in a per-driver table does not — it just reads
    as nonsense and discredits every honest number next to it.

    Deliberately NOT applied to chart aggregation. Large deltas are genuine
    and expected for backmarkers; filtering them there would repeat the
    MAX_DELTA = 25 mistake from Wave 1, which excluded half the grid.

    Fixing this properly needs corner detection from X/Y curvature so every
    car is measured on the same corner rather than the same distance window.
    That is the v2 trackmap work.
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


# ── Teammate lookup ───────────────────────────────────────

def get_teammate(driver_code: str) -> str | None:
    """Return the teammate driver code for a given driver (2026 grid)."""
    team = CARS.get(driver_code, {}).get("team", "")
    if not team:
        return None
    teammates = [d for d, info in CARS.items()
                 if info.get("team") == team and d != driver_code]
    return teammates[0] if teammates else None


# ── Teammate stats ────────────────────────────────────────

def teammate_stats(fps, driver1: str, driver2: str) -> dict:
    """
    Return head-to-head qualifying stats between two teammates.
    Returns dict with: d1_wins, d2_wins, total, med_gap_s, med_gap_pct
    Positive gap = driver1 is slower than driver2.
    """
    d1_fps = {(fp.race_round, fp.session_type): fp for fp in fps
              if fp.driver_code == driver1 and fp.session_type in ("Q", "SQ")}
    d2_fps = {(fp.race_round, fp.session_type): fp for fp in fps
              if fp.driver_code == driver2 and fp.session_type in ("Q", "SQ")}
    common = sorted(set(d1_fps) & set(d2_fps))

    if not common:
        return {"d1_wins": 0, "d2_wins": 0, "total": 0,
                "med_gap_s": 0.0, "med_gap_pct": 0.0}

    gaps_s   = [d1_fps[r].lap_time_s - d2_fps[r].lap_time_s for r in common]
    gaps_pct = [d1_fps[r].lap_time_gap_pct - d2_fps[r].lap_time_gap_pct for r in common]

    return {
        "d1_wins":    sum(1 for g in gaps_s if g < 0),
        "d2_wins":    sum(1 for g in gaps_s if g > 0),
        "total":      len(common),
        # Median, not mean: one binned session should not define a season.
        "med_gap_s":   float(np.median(gaps_s)),
        "med_gap_pct": float(np.median(gaps_pct)),
    }


# ── WAVE 3: driver identity helpers ───────────────────────

def driver_name(code: str) -> str:
    """Full driver name, falls back to code."""
    return CARS.get(code, {}).get("name", code)

def driver_number(code: str) -> int | None:
    return CARS.get(code, {}).get("number")

def driver_badge(code: str, size: str = "md") -> str:
    """Coloured driver badge: number + code in team colour. No trademarked assets."""
    info = CARS.get(code, {})
    col  = TEAM_COLOURS.get(info.get("team", ""), "#888")
    num  = info.get("number", "")
    fs, pad = (("1.0rem", "3px 9px") if size == "lg" else
               ("0.8rem", "2px 7px") if size == "md" else ("0.7rem", "1px 5px"))
    return (f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'background:{col}22;border-left:3px solid {col};border-radius:4px;'
            f'padding:{pad};font-family:monospace;font-size:{fs};">'
            f'<b style="color:{col};">{num}</b>'
            f'<span style="color:#E0E0E0;font-weight:bold;">{code}</span></span>')

def team_badge(team: str, size: str = "md") -> str:
    col = TEAM_COLOURS.get(team, "#888")
    fs  = "0.95rem" if size == "lg" else "0.82rem"
    return (f'<span style="color:{col};font-weight:bold;font-family:monospace;'
            f'font-size:{fs};">{team}</span>')

def status_chip(fp) -> str:
    """DNF / NC / blank chip for a fingerprint (Wave 3 decision: no 'OK' noise)."""
    status = (getattr(fp, "result_status", "") or "").strip()
    finished = getattr(fp, "completed_race", True)
    pos = getattr(fp, "finishing_position", None)

    if not finished:
        return (f'<span title="{status or "Retired"}" style="background:#FF444422;'
                f'color:#FF4444;border:1px solid #FF4444;border-radius:3px;'
                f'padding:1px 6px;font-size:0.7rem;font-family:monospace;">DNF</span>')
    if pos is None and status:
        return (f'<span title="Not classified — under 90% of winner\'s distance" '
                f'style="background:#FFD70022;color:#FFD700;border:1px solid #FFD700;'
                f'border-radius:3px;padding:1px 6px;font-size:0.7rem;'
                f'font-family:monospace;">NC</span>')
    return ""


# ── WAVE 3: race highlights ───────────────────────────────

def race_highlights(fps) -> dict:
    """
    Derive race highlight stats from Wave 1 fields for one session.
    Returns dict of headline stats; each value may be None if unavailable.
    """
    out = {"fastest_lap": None, "sectors": {}, "most_gained": None,
           "best_pit_lane": None, "pit_range": None, "dnf_count": 0, "nc_count": 0}
    if not fps:
        return out

    # Fastest lap of the session
    fl = [f for f in fps if getattr(f, "fastest_lap_s", None)]
    if fl:
        best = min(fl, key=lambda f: f.fastest_lap_s)
        out["fastest_lap"] = {
            "driver": best.driver_code, "team": best.team,
            "time_s": best.fastest_lap_s,
            "lap": getattr(best, "fastest_lap_number", None),
        }

    # Fastest each sector — uses PERSONAL BEST sectors (any lap), not rep-lap
    # splits. Falls back to rep-lap sectors only if best-sector data is absent
    # (i.e. store predates Wave 3), and flags that in the payload.
    for i in (1, 2, 3):
        best_field = f"best_sector_{i}_s"
        rep_field  = f"sector_{i}_s"
        vals = [f for f in fps if getattr(f, best_field, None)]
        source = "best"
        if not vals:
            vals = [f for f in fps if getattr(f, rep_field, None)]
            source = "rep_lap"
        if vals:
            field = best_field if source == "best" else rep_field
            b = min(vals, key=lambda f: getattr(f, field))
            out["sectors"][f"S{i}"] = {
                "driver": b.driver_code, "team": b.team,
                "time_s": getattr(b, field), "source": source,
            }

    # Most positions gained
    gained = [f for f in fps if getattr(f, "positions_gained", None) is not None]
    if gained:
        b = max(gained, key=lambda f: f.positions_gained)
        if b.positions_gained > 0:
            out["most_gained"] = {
                "driver": b.driver_code, "team": b.team,
                "gained": b.positions_gained,
                "grid": b.grid_position, "finish": b.finishing_position,
            }

    # Best pit lane transit (NOT stationary time — see race_pipeline note)
    pits = [f for f in fps if getattr(f, "pit_lane_time_s", None)]
    if pits:
        b = min(pits, key=lambda f: f.pit_lane_time_s)
        out["best_pit_lane"] = {
            "driver": b.driver_code, "team": b.team, "time_s": b.pit_lane_time_s,
        }

    stops = [getattr(f, "pit_stops", 0) for f in fps if getattr(f, "pit_stops", 0) > 0]
    if stops:
        out["pit_range"] = (min(stops), max(stops))

    out["dnf_count"] = sum(1 for f in fps if not getattr(f, "completed_race", True))
    out["nc_count"]  = sum(1 for f in fps
                           if getattr(f, "completed_race", True)
                           and getattr(f, "finishing_position", None) is None
                           and getattr(f, "result_status", ""))
    return out


def fmt_laptime(seconds) -> str:
    """Format seconds as M:SS.mmm"""
    if seconds is None:
        return "—"
    return f"{int(seconds // 60)}:{seconds % 60:06.3f}"


# ── WAVE 3: FIA classification (90% rule) ─────────────────
#
# FastF1 assigns an ordinal Position to EVERY driver including retirees, so
# `finishing_position` alone cannot tell you who was officially classified.
# FIA Sporting Regs: a car is classified only if it covered at least 90% of the
# number of laps completed by the winner, rounded DOWN to the nearest whole lap.
#
# Verified vs Monaco 2026 (78 laps -> 70 needed):
#   Sainz  71 laps -> classified P16   (official: P16)
#   Leclerc 65 laps -> NOT classified  (official: NC)

def classification_threshold(fps) -> int:
    """Minimum laps needed to be classified in this session (90% of winner)."""
    laps = [getattr(f, "laps_completed", 0) or 0 for f in fps]
    winner_laps = max(laps) if laps else 0
    return int(winner_laps * 0.9)          # floor

def is_classified(fp, threshold: int) -> bool:
    return (getattr(fp, "laps_completed", 0) or 0) >= threshold

def result_label(fp, threshold: int) -> str:
    """What to show in the Finish column: position, NC, or DNF+NC."""
    classified = is_classified(fp, threshold)
    if not classified:
        return "NC"
    pos = getattr(fp, "finishing_position", None)
    return str(pos) if pos else "—"


# ── WAVE 3: Driver season aggregates ──────────────────────

def driver_season_stats(fps, driver_code: str) -> dict:
    """
    Season aggregates for one driver.

    DECISION: DNF and NC results are EXCLUDED from average finishing position —
    a retirement says nothing about race pace or finishing ability, and counting
    it as last place would punish a driver twice for one mechanical failure.
    DNF count is reported separately so the reliability story is still visible.
    """
    race_fps = [f for f in fps if f.driver_code == driver_code
                and f.session_type in ("R", "S")]
    qual_fps = [f for f in fps if f.driver_code == driver_code
                and f.session_type in ("Q", "SQ")]

    # Classified finishes only (90% rule applied per session)
    finishes, dnfs, ncs = [], 0, 0
    for f in race_fps:
        session_peers = [x for x in fps if x.race_round == f.race_round
                         and x.session_type == f.session_type]
        thr = classification_threshold(session_peers)
        if not getattr(f, "completed_race", True):
            dnfs += 1
        elif not is_classified(f, thr):
            ncs += 1
        elif getattr(f, "finishing_position", None):
            finishes.append(f.finishing_position)

    q_gaps = [f.lap_time_gap_pct for f in qual_fps]
    poles  = sum(1 for f in qual_fps if f.lap_time_rank == 1)
    wins   = sum(1 for p in finishes if p == 1)
    podiums= sum(1 for p in finishes if p <= 3)

    return {
        "races":          len(race_fps),
        "classified":     len(finishes),
        "dnfs":           dnfs,
        "ncs":            ncs,
        "avg_finish":     (sum(finishes) / len(finishes)) if finishes else None,
        "best_finish":    min(finishes) if finishes else None,
        "wins":           wins,
        "podiums":        podiums,
        "poles":          poles,
        "avg_q_gap":      (sum(q_gaps) / len(q_gaps)) if q_gaps else None,
        "best_q_gap":     min(q_gaps) if q_gaps else None,
        "finish_history": [(f.race_round,
                            f.finishing_position if getattr(f, "completed_race", True)
                            else None)
                           for f in sorted(race_fps, key=lambda x: x.race_round)],
    }


def qualifying_ranking(fps) -> list[dict]:
    """All drivers ranked by average qualifying gap to pole (lower = better)."""
    from collections import defaultdict
    per = defaultdict(list)
    for f in fps:
        if f.session_type in ("Q", "SQ") and f.confidence >= 0.5:
            per[f.driver_code].append(f.lap_time_gap_pct)
    out = [{"driver": d, "team": CARS.get(d, {}).get("team", "?"),
            "avg_gap": sum(v) / len(v), "best_gap": min(v), "sessions": len(v)}
           for d, v in per.items() if v]
    return sorted(out, key=lambda x: x["avg_gap"])


def teammate_ranking(fps) -> list[dict]:
    """
    All 11 teams ranked by intra-team qualifying gap (largest gap first).
    Gap is the primary metric; H2H record shown alongside.
    """
    seen, out = set(), []
    for f in fps:
        if f.session_type not in ("Q", "SQ"):
            continue
        d1 = f.driver_code
        d2 = get_teammate(d1)
        if not d2 or (d1, d2) in seen or (d2, d1) in seen:
            continue
        seen.add((d1, d2))
        s = teammate_stats(fps, d1, d2)
        if s["total"] == 0:
            continue
        # Orient so the FASTER driver is always listed first
        if s["med_gap_s"] <= 0:
            faster, slower = d1, d2
            gap_s, gap_pct = abs(s["med_gap_s"]), abs(s["med_gap_pct"])
            f_wins, s_wins = s["d1_wins"], s["d2_wins"]
        else:
            faster, slower = d2, d1
            gap_s, gap_pct = s["med_gap_s"], s["med_gap_pct"]
            f_wins, s_wins = s["d2_wins"], s["d1_wins"]
        out.append({
            "team": f.team, "faster": faster, "slower": slower,
            "gap_s": gap_s, "gap_pct": gap_pct,
            "faster_wins": f_wins, "slower_wins": s_wins, "rounds": s["total"],
        })
    return sorted(out, key=lambda x: -x["gap_s"])
