"""Operational layer for DRISHTI.

Backs the six command-and-control features:
  1. cross-officer dispatch board   -> file-backed shared store (across sessions)
  2. tow / crane fleet + nearest-unit + time-to-clear SLA
  3. what-if intervention projection (transparent, tied to the CII weights)
  4. patrol-beat & shift planning from the forecast (grouped by police_station)
  5. repeat-offender escalation tiers
  6. event-mode surge projection around a chosen zone (H3 k-ring)

Everything is computed from the provided dataset. The tow fleet and dispatch
records are an operational SIMULATION layer (not external data).
"""
import json
import math
import os
import tempfile
import time

# ----------------------------------------------------------------------
# 1 + 4.  shared dispatch board (cross-session, cross-officer)
# /tmp is writable on HF Spaces and shared across all sessions of the container.
# ----------------------------------------------------------------------
DISPATCH_PATH = os.path.join(tempfile.gettempdir(), "drishti_dispatch.json")


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)          # atomic on the same filesystem


def read_dispatches():
    data = _read_json(DISPATCH_PATH, [])
    return data if isinstance(data, list) else []


def add_dispatch(rec):
    data = read_dispatches()
    rec["id"] = (max([r.get("id", 0) for r in data]) + 1) if data else 1
    data.insert(0, rec)
    _write_json(DISPATCH_PATH, data[:200])
    return rec["id"]


def resolve_dispatch(did):
    data = read_dispatches()
    now = time.time()
    for r in data:
        if r.get("id") == did and r.get("status") != "Resolved":
            r["status"] = "Resolved"
            r["resolved_ts"] = now
            r["clear_min"] = round((now - r.get("ts", now)) / 60.0, 1)
    _write_json(DISPATCH_PATH, data)


def clear_dispatches():
    _write_json(DISPATCH_PATH, [])


# ----------------------------------------------------------------------
# 2.  tow / crane fleet (simulated) + nearest-unit assignment + distance
# ----------------------------------------------------------------------
def make_fleet(hotspots):
    """Anchor a small simulated fleet at spread-out points across the data bbox."""
    lat0, lat1 = float(hotspots["lat"].min()), float(hotspots["lat"].max())
    lon0, lon1 = float(hotspots["lon"].min()), float(hotspots["lon"].max())
    names = ["Tow-North", "Tow-South", "Tow-East", "Tow-West", "Crane-Central", "Tow-SE"]
    frac = [(0.78, 0.50), (0.22, 0.50), (0.50, 0.82), (0.50, 0.18), (0.50, 0.50), (0.32, 0.72)]
    fleet = []
    for nm, (fy, fx) in zip(names, frac):
        fleet.append({"unit": nm,
                      "lat": lat0 + fy * (lat1 - lat0),
                      "lon": lon0 + fx * (lon1 - lon0)})
    return fleet


def haversine(la1, lo1, la2, lo2):
    R = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_unit(lat, lon, fleet):
    best, bd = None, 1e9
    for u in fleet:
        d = haversine(lat, lon, u["lat"], u["lon"])
        if d < bd:
            best, bd = u, d
    return best, round(bd, 2)


# ----------------------------------------------------------------------
# 3.  what-if intervention projection
# CII is a weighted sum of (volume, persistence, peak) components, so the
# headline CII drop is just the weighted blend of each lever's effect.
# ----------------------------------------------------------------------
INTERVENTIONS = {
    "No-parking signage":      {"volume": 0.25, "persistence": 0.05, "peak": 0.10},
    "Bollards / barricade":    {"volume": 0.45, "persistence": 0.25, "peak": 0.15},
    "Towing drive":            {"volume": 0.15, "persistence": 0.05, "peak": 0.35},
    "Dedicated parking bay":   {"volume": 0.40, "persistence": 0.30, "peak": 0.20},
    "Static enforcement post": {"volume": 0.30, "persistence": 0.35, "peak": 0.30},
}


