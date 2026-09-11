"""analysis/predictor.py

Weighted-history pace predictor for LatentLap.

The model intentionally remains simple and inspectable. This revision fixes
round-aware team resolution, canonical upgrade weighting, subset-weighted means,
and misleading session-count/methodology metadata without changing the validated
circuit/recency/epoch constants or sprint cross-session weight.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from data.race_store import load_all_fingerprints
from data.upgrade_history import SIGNIFICANCE_WEIGHT, planned_events_at_round, prediction_events
from config import (
    CIRCUITS,
    CIRCUIT_TYPES,
    DRIVER_SUBSTITUTIONS,
    PU_ADUO_UPGRADES,
    lineup_for_round,
)

# Harvest-ratio adjustment scale: seconds of lap time per unit deviation from 1.0.
# Kept unchanged: existing data does not yet justify recalibration.
HRV_SCALE = 1.0


@dataclass
class DriverPrediction:
    driver_code: str
    team: str
    pu_name: str
    predicted_delta_s: float
    delta_range_low: float
    delta_range_high: float
    predicted_straight_gap_kph: float
    predicted_harvest_ratio: float
    confidence: float
    n_races_used: int
    regulation_notes: list[str] = field(default_factory=list)


@dataclass
class RacePrediction:
    circuit_name: str
    circuit_type: str
    race_round: int
    year: int
    source: str = "qualifying"
    predictions: list[DriverPrediction] = field(default_factory=list)
    overall_confidence: float = 0.0
    n_historical_races: int = 0  # retained schema name; value is source sessions used
    methodology_notes: list[str] = field(default_factory=list)

    def fastest_predicted(self) -> DriverPrediction | None:
        if not self.predictions:
            return None
        return min(self.predictions, key=lambda p: p.predicted_delta_s)

    def ranked(self) -> list[DriverPrediction]:
        return sorted(self.predictions, key=lambda p: p.predicted_delta_s)


# ─────────────────────────────────────────────────────────
#  Similarity + recency weights
# ─────────────────────────────────────────────────────────
def circuit_similarity(source_type: str, target_type: str) -> float:
    if source_type == target_type:
        return 1.0
    similarity_map = {
        ("power", "balanced"): 0.65,
        ("balanced", "power"): 0.65,
        ("power", "high_speed"): 0.50,
        ("high_speed", "power"): 0.50,
        ("balanced", "high_speed"): 0.60,
        ("high_speed", "balanced"): 0.60,
        ("technical", "balanced"): 0.45,
        ("balanced", "technical"): 0.45,
        ("technical", "high_speed"): 0.35,
        ("high_speed", "technical"): 0.35,
        ("technical", "power"): 0.25,
        ("power", "technical"): 0.25,
    }
    return similarity_map.get((source_type, target_type), 0.40)


def recency_weight(race_round: int, current_round: int) -> float:
    age = current_round - race_round
    if age <= 0:
        return 1.0
    if age == 1:
        return 0.85
    if age == 2:
        return 0.70
    if age <= 4:
        return 0.55
    return 0.30


def epoch_weight(fp_epoch: str, target_round: int) -> float:
    from config import regulation_epoch_for_round

    target_epoch = regulation_epoch_for_round(target_round)
    if fp_epoch == target_epoch:
        return 1.0

    epoch_order = {"A_pre_miami": 0, "B_miami_canada": 1, "C_post_monaco": 2}
    fp_idx = epoch_order.get(fp_epoch, 0)
    target_idx = epoch_order.get(target_epoch, 2)
    gap = target_idx - fp_idx
    if gap <= 0:
        return 1.0
    if gap == 1:
        return 0.75
    return 0.50


# ─────────────────────────────────────────────────────────
#  Round-aware identity / upgrades
# ─────────────────────────────────────────────────────────
def _target_driver_info(driver: str, target_round: int) -> dict:
    return lineup_for_round(target_round).get(driver, {})


def _active_target_drivers(target_round: int) -> list[str]:
    """Return the intended round lineup, excluding explicitly unavailable drivers."""
    lineup = lineup_for_round(target_round)
    unavailable = set(DRIVER_SUBSTITUTIONS.get(target_round, {}).get("unavailable", {}))
    return [code for code in lineup if code not in unavailable]


def team_upgrade_weight(
    driver: str,
    fp_round: int,
    target_round: int,
    *,
    target_team: str | None = None,
) -> float:
    """Weight old fingerprints for confirmed persistent development steps only.

    The target team is resolved for the target round rather than from static CARS.
    Driver-scoped rollouts (e.g. Alpine R12/R13) only affect the relevant driver.
    """
    team = target_team or _target_driver_info(driver, target_round).get("team", "Unknown")
    weight = 1.0
    for upg in prediction_events(team, driver=driver):
        if fp_round < upg["round"] <= target_round:
            weight *= SIGNIFICANCE_WEIGHT.get(upg["significance"], 1.0)
    return weight


def get_upcoming_upgrade_notes(driver: str, target_round: int) -> list[str]:
    """Return only explicitly planned canonical upgrades at the target round."""
    info = _target_driver_info(driver, target_round)
    team = info.get("team", "Unknown")
    notes = []
    for upg in planned_events_at_round(target_round, team=team):
        text = " ".join(x for x in (upg.get("headline", ""), upg.get("detail", "")) if x)
        notes.append(f"⚠ INCOMING R{target_round}: {text}")
    return notes


def get_regulation_notes(pu_name: str, target_round: int) -> list[str]:
    notes: list[str] = []

    upg = PU_ADUO_UPGRADES.get(pu_name)
    if upg:
        first = upg.get("round")
        second = upg.get("second_round")
        if first is None:
            notes.append(f"ADUO allocated, not deployed: {upg['note']}")
        elif target_round < first:
            notes.append(f"Pre-ADUO: upgrade expected ~R{first}. {upg['note']}")
        elif target_round == first:
            notes.append(
                f"ADUO DEPLOYING THIS ROUND: {upg['note']} Historical fingerprints "
                "predate it, so this prediction may understate any gain."
            )
        else:
            notes.append(f"Post-ADUO: {upg['note']}")

        if second:
            second_note = upg.get("second_note", "Second ADUO upgrade.")
            if target_round < second:
                notes.append(f"Second ADUO upgrade expected ~R{second}.")
            elif target_round == second:
                notes.append(
                    f"SECOND ADUO DEPLOYING THIS ROUND: {second_note} Historical "
                    "fingerprints predate this second step."
                )
            else:
                notes.append(f"Post-second-ADUO: {second_note}")

    if pu_name == "RedBullFord":
        notes.append("ADUO benchmark: best ICE on grid; chassis performance is a separate signal")

    if pu_name == "Mercedes" and target_round >= 6:
        notes.append(
            "Compression ratio hot-test rule active from Monaco (R6) — loophole closed; "
            "pace advantage narrowed"
        )
    elif pu_name == "Mercedes" and target_round < 6:
        notes.append(
            "Pre-Monaco: fingerprints include compression-ratio advantage — pace may be "
            "0.2–0.3s/lap overstated vs R6+ baseline"
        )

    if pu_name == "Honda" and target_round <= 6:
        notes.append(
            "CAUTION: Honda battery vibration and energy-recovery issues — retirement risk "
            "elevated; confidence penalised"
        )
    return notes


# ─────────────────────────────────────────────────────────
#  Core prediction engine
# ─────────────────────────────────────────────────────────
def _predict_for_sessions(
    target_circuit: str,
    sessions: list[str],
    year: int = 2026,
    drivers: list[str] | None = None,
    source_label: str = "qualifying",
    session_weights: dict[str, float] | None = None,
) -> RacePrediction | None:
    if target_circuit not in CIRCUITS:
        raise ValueError(f"Unknown circuit: {target_circuit}")

    circuit_cfg = CIRCUITS[target_circuit]
    target_type = circuit_cfg["circuit_type"]
    target_round = circuit_cfg["round"]
    target_lineup = lineup_for_round(target_round)

    historical = load_all_fingerprints(year, sessions=sessions)
    if not historical:
        return None

    historical_codes = {
        fp.driver_code for rf in historical for fp in rf.fingerprints
    }
    if drivers is None:
        # Predict the target-round lineup, not every driver who happened to have
        # historical fingerprints. Stand-ins without history are naturally skipped.
        drivers = [d for d in _active_target_drivers(target_round) if d in historical_codes]

    prediction = RacePrediction(
        circuit_name=target_circuit,
        circuit_type=target_type,
        race_round=target_round,
        year=year,
        source=source_label,
    )

    uses_qualifying_harvest = any(s in ("Q", "SQ") for s in sessions)
    prediction.methodology_notes = [
        f"Sessions requested: {', '.join(sessions)}",
        f"Target circuit type: {target_type}",
        "Primary signal: lap_time_gap_pct",
        (
            "Secondary signal: qualifying-derived braking_harvest_ratio (hrv adjustment applied)"
            if uses_qualifying_harvest
            else "Harvest adjustment: not used for race/sprint-race fingerprints"
        ),
        "Weighting: circuit similarity × recency × regulation epoch × persistent upgrades × session type × fingerprint confidence",
        "Earlier regulation regimes are down-weighted",
    ]
    if session_weights:
        prediction.methodology_notes.append(
            "Session-type weighting: "
            + ", ".join(f"{k}x{v:g}" for k, v in session_weights.items())
        )

    driver_predictions: list[DriverPrediction] = []
    used_session_keys: set[tuple[int, str]] = set()

    for driver in drivers:
        all_driver_fps = [
            fp for rf in historical for fp in rf.fingerprints if fp.driver_code == driver
        ]
        if not all_driver_fps:
            continue

        target_info = target_lineup.get(driver, {})
        target_team = target_info.get("team")
        target_pu = target_info.get("pu") or target_info.get("pu_name")
        if not target_team:
            # Preserve compatibility for explicitly requested historical drivers.
            latest_fp = max(all_driver_fps, key=lambda f: f.race_round)
            target_team = latest_fp.team
            target_pu = latest_fp.pu_name

        # A transfer/substitution should use history from the target car once such
        # history exists. If none exists yet, fall back to the driver's own history
        # but flag that the car changed; do not pretend old-team upgrades apply.
        same_team_fps = [fp for fp in all_driver_fps if fp.team == target_team]
        using_cross_team_fallback = not same_team_fps
        driver_fps = same_team_fps or all_driver_fps

        weighted_gaps: list[tuple[float, float]] = []
        weighted_str: list[tuple[float, float]] = []
        weighted_hrv: list[tuple[float, float]] = []
        accepted_keys: set[tuple[int, str]] = set()

        for fp in driver_fps:
            sim = circuit_similarity(fp.circuit_type, target_type)
            recency = recency_weight(fp.race_round, target_round)
            ep_w = epoch_weight(fp.regulation_epoch, target_round)
            upg_w = (
                1.0
                if using_cross_team_fallback or fp.team != target_team
                else team_upgrade_weight(
                    driver, fp.race_round, target_round, target_team=target_team
                )
            )
            sess_w = (session_weights or {}).get(fp.session_type, 1.0)
            weight = sim * recency * ep_w * upg_w * sess_w * fp.confidence
            if weight < 0.05:
                continue

            weighted_gaps.append((fp.lap_time_gap_pct, weight))
            weighted_str.append((fp.straight_speed_delta_kph, weight))
            if fp.session_type in ("Q", "SQ"):
                weighted_hrv.append((fp.braking_harvest_ratio, weight))
            accepted_keys.add((fp.race_round, fp.session_type))

        if not weighted_gaps:
            continue

        def wmean(pairs: list[tuple[float, float]]) -> float:
            denom = sum(w for _, w in pairs)
            return sum(v * w for v, w in pairs) / denom

        def wstd(pairs: list[tuple[float, float]]) -> float:
            denom = sum(w for _, w in pairs)
            m = wmean(pairs)
            return float(np.sqrt(sum(w * (v - m) ** 2 for v, w in pairs) / denom))

        avg_gap_pct = wmean(weighted_gaps)
        gap_std = wstd(weighted_gaps)
        str_delta = wmean(weighted_str)
        avg_hrv = wmean(weighted_hrv) if weighted_hrv else 1.0

        ct = CIRCUIT_TYPES[target_type]
        hrv_adj_s = (
            (1.0 - avg_hrv) * ct["braking_weight"] * HRV_SCALE
            if weighted_hrv
            else 0.0
        )

        ref_lap_s = (circuit_cfg["lap_length_km"] / 250.0) * 3600.0
        predicted_delta = (avg_gap_pct / 100.0) * ref_lap_s + hrv_adj_s
        uncertainty = (gap_std / 100.0) * ref_lap_s
        n_samples = len(weighted_gaps)
        uncertainty = max(uncertainty, 0.30 / max(1.0, n_samples ** 0.5))

        reg_notes = get_regulation_notes(target_pu or "Unknown", target_round)
        reg_notes.extend(get_upcoming_upgrade_notes(driver, target_round))
        if using_cross_team_fallback:
            reg_notes.append(
                f"LINEUP CONTEXT: no stored {target_team} fingerprint exists yet for {driver}; "
                "the forecast falls back to the driver's earlier car history and should be treated cautiously."
            )

        if target_pu == "Honda" and target_round <= 6:
            uncertainty += 1.5

        data_conf = min(0.85, 0.40 + n_samples * 0.03)
        variance_conf = 1.0 / (1.0 + gap_std * 2.0)
        conf = min(0.85, 0.5 * data_conf + 0.5 * variance_conf)

        driver_predictions.append(
            DriverPrediction(
                driver_code=driver,
                team=target_team,
                pu_name=target_pu or "Unknown",
                predicted_delta_s=predicted_delta,
                delta_range_low=predicted_delta - uncertainty,
                delta_range_high=predicted_delta + uncertainty,
                predicted_straight_gap_kph=str_delta,
                predicted_harvest_ratio=avg_hrv,
                confidence=conf,
                n_races_used=n_samples,
                regulation_notes=reg_notes,
            )
        )
        used_session_keys.update(accepted_keys)

    if not driver_predictions:
        return None

    min_delta = min(p.predicted_delta_s for p in driver_predictions)
    for p in driver_predictions:
        p.predicted_delta_s -= min_delta
        p.delta_range_low -= min_delta
        p.delta_range_high -= min_delta

    prediction.predictions = driver_predictions
    prediction.overall_confidence = float(
        np.mean([p.confidence for p in driver_predictions])
    )
    prediction.n_historical_races = len(used_session_keys)
    prediction.methodology_notes.insert(
        1, f"Used {prediction.n_historical_races} source session(s) after weighting/filtering"
    )
    return prediction


# ─────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────
def predict_qualifying(
    target_circuit: str, year: int = 2026, drivers: list[str] | None = None
) -> RacePrediction | None:
    return _predict_for_sessions(
        target_circuit, ["Q", "SQ"], year, drivers, source_label="qualifying"
    )


def predict_race_pace(
    target_circuit: str, year: int = 2026, drivers: list[str] | None = None
) -> RacePrediction | None:
    return _predict_for_sessions(
        target_circuit, ["R", "S"], year, drivers, source_label="race"
    )


# Measured cross-session relationship; intentionally unchanged.
CROSS_SESSION_WEIGHT = 0.85


def predict_sprint_qualifying(
    target_circuit: str, year: int = 2026, drivers: list[str] | None = None
) -> RacePrediction | None:
    return _predict_for_sessions(
        target_circuit,
        ["SQ", "Q"],
        year,
        drivers,
        source_label="sprint qualifying",
        session_weights={"SQ": 1.0, "Q": CROSS_SESSION_WEIGHT},
    )


def predict_sprint_race(
    target_circuit: str, year: int = 2026, drivers: list[str] | None = None
) -> RacePrediction | None:
    return _predict_for_sessions(
        target_circuit,
        ["S", "R"],
        year,
        drivers,
        source_label="sprint race",
        session_weights={"S": 1.0, "R": CROSS_SESSION_WEIGHT},
    )


def predict_race(
    target_circuit: str, year: int = 2026, drivers: list[str] | None = None
) -> RacePrediction:
    """Legacy blended prediction retained for compatibility."""
    qual_pred = predict_qualifying(target_circuit, year, drivers)
    race_pred = predict_race_pace(target_circuit, year, drivers)

    if qual_pred is None and race_pred is None:
        raise ValueError("No historical fingerprints in store.")
    if race_pred is None or not race_pred.predictions:
        return qual_pred
    if qual_pred is None or not qual_pred.predictions:
        return race_pred

    n_race_sessions = race_pred.n_historical_races
    race_weight = min(0.70, 0.40 + n_race_sessions * 0.10)
    qual_weight = 1.0 - race_weight

    qual_by_drv = {p.driver_code: p for p in qual_pred.predictions}
    race_by_drv = {p.driver_code: p for p in race_pred.predictions}
    all_drivers = set(qual_by_drv) | set(race_by_drv)
    blended: list[DriverPrediction] = []

    for drv in all_drivers:
        qp = qual_by_drv.get(drv)
        rp = race_by_drv.get(drv)
        if qp is None:
            blended.append(rp)
            continue
        if rp is None:
            blended.append(qp)
            continue

        q_w = qual_weight * qp.confidence
        r_w = race_weight * rp.confidence
        tot = q_w + r_w + 1e-9
        blended.append(
            DriverPrediction(
                driver_code=drv,
                team=qp.team,
                pu_name=qp.pu_name,
                predicted_delta_s=(qp.predicted_delta_s * q_w + rp.predicted_delta_s * r_w) / tot,
                delta_range_low=(qp.delta_range_low * q_w + rp.delta_range_low * r_w) / tot,
                delta_range_high=(qp.delta_range_high * q_w + rp.delta_range_high * r_w) / tot,
                predicted_straight_gap_kph=(qp.predicted_straight_gap_kph * q_w + rp.predicted_straight_gap_kph * r_w) / tot,
                predicted_harvest_ratio=(qp.predicted_harvest_ratio * q_w + rp.predicted_harvest_ratio * r_w) / tot,
                confidence=(qp.confidence * q_w + rp.confidence * r_w) / tot,
                n_races_used=qp.n_races_used + rp.n_races_used,
                regulation_notes=qp.regulation_notes,
            )
        )

    min_delta = min(p.predicted_delta_s for p in blended)
    for p in blended:
        p.predicted_delta_s -= min_delta
        p.delta_range_low -= min_delta
        p.delta_range_high -= min_delta

    circuit_cfg = CIRCUITS[target_circuit]
    return RacePrediction(
        circuit_name=target_circuit,
        circuit_type=circuit_cfg["circuit_type"],
        race_round=circuit_cfg["round"],
        year=year,
        source="blended",
        predictions=blended,
        overall_confidence=float(np.mean([p.confidence for p in blended])),
        n_historical_races=qual_pred.n_historical_races + race_pred.n_historical_races,
        methodology_notes=[
            f"Blended: qualifying {qual_weight:.0%} / race pace {race_weight:.0%}",
            f"Qualifying source sessions: {qual_pred.n_historical_races}",
            f"Race source sessions: {race_pred.n_historical_races}",
            "Primary signal: lap_time_gap_pct",
            "Qualifying component may use braking_harvest_ratio; race component does not",
            "Epoch and persistent-upgrade weighting applied",
        ],
    )


def print_prediction(pred: RacePrediction):
    print(f"\n{'═' * 72}")
    print(
        f"  Prediction: {pred.circuit_name} [{pred.circuit_type}]  "
        f"Rd {pred.race_round} — {pred.year}  [{pred.source.upper()}]"
    )
    print(
        f"  Based on {pred.n_historical_races} session(s)  |  "
        f"Overall confidence: {pred.overall_confidence:.0%}"
    )
    print(f"{'─' * 72}")
    print(
        f"  {'Pos':<4} {'Driver':<6} {'Team':<18} {'PU':<14} "
        f"{'Gap':>6}  {'Range':>14}  {'HrvR':>5}  {'Conf':>5}  {'n':>3}"
    )
    source_key = str(pred.source).strip().lower()
    is_race_type = source_key in {"race", "sprint race"}

    for pos, p in enumerate(pred.ranked(), 1):
        if p.predicted_delta_s > 0:
            gap = f"+{p.predicted_delta_s:.3f}s"
        else:
            # "POLE" is meaningful only for qualifying-type pace predictions.
            # A race prediction ranks expected pace, not a starting-grid result.
            gap = "0.000s" if is_race_type else "POLE"

        range_ = f"[{p.delta_range_low:+.2f} / {p.delta_range_high:+.2f}]"
        # Race/sprint-race predictions deliberately do not use the qualifying
        # harvest adjustment. The stored neutral 1.000 is an internal modelling
        # placeholder, so do not present it as a measured/predicted race signal.
        hrv_display = "—" if is_race_type else f"{p.predicted_harvest_ratio:.3f}"
        print(
            f"  P{pos:<3} {p.driver_code:<6} {p.team:<18} {p.pu_name:<14} "
            f"{gap:>6}  {range_:>14}  {hrv_display:>5}  "
            f"{p.confidence:.0%}  {p.n_races_used:>3}"
        )
        for note in p.regulation_notes:
            print(f"         ↳ {note}")
    print("\n  Methodology:")
    for note in pred.methodology_notes:
        print(f"    • {note}")
    print(f"{'═' * 72}\n")


if __name__ == "__main__":
    from data.race_store import print_store_summary

    print_store_summary()
    try:
        prediction = predict_race("Miami")
        print_prediction(prediction)
    except ValueError as exc:
        print(f"\n  Cannot predict yet: {exc}")
