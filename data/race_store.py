"""
data/race_store.py

Persistence layer for committed session fingerprints.

Important: ``load_all_fingerprints`` intentionally discovers sessions through
``store/index.json`` rather than scanning the directory. ``save_fingerprints``
therefore always updates the index after writing a session payload.
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


def _load_fastf1_session_results(year: int, round_num: int, session: str) -> dict:
    """Best-effort full official result roster from the local FastF1 cache.

    The race pipeline already loaded this session, so this normally resolves
    from cache. It exists as a safety net until every caller passes the result
    map directly into ``save_fingerprints``. Failure is non-fatal.
    """
    if session not in ("R", "S"):
        return {}
    try:
        import math
        import fastf1

        cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cache"))
        fastf1.Cache.enable_cache(cache_dir)
        ff_session = fastf1.get_session(year, round_num, session)
        ff_session.load(telemetry=False, weather=False, messages=False)
        results = ff_session.results
        if results is None or results.empty:
            return {}

        out = {}
        for _, row in results.iterrows():
            code = row.get("Abbreviation")
            if not code:
                continue

            def _int_or_none(value):
                try:
                    if value is None or (isinstance(value, float) and math.isnan(value)):
                        return None
                    return int(value)
                except (TypeError, ValueError):
                    return None

            pos = _int_or_none(row.get("Position"))
            grid = _int_or_none(row.get("GridPosition"))
            laps = _int_or_none(row.get("Laps"))
            out[str(code)] = {
                "finishing_position": pos,
                "grid_position": grid,
                "positions_gained": (grid - pos) if grid is not None and pos is not None else None,
                "result_status": str(row.get("Status", "") or ""),
                "laps_completed": laps,
            }
        return out
    except Exception as exc:
        print(f"  Result-roster fallback unavailable: {exc}")
        return {}


def _results_from_fingerprints(rf: RaceFingerprints) -> dict:
    """Backward-compatible result roster derived from stored fingerprints.

    This cannot recover a driver who retired before a representative race lap
    existed, which is why the pipeline should pass the full FastF1 result map
    when saving R/S sessions. It does keep older stored files readable.
    """
    out = {}
    for fp in rf.fingerprints:
        out[fp.driver_code] = {
            "finishing_position": getattr(fp, "finishing_position", None),
            "grid_position": getattr(fp, "grid_position", None),
            "positions_gained": getattr(fp, "positions_gained", None),
            "result_status": getattr(fp, "result_status", "") or "",
            "laps_completed": getattr(fp, "laps_completed", None),
        }
    return out


# ─────────────────────────────────────────────────────────
#  Save
# ─────────────────────────────────────────────────────────
def save_fingerprints(
    rf: RaceFingerprints,
    stint_data_map: dict = None,
    session_results_map: dict = None,
):
    """Persist a RaceFingerprints object to the store.

    Args:
        rf:              RaceFingerprints to save.
        stint_data_map:  Optional ``{driver_code: [stint_dicts]}`` from race
                         sessions. It is stored alongside fingerprints for
                         downstream stint/race-context analysis.
    """
    _ensure_store()
    path = _race_path(rf.year, rf.race_round, rf.session_type)
    # Race/Sprint sessions need the full official result roster, not only the
    # subset of drivers for whom a representative pace lap could be built.
    # ``session_results_map`` is normally supplied by the pipeline. As a
    # backwards-compatible fallback, derive what we can from fingerprints.
    if session_results_map is None:
        session_results_map = _load_fastf1_session_results(
            rf.year, rf.race_round, rf.session_type
        )
    if not session_results_map:
        session_results_map = _results_from_fingerprints(rf)

    data = {
        "circuit_name": rf.circuit_name,
        "circuit_type": rf.circuit_type,
        "race_round": rf.race_round,
        "year": rf.year,
        "session_type": rf.session_type,
        "fingerprints": [asdict(fp) for fp in rf.fingerprints],
        "stint_data": stint_data_map or {},
        "session_results": session_results_map or {},
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _update_index(rf)
    print(f"  Saved {len(rf.fingerprints)} fingerprints → {path}")


def _update_index(rf: RaceFingerprints):
    idx_path = _index_path()
    index = load_index()
    key = f"{rf.year}_R{rf.race_round:02d}_{rf.session_type}"
    index[key] = {
        "circuit_name": rf.circuit_name,
        "circuit_type": rf.circuit_type,
        "race_round": rf.race_round,
        "year": rf.year,
        "session_type": rf.session_type,
        "n_fingerprints": len(rf.fingerprints),
        "path": os.path.basename(_race_path(rf.year, rf.race_round, rf.session_type)),
    }

    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────
#  Load
# ─────────────────────────────────────────────────────────
def load_index() -> dict:
    idx_path = _index_path()
    if not os.path.exists(idx_path):
        return {}
    with open(idx_path, encoding="utf-8") as f:
        return json.load(f)


def load_session_payload(year: int, round_num: int, session: str) -> dict | None:
    """Return the raw stored session payload, including ``stint_data``.

    This accessor is deliberately separate from ``load_fingerprints`` so the
    43-field fingerprint dataclass contract does not have to absorb auxiliary
    race-session data. It also gives the race-knowledge layer access to stored
    stint information without re-reading FastF1.
    """
    path = _race_path(year, round_num, session)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_session_results(year: int, round_num: int, session: str = "R") -> dict:
    """Load the full official result roster stored for a session.

    New R/S artifacts contain every starter, including drivers who retired too
    early to produce a representative pace fingerprint. Older artifacts fall
    back to result fields embedded in the available fingerprints.
    """
    payload = load_session_payload(year, round_num, session)
    if not payload:
        return {}
    results = payload.get("session_results") or {}
    if results:
        return results

    out = {}
    for fp in payload.get("fingerprints", []):
        code = fp.get("driver_code")
        if not code:
            continue
        out[code] = {
            "finishing_position": fp.get("finishing_position"),
            "grid_position": fp.get("grid_position"),
            "positions_gained": fp.get("positions_gained"),
            "result_status": fp.get("result_status", "") or "",
            "laps_completed": fp.get("laps_completed"),
        }
    return out


def load_stint_data(year: int, round_num: int, session: str = "R") -> dict:
    """Load stored per-driver stint data for a session.

    Returns an empty dict when the session does not exist or was saved without
    stint data. ``degradation_rate`` in these records is a fitted lap-time
    trend, not a direct measurement of tyre degradation; interpretation belongs
    in the analysis/UI layer.
    """
    payload = load_session_payload(year, round_num, session)
    if not payload:
        return {}
    return payload.get("stint_data") or {}


def load_fingerprints(year: int, round_num: int, session: str) -> RaceFingerprints | None:
    data = load_session_payload(year, round_num, session)
    if data is None:
        return None
    fps = [CarFingerprint(**fp) for fp in data["fingerprints"]]
    return RaceFingerprints(
        circuit_name=data["circuit_name"],
        circuit_type=data["circuit_type"],
        race_round=data["race_round"],
        year=data["year"],
        session_type=data["session_type"],
        fingerprints=fps,
    )


def load_all_fingerprints(
    year: int = 2026,
    sessions: list | str | None = None,
) -> list[RaceFingerprints]:
    """Load stored fingerprints for a season, filtered by session type(s).

    Args:
        year:     Season year.
        sessions: Session type or list of types. Defaults to ["Q"].
                  Examples: "Q", ["Q", "SQ"], ["R", "S"].

    Discovery intentionally comes from ``store/index.json``. A session file
    written without an index update is not considered part of the committed
    analytical store.
    """
    if sessions is None:
        sessions = ["Q"]
    elif isinstance(sessions, str):
        sessions = [sessions]

    index = load_index()
    result = []
    for _, meta in sorted(index.items()):
        if meta["year"] == year and meta["session_type"] in sessions:
            rf = load_fingerprints(year, meta["race_round"], meta["session_type"])
            if rf:
                result.append(rf)
    return result


def load_driver_history(driver_code: str, year: int = 2026) -> list[CarFingerprint]:
    all_races = load_all_fingerprints(year)
    return [
        fp
        for rf in all_races
        for fp in rf.fingerprints
        if fp.driver_code == driver_code
    ]


def load_pu_history(pu_name: str, year: int = 2026) -> list[CarFingerprint]:
    all_races = load_all_fingerprints(year)
    return [
        fp
        for rf in all_races
        for fp in rf.fingerprints
        if fp.pu_name == pu_name
    ]


def print_store_summary():
    index = load_index()
    if not index:
        print("  Race store is empty.")
        return
    print(f"\n  Race Store — {len(index)} sessions saved:")
    for key, meta in sorted(index.items()):
        print(
            f"    {key:<20} {meta['circuit_name']:<30} "
            f"{meta['n_fingerprints']} cars"
        )