def combine_interventions(selected):
    """Combine chosen levers multiplicatively per component (diminishing returns)."""
    comp = {"volume": 0.0, "persistence": 0.0, "peak": 0.0}
    for name in selected:
        eff = INTERVENTIONS.get(name, {})
        for k in comp:
            comp[k] = 1 - (1 - comp[k]) * (1 - eff.get(k, 0.0))
    return comp


def whatif_new_cii(cii, reductions, weights):
    """reductions: component -> fraction (0-1). weights: meta cii_weights dict."""
    wv = weights.get("weighted_volume", weights.get("volume", 0.45))
    wp = weights.get("persistence", 0.30)
    wk = weights.get("peak_share", weights.get("peak", weights.get("peak_concentration", 0.25)))
    s = (wv + wp + wk) or 1.0
    wv, wp, wk = wv / s, wp / s, wk / s
    eff = (wv * reductions.get("volume", 0)
           + wp * reductions.get("persistence", 0)
           + wk * reductions.get("peak", 0))
    eff = max(0.0, min(0.95, eff))
    return round(float(cii) * (1 - eff), 1), round(eff * 100, 1)


def new_rank(new_cii, all_cii_desc):
    """Rank a projected CII against the existing distribution (1 = worst)."""
    above = sum(1 for c in all_cii_desc if c > new_cii)
    return above + 1


# ----------------------------------------------------------------------
# 5.  repeat-offender escalation tiers (calibrated to the data's 11-55 range)
# ----------------------------------------------------------------------
def escalation_tier(n):
    """Return (tier_label, icon, recommended_action)."""
    if n >= 40:
        return ("Chronic — license/RC review", "🔴", "RTO referral + court summons")
    if n >= 25:
        return ("Habitual — court summons", "🟠", "Summons + cumulative penalty")
    if n >= 16:
        return ("Repeat — escalated fine", "🟡", "Escalated fine + formal notice")
    return ("Watchlist — formal notice", "🔵", "Formal notice via e-challan")


# ----------------------------------------------------------------------
# 6.  patrol-beat & shift planning (beats = police_station jurisdictions)
# ----------------------------------------------------------------------
def patrol_plan(forecast_df, hotspots_df, top_zones=40):
    cols = ["h3", "police_station", "peak_share", "location", "cii", "junction_name"]
    h = hotspots_df[cols].copy()
    plan = forecast_df.merge(h, on="h3", how="left", suffixes=("", "_h"))
    plan = plan.dropna(subset=["police_station"])
    plan = plan.sort_values("pred_intensity", ascending=False).head(top_zones).copy()

    def shift(ps):
        try:
            ps = float(ps)
        except Exception:
            return "All-day rotating"
        if math.isnan(ps):
            return "All-day rotating"
        return "Peak hours (08-11, 17-21)" if ps >= 0.45 else "All-day rotating"

    plan["shift"] = plan["peak_share"].apply(shift)
    pmax = plan["pred_intensity"].max() or 1.0
    plan["units"] = (plan["pred_intensity"] / pmax * 2 + 1).round().astype(int)
    # prefer the merged location/junction if present
    if "location_h" in plan.columns:
        plan["location"] = plan["location"].fillna(plan["location_h"])
    return plan


# ----------------------------------------------------------------------
# 7.  event-mode surge (H3 k-ring around a chosen zone)
# ----------------------------------------------------------------------
def event_surge(hotspots_df, center_h3, k, multiplier):
    try:
        import h3
        try:
            ring = set(h3.grid_disk(center_h3, k))      # h3 v4
        except Exception:
            ring = set(h3.k_ring(center_h3, k))         # h3 v3
    except Exception:
        ring = {center_h3}
    sub = hotspots_df[hotspots_df["h3"].isin(ring)].copy()
    sub["surge_cii"] = (sub["cii"] * float(multiplier)).clip(upper=100).round(1)
    sub["delta"] = (sub["surge_cii"] - sub["cii"]).round(1)
    return sub.sort_values("surge_cii", ascending=False)
