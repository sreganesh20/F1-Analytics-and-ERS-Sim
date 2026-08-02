"""
models/fingerprint.py
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from models.track import TrackSegment, segment_lap
from models.optimizer import OptimalStrategy, OptimalSegment, max_harvestable_mj
from config import CARS, CIRCUIT_TYPES, REGS, regulation_epoch_for_round


@dataclass
class CarFingerprint:
    # Identity
    driver_code:      str
    team:             str
    pu_name:          str
    circuit_name:     str
    circuit_type:     str
    race_round:       int
    year:             int
    session_type:     str

    # Observed lap metrics
    lap_time_s:       float
    lap_time_rank:    int
    lap_time_gap_pct: float

    # Segment-level speed deltas vs reference car
    straight_speed_delta_kph:   float
    braking_speed_delta_kph:    float
    corner_speed_delta_kph:     float

    # Inferred ERS behaviour ratios
    braking_harvest_ratio:  float
    straight_deploy_ratio:  float
    corner_deploy_ratio:    float

    # Time deltas from theoretical optimal
    time_lost_straights_s:  float
    time_lost_braking_s:    float
    time_lost_corners_s:    float
    time_lost_total_s:      float

    # Reliability signal
    completed_race:   bool
    laps_completed:   int

    # Data quality
    source:           str
    confidence:       float

    # Regulation context — MUST appear after all required fields
    # Default "A_pre_miami" ensures backward compatibility with stored JSONs
    # that predate this field. Derive via regulation_epoch_for_round(race_round).
    regulation_epoch: str = "A_pre_miami"


@dataclass
class RaceFingerprints:
    circuit_name:  str
    circuit_type:  str
    race_round:    int
    year:          int
    session_type:  str
    fingerprints:  list[CarFingerprint] = field(default_factory=list)

    def by_driver(self, driver_code: str) -> CarFingerprint | None:
        return next((f for f in self.fingerprints if f.driver_code == driver_code), None)

    def by_pu(self, pu_name: str) -> list[CarFingerprint]:
        return [f for f in self.fingerprints if f.pu_name == pu_name]

    def ranked(self) -> list[CarFingerprint]:
        return sorted(self.fingerprints, key=lambda f: f.lap_time_s)


def compute_speed_deltas(
    car_df:   pd.DataFrame,
    ref_df:   pd.DataFrame,
    segments: list[TrackSegment],
) -> dict:
    deltas = {
        "straight":   [],
        "superclip":  [],
        "braking":    [],
        "corner":     [],
        "lift_coast": [],
    }

    for seg in segments:
        if seg.seg_type == "corner":
            car_mask = (car_df["Distance"] >= seg.d_start) & (car_df["Distance"] < seg.d_end)
            ref_mask = (ref_df["Distance"] >= seg.d_start) & (ref_df["Distance"] < seg.d_end)
            car_time = float(np.sum(car_df.loc[car_mask, "DeltaTime"].values)) \
                       if car_df.loc[car_mask].shape[0] > 0 else 0
            ref_time = float(np.sum(ref_df.loc[ref_mask, "DeltaTime"].values)) \
                       if ref_df.loc[ref_mask].shape[0] > 0 else 0
            if ref_time > 0:
                delta = -(car_time - ref_time) / ref_time * seg.speed_mean
                deltas["corner"].append(delta)
            continue

        car_mask = (car_df["Distance"] >= seg.d_start) & (car_df["Distance"] < seg.d_end)
        ref_mask = (ref_df["Distance"] >= seg.d_start) & (ref_df["Distance"] < seg.d_end)

        car_speeds = car_df.loc[car_mask, "Speed"].values
        ref_speeds = ref_df.loc[ref_mask, "Speed"].values

        if len(car_speeds) == 0 or len(ref_speeds) == 0:
            continue

        delta   = np.mean(car_speeds) - np.mean(ref_speeds)
        seg_key = seg.seg_type if seg.seg_type in deltas else "corner"
        deltas[seg_key].append(delta)

    return {k: float(np.mean(v)) if v else 0.0 for k, v in deltas.items()}


def compute_harvest_ratios(
    car_df:   pd.DataFrame,
    ref_df:   pd.DataFrame,
    segments: list[TrackSegment],
    optimal:  OptimalStrategy,
) -> dict:
    """
    Infer effective harvest ratio using kinetic energy domain.

    For each braking zone:
      - Compute KE drop: ½v_entry² - ½v_min²  (mass cancels in ratio)
      - Compare car KE drop vs reference KE drop → relative harvest aggressiveness
      - Compare car KE drop vs optimizer max_harvest → utilisation vs physics ceiling
      - Blend both signals 60/40

    Uses REGS["car_mass_kg"] (not hardcoded) for the utilisation branch.
    """
    KPH_TO_MS   = 1 / 3.6
    car_mass_kg = REGS["car_mass_kg"]   # was previously hardcoded as 798

    ratios = {"braking": [], "superclip": [], "corner": []}

    for opt_seg in optimal.segments:
        seg_type = opt_seg.seg_type
        if seg_type not in ratios:
            continue
        if opt_seg.max_harvest <= 0.01:
            continue

        car_mask = (car_df["Distance"] >= opt_seg.d_start) & \
                   (car_df["Distance"] <  opt_seg.d_end)
        ref_mask = (ref_df["Distance"] >= opt_seg.d_start) & \
                   (ref_df["Distance"] <  opt_seg.d_end)

        car_data = car_df.loc[car_mask]
        ref_data = ref_df.loc[ref_mask]

        if car_data.empty or ref_data.empty:
            continue

        car_v_entry = car_data["Speed"].iloc[0]  * KPH_TO_MS
        car_v_min   = car_data["Speed"].min()    * KPH_TO_MS
        ref_v_entry = ref_data["Speed"].iloc[0]  * KPH_TO_MS
        ref_v_min   = ref_data["Speed"].min()    * KPH_TO_MS

        car_ke_drop = max(0.0, 0.5 * (car_v_entry**2 - car_v_min**2))
        ref_ke_drop = max(0.0, 0.5 * (ref_v_entry**2 - ref_v_min**2))

        if ref_ke_drop < 1.0:
            continue

        rel_ratio = np.clip(car_ke_drop / ref_ke_drop, 0.4, 1.2)

        car_ke_mj = 0.5 * car_mass_kg * car_ke_drop * 1e-6
        util_ratio = np.clip(car_ke_mj / opt_seg.max_harvest, 0.4, 1.2)

        blended = 0.60 * rel_ratio + 0.40 * util_ratio
        ratios[seg_type].append(float(np.clip(blended, 0.4, 1.1)))

    return {k: float(np.mean(v)) if v else 0.85 for k, v in ratios.items()}


def compute_time_deltas(
    lap_time_s:   float,
    optimal:      OptimalStrategy,
    speed_deltas: dict,
    circuit_type: str,
) -> dict:
    ct = CIRCUIT_TYPES.get(circuit_type, CIRCUIT_TYPES["balanced"])

    total_gap = lap_time_s - (lap_time_s + optimal.lap_time_delta_s)

    straight_delta_contribution = abs(speed_deltas.get("straight", 0))
    braking_delta_contribution  = abs(speed_deltas.get("braking",  0))
    corner_delta_contribution   = abs(speed_deltas.get("corner",   0))

    total_contribution = (straight_delta_contribution + braking_delta_contribution
                          + corner_delta_contribution + 1e-9)

    if total_contribution < 1.0:
        return {
            "straights": total_gap * ct["straight_weight"],
            "braking":   total_gap * ct["braking_weight"],
            "corners":   total_gap * ct["corner_weight"],
        }

    return {
        "straights": total_gap * (straight_delta_contribution / total_contribution),
        "braking":   total_gap * (braking_delta_contribution  / total_contribution),
        "corners":   total_gap * (corner_delta_contribution   / total_contribution),
    }


def fingerprint_car(
    driver_code:      str,
    car_df:           pd.DataFrame,
    ref_df:           pd.DataFrame,
    segments:         list[TrackSegment],
    optimal:          OptimalStrategy,
    circuit_name:     str,
    circuit_cfg:      dict,
    lap_time_s:       float,
    lap_time_rank:    int,
    completed_race:   bool  = True,
    laps_completed:   int   = 1,
    lap_time_gap_pct: float = 0.0,
) -> CarFingerprint:
    car_info     = CARS.get(driver_code, {"team": "Unknown", "pu": "Unknown"})
    circuit_type = circuit_cfg.get("circuit_type", "balanced")
    race_round   = circuit_cfg.get("round", 0)
    epoch        = regulation_epoch_for_round(race_round)

    speed_deltas   = compute_speed_deltas(car_df, ref_df, segments)
    harvest_ratios = compute_harvest_ratios(car_df, ref_df, segments, optimal)
    time_deltas    = compute_time_deltas(lap_time_s, optimal, speed_deltas, circuit_type)

    str_delta         = speed_deltas.get("straight", 0.0)
    ref_top_speed     = ref_df["Speed"].max() if not ref_df.empty else 300.0
    straight_deploy_ratio = np.clip(0.85 + (str_delta / ref_top_speed), 0.4, 1.05)

    confidence = 1.0
    if car_df["Source"].iloc[0] == "Synthetic":
        confidence = 0.5
    if not completed_race:
        confidence *= 0.6

    CORRUPT_DELTA = 80.0   # only catches genuinely broken telemetry
    if abs(speed_deltas.get("straight", 0)) > CORRUPT_DELTA or \
        abs(speed_deltas.get("braking",  0)) > CORRUPT_DELTA:
        confidence = min(confidence, 0.25)   # penalised but not auto-excluded
        print(f"  {driver_code} flagged — extreme speed delta, verify telemetry")

    return CarFingerprint(
        driver_code               = driver_code,
        team                      = car_info["team"],
        pu_name                   = car_info["pu"],
        circuit_name              = circuit_name,
        circuit_type              = circuit_type,
        race_round                = race_round,
        year                      = circuit_cfg.get("fastf1_year", 2026),
        session_type              = circuit_cfg.get("fastf1_session", "Q"),
        lap_time_s                = lap_time_s,
        lap_time_rank             = lap_time_rank,
        lap_time_gap_pct          = lap_time_gap_pct,
        straight_speed_delta_kph  = speed_deltas.get("straight", 0.0),
        braking_speed_delta_kph   = speed_deltas.get("braking",  0.0),
        corner_speed_delta_kph    = speed_deltas.get("corner",   0.0),
        braking_harvest_ratio     = harvest_ratios.get("braking",   0.85),
        straight_deploy_ratio     = float(straight_deploy_ratio),
        corner_deploy_ratio       = harvest_ratios.get("corner",    0.85),
        time_lost_straights_s     = time_deltas["straights"],
        time_lost_braking_s       = time_deltas["braking"],
        time_lost_corners_s       = time_deltas["corners"],
        time_lost_total_s         = sum(time_deltas.values()),
        completed_race            = completed_race,
        laps_completed            = laps_completed,
        source                    = str(car_df["Source"].iloc[0]),
        confidence                = confidence,
        regulation_epoch          = epoch,
    )


def fingerprint_race(
    driver_telemetry:   dict,
    lap_times:          dict,
    segments:           list[TrackSegment],
    optimal:            OptimalStrategy,
    circuit_name:       str,
    circuit_cfg:        dict,
    retirements:        list[str] = None,
    laps_completed_map: dict      = None,
) -> RaceFingerprints:
    retirements        = retirements        or []
    laps_completed_map = laps_completed_map or {}

    if not lap_times:
        raise ValueError("No lap times provided")

    valid_drivers = [d for d in lap_times if d in driver_telemetry]
    if not valid_drivers:
        raise ValueError("No matching drivers between telemetry and lap times")

    ref_driver     = min(valid_drivers, key=lambda d: lap_times[d])
    pole_time      = lap_times[ref_driver]
    ref_df         = driver_telemetry[ref_driver]
    ranked_drivers = sorted(valid_drivers, key=lambda d: lap_times[d])

    result = RaceFingerprints(
        circuit_name = circuit_name,
        circuit_type = circuit_cfg.get("circuit_type", "balanced"),
        race_round   = circuit_cfg.get("round", 0),
        year         = circuit_cfg.get("fastf1_year", 2026),
        session_type = circuit_cfg.get("fastf1_session", "Q"),
    )

    for rank, driver in enumerate(ranked_drivers, 1):
        car_df   = driver_telemetry[driver]
        lap_time = lap_times[driver]
        retired  = driver in retirements
        gap_pct  = (lap_times[driver] - pole_time) / pole_time * 100
        laps_done = laps_completed_map.get(driver, 1)

        fp = fingerprint_car(
            driver_code      = driver,
            car_df           = car_df,
            ref_df           = ref_df,
            lap_time_gap_pct = gap_pct,
            segments         = segments,
            optimal          = optimal,
            circuit_name     = circuit_name,
            circuit_cfg      = circuit_cfg,
            lap_time_s       = lap_time,
            lap_time_rank    = rank,
            completed_race   = not retired,
            laps_completed   = laps_done,
        )

        if fp.confidence < 0.15:
            print(f"  {fp.driver_code} excluded — corrupted lap (confidence {fp.confidence:.2f})")
            continue
        result.fingerprints.append(fp)

    return result


def print_race_fingerprints(rf: RaceFingerprints):
    print(f"\n{'═'*70}")
    print(f"  Fingerprints: {rf.circuit_name} [{rf.session_type}]  "
          f"Rd {rf.race_round} — {rf.year}")
    print(f"  Circuit type: {rf.circuit_type}")
    print(f"{'─'*70}")
    print(f"  {'Driver':<6} {'Team':<18} {'PU':<14} {'Lap':>8}  "
          f"{'Str Δ':>7} {'Brk Δ':>7} {'Hrv':>6} {'Dep':>6} {'Conf':>5} {'Epoch'}")
    print(f"  {'─'*6} {'─'*18} {'─'*14} {'─'*8}  "
          f"{'─'*7} {'─'*7} {'─'*6} {'─'*6} {'─'*5} {'─'*14}")

    for fp in rf.ranked():
        lap_str = f"{int(fp.lap_time_s//60)}:{fp.lap_time_s%60:06.3f}"
        print(f"  {fp.driver_code:<6} {fp.team:<18} {fp.pu_name:<14} {lap_str:>8}  "
              f"{fp.straight_speed_delta_kph:>+7.1f} "
              f"{fp.braking_speed_delta_kph:>+7.1f} "
              f"{fp.braking_harvest_ratio:>6.2f} "
              f"{fp.straight_deploy_ratio:>6.2f} "
              f"{fp.confidence:>5.2f} "
              f"{fp.regulation_epoch}")
    print(f"{'═'*70}\n")
