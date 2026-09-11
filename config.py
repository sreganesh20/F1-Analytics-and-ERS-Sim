"""config.py — ERS Optimizer / LatentLap core configuration.

2026 regulation constants, circuit taxonomy, driver/PU mapping, round-specific
lineups/penalties, PU ADUO state, and compatibility views over the canonical
chassis/aero upgrade history.

Design principle: the physics layer uses regulation/engineering assumptions;
car characteristics are derived from observations rather than silently invented.
"""

from datetime import datetime

from data.upgrade_history import legacy_team_upgrades, legacy_upcoming_upgrades

# ─────────────────────────────────────────────────────────
#  2026 REGULATION CONSTANTS
# ─────────────────────────────────────────────────────────
REGS = {
    "mgu_k_max_deploy_kw": 350.0,
    "mgu_k_max_harvest_kw": 350.0,
    "deploy_ramp_kw_per_s": 50.0,
    "deploy_taper_speed_kph": 290.0,
    "battery_capacity_mj": 4.0,
    "battery_min_mj": 0.0,
    "harvest_limit_race_mj": 8.5,
    "harvest_limit_quali_mj": 7.0,
    "harvest_limit_quali_min": 5.0,
    "ice_power_kw": 400.0,
    "total_power_kw": 750.0,
    "car_mass_kg": 805.0,
    "overtake_mode_extra_harvest_mj": 0.5,
}

SESSION_CONTEXTS = {
    "Q":  {"fuel_kg": 3,  "car_mass_adj": 0,  "tyre_context": "soft"},
    "SQ": {"fuel_kg": 3,  "car_mass_adj": 0,  "tyre_context": "soft_q3_medium_q1q2"},
    "S":  {"fuel_kg": 30, "car_mass_adj": 25, "tyre_context": "mixed"},
    "R":  {"fuel_kg": 95, "car_mass_adj": 90, "tyre_context": "mixed"},
}

REGULATION_EPOCHS = {
    "A_pre_miami": {
        "rounds": range(1, 4),
        "description": "Original 2026 rules: 8.5MJ baseline all sessions, 250kW superclip ceiling. Mercedes compression trick active.",
        "harvest_race_default": 8.5,
        "harvest_quali_default": None,
        "superclip_kw": 250.0,
        "mercedes_advantage": True,
    },
    "B_miami_canada": {
        "rounds": range(4, 6),
        "description": "Miami rule set: per-circuit quali harvest limits (5–9MJ), superclip raised to 350kW. Mercedes compression trick still active.",
        "harvest_race_default": 8.5,
        "harvest_quali_default": 7.0,
        "superclip_kw": 350.0,
        "mercedes_advantage": True,
    },
    "C_post_monaco": {
        "rounds": range(6, 99),
        "description": "Compression ratio hot-test rule in effect (1 June 2026). Mercedes loophole closed. Level ICE playing field.",
        "harvest_race_default": 8.5,
        "harvest_quali_default": 7.0,
        "superclip_kw": 350.0,
        "mercedes_advantage": False,
    },
}


def regulation_epoch_for_round(race_round: int) -> str:
    if race_round <= 3:
        return "A_pre_miami"
    if race_round <= 5:
        return "B_miami_canada"
    return "C_post_monaco"


UPCOMING_REG_CHANGES = [
    {
        "effective_from_race": 6,
        "description": "Compression ratio hot-test rule closes Mercedes loophole (FIA Article C5.4.3 amended; measured at 130°C from 1 June 2026)",
        "changes": {},
        "note": "No parameter change in REGS — fingerprint layer absorbs the performance delta from race data. Mercedes/customer pace should normalise post-Monaco.",
    },
    {
        "effective_from_race": 4,
        "description": "Miami rule package: per-circuit qualifying harvest limits formalised; superclip ceiling raised from 250kW to 350kW; Overtake Mode boost active",
        "changes": {"mgu_k_max_harvest_kw": 350.0},
        "note": "REGS already reflect post-Miami state. R1-R3 fingerprints used 250kW superclip ceiling — epoch field on CarFingerprint flags this.",
    },
]

