r"""
diag_corner_segments.py  —  run from D:\ERS_v2

Purpose: test three hypotheses about corner_speed_delta_kph before committing
to a full 30-session re-run. Touches nothing, writes one JSON + prints a report.

    python diag_corner_segments.py

H1  DISTANCE MISALIGNMENT
    race_pipeline.py uses `get_car_data().add_distance()`, which integrates
    speed over time to synthesise a Distance axis per driver. Errors accumulate
    along the lap, so a fixed distance window compares different physical parts
    of the track for different drivers. `get_telemetry()` merges positional data
    and gives a track-accurate distance instead.
    TEST: compare total lap distance across drivers, both ways.

H2  FORMULA
    compute_speed_deltas uses  -(t_car - t_ref)/t_ref * seg.speed_mean.
    Exact form over a fixed distance d is  3.6*d/t_car - 3.6*d/t_ref.
    The current version puts t_ref in the denominator where the exact form
    needs t_car, so it exaggerates slow cars and compresses fast ones.
    TEST: compute both per corner, report the divergence.

H3  SESSION-LEVEL BIAS
    Session medians of the stored metric swing from -25.29 (R9 SQ) to +12.27
    (R2 Q). A whole field cannot be 25 kph down in corners, nor 12 kph up on
    the pole car. TEST: see whether the bias survives H1 and H2 corrections.
"""

import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fastf1
from models.track import segment_lap
from config import CIRCUITS, CARS

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
OUT   = "corner_diagnostic.json"

# One session that looks clean, one that looks broken.
# (circuit key in CIRCUITS, fastf1 session code)
TARGETS = [
    ("Canada",  "Q"),    # R5  Q  — stored median  -2.45, zero extremes
    ("Britain", "SQ"),   # R9  SQ — stored median -25.29, 11 of 22 beyond +/-25
]


def resolve(key):
    """CIRCUITS keys are capitalised ('Canada'); accept any casing."""
    if key in CIRCUITS:
        return key
    for k in CIRCUITS:
        if k.lower() == key.lower():
            return k
    return None


def seg_time(df, d0, d1):
    """Elapsed time through a distance window, matching fingerprint.py."""
    m = (df["Distance"] >= d0) & (df["Distance"] < d1)
    return float(np.sum(df.loc[m, "DeltaTime"].values)) if m.any() else 0.0


def build_df(tel):
    return pd.DataFrame({
        "Distance":  tel["Distance"].values,
        "Speed":     tel["Speed"].values,
        "Throttle":  tel["Throttle"].values,
        "Brake":     tel["Brake"].astype(float).values,
        "DeltaTime": tel["Time"].diff().dt.total_seconds().fillna(0).values,
    })


