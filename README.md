# PitWall — F1 2026 Analytics

A telemetry-driven Formula 1 analytics platform built on FastF1. It fingerprints every car's energy-recovery behaviour from real session data, runs a dynamic-programming optimiser to find the theoretically optimal ERS strategy per circuit, and predicts qualifying and race pace for upcoming rounds — with an LLM layer that explains its own numbers in plain language.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://f1-analytics-and-ers-sim-qvp7tgfjxrwmbz4zs9nxr7.streamlit.app/)

All data is **real 2026 Formula 1 session data**, pulled from FastF1's FIA timing feed — actual lap times, telemetry, and results. The predictions are the model's own output; everything they are built from is measured.

---

## What it does

The platform turns raw lap telemetry into three things: a per-car performance fingerprint, an optimal energy-management strategy, and a forward-looking pace prediction. A natural-language layer sits on top so you can ask the model why it reached a conclusion.

**ERS fingerprinting.** Pulls real telemetry for every driver in every session, segments each lap into straights, braking zones, corners, and superclip zones, and computes per-driver metrics: braking harvest ratio (observed energy recovery vs theoretical maximum), straight-line speed delta, corner speed delta, and time lost per sector. Every fingerprint is tagged with the regulation epoch it was recorded under, because the rules changed mid-season and older data isn't directly comparable to newer.

**Dynamic-programming ERS optimiser.** Given a circuit's segmentation, it solves for the theoretically optimal lap-by-lap harvest and deploy strategy using Bellman DP over a discretised battery state-of-charge space. It respects the FIA per-circuit harvest limits (5–9 MJ), the 4 MJ battery cap, the MGU-K power ceiling, and an aero-density correction for high-altitude circuits.

**Race prediction.** For an upcoming round, it weights every stored fingerprint by circuit similarity, recency, regulation epoch, session type, and team upgrade status, applies a harvest-ratio correction, and produces a predicted order with confidence intervals. Qualifying (Q + sprint qualifying) and race pace (race + sprint) are predicted separately because they diverge, and sprint weekends produce four predictions instead of two.

**AI layer (Groq / GPT-OSS-120B).** Three features under strict retrieval-augmented grounding: an explainer that reads any prediction row and says why the model placed a driver there; auto-generated race recaps built from real finishing orders; and an "Ask the Engineer" page that answers free-text questions from a season digest plus retrieved session rows. The model answers only from the injected data and says so when a question falls outside it — it never draws on real-world F1 knowledge.

---

## The corner-delta problem — a worked example

The most involved piece of this project was a data-quality bug that was invisible until the numbers were interrogated, and the fix is worth describing because it shows the platform's approach: verify against the data before asserting anything.

Corner-speed deltas are measured over fixed distance windows taken from each session's fastest lap. Early in development the corner performance ranking put Audi — the seventh-fastest car by lap time — first, ahead of Mercedes and Ferrari. That's not impossible for a draggy, low-power car, but it was suspicious enough to check rather than ship.

The investigation traced it to two separate faults. First, the telemetry loader built each driver's distance axis by integrating their own speed trace over time (`get_car_data().add_distance()`), which accumulates error along the lap — up to **56 metres of drift across the field** at Silverstone. Since corner windows are fixed distance ranges, that misalignment meant a "corner" window measured a different piece of track for every car, producing physically incoherent readings (one lap showed a car 74 km/h down on the straights but 68 km/h up in the corners). Second, the corner-delta formula was a first-order time-ratio approximation that exaggerated slow cars without bound, generating values like −80 km/h that no real car produces.

The fix, verified against a clean session and a broken one before committing to a 30-session re-run: switch to `get_telemetry()` (which anchors distance to the true lap boundary via interpolation), replace the approximation with an exact distance-over-time speed calculation, and aggregate per-lap segments with a median rather than a mean so a single mis-segmented corner can't define a lap. The worst outlier dropped from −80.8 km/h to −23.8 km/h, and the corner ranking's agreement with overall pace (Spearman ρ) rose from 0.68 to 0.93 — Audi fell to seventh, exactly where its lap-time pace sits.

