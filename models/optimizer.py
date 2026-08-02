"""
models/optimizer.py

Finds the theoretically optimal ERS harvest/deploy strategy for a given
track segmentation, using ONLY 2026 regulation constraints.

No car parameters. No assumed efficiencies.
This is the physics ceiling — what a perfect power unit could achieve.

Algorithm: Dynamic programming over track segments.
  State:  battery SoC at entry to each segment
  Action: how much to harvest and deploy in each segment
  Reward: lap time saved (negative = faster)
  Constraints: battery 0–4MJ, total harvest ≤ limit, MGU-K power limits
"""

import numpy as np
from dataclasses import dataclass, field
from models.track import TrackSegment
from config import REGS

KPH_TO_MS = 1 / 3.6
MJ_PER_KJ = 1e-3
CAR_MASS = REGS["car_mass_kg"]

# ─────────────────────────────────────────────────────────
#  Physics helpers
# ─────────────────────────────────────────────────────────

def aero_density_factor(circuit_cfg: dict) -> float:
    """
    Compute air density ratio relative to ISA sea-level standard.
    Affects drag-dependent harvest only (superclip, lift_coast).
    Braking KE harvest is unaffected.

    Formula: simplified standard atmosphere × temperature correction.
    ISA standard: 15°C, sea level, ρ₀ = 1.225 kg/m³
    """
    altitude_m = circuit_cfg.get("altitude_m", 0)
    avg_temp_c = circuit_cfg.get("avg_temp_c", 20)
    altitude_factor = np.exp(-altitude_m / 8500.0)
    temp_factor     = 288.15 / (273.15 + avg_temp_c)
    return float(np.clip(altitude_factor * temp_factor, 0.60, 1.05))


def kinetic_energy_mj(v_kph: float) -> float:
    """Kinetic energy of the car at speed v (kph) in MJ."""
    v = v_kph * KPH_TO_MS
    return 0.5 * CAR_MASS * v**2 * MJ_PER_KJ


def max_harvestable_mj(seg: TrackSegment, aero_factor: float = 1.0) -> float:
    """Maximum energy physically recoverable from this segment."""
    if seg.seg_type == "braking":
        ke_drop   = max(0.0, kinetic_energy_mj(seg.speed_entry) - kinetic_energy_mj(seg.speed_min))
        mgu_limit = (REGS["mgu_k_max_harvest_kw"] * seg.time_s) * MJ_PER_KJ
        return min(ke_drop, mgu_limit)

    elif seg.seg_type == "superclip":
        mgu_limit    = (REGS["mgu_k_max_harvest_kw"] * seg.time_s) * MJ_PER_KJ
        aero_ceiling = min(mgu_limit * 0.35, 0.30) * aero_factor
        return aero_ceiling

    elif seg.seg_type == "lift_coast":
        ke_drop = max(0.0, kinetic_energy_mj(seg.speed_entry) - kinetic_energy_mj(seg.speed_exit))
        return min(ke_drop * 0.75, 0.20 * aero_factor)

    elif seg.seg_type == "corner":
        if seg.throttle_mean < 55:
            return min(0.10, (REGS["mgu_k_max_harvest_kw"] * seg.time_s * 0.15) * MJ_PER_KJ)
        return 0.0

    return 0.0


def max_deployable_mj(seg: TrackSegment) -> float:
    """Maximum useful energy deployable in this segment."""
    if seg.seg_type in ("straight", "superclip"):
        avg_speed = seg.speed_mean
        taper     = max(0.0, 1.0 - max(0.0, avg_speed - REGS["deploy_taper_speed_kph"]) / 60.0)
        return (REGS["mgu_k_max_deploy_kw"] * seg.time_s) * MJ_PER_KJ * taper

    elif seg.seg_type == "corner":
        if seg.throttle_mean > 35:
            return (REGS["mgu_k_max_deploy_kw"] * seg.time_s * 0.45) * MJ_PER_KJ
        return 0.0

    return 0.0


def time_saved_by_deploy(seg: TrackSegment, deploy_mj: float) -> float:
    """Estimate lap time saved by deploying energy in this segment."""
    if deploy_mj <= 0:
        return 0.0
    benefit_per_mj = {
        "straight":  0.18,
        "superclip": 0.12,
        "corner":    0.10,
    }.get(seg.seg_type, 0.0)
    return deploy_mj * benefit_per_mj


def time_lost_by_harvest(seg: TrackSegment, harvest_mj: float) -> float:
    """Estimate lap time lost by harvesting energy in this segment."""
    if harvest_mj <= 0:
        return 0.0
    cost_per_mj = {
        "braking":    0.03,
        "superclip":  0.06,
        "lift_coast": 0.28,
        "corner":     0.08,
    }.get(seg.seg_type, 0.0)
    return harvest_mj * cost_per_mj


# ─────────────────────────────────────────────────────────
#  Harvest limit selection
# ─────────────────────────────────────────────────────────

