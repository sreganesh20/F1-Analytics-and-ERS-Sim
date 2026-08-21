"""
config.py — ERS Optimizer
2026 F1 regulation constants and circuit taxonomy.

Design principle: No car parameters. No assumed efficiencies.
The only inputs to the physics layer are FIA regulations.
Car characteristics are DERIVED from observations, not assumed.
"""

from datetime import datetime

# ─────────────────────────────────────────────────────────
#  2026 REGULATION CONSTANTS
#  Source: FIA 2026 Technical Regulations
# ─────────────────────────────────────────────────────────

REGS = {
    # MGU-K
    "mgu_k_max_deploy_kw":      350.0,   # Max deploy power
    "mgu_k_max_harvest_kw":     350.0,   # Max harvest power (from Miami R4+; was 250kW R1-R3)
    "deploy_ramp_kw_per_s":      50.0,
    "deploy_taper_speed_kph":   290.0,   # Speed above which deploy tapers (Monaco: 200kph)

    # Battery
    "battery_capacity_mj":        4.0,
    "battery_min_mj":             0.0,

    # Per-lap harvest limits — FIA sets per event, per session type
    # These are FALLBACK values when a circuit entry doesn't override them.
    # Actual per-circuit values live in CIRCUITS below.
    "harvest_limit_race_mj":      8.5,   # FIA regulation baseline (race)
    "harvest_limit_quali_mj":     7.0,   # Post-Miami default (qualifying)
    "harvest_limit_quali_min":    5.0,   # Absolute floor (Monza)

    # ICE
    "ice_power_kw":             400.0,
    "total_power_kw":           750.0,

    # Car
    "car_mass_kg":              805.0,   # 768 (car+driver) + ~30 (tyres) + ~7 (fuel, quali)

    # Overtake Mode
    "overtake_mode_extra_harvest_mj": 0.5,
}

SESSION_CONTEXTS = {
    "Q":  {"fuel_kg": 3,  "car_mass_adj": 0,  "tyre_context": "soft"},
    "SQ": {"fuel_kg": 3,  "car_mass_adj": 0,  "tyre_context": "soft_q3_medium_q1q2"},
    "S":  {"fuel_kg": 30, "car_mass_adj": 25, "tyre_context": "mixed"},
    "R":  {"fuel_kg": 95, "car_mass_adj": 90, "tyre_context": "mixed"},
}

# ─────────────────────────────────────────────────────────
#  REGULATION EPOCHS
#  Used to tag fingerprints and gate predictor blending.
#  Rule changes create structural breaks in the data.
# ─────────────────────────────────────────────────────────

REGULATION_EPOCHS = {
    "A_pre_miami": {
        "rounds":      range(1, 4),    # R1–R3: Australia, China, Japan
        "description": "Original 2026 rules: 8.5MJ baseline all sessions, "
                       "250kW superclip ceiling. Mercedes compression trick active.",
        "harvest_race_default":  8.5,
        "harvest_quali_default": None,   # Per-circuit only — no universal quali limit R1-R3
        "superclip_kw":          250.0,
        "mercedes_advantage":    True,
    },
    "B_miami_canada": {
        "rounds":      range(4, 6),    # R4–R5: Miami, Canada
        "description": "Miami rule set: per-circuit quali harvest limits (5–9MJ), "
                       "superclip raised to 350kW. Mercedes compression trick still active.",
        "harvest_race_default":  8.5,
        "harvest_quali_default": 7.0,
        "superclip_kw":          350.0,
        "mercedes_advantage":    True,
    },
    "C_post_monaco": {
        "rounds":      range(6, 99),   # R6+: Monaco onwards
        "description": "Compression ratio hot-test rule in effect (1 June 2026). "
                       "Mercedes loophole closed. Level ICE playing field.",
        "harvest_race_default":  8.5,
        "harvest_quali_default": 7.0,
        "superclip_kw":          350.0,
        "mercedes_advantage":    False,
    },
}


def regulation_epoch_for_round(race_round: int) -> str:
    """Return the regulation epoch string for a given race round."""
    if race_round <= 3:
        return "A_pre_miami"
    elif race_round <= 5:
        return "B_miami_canada"
    else:
        return "C_post_monaco"


# ─────────────────────────────────────────────────────────
#  KNOWN REGULATION CHANGES
# ─────────────────────────────────────────────────────────

