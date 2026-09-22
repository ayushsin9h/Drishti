"""Aggregate cleaned records into per-H3-cell hotspot statistics."""
from collections import Counter

import pandas as pd

from src import config
from src.features import cell_to_latlng


def _mode_or_blank(series):
    s = series.dropna()
    return s.mode().iat[0] if not s.empty else ""


def _main_junction(series):
    s = series.fillna("No Junction")
    s = s[s.str.strip().str.lower() != "no junction"]
    return s.mode().iat[0] if not s.empty else ""


def _top_violation(series):
    c = Counter(v for lst in series for v in lst if v in config.PARKING_SEVERITY)
    return c.most_common(1)[0][0] if c else ""


def build_cell_stats(df, total_days):
    """One row per H3 cell with the components the CII is built from."""
    g = df.groupby("h3")
    stats = g.agg(
        n_violations=("id", "size"),
        weighted_volume=("severity", "sum"),
        active_days=("date", "nunique"),
        peak_violations=("is_peak", "sum"),
        junction_share=("has_junction", "mean"),
    )
    stats["persistence"] = stats["active_days"] / float(total_days)
    stats["peak_share"] = stats["peak_violations"] / stats["n_violations"]

    # representative centroid for each hexagon (for map centring / scatter)
    centroids = {c: cell_to_latlng(c) for c in stats.index}
    stats["lat"] = [centroids[c][0] for c in stats.index]
    stats["lon"] = [centroids[c][1] for c in stats.index]

    # human-readable context
    stats["location"] = g["location"].agg(_mode_or_blank)
    stats["police_station"] = g["police_station"].agg(_mode_or_blank)
    stats["junction_name"] = g["junction_name"].agg(_main_junction)
    stats["top_violation"] = g["violations"].agg(_top_violation)

    return stats.reset_index()
