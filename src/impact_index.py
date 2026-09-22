"""Compute the Congestion Impact Index (CII) per hotspot cell.

CII is a transparent, rank-normalised blend of four ideas:
  - severity-weighted VOLUME   (how much weighted illegal parking happens here)
  - PERSISTENCE                (chronic every-day spot vs one-off spike)
  - PEAK-hour concentration    (bad exactly when the road is busiest)
  - junction proximity         (blocking near junctions cascades downstream)

It is explicitly a *proxy* for traffic-flow impact, derived only from
enforcement data, with every weight exposed in config.py.
"""
from src import config


def _norm(series):
    """Rank-based normalisation to [0, 1] (robust to heavy-tailed counts)."""
    return series.rank(method="average", pct=True).fillna(0.0)


def add_cii(stats):
    stats = stats.copy()
    w = config.CII_WEIGHTS

    v = _norm(stats["weighted_volume"])
    p = _norm(stats["persistence"])
    k = _norm(stats["peak_share"])

    base = w["volume"] * v + w["persistence"] * p + w["peak"] * k
    junction = stats["junction_share"].clip(0, 1)
    cii = base * (1 + config.CII_JUNCTION_ALPHA * junction)

    # scale to a friendly 0-100
    cii = (cii - cii.min()) / (cii.max() - cii.min() + 1e-9) * 100
    stats["cii"] = cii.round(1)
    stats["cii_rank"] = stats["cii"].rank(ascending=False, method="min").astype(int)

    return stats.sort_values("cii", ascending=False).reset_index(drop=True)