UPCOMING_REG_CHANGES = [
    {
        "effective_from_race":  6,          # Monaco GP (round 6)
        "description":          "Compression ratio hot-test rule closes Mercedes loophole "
                                "(FIA Article C5.4.3 amended; measured at 130°C from 1 June 2026)",
        "changes":              {},
        "note": "No parameter change in REGS — fingerprint layer absorbs the performance "
                "delta from race data. Mercedes/customer pace should normalise post-Monaco.",
    },
    {
        "effective_from_race":  4,          # Miami GP (round 4)
        "description":          "Miami rule package: per-circuit qualifying harvest limits "
                                "formalised; superclip ceiling raised from 250kW to 350kW; "
                                "Overtake Mode boost active",
        "changes": {
            "mgu_k_max_harvest_kw": 350.0,  # Was 250kW R1-R3
        },
        "note": "REGS already reflect post-Miami state. R1-R3 fingerprints used 250kW "
                "superclip ceiling — epoch field on CarFingerprint flags this.",
    },
]

# ─────────────────────────────────────────────────────────
#  CIRCUIT DEFINITIONS — 2026 SEASON
#
#  harvest_limit_race_mj:  FIA-mandated race harvest ceiling (MJ/lap)
#  harvest_limit_quali_mj: FIA-mandated qualifying harvest ceiling (MJ/lap)
#
#  Sources:
#    R1 Australia quali:  7.0  — autosport 5 Mar 2026 (confirmed)
#    R2 China quali:      9.0  — motorsport.com Monaco article ("same value as China")
#    R3 Japan quali:      8.5  — pre-Miami regime, one-off superclip rate cut only
#    R4+ from The Race energy rankings (May 2026, confirmed per-event where noted)
# ─────────────────────────────────────────────────────────