A residual limitation remains, and the platform states it plainly rather than hiding it: because corners are still detected on the fastest lap's distance axis, cars that brake at materially different points are compared imperfectly. Per-driver corner deltas beyond ±40 km/h are suppressed in the UI rather than shown, and the charts carry the caveat. The real fix — geometric corner detection from X/Y track curvature — is on the roadmap.

---

## The Streamlit app

Six pages:

| Page | What you see |
|---|---|
| Home | Championship standings (live via API), power-unit performance evolution |
| Predictions | Qualifying and race predictions per session, sprint-weekend aware, cumulative race gaps, per-driver upgrade footnotes, AI explainer, driver-substitution handling |
| Race Analysis | Per-session fingerprint table with DNF/NC tracking |
| Teams & Drivers | Teammate head-to-head, straight-vs-corner scatter, corner profile ranking, power-unit analysis |
| Upgrades & News | Per-team upgrade timelines in two columns (confirmed and sourced), power-unit ADUO state, race commentary with AI auto-generation |
| Ask the Engineer | Natural-language questions answered from the season's data under strict grounding |

---

## Local setup

```bash
git clone https://github.com/sreganesh20/F1-Analytics-and-ERS-Sim.git
cd F1-Analytics-and-ERS-Sim
python -m venv .venv
.venv\Scripts\activate        # Windows; use source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
streamlit run Home.py
```

The `store/` folder holds pre-computed fingerprints for the completed rounds, committed to the repo, so the app runs without needing FastF1 or a local cache. FastF1 is only required to pull new session data.

### AI features (optional)

