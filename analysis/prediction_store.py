"""
analysis/prediction_store.py
Saves and loads race predictions for post-race comparison.
Supports pred_type: "quali" | "race" | "sprint_quali" | "sprint_race"
"""

import json
import os
from analysis.predictor import RacePrediction, DriverPrediction

PRED_DIR = os.path.join(os.path.dirname(__file__), "..", "store", "predictions")


def _ensure_dir():
    os.makedirs(PRED_DIR, exist_ok=True)


def _pred_path(circuit_name: str, year: int, pred_type: str = "quali") -> str:
    """New format: 2026_Netherlands_quali_prediction.json"""
    return os.path.join(PRED_DIR,
                        f"{year}_{circuit_name.replace(' ', '_')}_{pred_type}_prediction.json")


def _pred_path_legacy(circuit_name: str, year: int) -> str:
    """Old single-file format for backward compatibility."""
    return os.path.join(PRED_DIR,
                        f"{year}_{circuit_name.replace(' ', '_')}_prediction.json")


def save_prediction(pred: RacePrediction, pred_type: str = "quali"):
    _ensure_dir()
    path = _pred_path(pred.circuit_name, pred.year, pred_type)
    data = {
        "circuit_name":       pred.circuit_name,
        "circuit_type":       pred.circuit_type,
        "race_round":         pred.race_round,
        "year":               pred.year,
        "source":             pred.source,
        "pred_type":          pred_type,
        "overall_confidence": pred.overall_confidence,
        "n_historical_races": pred.n_historical_races,
        "methodology_notes":  pred.methodology_notes,
        "predictions": [
            {
                "driver_code":                p.driver_code,
                "team":                       p.team,
                "pu_name":                    p.pu_name,
                "predicted_delta_s":          p.predicted_delta_s,
                "delta_range_low":            p.delta_range_low,
                "delta_range_high":           p.delta_range_high,
                "predicted_straight_gap_kph": p.predicted_straight_gap_kph,
                "predicted_harvest_ratio":    p.predicted_harvest_ratio,
                "confidence":                 p.confidence,
                "n_races_used":               p.n_races_used,
                "regulation_notes":           p.regulation_notes,
            }
            for p in pred.ranked()
        ],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  [{pred_type.upper()}] Prediction saved → {path}")


def load_prediction(circuit_name: str, year: int = 2026,
                    pred_type: str = "quali") -> RacePrediction | None:
    # Try new format first
    path = _pred_path(circuit_name, year, pred_type)
    if not os.path.exists(path) and pred_type == "quali":
        # Fall back to legacy single-file format
        path = _pred_path_legacy(circuit_name, year)
    if not os.path.exists(path):
        return None

    with open(path) as f:
        data = json.load(f)

    preds = [DriverPrediction(**p) for p in data["predictions"]]
    return RacePrediction(
        circuit_name       = data["circuit_name"],
        circuit_type       = data["circuit_type"],
        race_round         = data["race_round"],
        year               = data["year"],
        source             = data["source"],
        overall_confidence = data["overall_confidence"],
        n_historical_races = data["n_historical_races"],
        methodology_notes  = data["methodology_notes"],
        predictions        = preds,
    )
