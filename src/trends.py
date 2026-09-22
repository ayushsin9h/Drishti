"""Precompute small aggregates for the dashboard charts.

Long format -> one tiny trends.parquet the app loads for line/bar/donut charts:
  kind   ∈ {daily, hourly, vehicle, dow, vtype}
  label  the x-axis label
  value  the count
  order  sort key
"""
from collections import Counter

import pandas as pd

from src import config

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def build_trends(df):
    rows = []

    # daily time series (for the line chart)
    daily = df.groupby("date").size().reset_index(name="value").sort_values("date")
    for i, (d, v) in enumerate(zip(daily["date"], daily["value"])):
        rows.append(("daily", str(d), int(v), i))

    # hourly profile (bar)
    hourly = df.groupby("hour").size()
    for h in range(24):
        rows.append(("hourly", f"{h:02d}", int(hourly.get(h, 0)), h))

    # by vehicle type (top 10 bar)
    for i, (k, v) in enumerate(df["vehicle_type"].value_counts().head(10).items()):
        rows.append(("vehicle", str(k), int(v), i))

    # by day-of-week (bar)
    dow = df.groupby("dow").size()
    for i in range(7):
        rows.append(("dow", DOW[i], int(dow.get(i, 0)), i))

    # by violation type (donut) — only parking-relevant labels
    vt = Counter()
    for lst in df["violations"]:
        for v in lst:
            if v in config.PARKING_SEVERITY:
                vt[v] += 1
    for i, (k, c) in enumerate(vt.most_common(8)):
        rows.append(("vtype", str(k).title(), int(c), i))

    return pd.DataFrame(rows, columns=["kind", "label", "value", "order"])


def build_byday(df):
    """Per-day aggregates so charts can animate cumulatively during replay.

    Long format: date, dim ∈ {hour, vehicle}, key, value.
    """
    rows = []
    h = df.groupby(["date", "hour"]).size().reset_index(name="value")
    for _, r in h.iterrows():
        rows.append((str(r["date"]), "hour", f'{int(r["hour"]):02d}', int(r["value"])))
    v = df.groupby(["date", "vehicle_type"]).size().reset_index(name="value")
    for _, r in v.iterrows():
        rows.append((str(r["date"]), "vehicle", str(r["vehicle_type"]), int(r["value"])))
    return pd.DataFrame(rows, columns=["date", "dim", "key", "value"])
