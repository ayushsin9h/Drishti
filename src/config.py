"""Central configuration for the parking congestion-impact pipeline.

Every tunable knob lives here so the rest of the code stays declarative and
the choices are transparent (useful when you defend the design to judges).
"""
from pathlib import Path

# ---- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw" / "violations.csv"
DATA_PROCESSED = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
HOTSPOTS_PARQUET = DATA_PROCESSED / "hotspots.parquet"
FORECAST_PARQUET = DATA_PROCESSED / "forecast.parquet"
OFFENDERS_PARQUET = DATA_PROCESSED / "offenders.parquet"
TRENDS_PARQUET = DATA_PROCESSED / "trends.parquet"
TRENDS_BYDAY_PARQUET = DATA_PROCESSED / "trends_byday.parquet"
META_JSON = DATA_PROCESSED / "meta.json"
MODEL_PATH = MODELS_DIR / "lgbm_intensity.txt"

# ---- Geography (Bengaluru bounding box, for sanity filtering) --------------
LAT_MIN, LAT_MAX = 12.70, 13.40
LON_MIN, LON_MAX = 77.30, 77.90
H3_RES = 9            # ~174 m edge hexagons ~ a block / deployable patrol zone

# ---- Time ------------------------------------------------------------------
TZ = "Asia/Kolkata"
PEAK_WINDOWS = [(8, 11), (17, 20)]   # morning & evening commute hours (IST)

# ---- Severity weights: how much each violation blocks MOVING traffic -------
# Tied to physical flow disruption, not legal severity. Tune and justify.
PARKING_SEVERITY = {
    "PARKING IN A MAIN ROAD": 1.00,                 # blocks carriageway
    "PARKING NEAR ROAD CROSSING": 0.90,
    "PARKING NEAR TRAFFIC LIGHT OR ZEBRA CROSS": 0.90,
    "DOUBLE PARKING": 0.85,                          # blocks a lane
    "PARKING NEAR BUSTOP/SCHOOL/HOSPITAL ETC": 0.70,
    "PARKING OPPOSITE TO ANOTHER PARKED VEHICLE": 0.60,
    "PARKING ON FOOTPATH": 0.50,                     # pushes pedestrians to road
    "WRONG PARKING": 0.50,
    "PARKING OTHER THAN BUS STOP": 0.45,
    "NO PARKING": 0.40,
}
# Any violation not in this map contributes 0 (non-parking, e.g. number plate).

# ---- Congestion Impact Index (CII) -----------------------------------------
CII_WEIGHTS = {"volume": 0.45, "persistence": 0.30, "peak": 0.25}  # sum = 1
CII_JUNCTION_ALPHA = 0.50    # junction-proximity amplification strength

# ---- Modelling -------------------------------------------------------------
MIN_CELL_VIOLATIONS = 20     # only model cells with >= this many records
LAGS = [1, 7, 14, 28]        # day lags for the intensity forecast
ROLL_WINDOWS = [7, 28]       # rolling-window features
VALID_DAYS = 21              # last N days held out for validation
RANDOM_STATE = 42
