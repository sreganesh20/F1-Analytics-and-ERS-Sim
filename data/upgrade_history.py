"""Canonical 2026 chassis/aero development history for LatentLap.

This module deliberately separates *what was declared/brought* from whether a
change should alter the prediction model's historical weighting.

Categories
----------
persistent       A lasting chassis/aero development carried forward.
circuit_specific A configuration/range change for a particular circuit.
reliability      Reliability/cooling/structural change without a defensible
                 persistent pace step.

Power-unit ADUO events remain in ``config.PU_ADUO_UPGRADES`` because they have
separate regulatory semantics.

Only entries with all of:
    status == "confirmed"
    category == "persistent"
    affects_prediction is True
are consumed by the prediction weighting logic.

The inventory was audited through R13 against official F1/FIA-style weekend
upgrade declarations, with reputable technical reporting used for context and
significance. Significance is intentionally manual/reviewable rather than LLM-
generated.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

UPGRADE_HISTORY: list[dict] = [
    # R2 — China
    {"team":"Ferrari","round":2,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Halo/front-of-halo winglet refinement","detail":"Small aerodynamic load refinement.","source":"RACER technical update — Chinese GP 2026"},
    {"team":"VCARB","round":2,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear brake-duct winglet update","detail":"Local aerodynamic refinement around the rear corner.","source":"RACER technical update — Chinese GP 2026"},
    {"team":"Haas","round":2,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear crash-structure winglet refinement","detail":"Small local-load change.","source":"RACER technical update — Chinese GP 2026"},
    {"team":"Audi","round":2,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"New nose and front-wing tandem","detail":"Front-end package intended to improve downstream/global flow structures.","source":"RACER technical update — Chinese GP 2026"},
    {"team":"Cadillac","round":2,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Diffuser trailing-edge and mirror-stay revisions","detail":"Local rear-load and mirror-support/aero changes.","source":"RACER technical update — Chinese GP 2026"},

    # R3 — Japan
    {"team":"Red Bull","round":3,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Sidepod inlet, engine-cover and floor package","detail":"Coordinated package targeting load and efficiency; separate cooling-only rear-wheel bodywork change is recorded separately.","source":"RACER technical update — Japanese GP 2026"},
    {"team":"Red Bull","round":3,"status":"confirmed","category":"reliability","significance":"minor","affects_prediction":False,"headline":"Rear-wheel bodywork cooling change","detail":"Cooling/reliability-focused detail rather than a persistent pace step.","source":"RACER technical update — Japanese GP 2026"},
    {"team":"Ferrari","round":3,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front brake-duct and floor-stay fairing refinements","detail":"Small front-corner/floor-flow evolution.","source":"RACER technical update — Japanese GP 2026"},
    {"team":"Williams","round":3,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front-suspension internal and cladding revisions","detail":"Meaningful suspension/aero integration update.","source":"RACER technical update — Japanese GP 2026"},
    {"team":"Aston Martin","round":3,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front wing/endplate and floor leading-edge update","detail":"Front-aero and floor-flow development.","source":"RACER technical update — Japanese GP 2026"},
    {"team":"Alpine","round":3,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front deflector and rear-wing/endplate redesign","detail":"Front- and rear-aero development package.","source":"RACER technical update — Japanese GP 2026"},
    {"team":"Cadillac","round":3,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Diffuser and fence update","detail":"Rear-load and ride-height-behaviour refinement.","source":"RACER technical update — Japanese GP 2026"},

    # R4 — Miami
    {"team":"Mercedes","round":4,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Tailpipe winglet and front-brake-drum refinement","detail":"Small aerodynamic detail changes.","source":"Official/technical upgrade declarations — Miami GP 2026"},
    {"team":"McLaren","round":4,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Major floor and front-aero development package","detail":"Front/rear corner structures, bodywork/sidepod inlet, floor/bargeboard, rear-wing and cooling-detail changes.","source":"F1.com / technical reporting — Miami GP 2026"},
    {"team":"VCARB","round":4,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Large front/rear aero and floor package","detail":"Front and rear wings, floor edge, rear brake ducts, rear suspension and endplate work.","source":"Official/technical upgrade declarations — Miami GP 2026"},
    {"team":"Audi","round":4,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front corner, suspension, floor-edge and diffuser package","detail":"First broad post-opening-round development step.","source":"Official/technical upgrade declarations — Miami GP 2026"},
    {"team":"Alpine","round":4,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front-brake, rear-suspension and rear-wing development","detail":"Also included nose-camera mounting and rear-impact-structure detail changes.","source":"Official/technical upgrade declarations — Miami GP 2026"},
    {"team":"Cadillac","round":4,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Comprehensive nine-area aero development package","detail":"Front wing, mirror stays, floor/diffuser, suspension fairings and other ride-height/aero changes.","source":"Official/technical upgrade declarations — Miami GP 2026"},
    {"team":"Red Bull","round":4,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Very large floor/bodywork/wing package","detail":"Front wing, brake ducts, floor, sidepods, engine cover, diffuser, rear wing and related details.","source":"F1.com Tech Weekly — Miami GP 2026"},
    {"team":"Ferrari","round":4,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Eleven-part aero package","detail":"Front wing/endplate, front deflector, suspension fairings, floor and sidepod work.","source":"F1.com / technical reporting — Miami GP 2026"},
    {"team":"Williams","round":4,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"First major 2026 development package","detail":"Floor, bodywork, front wing, rear suspension, exhaust interaction and weight-reduction work.","source":"Technical reporting — Miami GP 2026"},

    # R5 — Canada
    {"team":"Mercedes","round":5,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Front wing, front/rear corner and floor package","detail":"First major Mercedes chassis/aero update of the season.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Mercedes","round":5,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Front-brake cooling inlet enlargement","detail":"Cooling demand/configuration for Montreal.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"McLaren","round":5,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Front wing, bodywork, floor-edge and rear-aero package","detail":"Broad follow-up development across front, floor, rear wing and suspension fairings.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"McLaren","round":5,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Additional cooling-louvre option","detail":"Cooling-range option rather than a persistent baseline step.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Red Bull","round":5,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front-wing and bib/floor update","detail":"Persistent front-aero/floor development.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Red Bull","round":5,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Brake-duct and engine-cover cooling options","detail":"Montreal cooling configuration.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Williams","round":5,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Suspension cladding and tailpipe development","detail":"Evolution of the Miami package.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Williams","round":5,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Front-brake cooling geometry","detail":"Circuit cooling requirement.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"VCARB","round":5,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Floor, rear-corner and beam-wing package","detail":"Larger development step than Miami.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Haas","round":5,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"First major Haas 2026 package","detail":"Bodywork/sidepod, bespoke floor/diffuser, rear suspension and rear-corner development.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Audi","round":5,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Diffuser refinement","detail":"Persistent rear-aero development.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Audi","round":5,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Brake-duct and cooling-louvre configuration","detail":"Cooling-focused Montreal changes.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Alpine","round":5,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"New floor and rear wing","detail":"Notable aero development step.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Cadillac","round":5,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front-corner and diffuser/hanger refinements","detail":"Local aerodynamic development.","source":"F1.com official upgrade rundown — Canadian GP 2026"},
    {"team":"Cadillac","round":5,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Front-brake cooling update","detail":"Circuit cooling configuration.","source":"F1.com official upgrade rundown — Canadian GP 2026"},

    # R6 — Monaco: predominantly circuit-specific
    *[
        {"team":team,"round":6,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":headline,"detail":"Monaco-specific high-downforce, steering-clearance or cooling configuration; retained for context but excluded from persistent prediction weighting.","source":"F1.com official upgrade rundown — Monaco GP 2026"}
        for team, headline in [
            ("Mercedes","Rear-wing/straight-mode fairing detail"),
            ("McLaren","Cooling, steering-clearance and high-downforce rear-aero options"),
            ("Alpine","Rear-wing actuator winglets"),
            ("Red Bull","Cooling, brake-duct and steering-clearance changes"),
            ("Ferrari","Steering and Monaco floor/diffuser details"),
            ("Williams","Exhaust and front-suspension configuration"),
            ("Aston Martin","Suspension and cooling configuration"),
            ("Haas","Front-suspension and rear-wing actuator details"),
            ("Audi","Straight-mode actuator removal and cooling/mirror changes"),
            ("Cadillac","High-load rear-wing configuration"),
        ]
    ],

    # R7 — Barcelona
    {"team":"Ferrari","round":7,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Major front-wing, full-floor and sidepod package","detail":"The weekend's most extensive declared package: front wing/mainplane/endplates/nose, floor body/boards/edge/diffuser and sidepod/cokeline work.","source":"F1.com official upgrade rundown — Barcelona-Catalunya GP 2026"},
    {"team":"McLaren","round":7,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front-wing endplate refinement","detail":"Small persistent front-aero change.","source":"F1.com official upgrade rundown — Barcelona-Catalunya GP 2026"},
    {"team":"Mercedes","round":7,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Centreline rear-wing winglets","detail":"Event/range-specific rear-wing configuration.","source":"F1.com official upgrade rundown — Barcelona-Catalunya GP 2026"},
    {"team":"Red Bull","round":7,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front-wing geometry refinement","detail":"Small load/balance development.","source":"F1.com official upgrade rundown — Barcelona-Catalunya GP 2026"},
    {"team":"Williams","round":7,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Rear-wing straight-mode fairing winglets","detail":"Circuit/range-specific rear-wing configuration.","source":"F1.com official upgrade rundown — Barcelona-Catalunya GP 2026"},
    {"team":"VCARB","round":7,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Diffuser/rear-crash integration refinement","detail":"Persistent rear-aero detail; front-wing gurneys were primarily balance tuning.","source":"F1.com official upgrade rundown — Barcelona-Catalunya GP 2026"},
    {"team":"Haas","round":7,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Rear-impact geometry/tuning option","detail":"Created circuit-tuning flexibility rather than a clearly persistent baseline step.","source":"F1.com official upgrade rundown — Barcelona-Catalunya GP 2026"},
    {"team":"Cadillac","round":7,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Cooling-louvre and front-wing actuator configuration","detail":"Event/range configuration.","source":"F1.com official upgrade rundown — Barcelona-Catalunya GP 2026"},
    # Aston Martin, Audi and Alpine: explicitly no new chassis/aero components R7.

    # R8 — Austria
    {"team":"Red Bull","round":8,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Major floor, bodywork, suspension and rear-corner package","detail":"Broad development across floor/boards, sidepod inlet/engine cover, rear suspension/corner and supporting aero details.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"McLaren","round":8,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear brake-duct refinement","detail":"Small persistent rear-corner development; alternate rear-wing/SLM items treated separately as configuration.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"McLaren","round":8,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Alternate rear-wing / SLM configuration","detail":"Circuit/range-specific aero option.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"Mercedes","round":8,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front-suspension fairing refinement","detail":"Small suspension/aero integration development.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"Mercedes","round":8,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Narrower rear engine-cover cooling exit","detail":"Cooling-range option.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"Ferrari","round":8,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front-wing endplate development","detail":"Small persistent front-aero change. Test-only parts not raced are excluded.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"Audi","round":8,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Large front-wing, floor, diffuser and rear-aero package","detail":"Broad package spanning front wing/endplate, front/rear corners, floor, rear suspension, beam and rear wing.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"Alpine","round":8,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Large front-wing, nose and diffuser package","detail":"Broad front- and rear-aero development.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"Cadillac","round":8,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Substantial bodywork/floor/diffuser package","detail":"Large multi-area aero development including beam-wing work.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"VCARB","round":8,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Tailpipe and diffuser refinement","detail":"Small persistent rear-aero/exhaust-integration change.","source":"F1.com official upgrade rundown — Austrian GP 2026"},
    {"team":"Haas","round":8,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Cooling-louvre and front-brake-duct revision","detail":"Predominantly circuit/cooling driven.","source":"F1.com official upgrade rundown — Austrian GP 2026"},

    # R9 — Britain
    {"team":"Ferrari","round":9,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear-corner aero/cooling refinement","detail":"Rear-corner inlet/outlet, lower deflector and winglet cluster changes.","source":"F1.com official upgrade rundown — British GP 2026"},
    {"team":"McLaren","round":9,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front-brake-duct and floor-furniture development","detail":"Persistent front-corner/floor-flow refinement.","source":"F1.com official upgrade rundown — British GP 2026"},
    {"team":"Red Bull","round":9,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear-wheel bodywork cascade winglets","detail":"Small persistent rear-corner development.","source":"F1.com official upgrade rundown — British GP 2026"},
    {"team":"VCARB","round":9,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Floor-corner, diffuser and rear-corner package","detail":"Notable persistent rear-floor development.","source":"F1.com official upgrade rundown — British GP 2026"},
    {"team":"Haas","round":9,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear-wing profile/endplate refinement","detail":"Rear-aero development with some setup-range intent.","source":"F1.com official upgrade rundown — British GP 2026"},
    {"team":"Williams","round":9,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"New front-wing geometry","detail":"Meaningful front-aero development step.","source":"F1.com official upgrade rundown — British GP 2026"},

    # R10 — Belgium
    {"team":"McLaren","round":10,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Spa-specific low-drag rear wing","detail":"Circuit-specific rear-wing range.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"McLaren","round":10,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear-wing endplate refinement","detail":"Small change intended to work across a wider operating range.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Mercedes","round":10,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Spa-specific rear wing","detail":"Low-drag circuit configuration. This was previously mis-filed at R8.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Mercedes","round":10,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front-wing endplate and rear-drum winglet refinements","detail":"Small persistent aero details; separated from the Spa-only rear wing.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Red Bull","round":10,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear-wing pylon profile refinement","detail":"Small persistent rear-wing support/aero development.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Williams","round":10,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"New floor body","detail":"Meaningful floor development.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Williams","round":10,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Spa floor trim and rear-brake-duct load configuration","detail":"Circuit-specific load/range choice.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"VCARB","round":10,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Major chassis/bodywork and aero package","detail":"Engine cover/sidepod, narrower roll hoop, front corner and rear-wing development. Initially limited by parts availability.","source":"F1.com / RACER — Belgian GP 2026"},
    {"team":"Haas","round":10,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front-wing/endplate and front-corner package","detail":"Persistent front-aero development.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Haas","round":10,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Lower-downforce beam-wing option","detail":"Spa-specific drag/load configuration.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Audi","round":10,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"New diffuser","detail":"Persistent rear-floor development.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Audi","round":10,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Upper rear-wing configuration","detail":"Spa load-range choice.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Alpine","round":10,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Halo winglet refinement","detail":"Small local aero change.","source":"RACER technical update — Belgian GP 2026"},
    {"team":"Cadillac","round":10,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front-wing endplate/footplate revision","detail":"Small persistent front-aero development.","source":"RACER technical update — Belgian GP 2026"},

    # R11 — Hungary
    {"team":"Aston Martin","round":11,"status":"confirmed","category":"persistent","significance":"new_car","affects_prediction":True,"headline":"Sixteen-area B-spec overhaul","detail":"New front architecture and extensive floor, diffuser, sidepod, bodywork, cooling, suspension and rear-aero work — effectively a different car baseline.","source":"F1.com technical analysis — Hungarian GP 2026"},
    {"team":"McLaren","round":11,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Floor/front-corner/rear-corner package","detail":"New floor/floor-board work plus brake-duct and rear-wing/endplate development.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"Mercedes","round":11,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear/tail aero refinement","detail":"Small persistent rear-aero detail changes.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"Mercedes","round":11,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Wider rear-bodywork cooling option","detail":"Cooling-range configuration.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"Red Bull","round":11,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Rear-wing and diffuser development","detail":"Rear-wing pylon/flap and diffuser changes.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"Ferrari","round":11,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear-wing/endplate refinement","detail":"Small rear-aero load-range development.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"Williams","round":11,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Hungaroring high-downforce rear-wing/floor configuration","detail":"Circuit-specific load choice.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"VCARB","round":11,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Spa package rolled onto Lawson chassis","detail":"Rollout of the persistent R10 chassis package to Lawson; no second team-wide weight step is applied here.","source":"F1.com technical reporting — Hungarian GP 2026","drivers":["LAW"],"rollout_of_round":10},
    {"team":"VCARB","round":11,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Rear-wing/cooling/roll-hoop configuration","detail":"Hungary-specific configuration details.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"Haas","round":11,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Rear-wing SLM fairing detail","detail":"Track/range-specific rear-wing configuration.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"Audi","round":11,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Rear-wing endplate refinement","detail":"Small persistent rear-aero change.","source":"Technical upgrade reporting — Hungarian GP 2026"},
    {"team":"Cadillac","round":11,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Front-brake cooling change","detail":"Cooling configuration.","source":"Technical upgrade reporting — Hungarian GP 2026"},

    # R12 — Netherlands
    {"team":"Mercedes","round":12,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Front-corner flow refinement","detail":"Small persistent front-corner development.","source":"F1.com official upgrade rundown — Dutch GP 2026"},
    {"team":"Ferrari","round":12,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Further floor and diffuser development","detail":"Floor body/board/edge and diffuser geometry plus associated rear-aero work.","source":"F1.com official upgrade rundown — Dutch GP 2026"},
    {"team":"McLaren","round":12,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Rear-wing, bodywork and rear-brake-duct package","detail":"Post-shutdown continuation of the development programme.","source":"F1.com official upgrade rundown — Dutch GP 2026"},
    {"team":"Red Bull","round":12,"status":"confirmed","category":"reliability","significance":"minor","affects_prediction":False,"headline":"Wishbone shroud/gaiter reliability change","detail":"Reliability-focused; not treated as a persistent pace step.","source":"F1.com official upgrade rundown — Dutch GP 2026"},
    {"team":"Alpine","round":12,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Major floor/bodywork/diffuser package — Gasly rollout","detail":"Large floor, diffuser, bodywork/sidepod and rear-corner/rear-wing package. At Zandvoort only Gasly had the complete new specification.","source":"F1.com / RACER — Dutch GP 2026","drivers":["GAS"]},
    {"team":"Aston Martin","round":12,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front-wing, floor-fence and diffuser refinement","detail":"Further aero development after the Hungary B-spec.","source":"F1.com official upgrade rundown — Dutch GP 2026"},
    # Official declaration: no new chassis/aero upgrades for Williams, VCARB, Haas, Audi, Cadillac.

    # R13 — Italy
    {"team":"McLaren","round":13,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Rear-wing and floor-furniture development","detail":"Changes combined drag reduction with broader aero-performance intent.","source":"RACER technical update — Italian GP 2026"},
    {"team":"Mercedes","round":13,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Monza low-drag rear-wing/mirror configuration","detail":"Rear-wing winglet removal and trimmed mirror-stay work for drag reduction.","source":"RACER technical update — Italian GP 2026"},
    {"team":"Red Bull","round":13,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front-wing endplate and floor-bib development","detail":"Persistent front/floor performance changes.","source":"RACER technical update — Italian GP 2026"},
    {"team":"Red Bull","round":13,"status":"confirmed","category":"reliability","significance":"minor","affects_prediction":False,"headline":"Rear suspension/wheel-bodywork and exhaust-bracket reliability details","detail":"Structural/reliability changes separated from the performance package.","source":"RACER technical update — Italian GP 2026"},
    {"team":"Ferrari","round":13,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Monza drag-range floor/mirror/rear-brake/tailpipe configuration","detail":"Circuit-specific low-drag configuration. Ferrari's second ADUO step is tracked separately as a PU event.","source":"RACER technical update — Italian GP 2026"},
    {"team":"Williams","round":13,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Front-wing/floor-board Monza balance configuration","detail":"Low-drag/balance range changes.","source":"RACER technical update — Italian GP 2026"},
    {"team":"VCARB","round":13,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Rear-wing SLM and tailpipe configuration","detail":"Predominantly Monza drag/efficiency configuration.","source":"RACER technical update — Italian GP 2026"},
    {"team":"Aston Martin","round":13,"status":"confirmed","category":"persistent","significance":"medium","affects_prediction":True,"headline":"Front-suspension fairing and rear-floor development","detail":"Persistent aero refinements around suspension and floor ahead of the rear tyre.","source":"RACER technical update — Italian GP 2026"},
    {"team":"Haas","round":13,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Largest Haas package since Canada","detail":"New floor/side geometry/diffuser, sidepod/rear bodywork, narrower roll hoop/engine cover, rear suspension and rear-corner development.","source":"F1.com / RACER — Italian GP 2026"},
    {"team":"Alpine","round":13,"status":"confirmed","category":"persistent","significance":"major","affects_prediction":True,"headline":"Zandvoort package rolled out to Colapinto","detail":"Colapinto received the major R12 floor/bodywork specification at Monza; driver-scoped so Gasly is not double-weighted.","source":"F1.com — Italian GP 2026","drivers":["COL"],"rollout_of_round":12},
    {"team":"Alpine","round":13,"status":"confirmed","category":"circuit_specific","significance":"minor","affects_prediction":False,"headline":"Monza front-wing/endplate and SLM configuration","detail":"Low-drag circuit-specific details.","source":"RACER technical update — Italian GP 2026"},
    {"team":"Cadillac","round":13,"status":"confirmed","category":"persistent","significance":"minor","affects_prediction":True,"headline":"Floor-board stay and diffuser-vane refinement","detail":"Small persistent floor/diffuser development.","source":"RACER technical update — Italian GP 2026"},
    # Audi declared no chassis/aero upgrade at Monza.
]


SIGNIFICANCE_WEIGHT = {
    "new_car": 0.05,
    "major": 0.40,
    "medium": 0.70,
    "moderate": 0.70,  # accepted alias for future curated entries
    "minor": 0.90,
}


def events_for_team(team: str, *, through_round: int | None = None) -> list[dict]:
    """Return canonical events for a team, optionally capped by round."""
    events = [e for e in UPGRADE_HISTORY if e["team"] == team]
    if through_round is not None:
        events = [e for e in events if e["round"] <= through_round]
    return sorted(events, key=lambda e: (e["round"], e["headline"]))


def prediction_events(team: str, driver: str | None = None) -> list[dict]:
    """Persistent, confirmed events that are allowed to alter prediction weights."""
    out = []
    for e in events_for_team(team):
        if e.get("status") != "confirmed":
            continue
        if e.get("category") != "persistent" or not e.get("affects_prediction", False):
            continue
        scoped = e.get("drivers")
        if scoped and driver is not None and driver not in scoped:
            continue
        out.append(e)
    return out


def planned_events_at_round(round_num: int, team: str | None = None) -> list[dict]:
    """Return explicitly planned (not merely future-dated confirmed) events at a round."""
    return [
        e for e in UPGRADE_HISTORY
        if e.get("status") == "planned"
        and e.get("round") == round_num
        and (team is None or e.get("team") == team)
    ]


def legacy_team_upgrades() -> dict[str, list[dict]]:
    """Compatibility view for older code; derived, never independently maintained."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in UPGRADE_HISTORY:
        if e.get("status") != "confirmed":
            continue
        grouped[e["team"]].append({
            "from_round": e["round"],
            "significance": e["significance"],
            "headline": e["headline"],
            "detail": e.get("detail", ""),
            "source": e.get("source", ""),
            "category": e.get("category", "persistent"),
            "affects_prediction": e.get("affects_prediction", False),
            **({"drivers": list(e["drivers"])} if e.get("drivers") else {}),
        })
    return dict(grouped)


def legacy_upcoming_upgrades() -> dict[str, list[dict]]:
    """Compatibility view for planned events; derived from canonical history."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in UPGRADE_HISTORY:
        if e.get("status") != "planned":
            continue
        grouped[e["team"]].append({
            "at_round": e["round"],
            "significance": e["significance"],
            "note": " ".join(x for x in (e["headline"], e.get("detail", "")) if x),
        })
    return dict(grouped)