def _resolve_harvest_limit(circuit_cfg: dict, session: str) -> float:
    """
    Return the correct FIA harvest ceiling for this circuit + session combination.

    Priority:
      1. Per-circuit session-specific key (harvest_limit_quali_mj or harvest_limit_race_mj)
      2. Legacy harvest_limit_mj key (for any code still using the old schema)
      3. REGS default for the session type
    """
    if session in ("Q", "SQ"):
        if "harvest_limit_quali_mj" in circuit_cfg:
            return float(circuit_cfg["harvest_limit_quali_mj"])
        if "harvest_limit_mj" in circuit_cfg:
            return float(circuit_cfg["harvest_limit_mj"])
        return REGS["harvest_limit_quali_mj"]
    else:  # R, S, or anything else
        if "harvest_limit_race_mj" in circuit_cfg:
            return float(circuit_cfg["harvest_limit_race_mj"])
        if "harvest_limit_mj" in circuit_cfg:
            return float(circuit_cfg["harvest_limit_mj"])
        return REGS["harvest_limit_race_mj"]


# ─────────────────────────────────────────────────────────
#  Optimal strategy output
# ─────────────────────────────────────────────────────────

@dataclass
class OptimalSegment:
    seg_index:       int
    seg_type:        str
    d_start:         float
    d_end:           float
    time_s:          float
    optimal_harvest: float
    optimal_deploy:  float
    soc_entry:       float
    soc_exit:        float
    max_harvest:     float
    max_deploy:      float
    time_delta_s:    float


@dataclass
class OptimalStrategy:
    circuit_name:     str
    session_type:     str
    harvest_limit_mj: float
    segments:         list[OptimalSegment] = field(default_factory=list)
    total_harvest_mj: float = 0.0
    total_deploy_mj:  float = 0.0
    lap_time_delta_s: float = 0.0
    battery_floor_mj: float = 4.0

    @property
    def harvest_utilisation_pct(self):
        if self.harvest_limit_mj > 0:
            return 100 * self.total_harvest_mj / self.harvest_limit_mj
        return 0.0


# ─────────────────────────────────────────────────────────
#  Dynamic programming optimizer
# ─────────────────────────────────────────────────────────