CIRCUITS = {
    "Australia": {
        "fastf1_name":           "Australian Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 1,    "country": "Australia",
        "lap_length_km":         5.278, "circuit_type": "balanced",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":7.0,   # Confirmed: autosport 5 Mar 2026
        "full_throttle_pct":     0.58,
        "top_speed_kph":         315,  "key_straights": 1,
        "heavy_braking_zones":   4,    "has_sprint": False,
        "straight_weight":       0.38, "braking_weight": 0.35, "corner_weight": 0.27,
        "altitude_m":  30,   "avg_temp_c": 22,
        "telemetry_available": True,
    },
    "China": {
        "fastf1_name":           "Chinese Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 2,    "country": "China",
        "lap_length_km":         5.451, "circuit_type": "power",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":9.0,   # Confirmed: motorsport.com Monaco GP article
        "full_throttle_pct":     0.62,
        "top_speed_kph":         328,  "key_straights": 2,
        "heavy_braking_zones":   3,    "has_sprint": True,
        "straight_weight":       0.50, "braking_weight": 0.30, "corner_weight": 0.20,
        "altitude_m":  5,    "avg_temp_c": 15,
        "telemetry_available": True,
    },
    "Japan": {
        "fastf1_name":           "Japanese Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 3,    "country": "Japan",
        "lap_length_km":         5.807, "circuit_type": "high_speed",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":8.5,   # Pre-Miami regime; FIA made one-off superclip RATE cut
        "full_throttle_pct":     0.68,  # not harvest cap change
        "top_speed_kph":         291,  "key_straights": 2,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "straight_weight":       0.32, "braking_weight": 0.28, "corner_weight": 0.40,
        "altitude_m":  50,   "avg_temp_c": 18,
        "telemetry_available": True,
    },
    "Miami": {
        "fastf1_name":           "Miami Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 4,    "country": "USA",
        "lap_length_km":         5.412, "circuit_type": "power",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":8.0,   # The Race energy rankings (May 2026)
        "full_throttle_pct":     0.62,
        "top_speed_kph":         320,  "key_straights": 2,
        "heavy_braking_zones":   3,    "has_sprint": True,
        "straight_weight":       0.50, "braking_weight": 0.28, "corner_weight": 0.22,
        "altitude_m":  2,    "avg_temp_c": 30,
        "telemetry_available": False,
    },
    "Canada": {
        "fastf1_name":           "Canadian Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 5,    "country": "Canada",   # R5, not R6
        "lap_length_km":         4.361, "circuit_type": "power",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":6.0,   # Confirmed: The Race Canada article
        "full_throttle_pct":     0.60,
        "top_speed_kph":         325,  "key_straights": 2,
        "heavy_braking_zones":   4,    "has_sprint": True,
        "straight_weight":       0.48, "braking_weight": 0.32, "corner_weight": 0.20,
        "altitude_m":  20,   "avg_temp_c": 20,
        "telemetry_available": False,
    },
    "Monaco": {
        "fastf1_name":           "Monaco Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 6,    "country": "Monaco",   # R6, not R5
        "lap_length_km":         3.337, "circuit_type": "technical",
        "harvest_limit_race_mj": 9.0,  # Confirmed: 9MJ with Overtake Mode (RaceFans)
        "harvest_limit_quali_mj":9.0,  # Confirmed: RaceFans, motorsport.com
        "full_throttle_pct":     0.35,
        "top_speed_kph":         290,  "key_straights": 1,
        "heavy_braking_zones":   6,    "has_sprint": False,
        "straight_weight":       0.18, "braking_weight": 0.48, "corner_weight": 0.34,
        "altitude_m":  10,   "avg_temp_c": 20,
        "telemetry_available": False,
        "note": "Rev 1 power mode: MGU-K tapers from 200kph (not 290kph); "
                "no battery deployment above 300kph. Compression rule active.",
    },
    "Spain": {
        "fastf1_name":           "Barcelona Grand Prix",  # Barcelona-Catalunya R7
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 7,    "country": "Spain",
        "lap_length_km":         4.675, "circuit_type": "balanced",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":7.0,  # The Race energy rankings
        "full_throttle_pct":     0.60,
        "top_speed_kph":         315,  "key_straights": 1,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "straight_weight":       0.38, "braking_weight": 0.32, "corner_weight": 0.30,
        "altitude_m":  100,  "avg_temp_c": 22,
        "telemetry_available": False,
    },
    "Austria": {
        "fastf1_name":           "Austrian Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 8,    "country": "Austria",
        "lap_length_km":         4.318, "circuit_type": "high_speed",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":6.0,  # The Race energy rankings
        "full_throttle_pct":     0.67,
        "top_speed_kph":         310,  "key_straights": 1,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "straight_weight":       0.35, "braking_weight": 0.28, "corner_weight": 0.37,
        "altitude_m":  660,  "avg_temp_c": 18,
        "telemetry_available": False,
    },
    "Britain": {
        "fastf1_name":           "British Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 9,    "country": "UK",
        "lap_length_km":         5.891, "circuit_type": "high_speed",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":7.5,  # The Race energy rankings
        "full_throttle_pct":     0.64,
        "top_speed_kph":         318,  "key_straights": 1,
        "heavy_braking_zones":   3,    "has_sprint": True,
        "straight_weight":       0.35, "braking_weight": 0.28, "corner_weight": 0.37,
        "altitude_m":  80,   "avg_temp_c": 18,
        "telemetry_available": False,
    },
    "Belgium": {
        "fastf1_name":           "Belgian Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 10,   "country": "Belgium",
        "lap_length_km":         7.004, "circuit_type": "power",
        "harvest_limit_race_mj": 8.5,  # Confirmed: F1livepulse "race limit rises to 8.5MJ"
        "harvest_limit_quali_mj":7.0,  # Confirmed: f1livepulse "reduced from planned 8MJ to 7MJ"
        "full_throttle_pct":     0.64,
        "top_speed_kph":         335,  "key_straights": 2,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "straight_weight":       0.50, "braking_weight": 0.28, "corner_weight": 0.22,
        "altitude_m":  400,  "avg_temp_c": 15,
        "telemetry_available": False,
        "note": "Five active-aero straight-line-mode zones. "
                "Severe clipping expected: cars lose 30-50kph when battery depletes.",
    },
    "Hungary": {
        "fastf1_name":           "Hungarian Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 11,   "country": "Hungary",
        "lap_length_km":         4.381, "circuit_type": "technical",
        "harvest_limit_race_mj": 9.0,  # Energy-rich: Raceteq "Monaco and Hungary" at 9MJ
        "harvest_limit_quali_mj":9.0,  # The Race energy rankings + Raceteq confirmed
        "full_throttle_pct":     0.45,
        "top_speed_kph":         295,  "key_straights": 1,
        "heavy_braking_zones":   5,    "has_sprint": False,
        "straight_weight":       0.22, "braking_weight": 0.43, "corner_weight": 0.35,
        "altitude_m":  200,  "avg_temp_c": 28,
        "telemetry_available": False,
    },
    "Netherlands": {
        "fastf1_name":           "Dutch Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 12,   "country": "Netherlands",
        "lap_length_km":         4.259, "circuit_type": "high_speed",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":7.5,  # The Race energy rankings
        "full_throttle_pct":     0.58,
        "top_speed_kph":         305,  "key_straights": 1,
        "heavy_braking_zones":   3,    "has_sprint": True,
        "straight_weight":       0.33, "braking_weight": 0.30, "corner_weight": 0.37,
        "altitude_m":  5,    "avg_temp_c": 18,
        "telemetry_available": False,
    },
    "Italy": {
        "fastf1_name":           "Italian Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 13,   "country": "Italy",
        "lap_length_km":         5.793, "circuit_type": "power",
        "harvest_limit_race_mj": 5.0,  # Confirmed: Monza — energy-starved minimum
        "harvest_limit_quali_mj":5.0,  # Confirmed: multiple sources (Piastri "Spa and Monza are going to be sad")
        "full_throttle_pct":     0.72,
        "top_speed_kph":         350,  "key_straights": 2,
        "heavy_braking_zones":   2,    "has_sprint": False,
        "straight_weight":       0.60, "braking_weight": 0.25, "corner_weight": 0.15,
        "altitude_m":  160,  "avg_temp_c": 22,
        "telemetry_available": False,
        "note": "Lowest harvest limit on calendar. Almost no deployment on long straights. "
                "Extreme superclipping expected.",
    },
    "Madrid": {
        "fastf1_name":           "Spanish Grand Prix",  # Madring R14 — inherited name in FastF1
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 14,   "country": "Spain",
        "lap_length_km":         5.47, "circuit_type": "balanced",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":8.0,  # The Race: "Spain" = 8MJ (Madring, separate from Barcelona)
        "full_throttle_pct":     0.58,
        "top_speed_kph":         310,  "key_straights": 2,
        "heavy_braking_zones":   4,    "has_sprint": False,
        "straight_weight":       0.38, "braking_weight": 0.34, "corner_weight": 0.28,
        "altitude_m":  600,  "avg_temp_c": 25,
        "telemetry_available": False,
        "note": "New circuit — all aero/harvest values estimated; update after first race.",
    },
    "Azerbaijan": {
        "fastf1_name":           "Azerbaijan Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 15,   "country": "Azerbaijan",
        "lap_length_km":         6.003, "circuit_type": "power",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":8.5,  # The Race energy rankings
        "full_throttle_pct":     0.63,
        "top_speed_kph":         345,  "key_straights": 1,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "altitude_m":  0,    "avg_temp_c": 22,
        "straight_weight":       0.55, "braking_weight": 0.28, "corner_weight": 0.17,
        "telemetry_available": False,
        "note": "Saturday race format in 2026.",
    },
    "Singapore": {
        "fastf1_name":           "Singapore Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 16,   "country": "Singapore",
        "lap_length_km":         4.940, "circuit_type": "technical",
        "harvest_limit_race_mj": 9.0,  # Energy-rich — same bracket as Monaco/Hungary
        "harvest_limit_quali_mj":9.0,  # The Race energy rankings
        "full_throttle_pct":     0.38,
        "top_speed_kph":         295,  "key_straights": 2,
        "heavy_braking_zones":   7,    "has_sprint": True,
        "altitude_m":  10,   "avg_temp_c": 32,
        "straight_weight":       0.20, "braking_weight": 0.46, "corner_weight": 0.34,
        "telemetry_available": False,
    },
    "USA": {
        "fastf1_name":           "United States Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 17,   "country": "USA",
        "lap_length_km":         5.513, "circuit_type": "balanced",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":8.0,  # The Race energy rankings
        "full_throttle_pct":     0.58,
        "top_speed_kph":         318,  "key_straights": 1,
        "heavy_braking_zones":   4,    "has_sprint": False,
        "altitude_m":  220,  "avg_temp_c": 25,
        "straight_weight":       0.38, "braking_weight": 0.33, "corner_weight": 0.29,
        "telemetry_available": False,
    },
    "Mexico": {
        "fastf1_name":           "Mexico City Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 18,   "country": "Mexico",
        "lap_length_km":         4.304, "circuit_type": "power",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":8.5,  # The Race energy rankings
        "full_throttle_pct":     0.63,
        "top_speed_kph":         360,  "key_straights": 1,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "altitude_m":  2285, "avg_temp_c": 20,
        "straight_weight":       0.52, "braking_weight": 0.28, "corner_weight": 0.20,
        "telemetry_available": False,
        "note": "High altitude — lower air density increases top speed, reduces aero harvest.",
    },
    "Brazil": {
        "fastf1_name":           "São Paulo Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 19,   "country": "Brazil",
        "lap_length_km":         4.309, "circuit_type": "balanced",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":6.5,  # The Race energy rankings
        "full_throttle_pct":     0.60,
        "top_speed_kph":         315,  "key_straights": 1,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "altitude_m":  800,  "avg_temp_c": 22,
        "straight_weight":       0.40, "braking_weight": 0.32, "corner_weight": 0.28,
        "telemetry_available": False,
    },
    "LasVegas": {
        "fastf1_name":           "Las Vegas Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 20,   "country": "USA",
        "lap_length_km":         6.201, "circuit_type": "power",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":6.0,  # The Race energy rankings
        "full_throttle_pct":     0.65,
        "top_speed_kph":         342,  "key_straights": 3,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "altitude_m":  610,  "avg_temp_c": 15,
        "straight_weight":       0.55, "braking_weight": 0.27, "corner_weight": 0.18,
        "telemetry_available": False,
    },
    "Qatar": {
        "fastf1_name":           "Qatar Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 21,   "country": "Qatar",
        "lap_length_km":         5.380, "circuit_type": "high_speed",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":8.0,  # The Race energy rankings
        "full_throttle_pct":     0.65,
        "top_speed_kph":         318,  "key_straights": 1,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "altitude_m":  10,   "avg_temp_c": 30,
        "straight_weight":       0.38, "braking_weight": 0.28, "corner_weight": 0.34,
        "telemetry_available": False,
    },
    "AbuDhabi": {
        "fastf1_name":           "Abu Dhabi Grand Prix",
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 22,   "country": "UAE",
        "lap_length_km":         5.281, "circuit_type": "balanced",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":7.0,  # The Race energy rankings
        "full_throttle_pct":     0.60,
        "top_speed_kph":         315,  "key_straights": 2,
        "heavy_braking_zones":   3,    "has_sprint": False,
        "altitude_m":  5,    "avg_temp_c": 30,
        "straight_weight":       0.40, "braking_weight": 0.30, "corner_weight": 0.30,
        "telemetry_available": False,
    },
    "Malaysia": {
        "fastf1_name":           "Malaysian Grand Prix",   # Reinstated Bahrain GP at Sepang
        "fastf1_year":           2026, "fastf1_session": "Q",
        "round":                 23,   "country": "Malaysia",
        "lap_length_km":         5.543, "circuit_type": "balanced",
        "harvest_limit_race_mj": 8.5,
        "harvest_limit_quali_mj":7.5,  # Estimate — Sepang is moderate harvest opportunity
        "full_throttle_pct":     0.55,
        "top_speed_kph":         320,  "key_straights": 2,
        "heavy_braking_zones":   4,    "has_sprint": False,
        "altitude_m":  10,   "avg_temp_c": 32,
        "straight_weight":       0.42, "braking_weight": 0.32, "corner_weight": 0.26,
        "telemetry_available": False,
        "note": "Reinstated Bahrain GP moved to Sepang; pending final FIA sign-off. "
                "Harvest estimate only — update when FIA confirms.",
    },
}

