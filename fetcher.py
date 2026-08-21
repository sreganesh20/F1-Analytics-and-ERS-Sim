"""
data/fetcher.py

Pulls real FastF1 telemetry for 2026 circuits.
Falls back to realistic synthetic data if FastF1 is unavailable
(e.g. no internet, data not yet published).

Returns a standard DataFrame with columns:
  Distance, Speed, Throttle, Brake, Gear, RPM,
  DeltaTime, X, Y  (X/Y = GPS coordinates)
"""

import json
import os

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")
from config import CIRCUITS

# ─────────────────────────────────────────────
#  Real FastF1 fetch
# ─────────────────────────────────────────────
def lap_telemetry(lap):
    """
    Track-accurate single-lap telemetry.

    get_telemetry() pads the slice and interpolates the lap edges, so Distance
    is anchored to the true lap boundary. get_car_data().add_distance() snaps
    to whole samples, giving every driver a different zero point — up to 56 m
    apart at Silverstone SQ. That misalignment corrupted the corner deltas,
    because a fixed distance window then measured a different piece of track
    for each car.

    Falls back to the old method rather than dropping a driver entirely.
    """
    try:
        tel = lap.get_telemetry().copy()
    except Exception:
        tel = lap.get_car_data().add_distance().copy()
    tel["Distance"] = tel["Distance"] - tel["Distance"].iloc[0]
    return tel
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

        tel = lap.get_car_data().add_distance()

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

        # Try to attach GPS
        try:
            pos = lap.get_pos_data()
            pos_interp = np.interp(df["Distance"], np.linspace(0, df["Distance"].max(), len(pos)), pos["X"])
            df["X"] = pos_interp
            pos_interp_y = np.interp(df["Distance"], np.linspace(0, df["Distance"].max(), len(pos)), pos["Y"])
            df["Y"] = pos_interp_y
        except Exception:
            df["X"] = np.nan
            df["Y"] = np.nan

        df["Source"] = "FastF1"
        df["Driver"] = drv_code
        return df

    except Exception as e:
        print(f"  FastF1 failed: {type(e).__name__}: {e}")  # was silent before
    return None


# ─────────────────────────────────────────────
#  Committed telemetry extracts
#
#  The FastF1 cache is ~2 GB and cannot go in git, so the deployed site has
#  no real telemetry and falls back to the synthetic stub below. These
#  extracts are the fix: one representative lap per session, resampled onto
#  a uniform distance grid, small enough to commit.
#
#  Regenerate with:  python run.py extract-telemetry
# ─────────────────────────────────────────────

EXTRACT_DIR        = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "store", "telemetry")
EXTRACT_RESOLUTION_M = 5.0


def _extract_path(circuit_name: str, session_type: str, year: int = 2026) -> str:
    return os.path.join(EXTRACT_DIR,
                        f"{year}_{circuit_name.replace(' ', '_')}_{session_type}.json")


