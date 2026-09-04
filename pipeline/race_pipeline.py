"""
pipeline/race_pipeline.py
"""

import sys
import os
import pandas as pd
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fetcher import load_telemetry, generate_synthetic_telemetry, lap_telemetry
from models.track import segment_lap, print_track_summary
from models.optimizer import optimise, print_strategy_summary
from models.fingerprint import fingerprint_race, print_race_fingerprints
from data.race_store import save_fingerprints, print_store_summary
from config import CIRCUITS, CARS, lineup_for_round


# ─────────────────────────────────────────────────────────
#  Race pace helper — stint-grouped IQR representative lap
# ─────────────────────────────────────────────────────────

def _get_representative_race_lap(drv_laps: pd.DataFrame, total_race_laps: int):
    """
    Get representative race pace lap using stint-grouped IQR filtering.

    Returns:
        (rep_lap_row, stint_data_list, laps_completed, is_dnf)
        rep_lap_row:     pandas Series (single lap row) or None
        stint_data_list: list of dicts [{stint, compound, avg_pace, stint_length, degradation_rate}]
        laps_completed:  int
        is_dnf:          bool
    """
    laps_completed = len(drv_laps)
    is_dnf = laps_completed < total_race_laps * 0.30

    # Green flag laps from lap 5 onward
    green = drv_laps[
        (drv_laps["LapNumber"] >= 5) &
        (drv_laps["TrackStatus"].astype(str) == "1") &
        drv_laps["LapTime"].notna()
    ].copy()

    if green.empty:
        return None, [], laps_completed, is_dnf

    green["LapTime_s"] = green["LapTime"].dt.total_seconds()

    stint_data   = []
    filtered_dfs = []

    for stint_num, stint_laps in green.groupby("Stint"):
        if len(stint_laps) < 2:
            continue

        times    = stint_laps["LapTime_s"].values
        lap_nums = stint_laps["LapNumber"].values

        median = np.median(times)
        q1, q3  = np.percentile(times, 25), np.percentile(times, 75)
        iqr     = q3 - q1
        mask    = times <= (median + 1.5 * iqr)

        valid = stint_laps[mask]
        if valid.empty:
            continue

        valid_times    = valid["LapTime_s"].values
        valid_lap_nums = valid["LapNumber"].values

        avg_pace     = float(np.mean(valid_times))
        stint_length = len(valid)
        deg_rate     = float(np.polyfit(valid_lap_nums, valid_times, 1)[0]) \
                       if len(valid_times) >= 2 else 0.0

        compound = str(stint_laps["Compound"].iloc[0]) \
                   if "Compound" in stint_laps.columns else "UNKNOWN"

        stint_data.append({
            "stint":            int(stint_num),
            "compound":         compound,
            "avg_pace":         avg_pace,
            "stint_length":     stint_length,
            "degradation_rate": deg_rate,
        })
        filtered_dfs.append(valid)

    if not filtered_dfs:
        return None, [], laps_completed, is_dnf

    total_len    = sum(s["stint_length"] for s in stint_data)
    weighted_avg = sum(s["avg_pace"] * s["stint_length"] for s in stint_data) / total_len

    all_filtered = pd.concat(filtered_dfs)
    diff         = (all_filtered["LapTime_s"] - weighted_avg).abs()
    rep_idx      = diff.idxmin()

    return rep_idx, stint_data, laps_completed, is_dnf


# ─────────────────────────────────────────────────────────
#  Main pipeline
# ─────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────
#  WAVE 1: Result / sector / pit-stop extraction
# ─────────────────────────────────────────────────────────