# ─────────────────────────────────────────────────────────
#  CIRCUIT TAXONOMY
# ─────────────────────────────────────────────────────────

CIRCUIT_TYPES = {
    "power": {
        "description":        "Long straights, high top speed, moderate braking",
        "examples":           ["China", "Belgium", "Italy", "Miami"],
        "straight_weight":    0.55,
        "braking_weight":     0.25,
        "corner_weight":      0.20,
        "harvest_difficulty": "medium",
        "pu_sensitivity":     "high",
    },
    "balanced": {
        "description":        "Mix of straights and technical sections",
        "examples":           ["Australia", "Canada", "Spain", "Brazil"],
        "straight_weight":    0.38,
        "braking_weight":     0.32,
        "corner_weight":      0.30,
        "harvest_difficulty": "medium",
        "pu_sensitivity":     "medium",
    },
    "high_speed": {
        "description":        "Fast flowing corners, sustained high speed",
        "examples":           ["Japan", "Britain", "Netherlands"],
        "straight_weight":    0.35,
        "braking_weight":     0.28,
        "corner_weight":      0.37,
        "harvest_difficulty": "hard",
        "pu_sensitivity":     "medium",
    },
    "technical": {
        "description":        "Many corners, short straights, heavy braking",
        "examples":           ["Monaco", "Hungary", "Singapore"],
        "straight_weight":    0.20,
        "braking_weight":     0.45,
        "corner_weight":      0.35,
        "harvest_difficulty": "easy",
        "pu_sensitivity":     "low",
    },
}

