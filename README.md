# F1 Analytics & ERS Simulator — 2026 Season

A telemetry-driven F1 analytics platform built on FastF1. Fingerprints every car's ERS behaviour from real qualifying and race data, runs a dynamic-programming optimizer to find the theoretically optimal energy strategy per circuit, and produces race predictions from the combined signal.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://f1-analytics-and-ers-sim-qvp7tgfjxrwmbz4zs9nxr7.streamlit.app/)

---

## What it does

### ERS Fingerprinting
Pulls real telemetry from FastF1 for every driver in every session. Segments each lap into straights, braking zones, corners, and superclip zones. Computes per-driver metrics:
- Braking harvest ratio (observed KE recovery vs theoretical maximum)
- Straight-line speed delta vs session leader
- Corner speed delta vs session leader
- Time lost per track sector

Fingerprints are tagged with a **regulation epoch** — the 2026 season had three distinct rule states (pre-Miami, Miami/Canada, post-Monaco) with different harvest caps and superclip ceilings.

### Dynamic Programming Optimizer
Given a circuit's track segmentation, solves for the theoretically optimal lap-by-lap ERS harvest and deploy strategy using Bellman/DP over a discretised battery SoC state space. Respects:
- FIA per-circuit, per-session harvest limits (5–9 MJ depending on circuit)
- Battery capacity (4 MJ)
- MGU-K power ceiling (350 kW)
- Aero density correction for altitude circuits (Mexico, Brazil)

### Race Prediction
Predicts qualifying and race pace order for upcoming rounds by:
1. Loading all stored fingerprints for the season
2. Weighting each by circuit similarity, recency, regulation epoch, and team chassis upgrade status
3. Applying a harvest ratio correction to the predicted delta
4. Generating confidence intervals from cross-circuit variance

Predictions are split: **qualifying** (Q+SQ sessions) and **race pace** (R+S sessions) separately — they often diverge meaningfully.

---

## 2026 Architecture

| Component | What it captures |
|---|---|
| `lap_time_gap_pct` | Combined package performance (PU + chassis + aero + driver) |
| `straight_speed_delta_kph` | Straight-line output — combined PU + chassis drag (not ICE-only) |
| `corner_speed_delta_kph` | Mechanical grip + downforce |
| `braking_harvest_ratio` | ERS recovery aggressiveness vs theoretical max |
| `regulation_epoch` | Which rule set the fingerprint was recorded under |

The model knows about the 2026 ADUO system (Red Bull Ford = ICE benchmark, Mercedes/Ferrari/Honda/Audi get upgrade allocations), team chassis upgrades across all 11 teams, and the mid-season rule changes at Miami (R4) and Monaco (R6).

---

## Streamlit App

Five pages:

| Page | What you see |
|---|---|
| **Home** | Championship standings (live via API) · PU performance evolution chart |
| **Predictions** | Qualifying and race pace predictions side by side · cumulative race gap · driver notes |
| **Race Analysis** | Round selector · per-session fingerprint table · DNF tracking |
| **Teams & Drivers** | Teammate H2H comparison · straight vs corner scatter · corner profile ranking · PU analysis |
| **ERS Explorer** | Interactive optimizer — pick any circuit, adjust harvest limit and starting SoC, see optimal strategy |
| **Upgrades & News** | All 11 team upgrade timelines (confirmed, sourced) · race commentary |

---

## Local Setup

```bash
git clone https://github.com/sreganesh20/F1-Analytics-and-ERS-Sim.git
cd F1-Analytics-and-ERS-Sim
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
streamlit run Home.py
```

### Pulling race data

```bash
# Qualifying fingerprints
python run.py pipeline australia
python run.py pipeline china
# ... etc for each circuit

# Race fingerprints
python run.py race australia
python run.py race china
# ... etc

# Generate predictions for next round
python run.py predict netherlands

# After the race — compare vs actual
python run.py compare netherlands

# Regenerate all charts
python run.py viz all
```