# ─────────────────────────────────────────────────────────
#  CIRCUIT DEFINITIONS — 2026 SEASON
# ─────────────────────────────────────────────────────────
CIRCUITS = {
    "Australia": {"fastf1_name":"Australian Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":1,"country":"Australia","lap_length_km":5.278,"circuit_type":"balanced","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":7.0,"full_throttle_pct":0.58,"top_speed_kph":315,"key_straights":1,"heavy_braking_zones":4,"has_sprint":False,"straight_weight":0.38,"braking_weight":0.35,"corner_weight":0.27,"altitude_m":30,"avg_temp_c":22,"telemetry_available":True},
    "China": {"fastf1_name":"Chinese Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":2,"country":"China","lap_length_km":5.451,"circuit_type":"power","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":9.0,"full_throttle_pct":0.62,"top_speed_kph":328,"key_straights":2,"heavy_braking_zones":3,"has_sprint":True,"straight_weight":0.50,"braking_weight":0.30,"corner_weight":0.20,"altitude_m":5,"avg_temp_c":15,"telemetry_available":True},
    "Japan": {"fastf1_name":"Japanese Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":3,"country":"Japan","lap_length_km":5.807,"circuit_type":"high_speed","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":8.5,"full_throttle_pct":0.68,"top_speed_kph":291,"key_straights":2,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.32,"braking_weight":0.28,"corner_weight":0.40,"altitude_m":50,"avg_temp_c":18,"telemetry_available":True},
    "Miami": {"fastf1_name":"Miami Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":4,"country":"USA","lap_length_km":5.412,"circuit_type":"power","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":8.0,"full_throttle_pct":0.62,"top_speed_kph":320,"key_straights":2,"heavy_braking_zones":3,"has_sprint":True,"straight_weight":0.50,"braking_weight":0.28,"corner_weight":0.22,"altitude_m":2,"avg_temp_c":30,"telemetry_available":False},
    "Canada": {"fastf1_name":"Canadian Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":5,"country":"Canada","lap_length_km":4.361,"circuit_type":"power","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":6.0,"full_throttle_pct":0.60,"top_speed_kph":325,"key_straights":2,"heavy_braking_zones":4,"has_sprint":True,"straight_weight":0.48,"braking_weight":0.32,"corner_weight":0.20,"altitude_m":20,"avg_temp_c":20,"telemetry_available":False},
    "Monaco": {"fastf1_name":"Monaco Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":6,"country":"Monaco","lap_length_km":3.337,"circuit_type":"technical","harvest_limit_race_mj":9.0,"harvest_limit_quali_mj":9.0,"full_throttle_pct":0.35,"top_speed_kph":290,"key_straights":1,"heavy_braking_zones":6,"has_sprint":False,"straight_weight":0.18,"braking_weight":0.48,"corner_weight":0.34,"altitude_m":10,"avg_temp_c":20,"telemetry_available":False,"note":"Rev 1 power mode: MGU-K tapers from 200kph (not 290kph); no battery deployment above 300kph. Compression rule active."},
    "Spain": {"fastf1_name":"Barcelona Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":7,"country":"Spain","lap_length_km":4.675,"circuit_type":"balanced","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":7.0,"full_throttle_pct":0.60,"top_speed_kph":315,"key_straights":1,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.38,"braking_weight":0.32,"corner_weight":0.30,"altitude_m":100,"avg_temp_c":22,"telemetry_available":False},
    "Austria": {"fastf1_name":"Austrian Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":8,"country":"Austria","lap_length_km":4.318,"circuit_type":"high_speed","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":6.0,"full_throttle_pct":0.67,"top_speed_kph":310,"key_straights":1,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.35,"braking_weight":0.28,"corner_weight":0.37,"altitude_m":660,"avg_temp_c":18,"telemetry_available":False},
    "Britain": {"fastf1_name":"British Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":9,"country":"UK","lap_length_km":5.891,"circuit_type":"high_speed","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":7.5,"full_throttle_pct":0.64,"top_speed_kph":318,"key_straights":1,"heavy_braking_zones":3,"has_sprint":True,"straight_weight":0.35,"braking_weight":0.28,"corner_weight":0.37,"altitude_m":80,"avg_temp_c":18,"telemetry_available":False},
    "Belgium": {"fastf1_name":"Belgian Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":10,"country":"Belgium","lap_length_km":7.004,"circuit_type":"power","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":7.0,"full_throttle_pct":0.64,"top_speed_kph":335,"key_straights":2,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.50,"braking_weight":0.28,"corner_weight":0.22,"altitude_m":400,"avg_temp_c":15,"telemetry_available":False,"note":"Five active-aero straight-line-mode zones. Severe clipping expected: cars lose 30-50kph when battery depletes."},
    "Hungary": {"fastf1_name":"Hungarian Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":11,"country":"Hungary","lap_length_km":4.381,"circuit_type":"technical","harvest_limit_race_mj":9.0,"harvest_limit_quali_mj":9.0,"full_throttle_pct":0.45,"top_speed_kph":295,"key_straights":1,"heavy_braking_zones":5,"has_sprint":False,"straight_weight":0.22,"braking_weight":0.43,"corner_weight":0.35,"altitude_m":200,"avg_temp_c":28,"telemetry_available":False},
    "Netherlands": {"fastf1_name":"Dutch Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":12,"country":"Netherlands","lap_length_km":4.259,"circuit_type":"high_speed","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":7.5,"full_throttle_pct":0.58,"top_speed_kph":305,"key_straights":1,"heavy_braking_zones":3,"has_sprint":True,"straight_weight":0.33,"braking_weight":0.30,"corner_weight":0.37,"altitude_m":5,"avg_temp_c":18,"telemetry_available":False},
    "Italy": {"fastf1_name":"Italian Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":13,"country":"Italy","lap_length_km":5.793,"circuit_type":"power","harvest_limit_race_mj":5.0,"harvest_limit_quali_mj":5.0,"full_throttle_pct":0.72,"top_speed_kph":350,"key_straights":2,"heavy_braking_zones":2,"has_sprint":False,"straight_weight":0.60,"braking_weight":0.25,"corner_weight":0.15,"altitude_m":160,"avg_temp_c":22,"telemetry_available":False,"note":"Lowest harvest limit on calendar. Almost no deployment on long straights. Extreme superclipping expected."},
    "Madrid": {"fastf1_name":"Spanish Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":14,"country":"Spain","lap_length_km":5.47,"circuit_type":"balanced","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":8.0,"full_throttle_pct":0.58,"top_speed_kph":310,"key_straights":2,"heavy_braking_zones":4,"has_sprint":False,"straight_weight":0.38,"braking_weight":0.34,"corner_weight":0.28,"altitude_m":600,"avg_temp_c":25,"telemetry_available":False,"note":"New circuit — all aero/harvest values estimated; update after first race."},
    "Azerbaijan": {"fastf1_name":"Azerbaijan Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":15,"country":"Azerbaijan","lap_length_km":6.003,"circuit_type":"power","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":8.5,"full_throttle_pct":0.63,"top_speed_kph":345,"key_straights":1,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.55,"braking_weight":0.28,"corner_weight":0.17,"altitude_m":0,"avg_temp_c":22,"telemetry_available":False,"note":"Saturday race format in 2026."},
    "Singapore": {"fastf1_name":"Singapore Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":16,"country":"Singapore","lap_length_km":4.940,"circuit_type":"technical","harvest_limit_race_mj":9.0,"harvest_limit_quali_mj":9.0,"full_throttle_pct":0.38,"top_speed_kph":295,"key_straights":2,"heavy_braking_zones":7,"has_sprint":True,"straight_weight":0.20,"braking_weight":0.46,"corner_weight":0.34,"altitude_m":10,"avg_temp_c":32,"telemetry_available":False},
    "USA": {"fastf1_name":"United States Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":17,"country":"USA","lap_length_km":5.513,"circuit_type":"balanced","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":8.0,"full_throttle_pct":0.58,"top_speed_kph":318,"key_straights":1,"heavy_braking_zones":4,"has_sprint":False,"straight_weight":0.38,"braking_weight":0.33,"corner_weight":0.29,"altitude_m":220,"avg_temp_c":25,"telemetry_available":False},
    "Mexico": {"fastf1_name":"Mexico City Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":18,"country":"Mexico","lap_length_km":4.304,"circuit_type":"power","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":8.5,"full_throttle_pct":0.63,"top_speed_kph":360,"key_straights":1,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.52,"braking_weight":0.28,"corner_weight":0.20,"altitude_m":2285,"avg_temp_c":20,"telemetry_available":False,"note":"High altitude — lower air density increases top speed, reduces aero harvest."},
    "Brazil": {"fastf1_name":"São Paulo Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":19,"country":"Brazil","lap_length_km":4.309,"circuit_type":"balanced","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":6.5,"full_throttle_pct":0.60,"top_speed_kph":315,"key_straights":1,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.40,"braking_weight":0.32,"corner_weight":0.28,"altitude_m":800,"avg_temp_c":22,"telemetry_available":False},
    "LasVegas": {"fastf1_name":"Las Vegas Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":20,"country":"USA","lap_length_km":6.201,"circuit_type":"power","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":6.0,"full_throttle_pct":0.65,"top_speed_kph":342,"key_straights":3,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.55,"braking_weight":0.27,"corner_weight":0.18,"altitude_m":610,"avg_temp_c":15,"telemetry_available":False},
    "Qatar": {"fastf1_name":"Qatar Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":21,"country":"Qatar","lap_length_km":5.380,"circuit_type":"high_speed","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":8.0,"full_throttle_pct":0.65,"top_speed_kph":318,"key_straights":1,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.38,"braking_weight":0.28,"corner_weight":0.34,"altitude_m":10,"avg_temp_c":30,"telemetry_available":False},
    "AbuDhabi": {"fastf1_name":"Abu Dhabi Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":22,"country":"UAE","lap_length_km":5.281,"circuit_type":"balanced","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":7.0,"full_throttle_pct":0.60,"top_speed_kph":315,"key_straights":2,"heavy_braking_zones":3,"has_sprint":False,"straight_weight":0.40,"braking_weight":0.30,"corner_weight":0.30,"altitude_m":5,"avg_temp_c":30,"telemetry_available":False},
    "Malaysia": {"fastf1_name":"Malaysian Grand Prix","fastf1_year":2026,"fastf1_session":"Q","round":23,"country":"Malaysia","lap_length_km":5.543,"circuit_type":"balanced","harvest_limit_race_mj":8.5,"harvest_limit_quali_mj":7.5,"full_throttle_pct":0.55,"top_speed_kph":320,"key_straights":2,"heavy_braking_zones":4,"has_sprint":False,"straight_weight":0.42,"braking_weight":0.32,"corner_weight":0.26,"altitude_m":10,"avg_temp_c":32,"telemetry_available":False,"note":"Reinstated Bahrain GP moved to Sepang; pending final FIA sign-off. Harvest estimate only — update when FIA confirms."},
}