# ─────────────────────────────────────────────────────────
#  2026 GRID — driver → team / PU mapping
#  ADUO ICE benchmark ranking (confirmed Monaco weekend):
#    1. RedBullFord (benchmark — no ADUO upgrade)
#    2. Mercedes    (>2% behind → 1 upgrade)
#    3. Ferrari     (>4% behind → 2 upgrades)
#    4. Audi        (>4% behind → 2 upgrades)
#    5. Honda       (>4% behind → 2 upgrades; worst PU)
# ─────────────────────────────────────────────────────────

CARS = {
    # Mercedes PU
    "RUS": {"team": "Mercedes",      "pu": "Mercedes",    "fastf1_code": "RUS",
            "name": "George Russell",            "number": 63},
    "ANT": {"team": "Mercedes",      "pu": "Mercedes",    "fastf1_code": "ANT",
            "name": "Andrea Kimi Antonelli",     "number": 12},
    "NOR": {"team": "McLaren",       "pu": "Mercedes",    "fastf1_code": "NOR",
            "name": "Lando Norris",              "number": 1},
    "PIA": {"team": "McLaren",       "pu": "Mercedes",    "fastf1_code": "PIA",
            "name": "Oscar Piastri",             "number": 81},
    "ALB": {"team": "Williams",      "pu": "Mercedes",    "fastf1_code": "ALB",
            "name": "Alexander Albon",           "number": 23},
    "SAI": {"team": "Williams",      "pu": "Mercedes",    "fastf1_code": "SAI",
            "name": "Carlos Sainz",              "number": 55},
    "GAS": {"team": "Alpine",        "pu": "Mercedes",    "fastf1_code": "GAS",
            "name": "Pierre Gasly",              "number": 10},
    "COL": {"team": "Alpine",        "pu": "Mercedes",    "fastf1_code": "COL",
            "name": "Franco Colapinto",          "number": 43},
    # Ferrari PU
    "LEC": {"team": "Ferrari",       "pu": "Ferrari",     "fastf1_code": "LEC",
            "name": "Charles Leclerc",           "number": 16},
    "HAM": {"team": "Ferrari",       "pu": "Ferrari",     "fastf1_code": "HAM",
            "name": "Lewis Hamilton",            "number": 44},
    "BEA": {"team": "Haas",          "pu": "Ferrari",     "fastf1_code": "BEA",
            "name": "Oliver Bearman",            "number": 87},
    "OCO": {"team": "Haas",          "pu": "Ferrari",     "fastf1_code": "OCO",
            "name": "Esteban Ocon",              "number": 31},
    "PER": {"team": "Cadillac",      "pu": "Ferrari",     "fastf1_code": "PER",
            "name": "Sergio Perez",              "number": 11},
    "BOT": {"team": "Cadillac",      "pu": "Ferrari",     "fastf1_code": "BOT",
            "name": "Valtteri Bottas",           "number": 77},
    # Red Bull Ford PU — ADUO benchmark ICE (best ICE, poor chassis)
    "VER": {"team": "Red Bull",      "pu": "RedBullFord", "fastf1_code": "VER",
            "name": "Max Verstappen",            "number": 3},
    "HAD": {"team": "Red Bull",      "pu": "RedBullFord", "fastf1_code": "HAD",
            "name": "Isack Hadjar",              "number": 6},
    "LIN": {"team": "VCARB",         "pu": "RedBullFord", "fastf1_code": "LIN",
            "name": "Arvid Lindblad",            "number": 41},
    "LAW": {"team": "VCARB",         "pu": "RedBullFord", "fastf1_code": "LAW",
            "name": "Liam Lawson",               "number": 30},
    # Honda PU — worst performing PU on grid; 2 ADUO upgrades allocated
    "ALO": {"team": "Aston Martin",  "pu": "Honda",       "fastf1_code": "ALO",
            "name": "Fernando Alonso",           "number": 14},
    "STR": {"team": "Aston Martin",  "pu": "Honda",       "fastf1_code": "STR",
            "name": "Lance Stroll",              "number": 18},
    # Audi PU — debut season; 2 ADUO upgrades allocated
    "HUL": {"team": "Audi",          "pu": "Audi",        "fastf1_code": "HUL",
            "name": "Nico Hulkenberg",           "number": 27},
    "BOR": {"team": "Audi",          "pu": "Audi",        "fastf1_code": "BOR",
            "name": "Gabriel Bortoleto",         "number": 5},
}

