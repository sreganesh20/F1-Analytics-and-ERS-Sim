"""
models/fingerprint.py
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from models.track import TrackSegment, segment_lap
from models.optimizer import OptimalStrategy, OptimalSegment, max_harvestable_mj
from config import CARS, CIRCUIT_TYPES, REGS, regulation_epoch_for_round, lineup_for_round

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
    # ── WAVE 1: Race result fields (race sessions only; None for quali) ──
    finishing_position: int | None   = None   # classified finishing position
    grid_position:      int | None   = None   # starting grid slot
    positions_gained:   int | None   = None   # grid - finish (+ve = gained places)
    result_status:      str          = ""     # "Finished" | "+1 Lap" | "Retired" | "DSQ" ...
    # ── WAVE 1: Sector times of the representative/fastest lap ──
    sector_1_s:  float | None = None
    sector_2_s:  float | None = None
    sector_3_s:  float | None = None
    # ── WAVE 3: PERSONAL BEST sector across the whole session ──
    # Distinct from the above: sector_N_s are the splits of ONE lap, so the
    # fastest driver sweeps all three. These are each driver's best individual
    # sector from any lap — what "fastest sector" actually means.
    best_sector_1_s: float | None = None
    best_sector_2_s: float | None = None
    best_sector_3_s: float | None = None
    # ── WAVE 1: Race operations ──
    pit_stops:          int          = 0      # tyre changes (compound changes)
    tyre_compounds:     list         = field(default_factory=list)  # e.g. ["MEDIUM","HARD","SOFT"]
    pit_lane_time_s:    float | None = None   # BEST pit lane transit (in->out), NOT stationary
    fastest_lap_s:      float | None = None   # driver's outright fastest lap of session
    fastest_lap_number: int | None   = None
    # ── WAVE 1: Corner speed deltas split by corner type (kph vs reference) ──
    corner_slow_delta_kph:   float | None = None
    corner_medium_delta_kph: float | None = None
    corner_fast_delta_kph:   float | None = None


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


def _distance_integrated_mean_speed_kph(
    df: pd.DataFrame,
    d_start: float,
    d_end: float,
    resolution_m: float = 2.0,
) -> float | None:
    """
    Mean traversal speed through a fixed distance window.

    Telemetry samples are not guaranteed to land on identical distance points for
    every driver. Summing per-sample DeltaTime inside a short corner therefore
    makes the result depend on sample boundaries (e.g. 6 samples for one driver,
    7 for another). Instead, interpolate speed onto the SAME distance grid for
    every car and integrate dt = dx / v.

    This keeps the comparison in the fixed-distance domain used by the corner
    segments while removing sampling-density/boundary artefacts.
    """
    if df.empty or d_end <= d_start:
        return None
    if "Distance" not in df.columns or "Speed" not in df.columns:
        return None

    work = df[["Distance", "Speed"]].replace([np.inf, -np.inf], np.nan).dropna()
    work = work[work["Speed"] > 1.0]
    if len(work) < 2:
        return None

    # np.interp requires monotonically increasing x values. FastF1 can contain
    # duplicate distance samples, so collapse them deterministically first.
    work = (
        work.sort_values("Distance")
        .groupby("Distance", as_index=False, sort=True)["Speed"]
        .mean()
    )
    distances = work["Distance"].to_numpy(dtype=float)
    speeds_kph = work["Speed"].to_numpy(dtype=float)
    if len(distances) < 2:
        return None

    # Never silently extrapolate beyond the driver's recorded lap coverage.
    if d_start < distances[0] or d_end > distances[-1]:
        return None

    seg_len = float(d_end - d_start)
    n_points = max(3, int(np.ceil(seg_len / max(resolution_m, 0.5))) + 1)
    grid = np.linspace(float(d_start), float(d_end), n_points)
    interp_speed_kph = np.interp(grid, distances, speeds_kph)
    interp_speed_ms = interp_speed_kph / 3.6

    if np.any(~np.isfinite(interp_speed_ms)) or np.any(interp_speed_ms <= 0):
        return None

    # Trapezoidal integration of reciprocal speed gives traversal time over the
    # exact same metres for every driver.
    reciprocal_speed = 1.0 / interp_speed_ms
    dx = np.diff(grid)
    traversal_time_s = float(np.sum(0.5 * (reciprocal_speed[:-1] + reciprocal_speed[1:]) * dx))
    if not np.isfinite(traversal_time_s) or traversal_time_s <= 0:
        return None

    return 3.6 * seg_len / traversal_time_s


def compute_speed_deltas(
    car_df:   pd.DataFrame,
    ref_df:   pd.DataFrame,
    segments: list[TrackSegment],
) -> dict:
    deltas = {
        "straight":      [],
        "superclip":     [],
        "braking":       [],
        "corner":        [],
        "lift_coast":    [],
        # WAVE 1: corner deltas split by apex-speed class
        "corner_slow":   [],
        "corner_medium": [],
        "corner_fast":   [],
    }
    for seg in segments:
        if seg.seg_type == "corner":
            # Exact fixed-distance comparison on a shared interpolation grid.
            # This replaces summing whatever DeltaTime samples happened to fall
            # inside the window, which was unstable on short corners/chicanes.
            car_speed = _distance_integrated_mean_speed_kph(
                car_df, seg.d_start, seg.d_end
            )
            ref_speed = _distance_integrated_mean_speed_kph(
                ref_df, seg.d_start, seg.d_end
            )
            if car_speed is not None and ref_speed is not None:
                delta = car_speed - ref_speed
                deltas["corner"].append(delta)
                # Also bucket by corner speed class
                sc = getattr(seg, "speed_class", "")
                if sc in ("slow", "medium", "fast"):
                    deltas[f"corner_{sc}"].append(delta)
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
    # Median, not mean, across segments within a lap. A single mis-segmented
    # or compromised corner can otherwise define the whole lap: at Britain SQ
    # Piastri's mean across 8 corners was +24.48 kph while his median was
    # +2.69 — one segment was producing the entire number.
    out = {}
    for k, v in deltas.items():
        if k.startswith("corner_") and k != "corner":
            # None when this circuit has no corners of that class
            out[k] = float(np.median(v)) if v else None
        else:
            out[k] = float(np.median(v)) if v else 0.0
    return out


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
    result_data:      dict  = None,   # WAVE 1: race result / sector / pit data
) -> CarFingerprint:
    rd           = result_data or {}
    session_is_quali = circuit_cfg.get("fastf1_session", "Q") in ("Q", "SQ")
    circuit_type = circuit_cfg.get("circuit_type", "balanced")
    race_round   = circuit_cfg.get("round", 0)
    # Round-aware lineup, not the flat CARS dict. This is the field that ends up
    # in the stored fingerprint, so reading CARS here meant a substitute driver
    # was filed under the wrong team (Lawson's Red Bull laps tagged VCARB) or,
    # for a reserve absent from CARS entirely, "Unknown".
    car_info     = lineup_for_round(race_round).get(
        driver_code, {"team": "Unknown", "pu": "Unknown"})
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
    # Corrupted telemetry detection — only flags physically impossible data.
    # Large speed deltas vs reference are EXPECTED for midfield/backmarker cars
    # and must never trigger exclusion. A legitimate Aston Martin at Austria Q
    # will be 50+ kph off the reference Ferrari in braking zones. That is data.
    _spd = car_df["Speed"]
    _dst = car_df["Distance"]
    if _spd.isnull().any() or (_spd < 0).any() or _dst.isnull().any() \
            or car_df["Throttle"].isnull().any():
        confidence = 0.1
        print(f"  {driver_code} flagged — corrupted telemetry (NaN/negative speed)")
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
        # ── WAVE 1 fields ──
        finishing_position        = rd.get("finishing_position"),
        grid_position             = rd.get("grid_position"),
        positions_gained          = rd.get("positions_gained"),
        result_status             = rd.get("result_status", ""),
        sector_1_s                = rd.get("sector_1_s"),
        sector_2_s                = rd.get("sector_2_s"),
        sector_3_s                = rd.get("sector_3_s"),
        best_sector_1_s           = rd.get("best_sector_1_s"),
        best_sector_2_s           = rd.get("best_sector_2_s"),
        best_sector_3_s           = rd.get("best_sector_3_s"),
        pit_stops                 = rd.get("pit_stops", 0),
        tyre_compounds            = rd.get("tyre_compounds", []) or [],
        pit_lane_time_s           = rd.get("pit_lane_time_s"),
        fastest_lap_s             = rd.get("fastest_lap_s"),
        fastest_lap_number        = rd.get("fastest_lap_number"),
        # Corner-class deltas: QUALIFYING ONLY. Race laps re-segment differently
        # (fuel, lift-and-coast shift braking points), so per-class comparison
        # across sessions is invalid. Circuit corner profile = quali profile.
        corner_slow_delta_kph     = speed_deltas.get("corner_slow")   if session_is_quali else None,
        corner_medium_delta_kph   = speed_deltas.get("corner_medium") if session_is_quali else None,
        corner_fast_delta_kph     = speed_deltas.get("corner_fast")   if session_is_quali else None,
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
    result_map:         dict      = None,   # WAVE 1: driver_code -> result dict
) -> RaceFingerprints:
    retirements        = retirements        or []
    laps_completed_map = laps_completed_map or {}
    result_map         = result_map         or {}
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
            result_data      = result_map.get(driver, {}),
        )
        if fp.confidence < 0.12:
            print(f"  {fp.driver_code} excluded — corrupted telemetry (confidence {fp.confidence:.2f})")
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
