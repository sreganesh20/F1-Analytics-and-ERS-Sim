"""
analysis/compare.py
Loads actual race results from FastF1 and compares to stored prediction.
Also saves actual results JSON for the prediction scatter chart.
"""

import os
import sys
import json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analysis.prediction_store import load_prediction, PRED_DIR
from config import CIRCUITS


def load_actual_results(circuit_name: str, year: int = 2026) -> list[dict] | None:
    try:
        import fastf1
        import pandas as pd

        cache_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "cache")
        )
        fastf1.Cache.enable_cache(cache_dir)

        circuit_cfg = CIRCUITS[circuit_name]
        session = fastf1.get_session(
            circuit_cfg["fastf1_year"],
            circuit_cfg["fastf1_name"],
            "R",
        )
        session.load(telemetry=False, weather=False)

        results = session.results[["Abbreviation", "Position", "Time", "Status"]].copy()
        results = results.dropna(subset=["Position"])
        results = results.sort_values("Position")

        winner_time = results.iloc[0]["Time"]
        actual = []
        for _, row in results.iterrows():
            t = row["Time"]
            if pd.isna(t):
                gap_s = None
            else:
                gap_s = (t - winner_time).total_seconds() \
                        if row["Position"] > 1 else 0.0
            actual.append({
                "driver": row["Abbreviation"],
                "pos":    int(row["Position"]),
                "gap_s":  gap_s,
                "status": row["Status"],
            })
        return actual

    except Exception as e:
        print(f"  Could not load actual results: {e}")
        return None


def _save_actual_results(circuit_name: str, year: int, actual: list[dict]):
    """Save actual results JSON for use by prediction_scatter chart."""
    os.makedirs(PRED_DIR, exist_ok=True)
    path = os.path.join(
        PRED_DIR,
        f"{year}_{circuit_name.replace(' ', '_')}_actual.json"
    )
    with open(path, "w") as f:
        json.dump(actual, f, indent=2)
    print(f"  Actual results saved → {path}")


def compare(circuit_name: str, year: int = 2026):
    circuit_name = circuit_name.title()

    pred = load_prediction(circuit_name, year)
    if pred is None:
        print(f"  No stored prediction found for {circuit_name} {year}.")
        print(f"  Run: python run.py predict {circuit_name.lower()}  before the race.")
        return

    actual = load_actual_results(circuit_name, year)
    if actual is None:
        return

    # Save actual results for scatter chart
    _save_actual_results(circuit_name, year, actual)

    pred_by_driver   = {p.driver_code: (i+1, p)
                        for i, p in enumerate(pred.ranked())}
    actual_by_driver = {r["driver"]: r for r in actual}

    all_drivers = sorted(
        set(pred_by_driver) | set(actual_by_driver),
        key=lambda d: actual_by_driver[d]["pos"]
                      if d in actual_by_driver else 99
    )

    print(f"\n{'═'*80}")
    print(f"  Post-Race Comparison: {circuit_name} {year}")
    print(f"  Prediction source: {pred.source.upper()}  |  "
          f"Confidence was: {pred.overall_confidence:.0%}")
    print(f"{'─'*80}")
    print(f"  {'Driver':<6}  {'Team':<18}  "
          f"{'Pred':>4}  {'Actual':>6}  {'ΔPos':>5}  "
          f"{'PredGap':>8}  {'ActualGap':>9}  {'ΔGap':>7}  {'In Range?':>9}")
    print(f"  {'─'*6}  {'─'*18}  "
          f"{'─'*4}  {'─'*6}  {'─'*5}  "
          f"{'─'*8}  {'─'*9}  {'─'*7}  {'─'*9}")

    pos_errors  = []
    gap_errors  = []
    in_range_n  = 0
    compared_n  = 0

    for drv in all_drivers:
        in_pred   = drv in pred_by_driver
        in_actual = drv in actual_by_driver

        pred_pos = pred_by_driver[drv][0]  if in_pred   else "—"
        pred_p   = pred_by_driver[drv][1]  if in_pred   else None
        act_row  = actual_by_driver[drv]   if in_actual else None

        act_pos    = act_row["pos"]    if in_actual else "—"
        act_gap    = act_row["gap_s"]  if in_actual else None
        act_status = act_row["status"] if in_actual else ""

        team = pred_p.team if pred_p else "—"

        if isinstance(pred_pos, int) and isinstance(act_pos, int):
            d_pos     = act_pos - pred_pos
            d_pos_str = f"{d_pos:+d}"
            pos_errors.append(abs(d_pos))
        else:
            d_pos_str = "—"

        pred_gap_str = (f"+{pred_p.predicted_delta_s:.3f}s"
                        if pred_p and pred_p.predicted_delta_s > 0
                        else ("POLE" if pred_p else "—"))
        act_gap_str  = (f"+{act_gap:.3f}s"
                        if act_gap is not None and act_gap > 0
                        else ("WINNER" if act_gap == 0.0
                              else ("DNF" if act_gap is None else "—")))

        if pred_p and act_gap is not None:
            d_gap     = act_gap - pred_p.predicted_delta_s
            d_gap_str = f"{d_gap:+.3f}s"
            gap_errors.append(abs(d_gap))

            in_range  = pred_p.delta_range_low <= act_gap <= pred_p.delta_range_high
            range_str = "✓" if in_range else "✗"
            if in_range:
                in_range_n += 1
            compared_n += 1
        else:
            d_gap_str = "—"
            range_str = ("DNF" if ("DNF" in str(act_status) or act_gap is None)
                         else "—")

        print(f"  {drv:<6}  {team:<18}  "
              f"{str(pred_pos):>4}  {str(act_pos):>6}  {d_pos_str:>5}  "
              f"{pred_gap_str:>8}  {act_gap_str:>9}  "
              f"{d_gap_str:>7}  {range_str:>9}")

    print(f"\n{'─'*80}")
    if pos_errors:
        print(f"  Mean absolute position error: {np.mean(pos_errors):.1f} places")
    if gap_errors:
        print(f"  Mean absolute gap error:      {np.mean(gap_errors):.3f}s")
    if compared_n > 0:
        print(f"  Actual gap in predicted range: {in_range_n}/{compared_n} "
              f"({in_range_n/compared_n:.0%})")
    print(f"{'═'*80}\n")
