"""Spatial (H3) indexing helpers, version-robust across h3 v3 and v4."""
import h3

from src import config


def latlng_to_cell(lat, lng, res=config.H3_RES):
    if hasattr(h3, "latlng_to_cell"):          # h3 v4
        return h3.latlng_to_cell(lat, lng, res)
    return h3.geo_to_h3(lat, lng, res)         # h3 v3


def cell_to_latlng(cell):
    if hasattr(h3, "cell_to_latlng"):          # h3 v4
        return tuple(h3.cell_to_latlng(cell))
    return tuple(h3.h3_to_geo(cell))           # h3 v3


def add_h3(df):
    """Attach an H3 cell id to every record (the unit we aggregate hotspots over)."""
    df = df.copy()
    df["h3"] = [latlng_to_cell(la, lo) for la, lo in zip(df["latitude"], df["longitude"])]
    return df