def _extract_session_results(full_session) -> dict:
    """
    Pull classified race results from FastF1 -> {driver_code: {...}}.
    Returns {} for sessions with no results (some quali sessions).
    """
    out = {}
    try:
        res = full_session.results
        if res is None or res.empty:
            return {}
        for _, row in res.iterrows():
            code = row.get("Abbreviation")
            if not code:
                continue
            pos  = row.get("Position")
            grid = row.get("GridPosition")
            pos_i  = int(pos)  if pd.notna(pos)  else None
            grid_i = int(grid) if pd.notna(grid) else None
            gained = (grid_i - pos_i) if (pos_i is not None and grid_i is not None) else None
            out[code] = {
                "finishing_position": pos_i,
                "grid_position":      grid_i,
                "positions_gained":   gained,
                "result_status":      str(row.get("Status", "")) or "",
            }
    except Exception as e:
        print(f"  Could not extract session results: {e}")
    return out


# Status strings that mean the car COMPLETED the race (classified finisher).
# FastF1 / Ergast use several forms for "finished, possibly a lap down".
FINISHER_STATUSES = {"finished", "lapped", "classified"}


def _is_dnf_from_status(status: str) -> bool:
    """
    Authoritative DNF determination from FastF1's classified result status.

    FINISHER statuses:  "Finished", "Lapped", "+1 Lap", "+2 Laps"
    DNF statuses:       "Retired", "Accident", "Collision", "Engine",
                        "Power Unit", "Gearbox", "Hydraulics", "Disqualified",
                        "Withdrew", "Spun off", ...

    History:
      v1 used a lap-count heuristic (laps < 30% of distance) — caught only very
      early retirements. Monaco 2026 had 7 DNFs; it flagged 1.
      v2 whitelisted only "Finished"/"+N Lap" — misclassified every LAPPED
      finisher as a DNF (Hungary 2026 flagged 9 lapped runners as retirements).
      v3 (this) whitelists the full finisher set incl. "Lapped".
    """
    if not status:
        return False
    s = str(status).strip().lower()
    if s in FINISHER_STATUSES:
        return False
    if s.startswith("finished"):
        return False
    if s.startswith("+"):          # "+1 Lap", "+2 Laps"
        return False
    return True                    # everything else = did not finish


