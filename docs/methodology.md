# Methodology — Congestion Impact Index (CII)

## Problem framing
The brief asks us to *detect illegal-parking hotspots and quantify their impact
on traffic flow*. The dataset contains 298k+ parking-enforcement records with
location, time, and violation type, but **no direct traffic-speed/volume
measurement**. Rather than claim a flow metric we do not have, we build a
**transparent proxy** for flow impact, derived only from enforcement data, with
every weight exposed and defensible.

## Pipeline
1. **Clean** — keep records inside the Bengaluru bounding box with valid
   timestamps; parse the multi-label `violation_type`; keep only parking-
   relevant violations.
2. **Spatial unit** — index every record to an **H3 resolution-9 hexagon**
   (~174 m edge ≈ a block / deployable patrol zone). Deterministic and
   map-friendly.
3. **Per-cell statistics** — severity-weighted volume, active-day persistence,
   peak-hour concentration, junction proximity.
4. **CII** — combine the components (below).
5. **Forecast** — a LightGBM model predicts next-day intensity per cell.

## Severity weighting
Each violation type is weighted by how much it physically blocks *moving*
traffic (not legal severity):

| Violation | Weight | Why |
|---|---|---|
| Parking in a main road | 1.00 | blocks the carriageway |
| Near road crossing / traffic light | 0.90 | blocks turning / sightlines |
| Double parking | 0.85 | removes a live lane |
| Near bus-stop / school / hospital | 0.70 | high-churn frontage |
| On footpath | 0.50 | pushes pedestrians into the road |
| Wrong parking | 0.50 | partial obstruction |
| No parking | 0.40 | designated-clear zone |

A record's severity is the **max** weight across its violations.

## The index
For each cell, with rank-normalised components in [0, 1]:

```
base = 0.45·volume + 0.30·persistence + 0.25·peak_concentration
CII  = base × (1 + 0.50·junction_share)          # then scaled to 0–100
```

- **Volume** — total severity-weighted violations (how bad, weighted).
- **Persistence** — active days ÷ total days. Separates a *chronic* daily
  bottleneck from a one-off spike. (In this data the worst cells are active
  ~149/151 days.)
- **Peak concentration** — share of violations in commute windows (08–11,
  17–20). A blockage that happens exactly at rush hour hurts flow more.
- **Junction proximity** — amplifies cells near junctions, where a blockage
  cascades upstream.

All weights live in `src/config.py` and can be re-tuned in seconds.

## Forecast model
LightGBM regression on a (cell × day) panel. Features: cell location + junction
share, calendar (day-of-week, month, weekend), and **lag/rolling** features
(1/7/14/28-day lags, 7/28-day rolling mean & max). Target: next-day
severity-weighted intensity. Validated on the final 21 days, compared against a
naive "same weekday last week" baseline.
