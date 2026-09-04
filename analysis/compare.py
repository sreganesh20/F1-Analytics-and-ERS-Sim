"""
analysis/compare.py
Compares each stored prediction against the matching actual session result.

A prediction is only meaningfully comparable to the session it predicted:
qualifying against qualifying, race against race. The earlier version compared
the qualifying prediction to race finishing positions, which conflated two
different things — a one-lap pace order and a 72-lap race outcome shaped by
strategy, tyre wear and retirements.

It also compared a per-lap qualifying delta (tenths) against a cumulative race
gap (tens of seconds) and reported the difference as error, producing a
meaningless ~7000s figure. Gap comparison is valid for qualifying, where both
sides are per-lap seconds, and is omitted for races, where they are not the
same quantity.

Also saves actual results JSON for the prediction scatter chart.
"""

import os
import sys
import json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analysis.prediction_store import load_prediction, PRED_DIR
from config import CIRCUITS

# pred_type -> (FastF1 session code, human label, is this a race-type session)
SESSION_MAP = {
    "sprint_quali": ("SQ", "Sprint Qualifying", False),
    "sprint_race":  ("S",  "Sprint",            True),
    "quali":        ("Q",  "Qualifying",        False),
    "race":         ("R",  "Race",              True),
}


def load_actual_results(circuit_name: str, year: int = 2026,
                        session_code: str = "R") -> list[dict] | None:
    """
    Actual classification for one session.

    For races, gap_s is the cumulative gap to the winner. For qualifying, it is
    the per-lap gap to pole — the same quantity the predictor outputs, so the
    two are directly comparable there.
    """
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
            session_code,
        )
        session.load(telemetry=False, weather=False)

        is_race = session_code in ("R", "S")
        cols = ["Abbreviation", "Position", "Status"]
        cols += ["Time", "Laps"] if is_race else ["Q1", "Q2", "Q3"]
        available = [c for c in cols if c in session.results.columns]
        results = session.results[available].copy()
        results = results.dropna(subset=["Position"]).sort_values("Position")

        actual = []
        if is_race:
            # FastF1 quirk: results["Time"] is the winner's TOTAL race time for
            # P1, but for every other classified car it is ALREADY the gap to
            # the winner. Subtracting winner_time from those gave the winner's
            # race duration negated (e.g. -7473s).
            #
            # Lapped cars are the second trap: FastF1 may still report a Time
            # value for them, but a car a lap down is not "+36s" — it finished
            # +1 lap. Reporting seconds there is simply false. Compare each
            # car's lap count to the winner's to catch it.
            winner_laps = None
            if "Laps" in results.columns and len(results):
                wl = results.iloc[0].get("Laps")
                winner_laps = int(wl) if not pd.isna(wl) else None

            for _, row in results.iterrows():
                t   = row.get("Time")
                pos = int(row["Position"])
                laps_done = row.get("Laps")
                laps_down = None
                if winner_laps is not None and not pd.isna(laps_done):
                    laps_down = winner_laps - int(laps_done)

                if pos == 1:
                    gap_s = 0.0
                elif laps_down and laps_down > 0:
                    gap_s = None            # lapped — seconds would be a lie
                elif pd.isna(t):
                    gap_s = None
                else:
                    gap_s = t.total_seconds()

                actual.append({
                    "driver":    row["Abbreviation"],
                    "pos":       pos,
                    "gap_s":     gap_s,
                    "laps_down": laps_down if laps_down and laps_down > 0 else 0,
                    "status":    row.get("Status", ""),
                })
        else:
            # Qualifying: best available session time per driver, gap to pole.
            #
            # Sprint qualifying in particular can come back without usable
            # Q1/Q2/Q3 columns — FastF1 warns "Cannot calculate qualifying
            # results: missing information about deleted laps" — so fall back
            # to each driver's fastest lap from the timing data.
            best = {}
            has_q_cols = any(q in results.columns for q in ("Q1", "Q2", "Q3"))
            if has_q_cols:
                for _, row in results.iterrows():
                    times = [row.get(q) for q in ("Q3", "Q2", "Q1")
                             if q in results.columns and not pd.isna(row.get(q))]
                    best[row["Abbreviation"]] = (
                        min(t.total_seconds() for t in times) if times else None)

            if not any(v is not None for v in best.values()):
                for _, row in results.iterrows():
                    code = row["Abbreviation"]
                    try:
                        fl = session.laps.pick_drivers(code).pick_fastest()
                        best[code] = (fl["LapTime"].total_seconds()
                                      if fl is not None and not pd.isna(fl["LapTime"])
                                      else None)
                    except Exception:
                        best[code] = None

            pole = min((v for v in best.values() if v is not None), default=None)
            for _, row in results.iterrows():
                code = row["Abbreviation"]
                bt   = best.get(code)
                actual.append({
                    "driver": code,
                    "pos":    int(row["Position"]),
                    "gap_s":  (bt - pole) if (bt is not None and pole) else None,
                    "status": row.get("Status", ""),
                })

        return actual

    except Exception as e:
        print(f"  Could not load actual {session_code} results: {e}")
        return None