PU_GROUPS = {
    "Mercedes":    ["RUS", "ANT", "NOR", "PIA", "ALB", "SAI", "GAS", "COL"],
    "Ferrari":     ["LEC", "HAM", "BEA", "OCO", "PER", "BOT"],
    "RedBullFord": ["VER", "HAD", "LIN", "LAW"],
    "Honda":       ["ALO", "STR"],
    "Audi":        ["HUL", "BOR"],
}

CURRENT_YEAR = datetime.now().year

# ─────────────────────────────────────────────────────────
#  TEAM CHASSIS/AERO UPGRADE TRACKER — 2026
#
#  Separate from ADUO (which is PU-only).
#  These are chassis, aero, and suspension changes that
#  make pre-upgrade fingerprints unrepresentative.
#
#  significance levels:
#    "new_car"  — B-spec or equivalent redesign. Pre-upgrade
#                 fingerprints are from a different car. Weight ≈ 0.
#    "major"    — Large multi-part aero package. Meaningful
#                 performance step. Pre-upgrade weight = 0.40.
#    "medium"   — Notable update, part of ongoing programme.
#                 Pre-upgrade weight = 0.70.
#    "minor"    — Small refinement, minor step.
#                 Pre-upgrade weight = 0.90.
#
#  Sources: FIA technical lists, formula1.com upgrade tracker,
#           The Race, Sky Sports, motorsport.com (confirmed per round).
# ─────────────────────────────────────────────────────────

