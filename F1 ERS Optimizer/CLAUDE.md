# Memory — ERS_v2

## Me
Ganesh. Master's Data Science student. Building ERS_v2 as a portfolio piece targeting F1 team analytics roles.

## Tone
Direct, technically honest. Short answers, no padding. Call out errors clearly. State uncertainty explicitly. Treat me as a technical peer — I know F1 and catch mistakes fast. No preambles or workflow narration unless I ask.

## Project: ERS_v2
Physics-grounded F1 ERS strategy optimizer + race predictor for 2026 season.

**Core idea:** observation-first inference. Compute theoretical optimal from 2026 FIA regs, compare to real FastF1 telemetry, treat the gap as signal. Dual output: quali grid + race result, blended.

**Path:** `D:\ERS_v2\` (Windows). Cache at `D:\cache`.

**Stack:** Python, FastF1 ≥3.4.0, numpy, pandas, scipy, matplotlib, plotly.

**CLI entry:** `run.py` — commands: `pipeline`, `race`, `predict`, `store`, `compare`, `test`, `viz`, `vizly`.

## Current state

**Done:**
- Phase 1: real lap times from `session.laps`, all 22 drivers, outlier/confidence filter (5% median + 40kph hard cap), corrupted laps excluded (ALB, VER crash), `_apply_known_lap_delta` killed
- `lap_time_gap_pct` = primary signal; `straight_speed_delta_kph` = secondary; corner delta dropped (unreliable)
- Sprint SQ loading; all 22 circuits configured
- `race_pipeline.py` with `run_race_session`, `_get_representative_race_lap` using stint-grouped IQR; per-stint degradation stored (not yet used)
- `fingerprint.py` updated with `laps_completed_map`; `fingerprint_race` added
- `predictor.py` split: `predict_qualifying()` (Q+SQ), `predict_race_pace()` (R+S), `predict_race()` blends
- `compare.py`, `prediction_store.py` done
- Plotly viz layer complete (7 files in `viz/plotly/`), dashboard via `run.py vizly dashboard`
- Fingerprint store: Q for Australia, China (+SQ), Japan; R for Australia, China, Japan. Miami pre-saved.

**Race pipeline code is written but NOT yet executed.** First run is the immediate next step.

## Immediate next step
1. `python run.py race australia`
2. `python run.py race china`
3. `python run.py race japan`
4. `python run.py store` — verify race fingerprints appear
5. `python run.py predict miami` — regenerate with race pace blended in
6. `python run.py predict bahrain` — next race weekend

## Hard constraints / gotchas
- FastF1 `TrackStatus` is string `"1"` (not int) — green flag filter must use string
- Stint detection: use `session.laps["Stint"]` directly. Do NOT detect via compound changes.
- Degradation: `np.polyfit(lap_numbers, lap_times, 1)[0]` per stint
- Race fingerprints save as `2026_R01_R.json` via existing `race_store.py` convention
- `load_all_fingerprints()` must filter by `session_type` before hitting predictor — never mix Q and R in same branch
- Predictions = weighted avg of `lap_time_gap_pct` across historical fingerprints, weighted by recency + circuit similarity
- Confidence 0.3 when `laps_completed < 30%` of race distance (DNF detection — Honda/Aston matter here)
- Compound tyre data stored per stint but NOT used in predictor until race 8+
- Hrv/Dep signals stored but decorative — predictor is pure lap time gap interpolator

## Open questions to verify on first race run
- Is `load_all_fingerprints()` correctly filtering R vs Q/SQ in the split predictor?
- Do ALO/STR trigger confidence 0.3 in Australia/China DNFs?
- Are safety car laps removed by IQR before they inflate stint averages? Check China R.
- Does `S` session (China sprint) load correctly via `run_race_session` with `fastf1_session: "S"`?

## Deferred — do not fix now
Hrv/Dep inference (flat, not differentiating PUs). Needs more circuit variety + Phase 2 sector cross-validation first.

## Remaining phases (in order)
1. Sector time S1/S2/S3 pull + cross-validate speed deltas
2. Hrv/Dep inference fix
3. Bellman/DP optimizer to replace greedy pass
4. Aero density normalisation (altitude circuits: Mexico, Brazil, Baku)
5. Dynamic Honda penalty decay as they finish more races
6. Kalman filter for segment boundary detection in `track.py`

## Known upcoming reg change
Round 6 (Canadian GP, post-ADUO): compression ratio hot-test rule closes Mercedes loophole. No parameter change — fingerprint layer absorbs it from race data.