CIRCUIT_TYPES = {
    "power": {"description":"Long straights, high top speed, moderate braking","examples":["China","Belgium","Italy","Miami"],"straight_weight":0.55,"braking_weight":0.25,"corner_weight":0.20,"harvest_difficulty":"medium","pu_sensitivity":"high"},
    "balanced": {"description":"Mix of straights and technical sections","examples":["Australia","Canada","Spain","Brazil"],"straight_weight":0.38,"braking_weight":0.32,"corner_weight":0.30,"harvest_difficulty":"medium","pu_sensitivity":"medium"},
    "high_speed": {"description":"Fast flowing corners, sustained high speed","examples":["Japan","Britain","Netherlands"],"straight_weight":0.35,"braking_weight":0.28,"corner_weight":0.37,"harvest_difficulty":"hard","pu_sensitivity":"medium"},
    "technical": {"description":"Many corners, short straights, heavy braking","examples":["Monaco","Hungary","Singapore"],"straight_weight":0.20,"braking_weight":0.45,"corner_weight":0.35,"harvest_difficulty":"easy","pu_sensitivity":"low"},
}

# ─────────────────────────────────────────────────────────
#  2026 GRID
# ─────────────────────────────────────────────────────────
CARS = {
    "RUS":{"team":"Mercedes","pu":"Mercedes","fastf1_code":"RUS","name":"George Russell","number":63},
    "ANT":{"team":"Mercedes","pu":"Mercedes","fastf1_code":"ANT","name":"Andrea Kimi Antonelli","number":12},
    "NOR":{"team":"McLaren","pu":"Mercedes","fastf1_code":"NOR","name":"Lando Norris","number":1},
    "PIA":{"team":"McLaren","pu":"Mercedes","fastf1_code":"PIA","name":"Oscar Piastri","number":81},
    "ALB":{"team":"Williams","pu":"Mercedes","fastf1_code":"ALB","name":"Alexander Albon","number":23},
    "SAI":{"team":"Williams","pu":"Mercedes","fastf1_code":"SAI","name":"Carlos Sainz","number":55},
    "GAS":{"team":"Alpine","pu":"Mercedes","fastf1_code":"GAS","name":"Pierre Gasly","number":10},
    "COL":{"team":"Alpine","pu":"Mercedes","fastf1_code":"COL","name":"Franco Colapinto","number":43},
    "LEC":{"team":"Ferrari","pu":"Ferrari","fastf1_code":"LEC","name":"Charles Leclerc","number":16},
    "HAM":{"team":"Ferrari","pu":"Ferrari","fastf1_code":"HAM","name":"Lewis Hamilton","number":44},
    "BEA":{"team":"Haas","pu":"Ferrari","fastf1_code":"BEA","name":"Oliver Bearman","number":87},
    "OCO":{"team":"Haas","pu":"Ferrari","fastf1_code":"OCO","name":"Esteban Ocon","number":31},
    "PER":{"team":"Cadillac","pu":"Ferrari","fastf1_code":"PER","name":"Sergio Perez","number":11},
    "BOT":{"team":"Cadillac","pu":"Ferrari","fastf1_code":"BOT","name":"Valtteri Bottas","number":77},
    "VER":{"team":"Red Bull","pu":"RedBullFord","fastf1_code":"VER","name":"Max Verstappen","number":3},
    "HAD":{"team":"Red Bull","pu":"RedBullFord","fastf1_code":"HAD","name":"Isack Hadjar","number":6},
    "LIN":{"team":"VCARB","pu":"RedBullFord","fastf1_code":"LIN","name":"Arvid Lindblad","number":41},
    "LAW":{"team":"VCARB","pu":"RedBullFord","fastf1_code":"LAW","name":"Liam Lawson","number":30},
    "ALO":{"team":"Aston Martin","pu":"Honda","fastf1_code":"ALO","name":"Fernando Alonso","number":14},
    "STR":{"team":"Aston Martin","pu":"Honda","fastf1_code":"STR","name":"Lance Stroll","number":18},
    "HUL":{"team":"Audi","pu":"Audi","fastf1_code":"HUL","name":"Nico Hulkenberg","number":27},
    "BOR":{"team":"Audi","pu":"Audi","fastf1_code":"BOR","name":"Gabriel Bortoleto","number":5},
}