FastF1 caches sessions to `cache/` on first load. Subsequent runs use the local cache. The `store/` folder contains pre-computed fingerprints for R1–R11 committed to the repo — the app reads these directly without needing FastF1.

---

## Data Pipeline

```
FastF1 API
    ↓
fetcher.py          pull real telemetry per driver per session
    ↓
models/track.py     segment lap into straights, braking, corners, superclip
    ↓
models/optimizer.py  DP optimizer → theoretical optimal harvest/deploy
    ↓
models/fingerprint.py compare car telemetry vs reference → fingerprint metrics
    ↓
data/race_store.py  persist to store/ as JSON
    ↓
analysis/predictor.py  weighted prediction for upcoming round
    ↓
Streamlit app       interactive visualisation
```

---

## 2026 Regulation Context

The 2026 season has three regulatory epochs that affect fingerprint comparability:

**Epoch A (R1–R3, Australia/China/Japan)**
Original rules: 8.5 MJ harvest cap, 250 kW superclip ceiling. Mercedes compression ratio advantage active.

**Epoch B (R4–R5, Miami/Canada)**
Miami rule package: per-circuit qualifying harvest limits formalised (5–9 MJ), superclip raised to 350 kW. Mercedes compression advantage still active.

**Epoch C (R6+, Monaco onwards)**
Compression ratio hot-test rule (Article C5.4.3 amended) closes Mercedes loophole. ADUO results published: Red Bull Ford is the ICE benchmark. Level PU playing field.

Fingerprints from earlier epochs are down-weighted when predicting in later epochs.

---

## Project Structure

```
├── Home.py                   Streamlit entry point
├── pages/                    Streamlit multipage app
│   ├── 1_Predictions.py
│   ├── 2_Race_Analysis.py
│   ├── 3_Teams_and_Drivers.py
│   ├── 4_Upgrades_and_News.py
│   └── 5_ERS_Explorer.py
├── app/
│   ├── charts.py             Plotly chart functions
│   └── data_loader.py        Cached data loading helpers
├── models/
│   ├── track.py              Lap segmentation
│   ├── optimizer.py          DP ERS optimizer
│   └── fingerprint.py        Car ERS fingerprinting
├── analysis/
│   ├── predictor.py          Race prediction engine
│   ├── prediction_store.py   Save/load predictions
│   └── compare.py            Post-race accuracy analysis
├── pipeline/
│   └── race_pipeline.py      End-to-end session processing
├── data/
│   ├── race_store.py         Fingerprint persistence
│   ├── fetcher.py            FastF1 telemetry fetcher
│   └── commentary.json       Manual race summaries
├── store/                    Pre-computed fingerprints (R1–R11)
├── config.py                 Circuits, regulations, team upgrades
└── run.py                    CLI entry point
```

---

## Known Limitations

- **Race session harvest ratios are unreliable.** Each driver's representative lap comes from a different race moment (fuel load, tyre compound, track evolution). Speed-based KE comparison vs a single reference car is not valid. Qualifying harvest ratios are used for all ERS signals in the predictor.
- **ADUO measures ICE only**, not the full power unit. The straight-line speed delta from our fingerprints captures combined PU + chassis drag — it is not a pure ICE signal.
- **Team chassis upgrades** are tracked manually in `config.py` based on sourced technical lists. Fingerprints from before a significant upgrade are down-weighted automatically.
- **Circuit layout map** (Option B) is on the roadmap — requires a local `python run.py layout <circuit>` command to store X/Y GPS coordinates from FastF1.

---

## Tech Stack

- **FastF1** — F1 telemetry and timing data
- **Streamlit** — web app framework
- **Plotly** — interactive charts
- **NumPy / Pandas** — data processing
- **Jolpica API** — live championship standings

---

*Data updates after each race weekend. Run the pipeline locally, push to GitHub, Streamlit Cloud redeploys automatically.*
