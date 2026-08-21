"""
analysis/predictor.py
"""

import numpy as np
from dataclasses import dataclass, field
from models.fingerprint import CarFingerprint
from data.race_store import load_all_fingerprints
from config import CIRCUITS, CIRCUIT_TYPES, PU_GROUPS, PU_ADUO_UPGRADES

# Harvest ratio adjustment scale: seconds of lap time per unit deviation from 1.0
# Kept conservative — lap_time_gap_pct remains the dominant signal.
HRV_SCALE = 1.0

# ─────────────────────────────────────────────────────────
#  Output structures
# ─────────────────────────────────────────────────────────

@dataclass
class DriverPrediction:
    driver_code:       str
    team:              str
    pu_name:           str

    predicted_delta_s:  float
    delta_range_low:    float
    delta_range_high:   float

    predicted_straight_gap_kph: float
    predicted_harvest_ratio:    float

    confidence:         float
    n_races_used:       int

    regulation_notes:   list[str] = field(default_factory=list)


@dataclass
class RacePrediction:
    circuit_name:      str
    circuit_type:      str
    race_round:        int
    year:              int
    source:            str = "qualifying"

    predictions:       list[DriverPrediction] = field(default_factory=list)

    overall_confidence:   float = 0.0
    n_historical_races:   int   = 0
    methodology_notes:    list[str] = field(default_factory=list)

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
        ("power",      "balanced"):    0.65,
        ("balanced",   "power"):       0.65,
        ("power",      "high_speed"):  0.50,
        ("high_speed", "power"):       0.50,
        ("balanced",   "high_speed"):  0.60,
        ("high_speed", "balanced"):    0.60,
        ("technical",  "balanced"):    0.45,
        ("balanced",   "technical"):   0.45,
        ("technical",  "high_speed"):  0.35,
        ("high_speed", "technical"):   0.35,
        ("technical",  "power"):       0.25,
        ("power",      "technical"):   0.25,
    }
    return similarity_map.get((source_type, target_type), 0.40)


def recency_weight(race_round: int, current_round: int) -> float:
    age = current_round - race_round
    if age <= 0:  return 1.0
    if age == 1:  return 0.85
    if age == 2:  return 0.70
    if age <= 4:  return 0.55
    return 0.30


# ─────────────────────────────────────────────────────────
#  Epoch weight modifier
#  Fingerprints from different regulation epochs are less
#  comparable. Apply a penalty when epochs differ.
# ─────────────────────────────────────────────────────────

def epoch_weight(fp_epoch: str, target_round: int) -> float:
    """
    Reduce the weight of fingerprints from earlier epochs when predicting
    in a later epoch. The further back the epoch, the lower the trust.

    Epochs (in order):
      A_pre_miami   — R1-R3: different harvest cap + superclip ceiling
      B_miami_canada — R4-R5: new harvest + superclip, but Mercedes trick active
      C_post_monaco — R6+:   full level playing field

    When the target circuit is C epoch:
      - A fingerprints get 0.5x weight (wrong harvest regime AND wrong PU order)
      - B fingerprints get 0.75x weight (correct harvest/superclip, but Mercedes inflated)
      - C fingerprints get 1.0x weight
    When target is B epoch:
      - A fingerprints get 0.65x weight
      - B/C fingerprints get 1.0x weight
    """
    from config import regulation_epoch_for_round
    target_epoch = regulation_epoch_for_round(target_round)

    if fp_epoch == target_epoch:
        return 1.0

    epoch_order = {"A_pre_miami": 0, "B_miami_canada": 1, "C_post_monaco": 2}
    fp_idx     = epoch_order.get(fp_epoch, 0)
    target_idx = epoch_order.get(target_epoch, 2)

    gap = target_idx - fp_idx
    if gap <= 0:
        return 1.0    # same or newer epoch — no penalty
    elif gap == 1:
        return 0.75
    else:
        return 0.50


# ─────────────────────────────────────────────────────────
#  Team upgrade weight
#  Chassis/aero upgrades can make pre-upgrade fingerprints
#  unrepresentative. Separate from regulation epochs.
# ─────────────────────────────────────────────────────────