def _extract_lap_extras(drv_laps: pd.DataFrame, rep_lap) -> dict:
    """
    Sector times from the representative/fastest lap, plus pit + fastest-lap
    stats across the driver's whole session.

    NOTE ON PIT DATA: FastF1 exposes PitInTime / PitOutTime only, which gives
    PIT LANE TRANSIT time (entry loop -> exit loop, includes the 60kph drive
    through). It does NOT expose STATIONARY time (the ~2s DHL 'fastest pit
    stop' figure). Stationary times must come from an external source.
    """
    extras = {
        "sector_1_s": None, "sector_2_s": None, "sector_3_s": None,
        "best_sector_1_s": None, "best_sector_2_s": None, "best_sector_3_s": None,
        "pit_stops": 0, "pit_lane_time_s": None, "tyre_compounds": [],
        "fastest_lap_s": None, "fastest_lap_number": None,
    }

    # PERSONAL BEST sector across every lap of the session.
    # The rep-lap sectors above all belong to one lap, so the fastest driver
    # sweeps all three — useless as a "fastest sector" stat. These are real
    # per-driver bests, taken independently per sector from any lap.
    try:
        for i, col in enumerate(["Sector1Time", "Sector2Time", "Sector3Time"], start=1):
            if col in drv_laps.columns:
                vals = drv_laps[col].dropna()
                if not vals.empty:
                    extras[f"best_sector_{i}_s"] = float(vals.min().total_seconds())
    except Exception:
        pass

    # Sector times from the representative lap
    try:
        for i, key in enumerate(["Sector1Time", "Sector2Time", "Sector3Time"], start=1):
            val = rep_lap.get(key) if hasattr(rep_lap, "get") else None
            if val is not None and pd.notna(val):
                extras[f"sector_{i}_s"] = float(val.total_seconds())
    except Exception:
        pass

    # Pit stops = COMPOUND CHANGES, after merging consecutive same-compound stints.
    #
    # Why not PitInTime, and why not raw stint count? Both count pit LANE ENTRIES,
    # which include safety-car and red-flag entries where no tyre change happens.
    # Verified against Monaco 2026 raw data:
    #     HUL stints: MEDIUM(12) HARD(46) HARD(1) HARD(6) HARD(2) SOFT(1) SOFT(10)
    # Three consecutive HARD stints and a one-lap SOFT stint are not pit stops —
    # they are the field being cycled through the pit lane during a race event.
    # Both ANT and HUL had boundaries clustered in laps 59-69, the same window.
    #
    # Merging consecutive identical compounds gives ANT and HUL 2 stops each,
    # which matches a real Monaco race.
    #
    # Known trade-off: a genuine stop onto a FRESH SET OF THE SAME COMPOUND is
    # merged away and undercounted. That is rarer than the safety-car over-count
    # and errs conservative, which is the right direction for a published stat.
    try:
        if "Stint" in drv_laps.columns and "Compound" in drv_laps.columns:
            seq = (drv_laps.sort_values("LapNumber")
                           .groupby("Stint")["Compound"]
                           .first()
                           .sort_index()
                           .tolist())
            merged = [c for i, c in enumerate(seq) if i == 0 or c != seq[i - 1]]
            extras["pit_stops"]       = max(0, len(merged) - 1)
            extras["tyre_compounds"]  = merged          # e.g. ["MEDIUM","HARD","SOFT"]
    except Exception:
        pass

    # Best pit lane transit (separate from stop count)
    try:
        if "PitInTime" in drv_laps.columns:
            pit_in_laps = drv_laps[drv_laps["PitInTime"].notna()]
            transits = []
            for _, in_lap in pit_in_laps.iterrows():
                lap_no  = in_lap.get("LapNumber")
                out_lap = drv_laps[(drv_laps["LapNumber"] == (lap_no + 1))
                                   & (drv_laps["PitOutTime"].notna())]
                if out_lap.empty:
                    continue
                t_in  = in_lap["PitInTime"]
                t_out = out_lap.iloc[0]["PitOutTime"]
                if pd.notna(t_in) and pd.notna(t_out):
                    dt = (t_out - t_in).total_seconds()
                    if 10.0 < dt < 90.0:   # sanity band for a pit lane transit
                        transits.append(dt)
            if transits:
                extras["pit_lane_time_s"] = float(min(transits))
    except Exception:
        pass

    # Outright fastest lap of the session for this driver
    try:
        valid = drv_laps[drv_laps["LapTime"].notna()]
        if not valid.empty:
            best = valid.loc[valid["LapTime"].idxmin()]
            extras["fastest_lap_s"] = float(best["LapTime"].total_seconds())
            if pd.notna(best.get("LapNumber")):
                extras["fastest_lap_number"] = int(best["LapNumber"])
    except Exception:
        pass

    return extras