def optimise(
    segments:     list[TrackSegment],
    circuit_cfg:  dict,
    soc_start:    float = None,
    session_type: str   = None,
) -> OptimalStrategy:
    """
    Optimal ERS harvest/deploy strategy via dynamic programming (Bellman).

    State:  battery SoC at entry to each segment (discretised)
    Action: (harvest, deploy) pair for each segment
    Reward: net lap time saved (deploy benefit - harvest cost)
    """
    from config import SESSION_CONTEXTS

    session       = session_type or circuit_cfg.get("fastf1_session", "Q")
    ctx           = SESSION_CONTEXTS.get(session, SESSION_CONTEXTS["Q"])
    mass_adj      = ctx["car_mass_adj"]
    aero_factor   = aero_density_factor(circuit_cfg)

    # Session-aware harvest limit — the key fix
    base_harvest  = _resolve_harvest_limit(circuit_cfg, session)
    harvest_limit = base_harvest

    battery_cap   = REGS["battery_capacity_mj"]
    soc_init      = soc_start if soc_start is not None else battery_cap

    strategy = OptimalStrategy(
        circuit_name     = circuit_cfg.get("fastf1_name", "Unknown"),
        session_type     = session,
        harvest_limit_mj = harvest_limit,
    )

    N = len(segments)
    if N == 0:
        return strategy

    SOC_STEP   = 0.1
    SOC_LEVELS = int(round(battery_cap / SOC_STEP)) + 1
    INF        = 1e9

    def soc_to_idx(soc: float) -> int:
        return int(round(np.clip(soc, 0.0, battery_cap) / SOC_STEP))

    def idx_to_soc(idx: int) -> float:
        return idx * SOC_STEP

    max_h = [max_harvestable_mj(seg, aero_factor) for seg in segments]
    max_d = [max_deployable_mj(seg)               for seg in segments]

    def _candidates(limit: float) -> np.ndarray:
        if limit < SOC_STEP:
            return np.array([0.0])
        steps = int(round(limit / SOC_STEP))
        return np.linspace(0.0, limit, min(steps + 1, 12))

    actions = []
    for i in range(N):
        h_cands = _candidates(max_h[i])
        d_cands = _candidates(max_d[i])
        actions.append([(h, d) for h in h_cands for d in d_cands])

    BUDGET_STEP   = 0.5
    BUDGET_LEVELS = int(round(harvest_limit / BUDGET_STEP)) + 1

    def budget_to_idx(b: float) -> int:
        return int(round(np.clip(b, 0.0, harvest_limit) / BUDGET_STEP))

    def idx_to_budget(idx: int) -> float:
        return idx * BUDGET_STEP

    V2      = np.full((N + 1, SOC_LEVELS, BUDGET_LEVELS), -INF)
    policy2 = [[[None] * BUDGET_LEVELS for _ in range(SOC_LEVELS)] for _ in range(N)]
    V2[N, :, :] = 0.0

    for i in range(N - 1, -1, -1):
        seg = segments[i]
        for s_idx in range(SOC_LEVELS):
            soc_entry = idx_to_soc(s_idx)
            for b_idx in range(BUDGET_LEVELS):
                budget_used      = idx_to_budget(b_idx)
                budget_remaining = harvest_limit - budget_used
                if budget_remaining < 0:
                    continue

                best_val    = -INF
                best_action = (0.0, 0.0)

                for (h, d) in actions[i]:
                    if h > budget_remaining + 1e-6:
                        continue
                    if h > battery_cap - soc_entry + 1e-6:
                        continue
                    if d > soc_entry + h + 1e-6:
                        continue

                    h = min(h, budget_remaining)
                    h = min(h, battery_cap - soc_entry)
                    d = min(d, soc_entry + h)

                    soc_exit   = np.clip(soc_entry + h - d, 0.0, battery_cap)
                    next_s_idx = soc_to_idx(soc_exit)
                    next_b_idx = budget_to_idx(budget_used + h)

                    future_val = V2[i + 1][next_s_idx][next_b_idx]
                    if future_val < -INF / 2:
                        continue

                    reward = (time_saved_by_deploy(seg, d)
                              - time_lost_by_harvest(seg, h))
                    val    = reward + future_val

                    if val > best_val:
                        best_val    = val
                        best_action = (h, d)

                V2[i][s_idx][b_idx]      = best_val
                policy2[i][s_idx][b_idx] = best_action

    soc         = soc_init
    budget_used = 0.0
    total_harvest = total_deploy = total_dt = 0.0

    for i, seg in enumerate(segments):
        s_idx  = soc_to_idx(soc)
        b_idx  = budget_to_idx(budget_used)
        action = policy2[i][s_idx][b_idx]

        h, d = action if action is not None else (0.0, 0.0)

        h = float(np.clip(h, 0.0, min(max_h[i],
                                       harvest_limit - budget_used,
                                       battery_cap - soc)))
        d = float(np.clip(d, 0.0, min(max_d[i], soc + h)))

        soc_entry   = soc
        soc         = float(np.clip(soc + h - d, 0.0, battery_cap))
        budget_used += h

        dt = (time_saved_by_deploy(seg, d) - time_lost_by_harvest(seg, h))
        total_harvest += h
        total_deploy  += d
        total_dt      += dt

        strategy.segments.append(OptimalSegment(
            seg_index       = seg.index,
            seg_type        = seg.seg_type,
            d_start         = seg.d_start,
            d_end           = seg.d_end,
            time_s          = seg.time_s,
            optimal_harvest = h,
            optimal_deploy  = d,
            soc_entry       = soc_entry,
            soc_exit        = soc,
            max_harvest     = max_h[i],
            max_deploy      = max_d[i],
            time_delta_s    = -dt,
        ))

    strategy.total_harvest_mj = total_harvest
    strategy.total_deploy_mj  = total_deploy
    strategy.lap_time_delta_s = -total_dt
    strategy.battery_floor_mj = min(
        (s.soc_exit for s in strategy.segments), default=0.0
    )
    return strategy


def print_strategy_summary(s: OptimalStrategy):
    print(f"\n{'═'*55}")
    print(f"  Optimal Strategy: {s.circuit_name} [{s.session_type}]")
    print(f"{'═'*55}")
    print(f"  Harvest limit:     {s.harvest_limit_mj:.1f} MJ")
    print(f"  Total harvested:   {s.total_harvest_mj:.3f} MJ  "
          f"({s.harvest_utilisation_pct:.1f}% of limit)")
    print(f"  Total deployed:    {s.total_deploy_mj:.3f} MJ")
    print(f"  Battery floor:     {s.battery_floor_mj:.3f} MJ")
    print(f"  Lap time vs base:  {s.lap_time_delta_s:+.3f}s")
    print(f"{'─'*55}")
    print(f"  Key harvest zones:")
    for seg in s.segments:
        if seg.optimal_harvest > 0.05:
            print(f"    {seg.seg_type:<12} d={seg.d_start:.0f}–{seg.d_end:.0f}m  "
                  f"harvest={seg.optimal_harvest:.3f}MJ  "
                  f"(max={seg.max_harvest:.3f}MJ)")
    print(f"{'═'*55}\n")


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from fetcher import generate_synthetic_telemetry
    from models.track import segment_lap
    from config import CIRCUITS

    for name in ["Australia", "China", "Japan"]:
        df  = generate_synthetic_telemetry(name)
        seg = segment_lap(df)
        opt = optimise(seg, CIRCUITS[name], session_type="Q")
        print_strategy_summary(opt)
