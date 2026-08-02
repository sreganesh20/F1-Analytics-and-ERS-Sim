"""
pipeline/race_pipeline.py
"""

import sys
import os
import pandas as pd
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fetcher import load_telemetry, generate_synthetic_telemetry
from models.track import segment_lap, print_track_summary
from models.optimizer import optimise, print_strategy_summary
from models.fingerprint import fingerprint_race, print_race_fingerprints
from data.race_store import save_fingerprints, print_store_summary
from config import CIRCUITS, CARS


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
    except Exception as e:
        print(f"  Could not load full session: {e}")
        full_session = None

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
                    if drv_code not in CARS:
                        continue

                    lt = rep_lap["LapTime"]
                    if pd.isna(lt):
                        continue

                    lap_time_s = lt.total_seconds()

                    if is_dnf:
                        retirements.append(drv_code)
                        print(f"  {drv_code:<6} DNF — {laps_completed}/{total_race_laps} laps")

                    try:
                        tel = rep_lap.get_car_data().add_distance()
                    except Exception as e:
                        print(f"  {drv_code} telemetry error: {e}")
                        continue

                    driver_stint_data[drv_code] = stint_data

                else:
                    # Qualifying / SQ: pick fastest lap
                    fastest = drv_laps.pick_fastest()
                    if fastest is None:
                        continue

                    drv_code = fastest["Driver"]
                    if drv_code not in CARS:
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
                        tel = fastest.get_car_data().add_distance()
                    except Exception as e:
                        print(f"  {drv_code} telemetry error: {e}")
                        continue

                    stint_data = []

                # ── Build car DataFrame (same for both paths) ──
                car_df = pd.DataFrame({
                    "Distance":  tel["Distance"].values,
                    "Speed":     tel["Speed"].values,
                    "Throttle":  tel["Throttle"].values,
                    "Brake":     tel["Brake"].astype(float).values,
                    "Gear":      tel["nGear"].values,
                    "RPM":       tel["RPM"].values,
                    "DeltaTime": tel["Time"].diff().dt.total_seconds().fillna(0).values,
                    "X":         np.nan,
                    "Y":         np.nan,
                })
                car_df["Source"]  = "FastF1"
                car_df["Driver"]  = drv_code
                car_df["LapTime"] = lap_time_s

                car_info = CARS[drv_code]
                driver_telemetry[drv_code]  = car_df
                lap_times[drv_code]         = lap_time_s
                driver_laps_compl[drv_code] = laps_completed

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