def team_upgrade_weight(driver: str, fp_round: int, target_round: int) -> float:
    """
    Returns a weight modifier (0–1) based on known team chassis/aero upgrades.
    When a significant upgrade landed between fp_round and target_round,
    the older fingerprint is less representative of the car at target_round.

    Stacks multiplicatively when multiple upgrades intervene.
    """
    from config import CARS, TEAM_UPGRADES

    team = CARS.get(driver, {}).get("team", "Unknown")
    upgrades = TEAM_UPGRADES.get(team, [])

    weight = 1.0
    for upg in upgrades:
        if fp_round < upg["from_round"] <= target_round:
            sig = upg["significance"]
            if sig == "new_car":
                weight *= 0.05    # essentially discard — different car
            elif sig == "major":
                weight *= 0.40
            elif sig == "medium":
                weight *= 0.70
            elif sig == "minor":
                weight *= 0.90
    return weight


def get_upcoming_upgrade_notes(driver: str, target_round: int) -> list[str]:
    """Return notes for known upcoming upgrades at target_round."""
    from config import CARS, KNOWN_UPCOMING_UPGRADES

    team = CARS.get(driver, {}).get("team", "Unknown")
    pu   = CARS.get(driver, {}).get("pu",   "Unknown")
    notes = []

    for source in (team, pu):
        for upg in KNOWN_UPCOMING_UPGRADES.get(source, []):
            if upg["at_round"] == target_round:
                notes.append(f"⚠ INCOMING R{target_round}: {upg['note']}")

    return notes


# ─────────────────────────────────────────────────────────
#  Regulation notes
# ─────────────────────────────────────────────────────────

def get_regulation_notes(pu_name: str, target_round: int) -> list[str]:
    notes = []

    # ADUO table lives in config.PU_ADUO_UPGRADES — single source of truth,
    # shared with the Upgrades page so the two can never disagree.
    aduo_upgrades = PU_ADUO_UPGRADES

    if pu_name in aduo_upgrades:
        upg   = aduo_upgrades[pu_name]
        rnd   = upg.get("round")
        if rnd is None:
            notes.append(f"ADUO allocated, not deployed: {upg['note']}")
        elif target_round > rnd:
            notes.append(f"Post-ADUO: {upg['note']}")
        elif target_round == rnd:
            notes.append(f"ADUO DEPLOYING THIS ROUND: {upg['note']} "
                         "Historical fingerprints predate it, so this prediction "
                         "understates any gain.")
        else:
            notes.append(f"Pre-ADUO: upgrade expected ~R{rnd}. {upg['note']}")

        second = upg.get("second_round")
        if second and target_round < second:
            notes.append(f"Second ADUO upgrade expected ~R{second}.")

    # RedBullFord note
    if pu_name == "RedBullFord":
        notes.append("ADUO benchmark: best ICE on grid but chassis deficit limits results")

    # Compression rule — effective Monaco R6
    if pu_name == "Mercedes" and target_round >= 6:
        notes.append("Compression ratio hot-test rule active from Monaco (R6) — "
                     "loophole closed; pace advantage narrowed")
    elif pu_name in ("Mercedes",) and target_round < 6:
        notes.append("Pre-Monaco: fingerprints include compression ratio advantage — "
                     "pace may be 0.2–0.3s/lap overstated vs R6+ baseline")

    # Honda caution
    if pu_name == "Honda" and target_round <= 6:
        notes.append("CAUTION: Honda battery vibration and energy recovery issues — "
                     "retirement risk elevated; confidence penalised")

    return notes


# ─────────────────────────────────────────────────────────
#  Core prediction engine
# ─────────────────────────────────────────────────────────

