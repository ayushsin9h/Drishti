"""Repeat-offender intelligence from the (anonymised) `vehicle_number` column.

This is the honest, data-grounded reframe of "license plate recognition": the
plate is already present in the records, so instead of OCR-from-images we surface
*chronic* offenders across time and space — something a single-snapshot CV
pipeline structurally cannot do. All IDs are anonymised, so this is privacy-safe.
"""
import pandas as pd


def _clean_plates(df):
    v = df.dropna(subset=["vehicle_number"]).copy()
    v = v[~v["vehicle_number"].astype(str).str.lower().isin(["nan", "none", ""])]
    return v


def _mode(series):
    s = series.dropna()
    return s.mode().iat[0] if not s.empty else ""


def build_offender_stats(df, top_n=500):
    """Top repeat offenders with where/what/when context."""
    v = _clean_plates(df)
    g = v.groupby("vehicle_number")
    stats = g.agg(
        n_violations=("id", "size"),
        weighted_severity=("severity", "sum"),
        n_zones=("h3", "nunique"),
        vehicle_type=("vehicle_type", _mode),
        top_location=("location", _mode),
        first_seen=("ts", "min"),
        last_seen=("ts", "max"),
    ).reset_index()
    stats["first_seen"] = stats["first_seen"].dt.date.astype(str)
    stats["last_seen"] = stats["last_seen"].dt.date.astype(str)
    stats["weighted_severity"] = stats["weighted_severity"].round(1)
    stats = stats.sort_values("n_violations", ascending=False).reset_index(drop=True)
    stats["rank"] = stats.index + 1
    return stats.head(top_n)


def offender_summary(df):
    """Headline KPIs about repeat offending."""
    v = _clean_plates(df)
    counts = v["vehicle_number"].value_counts()
    repeat = counts[counts >= 2]
    return dict(
        distinct_vehicles=int(counts.size),
        repeat_offenders=int(repeat.size),
        repeat_share_pct=round(100 * repeat.sum() / len(v), 1),
        worst_count=int(counts.max()),
    )
