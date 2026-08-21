"""
run.py — ERS Optimizer entry point

Usage:
  python run.py pipeline          # Process all known 2026 races (qualifying)
  python run.py pipeline china    # Process single circuit qualifying
  python run.py race china        # Load race (R) session for a circuit
  python run.py race              # Load race sessions for all known circuits
  python run.py predict miami     # Predict for an upcoming race (blended)
  python run.py store             # Show race store contents
  python run.py test              # Run quick validation test
  python run.py compare miami     # Predicted vs actual post-race
  python run.py viz all                  # All charts
  python run.py viz season_evolution     # PU performance over season
  python run.py viz harvest_bars         # ERS harvest efficiency per driver
  python run.py viz prediction_scatter   # Predicted vs actual scatter
  python run.py viz fingerprint_radar    # PU fingerprint radar chart
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


def cmd_pipeline(args):
    from pipeline.race_pipeline import run_race_pipeline, run_all_known_races
    if args:
        circuit = args[0].title()
        run_race_pipeline(circuit, force_synthetic=False, verbose=True)
    else:
        run_all_known_races(force_synthetic=False, verbose=True)


def cmd_race(args):
    from pipeline.race_pipeline import run_race_session
    if args:
        circuit = args[0].title()
        print(f"\nLoading race session for {circuit}...")
        run_race_session(circuit, verbose=True)
    else:
        known = ["Australia", "China", "Japan"]
        for circuit in known:
            try:
                run_race_session(circuit, verbose=False)
            except Exception as e:
                print(f"  ERROR {circuit}: {e}")


def cmd_predict(args):
    from analysis.predictor import (predict_qualifying, predict_race_pace,
                                    predict_sprint_qualifying, predict_sprint_race,
                                    print_prediction)
    from analysis.prediction_store import save_prediction
    from config import CIRCUITS
    circuit = args[0].title() if args else "Netherlands"
    print(f"\nGenerating predictions for {circuit}...\n")

    cfg         = CIRCUITS.get(circuit, {})
    is_sprint   = bool(cfg.get("has_sprint"))

    # Order matters on a sprint weekend: SQ (Fri) -> S (Sat) -> Q (Sat) -> R (Sun)
    jobs = []
    if is_sprint:
        print(f"  {circuit} is a SPRINT weekend — generating 4 predictions.\n")
        jobs += [("sprint_quali", predict_sprint_qualifying, "sprint qualifying"),
                 ("sprint_race",  predict_sprint_race,       "sprint race")]
    jobs += [("quali", predict_qualifying, "qualifying"),
             ("race",  predict_race_pace,  "race pace")]

    written = []
    for pred_type, fn, label in jobs:
        pred = fn(circuit)
        if pred:
            print_prediction(pred)
            save_prediction(pred, pred_type=pred_type)
            written.append(pred_type)
        else:
            print(f"  No {label} data available.\n")

    print(f"\n  Wrote {len(written)} prediction file(s): {', '.join(written) or 'none'}")
    if is_sprint and len(written) < 4:
        print("  WARNING: sprint weekend expected 4 files. Check that S/SQ "
              "sessions exist in store/ for previous sprint rounds.")


def cmd_store(args):
    from data.race_store import print_store_summary
    print_store_summary()


def cmd_compare(args):
    from analysis.compare import compare
    circuit = args[0].title() if args else None
    if not circuit:
        print("Usage: python run.py compare <circuit>")
        return
    compare(circuit)


def cmd_test(args):
    print("Running validation test...\n")
    from fetcher import generate_synthetic_telemetry
    from models.track import segment_lap
    from models.optimizer import optimise, print_strategy_summary
    from config import CIRCUITS

    circuit = "China"
    df      = generate_synthetic_telemetry(circuit)
    segs    = segment_lap(df)
    opt     = optimise(segs, CIRCUITS[circuit])
    print_strategy_summary(opt)
    print("Test passed.")


def cmd_viz(args):
    """
    Generate visualisation charts.
    Usage:
      python run.py viz all
      python run.py viz season_evolution
      python run.py viz harvest_bars
      python run.py viz prediction_scatter
      python run.py viz fingerprint_radar
    """
    from viz.season_evolution   import plot_season_evolution
    from viz.harvest_bars       import plot_harvest_bars
    from viz.prediction_scatter import plot_prediction_scatter
    from viz.fingerprint_radar  import plot_fingerprint_radar

    CHARTS = {
        "season_evolution":   plot_season_evolution,
        "harvest_bars":       plot_harvest_bars,
        "prediction_scatter": plot_prediction_scatter,
        "fingerprint_radar":  plot_fingerprint_radar,
    }

    chart = args[0].lower() if args else "all"

    if chart == "all":
        print("\nGenerating all charts...\n")
        for name, fn in CHARTS.items():
            print(f"  → {name}")
            try:
                fn(show=False, save=True)
            except Exception as e:
                print(f"    ERROR: {e}")
                import traceback
                traceback.print_exc()
        print(f"\nAll charts saved to viz/outputs/")
    elif chart in CHARTS:
        print(f"\nGenerating {chart}...")
        CHARTS[chart](show=True, save=True)
    else:
        print(f"Unknown chart: {chart}")
        print(f"Available: all, {', '.join(CHARTS.keys())}")


COMMANDS = {
    "pipeline": cmd_pipeline,
    "race":     cmd_race,
    "predict":  cmd_predict,
    "store":    cmd_store,
    "compare":  cmd_compare,
    "test":     cmd_test,
    "viz":      cmd_viz,
}

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd  = args[0].lower() if args else "test"
    rest = args[1:]

    if cmd in COMMANDS:
        COMMANDS[cmd](rest)
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(COMMANDS.keys())}")