PU_GROUPS = {
    "Mercedes":["RUS","ANT","NOR","PIA","ALB","SAI","GAS","COL"],
    "Ferrari":["LEC","HAM","BEA","OCO","PER","BOT"],
    "RedBullFord":["VER","HAD","LIN","LAW"],
    "Honda":["ALO","STR"],
    "Audi":["HUL","BOR"],
}

CURRENT_YEAR = datetime.now().year

# Canonical chassis/aero history lives in data/upgrade_history.py. These are
# compatibility views only; do not edit them independently.
TEAM_UPGRADES = legacy_team_upgrades()
KNOWN_UPCOMING_UPGRADES = legacy_upcoming_upgrades()

# ─────────────────────────────────────────────────────────
#  ROUND-SPECIFIC LINEUPS
# ─────────────────────────────────────────────────────────
ROUND_LINEUP_OVERRIDES = {
    12: {
        "LAW":{"team":"Red Bull"},
        "TSU":{"team":"VCARB","pu":"RedBullFord","fastf1_code":"TSU","name":"Yuki Tsunoda","number":22},
    },
    13: {
        "LAW":{"team":"Red Bull"},
        "TSU":{"team":"VCARB","pu":"RedBullFord","fastf1_code":"TSU","name":"Yuki Tsunoda","number":22},
    },
    14: {
        "LAW":{"team":"Red Bull"},
        "TSU":{"team":"VCARB","pu":"RedBullFord","fastf1_code":"TSU","name":"Yuki Tsunoda","number":22},
    },
}