def run_race_pipeline(
    circuit_name:         str,
    force_synthetic:      bool = False,
    save:                 bool = True,
    verbose:              bool = True,
    circuit_cfg_override: dict = None,
) -> dict:

    circuit_cfg  = circuit_cfg_override or CIRCUITS.get(circuit_name)
    if circuit_cfg is None:
        raise ValueError(f"Unknown circuit: {circuit_name}. Check config.CIRCUITS.")

    session_type    = circuit_cfg.get("fastf1_session", "Q")
    # Who actually drove this round, not who normally drives. Reverts
    # automatically for any round without an override entry.
    cars            = lineup_for_round(circuit_cfg["round"])
    is_race_session = session_type in ("R", "S")

    print(f"\n{'-'*60}")
    print(f"  Race Pipeline: {circuit_name}  "
          f"[{session_type} — Rd {circuit_cfg['round']} — {circuit_cfg.get('fastf1_year', 2026)}]")
    print(f"{'-'*60}")

    # ── Stage 1: Load reference telemetry ─────────────────
    print("\n[1/5] Loading telemetry...")
    ref_df = load_telemetry(
        circuit_name    = circuit_name,
        circuit_cfg     = circuit_cfg,
        force_synthetic = force_synthetic,
    )

    # ── Stage 2: Segment the track ────────────────────────
    print("\n[2/5] Segmenting track...")
    segments = segment_lap(ref_df)
    if verbose:
        print_track_summary(segments, circuit_name)

    # ── Stage 3: Compute theoretical optimal ──────────────
    print("\n[3/5] Computing theoretical optimal strategy...")
    optimal = optimise(segments, circuit_cfg)
    if verbose:
        print_strategy_summary(optimal)

    # ── Stage 4: Load per-driver telemetry & fingerprint ──
    print("\n[4/5] Fingerprinting cars...")

    driver_telemetry    = {}
    lap_times           = {}
    retirements         = []
    driver_laps_compl   = {}   # driver_code → laps completed
    driver_stint_data   = {}   # driver_code → list of stint dicts (race sessions only)
    driver_result_map   = {}   # WAVE 1: driver_code → result/sector/pit dict

    try:
        import fastf1
        cache_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "cache")
        )
        fastf1.Cache.enable_cache(cache_dir)
        full_session = fastf1.get_session(
            circuit_cfg["fastf1_year"],
            circuit_cfg["fastf1_name"],
            session_type,
        )
        full_session.load(telemetry=True, weather=False)
        print(f"  Session loaded — {len(full_session.drivers)} drivers")
        session_results = _extract_session_results(full_session)
        if session_results:
            print(f"  Classified results extracted for {len(session_results)} drivers")
            # Surface the status distribution so any UNKNOWN status is visible
            from collections import Counter
            _statuses = Counter(r.get("result_status", "") for r in session_results.values())
            _summary = ", ".join(f"{k or '(blank)'}x{v}" for k, v in _statuses.most_common())
            print(f"  Result statuses: {_summary}")
            _unknown = [k for k in _statuses
                        if k and _is_dnf_from_status(k)
                        and k.strip().lower() not in
                        {"retired","accident","collision","engine","gearbox","power unit",
                         "hydraulics","disqualified","withdrew","spun off","transmission",
                         "brakes","suspension","electrical","overheating","mechanical",
                         "puncture","wheel","water leak","oil leak","fuel pressure",
                         "did not start","electronics","clutch","driveshaft","differential",
                         "steering","exhaust","tyre","radiator","battery","turbo","ers",
                         "cooling system","seat","damage","illness","fuel system"}]
            if _unknown:
                print(f"  NOTE: unrecognised status(es) treated as DNF: {_unknown}")
    except Exception as e:
        print(f"  Could not load full session: {e}")
        full_session = None
        session_results = {}

    if full_session is not None:

        # Total race laps for DNF detection
        total_race_laps = None
        if is_race_session:
            total_race_laps = int(full_session.laps["LapNumber"].max())
            print(f"  Race laps: {total_race_laps}")

        for drv_num in full_session.drivers:
            try:
                drv_laps = full_session.laps.pick_driver(drv_num)
                if drv_laps.empty:
                    continue

                # ── Lap selection branch ───────────────────
                if is_race_session:
                    rep_idx, stint_data, laps_completed, is_dnf = \
                        _get_representative_race_lap(drv_laps, total_race_laps)

                    if rep_idx is None:
                        continue

                    rep_lap = drv_laps.loc[rep_idx]         
                    drv_code = rep_lap["Driver"]
                    if drv_code not in cars:
                        continue

                    lt = rep_lap["LapTime"]
                    if pd.isna(lt):
                        continue

                    lap_time_s = lt.total_seconds()

                    # AUTHORITATIVE DNF: use classified result status when available,
                    # fall back to the lap-count heuristic only if results are missing.
                    _res = session_results.get(drv_code, {})
                    _status = _res.get("result_status", "")
                    if _status:
                        is_dnf = _is_dnf_from_status(_status)

                    if is_dnf:
                        retirements.append(drv_code)
                        _reason = f" [{_status}]" if _status else ""
                        print(f"  {drv_code:<6} DNF — {laps_completed}/{total_race_laps} laps{_reason}")

                    try:
                        tel = lap_telemetry(rep_lap)
                    except Exception as e:
                        print(f"  {drv_code} telemetry error: {e}")
                        continue

                    driver_stint_data[drv_code] = stint_data
                    _extras = _extract_lap_extras(drv_laps, rep_lap)

                else:
                    # Qualifying / SQ: pick fastest lap
                    fastest = drv_laps.pick_fastest()
                    if fastest is None:
                        continue

                    drv_code = fastest["Driver"]
                    if drv_code not in cars:
                        continue

                    lt = fastest["LapTime"]
                    if pd.isna(lt):
                        continue

                    lap_time_s   = lt.total_seconds()
                    laps_completed = 1

                    # Confidence filter — skip clearly corrupted laps
                    valid_times = [
                        l["LapTime"].total_seconds()
                        for _, l in drv_laps.iterrows()
                        if pd.notna(l["LapTime"])
                    ]
                    if len(valid_times) > 1:
                        median_time = sorted(valid_times)[len(valid_times) // 2]
                        if lap_time_s > median_time * 1.05:
                            print(f"  {drv_code:<6} {lap_time_s:.1f}s >5% off median "
                                  f"{median_time:.1f}s — skipping")
                            continue

                    try:
                        tel = lap_telemetry(fastest)
                    except Exception as e:
                        print(f"  {drv_code} telemetry error: {e}")
                        continue

                    stint_data = []
                    _extras = _extract_lap_extras(drv_laps, fastest)

                # ── Build car DataFrame (same for both paths) ──
                car_df = pd.DataFrame({
                    "Distance":  tel["Distance"].values,
                    "Speed":     tel["Speed"].values,
                    "Throttle":  tel["Throttle"].values,
                    "Brake":     tel["Brake"].astype(float).values,
                    "Gear":      tel["nGear"].values,
                    "RPM":       tel["RPM"].values,
                    "DeltaTime": tel["Time"].diff().dt.total_seconds().fillna(0).values,
                    "X":         tel["X"].values if "X" in tel.columns else np.nan,
                    "Y":         tel["Y"].values if "Y" in tel.columns else np.nan,
                })
                car_df["Source"]  = "FastF1"
                car_df["Driver"]  = drv_code
                car_df["LapTime"] = lap_time_s

                car_info = cars[drv_code]
                driver_telemetry[drv_code]  = car_df
                lap_times[drv_code]         = lap_time_s
                driver_laps_compl[drv_code] = laps_completed
                driver_result_map[drv_code] = {
                    **session_results.get(drv_code, {}),
                    **_extras,
                }

                pace_note = f"{len(stint_data)} stints" if is_race_session else "FastF1"
                print(f"  {drv_code:<6} {car_info['team']:<20} {lap_time_s:.3f}s  {pace_note}")

            except Exception as e:
                print(f"  Error processing driver #{drv_num}: {e}")
                continue

    # ── Build fingerprints ─────────────────────────────────
    if driver_telemetry:
        race_fingerprints = fingerprint_race(
            driver_telemetry  = driver_telemetry,
            lap_times         = lap_times,
            segments          = segments,
            optimal           = optimal,
            circuit_name      = circuit_name,
            circuit_cfg       = circuit_cfg,
            retirements       = retirements,
            laps_completed_map = driver_laps_compl,
            result_map        = driver_result_map,
        )
        print_race_fingerprints(race_fingerprints)
    else:
        print("  No valid driver data — cannot fingerprint")
        return {
            "circuit":      circuit_name,
            "segments":     segments,
            "optimal":      optimal,
            "fingerprints": None,
        }

    # ── Stage 5: Save ──────────────────────────────────────
    if save:
        print("\n[5/5] Saving to race store...")
        save_fingerprints(race_fingerprints, stint_data_map=driver_stint_data)
        print_store_summary()
    else:
        print("\n[5/5] Skipping save (save=False)")

    # Auto-trigger SQ for qualifying weekends (existing behaviour)
    if circuit_cfg.get("has_sprint") and not force_synthetic \
            and not circuit_cfg_override and session_type == "Q":
        print(f"\n  Sprint weekend — also processing SQ session...")
        sprint_cfg = {**circuit_cfg, "fastf1_session": "SQ"}
        run_race_pipeline(
            circuit_name         = circuit_name,
            force_synthetic      = False,
            save                 = save,
            verbose              = False,
            circuit_cfg_override = sprint_cfg,
        )

    return {
        "circuit":      circuit_name,
        "segments":     segments,
        "optimal":      optimal,
        "fingerprints": race_fingerprints,
        "stint_data":   driver_stint_data,
    }


# ─────────────────────────────────────────────────────────
#  Race session entry points
# ─────────────────────────────────────────────────────────

def run_race_session(circuit_name: str, verbose: bool = False):
    """Load and fingerprint race (R) session. Auto-loads Sprint (S) if applicable."""
    circuit_cfg = CIRCUITS.get(circuit_name)
    if circuit_cfg is None:
        raise ValueError(f"Unknown circuit: {circuit_name}")

    race_cfg = {**circuit_cfg, "fastf1_session": "R"}
    run_race_pipeline(
        circuit_name         = circuit_name,
        force_synthetic      = False,
        save                 = True,
        verbose              = verbose,
        circuit_cfg_override = race_cfg,
    )

    if circuit_cfg.get("has_sprint"):
        print(f"\n  Sprint weekend — also loading S session...")
        sprint_cfg = {**circuit_cfg, "fastf1_session": "S"}
        run_race_pipeline(
            circuit_name         = circuit_name,
            force_synthetic      = False,
            save                 = True,
            verbose              = verbose,
            circuit_cfg_override = sprint_cfg,
        )


def run_all_known_races(force_synthetic: bool = False, verbose: bool = False):
    """Process qualifying sessions for all races with available data."""
    known_races = ["Australia", "China", "Japan"]
    results     = {}

    print("\n" + "█"*60)
    print("  Processing all known 2026 races")
    print("█"*60)

    for circuit in known_races:
        try:
            result = run_race_pipeline(
                circuit_name    = circuit,
                force_synthetic = force_synthetic,
                save            = True,
                verbose         = verbose,
            )
            results[circuit] = result
        except Exception as e:
            print(f"\n  ERROR processing {circuit}: {e}")
            import traceback
            traceback.print_exc()

    return results


# ─────────────────────────────────────────────────────────
#  Synthetic driver variation (testing only)
# ─────────────────────────────────────────────────────────

PU_SPEED_MODIFIERS = {
    "Mercedes":    {"straight": +0.015, "braking": +0.005, "corner": +0.010},
    "RedBullFord": {"straight": +0.012, "braking": +0.008, "corner": +0.005},
    "Ferrari":     {"straight": +0.008, "braking": +0.010, "corner": +0.012},
    "Audi":        {"straight": -0.005, "braking": -0.003, "corner": -0.002},
    "Honda":       {"straight": -0.080, "braking": -0.060, "corner": -0.020},
}

OVERWEIGHT_PENALTY_S_PER_KG = 0.030

TEAM_OVERWEIGHT_KG = {
    "Red Bull":     9.5,
    "McLaren":      4.0,
    "Williams":     4.4,
    "Alpine":       6.0,
    "Haas":         3.0,
    "Audi":         5.0,
    "Ferrari":      0.0,
    "Mercedes":     0.0,
    "Aston Martin": 3.0,
    "VCARB":        4.0,
    "Cadillac":     8.0,
}


if __name__ == "__main__":
    result = run_race_pipeline("China", force_synthetic=True, verbose=True)