def _save_actual_results(circuit_name: str, year: int, actual: list[dict],
                         pred_type: str = "race"):
    """Save actual results JSON. The race file keeps its original name so the
    existing scatter chart keeps working; other sessions get a suffix."""
    suffix = "" if pred_type == "race" else f"_{pred_type}"
    path = os.path.join(
        PRED_DIR,
        f"{year}_{circuit_name.replace(' ', '_')}{suffix}_actual.json"
    )
    with open(path, "w") as f:
        json.dump(actual, f, indent=2)
    return path


def compare_session(circuit_name: str, pred_type: str, year: int = 2026):
    """Compare one prediction against its own session. Returns True if it ran."""
    session_code, label, is_race = SESSION_MAP[pred_type]

    pred = load_prediction(circuit_name, year, pred_type=pred_type)
    if pred is None:
        return False

    actual = load_actual_results(circuit_name, year, session_code)
    if actual is None:
        return False

    path = _save_actual_results(circuit_name, year, actual, pred_type)

    pred_by_driver   = {p.driver_code: (i + 1, p)
                        for i, p in enumerate(pred.ranked())}
    actual_by_driver = {r["driver"]: r for r in actual}

    all_drivers = sorted(
        set(pred_by_driver) | set(actual_by_driver),
        key=lambda d: actual_by_driver[d]["pos"] if d in actual_by_driver else 99
    )

    print(f"\n{'═'*84}")
    print(f"  {label} — {circuit_name} {year}")
    print(f"  Predicted from: {pred.source}  |  confidence {pred.overall_confidence:.0%}")
    print(f"{'─'*84}")
    # Column names carry the units, because for a race the two gap columns are
    # different quantities: predicted per-lap pace vs actual cumulative gap.
    pred_col = "Pred/lap" if is_race else "PredGap"
    act_col  = "ActualTotal" if is_race else "ActualGap"
    hdr = (f"  {'Driver':<6}  {'Team':<16}  {'Pred':>4}  {'Actual':>6}  {'ΔPos':>5}  "
           f"{pred_col:>9}  {act_col:>11}")
    if not is_race:
        hdr += f"  {'ΔGap':>8}  {'In Range?':>9}"
    print(hdr)
    print(f"  {'─'*6}  {'─'*16}  {'─'*4}  {'─'*6}  {'─'*5}  {'─'*9}  {'─'*11}"
          + (f"  {'─'*8}  {'─'*9}" if not is_race else ""))

    pos_all, pos_fin, gap_err, dnfs = [], [], [], []
    in_range_n = compared_n = 0

    for drv in all_drivers:
        pp = pred_by_driver.get(drv)
        ar = actual_by_driver.get(drv)

        pred_pos = pp[0] if pp else "—"
        pred_p   = pp[1] if pp else None
        act_pos   = ar["pos"]        if ar else "—"
        act_gap   = ar["gap_s"]      if ar else None
        laps_down = ar.get("laps_down", 0) if ar else 0
        status    = ar["status"]     if ar else ""

        is_dnf = bool(ar) and ("DNF" in str(status)
                               or (act_gap is None and status not in ("", "Finished")))
        if is_dnf:
            dnfs.append(drv)

        if isinstance(pred_pos, int) and isinstance(act_pos, int):
            d_pos = act_pos - pred_pos
            d_pos_str = f"{d_pos:+d}"
            pos_all.append(abs(d_pos))
            if not is_dnf:
                pos_fin.append(abs(d_pos))
        else:
            d_pos_str = "—"

        # "POLE" only makes sense for a qualifying session. For a race the
        # top predicted car is the predicted WINNER.
        leader_label = "WINNER" if is_race else "POLE"
        if pred_p and pred_p.predicted_delta_s > 0:
            pred_gap_str = f"+{pred_p.predicted_delta_s:.3f}s"
        elif pred_p:
            pred_gap_str = leader_label
        else:
            pred_gap_str = "—"

        if is_dnf:
            act_gap_str = "DNF"
        elif laps_down:
            # A lapped car is not "+36s" behind — it finished a lap down, and
            # printing seconds there is simply false.
            act_gap_str = f"+{laps_down} lap" + ("s" if laps_down > 1 else "")
        elif act_gap == 0.0:
            act_gap_str = leader_label
        elif act_gap is not None:
            act_gap_str = f"+{act_gap:.1f}s" if is_race else f"+{act_gap:.3f}s"
        else:
            act_gap_str = "—"

        line = (f"  {drv:<6}  {(pred_p.team if pred_p else '—'):<16}  "
                f"{str(pred_pos):>4}  {str(act_pos):>6}  {d_pos_str:>5}  "
                f"{pred_gap_str:>9}  {act_gap_str:>11}")

        # Gap error only for qualifying: both sides are per-lap seconds there.
        if not is_race:
            if pred_p and act_gap is not None and not is_dnf:
                d_gap = act_gap - pred_p.predicted_delta_s
                gap_err.append(abs(d_gap))
                in_range = pred_p.delta_range_low <= act_gap <= pred_p.delta_range_high
                in_range_n += int(in_range)
                compared_n += 1
                line += f"  {d_gap:>+7.3f}s  {('✓' if in_range else '✗'):>9}"
            else:
                line += f"  {'—':>8}  {('DNF' if is_dnf else '—'):>9}"

        print(line)

    print(f"{'─'*84}")
    if pos_all:
        print(f"  Mean absolute position error: {np.mean(pos_all):.1f} places "
              f"({len(pos_all)} classified)")
    if pos_fin and len(pos_fin) != len(pos_all):
        print(f"  Excluding retirements:        {np.mean(pos_fin):.1f} places "
              f"({len(pos_fin)} finishers)")
    if dnfs:
        print(f"  Retirements ({len(dnfs)}): {', '.join(dnfs)}")
    if not is_race:
        if gap_err:
            print(f"  Mean absolute gap error:      {np.mean(gap_err):.3f}s")
        if compared_n:
            print(f"  Actual gap inside predicted range: {in_range_n}/{compared_n} "
                  f"({in_range_n/compared_n:.0%})")
    else:
        print("  Gap error not reported: the prediction is a per-lap pace delta, "
              "the actual is a cumulative race gap.")
    print(f"{'═'*84}")
    return True


def compare(circuit_name: str, year: int = 2026):
    """Compare every stored prediction for a weekend against its own session."""
    circuit_name = circuit_name.title()
    ran = []
    for pred_type in ("sprint_quali", "sprint_race", "quali", "race"):
        if compare_session(circuit_name, pred_type, year):
            ran.append(SESSION_MAP[pred_type][1])

    if not ran:
        print(f"\n  No stored predictions found for {circuit_name} {year}.")
        print(f"  Run: python run.py predict {circuit_name.lower()}  before the weekend.\n")
    else:
        print(f"\n  Compared {len(ran)} session(s): {', '.join(ran)}\n")