def save_telemetry_extract(df, circuit_name: str, session_type: str,
                           year: int = 2026, resolution_m: float = EXTRACT_RESOLUTION_M):
    """
    Resample one lap onto a uniform distance grid and write it as JSON.

    Distance and DeltaTime are not stored — on a uniform grid both are
    derivable (d = i*res, dt = res / (speed/3.6)), which keeps the file to
    three arrays. Brake is thresholded back to 0/1 after interpolation
    because interpolating a boolean produces meaningless fractions.
    """
    os.makedirs(EXTRACT_DIR, exist_ok=True)

    d = df["Distance"].values.astype(float)
    d = d - d[0]
    lap_length = float(d[-1])
    n = int(lap_length // resolution_m) + 1
    grid = np.arange(n) * resolution_m

    speed    = np.interp(grid, d, df["Speed"].values.astype(float))
    throttle = np.interp(grid, d, df["Throttle"].values.astype(float))
    brake    = (np.interp(grid, d, df["Brake"].values.astype(float)) > 0.5).astype(int)

    payload = {
        "circuit":      circuit_name,
        "session_type": session_type,
        "year":         year,
        "driver":       str(df["Driver"].iloc[0]) if "Driver" in df else "",
        "lap_length_m": round(lap_length, 1),
        "resolution_m": resolution_m,
        "n_points":     n,
        "speed":        [round(float(v), 1) for v in speed],
        "throttle":     [round(float(v), 1) for v in throttle],
        "brake":        [int(v) for v in brake],
    }

    path = _extract_path(circuit_name, session_type, year)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    return path, os.path.getsize(path)


def load_telemetry_extract(circuit_name: str, session_type: str, year: int = 2026):
    """Rebuild a telemetry DataFrame from a committed extract, or None."""
    path = _extract_path(circuit_name, session_type, year)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        res    = float(p["resolution_m"])
        speed  = np.array(p["speed"], dtype=float)
        dist   = np.arange(len(speed)) * res
        # dt = distance / speed, with a floor so a stationary sample can't
        # produce an infinite segment time.
        dt     = res / np.maximum(speed / 3.6, 1.0)
        df = pd.DataFrame({
            "Distance":  dist,
            "Speed":     speed,
            "Throttle":  np.array(p["throttle"], dtype=float),
            "Brake":     np.array(p["brake"], dtype=float),
            "Gear":      np.nan,
            "RPM":       np.nan,
            "DeltaTime": dt,
            "X":         np.nan,
            "Y":         np.nan,
        })
        df["Source"]  = "Extract"
        df["Driver"]  = p.get("driver", "")
        df["LapTime"] = float(dt.sum())
        return df
    except Exception as e:
        print(f"  Extract unreadable ({path}): {e}")
        return None


def list_telemetry_extracts(year: int = 2026) -> dict:
    """{circuit: [session_type, ...]} for everything committed."""
    out = {}
    if not os.path.isdir(EXTRACT_DIR):
        return out
    for fn in sorted(os.listdir(EXTRACT_DIR)):
        if not fn.startswith(f"{year}_") or not fn.endswith(".json"):
            continue
        stem = fn[len(f"{year}_"):-len(".json")]
        circuit, _, session = stem.rpartition("_")
        if circuit:
            out.setdefault(circuit.replace("_", " "), []).append(session)
    return out


# ─────────────────────────────────────────────
#  Synthetic telemetry generator
#  Physics-accurate enough to develop and test
#  the energy model against.
# ─────────────────────────────────────────────

def generate_synthetic_telemetry(circuit_name: str) -> pd.DataFrame:
    """
    Fallback lap for circuits with no committed extract and no local cache.

    This is a MODEL, not a measurement, and every caller must label it as
    such. It exists because the previous version emitted a constant-speed
    lap at Throttle=70 / Brake=0, which segment_lap classified as a single
    "corner" spanning the whole circuit — no braking zones, therefore no
    harvest opportunities, therefore a flat battery drain. That made the ERS
    Explorer meaningless wherever it was used.

    The shape here is built from the per-circuit values already in config
    (lap length, top speed, heavy_braking_zones, key_straights,
    full_throttle_pct), so the optimizer sees a plausible alternation of
    straight -> braking -> corner -> straight and can actually solve
    something. The numbers are still invented.
    """
    cfg        = CIRCUITS.get(circuit_name, {})
    lap_length = cfg.get("lap_length_km", 5.0) * 1000
    top_speed  = float(cfg.get("top_speed_kph", 300))
    n_brake    = max(2, int(cfg.get("heavy_braking_zones", 4)))
    full_thr   = float(cfg.get("full_throttle_pct", 0.55))

    res      = 5.0
    n_points = max(50, int(lap_length / res))
    dist     = np.linspace(0, lap_length, n_points)

    speed    = np.full(n_points, top_speed * 0.95)
    throttle = np.full(n_points, 100.0)
    brake    = np.zeros(n_points)

    # Corner apex speed scales with how much of the lap is full throttle:
    # a power circuit gets faster corners than a technical one.
    apex_speed  = top_speed * (0.30 + 0.25 * full_thr)
    # Split the non-full-throttle portion between braking and cornering.
    event_frac  = max(0.10, 1.0 - full_thr)
    brake_len   = (event_frac * 0.40 / n_brake) * n_points
    corner_len  = (event_frac * 0.60 / n_brake) * n_points

    centres = np.linspace(0, n_points, n_brake, endpoint=False) + n_points / (2 * n_brake)

    for c in centres:
        b0, b1 = int(c - brake_len), int(c)
        c0, c1 = int(c), int(c + corner_len)
        b0, b1 = max(0, b0), min(n_points, b1)
        c0, c1 = max(0, c0), min(n_points, c1)

        if b1 > b0:                                  # braking: decelerate hard
            speed[b0:b1]    = np.linspace(top_speed * 0.95, apex_speed, b1 - b0)
            throttle[b0:b1] = 0.0
            brake[b0:b1]    = 1.0
        if c1 > c0:                                  # corner: apex then pick up
            speed[c0:c1]    = np.linspace(apex_speed, top_speed * 0.70, c1 - c0)
            throttle[c0:c1] = np.linspace(25.0, 90.0, c1 - c0)
            brake[c0:c1]    = 0.0

    dt       = res / np.maximum(speed / 3.6, 1.0)
    lap_time = float(dt.sum())

    df = pd.DataFrame({
        "Distance":  dist,
        "Speed":     speed,
        "Throttle":  throttle,
        "Brake":     brake,
        "Gear":      np.clip((speed / top_speed * 8).astype(int), 1, 8),
        "RPM":       11000 * (speed / top_speed),
        "DeltaTime": dt,
        "X":         np.nan,
        "Y":         np.nan,
        "LapTime":   lap_time,
    })
    df["Source"] = "Synthetic"
    df["Driver"] = "SIM"

    print(f"  Synthetic model for {circuit_name}: {n_points} points, "
          f"{n_brake} braking zones, ~{lap_time:.1f}s — NOT measured data")
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