def lineup_for_round(round_num: int) -> dict:
    """Return base driver metadata with round-specific assignments overlaid."""
    merged = {code: dict(car) for code, car in CARS.items()}
    for code, override in ROUND_LINEUP_OVERRIDES.get(round_num, {}).items():
        merged.setdefault(code, {}).update(override)
    return merged


# Display/context only. Predictions remain a pace ranking and are never reordered.
GRID_PENALTIES = {
    13: {
        "ANT": {
            "penalty":"Starts from the back",
            "note":"Complete new power unit beyond the season allowance; back-of-grid start.",
            "known_at_prediction_time": True,
            "source":"Official Italian GP grid / Mercedes weekend reporting",
        },
        "PIA": {
            "penalty":"Three-place grid penalty",
            "note":"Dropped three grid places for impeding Liam Lawson in qualifying.",
            "known_at_prediction_time": False,
            "source":"Official Italian GP grid",
        },
        "ALB": {
            "penalty":"Starts from the back",
            "note":"Power-unit element changes beyond the permitted allocation.",
            "known_at_prediction_time": False,
            "source":"Official Italian GP grid",
        },
        "LAW": {
            "penalty":"Starts from the pit lane",
            "note":"Parc-fermé setup changes after qualifying.",
            "known_at_prediction_time": False,
            "source":"Official Italian GP grid",
        },
        "ALO": {
            "penalty":"Starts from the pit lane",
            "note":"Power-unit element changes under parc fermé.",
            "known_at_prediction_time": False,
            "source":"Official Italian GP grid",
        },
    },
}