def _predict_for_sessions(
    target_circuit: str,
    sessions:       list[str],
    year:           int = 2026,
    drivers:        list[str] = None,
    source_label:   str = "qualifying",
    session_weights: dict[str, float] = None,
) -> RacePrediction | None:
    """
    Core prediction logic. Loads fingerprints from the specified session types
    and produces a RacePrediction.

    session_weights optionally scales each session type's contribution, e.g.
    {"SQ": 1.0, "Q": 0.85} to favour sprint qualifying when predicting a
    sprint qualifying session while still using the far larger GP qualifying
    sample. Omitted types default to 1.0.

    Returns None if no data is available.
    """
    if target_circuit not in CIRCUITS:
        raise ValueError(f"Unknown circuit: {target_circuit}")

    circuit_cfg  = CIRCUITS[target_circuit]
    target_type  = circuit_cfg["circuit_type"]
    target_round = circuit_cfg["round"]

    historical = load_all_fingerprints(year, sessions=sessions)
    if not historical:
        return None

    if drivers is None:
        drivers = list({fp.driver_code
                        for rf in historical
                        for fp in rf.fingerprints})

    prediction = RacePrediction(
        circuit_name       = target_circuit,
        circuit_type       = target_type,
        race_round         = target_round,
        year               = year,
        source             = source_label,
        n_historical_races = len(historical),
    )

    prediction.methodology_notes = [
        f"Sessions used: {', '.join(sessions)}",
        f"Based on {len(historical)} session(s) of observed data",
        f"Target circuit type: {target_type}",
        "Primary signal: lap_time_gap_pct",
        "Secondary signal: braking_harvest_ratio (hrv_adj applied)",
        "Epoch weighting applied — earlier regulation regimes down-weighted",
    ]
    if session_weights:
        prediction.methodology_notes.append(
            "Session-type weighting: "
            + ", ".join(f"{k}x{v:g}" for k, v in session_weights.items())
        )

    driver_predictions = []

    for driver in drivers:
        driver_fps = [fp for rf in historical
                      for fp in rf.fingerprints
                      if fp.driver_code == driver]
        if not driver_fps:
            continue

        weighted_gaps = []
        weighted_str  = []
        weighted_hrv  = []
        weights       = []

        # Single loop — applies epoch, upgrade, and session-type weights
        for fp in driver_fps:
            sim     = circuit_similarity(fp.circuit_type, target_type)
            recency = recency_weight(fp.race_round, target_round)
            ep_w    = epoch_weight(fp.regulation_epoch, target_round)
            upg_w   = team_upgrade_weight(driver, fp.race_round, target_round)
            sess_w  = (session_weights or {}).get(fp.session_type, 1.0)
            weight  = sim * recency * ep_w * upg_w * sess_w * fp.confidence
            if weight < 0.05:
                continue
            weighted_gaps.append((fp.lap_time_gap_pct,        weight))
            weighted_str.append((fp.straight_speed_delta_kph, weight))
            weights.append(weight)

            # ERS harvest ratio — qualifying only.
            # Race rep laps come from different race moments (fuel/tyre/temp vary
            # per driver), making telemetry speed comparisons unreliable.
            # lap_time_gap_pct from race sessions is valid; speed traces are not.
            if fp.session_type in ("Q", "SQ"):
                weighted_hrv.append((fp.braking_harvest_ratio, weight))

        if not weights:
            continue

        total_weight = sum(weights)

        def wmean(pairs):
            return sum(v * w for v, w in pairs) / total_weight

        def wstd(pairs):
            m = wmean(pairs)
            return np.sqrt(sum(w * (v - m)**2 for v, w in pairs) / total_weight)

        avg_gap_pct = wmean(weighted_gaps)
        gap_std     = wstd(weighted_gaps)
        str_delta   = wmean(weighted_str)
        avg_hrv     = wmean(weighted_hrv) if weighted_hrv else 1.0

        ct        = CIRCUIT_TYPES[target_type]
        hrv_adj_s = (1.0 - avg_hrv) * ct["braking_weight"] * HRV_SCALE

        ref_lap_s       = (circuit_cfg["lap_length_km"] / 250) * 3600
        predicted_delta = (avg_gap_pct / 100) * ref_lap_s + hrv_adj_s
        uncertainty     = (gap_std / 100) * ref_lap_s
        uncertainty     = max(uncertainty, 0.30 / max(1, len(weights) ** 0.5))

        reg_notes = get_regulation_notes(driver_fps[0].pu_name, target_round)

        # Honda retirement risk: inflate gap uncertainty pre-ADUO
        if driver_fps[0].pu_name == "Honda" and target_round <= 6:
            uncertainty += 1.5

        # Upcoming upgrade warnings
        upcoming = get_upcoming_upgrade_notes(driver, target_round)
        reg_notes.extend(upcoming)

        # Confidence: based on cross-circuit variance, not just count.
        # Low gap_std → consistently fast/slow across circuits → higher confidence.
        # Capped at 0.85 to reflect irreducible uncertainty.
        n_races = len(weights)
        data_conf     = min(0.85, 0.40 + n_races * 0.03)
        variance_conf = 1.0 / (1.0 + gap_std * 2.0)   # gap_std in % units
        conf          = min(0.85, 0.5 * data_conf + 0.5 * variance_conf)

        dp = DriverPrediction(
            driver_code                = driver,
            team                       = driver_fps[0].team,
            pu_name                    = driver_fps[0].pu_name,
            predicted_delta_s          = predicted_delta,
            delta_range_low            = predicted_delta - uncertainty,
            delta_range_high           = predicted_delta + uncertainty,
            predicted_straight_gap_kph = str_delta,
            predicted_harvest_ratio    = avg_hrv,
            confidence                 = conf,
            n_races_used               = n_races,
            regulation_notes           = reg_notes,
        )
        driver_predictions.append(dp)

    if not driver_predictions:
        return None

    # Normalise so fastest = 0
    min_delta = min(p.predicted_delta_s for p in driver_predictions)
    for p in driver_predictions:
        p.predicted_delta_s  -= min_delta
        p.delta_range_low    -= min_delta
        p.delta_range_high   -= min_delta

    prediction.predictions        = driver_predictions
    prediction.overall_confidence = np.mean([p.confidence for p in driver_predictions])

    return prediction