def analyse(circuit_key, session_code):
    cfg  = CIRCUITS[circuit_key]
    year = cfg.get("fastf1_year", 2026)
    rnd  = cfg["round"]

    print(f"\n{'='*78}\n  {circuit_key.upper()}  {session_code}  (R{rnd} {year})\n{'='*78}")

    ses = fastf1.get_session(year, cfg["fastf1_name"], session_code)
    ses.load(telemetry=True, laps=True, weather=False, messages=False)

    # ---- collect each driver's fastest lap, both distance methods ----
    cars = {}
    for code in CARS:
        try:
            laps = ses.laps.pick_drivers(code)
            if laps.empty:
                continue
            fl = laps.pick_fastest()
            if fl is None or pd.isna(fl["LapTime"]):
                continue
            cars[code] = {
                "lap_time": fl["LapTime"].total_seconds(),
                "add_dist": build_df(fl.get_car_data().add_distance()),
                "get_tel":  build_df(fl.get_telemetry()),
            }
        except Exception as e:
            print(f"  skip {code}: {e}")

    if not cars:
        print("  no drivers loaded")
        return None

    ref = min(cars, key=lambda c: cars[c]["lap_time"])
    print(f"  reference car: {ref}  ({cars[ref]['lap_time']:.3f}s)   drivers: {len(cars)}")

    # ---------------- H1: distance misalignment ----------------
    print(f"\n  --- H1: total lap Distance per driver (metres) ---")
    print(f"  {'drv':<5}{'add_distance()':>16}{'get_telemetry()':>18}{'diff':>10}")
    h1 = {}
    for c in sorted(cars, key=lambda c: cars[c]["lap_time"]):
        a = float(cars[c]["add_dist"]["Distance"].iloc[-1])
        g = float(cars[c]["get_tel"]["Distance"].iloc[-1])
        h1[c] = {"add_distance": a, "get_telemetry": g, "diff": a - g}
        print(f"  {c:<5}{a:>16.1f}{g:>18.1f}{a-g:>10.1f}")

    spread_a = max(v["add_distance"] for v in h1.values()) - \
               min(v["add_distance"] for v in h1.values())
    spread_g = max(v["get_telemetry"] for v in h1.values()) - \
               min(v["get_telemetry"] for v in h1.values())
    print(f"\n  spread across field:  add_distance() {spread_a:7.1f} m"
          f"   get_telemetry() {spread_g:7.1f} m")
    print("  >> If add_distance() spread is tens of metres and get_telemetry()")
    print("     is near zero, H1 is confirmed and the fix is the loader, not the maths.")

    # ---------------- H2 + H3: per-corner formulas ----------------
    results = {}
    for method in ("add_dist", "get_tel"):
        segments = segment_lap(cars[ref][method])
        corners  = [s for s in segments if s.seg_type == "corner"]
        if not corners:
            continue

        per_driver = {}
        for c in cars:
            cur, exact = [], []
            for s in corners:
                d = s.d_end - s.d_start
                t_c = seg_time(cars[c][method], s.d_start, s.d_end)
                t_r = seg_time(cars[ref][method], s.d_start, s.d_end)
                if t_r <= 0 or t_c <= 0:
                    continue
                cur.append(-(t_c - t_r) / t_r * s.speed_mean)   # current code
                exact.append(3.6 * d / t_c - 3.6 * d / t_r)     # exact
            if cur:
                per_driver[c] = {
                    "current":  float(np.mean(cur)),
                    "exact":    float(np.mean(exact)),
                    "current_med": float(np.median(cur)),
                    "exact_med":   float(np.median(exact)),
                    "n_corners": len(cur),
                }

        results[method] = {"n_corners": len(corners), "per_driver": per_driver}

        label = "add_distance()" if method == "add_dist" else "get_telemetry()"
        print(f"\n  --- H2/H3 via {label}   ({len(corners)} corner segments) ---")
        print(f"  {'drv':<5}{'current(mean)':>15}{'exact(mean)':>14}"
              f"{'current(med)':>14}{'exact(med)':>12}")
        for c in sorted(per_driver, key=lambda c: cars[c]["lap_time"]):
            v = per_driver[c]
            print(f"  {c:<5}{v['current']:>15.2f}{v['exact']:>14.2f}"
                  f"{v['current_med']:>14.2f}{v['exact_med']:>12.2f}")

        for k in ("current", "exact"):
            vals = np.array([v[k] for v in per_driver.values()])
            print(f"    field {k:<8} median={np.median(vals):>8.2f}  "
                  f"min={vals.min():>8.2f}  max={vals.max():>7.2f}  "
                  f"n>|25|={int((np.abs(vals) > 25).sum())}")

    print("\n  >> A field median near 0 means the metric is comparable across")
    print("     sessions. A field median far from 0 means it is not, and no")
    print("     choice of mean vs median at team level can repair that.")

    return {"reference": ref, "n_drivers": len(cars), "h1": h1, "h2_h3": results}


def main():
    os.makedirs(CACHE, exist_ok=True)
    fastf1.Cache.enable_cache(CACHE)

    out = {}
    for circuit_key, session_code in TARGETS:
        circuit_key = resolve(circuit_key)
        if circuit_key is None:
            print(f"!! circuit not in CIRCUITS — check the key")
            continue
        try:
            out[f"{circuit_key}_{session_code}"] = analyse(circuit_key, session_code)
        except Exception as e:
            import traceback
            print(f"\n!! {circuit_key} {session_code} failed: {e}")
            traceback.print_exc()

    with open(OUT, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n\nWrote {OUT}  — send me this file plus the console output.")


if __name__ == "__main__":
    main()
