"""Run the full offline pipeline: raw CSV -> small artifacts the app serves.

    python -m src.build_artifacts        # run from the repo root

Outputs:
    data/processed/hotspots.parquet      per-cell stats + CII
    data/processed/forecast.parquet      next-day predicted intensity per cell
    data/processed/meta.json             config, date range, model metrics
    models/lgbm_intensity.txt            saved LightGBM model
"""
import json

from src import config
from src.data_prep import load_clean
from src.features import add_h3
from src.hotspots import build_cell_stats
from src.impact_index import add_cii
from src.model import train_and_forecast
from src.offenders import build_offender_stats, offender_summary
from src.trends import build_trends, build_byday


def main():
    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] Loading & cleaning ...")
    df = load_clean()
    print(f"      clean parking records: {len(df):,}")

    df = add_h3(df)
    total_days = (df["ts"].dt.date.max() - df["ts"].dt.date.min()).days + 1

    print("[2/4] Building hotspot stats & CII ...")
    stats = add_cii(build_cell_stats(df, total_days))
    stats.to_parquet(config.HOTSPOTS_PARQUET, index=False)
    print(f"      {len(stats):,} cells -> {config.HOTSPOTS_PARQUET.name}")

    print("[2b] Repeat-offender intelligence ...")
    offenders = build_offender_stats(df, top_n=500)
    offenders.to_parquet(config.OFFENDERS_PARQUET, index=False)
    off_summary = offender_summary(df)
    print(f"      {len(offenders):,} offenders -> {config.OFFENDERS_PARQUET.name} | {off_summary}")

    print("[2c] Trend aggregates ...")
    build_trends(df).to_parquet(config.TRENDS_PARQUET, index=False)
    build_byday(df).to_parquet(config.TRENDS_BYDAY_PARQUET, index=False)
    print(f"      -> {config.TRENDS_PARQUET.name}, {config.TRENDS_BYDAY_PARQUET.name}")

    print("[3/4] Training LightGBM & forecasting ...")
    model, forecast, metrics = train_and_forecast(df)
    model.save_model(str(config.MODEL_PATH))
    forecast.to_parquet(config.FORECAST_PARQUET, index=False)
    print(f"      {len(forecast):,} cells -> {config.FORECAST_PARQUET.name}")
    print(f"      metrics: {metrics}")

    print("[4/4] Writing meta.json ...")
    # small real daily series for the KPI sparklines
    dord = sorted(df["date"].unique())
    gd = df.groupby("date")
    kpi_sparks = dict(
        violations=gd["id"].size().reindex(dord, fill_value=0).astype(int).tolist(),
        zones=gd["h3"].nunique().reindex(dord, fill_value=0).astype(int).tolist(),
        peak=(df[df["is_peak"]].groupby("date")["id"].size()
              .reindex(dord, fill_value=0).astype(int).tolist()),
    )
    meta = dict(
        date_range=[df["ts"].dt.date.min().isoformat(),
                    df["ts"].dt.date.max().isoformat()],
        total_days=total_days,
        n_records=int(len(df)),
        n_cells=int(len(stats)),
        h3_res=config.H3_RES,
        severity_weights=config.PARKING_SEVERITY,
        cii_weights=config.CII_WEIGHTS,
        cii_junction_alpha=config.CII_JUNCTION_ALPHA,
        offender_summary=off_summary,
        model_metrics=metrics,
        kpi_sparks=kpi_sparks,
    )
    config.META_JSON.write_text(json.dumps(meta, indent=2))
    print(f"      -> {config.META_JSON.name}")
    print("Done. You can now run:  streamlit run app.py")


if __name__ == "__main__":
    main()