The AI features need a free [Groq](https://console.groq.com) API key. Without one, those parts of the app hide themselves cleanly and everything else works.

Create `.streamlit/secrets.toml` (gitignored) with a single line:

```toml
GROQ_API_KEY = "gsk_your_key_here"
```

For the deployed app, add the same line under Manage app → Settings → Secrets. The model ID can be overridden with an optional `GROQ_MODEL` secret if Groq deprecates the default.

---

## Weekend workflow

After a race weekend, pull the new data, rebuild the derived artefacts, and push. Streamlit Cloud redeploys on push; module changes need a manual reboot from the dashboard.

```bash
python run.py pipeline netherlands     # qualifying fingerprints (auto-includes SQ on sprint weekends)
python run.py race netherlands         # race fingerprints (auto-includes sprint)
python run.py extract-telemetry        # commit-sized telemetry for the ERS Explorer
python run.py predict netherlands      # four predictions on a sprint weekend, two otherwise
python run.py build-digest             # refresh the season digest the AI reads
python run.py compare netherlands      # after the race — prediction vs actual

git add -A && git commit -m "Round 12" && git push
```

Then bump `CURRENT_ROUND` in `app/data_loader.py` so upgrades and results register as past rather than upcoming, and reboot the deployed app.

---

## Command reference

| Command | What it does |
|---|---|
| `pipeline <circuit>` | Pull qualifying (and sprint qualifying) fingerprints |
| `race <circuit>` | Pull race (and sprint) fingerprints |
| `predict <circuit>` | Generate predictions for a round |
| `extract-telemetry [circuit]` | Write commit-sized telemetry extracts from the cache |
| `build-digest` | Rebuild the season digest for the AI features |
| `compare <circuit>` | Post-race prediction accuracy |
| `viz [chart]` | Regenerate static charts |

---

## How the data flows

```
FastF1 API
  -> fetcher.py            pull real telemetry, track-accurate distance axis
  -> models/track.py       segment lap into straights, braking, corners, superclip
  -> models/fingerprint.py exact speed deltas vs the reference car, median-aggregated
  -> models/optimizer.py   DP optimiser -> theoretical optimal harvest/deploy
  -> store/ (JSON)         committed fingerprints, telemetry extracts, predictions
  -> analysis/predictor.py weighted prediction for the next round
  -> analysis/llm.py       season digest + retrieval -> grounded AI answers
  -> Streamlit app         interactive pages
```

---

## Regulation context

The season has three regulatory epochs, and fingerprints from earlier epochs are down-weighted when predicting in later ones because they aren't directly comparable.

**Epoch A (R1–R3).** Original rules: higher harvest cap, lower superclip ceiling, a Mercedes compression-ratio advantage active.

**Epoch B (R4–R5).** Per-circuit qualifying harvest limits formalised (5–9 MJ) and the superclip ceiling raised. Mercedes advantage still active.

**Epoch C (R6 onward).** A compression-ratio hot-test rule closes the Mercedes loophole, and the ADUO allocations take effect — Red Bull Ford is the ICE benchmark, with Mercedes, Ferrari, Honda, and Audi receiving development upgrades that deploy at different rounds (Audi R7, Ferrari R8, Honda R12; Mercedes allocated but holding its token).

---

## What the metrics mean

| Metric | Captures |
|---|---|
| `lap_time_gap_pct` | Combined package performance: power unit, chassis, aero, driver |
| `straight_speed_delta_kph` | Straight-line output — combined PU and chassis drag, not ICE alone |
| `corner_speed_delta_kph` | Mechanical grip and downforce (see the corner-delta caveats above) |
| `braking_harvest_ratio` | Energy-recovery aggressiveness vs the theoretical maximum |
| `regulation_epoch` | Which rule set the fingerprint was recorded under |

---

## Known limitations

The platform is explicit about where its signals are and aren't trustworthy.

Race-session harvest ratios are unreliable, because each driver's representative race lap comes from a different fuel load, tyre compound, and point in track evolution — a speed-based comparison against one reference car isn't valid there. Qualifying harvest ratios are used for all ERS signals in the predictor.

Corner deltas are measured over fixed distance windows from the fastest lap, so cars braking at materially different points are compared imperfectly, and the fast-corner class skews negative field-wide because corner detection is throttle- and brake-based rather than geometric. Per-driver values beyond ±40 km/h are suppressed in the UI, and the charts state the caveat.

The ADUO signal reflects the whole power unit as it appears in straight-line speed, not the ICE in isolation. Team chassis upgrades are tracked manually in `config.py` from sourced technical lists, with pre-upgrade fingerprints down-weighted automatically.

The AI features are grounded but not infallible — they read the model's own numbers under strict instruction and can still misread, so the UI labels every AI answer as advisory and points to the underlying data as the source of truth.

---

## Project structure

```
Home.py                      Streamlit entry point
pages/                       multipage app (Predictions, Race Analysis,
                             Teams & Drivers, Upgrades & News, ERS Explorer,
                             Ask the Engineer)
app/
  charts.py                  Plotly chart functions
  data_loader.py             cached loaders, teammate stats, display guards
models/
  track.py                   lap segmentation
  fingerprint.py             exact speed-delta fingerprinting
  optimizer.py               DP ERS optimiser
analysis/
  predictor.py               weighted prediction engine
  prediction_store.py        save/load predictions
  compare.py                 post-race accuracy
  llm.py                     Groq client, season digest, RAG features
pipeline/
  race_pipeline.py           end-to-end session processing
fetcher.py                   FastF1 telemetry, synthetic fallback, extracts
config.py                    circuits, regulations, upgrades, substitutions
run.py                       CLI entry point
store/                       committed fingerprints, telemetry, predictions, digest
```

---

## Tech stack

FastF1 for telemetry and timing, Streamlit for the app, Plotly for charts, NumPy and Pandas for processing, the Jolpica/Ergast API for live standings, and Groq (GPT-OSS-120B) for the natural-language layer.