DRIVER_SUBSTITUTIONS = {
    12: {
        "banner":"Isack Hadjar missed the Dutch Grand Prix with a wrist fracture. Liam Lawson moved to Red Bull and Yuki Tsunoda took the Racing Bulls seat alongside Lindblad. The saved pre-race prediction is preserved as generated; the late lineup change is treated as a documented exception rather than retroactively rerunning the forecast.",
        "unavailable":{"HAD":"Wrist injury — did not race at Zandvoort"},
        "moved":{"LAW":"Red Bull"},
        "added":[{"code":"TSU","name":"Yuki Tsunoda","team":"VCARB","reason":"Reserve driver — late substitution"}],
    },
    13: {
        "banner":"Isack Hadjar misses Monza while his wrist continues to heal. Liam Lawson remains alongside Verstappen at Red Bull and Yuki Tsunoda remains alongside Lindblad at Racing Bulls.",
        "unavailable":{"HAD":"Wrist injury — not racing at Monza"},
        "moved":{"LAW":"Red Bull"},
        "added":[{"code":"TSU","name":"Yuki Tsunoda","team":"VCARB","reason":"Reserve driver standing in for Lawson"}],
    },
    14: {
        "banner":"The Red Bull/Racing Bulls substitution continues for Madrid: Isack Hadjar remains unavailable, Liam Lawson stays at Red Bull, and Yuki Tsunoda stays alongside Lindblad at Racing Bulls.",
        "unavailable":{"HAD":"Wrist injury — not racing at Madrid"},
        "moved":{"LAW":"Red Bull"},
        "added":[{"code":"TSU","name":"Yuki Tsunoda","team":"VCARB","reason":"Reserve driver continuing in Lawson's Racing Bulls seat"}],
    },
}

# ─────────────────────────────────────────────────────────
#  ADUO — Additional Development Upgrade Opportunity
# ─────────────────────────────────────────────────────────
PU_ADUO_UPGRADES = {
    "Audi": {
        "round": 7,
        "tokens_allocated": 2,
        "aduo_band": ">4% deficit",
        "benchmark": False,
        "note": "ADUO upgrade 1 deployed at Barcelona (R7), 2 allocated (>4% deficit). Reported as driveability/throttle-response work around the large turbocharger rather than a clearly measured outright power step.",
    },
    "Ferrari": {
        "round": 8,
        "second_round": 13,
        "tokens_allocated": 2,
        "aduo_band": ">4% deficit",
        "benchmark": False,
        "note": "ADUO upgrade 1 deployed at Austria (R8), 2 allocated (>4% deficit). ICE/fuel changes were reported as a modest performance step.",
        "second_note": "ADUO upgrade 2 deployed at Monza (R13), including the latest Ferrari PU specification and redesigned turbocharger work.",
    },
    "Honda": {
        "round": 12,
        "tokens_allocated": 2,
        "aduo_band": ">4% deficit",
        "benchmark": False,
        "note": "ADUO upgrade 1 deployed at Zandvoort (R12), 2 allocated (>4% deficit). Updated RA626H targeted raw ICE power with minor battery changes; effect remains difficult to isolate from chassis/race context.",
    },
    "Mercedes": {
        "round": None,
        "tokens_allocated": 1,
        "aduo_band": "2–4% deficit",
        "benchmark": False,
        "note": "ADUO upgrade allocated (1, 2–4% behind benchmark ICE) but not yet used. Fresh PU components fitted earlier in the season were treated as reliability measures rather than a performance homologation.",
    },
}
