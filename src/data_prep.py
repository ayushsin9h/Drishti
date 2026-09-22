"""Load and clean the raw violation data into a tidy parking-records frame."""
import ast
import json

import pandas as pd

from src import config


def _parse_list(x):
    """`violation_type` arrives as a JSON-ish string like ["NO PARKING"]."""
    if isinstance(x, list):
        return x
    if not isinstance(x, str) or not x.strip():
        return []
    try:
        return json.loads(x)
    except Exception:
        try:
            return ast.literal_eval(x)
        except Exception:
            return []


def record_severity(violations):
    """Max flow-disruption weight across a record's violations (0 if none parking)."""
    return max((config.PARKING_SEVERITY.get(v, 0.0) for v in violations), default=0.0)


def _is_peak(hour):
    return any(lo <= hour < hi for lo, hi in config.PEAK_WINDOWS)


def load_clean():
    """Return one row per parking violation with engineered time/severity fields."""
    df = pd.read_csv(config.DATA_RAW, low_memory=False)

    # --- coordinates: drop missing / out-of-Bengaluru ---
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[df["latitude"].between(config.LAT_MIN, config.LAT_MAX)
            & df["longitude"].between(config.LON_MIN, config.LON_MAX)].copy()

    # --- timestamps -> IST ---
    df["created_dt"] = pd.to_datetime(df["created_datetime"], errors="coerce", utc=True)
    df = df.dropna(subset=["created_dt"]).copy()
    df["ts"] = df["created_dt"].dt.tz_convert(config.TZ)
    df["date"] = df["ts"].dt.date
    df["hour"] = df["ts"].dt.hour
    df["dow"] = df["ts"].dt.dayofweek
    df["month"] = df["ts"].dt.month
    df["is_peak"] = df["hour"].apply(_is_peak)

    # --- violations & severity ---
    df["violations"] = df["violation_type"].apply(_parse_list)
    df["severity"] = df["violations"].apply(record_severity)
    df = df[df["severity"] > 0].copy()          # keep only parking-relevant records

    # --- junction presence ---
    df["junction_name"] = df["junction_name"].fillna("No Junction")
    df["has_junction"] = (df["junction_name"].str.strip().str.lower() != "no junction")

    keep = ["id", "latitude", "longitude", "location", "police_station",
            "junction_name", "has_junction", "vehicle_type", "vehicle_number", "violations",
            "severity", "ts", "date", "hour", "dow", "month", "is_peak"]
    return df[keep].reset_index(drop=True)


if __name__ == "__main__":
    d = load_clean()
    print(d.shape)
    print(d.head())