# ─────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────

def predict_qualifying(
    target_circuit: str,
    year:           int        = 2026,
    drivers:        list[str]  = None,
) -> RacePrediction | None:
    """Predict based on Q + SQ fingerprints only."""
    return _predict_for_sessions(
        target_circuit, ["Q", "SQ"], year, drivers, source_label="qualifying"
    )


def predict_race_pace(
    target_circuit: str,
    year:           int        = 2026,
    drivers:        list[str]  = None,
) -> RacePrediction | None:
    """Predict based on R + S fingerprints only."""
    return _predict_for_sessions(
        target_circuit, ["R", "S"], year, drivers, source_label="race"
    )


# ── Sprint weekends ───────────────────────────────────────
#
# Pooled, not SQ-only. Measured on the four 2026 sprint weekends so far
# (China, Miami, Canada, Britain), GP qualifying predicts sprint qualifying
# at the SAME weekend with spearman +0.906 — better than one GP qualifying
# predicts the NEXT one (+0.876). So GP quali is not a weak stand-in for
# sprint quali; it is a stronger signal than sprint quali from a different
# weekend. Filtering to ["SQ"] alone would cut the sample from 15 sessions
# to 4 and discard the better-correlated data.
#
# The matching session type still gets a mild preference, because the
# correlation is high but not perfect (mean absolute difference 0.745
# percentage points). Raise CROSS_SESSION_WEIGHT to 1.0 for pure pooling,
# or lower it to lean harder on sprint-specific history.
CROSS_SESSION_WEIGHT = 0.85


def predict_sprint_qualifying(
    target_circuit: str,
    year:           int        = 2026,
    drivers:        list[str]  = None,
) -> RacePrediction | None:
    """Predict sprint qualifying. Pooled SQ + Q, SQ weighted higher."""
    return _predict_for_sessions(
        target_circuit, ["SQ", "Q"], year, drivers,
        source_label    = "sprint qualifying",
        session_weights = {"SQ": 1.0, "Q": CROSS_SESSION_WEIGHT},
    )


def predict_sprint_race(
    target_circuit: str,
    year:           int        = 2026,
    drivers:        list[str]  = None,
) -> RacePrediction | None:
    """Predict the sprint race. Pooled S + R, S weighted higher."""
    return _predict_for_sessions(
        target_circuit, ["S", "R"], year, drivers,
        source_label    = "sprint race",
        session_weights = {"S": 1.0, "R": CROSS_SESSION_WEIGHT},
    )


