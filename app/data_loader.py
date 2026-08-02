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
    "Cadillac":     "#FFFFFF",
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
    Returns dict with: d1_wins, d2_wins, total, avg_gap_s, avg_gap_pct
    Positive gap = driver1 is slower than driver2.
    """
    d1_fps = {fp.race_round: fp for fp in fps
              if fp.driver_code == driver1 and fp.session_type in ("Q", "SQ")}
    d2_fps = {fp.race_round: fp for fp in fps
              if fp.driver_code == driver2 and fp.session_type in ("Q", "SQ")}
    common = sorted(set(d1_fps) & set(d2_fps))

    if not common:
        return {"d1_wins": 0, "d2_wins": 0, "total": 0,
                "avg_gap_s": 0.0, "avg_gap_pct": 0.0}

    gaps_s   = [d1_fps[r].lap_time_s - d2_fps[r].lap_time_s for r in common]
    gaps_pct = [d1_fps[r].lap_time_gap_pct - d2_fps[r].lap_time_gap_pct for r in common]

    return {
        "d1_wins":    sum(1 for g in gaps_s if g < 0),
        "d2_wins":    sum(1 for g in gaps_s if g > 0),
        "total":      len(common),
        "avg_gap_s":  float(np.mean(gaps_s)),
        "avg_gap_pct": float(np.mean(gaps_pct)),
    }
