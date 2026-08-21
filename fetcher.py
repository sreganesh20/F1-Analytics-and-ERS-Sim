"""
data/fetcher.py

Pulls real FastF1 telemetry for 2026 circuits.
Falls back to realistic synthetic data if FastF1 is unavailable
(e.g. no internet, data not yet published).

Returns a standard DataFrame with columns:
  Distance, Speed, Throttle, Brake, Gear, RPM,
  DeltaTime, X, Y  (X/Y = GPS coordinates)
"""

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")
from config import CIRCUITS

# ─────────────────────────────────────────────
#  Single-lap telemetry — track-accurate Distance
# ─────────────────────────────────────────────

def lap_telemetry(lap):
    """
    Return telemetry for one lap with a Distance axis anchored to the true
    lap boundary.

    WHY THIS EXISTS
    ---------------
    The pipeline previously used get_car_data().add_distance(). That slices
    the lap by snapping to whole telemetry samples, so each driver's Distance
    zero sits at a slightly different physical point on track — measured at
    up to 56 m apart across the field at Silverstone SQ.

    Because track segments are fixed distance windows, that misalignment
    meant a "corner" window measured a different piece of tarmac for every
    car. It was the dominant source of corrupt corner deltas: Britain SQ had
    11 of 22 cars beyond +/-25 kph and a field median of -25.29 kph, which is
    not something a real field does.

    get_telemetry() pads the slice on both sides and interpolates an exact
    sample at each lap edge, which fixes the zero point. Subtracting
    Distance.iloc[0] then removes the residual pad offset so every lap starts
    at exactly 0.

    Falls back to the old method on failure rather than dropping the driver
    from the session entirely.
    """
    try:
        tel = lap.get_telemetry().copy()
    except Exception:
        tel = lap.get_car_data().add_distance().copy()
    tel["Distance"] = tel["Distance"] - tel["Distance"].iloc[0]
    return tel


# ─────────────────────────────────────────────
#  Real FastF1 fetch
# ─────────────────────────────────────────────

def fetch_real_telemetry(circuit_cfg: dict, driver: str = None):
    try:
        import fastf1
        import os

        cache_dir = os.path.join(os.path.dirname(__file__), "..", "cache")
        cache_dir = os.path.abspath(cache_dir)
        print(f"  Cache dir: {cache_dir}")
        os.makedirs(cache_dir, exist_ok=True)
        fastf1.Cache.enable_cache(cache_dir)

        session_type = circuit_cfg.get("fastf1_session", "Q")
        print(f"  Loading session: {circuit_cfg['fastf1_name']} {circuit_cfg['fastf1_year']} — {session_type}...")
        session = fastf1.get_session(
            circuit_cfg["fastf1_year"],
            circuit_cfg["fastf1_name"],
            session_type,
        )
        session.load(telemetry=True, weather=False)

        # Pick driver
        if driver:
            lap = session.laps.pick_driver(driver).pick_fastest()
        else:
            lap = session.laps.pick_fastest()

        drv_code = lap["Driver"]
        print(f"  Using fastest lap: {drv_code}  {lap['LapTime']}")

        tel = lap_telemetry(lap)

        # Normalise column names
        df = pd.DataFrame({
            "Distance": tel["Distance"].values,
            "Speed":    tel["Speed"].values,
            "Throttle": tel["Throttle"].values,    # 0–100 %
            "Brake":    tel["Brake"].astype(float).values,  # 0 or 1
            "Gear":     tel["nGear"].values,
            "RPM":      tel["RPM"].values,
            "DeltaTime": tel["Time"].diff().dt.total_seconds().fillna(0).values,
        })

        # GPS comes straight from the merged telemetry now. The previous
        # np.interp approach assumed position samples were evenly spaced in
        # distance, which they are not, so those X/Y values were wrong.
        df["X"] = tel["X"].values if "X" in tel.columns else np.nan
        df["Y"] = tel["Y"].values if "Y" in tel.columns else np.nan

        df["Source"] = "FastF1"
        df["Driver"] = drv_code
        return df

    except Exception as e:
        print(f"  FastF1 failed: {type(e).__name__}: {e}")  # was silent before
    return None


# ─────────────────────────────────────────────
#  Synthetic telemetry generator
#  Physics-accurate enough to develop and test
#  the energy model against.
# ─────────────────────────────────────────────

def generate_synthetic_telemetry(circuit_name: str) -> pd.DataFrame:
    """
    Minimal fallback when FastF1 is unavailable.
    Generates a flat constant-speed lap — no fake geometry.
    Just enough for the pipeline to run without crashing.
    Real FastF1 data replaces this entirely once available.
    """
    cfg        = CIRCUITS.get(circuit_name, {})
    lap_length = cfg.get("lap_length_km", 5.0) * 1000   # metres
    top_speed  = cfg.get("top_speed_kph", 300)
    n_points   = int(lap_length / 5)                     # one point per 5m

    distances  = np.linspace(0, lap_length, n_points)
    speeds     = np.full(n_points, top_speed * 0.75)     # conservative average speed
    dt         = 5.0 / (speeds / 3.6)
    lap_time   = float(dt.sum())

    df = pd.DataFrame({
        "Distance":  distances,
        "Speed":     speeds,
        "Throttle":  np.full(n_points, 70.0),
        "Brake":     np.zeros(n_points),
        "Gear":      np.full(n_points, 6),
        "RPM":       np.full(n_points, 11000),
        "DeltaTime": dt,
        "X":         np.full(n_points, np.nan),
        "Y":         np.full(n_points, np.nan),
        "LapTime":   lap_time,
    })

    df["Source"] = "Synthetic"
    df["Driver"] = "SIM"

    print(f"  Synthetic fallback for {circuit_name}: {n_points} points, "
          f"~{lap_time:.1f}s — replace with FastF1 data ASAP")
    return df

# ─────────────────────────────────────────────
#  Main entry point
# ─────────────────────────────────────────────

def load_telemetry(circuit_name: str, circuit_cfg: dict,
                   driver: str = None, force_synthetic: bool = False) -> pd.DataFrame:
    """
    Load telemetry for a circuit. Tries FastF1 first, falls back to synthetic.

    Args:
        circuit_name:    Key from config.CIRCUITS (e.g. "Australia")
        circuit_cfg:     Circuit dict from config.CIRCUITS
        driver:          Driver code override (e.g. "VER")
        force_synthetic: Skip FastF1 and use synthetic data directly
    """
    print(f"\n{'─'*50}")
    print(f"Loading telemetry: {circuit_name}")
    print(f"{'─'*50}")

    if not force_synthetic:
        df = fetch_real_telemetry(circuit_cfg, driver)
        if df is not None:
            return df

    return generate_synthetic_telemetry(circuit_name)


def load_all_circuits(force_synthetic: bool = False) -> dict:
    """
    Load telemetry for all 3 circuits.
    Returns: {"Australia": df, "China": df, "Japan": df}
    """
    
    results = {}
    for name, cfg in CIRCUITS.items():
        results[name] = load_telemetry(name, cfg, force_synthetic=force_synthetic)
    return results


if __name__ == "__main__":
    # Quick test
    data = load_all_circuits(force_synthetic=True)
    for name, df in data.items():
        print(f"\n{name}: {len(df)} rows | "
              f"Speed range: {df['Speed'].min():.0f}–{df['Speed'].max():.0f} kph | "
              f"Source: {df['Source'].iloc[0]}")
        print(df[["Distance", "Speed", "Throttle", "Brake"]].describe().round(1))
