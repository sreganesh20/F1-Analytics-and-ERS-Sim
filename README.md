# LatentLap

**Formula 1 Inference & Intelligence**  
*What the timing screen doesn’t tell you.*

[![Live App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://latentlap-v1.streamlit.app/)

LatentLap is a Formula 1 analytics project built around a simple problem: some of the most interesting information in F1 is not public.

Rather than pretending otherwise, LatentLap starts from the timing, telemetry and results that **are** observable, derives carefully bounded signals from them, and keeps those signals separate from assumptions, optimisation outputs and predictions.

The project combines telemetry processing, performance fingerprinting, ERS inference, a constrained dynamic-programming optimiser, race-pace forecasting, reviewed race knowledge and provenance-constrained retrieval for natural-language explanation.

> **Core principle:** incomplete public observations → inference / reverse engineering → derived race information → analytics and comparison → prediction / optimisation → structured race knowledge → provenance-constrained retrieval → LLM explanation.

---

## Evidence first

LatentLap deliberately separates five different kinds of information:

| Evidence type | Meaning in LatentLap |
|---|---|
| **Observed** | Public timing, results and telemetry such as speed, throttle, brake, gear and RPM. |
| **Inferred** | Signals derived from observed data, including relative performance and ERS-behaviour proxies. |
| **Assumed** | Regulation constants, model coefficients and simplifications that must be supplied by the model. |
| **Optimised** | Theoretical outputs produced by the constrained ERS optimiser. |
| **Predicted** | Deterministic future relative-pace forecasts generated from historical fingerprints. |

Those categories are not interchangeable. In particular, LatentLap does **not** claim to recover private team telemetry, true battery state-of-charge, exact MGU-K deployment or a team’s real control strategy.

---

## What LatentLap does

### Race and season analysis

LatentLap processes 2026 Formula 1 session data into comparable performance fingerprints. The app exposes race-weekend pace, driver and team comparisons, teammate head-to-heads, straight-line and corner performance, finishing history, power-unit context and development timelines.

The primary pace signal is a driver’s lap-time gap to the fastest valid car in the same session. Speed deltas are derived relative to that session reference rather than treated as absolute car-performance measurements.

### ERS inference

Public F1 telemetry does not expose true battery SoC, exact recovered electrical energy or exact deployment. LatentLap therefore treats ERS analysis as an **inference problem**.

The fingerprinting layer uses observable braking and speed behaviour to build bounded proxy signals. For example, the braking-harvest signal compares kinetic-energy loss in usable braking zones with both a session reference and a theoretical segment opportunity. It represents apparent harvest aggressiveness relative to those references — **not measured electrical efficiency and not recovered MJ from the real car**.

Race-session ERS comparisons are intentionally restricted because representative race laps occur under different fuel loads, tyre states, traffic and track evolution. Qualifying-type sessions provide the cleaner comparative signal.

### Theoretical ERS optimisation

The ERS Explorer runs a Bellman dynamic-programming optimiser over a segmented lap.

The optimiser state includes battery state-of-charge and cumulative harvest budget. At each segment, it considers harvest/deploy actions while enforcing configured battery, harvest and power constraints. The objective uses modelled time benefit from deployment minus modelled time cost from harvesting.

That last sentence matters: the time-cost and time-benefit coefficients are **engineering heuristics**. The optimiser is therefore a constrained theoretical benchmark under explicit assumptions, not a reconstruction of a real team’s battery trace or secret deployment map.

When committed telemetry is available, the Explorer uses it as the observed lap input. If real telemetry is unavailable, the app can demonstrate the method on a synthetic circuit model and labels that fallback explicitly.

### Deterministic pace prediction

LatentLap predicts **relative pace**, not guaranteed finishing order.

For each driver, accepted historical fingerprints are weighted using circuit similarity, recency, regulation epoch, session type, fingerprint confidence and confirmed persistent-upgrade relevance. Qualifying-type forecasts can also use the inferred braking-harvest signal. Weighted historical dispersion is converted into an uncertainty band.

The saved prediction JSON is the source of truth. The language model can explain a stored prediction, but it cannot alter, re-rank or recompute it.

Incidents, safety cars, reliability, tactical strategy calls and other race events are outside the pace model unless explicitly represented in committed evidence.

LatentLap does not manufacture historical predictions for rounds where forecasts were never actually run and saved.

### Ask the Engineer

Ask the Engineer is the explanation layer over LatentLap’s committed evidence.

At query time it can retrieve deterministic session analytics, saved predictions, implementation-grounded methodology and **human-approved race dossiers**. It does not perform a live web search at question time, and the prompt explicitly forbids filling missing 2026 facts from pretrained model memory.

If the available evidence is insufficient, the expected behaviour is to state that limitation instead of improvising an answer.

Driver and team identity is deterministic and round-aware. Race classification is authoritative for winner, podium and finishing-order claims; representative race pace cannot be substituted for official results.

Reviewed race dossiers may add externally reported context, but only approved dossiers are eligible for retrieval and their source provenance is stored with the dossier.

---

## The app

LatentLap is a six-page Streamlit application:

| Page | Purpose |
|---|---|
| **Home** | Project philosophy, season state, navigation and latest saved forecast preview. |
| **Predictions** | Saved qualifying / sprint / race-pace forecasts, uncertainty, weekend notes and grounded per-driver explanations. |
| **Race Analysis** | Session-level fingerprints and race-weekend performance analysis. |
| **Teams & Drivers** | Teammate comparisons, driver trends, straight-vs-corner analysis, corner profiles and power-unit views. |
| **Upgrades & News** | Reviewed development context, upgrade timelines, PU/ADUO state and race commentary. |
| **ERS Explorer** | Theoretical harvest/deploy optimisation with explicit observed / inferred / assumed / optimised separation. |
| **Ask the Engineer** | Free-text questions answered from committed LatentLap evidence and approved knowledge. |

The UI is designed so a casual F1 viewer can start with a question rather than with a model name, while the methodology remains available for deeper inspection.

---

## Data and architecture

```text
Public F1 timing / telemetry / results
        │
        ▼
fetcher.py
        │
        ├── committed telemetry extracts
        ▼
models/track.py
        │  throttle/brake-based lap segmentation
        ▼
models/fingerprint.py
        │  relative pace + speed deltas + ERS-behaviour proxies
        ▼
data/race_store.py  ───────────────► store/
        │                               │
        │                               ├── session fingerprints
        │                               ├── telemetry extracts
        │                               ├── saved predictions
        │                               └── season digest
        │
        ├────────► analysis/predictor.py
        │              deterministic relative-pace forecasts
        │
        ├────────► models/optimizer.py
        │              theoretical ERS strategy
        │
        └────────► data/race_knowledge.py
                       deterministic weekend snapshots
                       + approved race dossiers
                                │
                                ▼
                         analysis/llm.py
                    provenance-constrained explanation
                                │
                                ▼
                         Streamlit application
```

The separation is intentional: deterministic Python and committed data establish analytical facts; the LLM explains retrieved evidence.

---

## Race knowledge and provenance

LatentLap stores one structured dossier per completed race weekend under `data/race_dossiers/`.

A dossier can contain weekend summaries, session progression, key moments, selective driver/team insights, strategy and conditions, technical context, a deterministic performance snapshot, prediction review, knowledge limits and source references.

Only dossiers with `review_status == "approved"` are eligible for Ask the Engineer retrieval.

Deterministic performance snapshots are hydrated from the committed session store rather than hand-written into the narrative. This helps keep calculated metrics separate from reported context.

Prediction provenance is also time-aware: information learned later in a weekend should not be presented as though it was known when an earlier forecast was saved.

---

## A useful engineering failure: the corner-delta problem

One of the most important fixes in LatentLap came from a result that looked plausible enough to ship but did not survive interrogation.

An early corner-performance ranking placed Audi — roughly the seventh-fastest car by lap-time pace in the investigated sample — at the top of the corner ranking. The underlying problem had two parts.

First, the original loader constructed each driver’s distance axis by integrating their own speed trace. Small errors accumulated along the lap, causing fixed-distance corner windows to represent slightly different pieces of track for different cars. In one Silverstone investigation, the drift reached roughly 56 metres across the field.

Second, the original corner-delta calculation used a first-order time-ratio approximation that exaggerated slow outliers.

The fix switched the telemetry path to the track-aligned distance generated by FastF1 telemetry interpolation, replaced the approximation with exact distance-over-time mean speed, and aggregated segment deltas with a median rather than a mean. In the validation sample, the worst corner-delta outlier fell from about -80.8 km/h to -23.8 km/h and the corner ranking’s agreement with overall pace improved substantially.

A limitation still remains: the current corner detector is based on throttle and brake behaviour rather than X/Y track geometry. Flat-out corners can therefore be classified as straights, and cars braking at materially different locations are compared imperfectly. Extreme corner deltas are suppressed in the UI rather than presented as trustworthy facts. Geometric corner detection is a future improvement, not hidden inside the current release.

---

## Prediction integrity

A few design rules are intentionally strict:

- **Saved deterministic predictions are authoritative.** The LLM only explains them.
- **Pace ranking is not finishing order.** Race outcomes require official classification evidence.
- **Driver identity is round-aware.** Temporary substitutions and team changes are resolved deterministically.
- **Upgrade context is not causal proof.** An upgrade arriving during a faster weekend does not by itself prove the upgrade caused the improvement.
- **Sprint and Grand Prix sessions are distinct contexts.** Q, SQ, S and R are not casually mixed or subtracted as though they were identical measurements.
- **Missing evidence stays missing.** LatentLap prefers an explicit limitation over unsupported 2026 model-memory filling.

---

## Local setup

```bash
git clone https://github.com/sreganesh20/F1-Analytics-and-ERS-Sim.git
cd F1-Analytics-and-ERS-Sim

python -m venv .venv
```

Activate the environment:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Install dependencies and launch the app:

```bash
pip install -r requirements.txt
streamlit run Home.py
```

The committed `store/` contains the derived artifacts needed for the deployed analytical views. FastF1 is used when pulling or rebuilding session telemetry locally.

### Optional AI features

Ask the Engineer and prediction explanations require a Groq API key.

Create `.streamlit/secrets.toml` locally:

```toml
GROQ_API_KEY = "your_key_here"
```

`secrets.toml` is gitignored. Without the key, the deterministic analytics remain available and the AI entry points disable cleanly.

The default model is configured in `analysis/llm.py`.

---

## Weekend workflow

A typical completed-weekend refresh is:

```bash
# Build qualifying fingerprints for one circuit
python run.py pipeline italy

# Build race fingerprints
python run.py race italy

# Refresh commit-sized telemetry extracts
python run.py extract-telemetry italy

# Generate and save the next forecast when appropriate
python run.py predict madrid

# Rebuild compact season context used by AI features
python run.py build-digest

# Compare a saved forecast with the eventual result
python run.py compare italy
```

Sprint weekends automatically use the corresponding SQ / S paths where configured.

After generation, inspect the new artifacts before committing them. Race dossiers are reviewed separately and should only be marked approved after their narrative and provenance have been checked.

---

## Command reference

| Command | Purpose |
|---|---|
| `pipeline <circuit>` | Process qualifying fingerprints; sprint qualifying is included where configured. |
| `race <circuit>` | Process race fingerprints; sprint race is included where configured. |
| `predict <circuit>` | Generate deterministic saved pace forecasts. |
| `extract-telemetry [circuit]` | Build commit-sized telemetry extracts from local FastF1 data. |
| `build-digest` | Refresh the compact committed season digest. |
| `compare <circuit>` | Compare a saved forecast with post-event actual data. |
| `store` | Print the current committed race-store summary. |
| `test` | Run the lightweight optimiser validation path. |
| `viz [chart]` | Regenerate optional static visualisations. |

---

## Project structure

```text
Home.py                         Streamlit entry point
pages/                          public application pages
app/
  ui.py                         shared LatentLap UI system
  charts.py                     Plotly visualisations
  data_loader.py                cached loading and display helpers
models/
  track.py                      telemetry segmentation
  fingerprint.py                performance + ERS proxy construction
  optimizer.py                  constrained Bellman ERS optimiser
analysis/
  predictor.py                  deterministic relative-pace forecasting
  prediction_store.py           saved prediction I/O
  compare.py                    post-event forecast comparison
  llm.py                        grounded retrieval + Groq explanation layer
data/
  race_store.py                 committed session-store access
  race_knowledge.py             approved dossier + deterministic snapshot access
  race_dossiers/                reviewed race-weekend knowledge
  upgrade_history.py            canonical development history
pipeline/
  race_pipeline.py              session processing pipeline
fetcher.py                      FastF1 telemetry acquisition / extracts
config.py                       season, regulations, lineups and model configuration
run.py                          CLI entry point
store/                          committed fingerprints, telemetry, predictions, digest
viz/                            optional standalone visualisation scripts
```

---

## Known limitations

LatentLap is explicit about the boundaries of the current release.

**ERS is inferred, not directly observed.** Public data does not expose true battery SoC, exact recovered energy or exact deployment. ERS fingerprint fields are proxy signals derived from observable behaviour.

**The optimiser is theoretical.** Its state constraints are explicit, but its time benefit/cost coefficients are modelling assumptions. Its SoC trace is an internal model state, not hidden team telemetry.

**Race-lap comparability is limited.** Fuel load, tyre compound, traffic, management and track evolution make representative race laps unsuitable for some cross-driver telemetry comparisons. Race pace is treated more conservatively than qualifying telemetry.

**Corner detection is not geometric yet.** The current throttle/brake segmentation misses some flat-out geometry and fixed windows can compare cars imperfectly when braking points differ.

**Straight-line speed is not an ICE dyno measurement.** The signal contains the combined effect of power-unit output, aero drag, setup and other vehicle factors.

**Predictions are relative-pace models.** They do not attempt to predict every stochastic race event.

**The LLM is an explanation layer.** Guardrails and provenance materially reduce unsupported answers, but generated language should still be checked against the displayed deterministic evidence for high-confidence use.

---

## Tech stack

- **Python**
- **FastF1** for Formula 1 timing and telemetry access
- **Pandas / NumPy** for data processing
- **Streamlit** for the application
- **Plotly** for interactive visualisation
- **Groq / GPT-OSS-120B** for grounded natural-language explanation

---

## Project status

LatentLap is an actively developed 2026 Formula 1 inference and analytics project. The current public release focuses on transparent inference, deterministic pace analysis, ERS exploration, saved predictions and grounded explanation.

Future work is evaluated separately from the release branch; speculative modelling ideas are not presented as implemented features.

---

## Disclaimer

LatentLap is an independent analytics project and is not affiliated with Formula 1, the FIA, any Formula 1 team, FastF1 or Groq. Formula 1 team and event names are used only to describe publicly available motorsport data and analysis.
