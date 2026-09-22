---
title: DRISHTI
emoji: 🚦
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 8501
pinned: false
short_description: Parking-induced congestion intelligence for Bengaluru
---

# दृष्टि — DRISHTI

### Digital Real-time Intelligence for Smart Hotspot & Traffic Insights

**A decision-support platform that helps traffic police _see, predict, and act on_ parking-induced congestion.**

> *हर सड़क पर नज़र, हर सफ़र आसान* — a watch on every road, every journey easier.

🔗 **Live demo:** https://data-aimers-drishti.hf.space
*(Demo login — `admin` / `admin123` or `officer` / `officer123`)*

Built for the **Flipkart Gridlock Hackathon 2.0** (Theme 1 — Parking-Induced Congestion) by **Team Data AImers**, entirely on the provided dataset: **~298,445 violations across 2,534 zones**.

---

## The problem

On-street and spillover parking near commercial areas, metro stations, and event venues chokes carriageways and junctions. Today, enforcement is **patrol-based and reactive**, there is **no heatmap of which violations actually impact traffic**, and it is **hard to prioritise enforcement zones**. DRISHTI closes that gap.

## What it does

| Capability | What it delivers |
|---|---|
| 🗺️ **Impact map (CII)** | A transparent Congestion Impact Index ranks every zone 0–100 |
| 🔮 **Forecast** | LightGBM predicts next-day hotspots — **MAE 0.708, ~34% better than baseline** |
| ⚠️ **Live alerts + dispatch** | Real-time, **cross-officer** alert + enforcement-dispatch board |
| 🚓 **Tow / crane + SLA** | Nearest-unit assignment with time-to-clear tracking |
| 🧪 **What-if simulator** | Projects the CII drop from signage / bollards / towing — auditable |
| 🗓️ **Patrol planner** | Tomorrow's hotspots grouped into a deployable morning briefing |
| 🚗 **Repeat offenders** | 34.2% of violations traced to repeat plates; auto-tiered escalation |
| 🎪 **Event mode** | Surge projection around venues (Chinnaswamy, malls, metro) |
| 📈 **Trends** | Temporal, hourly, and vehicle-mix analytics |

Plus **trilingual UI + voice (English / ಕನ್ನಡ / हिन्दी)** for real field adoption, and a **secure role-based login**.

---

## Core IP — the Congestion Impact Index (CII)

The dataset has violations but no raw traffic flow, so we built a **transparent proxy** for congestion impact:

```
CII_raw = ( 0.45 · rank(severity-weighted volume)
          + 0.30 · rank(persistence)
          + 0.25 · rank(peak-hour concentration) )
          × (1 + 0.5 · junction_share)

CII = rank-normalise(CII_raw) → 0–100
```

Every term is published and auditable — a government body can trust and inspect it, not a black box. It surfaces a clear insight: **the top ~100 zones drive about 40% of all violations.**

## Predict — reactive → proactive

A **LightGBM** model forecasts next-day hotspot intensity per zone:

- **MAE 0.708** — about **34% better** than the same-weekday baseline (1.078).
- **Leak-aware temporal validation** (cell × day panel, lags 1/7/14/28, rolling features).
- **Objective ablation:** L1 chosen because it directly optimises the error metric on skewed counts — it beat L2, Huber, Poisson, and Tweedie on the same split.

## Act — the Operations Command Suite

What turns DRISHTI from a dashboard into a command tool:

- **Cross-officer dispatch board** — dispatches are written to a shared store and appear on every officer's screen in near-real-time (live feed + notification + auto-refresh).
- **Tow / crane dispatch + SLA** — the nearest available unit is auto-assigned by distance; resolving a job logs time-to-clear as a governance KPI.
- **What-if simulator** — recomputes the **exact published CII formula** on intervention-adjusted inputs to project the resulting CII drop and new city rank.
- **Patrol-beat & shift planner** — the forecast grouped by police-station jurisdiction, with shift windows and units to deploy, exportable as a CSV briefing.
- **Repeat-offender escalation** — chronic plates auto-tiered (🔴 Chronic → 🔵 Watchlist) with recommended actions and an e-challan notice draft.
- **Event mode** — H3 k-ring spatial query around a venue × an event multiplier to project surge zones for pre-positioning.

---

## Architecture

A heavy **offline pipeline** crunches the raw CSV into tiny artifacts; the deployed app reads **only** those small files — so it's fast and runs on a free tier. The same engine becomes real-time by swapping the data source.

```
Raw CSV ──► [ offline pipeline ] ──► small artifacts (Parquet/JSON, <1 MB) ──► [ Streamlit app ] ──► Docker / Hugging Face Spaces
  clean & geocode · H3 indexing · per-cell stats · CII · LightGBM forecast · offender + trend analytics
```

*Production path: connect ANPR / e-challan / FASTag feeds → streaming compute → push alerts to field officers. Same engine, swapped source.*

## Tech stack

**Core:** Python · pandas · NumPy
**ML / forecast:** LightGBM (L1, leak-aware CV)
**Geospatial:** H3 · pydeck · haversine
**UI / viz:** Streamlit · Plotly
**Accessibility:** gTTS · indic-transliteration · streamlit-mic-recorder
**Deploy:** Docker · Hugging Face Spaces · GitHub

## Project structure

```
DRISHTI/
├── app.py                   # entire Streamlit UI (9 sections, login, voice, theming)
├── Dockerfile               # HF Spaces deploy (Streamlit on :8501)
├── requirements.txt
├── .streamlit/config.toml   # purple light/dark themes + server config
├── src/
│   ├── build_artifacts.py   # offline pipeline orchestrator (raw CSV → artifacts)
│   ├── config.py            # paths, CII weights, constants
│   ├── data_prep.py         # clean + geocode raw violations
│   ├── features.py          # H3 spatial indexing + feature engineering
│   ├── hotspots.py          # per-cell statistics
│   ├── impact_index.py      # the Congestion Impact Index (CII)
│   ├── model.py             # LightGBM next-day forecast
│   ├── offenders.py         # repeat-offender analytics
│   ├── trends.py            # temporal aggregates
│   ├── ops.py               # ops suite: dispatch, tow/SLA, what-if, patrol, event, escalation
│   └── i18n.py              # EN / Kannada / Hindi strings + transliteration
├── data/
│   ├── processed/           # small artifacts the app reads (committed)
│   └── raw/                 # violations.csv (gitignored — not in repo)
└── experiments/             # MAE objective-ablation scripts
```

## Run it locally

```bash
git clone https://github.com/data-aimers/drishti.git
cd drishti

python -m venv venv
source venv/bin/activate          # Windows: .\venv\Scripts\activate

pip install -r requirements.txt
python -m streamlit run app.py    # opens at http://localhost:8501
```

Log in with `admin` / `admin123` (or `officer` / `officer123`). The app reads the pre-computed artifacts in `data/processed/`, so it runs without the raw data.

**Rebuilding the artifacts** (optional — needs `data/raw/violations.csv`):

```bash
python -m src.build_artifacts
```

## Notes

- **Dataset only.** Built entirely on the provided Flipkart dataset; no external data is used.
- **Honest framing.** The dispatch fleet and the simulator's lever effects are a clearly-labelled **simulation layer with transparent, configurable assumptions** — production-ready the moment live GPS units and e-challan feeds connect.

## Roadmap

Live feed integration → streaming alerts → push notifications to field officers → city-wide rollout. The engine is **city-agnostic** — retrain on any city's data.

## Team

**Data AImers** — Flipkart Gridlock Hackathon 2.0.

---

*दृष्टि — DRISHTI · हर सड़क पर नज़र, हर सफ़र आसान*