def predict_race(
    target_circuit: str,
    year:           int        = 2026,
    drivers:        list[str]  = None,
) -> RacePrediction:
    """
    Blended prediction. Uses race pace data if available, falls back to
    qualifying only. When both exist, weights race 60 / quali 40.
    Race weight grows as more race data accumulates.
    """
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

    blended = []
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

        delta   = (qp.predicted_delta_s * q_w + rp.predicted_delta_s * r_w) / tot
        low     = (qp.delta_range_low   * q_w + rp.delta_range_low   * r_w) / tot
        high    = (qp.delta_range_high  * q_w + rp.delta_range_high  * r_w) / tot
        str_gap = (qp.predicted_straight_gap_kph * q_w +
                   rp.predicted_straight_gap_kph * r_w) / tot
        hrv     = (qp.predicted_harvest_ratio * q_w +
                   rp.predicted_harvest_ratio * r_w) / tot
        conf    = (qp.confidence * q_w + rp.confidence * r_w) / tot
        n       = qp.n_races_used + rp.n_races_used

        blended.append(DriverPrediction(
            driver_code                = drv,
            team                       = qp.team,
            pu_name                    = qp.pu_name,
            predicted_delta_s          = delta,
            delta_range_low            = low,
            delta_range_high           = high,
            predicted_straight_gap_kph = str_gap,
            predicted_harvest_ratio    = hrv,
            confidence                 = conf,
            n_races_used               = n,
            regulation_notes           = qp.regulation_notes,
        ))

    min_delta = min(p.predicted_delta_s for p in blended)
    for p in blended:
        p.predicted_delta_s  -= min_delta
        p.delta_range_low    -= min_delta
        p.delta_range_high   -= min_delta

    circuit_cfg  = CIRCUITS[target_circuit]
    return RacePrediction(
        circuit_name       = target_circuit,
        circuit_type       = circuit_cfg["circuit_type"],
        race_round         = circuit_cfg["round"],
        year               = year,
        source             = "blended",
        predictions        = blended,
        overall_confidence = float(np.mean([p.confidence for p in blended])),
        n_historical_races = qual_pred.n_historical_races + race_pred.n_historical_races,
        methodology_notes  = [
            f"Blended: qualifying {qual_weight:.0%} / race pace {race_weight:.0%}",
            f"Qualifying sessions: {qual_pred.n_historical_races}",
            f"Race sessions: {race_pred.n_historical_races}",
            "Primary signal: lap_time_gap_pct",
            "hrv_adj applied",
            "Epoch weighting: A=0.50x, B=0.75x, C=1.0x relative to C target",
        ],
    )


def print_prediction(pred: RacePrediction):
    print(f"\n{'═'*72}")
    print(f"  Prediction: {pred.circuit_name} [{pred.circuit_type}]  "
          f"Rd {pred.race_round} — {pred.year}  [{pred.source.upper()}]")
    print(f"  Based on {pred.n_historical_races} session(s)  |  "
          f"Overall confidence: {pred.overall_confidence:.0%}")
    print(f"{'─'*72}")
    print(f"  {'Pos':<4} {'Driver':<6} {'Team':<18} {'PU':<14} "
          f"{'Gap':>6}  {'Range':>14}  {'HrvR':>5}  {'Conf':>5}  {'n':>3}")
    print(f"  {'─'*4} {'─'*6} {'─'*18} {'─'*14} "
          f"{'─'*6}  {'─'*14}  {'─'*5}  {'─'*5}  {'─'*3}")

    for pos, p in enumerate(pred.ranked(), 1):
        gap    = f"+{p.predicted_delta_s:.3f}s" if p.predicted_delta_s > 0 else "POLE"
        range_ = f"[{p.delta_range_low:+.2f} / {p.delta_range_high:+.2f}]"
        print(f"  P{pos:<3} {p.driver_code:<6} {p.team:<18} {p.pu_name:<14} "
              f"{gap:>6}  {range_:>14}  {p.predicted_harvest_ratio:.3f}  "
              f"{p.confidence:.0%}  {p.n_races_used:>3}")
        for note in p.regulation_notes:
            print(f"         ↳ {note}")

    print(f"\n  Methodology:")
    for note in pred.methodology_notes:
        print(f"    • {note}")
    print(f"{'═'*72}\n")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data.race_store import print_store_summary

    print_store_summary()
    try:
        pred = predict_race("Miami")
        print_prediction(pred)
    except ValueError as e:
        print(f"\n  Cannot predict yet: {e}")
