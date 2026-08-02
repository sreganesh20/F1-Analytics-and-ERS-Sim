"""
data/race_store.py
"""

import json
import os
from dataclasses import asdict
from models.fingerprint import CarFingerprint, RaceFingerprints

STORE_DIR = os.path.join(os.path.dirname(__file__), "..", "store")


def _ensure_store():
    os.makedirs(STORE_DIR, exist_ok=True)


def _race_path(year: int, round_num: int, session: str) -> str:
    return os.path.join(STORE_DIR, f"{year}_R{round_num:02d}_{session}.json")


def _index_path() -> str:
    return os.path.join(STORE_DIR, "index.json")


# ─────────────────────────────────────────────────────────
#  Save
# ─────────────────────────────────────────────────────────

def save_fingerprints(rf: RaceFingerprints, stint_data_map: dict = None):
    """Persist a RaceFingerprints object to the store.

    Args:
        rf:              RaceFingerprints to save
        stint_data_map:  Optional {driver_code: [stint_dicts]} from race sessions.
                         Stored in JSON for future compound analysis — not loaded back
                         into the dataclass until race 8+.
    """
    _ensure_store()
    path = _race_path(rf.year, rf.race_round, rf.session_type)

    data = {
        "circuit_name":  rf.circuit_name,
        "circuit_type":  rf.circuit_type,
        "race_round":    rf.race_round,
        "year":          rf.year,
        "session_type":  rf.session_type,
        "fingerprints":  [asdict(fp) for fp in rf.fingerprints],
        "stint_data":    stint_data_map or {},   # stored, not yet used in predictor
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    _update_index(rf)
    print(f"  Saved {len(rf.fingerprints)} fingerprints → {path}")


def _update_index(rf: RaceFingerprints):
    idx_path = _index_path()
    index    = load_index()

    key = f"{rf.year}_R{rf.race_round:02d}_{rf.session_type}"
    index[key] = {
        "circuit_name": rf.circuit_name,
        "circuit_type": rf.circuit_type,
        "race_round":   rf.race_round,
        "year":         rf.year,
        "session_type": rf.session_type,
        "n_fingerprints": len(rf.fingerprints),
        "path": os.path.basename(_race_path(rf.year, rf.race_round, rf.session_type)),
    }

    with open(idx_path, "w") as f:
        json.dump(index, f, indent=2)


# ─────────────────────────────────────────────────────────
#  Load
# ─────────────────────────────────────────────────────────

def load_index() -> dict:
    idx_path = _index_path()
    if not os.path.exists(idx_path):
        return {}
    with open(idx_path) as f:
        return json.load(f)


def load_fingerprints(year: int, round_num: int, session: str) -> RaceFingerprints | None:
    path = _race_path(year, round_num, session)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    fps = [CarFingerprint(**fp) for fp in data["fingerprints"]]
    return RaceFingerprints(
        circuit_name = data["circuit_name"],
        circuit_type = data["circuit_type"],
        race_round   = data["race_round"],
        year         = data["year"],
        session_type = data["session_type"],
        fingerprints = fps,
    )


def load_all_fingerprints(
    year:     int             = 2026,
    sessions: list | str | None = None,
) -> list[RaceFingerprints]:
    """Load stored fingerprints for a season, filtered by session type(s).

    Args:
        year:     Season year
        sessions: Session type or list of types. Defaults to ["Q"].
                  Examples: "Q", ["Q", "SQ"], ["R", "S"]
    """
    if sessions is None:
        sessions = ["Q"]
    elif isinstance(sessions, str):
        sessions = [sessions]

    index  = load_index()
    result = []
    for key, meta in sorted(index.items()):
        if meta["year"] == year and meta["session_type"] in sessions:
            rf = load_fingerprints(year, meta["race_round"], meta["session_type"])
            if rf:
                result.append(rf)
    return result


def load_driver_history(driver_code: str, year: int = 2026) -> list[CarFingerprint]:
    all_races = load_all_fingerprints(year)
    return [fp for rf in all_races
            for fp in rf.fingerprints
            if fp.driver_code == driver_code]


def load_pu_history(pu_name: str, year: int = 2026) -> list[CarFingerprint]:
    all_races = load_all_fingerprints(year)
    return [fp for rf in all_races
            for fp in rf.fingerprints
            if fp.pu_name == pu_name]


def print_store_summary():
    index = load_index()
    if not index:
        print("  Race store is empty.")
        return
    print(f"\n  Race Store — {len(index)} sessions saved:")
    for key, meta in sorted(index.items()):
        print(f"    {key:<20} {meta['circuit_name']:<30} "
              f"{meta['n_fingerprints']} cars")
