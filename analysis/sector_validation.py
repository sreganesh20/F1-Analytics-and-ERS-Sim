#sector_validation.py
"""
analysis/sector_validation.py

Cross-validates our fingerprint speed deltas against official F1 sector times.
Checks: do our segment-level speed deltas directionally match sector time gaps?

Run: python analysis/sector_validation.py
"""

import sys
import os
import pandas as pd
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.race_store import load_all_fingerprints
from config import CIRCUITS

# ─────────────────────────────────────────────
# Sector → segment type mapping per circuit
# S1/S2/S3 each dominated by a particular segment type
# ─────────────────────────────────────────────
SECTOR_CHARACTERISTICS = {
    "Australia": {
        "S1": "straight",   # Main straight into T1
        "S2": "braking",    # Technical middle sector, heavy braking
        "S3": "corner",     # Final sector, flowing corners
    },
    "China": {
        "S1": "corner",     # T1-T6 technical
        "S2": "straight",   # Back straight — T14 braking is END of S2
        "S3": "balanced",   # Final mixed sector — don't use for validation
    },
    "Japan": {
        "S1": "corner",     # Esses + Degners
        "S2": "straight",   # Back straight + 130R approach
        "S3": "braking",    # Spoon + chicane
    },
}


def load_sector_times(circuit_name: str, circuit_cfg: dict) -> pd.DataFrame | None:
    """Load official sector times from FastF1 for a circuit."""
    try:
        import fastf1
        cache_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "cache")
        )
        fastf1.Cache.enable_cache(cache_dir)

        session = fastf1.get_session(
            circuit_cfg["fastf1_year"],
            circuit_cfg["fastf1_name"],
            circuit_cfg.get("fastf1_session", "Q"),
        )
        session.load(telemetry=False, weather=False)

        laps = session.laps[["Driver", "LapTime", "Sector1Time", "Sector2Time", "Sector3Time"]].copy()
        laps = laps.dropna(subset=["LapTime"])

        # Keep fastest lap per driver
        laps["LapTime_s"] = laps["LapTime"].dt.total_seconds()
        laps["S1_s"]      = laps["Sector1Time"].dt.total_seconds()
        laps["S2_s"]      = laps["Sector2Time"].dt.total_seconds()
        laps["S3_s"]      = laps["Sector3Time"].dt.total_seconds()

        fastest = laps.loc[laps.groupby("Driver")["LapTime_s"].idxmin()]
        fastest = fastest.dropna(subset=["S1_s", "S2_s", "S3_s"])

        # Compute deltas vs pole
        ref_driver = fastest.loc[fastest["LapTime_s"].idxmin(), "Driver"]
        ref_row    = fastest[fastest["Driver"] == ref_driver].iloc[0]

        fastest = fastest.copy()
        fastest["S1_delta"] = fastest["S1_s"] - ref_row["S1_s"]
        fastest["S2_delta"] = fastest["S2_s"] - ref_row["S2_s"]
        fastest["S3_delta"] = fastest["S3_s"] - ref_row["S3_s"]
        fastest["ref_driver"] = ref_driver

        print(f"  Loaded sector times: {circuit_name} — ref: {ref_driver} "
              f"({len(fastest)} drivers)")
        return fastest[["Driver", "S1_delta", "S2_delta", "S3_delta",
                         "LapTime_s", "ref_driver"]]

    except Exception as e:
        print(f"  Could not load sector times for {circuit_name}: {e}")
        return None