TEAM_UPGRADES = {
    # ── Top teams ──────────────────────────────────────────
    "Mercedes": [
        {"from_round": 5,  "significance": "major",
         "note": "Canada R5 — 8-part package (front wing, front corner, rear corner, floor). "
                 "First major upgrade of 2026, deliberately held back from Miami. "
                 "Source: Crash.net, F1.com confirmed parts list."},
        {"from_round": 8,  "significance": "minor",
         "note": "Austria R8 — front wing endplate top-edge camber, rear drum winglets, "
                 "Spa-specific rear wing. Source: F1.com upgrade tracker."},
    ],
    "Ferrari": [
        {"from_round": 4,  "significance": "major",
         "note": "Miami R4 — 11 parts (largest single package on grid): front wing endplate, "
                 "front deflector, front suspension fairings, floor, sidepods. "
                 "Source: RacingNews365, F1.com."},
        {"from_round": 9,  "significance": "minor",
         "note": "Silverstone R9 — rear corner: cooling inlet/outlet, lower deflector, "
                 "rearward winglet cluster. Source: F1.com upgrade tracker."},
    ],
    "McLaren": [
        {"from_round": 4,  "significance": "major",
         "note": "Miami R4 — 7 parts: floor, front aero overhaul. NOR sprint pole — "
                 "first non-Mercedes pole of 2026. Car was 2-3 months behind rivals before this. "
                 "Source: Sky Sports, F1.com."},
        {"from_round": 9,  "significance": "major",
         "note": "Silverstone R9 — led all teams on updates. NOR won race. "
                 "Stella confirmed further upgrades planned for Hungary. Source: F1.com, Crash.net."},
        {"from_round": 11, "significance": "medium",
         "note": "Hungary R11 — floor body + rear wing endplate. Part 1 of confirmed "
                 "2-part package. Part 2 lands Netherlands R12. Source: motorsport.com."},
    ],
    "Red Bull": [
        {"from_round": 4,  "significance": "major",
         "note": "Miami R4 — 7 parts: new rotating rear wing, floor architecture reset, "
                 "revised suspension geometries targeting tyre graining and rear instability. "
                 "Source: Sky Sports, RacingNews365."},
        {"from_round": 6,  "significance": "minor",
         "note": "Monaco R6 — front brake duct exits, engine cover + sidepod cooling, "
                 "rear wing extensions. Source: The Race, F1.com."},
    ],
    "Aston Martin": [
        {"from_round": 11, "significance": "new_car",
         "note": "Hungary R11 — 16-part B-spec overhaul: new nose + front wing package, "
                 "front brake duct shaping, ALL permitted floor surfaces + leading edge vanes "
                 "+ floor edge, rear wing. R1-R10 fingerprints are from a different car. "
                 "Source: The Race (confirmed), GPblog."},
    ],
    # ── Midfield teams ─────────────────────────────────────
    "VCARB": [
        {"from_round": 4,  "significance": "medium",
         "note": "Miami R4 — 6 enhancements: sidepods, engine cover, mid-section, both wings. "
                 "First significant development wave for the VCARB03. "
                 "Source: RacingNews365."},
        {"from_round": 5,  "significance": "medium",
         "note": "Canada R5 — larger package than Miami: floor update, rear corner devices "
                 "reprofiled, beam wing modifications. Source: F1.com confirmed parts list."},
        {"from_round": 6,  "significance": "minor",
         "note": "Monaco R6 — front suspension tweak, rear wing flap and central winglet. "
                 "Source: The Race."},
    ],
    "Haas": [
        {"from_round": 5,  "significance": "medium",
         "note": "Canada R5 — first significant 2026 package. Team split it between Bearman "
                 "and Ocon across the sprint weekend. Bearman: 'chasing our tails all weekend.' "
                 "Source: Crash.net, Pit Debrief."},
        {"from_round": 8,  "significance": "minor",
         "note": "Austria R8 — cooling louvres (2 apertures, upper sidepod surface), "
                 "front brake duct revision. Circuit-specific. Source: F1.com."},
        {"from_round": 10, "significance": "major",
         "note": "Belgium R10 — 4 upgrades, 2 non-circuit-specific: heavily revised front wing "
                 "(new endplates, pylon geometry, distinctive J-shaped nose assembly), "
                 "lower-drag rear wing. Described by The Race as 'unique development.' "
                 "Source: The Race, fervogear.com."},
    ],
    "Alpine": [
        {"from_round": 4,  "significance": "minor",
         "note": "Miami R4 — front corner update, nose camera mounts, rear suspension reprofiled, "
                 "additional element to rear impact structure. GAS: new rear wing. "
                 "COL: new chassis. Source: RacingNews365."},
        {"from_round": 5,  "significance": "minor",
         "note": "Canada R5 — 'noticeably bigger package than Miami.' Source: carhp.in."},
        {"from_round": 7,  "significance": "minor",
         "note": "Barcelona R7 — front corner update, sidepod cooling louvres (upper surface), "
                 "SLM actuator fairing on rear wing. Source: F1.com confirmed parts list."},
    ],
    "Williams": [
        {"from_round": 4,  "significance": "major",
         "note": "Miami R4 — first major 2026 package: floor, bodywork, front wing, rear "
                 "suspension, exhaust blowing, weight reduction. Immediate double-points finish. "
                 "Vowles: 'more performance coming for Montreal.' Source: Crash.net, Vowles quotes."},
        {"from_round": 5,  "significance": "medium",
         "note": "Canada R5 — FBD geometry (brake cooling), suspension cladding, "
                 "tailpipe repositioning, enhanced Miami exhaust upgrade. Source: F1.com."},
        {"from_round": 9,  "significance": "medium",
         "note": "Silverstone R9 — Vowles confirmed to Sky Sports Germany: "
                 "updates coming for British GP following Austria struggle. Source: Crash.net."},
        {"from_round": 12, "significance": "medium",
         "note": "Netherlands R12 — weight reduction package. Vowles: 'almost a completely "
                 "new car' by Baku. Source: Crash.net interview."},
    ],
    "Audi": [
        {"from_round": 4,  "significance": "medium",
         "note": "Miami R4 — reworked front suspension, floor edge, diffuser. "
                 "Debut team's first significant development step. Source: RacingNews365."},
        {"from_round": 7,  "significance": "minor",
         "note": "Barcelona R7 — sidepod cooling louvres, rear wing SLM actuator fairing. "
                 "Source: F1.com confirmed parts list."},
    ],
    "Cadillac": [
        {"from_round": 4,  "significance": "major",
         "note": "Miami R4 — 9 upgrades targeting performance and ride height sensitivities. "
                 "Debut team's first comprehensive development push. Source: RacingNews365."},
        {"from_round": 10, "significance": "minor",
         "note": "Belgium R10 — front wing footplate revision, added horizontal endplate vane. "
                 "Source: The Race confirmed parts list."},
    ],
}

# Known upgrades arriving AT a specific future round.
KNOWN_UPCOMING_UPGRADES = {
    "Aston Martin": [
        {"at_round": 12, "significance": "major",
         "note": "Netherlands R12 — second major chassis package confirmed. "
                 "Honda PU ADUO upgrade also due within 2 races of Belgium (R10): "
                 "expect at R12 or R13. Source: GPblog, Honda Orihara quote."},
    ],
    "McLaren": [
        {"at_round": 12, "significance": "medium",
         "note": "Netherlands R12 — part 2 of Hungary 2-part development package. "
                 "Stella: 'next upgrades in Hungary and then after the shutdown.' "
                 "Source: motorsport.com."},
    ],
    "Honda": [
        {"at_round": 12, "significance": "major",
         "note": "PU ADUO upgrade expected at R12 Netherlands or R13 Italy. "
                 "Honda trackside GM Orihara: 'two more races' from Belgium (R10). "
                 "Source: GPblog confirmed."},
    ],
    "Williams": [
        {"at_round": 12, "significance": "medium",
         "note": "Netherlands R12 — confirmed weight reduction package. Source: Crash.net."},
    ],
}