def validate_circuit(circuit_name: str) -> dict:
    """
    Validate fingerprint deltas against sector times for one circuit.
    Returns correlation metrics.
    """
    circuit_cfg = CIRCUITS[circuit_name]
    chars       = SECTOR_CHARACTERISTICS.get(circuit_name, {})

    print(f"\n{'═'*60}")
    print(f"  Validating: {circuit_name}")
    print(f"{'═'*60}")

    # Load sector times
    sector_df = load_sector_times(circuit_name, circuit_cfg)
    if sector_df is None:
        return {}

    # Load fingerprints for this circuit
    all_fps  = load_all_fingerprints()
    race_fps = next((rf for rf in all_fps
                     if rf.circuit_name == circuit_name
                     and rf.session_type == "Q"), None)

    if race_fps is None:
        print(f"  No fingerprints found for {circuit_name}")
        return {}

    # Build comparison table
    rows = []
    for fp in race_fps.fingerprints:
        sec = sector_df[sector_df["Driver"] == fp.driver_code]
        if sec.empty:
            continue

        row = sec.iloc[0]
        rows.append({
            "driver":          fp.driver_code,
            "pu":              fp.pu_name,
            "S1_delta":        row["S1_delta"],
            "S2_delta":        row["S2_delta"],
            "S3_delta":        row["S3_delta"],
            "str_speed_delta": fp.straight_speed_delta_kph,
            "brk_speed_delta": fp.braking_speed_delta_kph,
            "cor_speed_delta": fp.corner_speed_delta_kph,
            "lap_gap_pct":     fp.lap_time_gap_pct,
        })

    if not rows:
        print("  No matching drivers between fingerprints and sector times")
        return {}

    df = pd.DataFrame(rows)

    # Map sector deltas to our delta types based on circuit characteristics
    # Positive sector delta = slower = should correspond to negative speed delta
    sector_to_our = {
        "straight": ("S2_delta", "str_speed_delta"),
        "braking":  ("S3_delta", "brk_speed_delta"),
        "corner":   ("S1_delta", "cor_speed_delta"),
    }

    results = {}
    print(f"\n  {'Driver':<6} {'PU':<14} "
          f"{'S1Δ':>6} {'S2Δ':>6} {'S3Δ':>6}  "
          f"{'StrΔ':>7} {'BrkΔ':>7} {'CorΔ':>7}  {'Match?'}")
    print(f"  {'─'*6} {'─'*14} "
          f"{'─'*6} {'─'*6} {'─'*6}  "
          f"{'─'*7} {'─'*7} {'─'*7}  {'─'*6}")

    for _, row in df.sort_values("S2_delta").iterrows():
        # Direction match: slower sector (positive delta) should = slower speed (negative delta)
        s2_dir    = "↑" if row["S2_delta"] > 0 else "↓"
        str_dir   = "↓" if row["str_speed_delta"] < 0 else "↑"
        match_str = "✓" if s2_dir == str_dir else "✗"

        print(f"  {row['driver']:<6} {row['pu']:<14} "
              f"{row['S1_delta']:>+6.3f} {row['S2_delta']:>+6.3f} {row['S3_delta']:>+6.3f}  "
              f"{row['str_speed_delta']:>+7.1f} {row['brk_speed_delta']:>+7.1f} "
              f"{row['cor_speed_delta']:>+7.1f}  {match_str}")

    # Compute correlations
    for seg_type, (sec_col, our_col) in sector_to_our.items():
        if sec_col in df.columns and our_col in df.columns:
            valid = df[[sec_col, our_col]].dropna()
            if len(valid) > 3:
                # Sector delta positive = slower, speed delta negative = slower
                # So we expect negative correlation
                corr = valid[sec_col].corr(-valid[our_col])
                results[seg_type] = corr
                verdict = "✓ GOOD" if corr > 0.7 else ("⚠ WEAK" if corr > 0.4 else "✗ POOR")
                print(f"\n  {seg_type:<12} correlation: {corr:.3f}  {verdict}")
                print(f"    (sector col: {sec_col}, our col: {our_col})")

    return results


def run_validation():
    """Run validation for all circuits with data."""
    circuits = ["Australia", "China", "Japan"]
    all_results = {}

    print("\n" + "█"*60)
    print("  Sector Time Validation")
    print("█"*60)

    for circuit in circuits:
        if circuit in CIRCUITS:
            results = validate_circuit(circuit)
            all_results[circuit] = results

    # Summary
    print(f"\n{'═'*60}")
    print("  Summary")
    print(f"{'═'*60}")
    for circuit, results in all_results.items():
        if results:
            vals = [v for v in results.values() if not np.isnan(v)]
            avg  = np.mean(vals) if vals else 0.0
            verdict = "✓ TRUSTWORTHY" if avg > 0.7 else \
                      ("⚠ PARTIALLY VALID" if avg > 0.4 else "✗ NEEDS FIX")
            print(f"  {circuit:<15} avg correlation: {avg:.3f}  {verdict}")
        else:
            print(f"  {circuit:<15} no results")

    return all_results


if __name__ == "__main__":
    run_validation()